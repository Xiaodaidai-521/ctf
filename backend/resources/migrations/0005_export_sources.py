from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('resources', '0004_resource_private_files')]

    operations = [
        migrations.CreateModel(
            name='ExportSource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_ref', models.CharField(max_length=160, unique=True)),
                ('document', models.JSONField()),
                ('document_hash', models.CharField(max_length=64)),
                ('expires_at', models.DateTimeField()),
                ('approval', models.JSONField(null=True)),
                ('plan_document', models.JSONField(null=True)),
                ('revoked_at', models.DateTimeField(null=True)),
                ('execution_document', models.JSONField(null=True)),
                ('target_approval_ref', models.CharField(blank=True, max_length=160)),
                ('resource', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='resources.resource')),
            ],
        ),
        migrations.CreateModel(
            name='ExportSourcePermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('authorization_ref', models.CharField(max_length=160, unique=True)),
                ('actor_ref', models.CharField(max_length=160)),
                ('source_hash', models.CharField(max_length=64)),
                ('granted_by', models.CharField(max_length=160)),
                ('expires_at', models.DateTimeField()),
                ('revoked_at', models.DateTimeField(null=True)),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='resources.exportsource')),
            ],
        ),
    ]
