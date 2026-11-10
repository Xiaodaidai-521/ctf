from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('security_policies', '0010_privatefileoperation')]

    operations = [
        migrations.AddField(
            model_name='privatefileoperation',
            name='legacy_sources',
            field=models.JSONField(default=dict),
        ),
    ]
