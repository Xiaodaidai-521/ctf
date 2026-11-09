from django.apps import AppConfig


class AgentMemoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent_memory'

    def ready(self):
        from django.core.signals import request_started, request_finished
        from django.db.models.signals import post_save
        from ai_assistant.models import AIMessage
        from .ledger import bind_saved_message, clear_request

        post_save.connect(bind_saved_message, sender=AIMessage, dispatch_uid='agent_memory.bind_saved_message')
        request_started.connect(clear_request, dispatch_uid='agent_memory.start_request')
        request_finished.connect(clear_request, dispatch_uid='agent_memory.finish_request')

        # The legacy service shares one summary between its cache and prompt.
        # Extend only cache serialization; HistorySummary remains plain text.
        from functools import wraps
        import json
        from ai_assistant.service import MultiAgentChatService
        from .prompt import HistorySummary

        build_key = MultiAgentChatService._build_response_cache_key

        @wraps(build_key)
        def memory_cache_key(service, question, challenge_id, agent_ids, mode,
                             force_ai, knowledge_scope, context_summary=''):
            if isinstance(context_summary, HistorySummary):
                context_summary = json.dumps([str(context_summary), context_summary.history_key], ensure_ascii=False)
            return build_key(service, question, challenge_id, agent_ids, mode,
                             force_ai, knowledge_scope, context_summary)

        MultiAgentChatService._build_response_cache_key = memory_cache_key
