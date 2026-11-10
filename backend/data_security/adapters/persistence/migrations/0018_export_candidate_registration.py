from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('security_policies', '0017_reveal_retention_registration'),
    ]

    operations = [
        migrations.AddField(
            model_name='exportreport',
            name='retention_candidate',
            field=models.JSONField(null=True),
        ),
    ]
