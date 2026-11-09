from django.apps import AppConfig


class SecurityConfig(AppConfig):
    name = 'ctf_backend'

    def ready(self):
        from .security_bootstrap import start_application
        start_application()
