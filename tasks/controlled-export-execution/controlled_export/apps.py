from django.apps import AppConfig


class ControlledExportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "controlled_export"

    def ready(self):
        from controlled_export_service.security_bootstrap import start_application
        start_application()
