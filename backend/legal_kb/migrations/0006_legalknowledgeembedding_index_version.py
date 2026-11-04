from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('legal_kb', '0005_alter_legalknowledgeembedding_source_type')]

    operations = [
        # Do not guess the vector space of legacy JSON/pgvector dual writes.
        # Empty versions stay lexical-only until explicitly re-embedded.
        migrations.AddField(
            model_name='legalknowledgeembedding',
            name='index_version',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
    ]
