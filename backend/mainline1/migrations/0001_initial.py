import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ParseAttempt',
            fields=[
                ('id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('number', models.PositiveIntegerField()),
                ('state', models.JSONField()),
            ],
        ),
        migrations.CreateModel(
            name='ParseRun',
            fields=[
                ('id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('domain', models.CharField(max_length=128)),
                ('environment', models.CharField(max_length=16)),
                ('evaluation', models.CharField(default='', max_length=128)),
                ('principal', models.CharField(max_length=128)),
                ('idempotency_key', models.CharField(max_length=128)),
                ('revision', models.PositiveBigIntegerField()),
                ('status', models.CharField(db_index=True, max_length=16)),
                ('state', models.JSONField()),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('domain', 'environment', 'evaluation', 'principal', 'idempotency_key'), name='ml1_parse_run_idempotency')],
            },
        ),
        migrations.CreateModel(
            name='ParsedArtifact',
            fields=[
                ('id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('payload', models.JSONField()),
                ('attempt', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to='mainline1.parseattempt')),
                ('run', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to='mainline1.parserun')),
            ],
        ),
        migrations.AddField(
            model_name='parseattempt',
            name='run',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='mainline1.parserun'),
        ),
        migrations.AddConstraint(
            model_name='parseattempt',
            constraint=models.UniqueConstraint(fields=('run', 'number'), name='ml1_parse_attempt_number'),
        ),
    ]
