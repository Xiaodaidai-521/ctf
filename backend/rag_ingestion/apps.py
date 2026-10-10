from django.apps import AppConfig


class RagIngestionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rag_ingestion'
    verbose_name = 'RAG document ingestion'
