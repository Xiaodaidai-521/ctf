from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('challenges', '0009_field_envelopes')]

    operations = [
        migrations.AddField(model_name='challenge', name='canary_payload',
            field=models.JSONField(default=dict, blank=True, editable=False)),
    ]
