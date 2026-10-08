import asyncio
import concurrent.futures
from typing import Any, Dict, List, Optional

from .models import AgentRun
from .retrieval import LearningRetrievalService
from .state_store import AgentRunStateStore
from .verifier import AgentRuntimeVerifier


def _run_coroutine(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result(timeout=300)


class AgentGateway:
    """Runtime entry point that wraps the existing AI service."""

    def __init__(
        self,
        *,
        state_store: Optional[AgentRunStateStore] = None,
        retrieval_service: Optional[LearningRetrievalService] = None,
        verifier: Optional[AgentRuntimeVerifier] = None,
        service=None,
    ):
        self.state_store = state_store or AgentRunStateStore()
        self.retrieval_service = retrieval_service or LearningRetrievalService()
        self.verifier = verifier or AgentRuntimeVerifier()
        self.service = service

    def run_learning_task(
        self,
        *,
        user,
        message: str,
        agent_id: str = 'tutor',
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentRun:
        plan = [
            {'name': 'prepare_context', 'status': 'pending'},
            {'name': 'call_learning_agent', 'status': 'pending'},
            {'name': 'record_result', 'status': 'pending'},
        ]
        run = self.state_store.create_run(
            user=user,
            task_type=AgentRun.TASK_LEARNING,
            plan=plan,
            current_step='prepare_context',
        )

        try:
            retrieval = self.retrieval_service.retrieve(user=user, query=message)
            self.state_store.record_retrieval(run, retrieval.get('retrieved_docs', []))
            for tool_record in retrieval.get('used_tools', []):
                self.state_store.record_tool_use(run, tool_record)

            runtime_context = dict(context or {})
            knowledge_context = retrieval.get('knowledge_context') or ''
            response_instruction = self._build_learning_response_instruction(
                retrieval.get('retrieved_docs', [])
            )
            if knowledge_context:
                existing_context = runtime_context.get('knowledge_context') or ''
                runtime_context['knowledge_context'] = (
                    f'{existing_context}\n\n{knowledge_context}'.strip()
                    if existing_context
                    else knowledge_context
                )
            if response_instruction:
                existing_instruction = runtime_context.get('agent_task_instruction') or ''
                runtime_context['agent_task_instruction'] = (
                    f'{existing_instruction}\n\n{response_instruction}'.strip()
                    if existing_instruction
                    else response_instruction
                )

            self.state_store.mark_running(run, current_step='call_learning_agent')
            final_result = self._call_learning_agent(
                agent_id,
                message,
                runtime_context,
                conversation_history or [],
            )
            verification_result = self.verifier.verify_learning_response(
                final_result=final_result,
                retrieved_docs=retrieval.get('retrieved_docs', []),
            )

            if not verification_result.get('passed'):
                self.state_store.record_intermediate(
                    run,
                    {
                        'attempts': [
                            {
                                'name': 'initial',
                                'final_result': final_result,
                                'verification_result': verification_result,
                            },
                        ],
                    },
                )
                retry_instruction = self._build_verification_retry_instruction(verification_result)
                if retry_instruction:
                    retry_context = dict(runtime_context)
                    existing_instruction = retry_context.get('agent_task_instruction') or ''
                    retry_context['agent_task_instruction'] = (
                        f'{existing_instruction}\n\n{retry_instruction}'.strip()
                        if existing_instruction
                        else retry_instruction
                    )
                    self.state_store.mark_running(run, current_step='retry_learning_agent')
                    final_result = self._call_learning_agent(
                        agent_id,
                        message,
                        retry_context,
                        conversation_history or [],
                    )
                    verification_result = self.verifier.verify_learning_response(
                        final_result=final_result,
                        retrieved_docs=retrieval.get('retrieved_docs', []),
                    )

            return self.state_store.complete(
                run,
                final_result=final_result,
                verification_result=verification_result,
            )
        except Exception as exc:
            return self.state_store.fail(run, error_message=str(exc))

    def _get_service(self):
        if self.service is not None:
            return self.service
        from ai_assistant.service import get_multi_agent_service

        self.service = get_multi_agent_service()
        return self.service

    async def _chat_with_learning_agent(
        self,
        agent_id: str,
        message: str,
        context: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return await self._get_service().chat_with_agent(
            agent_id,
            message,
            context,
            conversation_history,
        )

    def _call_learning_agent(
        self,
        agent_id: str,
        message: str,
        context: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        ai_response = _run_coroutine(self._chat_with_learning_agent(
            agent_id,
            message,
            context,
            conversation_history,
        ))
        return {
            'agent_id': ai_response.get('agent_id', agent_id),
            'agent_name': ai_response.get('agent_name', ''),
            'provider': ai_response.get('provider', ''),
            'model': ai_response.get('model', ''),
            'content': ai_response.get('content', ''),
            'security_warnings': ai_response.get('security_warnings'),
        }

    def _build_learning_response_instruction(self, retrieved_docs: List[Dict[str, Any]]) -> str:
        source_refs = [
            str(doc.get('source_ref'))
            for doc in retrieved_docs
            if doc.get('source_ref')
        ]
        if not source_refs:
            return (
                'Answer as a learning tutor. If platform learning context is insufficient, '
                'state what information is missing and give one safe next learning step.'
            )

        refs = ', '.join(source_refs[:8])
        return '\n'.join([
            'Answer as a learning tutor using the provided platform learning context.',
            f'When using retrieved context, cite valid source references exactly like [{source_refs[0]}].',
            f'Available source references: {refs}.',
            'Include at least one concrete next learning action.',
            'If the retrieved context is insufficient, state the gap and still cite the closest relevant source.',
        ])

    def _build_verification_retry_instruction(self, verification_result: Dict[str, Any]) -> str:
        remediations = [
            str(check.get('remediation')).strip()
            for check in verification_result.get('checks', [])
            if not check.get('passed') and str(check.get('remediation') or '').strip()
        ]
        if not remediations:
            return ''

        unique_remediations = list(dict.fromkeys(remediations))
        return '\n'.join([
            'Revise the previous learning answer to satisfy these verification requirements:',
            *[f'- {remediation}' for remediation in unique_remediations],
        ])
