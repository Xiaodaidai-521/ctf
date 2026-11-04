"""Local lexical ranking of already-authorized chunks, with no model or I/O.

Overlapping Chinese bigrams avoid the old even/odd character boundary loss.
Small, explicit terminology groups bridge common course paraphrases; these are
lexical aliases, not semantic embeddings and not an authorization signal.
"""
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

RANKING_VERSION = 'm3-lexical-bm25-1'

# Keep these auditable: broad concepts such as privacy and security are not synonyms.
ALIASES = (
    ('授权', '许可', '允许', '准许'),
    ('认证', '身份验证', '验证身份', 'authentication'),
    ('口令', '密码', 'password'),
    ('个人信息', '个人资料', '个人数据', 'personal data'),
    ('最小必要', '最少够用', '仅收集必需', '数据最小化'),
    ('脱敏', '掩码', '遮盖敏感字段', 'masking'),
    ('留存', '保存期限', '存多久', '保留多久'),
    ('删除', '清除', '移除'),
    ('加密', '密文', 'encryption'),
    ('审计', '操作记录', 'audit'),
    ('备份', '备份副本', 'backup'),
    ('越权', '超出权限', '超越权限'),
    ('哈希', '散列', 'hash'),
    ('参数化查询', '预编译查询', 'prepared statement'),
    ('跨站脚本', 'xss'),
    ('跨站请求伪造', 'csrf'),
    ('多因素', '双因素', '两步验证', '二次验证', 'mfa', '2fa'),
)
STOP_BIGRAMS = frozenset({
    '什么', '怎么', '如何', '为何', '为什', '么要', '是否', '哪些', '一下',
    '请问', '可以', '应该', '需要', '进行', '一个', '这个', '那个', '我们',
    '他们', '时候', '的是', '的时', '以及', '如果', '怎样',
})
TOKEN_PATTERN = re.compile(r'[a-z0-9_]+|[㐀-鿿]+')


@dataclass(frozen=True)
class Candidate:
    id: int
    title: str
    text: str


def _normalize(text):
    return unicodedata.normalize('NFKC', text).lower()


def features(text):
    text = _normalize(text)
    counts = Counter()
    for match in TOKEN_PATTERN.finditer(text):
        token = match.group()
        if token[0].isascii():
            counts['word:' + token] += 1
        else:
            for index in range(len(token) - 1):
                pair = token[index:index + 2]
                if pair not in STOP_BIGRAMS:
                    counts['pair:' + pair] += 1
    for index, aliases in enumerate(ALIASES):
        for alias in aliases:
            present = (re.search(r'(?<![a-z0-9_])' + re.escape(alias) + r'(?![a-z0-9_])', text)
                       if alias.isascii() else alias in text)
            if present:
                counts[f'alias:{index}'] = 1
                break
    return counts


def rank_candidates(candidates, query, limit=12):
    """Return IDs only. Callers own filtering before ranking and reauthorization."""
    candidates = list(candidates)
    if limit <= 0 or not candidates:
        return []
    if not query.strip():
        return sorted(item.id for item in candidates)[:limit]
    terms = features(query)
    if not terms:
        return []
    documents = []
    frequencies = Counter()
    for item in candidates:
        counts = features(item.text)
        counts.update({term: count * 2 for term, count in features(item.title).items()})
        documents.append((item.id, counts))
        frequencies.update(counts.keys())
    average_length = sum(sum(counts.values()) for _, counts in documents) / len(documents) or 1
    ranked = []
    for pk, counts in documents:
        length = sum(counts.values())
        score = 0.0
        for term in terms.keys() & counts.keys():
            idf = math.log1p((len(documents) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            tf = counts[term]
            weight = 1.5 if term.startswith('alias:') else 1.0
            score += weight * idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / average_length))
        if score:
            ranked.append((score, pk))
    return [pk for _, pk in sorted(ranked, key=lambda row: (-row[0], row[1]))[:limit]]
