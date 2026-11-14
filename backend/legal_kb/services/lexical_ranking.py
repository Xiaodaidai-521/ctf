"""BM25 ranking for authorized knowledge chunks, without character-vector recall.

Source titles are supplied by the caller after visibility filtering. Terminology
aliases are explicit lexical equivalences, not inferred semantics or permissions.
"""

from collections import Counter
from functools import lru_cache
import math
import re
import unicodedata

from learning_knowledge.ranking import ALIASES, features


RANKING_VERSION = 'kb-lexical-bm25-1'
DOMAIN_ALIASES = (
    ('sql injection', 'sql注入', 'sql 注入'),
    ('cross site scripting', 'cross-site scripting', '跨站脚本', 'xss'),
    ('cross site request forgery', 'cross-site request forgery', '跨站请求伪造', 'csrf'),
    ('server side request forgery', 'server-side request forgery', '服务端请求伪造', 'ssrf'),
    ('xml external entity', 'xml外部实体', 'xml 外部实体', 'xxe'),
    ('prompt injection', '提示词注入', '提示注入'),
    ('zero trust', '零信任'),
    ('cryptographic storage', '加密存储'),
    ('跨境', '出境', '境外'),
    ('跨境提供', '境外提供'),
    ('防护', '防御', '预防', '防范', 'prevention', 'defense'),
)


def normalize(text):
    return unicodedata.normalize('NFKC', str(text or '')).casefold()


def query_text(text):
    value = normalize(text)
    value = re.sub(r'需要|什么|如何|哪些|请问|怎么|是否', ' ', value)
    # Do not create imaginary Chinese pairs across known terminology units or
    # across an interrogative. This also keeps coverage useful in tiny corpora.
    aliases = {alias for group in ALIASES for alias in group if not alias.isascii()}
    for alias in sorted(aliases, key=lambda value: (-len(value), value)):
        value = value.replace(alias, f' {alias} ')
    return ' '.join(value.split())


@lru_cache(maxsize=8192)
def terms(text):
    counts = features(text)
    value = normalize(text)
    for index, aliases in enumerate(DOMAIN_ALIASES):
        if any(re.search(r'(?<![a-z0-9_])' + re.escape(alias) + r'(?![a-z0-9_])', value)
               if alias.isascii() else alias in value for alias in aliases):
            counts[f'domain:{index}'] = 1
            # Canonical bilingual features prevent an abbreviation-only title
            # from gaining an extra alias signal over its spelled-out equivalent.
            for key in features(' '.join(aliases)):
                counts[key] = max(1, counts[key])
    return counts


def rank_chunks(items, query, source_titles=None):
    """Return (item, score, query coverage) sorted by relevant lexical evidence.

    No match means no result, regardless of any stored deterministic vector.
    BM25 uses all authorized candidates to retain rare-term discrimination.
    """
    source_titles = source_titles or {}
    query_terms = terms(query_text(query))
    query_domains = {key for key in query_terms if key.startswith('domain:')}
    primary_domains = query_domains - {f'domain:{len(DOMAIN_ALIASES) - 1}'}
    if not query_terms:
        return []
    documents = []
    frequencies = Counter()
    phrase = ' '.join(normalize(query).split())
    for item in items:
        title = source_titles.get(item.id, item.title)
        body = terms(item.text)
        title_terms = terms(title)
        counts = body.copy()
        counts.update({key: value * 2 for key, value in title_terms.items()})
        # Legal provisions typically state their operative rule before listing
        # details. Weight that opening field separately from long enumerations.
        if item.source_type == 'legal_clause':
            opening = item.text.split('\n\n', 1)[0]
            counts.update({key: value * 3 for key, value in terms(opening).items()})
        documents.append((item, title, counts))
        frequencies.update(counts.keys())
    if not documents:
        return []
    average_length = sum(sum(counts.values()) for _, _, counts in documents) / len(documents) or 1
    query_weight = {key: math.log1p((len(documents) - frequencies[key] + .5) / (frequencies[key] + .5))
                    for key in query_terms}
    total_weight = sum(query_weight.values()) or 1
    ranked = []
    for item, title, counts in documents:
        overlap = query_terms.keys() & counts.keys()
        if not overlap:
            continue
        if primary_domains and not primary_domains.intersection(overlap):
            continue
        coverage = sum(query_weight[key] for key in overlap) / total_weight
        # A single incidental bigram or a generic word cannot answer a long
        # multi-term question. Explicit terminology aliases may bridge languages.
        domain_match = bool(primary_domains.intersection(overlap))
        if coverage < .25 and not domain_match:
            continue
        length = sum(counts.values())
        score = sum(query_weight[key] * (1.5 if key.startswith(('domain:', 'alias:')) else 1)
                    * counts[key] * 2.2 / (counts[key] + 1.2 * (.25 + .75 * length / average_length))
                    for key in overlap)
        score *= .5 + coverage
        title_value = ' '.join(normalize(title).split())
        body_value = ' '.join(normalize(item.text).split())
        if phrase and phrase == title_value:
            score += total_weight * 4
        elif phrase and phrase in title_value:
            score += total_weight * 2
        if phrase and phrase in body_value:
            score += total_weight
            # Early definitions and operative text beat a passing reference in
            # a long provision. This applies to any phrase, not named test laws.
            if phrase in body_value[:160]:
                score += total_weight * .5
        # A translated operative phrase early in a provision is stronger than
        # a passing territorial reference later in the same document.
        for index, aliases in enumerate(DOMAIN_ALIASES):
            if f'domain:{index}' in query_domains and any(alias in body_value[:160] for alias in aliases):
                score += query_weight[f'domain:{index}'] * 2
        ranked.append((item, score, coverage))
    return sorted(ranked, key=lambda row: (-row[1], row[0].id))
