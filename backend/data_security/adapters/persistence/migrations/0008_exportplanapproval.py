from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('security_policies', '0007_recoverypermission')]

    operations = [
        migrations.CreateModel(
            name='ExportPlanApproval',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('approval_ref', models.CharField(max_length=160, unique=True)),
                ('plan_hash', models.CharField(max_length=64)),
                ('binding_hash', models.CharField(max_length=64)),
                ('context_hash', models.CharField(max_length=64)),
                ('document', models.JSONField()),
                ('expires_at', models.DateTimeField()),
                ('revoked_at', models.DateTimeField(null=True)),
            ],
        ),
    ]
