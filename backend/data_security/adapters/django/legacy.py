"""Phase-1 compatibility by default; explicit delegates fail closed on errors."""
from collections.abc import Callable
import re

from data_security.contracts import ContractViolation, ReasonCode
from data_security.contracts.schema import require

# One copy of the original business patterns, also supplied to the explicit
# phase-2 delegate by B. These are not registered with the three-category Detect.
LEGACY_SECRET = (
    (re.compile(r'AKIA[0-9A-Z]{16}'), 'AWS Access Key'),
    (re.compile(r'sk-[a-zA-Z0-9]{48}'), 'OpenAI API Key'),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), 'GitHub Token'),
    (re.compile(r'-----BEGIN\s+(RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'), '私钥文件'),
    (re.compile(r'''password\s*[:=]\s*[\'"\w!@#$%^&*()+-]{8,}'''), '密码明文'),
)
LEGACY_TOKEN = re.compile(r'(?i)(authorization|token|password|secret|cookie)\s*[:=]\s*[^\s,;]+')
LEGACY_INTERNAL = (
    (re.compile(r'10\.\d{1,3}\.\d{1,3}\.\d{1,3}'), '内网IP段 10.x.x.x'),
    (re.compile(r'172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}'), '内网IP段 172.16-31.x.x'),
    (re.compile(r'192\.168\.\d{1,3}\.\d{1,3}'), '内网IP段 192.168.x.x'),
    (re.compile(r'127\.\d{1,3}\.\d{1,3}\.\d{1,3}'), '本地回环地址'),
)

_confidentiality: Callable[[str, str], tuple[str, tuple[str, ...]]] | None = None


def baseline_confidentiality(text, profile):
    """Preserve phase-1 substitutions; truncation and prompt/flag rules stay outside."""
    if profile == 'legal-v1':
        return LEGACY_TOKEN.sub(r'\1=[REDACTED]', text), ()
    warnings = []
    for pattern, name in LEGACY_SECRET:
        if pattern.search(text):
            text = pattern.sub('[' + name + ' 已过滤]', text)
            warnings.append('检测到真实' + name + '，已过滤')
    for pattern, name in LEGACY_INTERNAL:
        if pattern.search(text):
            text = pattern.sub('[内网地址 已过滤]', text)
            warnings.append('检测到' + name + '，已过滤')
    return text, tuple(warnings)


def bind_confidentiality(protect: Callable[[str, str], tuple[str, tuple[str, ...]]]):
    global _confidentiality
    require(callable(protect), ReasonCode.INVALID_TYPE)
    _confidentiality = protect


def protect_legacy(text, profile) -> tuple[str, tuple[str, ...]] | None:
    # None means unbound, not a failed call. Only the former uses the baseline.
    if _confidentiality is None:
        return None
    try:
        result = _confidentiality(text, profile)
        require(type(result) is tuple and len(result) == 2 and type(result[0]) is str and
                type(result[1]) is tuple and all(type(v) is str for v in result[1]), ReasonCode.INVALID_TYPE)
        return result
    except Exception:
        raise ContractViolation(ReasonCode.SCOPE_INCOMPLETE) from None
