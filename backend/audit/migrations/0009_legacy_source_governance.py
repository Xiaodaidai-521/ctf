from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('audit', '0008_legacy_archive_permission')]

    operations = [
        migrations.AddField(
            model_name='auditledgerlock',
            name='legacy_archive',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
