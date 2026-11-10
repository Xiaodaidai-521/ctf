from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('security_policies', '0009_export_binding')]

    operations = [
        migrations.CreateModel(
            name='PrivateFileOperation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operation_ref', models.CharField(max_length=160, unique=True)),
                ('actor_ref', models.CharField(max_length=160)),
                ('scope_ref', models.CharField(max_length=160)),
                ('request_hash', models.CharField(max_length=64)),
                ('object_uuid', models.UUIDField()),
                ('field_refs', models.JSONField()),
                ('files', models.JSONField(default=dict)),
                ('state', models.CharField(default='preparing', max_length=16)),
                ('result_ref', models.CharField(blank=True, max_length=160)),
            ],
        ),
        migrations.CreateModel(
            name='PrivateFileShare',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('share_id', models.UUIDField(unique=True)),
                ('operation_ref', models.CharField(max_length=160, unique=True)),
                ('document', models.JSONField()),
                ('revoked_at', models.DateTimeField(null=True)),
            ],
        ),
    ]
