from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('security_policies', '0011_privatefileoperation_legacy_sources')]

    operations = [
        migrations.CreateModel(
            name='CanaryRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('seed_id', models.CharField(max_length=32, unique=True)),
                ('seed_document', models.JSONField()),
                ('target_pk', models.CharField(max_length=160)),
                ('actor_ref', models.CharField(max_length=160)),
                ('packet_hash', models.CharField(max_length=64)),
                ('state', models.CharField(default='planted', max_length=16)),
                ('plant_event_id', models.CharField(max_length=160)),
                ('retire_event_id', models.CharField(blank=True, max_length=160)),
            ],
        ),
    ]
