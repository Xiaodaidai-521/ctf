from typing import Any, Dict, List, Optional

from .models import AgentRun


class AgentRunStateStore:
    """Small persistence wrapper for agent run lifecycle updates."""

    def create_run(
        self,
        *,
        user,
        task_type: str,
        plan: Optional[List[Dict[str, Any]]] = None,
        current_step: str = '',
    ) -> AgentRun:
        return AgentRun.objects.create(
            user=user,
            task_type=task_type,
            status=AgentRun.STATUS_PENDING,
            current_step=current_step,
            plan=plan or [],
        )

    def mark_running(self, run: AgentRun, *, current_step: str = '') -> AgentRun:
        run.status = AgentRun.STATUS_RUNNING
        if current_step:
            run.current_step = current_step
        run.save(update_fields=['status', 'current_step', 'updated_at'])
        return run

    def record_tool_use(self, run: AgentRun, tool_record: Dict[str, Any]) -> AgentRun:
        used_tools = list(run.used_tools or [])
        used_tools.append(tool_record)
        run.used_tools = used_tools
        run.save(update_fields=['used_tools', 'updated_at'])
        return run

    def record_retrieval(self, run: AgentRun, retrieved_docs: List[Dict[str, Any]]) -> AgentRun:
        run.retrieved_docs = retrieved_docs
        run.save(update_fields=['retrieved_docs', 'updated_at'])
        return run

    def record_intermediate(self, run: AgentRun, intermediate_result: Dict[str, Any]) -> AgentRun:
        run.intermediate_result = intermediate_result
        run.save(update_fields=['intermediate_result', 'updated_at'])
        return run

    def complete(
        self,
        run: AgentRun,
        *,
        final_result: Dict[str, Any],
        verification_result: Optional[Dict[str, Any]] = None,
    ) -> AgentRun:
        run.status = AgentRun.STATUS_COMPLETED
        run.current_step = 'completed'
        run.final_result = final_result
        run.verification_result = verification_result or {}
        run.error_message = ''
        run.save(update_fields=[
            'status',
            'current_step',
            'final_result',
            'verification_result',
            'error_message',
            'updated_at',
        ])
        return run

    def fail(
        self,
        run: AgentRun,
        *,
        error_message: str,
        intermediate_result: Optional[Dict[str, Any]] = None,
    ) -> AgentRun:
        run.status = AgentRun.STATUS_FAILED
        run.current_step = 'failed'
        run.error_message = error_message
        if intermediate_result is not None:
            run.intermediate_result = intermediate_result
        run.save(update_fields=[
            'status',
            'current_step',
            'error_message',
            'intermediate_result',
            'updated_at',
        ])
        return run
