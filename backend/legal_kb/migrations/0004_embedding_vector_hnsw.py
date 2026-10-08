from django.db import migrations
from pgvector.django import VectorField


def create_hnsw_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
        cursor.execute(
            'CREATE INDEX IF NOT EXISTS legal_kb_embedding_vector_hnsw '
            'ON legal_kb_legalknowledgeembedding '
            'USING hnsw (embedding_vector vector_cosine_ops) '
            'WITH (m = 16, ef_construction = 64) '
            'WHERE embedding_vector IS NOT NULL'
        )


def drop_hnsw_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('DROP INDEX IF EXISTS legal_kb_embedding_vector_hnsw')


class Migration(migrations.Migration):

    dependencies = [
        ('legal_kb', '0003_alter_legaldocument_source_hash'),
    ]

    operations = [
        migrations.AddField(
            model_name='legalknowledgeembedding',
            name='embedding_vector',
            field=VectorField(blank=True, dimensions=1024, null=True, verbose_name='Embedding vector'),
        ),
        migrations.RunPython(create_hnsw_index, drop_hnsw_index),
    ]
