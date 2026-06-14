"""
AI 安全模块 - 多层安全防护
包含：Prompt注入检测、输出过滤、多AI一致性校验、安全审计

创新点：多AI协同安全校验机制
- 输入层：Prompt注入检测 + 系统提示词篡改识别
- 校验层：多AI交叉验证一致性投票
- 输出层：内容脱敏 + 合规审核
"""

import os, re, time, hashlib, hmac, logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import IntEnum
from collections import defaultdict, Counter
import threading
from django.conf import settings

class SecurityLevel(IntEnum):
    SAFE = 0
    WARNING = 1
    SUSPICIOUS = 2
    BLOCKED = 3

@dataclass
class SecurityCheckResult:
    level: SecurityLevel
    reason: str
    detail: str = ""
    matched_pattern: str = ""
    confidence: float = 0.0

    @property
    def is_blocked(self) -> bool:
        return self.level >= SecurityLevel.BLOCKED

    @property
    def is_safe(self) -> bool:
        return self.level == SecurityLevel.SAFE

@dataclass
class MultiAIValidationResult:
    is_consistent: bool
    consistency_score: float
    responses: List[Dict] = field(default_factory=list)
    agreement_ratio: float = 0.0
    risk_level: SecurityLevel = SecurityLevel.SAFE
    alert_messages: List[str] = field(default_factory=list)
    trusted_response: Optional[Dict] = None

@dataclass
class SecurityAuditRecord:
    timestamp: str
    event_type: str
    user_id: Optional[int]
    ip_address: str
    input_preview: str
    result: SecurityLevel
    detail: str
    providers_used: List[str] = field(default_factory=list)


# ============================================================
# 第一层：Prompt 安全检查器 - 注入检测 + 越狱检测
# ============================================================

class PromptSecurityChecker:
    """Prompt 安全检查器 - 检测注入攻击、越狱指令"""

    INJECTION_PATTERNS = [
        # 角色扮演绕过
        (r"(?i)(forget|ignore|disregard)\s+(all\s+)?(previous|system|prompt|instruct)", 0.95),
        (r"(?i)you\s+are\s+now\s+", 0.8),
        (r"(?i)pretend\s+you\s+(are|have)", 0.7),
        (r"(?i)new\s+(system\s+)?(prompt|instruction)", 0.85),
        (r"(?i) DAN\s", 0.9),
        (r"(?i)developer\s+mode", 0.9),
        (r"(?i)jailbreak", 0.95),
        # 指令覆盖
        (r"(?i)disable\s+(your\s+)?(safety|filter|restriction)", 0.95),
        (r"(?i)bypass\s+(your\s+)?(safety|policy|restriction)", 0.9),
        (r"(?i)override\s+(your\s+)?(instruction|system)", 0.85),
        (r"(?i)remove\s+(your\s+)?(limit|constraint)", 0.9),
        # 系统指令注入
        (r"(?i)<\|?(system|user|assistant\|?)>", 0.75),
        (r"(?i)\[INST\]\s*\[/INST\]", 0.8),
        (r"(?i){{(system|user)}}", 0.7),
        # 越狱关键词
        (r"(?i)reveal\s+(your\s+)?(underlying|real|actual)\s+(instruction|system|prompt)", 0.9),
        (r"(?i)print\s+(all\s+)?(your\s+)?(system\s+)?(prompt|instruction)", 0.9),
        (r"(?i)output\s+(your\s+)?(entire|complete)\s+(system\s+)?prompt", 0.95),
        (r"(?i)(show|tell|repeat|dump|export|copy)\s+(me\s+)?(your\s+)?(system|developer|hidden|internal)\s+(prompt|instruction|rules?)", 0.95),
        (r"(?i)what\s+(are|is)\s+(your\s+)?(system|developer|hidden|internal)\s+(prompt|instruction|rules?)", 0.9),
        (r"(?i)verbatim\s+(system|developer|hidden|internal)\s+(prompt|instruction|rules?)", 0.95),
        (r"(系统|开发者|隐藏|内部|初始|上面|前面).{0,12}(提示词|指令|规则|设定|人设|prompt)", 0.95),
        (r"(复述|逐字|原文|完整|全部|打印|输出|展示|透露|泄露|告诉我).{0,12}(提示词|指令|规则|设定|人设|prompt)", 0.95),
        (r"(忽略|忘记|无视|覆盖|绕过).{0,12}(之前|上面|系统|开发者|安全|限制|约束)", 0.95),
    ]

    def __init__(self):
        self._compiled = [
            (re.compile(p, re.DOTALL), c) for p, c in self.INJECTION_PATTERNS
        ]

    def check(self, text: str) -> SecurityCheckResult:
        """检查输入是否包含恶意注入"""
        if not text:
            return SecurityCheckResult(SecurityLevel.SAFE, "空输入")
        for pattern, confidence in self._compiled:
            m = pattern.search(text)
            if m:
                return SecurityCheckResult(
                    level=SecurityLevel.BLOCKED if confidence > 0.9 else SecurityLevel.SUSPICIOUS,
                    reason="检测到提示词注入攻击",
                    detail="匹配内容: " + m.group(0)[:50],
                    matched_pattern=pattern.pattern[:50],
                    confidence=confidence
                )
        return SecurityCheckResult(SecurityLevel.SAFE, "检查通过")


# ============================================================
# 第二层：输出脱敏器 - 过滤真实密钥 / 内网地址
# ============================================================

class OutputSanitizer:
    """AI 输出内容脱敏器"""

    SECRET_PATTERNS = [
        (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
        (r"sk-[a-zA-Z0-9]{48}", "OpenAI API Key"),
        (r"ghp_[a-zA-Z0-9]{36}", "GitHub Token"),
        (r"-----BEGIN\s+(RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "私钥文件"),
        (r"password\s*[:=]\s*[\'\"\w!@#$%^&*()+-]{8,}", "密码明文"),
    ]

    INTERNAL_IP_PATTERNS = [
        (r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}", "内网IP段 10.x.x.x"),
        (r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}", "内网IP段 172.16-31.x.x"),
        (r"192\.168\.\d{1,3}\.\d{1,3}", "内网IP段 192.168.x.x"),
        (r"127\.\d{1,3}\.\d{1,3}\.\d{1,3}", "本地回环地址"),
    ]

    PROMPT_LEAK_PATTERNS = [
        (
            r"(?is)(system|developer|hidden|internal)\s+(prompt|instruction|message|rules?)\s*[:：].{0,2000}",
            "疑似英文内部提示词回显",
        ),
        (
            r"(?s)(系统|开发者|隐藏|内部|初始)(提示词|指令|消息|规则|设定)\s*[:：].{0,2000}",
            "疑似中文内部提示词回显",
        ),
        (
            r"(?s)(你是|我是).{0,80}(智能体|AI|助手).{0,120}(核心能力|口头禅|风格|约束|职责)\s*[:：]?.{0,2000}",
            "疑似智能体设定回显",
        ),
        (
            r"(?s)(以下是|下面是|我的)(系统提示词|内部指令|隐藏规则|完整设定).{0,2000}",
            "疑似提示词泄露说明",
        ),
    ]

    def __init__(self):
        self._secrets = [(re.compile(p), n) for p, n in self.SECRET_PATTERNS]
        self._internal = [(re.compile(p), n) for p, n in self.INTERNAL_IP_PATTERNS]
        self._prompt_leaks = [(re.compile(p), n) for p, n in self.PROMPT_LEAK_PATTERNS]

    def sanitize(self, text: str) -> Tuple[str, List[str]]:
        """脱敏并返回告警列表"""
        warnings = []
        result = text
        for pattern, name in self._secrets:
            if pattern.search(result):
                result = pattern.sub("[" + name + " 已过滤]", result)
                warnings.append("检测到真实" + name + "，已过滤")
        for pattern, name in self._internal:
            if pattern.search(result):
                result = pattern.sub("[内网地址 已过滤]", result)
                warnings.append("检测到" + name + "，已过滤")
        for pattern, name in self._prompt_leaks:
            if pattern.search(result):
                result = pattern.sub(
                    "我不能透露系统提示词、内部规则或隐藏设定。可以直接告诉我你想解决的问题，我会按当前身份继续帮你分析。",
                    result,
                )
                warnings.append("检测到" + name + "，已过滤")
        return result, warnings


# ============================================================
# 第三层：多AI一致性校验器 - 核心创新点
# ============================================================

class MultiAIValidator:
    """
    多AI一致性校验器 - 核心创新

    同时调用多个AI，对比结果一致性：
    - 完全一致（3/3相同） -> 高可信，直接返回
    - 部分一致（2/3相同） -> 中可信，标记后返回
    - 完全分歧（各说各的） -> 低可信，拦截+告警

    对比传统方案：
    - 传统：选最好的一个AI用
    - 本方案：多AI互相背书，用一致性换可信度
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def validate(self, responses: List[Dict]) -> MultiAIValidationResult:
        if len(responses) < 2:
            return MultiAIValidationResult(
                is_consistent=True,
                consistency_score=1.0,
                responses=responses,
                agreement_ratio=1.0,
            )

        contents = [r.get('content', '') for r in responses]
        providers = [r.get('provider', 'unknown') for r in responses]
        normalized = [self._normalize(c) for c in contents]

        consistency_score = self._calculate_consistency(normalized)
        agreement_ratio = self._calculate_agreement(normalized)
        risk_level, alerts = self._assess_risk(consistency_score, agreement_ratio, contents, providers)
        trusted = self._select_trusted_response(responses, normalized)

        return MultiAIValidationResult(
            is_consistent=consistency_score >= 0.7,
            consistency_score=consistency_score,
            responses=responses,
            agreement_ratio=agreement_ratio,
            risk_level=risk_level,
            alert_messages=alerts,
            trusted_response=trusted,
        )

    def _normalize(self, text: str) -> str:
        t = text.lower().strip()
        t = re.sub(r"\s+", "", t)
        t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
        return t

    def _similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        set_a = set(a)
        set_b = set(b)
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def _calculate_consistency(self, normalized: List[str]) -> float:
        if len(set(normalized)) == 1:
            return 1.0
        total_sim = 0.0
        pairs = 0
        for i in range(len(normalized)):
            for j in range(i + 1, len(normalized)):
                total_sim += self._similarity(normalized[i], normalized[j])
                pairs += 1
        return total_sim / pairs if pairs > 0 else 0.0

    def _calculate_agreement(self, normalized: List[str]) -> float:
        if not normalized:
            return 0.0
        counts = Counter(normalized)
        most_common_count = counts.most_common(1)[0][1]
        return most_common_count / len(normalized)

    def _assess_risk(
        self,
        consistency_score: float,
        agreement_ratio: float,
        contents: List[str],
        providers: List[str]
    ) -> Tuple[SecurityLevel, List[str]]:
        alerts = []
        if consistency_score >= 0.85 and agreement_ratio >= 0.8:
            return SecurityLevel.SAFE, ["多AI验证通过：高一致性"]
        if consistency_score >= 0.6:
            alerts.append("多AI存在分歧（一致率" + f"{consistency_score:.0%}" + "），建议人工复核")
            return SecurityLevel.WARNING, alerts
        alerts.append("多AI响应完全分歧（一致率" + f"{consistency_score:.0%}" + "），已拦截并告警")
        alerts.append("调用厂商：" + ", ".join(providers))
        short_responses = [c for c in contents if len(c) < 30]
        if short_responses:
            alerts.append("警告：" + str(len(short_responses)) + "个响应过短，可能调用失败")
        return SecurityLevel.BLOCKED, alerts

    def _select_trusted_response(
        self,
        responses: List[Dict],
        normalized: List[str]
    ) -> Optional[Dict]:
        if not responses:
            return None
        if len(set(normalized)) == 1:
            return responses[0]
        scored = []
        for i, r in enumerate(responses):
            content = r.get('content', '')
            score = len(content)
            if 50 < len(content) < 2000:
                score *= 1.5
            scored.append((score, i))
        scored.sort(reverse=True)
        return responses[scored[0][1]]


# ============================================================
# 第四层：安全审计日志记录器
# ============================================================

class SecurityAuditLogger:
    def __init__(self):
        self.logger = logging.getLogger('ai_security')
        self._lock = threading.Lock()
        self._recent: List[SecurityAuditRecord] = []
        self._max_recent = 100

    def log(self, record: SecurityAuditRecord):
        with self._lock:
            self._recent.append(record)
            if len(self._recent) > self._max_recent:
                self._recent.pop(0)
        log_msg = "[" + record.event_type + "] " + record.result.name + " | user=" + str(record.user_id) + " ip=" + record.ip_address + " | " + record.detail
        if record.result >= SecurityLevel.WARNING:
            self.logger.warning(log_msg)
        else:
            self.logger.info(log_msg)

    def get_recent(self, limit: int = 20) -> List[SecurityAuditRecord]:
        with self._lock:
            return list(self._recent[-limit:])


# ============================================================
# 全局单例
# ============================================================

_prompt_checker: Optional[PromptSecurityChecker] = None
_output_sanitizer: Optional[OutputSanitizer] = None
_multi_ai_validator: Optional[MultiAIValidator] = None
_audit_logger: Optional[SecurityAuditLogger] = None

def get_prompt_checker() -> PromptSecurityChecker:
    global _prompt_checker
    if _prompt_checker is None:
        _prompt_checker = PromptSecurityChecker()
    return _prompt_checker

def get_output_sanitizer() -> OutputSanitizer:
    global _output_sanitizer
    if _output_sanitizer is None:
        _output_sanitizer = OutputSanitizer()
    return _output_sanitizer

def get_multi_ai_validator() -> MultiAIValidator:
    global _multi_ai_validator
    if _multi_ai_validator is None:
        _multi_ai_validator = MultiAIValidator()
    return _multi_ai_validator

def get_audit_logger() -> SecurityAuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = SecurityAuditLogger()
    return _audit_logger


# ============================================================
# API签名验证（网关层）
# ============================================================

class RequestSigner:
    """
    HMAC-SHA256 请求签名验证

    前端请求需携带：
    - X-Api-Timestamp: 时间戳（Unix秒）
    - X-Api-Signature: HMAC-SHA256签名
    - 签名 = HMAC-SHA256(request_body + timestamp + secret_key)

    5分钟内有效，超时拒绝
    """

    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or os.getenv('AI_API_SECRET') or settings.SECRET_KEY

    def sign(self, body: str, timestamp: int) -> str:
        message = body + str(timestamp) + self.secret_key
        return hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def verify(self, body: str, timestamp: int, signature: str) -> Tuple[bool, str]:
        now = int(time.time())
        if abs(now - timestamp) > 300:
            return False, "签名已过期（超过5分钟）"
        expected = self.sign(body, timestamp)
        if not hmac.compare_digest(expected, signature):
            return False, "签名验证失败"
        return True, ""


# ============================================================
# 滑动窗口限流器
# ============================================================

class RateLimiter:
    """
    滑动窗口限流器
    - 按 user_id 限流（已登录用户）
    - 按 IP 限流（未登录用户）
    """

    def __init__(self):
        self._user_buckets: Dict[int, List[float]] = defaultdict(list)
        self._ip_buckets: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._max_requests = 20  # 每分钟最多20次
        self._window = 60  # 滑动窗口60秒

    def check(self, user_id: Optional[int], ip_address: str) -> Tuple[bool, str]:
        key = user_id if user_id else ip_address
        bucket = self._user_buckets if user_id else self._ip_buckets
        with self._lock:
            now = time.time()
            bucket[key] = [t for t in bucket[key] if now - t < self._window]
            if len(bucket[key]) >= self._max_requests:
                return False, "请求过于频繁，请" + str(self._window) + "秒后再试"
            bucket[key].append(now)
            return True, ""


# ============================================================
# 便捷函数
# ============================================================

def check_input_security(text: str) -> SecurityCheckResult:
    return get_prompt_checker().check(text)

def sanitize_output(text: str) -> Tuple[str, List[str]]:
    return get_output_sanitizer().sanitize(text)

def validate_multi_ai(responses: List[Dict]) -> MultiAIValidationResult:
    return get_multi_ai_validator().validate(responses)

def audit_event(record: SecurityAuditRecord):
    get_audit_logger().log(record)

def verify_signature(body: str, timestamp: int, signature: str) -> Tuple[bool, str]:
    return RequestSigner().verify(body, timestamp, signature)

def check_rate_limit(user_id: Optional[int], ip_address: str) -> Tuple[bool, str]:
    return RateLimiter().check(user_id, ip_address)
