from django.apps import AppConfig


class AiAssistantConfig(AppConfig):
    name = 'ai_assistant'

    def ready(self):
        from . import signals  # noqa: F401
        from resources import signals as resource_signals  # noqa: F401
