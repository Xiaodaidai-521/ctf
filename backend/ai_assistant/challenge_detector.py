"""Challenge detection utilities for multi-agent chat.

The detector supports:
1. explicit challenge numbers, such as "第46题", "46题", "challenge 46";
2. fuzzy matching by title, category, description, and hint.
"""

import re
from typing import List, Optional, Tuple

from challenges.models import Challenge


CHALLENGE_KEYWORDS = [
    '题目', '题', 'flag', 'ctf', '怎么', '如何', '解题', 'solve',
    'challenge', 'hint', '提示', 'web', 'pwn', 'reverse', 'crypto',
    'misc', 'forensics', 'sql', '注入', 'xss', 'csrf', 'ssrf', 'rce',
    '文件上传', '反序列化', '溢出', 'rop', '逆向', '加密', '隐写',
    '流量分析', '缓存', 'cors',
]


CHALLENGE_ID_PATTERNS = [
    r'第\s*(\d+)\s*题',
    r'题目\s*(\d+)',
    r'题\s*(\d+)',
    r'(\d+)\s*题',
    r'挑战\s*(\d+)',
    r'challenge\s*#?\s*(\d+)',
    r'#\s*(\d+)',
    r'id[=:\s#]*(\d+)',
]


STOP_WORDS = {
    '怎么', '如何', '一下', '这个', '那个', '题目', '挑战', '解题', '提示',
    '请问', '帮我', '帮忙', '分析', '回答', '讲讲', '理解', '工作原理',
    'ctf', 'challenge',
}


def is_challenge_related(message: str) -> bool:
    """Return whether the message looks related to a challenge."""
    msg_lower = (message or '').lower()
    if extract_challenge_id(message):
        return True
    return any(keyword in msg_lower for keyword in CHALLENGE_KEYWORDS)


def extract_challenge_id(message: str) -> Optional[int]:
    """Extract a challenge id from natural language."""
    text = message or ''
    for pattern in CHALLENGE_ID_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        try:
            return int(match.group(1))
        except (TypeError, ValueError, IndexError):
            continue
    return None


def _extract_keywords(message: str) -> List[str]:
    words = re.findall(r'[\u4e00-\u9fff]{2,20}|[a-zA-Z0-9_+#.-]{2,40}', message or '')
    keywords = []
    seen = set()
    for word in words:
        value = word.strip().lower()
        if not value or value in STOP_WORDS or value in seen:
            continue
        seen.add(value)
        keywords.append(value)
    return keywords[:12]


def _challenge_to_info(challenge: Challenge, match_score: Optional[float] = None) -> dict:
    info = {
        'id': challenge.id,
        'title': challenge.title,
        'category': challenge.category.name if challenge.category else None,
        'category_name': challenge.category.name if challenge.category else '未知',
        'difficulty': challenge.difficulty,
        'description': challenge.description,
        'hint': challenge.hint,
    }
    if match_score is not None:
        info['match_score'] = round(match_score, 2)
    return info


def match_challenge_by_description(message: str, user_id: int = None) -> Optional[dict]:
    """Fuzzy-match an active challenge by user text."""
    keywords = _extract_keywords(message)
    if not keywords:
        return None

    best_match = None
    best_score = 0.0
    for challenge in Challenge.objects.filter(is_active=True).select_related('category'):
        fields = {
            'title': challenge.title or '',
            'description': challenge.description or '',
            'category': challenge.category.name if challenge.category else '',
            'hint': challenge.hint or '',
        }
        haystack = ' '.join(fields.values()).lower()
        score = 0
        for keyword in keywords:
            if keyword in fields['title'].lower():
                score += 8
            if keyword in fields['category'].lower():
                score += 4
            if keyword in fields['description'].lower():
                score += 2
            if keyword in fields['hint'].lower():
                score += 1
        normalized_score = score / max(len(keywords) * 8, 1)
        if keyword_count := sum(1 for keyword in keywords if keyword in haystack):
            normalized_score += min(keyword_count / len(keywords), 1) * 0.25
        if normalized_score > best_score:
            best_score = normalized_score
            best_match = challenge

    if best_match and best_score >= 0.18:
        return _challenge_to_info(best_match, best_score)
    return None


def detect_challenge(message: str, user_id: int = None) -> Tuple[Optional[dict], Optional[str]]:
    """Detect challenge context from a user message."""
    challenge_id = extract_challenge_id(message)
    if challenge_id:
        try:
            challenge = Challenge.objects.select_related('category').get(
                id=challenge_id,
                is_active=True,
            )
            return _challenge_to_info(challenge), 'id'
        except Challenge.DoesNotExist:
            pass

    if is_challenge_related(message) or _extract_keywords(message):
        match_result = match_challenge_by_description(message, user_id)
        if match_result:
            return match_result, 'description'

    return None, None


def auto_select_agents(challenge_info: dict) -> List[str]:
    """Select useful agents based on challenge category."""
    category = (challenge_info.get('category') or challenge_info.get('category_name') or '').lower()
    default_agents = ['analyst', 'security', 'developer']
    agent_map = {
        'web': ['analyst', 'security', 'developer'],
        'pwn': ['analyst', 'developer', 'security'],
        'reverse': ['analyst', 'developer', 'security'],
        'crypto': ['analyst', 'developer'],
        'forensics': ['analyst', 'developer', 'tester'],
        'misc': ['analyst', 'developer', 'tester'],
    }
    return agent_map.get(category, default_agents)


def build_challenge_context(challenge_info: dict) -> str:
    """Format detected challenge info as model context."""
    return (
        "当前正在讨论的 CTF 题目信息：\n"
        f"题目ID：{challenge_info.get('id', '未知')}\n"
        f"标题：{challenge_info.get('title', '未知')}\n"
        f"分类：{challenge_info.get('category_name', '未知')}\n"
        f"难度：{challenge_info.get('difficulty', '未知')}\n\n"
        f"题目描述：{challenge_info.get('description', '无描述')}\n\n"
        f"提示：{challenge_info.get('hint', '无提示')}"
    )
