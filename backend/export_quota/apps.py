from django.apps import AppConfig


class ExportQuotaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'export_quota'
    verbose_name = '外发配额预占'
