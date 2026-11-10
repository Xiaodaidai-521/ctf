from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('security_policies', '0014_reveal_request_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='exportreport',
            name='retention_scope',
            field=models.CharField(max_length=160, null=True),
        ),
        migrations.AddField(
            model_name='exportreport',
            name='retention_registration',
            field=models.JSONField(null=True),
        ),
    ]
