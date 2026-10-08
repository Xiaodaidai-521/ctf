from django.db import migrations


def enable_pgvector(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('legal_kb', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(enable_pgvector, noop_reverse),
    ]
