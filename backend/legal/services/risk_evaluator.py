"""Deterministic legal risk scoring for early compliance analysis."""

import re
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class RiskAssessment:
    """Structured risk assessment generated from rules and evidence."""

    title: str
    description: str
    severity: str
    likelihood: float
    impact: float
    score: float
    recommendation: str
    matched_keywords: List[str]


class RiskEvaluator:
    """Evaluate legal risk with deterministic heuristics."""

    KEYWORD_RULES = {
        'critical': [
            '泄露',
            '出售',
            '非法提供',
            '敏感个人信息',
            '未成年人',
            '跨境',
            '安全事件',
        ],
        'high': [
            '人脸',
            '身份证',
            '手机号',
            '精准定位',
            '生物识别',
            '拒绝删除',
        ],
        'medium': [
            '隐私政策',
            '数据处理',
            '第三方',
            '共享',
            '自动化决策',
            '真实个人信息',
            '过度采集',
            '未告知',
            '未取得同意',
            '无保存周期',
            '未限制访问',
        ],
        'low': [
            '告知',
            '备案',
            '培训',
            '资源',
            '题目',
        ],
    }

    SEVERITY_LABELS = {
        'critical': '严重',
        'high': '高危',
        'medium': '中危',
        'low': '低危',
    }

    AGGRAVATING_TERMS = ['泄露', '出售', '非法提供', '拒绝删除', '安全事件', '未授权', '违规共享']
    CONTROL_TERMS = [
        '已告知',
        '告知',
        '同意记录',
        '取得同意',
        '授权记录',
        '审计',
        '哈希链',
        '留痕',
        '保存周期',
        '访问范围',
        '最小必要',
        '脱敏',
        '不使用真实',
        '不涉及真实',
        '受控容器',
        '限制',
        '自动清理',
    ]
    CONTROL_NEGATION_TERMS = [
        '未告知',
        '未取得同意',
        '无同意',
        '无授权',
        '缺少授权',
        '无保存周期',
        '未限制访问',
        '未脱敏',
        '无审计',
        '无留痕',
    ]
    DATA_TERMS = [
        '个人信息',
        '敏感个人信息',
        '人脸',
        '身份证',
        '手机号',
        '精准定位',
        '生物识别',
        'personal information',
        'sensitive personal information',
        'id card',
        'phone number',
    ]
    PROCESSING_TERMS = [
        '收集',
        '处理',
        '存储',
        '留存',
        '日志',
        '共享',
        '传输',
        '跨境',
        '采集',
        '删除',
        '授权',
        '同意',
        'collect',
        'process',
        'store',
        'share',
        'transfer',
        'consent',
    ]

    def evaluate(self, *, text: str, evidence: List[Dict]) -> RiskAssessment:
        """Return a single summarized risk assessment."""
        normalized = text or ''
        matched = self._match_keywords(normalized)
        severity = self._choose_severity(normalized, matched, evidence)
        likelihood, impact = self._score_components(severity, matched, evidence)
        score = round(likelihood * impact, 4)
        return RiskAssessment(
            title=self._build_title(severity, matched),
            description=self._build_description(severity, matched, evidence),
            severity=severity,
            likelihood=likelihood,
            impact=impact,
            score=score,
            recommendation=self._build_recommendation(severity, matched),
            matched_keywords=matched,
        )

    def _match_keywords(self, text: str) -> List[str]:
        matched = []
        for keywords in self.KEYWORD_RULES.values():
            for keyword in keywords:
                if re.search(re.escape(keyword), text, flags=re.IGNORECASE) and keyword not in matched:
                    matched.append(keyword)
        return matched

    def _choose_severity(self, text: str, matched: List[str], evidence: List[Dict]) -> str:
        normalized = text.lower()
        has_aggravating = self._contains_any(normalized, self.AGGRAVATING_TERMS)
        has_control_gap = self._contains_any(normalized, self.CONTROL_NEGATION_TERMS)
        has_controls = self._contains_any(normalized, self.CONTROL_TERMS)
        has_data = self._contains_any(normalized, self.DATA_TERMS)
        has_processing = self._contains_any(normalized, self.PROCESSING_TERMS)
        has_minor = self._contains_any(normalized, ['未成年人', 'minor'])
        has_sensitive = self._contains_any(normalized, ['敏感个人信息', '人脸', '生物识别', '精准定位', 'sensitive personal information'])
        has_cross_border = self._contains_any(normalized, ['跨境', 'cross-border', 'cross border'])

        if has_aggravating and (has_data or has_processing):
            return 'critical'
        if (has_sensitive or has_minor or has_cross_border) and (has_data or has_processing):
            return 'high'
        if any(keyword in matched for keyword in self.KEYWORD_RULES['high']):
            return 'high'
        if has_control_gap and (has_data or has_processing):
            return 'medium'
        if any(keyword in matched for keyword in self.KEYWORD_RULES['medium']):
            return 'medium'
        if has_controls:
            return 'low'
        if any(keyword in matched for keyword in self.KEYWORD_RULES['low']) or evidence:
            return 'low'
        return 'low'

    def _score_components(self, severity: str, matched: List[str], evidence: List[Dict]) -> tuple:
        base = {
            'critical': (0.82, 0.9),
            'high': (0.65, 0.72),
            'medium': (0.48, 0.56),
            'low': (0.28, 0.34),
        }[severity]
        evidence_boost = min(len(evidence), 5) * 0.01
        keyword_boost = min(len(matched), 6) * 0.012
        likelihood = min(base[0] + keyword_boost, 0.99)
        impact = min(base[1] + evidence_boost, 0.99)
        return round(likelihood, 4), round(impact, 4)

    def _build_title(self, severity: str, matched: List[str]) -> str:
        label = self.SEVERITY_LABELS.get(severity, severity)
        if matched:
            return f'初评为{label}风险：{matched[0]}'
        return f'初评为{label}风险：未发现明确高风险要素'

    def _build_description(self, severity: str, matched: List[str], evidence: List[Dict]) -> str:
        label = self.SEVERITY_LABELS.get(severity, severity)
        keyword_text = '、'.join(matched[:8]) if matched else '未命中明确风险要素'
        evidence_count = len(evidence)
        return (
            f'规则初评为{label}风险。输入内容命中：{keyword_text}。'
            f'已检索到{evidence_count}条知识库引用材料，引用材料只作为依据，不单独抬高风险等级。'
            '请结合实际采集字段、用户范围、授权记录和保存周期复核。'
        )

    def _build_recommendation(self, severity: str, matched: List[str]) -> str:
        actions = [
            '补充处理目的、处理范围、保存期限和安全措施说明。',
            '核对用户同意记录、协议版本和审计哈希链是否完整。',
            '引用知识库中对应法规条款，形成整改闭环和责任人。',
        ]
        if severity in {'critical', 'high'}:
            actions.insert(0, '暂停高风险处理活动或演练发布，先完成法务与安全复核。')
        if '敏感个人信息' in matched or '未成年人' in matched:
            actions.append('对敏感个人信息或未成年人信息执行单独同意与最小必要校验。')
        return '\n'.join(actions)

    def _contains_any(self, text: str, terms: List[str]) -> bool:
        return any(term.lower() in text for term in terms)
