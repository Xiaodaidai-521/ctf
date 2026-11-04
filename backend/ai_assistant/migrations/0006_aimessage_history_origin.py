from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ai_assistant', '0005_legal_reviewer_preset')]

    operations = [
        migrations.AddField(
            model_name='aimessage',
            name='history_origin',
            field=models.JSONField(default=dict, blank=True, editable=False),
        ),
    ]
