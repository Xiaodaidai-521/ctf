from typing import Any, Dict, List


class LearningToolRegistry:
    """Read-only batch tools, with explicitly selected user-memory tools."""

    def read_student_profile(self, *, user, query: str = '') -> Dict[str, Any]:
        from student_profiles.models import StudentProfile

        try:
            profile = StudentProfile.objects.select_related('preference').get(user=user)
        except StudentProfile.DoesNotExist:
            return {
                'status': 'empty',
                'items': [],
                'message': 'No student profile is available.',
            }

        preference = getattr(profile, 'preference', None)
        item = {
            'id': profile.id,
            'learning_goals': profile.learning_goals,
            'self_assessed_skills': profile.self_assessed_skills,
            'onboarding_completed': profile.onboarding_completed,
            'preferred_pace': getattr(preference, 'preferred_pace', ''),
            'preferred_modality': getattr(preference, 'preferred_modality', []),
            'daily_study_hours': getattr(preference, 'daily_study_hours', None),
        }
        return {'status': 'success', 'items': [item]}

    def read_user_knowledge_state(self, *, user, query: str = '') -> Dict[str, Any]:
        from learning_paths.models import KnowledgeConcept, UserKnowledgeState
        from learning_knowledge.policy import filter_legacy_queryset

        concepts = filter_legacy_queryset(KnowledgeConcept.objects.all(), 'knowledge_concept', user)
        queryset = (
            UserKnowledgeState.objects
            .filter(user=user, concept__in=concepts)
            .select_related('concept')
            .order_by('mastery_level', '-updated_at')[:8]
        )
        items = []
        for state in queryset:
            items.append({
                'id': state.id,
                'concept_id': state.concept_id,
                'concept_name': state.concept.name,
                # Descriptions and derived prose require separate evidence authority.
                'mastery_level': state.mastery_level,
                'recall_probability': state.recall_probability,
                'lab_attempts': state.lab_attempts,
                'lab_successes': state.lab_successes,
            })
        return {'status': 'success' if items else 'empty', 'items': items}

    def read_learning_path_modules(self, *, user, query: str = '') -> Dict[str, Any]:
        from learning_paths.models import PathModule

        tokens = self._query_tokens(query)
        queryset = (
            PathModule.objects
            .filter(learning_path__is_published=True)
            .select_related('learning_path')
            .order_by('learning_path__order', 'order', 'id')
        )
        items = []
        for module in queryset[:40]:
            haystack = ' '.join([
                module.title,
                module.learning_path.title,
            ]).lower()
            if tokens and not any(token in haystack for token in tokens):
                continue
            items.append({
                'id': module.id,
                'learning_path_id': module.learning_path_id,
                'learning_path_title': module.learning_path.title,
                'title': module.title,
                # Navigation metadata only; module.content is not evidence.
                'module_type': module.module_type,
                'order': module.order,
            })
            if len(items) >= 8:
                break
        return {'status': 'success' if items else 'empty', 'items': items}

    def recall_memories(self, *, user, query: str = '', memory_type=None, memory_key=None) -> Dict[str, Any]:
        from agent_memory.long_term import run_memory_tool

        return run_memory_tool('recall_memories', user=user, memory_type=memory_type, memory_key=memory_key)

    def forget_memory(self, *, user, query: str = '', memory_type=None, memory_key=None) -> Dict[str, Any]:
        from agent_memory.long_term import run_memory_tool

        return run_memory_tool('forget_memory', user=user, memory_type=memory_type, memory_key=memory_key)

    def run(self, name: str, *, user, query: str = '', memory_type=None, memory_key=None, task_context=None) -> Dict[str, Any]:
        if name not in self.available_learning_tools(include_memory=True):
            return {'status': 'error', 'items': [], 'error': f'Unknown tool: {name}'}
        if task_context is not None:
            from teaching_agent.permissions import require_tool_permission

            require_tool_permission(task_context, name)
        tool = getattr(self, name)
        if name in {'recall_memories', 'forget_memory'}:
            result = tool(user=user, memory_type=memory_type, memory_key=memory_key)
        else:
            result = tool(user=user, query=query)
        return result

    def available_learning_tools(self, *, include_memory: bool = False) -> List[str]:
        tools = [
            'read_student_profile',
            'read_user_knowledge_state',
            'read_learning_path_modules',
        ]
        # LearningRetrievalService runs this default batch automatically. Never add
        # forget (or change existing retrieval/prompt behavior) to that batch.
        if include_memory:
            tools.extend(['recall_memories', 'forget_memory'])
        return tools

    def _query_tokens(self, value: str) -> List[str]:
        import re

        return [
            token.lower()
            for token in re.findall(r'[\u4e00-\u9fff]{2,}|[a-z0-9_+#.-]{2,}', value or '')
        ][:12]
