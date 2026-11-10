from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('security_policies', '0008_exportplanapproval'),
    ]

    operations = [
        migrations.AddField(
            model_name='exportreport',
            name='binding_document',
            field=models.JSONField(null=True),
        ),
    ]
