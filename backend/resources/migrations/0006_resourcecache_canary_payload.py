from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('resources', '0005_export_sources')]

    operations = [
        migrations.AddField(model_name='resourcecache', name='canary_payload',
            field=models.JSONField(default=dict, blank=True, editable=False)),
    ]
