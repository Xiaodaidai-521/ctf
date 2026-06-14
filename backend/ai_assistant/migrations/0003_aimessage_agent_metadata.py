# Generated manually to persist multi-agent chat metadata.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0002_agentpreset'),
    ]

    operations = [
        migrations.AddField(
            model_name='aimessage',
            name='agent_id',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='aimessage',
            name='agent_name',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='aimessage',
            name='provider',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='aimessage',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
