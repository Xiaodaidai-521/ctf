from django.db import migrations, models


def assert_no_duplicate_source_hashes(apps, schema_editor):
    LegalDocument = apps.get_model('legal_kb', 'LegalDocument')
    duplicates = (
        LegalDocument.objects
        .values('source_hash')
        .annotate(count=models.Count('id'))
        .filter(count__gt=1)
    )
    duplicate_hashes = [item['source_hash'] for item in duplicates[:10]]
    if duplicate_hashes:
        raise RuntimeError(
            'Cannot add unique constraint to legal_kb.Legaldocument.source_hash; '
            f'duplicate source_hash values exist: {", ".join(duplicate_hashes)}'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('legal_kb', '0002_enable_pgvector'),
    ]

    operations = [
        migrations.RunPython(assert_no_duplicate_source_hashes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='legaldocument',
            name='source_hash',
            field=models.CharField(max_length=64, unique=True, verbose_name='Source hash'),
        ),
    ]
