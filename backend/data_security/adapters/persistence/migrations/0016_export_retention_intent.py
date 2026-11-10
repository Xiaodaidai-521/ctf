from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('security_policies', '0015_export_retention_registration'),
    ]

    operations = [
        migrations.AddField(
            model_name='exportreport',
            name='retention_retirement',
            field=models.JSONField(null=True),
        ),
    ]
