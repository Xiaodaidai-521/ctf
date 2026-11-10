from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('resources', '0003_resource_ai_resource_type')]

    operations = [
        migrations.AddField(
            model_name='resource',
            name='private_files',
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
    ]
