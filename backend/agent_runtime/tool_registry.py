from typing import Any, Dict, List


class LearningToolRegistry:
    """Read-only data tools available to runtime-managed learning agents."""

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
        from learning_paths.models import UserKnowledgeState

        queryset = (
            UserKnowledgeState.objects
            .filter(user=user)
            .select_related('concept')
            .order_by('mastery_level', '-updated_at')[:8]
        )
        items = []
        for state in queryset:
            items.append({
                'id': state.id,
                'concept_id': state.concept_id,
                'concept_name': state.concept.name,
                'concept_description': state.concept.description,
                'mastery_level': state.mastery_level,
                'recall_probability': state.recall_probability,
                'lab_attempts': state.lab_attempts,
                'lab_successes': state.lab_successes,
                'recommended_intervention': state.recommended_intervention,
                'struggle_indicators': state.struggle_indicators,
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
                module.description,
                module.content,
                module.learning_path.title,
                module.learning_path.description,
            ]).lower()
            if tokens and not any(token in haystack for token in tokens):
                continue
            items.append({
                'id': module.id,
                'learning_path_id': module.learning_path_id,
                'learning_path_title': module.learning_path.title,
                'title': module.title,
                'description': module.description,
                'module_type': module.module_type,
                'content': module.content,
                'order': module.order,
            })
            if len(items) >= 8:
                break
        return {'status': 'success' if items else 'empty', 'items': items}

    def run(self, name: str, *, user, query: str = '') -> Dict[str, Any]:
        tool = getattr(self, name, None)
        if tool is None:
            return {'status': 'error', 'items': [], 'error': f'Unknown tool: {name}'}
        return tool(user=user, query=query)

    def available_learning_tools(self) -> List[str]:
        return [
            'read_student_profile',
            'read_user_knowledge_state',
            'read_learning_path_modules',
        ]

    def _query_tokens(self, value: str) -> List[str]:
        import re

        return [
            token.lower()
            for token in re.findall(r'[\u4e00-\u9fff]{2,}|[a-z0-9_+#.-]{2,}', value or '')
        ][:12]
