from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('legal_kb', '0005_alter_legalknowledgeembedding_source_type')]

    operations = [
        migrations.AddField(model_name='legaldocument', name='canary_payload',
            field=models.JSONField(default=dict, blank=True, editable=False)),
    ]
