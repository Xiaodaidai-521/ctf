"""The normal application's versioned display/summary/export redaction policy."""
import re
from data_security.core.redaction import EMAIL, IPV4

POLICY_VERSION = 'personal-data-v1'
_PHONE = re.compile(r'(?<!\d)(?:\+?86[ -]?)?1[3-9]\d{9}(?!\d)')
_IDENTITY = re.compile(r'(?<![\dA-Za-z])\d{17}[\dXx](?![\dA-Za-z])')
_ACCOUNT = re.compile(r'(?<!\d)\d{13,19}(?!\d)')
_CREDENTIAL = re.compile(
    r'''(?i)(?P<key>["']?\b(?:password|passwd|token|secret|api[_-]?key|authorization|cookie)\b["']?\s*[:=]\s*)'''
    r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|(?:Bearer\s+)?[^\s,;]+)''')
_PRIVATE_KEY = re.compile(r'-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----.*?-----END (?:[A-Z ]+)?PRIVATE KEY-----', re.S)
_SENSITIVE_KEYS = frozenset(('email', 'phone', 'mobile', 'telephone', 'id_card', 'id_number',
    'identity_number', 'password', 'passwd', 'token', 'access_token', 'refresh_token', 'api_key',
    'secret', 'authorization', 'cookie', '姓名', '身份证', '身份证号', '手机号', '电话', '邮箱', '住址', 'address', 'real_name', 'full_name'))


def redact(value):
    if isinstance(value, dict):
        return {str(redact(key)): '[REDACTED]' if str(key).lower() in _SENSITIVE_KEYS else redact(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    value = _PRIVATE_KEY.sub('[REDACTED]', value)
    value = _CREDENTIAL.sub(lambda match: match.group('key') + '[REDACTED]', value)
    for pattern in (EMAIL, _IDENTITY, _PHONE, _ACCOUNT, IPV4):
        value = pattern.sub('[REDACTED]', value)
    return value
