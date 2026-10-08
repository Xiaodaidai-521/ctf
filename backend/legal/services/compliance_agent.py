"""Compliance officer agent adapter with deterministic fallback."""

import asyncio
import time
from typing import Dict, List

from django.conf import settings

from ai_providers import Message, get_manager


class ComplianceAgent:
    """Run the compliance officer agent if configured, otherwise use fallback output."""

    agent_id = 'compliance_officer'

    def analyze(self, *, task, evidence: List[Dict], assessment) -> Dict:
        """Return normalized agent output for a legal analysis task."""
        started = time.perf_counter()
        prompt = self._build_prompt(task=task, evidence=evidence, assessment=assessment)
        provider = 'fallback'
        model = 'rules-v1'
        success = True
        error_message = ''
        content = ''

        try:
            response = self._call_provider(prompt)
            if response:
                provider = response.provider
                model = response.model
                content = response.content
        except Exception as exc:
            success = False
            error_message = str(exc)

        if not content:
            content = self._fallback_content(assessment=assessment, evidence=evidence)

        return {
            'agent_id': self.agent_id,
            'provider': provider,
            'model': model,
            'input_payload': {
                'task_id': task.id,
                'title': task.title,
                'source_type': task.source_type,
                'evidence_count': len(evidence),
                'prompt': prompt,
            },
            'output_payload': {
                'content': content,
                'assessment': {
                    'severity': assessment.severity,
                    'score': assessment.score,
                    'matched_keywords': assessment.matched_keywords,
                },
                'evidence': evidence,
            },
            'success': success,
            'error_message': error_message,
            'duration_ms': int((time.perf_counter() - started) * 1000),
        }

    def _call_provider(self, prompt: str):
        if not getattr(settings, 'LEGAL_COMPLIANCE_AGENT_USE_LLM', False):
            return None
        manager = get_manager()
        provider = manager.get_provider_for_agent(self.agent_id)
        if not provider or not provider.is_available():
            return None
        messages = [
            Message(
                role='system',
                content='你是数智合规官。必须基于证据回答，不得编造法规条款。',
            ),
            Message(role='user', content=prompt),
        ]
        return asyncio.run(provider.chat(messages))

    def _build_prompt(self, *, task, evidence: List[Dict], assessment) -> str:
        evidence_lines = [
            f"- {item.get('title')} score={item.get('score')}: {item.get('text', '')[:300]}"
            for item in evidence[:8]
        ]
        return '\n'.join([
            f'任务：{task.title}',
            f'来源类型：{task.source_type}',
            f'输入内容：{task.input_text}',
            f'规则初评：{assessment.severity} / {assessment.score}',
            '证据：',
            '\n'.join(evidence_lines) or '(无检索证据)',
            '请输出风险等级、法律依据、影响分析、整改建议和待补充证据。',
            '同时增加“协同意见”区块：合规官关注法规与用户权益风险；安全官关注 Docker、端口、镜像、资源限制与演练隔离风险；审计官关注审计账本、证据完整性与报告留痕。',
        ])

    def _fallback_content(self, *, assessment, evidence: List[Dict]) -> str:
        severity_labels = {
            'critical': '严重',
            'high': '高危',
            'medium': '中危',
            'low': '低危',
        }
        evidence_titles = '、'.join(item.get('title', '') for item in evidence[:5]) or '暂无可引用知识库证据'
        matched = '、'.join(assessment.matched_keywords[:8]) or '未发现明确高风险关键词'
        return '\n'.join([
            f'初评结论：{severity_labels.get(assessment.severity, assessment.severity)}风险，风险分值 {assessment.score}。',
            f'命中要素：{matched}。',
            f'判断说明：{assessment.description}',
            f'参考依据：{evidence_titles}。',
            f'整改建议：{assessment.recommendation}',
            '协同意见：',
            f'- 合规官：围绕法规依据、用户权益告知和最小必要原则复核，当前结论为 {severity_labels.get(assessment.severity, assessment.severity)} 风险。',
            '- 安全官：复核 Docker 镜像、端口暴露、资源限制和演练隔离配置，异常容器事件需纳入整改跟踪。',
            '- 审计官：核对 AuditEvent 与哈希链账本是否完整，报告导出时应引用关键证据 hash 和处置记录。',
            '待补充材料：实际采集字段、授权/同意记录、保存周期、访问控制和删除机制。',
        ])
