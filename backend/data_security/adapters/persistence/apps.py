from django.apps import AppConfig


class PolicyPersistenceConfig(AppConfig):
    name = 'data_security.adapters.persistence'
    label = 'security_policies'
    default_auto_field = 'django.db.models.BigAutoField'
