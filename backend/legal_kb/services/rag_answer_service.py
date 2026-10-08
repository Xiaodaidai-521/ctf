"""RAG answer synthesis over retrieved legal and CTF knowledge chunks."""

import asyncio
import time
from typing import Dict, List, Optional

from django.conf import settings

from ai_providers import Message, get_manager

from .retrieval_service import LegalRetrievalService


class RagAnswerService:
    """Retrieve knowledge and synthesize a user-facing answer before returning it."""

    def __init__(self, retrieval_service: Optional[LegalRetrievalService] = None):
        self.retrieval_service = retrieval_service or LegalRetrievalService()

    def answer(
        self,
        *,
        query: str,
        top_k: int = 8,
        filters: Optional[Dict] = None,
        user=None,
        include_raw: bool = False,
    ) -> Dict:
        """Return synthesized answer, citations, and optional raw retrieval results."""
        started = time.perf_counter()
        results = self.retrieval_service.retrieve(
            query=query,
            top_k=top_k,
            filters=filters or {},
            user=user,
        )
        citations = self._build_citations(results)
        provider = 'local'
        model = 'rag-template-v1'
        answer_text = ''
        provider_error = ''

        if getattr(settings, 'LEGAL_KB_RAG_USE_LLM', False):
            try:
                response = self._call_provider(query=query, citations=citations)
                if response and response.content:
                    answer_text = response.content
                    provider = response.provider
                    model = response.model
            except Exception as exc:
                provider_error = str(exc)
                answer_text = ''

        sections = self._build_sections(query=query, citations=citations)
        if not answer_text:
            answer_text = self._render_sections(sections)

        payload = {
            'answer': answer_text,
            'sections': sections,
            'citations': citations,
            'provider': provider,
            'model': model,
            'latency_ms': int((time.perf_counter() - started) * 1000),
        }
        if provider_error:
            payload['provider_error'] = provider_error
        if include_raw:
            payload['results'] = results
        return payload

    def _call_provider(self, *, query: str, citations: List[Dict]):
        manager = get_manager()
        agent_id = getattr(settings, 'LEGAL_KB_RAG_AGENT_ID', 'compliance_officer')
        providers = self._provider_candidates(manager=manager, agent_id=agent_id)
        if not providers:
            raise RuntimeError('no available LLM provider for legal KB RAG')

        messages = [
            Message(
                role='system',
                content=(
                    '你是数智法律审计与数据安全演练平台的合规中心审计引擎。'
                    '当前输出代表三类协同角色：合规官负责法规与用户权益风险，'
                    '安全官负责 Docker、端口、镜像、资源限制与演练隔离风险，'
                    '审计官负责审计账本、证据完整性和报告留痕。'
                    '只能基于提供的知识库引用回答，不得编造法规、题解、事实或来源。'
                    '回答必须先给审计结论，再列法规依据、合规官/安全官/审计官协同意见、演练建议和证据缺口。'
                    'CTF 场景只提供教学引导和步骤思路，不直接给出 flag。'
                    '不要以“法律审核师”自称，法律审核师只用于用户问答页。'
                ),
            ),
            Message(role='user', content=self._build_prompt(query=query, citations=citations)),
        ]
        errors = []
        for provider in providers:
            try:
                response = asyncio.run(provider.chat(messages))
                if response and response.content:
                    return response
                errors.append(f'{provider.name}: empty response')
            except Exception as exc:
                errors.append(f'{provider.name}: {exc}')
        raise RuntimeError('; '.join(errors) or 'no provider returned a response')

    def _provider_candidates(self, *, manager, agent_id: str) -> List:
        candidates = []
        seen = set()

        def add_provider(provider):
            if provider and provider.is_available() and provider.name not in seen:
                candidates.append(provider)
                seen.add(provider.name)

        add_provider(manager.get_provider_for_agent(agent_id))
        add_provider(manager.get_provider('deepseek'))

        for provider in getattr(manager, '_instances', {}).values():
            add_provider(provider)
        return candidates

    def _build_prompt(self, *, query: str, citations: List[Dict]) -> str:
        evidence = []
        for index, item in enumerate(citations, start=1):
            evidence.append(
                f'[{index}] {item["title"]} '
                f'({item["source_type"]}, score={item["score"]})\n'
                f'{item["excerpt"]}'
            )
        return '\n\n'.join([
            f'用户问题：{query}',
            '知识库引用：',
            '\n\n'.join(evidence) or '无可用引用。',
            '请输出：1. 审计结论；2. 相关法规依据；3. 合规官/安全官/审计官协同意见；4. 靶场实验合规建议；5. 平台数据安全建议；6. 不足证据或需人工确认事项。',
            '注意：这是合规中心审计检索，不是用户问答页的法律审核师回答。',
        ])

    def _build_citations(self, results: List[Dict]) -> List[Dict]:
        citations = []
        for index, item in enumerate(results, start=1):
            citations.append({
                'index': index,
                'id': item.get('id'),
                'source_type': item.get('source_type', ''),
                'object_id': item.get('object_id'),
                'title': item.get('title') or 'Knowledge chunk',
                'score': item.get('score') or 0,
                'excerpt': self._truncate(item.get('text', ''), 600),
                'metadata': item.get('metadata') or {},
            })
        return citations

    def _build_sections(self, *, query: str, citations: List[Dict]) -> Dict:
        legal_source_types = {'legal_clause', 'legal_document', 'legal_case', 'legal_template'}
        legal_items = [item for item in citations if item['source_type'] in legal_source_types]
        challenge_items = [item for item in citations if item['source_type'] == 'challenge']
        platform_items = [
            item for item in citations
            if item['source_type'] not in legal_source_types and item['source_type'] != 'challenge'
        ]

        if not citations:
            return {
                'audit_conclusion': f'暂未检索到足够证据支撑“{query}”的法律审计结论。',
                'legal_basis': [],
                'multi_agent_views': [
                    {'role': '合规官', 'content': '缺少可引用法规或条款，不能形成正式合规判断。'},
                    {'role': '安全官', 'content': '缺少题目、容器或平台演练上下文，无法评估实验边界。'},
                    {'role': '审计官', 'content': '缺少可追溯证据，建议补充审计记录后再生成报告。'},
                ],
                'challenge_context': [],
                'exercise_advice': [
                    '补充题目名称、实验目的、容器暴露端口、访问范围和预期学习结果。',
                    '补充平台日志、Docker 行为审计或哈希链记录后再进行证据化审查。',
                ],
                'data_security_advice': [
                    '避免在证据不足时输出具体法律结论或最终题目答案。',
                    '对涉及个人信息、未成年人、日志留存的问题保留人工复核入口。',
                ],
                'evidence_gaps': ['未检索到法规证据。', '未检索到题目知识包或平台演练材料。'],
            }

        legal_basis = [
            {
                'index': item['index'],
                'title': item['title'],
                'source_type': item['source_type'],
                'score': item['score'],
                'excerpt': item['excerpt'],
                'applicability': self._describe_legal_applicability(query=query, item=item),
            }
            for item in legal_items[:5]
        ]
        challenge_context = [
            {
                'index': item['index'],
                'title': item['title'],
                'source_type': item['source_type'],
                'score': item['score'],
                'excerpt': item['excerpt'],
            }
            for item in challenge_items[:3]
        ]

        evidence_gaps = []
        if not legal_items:
            evidence_gaps.append('本次召回缺少法规条款、法律文档、案例或模板，法规依据需要人工补充。')
        if not challenge_items:
            evidence_gaps.append('本次召回缺少题目知识包或挑战上下文，靶场建议只能给出通用边界。')
        if not any(item.get('metadata', {}).get('audit_event_id') for item in citations):
            evidence_gaps.append('未召回容器行为审计或哈希链证据，报告留痕需结合审计账本复核。')

        return {
            'audit_conclusion': (
                f'已基于 {len(citations)} 条知识库证据完成“{query}”的审计检索。'
                '结论仅适用于教学靶场和平台实验场景，正式处置前仍需人工复核。'
            ),
            'legal_basis': legal_basis,
            'multi_agent_views': [
                {
                    'role': '合规官',
                    'content': (
                        self._summarize_legal_view(query=query, legal_items=legal_items)
                    ),
                },
                {
                    'role': '安全官',
                    'content': (
                        f'已召回 {len(challenge_items)} 条题目或知识包证据，建议把实验限制在授权靶场、'
                        '受控容器、限定端口和最小数据集内。'
                    ),
                },
                {
                    'role': '审计官',
                    'content': (
                        '建议将检索引用、Docker 行为审计、Flag 提交和报告导出记录串联到哈希链，'
                        '形成可复核的演练证据。'
                    ),
                },
            ],
            'challenge_context': challenge_context,
            'exercise_advice': [
                '若问题关联 CTF 题目，优先使用题目知识包说明实验目标、入口验证、复现步骤和防护复盘，不直接暴露 flag。',
                '启动靶场前记录镜像、容器名、端口、网络和资源限制；异常启动或停止失败应进入容器行为审计。',
                '将法律条文引用与实验建议分开呈现，避免把通用法规解释误写成题目结论。',
            ],
            'data_security_advice': [
                '对日志、账号、提交记录和对话内容执行最小必要采集，并明确保存周期与访问范围。',
                '报告导出时引用法规证据、题目知识证据和审计链哈希，证明演练环境受控、可追溯。',
                '涉及真实个人信息、未成年人信息或外部系统时，需转人工确认授权、告知和脱敏要求。',
            ],
            'evidence_gaps': evidence_gaps or ['当前检索证据较完整，但仍建议在报告发布前进行人工复核。'],
            'evidence_summary': {
                'legal_count': len(legal_items),
                'challenge_count': len(challenge_items),
                'platform_count': len(platform_items),
                'total_count': len(citations),
            },
        }

    def _render_sections(self, sections: Dict) -> str:
        lines = [
            '审计结论：',
            sections.get('audit_conclusion', ''),
            '',
            '相关法规依据：',
        ]
        legal_basis = sections.get('legal_basis') or []
        if legal_basis:
            for item in legal_basis:
                lines.append(
                    f'[{item["index"]}] {item["title"]}（{item["source_type"]}，相关度 {item["score"]}）'
                    f'：{item.get("applicability") or item["excerpt"]}'
                )
        else:
            lines.append('暂无可引用法规证据。')

        lines.extend(['', '多智能体协同意见：'])
        for item in sections.get('multi_agent_views', []):
            lines.append(f'{item["role"]}：{item["content"]}')

        lines.extend(['', '靶场实验合规建议：'])
        for index, item in enumerate(sections.get('exercise_advice', []), start=1):
            lines.append(f'{index}. {item}')

        lines.extend(['', '平台数据安全建议：'])
        for index, item in enumerate(sections.get('data_security_advice', []), start=1):
            lines.append(f'{index}. {item}')

        lines.extend(['', '不足证据或需人工确认事项：'])
        for index, item in enumerate(sections.get('evidence_gaps', []), start=1):
            lines.append(f'{index}. {item}')
        return '\n'.join(lines)

    def _summarize_legal_view(self, *, query: str, legal_items: List[Dict]) -> str:
        if not legal_items:
            return '本次未召回法规类证据，不能把合规结论写成确定性法律判断。'

        titles = '、'.join(item['title'] for item in legal_items[:3])
        return (
            f'已召回 {len(legal_items)} 条法规类证据，包括 {titles}。'
            f'针对“{query}”，应把这些法条用于限定处理目的、合法性基础、最小必要、告知同意、'
            '安全保护义务和未成年人保护边界；输出时需要明确这是教学靶场合规建议，不替代正式法律意见。'
        )

    def _describe_legal_applicability(self, *, query: str, item: Dict) -> str:
        excerpt = item.get('excerpt') or ''
        title = item.get('title') or '该法规依据'
        query_text = query or ''
        concerns = []
        combined = f'{query_text} {title} {excerpt}'

        if any(word in combined for word in ['未成年人', '儿童', '学生']):
            concerns.append('未成年人或学生权益保护')
        if any(word in combined for word in ['个人信息', '隐私', '账号', '日志', '学习记录']):
            concerns.append('个人信息处理与最小必要')
        if any(word in combined for word in ['数据安全', '安全保护', '审计', '留痕', '哈希链']):
            concerns.append('数据安全保护与审计留痕')
        if any(word in combined for word in ['CTF', '题目', '靶场', '容器', 'Docker', '漏洞']):
            concerns.append('授权靶场和实验边界')

        if concerns:
            return f'{title} 可用于约束{"、".join(dict.fromkeys(concerns))}，应结合证据摘要核对具体适用条件。'
        return f'{title} 与本次问题存在语义相关性，需结合条文原文确认适用范围。'

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        value = ' '.join((text or '').split())
        if len(value) <= limit:
            return value
        return value[:limit - 3].rstrip() + '...'
