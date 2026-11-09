import uuid

from django.db import migrations, models


PROTECTED_MODELS = ('StudentProfile', 'DynamicGrowthProfile', 'LearningPreference',
                    'LearningPersona', 'OnboardingInterview', 'StudentProfileReport')


def assign_object_ids(apps, schema_editor):
    for name in PROTECTED_MODELS:
        model = apps.get_model('student_profiles', name)
        rows = model.objects.using(schema_editor.connection.alias)
        for pk in rows.filter(security_uuid__isnull=True).values_list('pk', flat=True).iterator():
            rows.filter(pk=pk, security_uuid__isnull=True).update(security_uuid=uuid.uuid4())


def refuse_sealed_rollback(apps, schema_editor):
    for name in PROTECTED_MODELS:
        model = apps.get_model('student_profiles', name)
        if model.objects.using(schema_editor.connection.alias).exclude(security_state='legacy-v0').exists():
            raise RuntimeError('SEALED_FIELD_SCHEMA_ROLLBACK_REFUSED')


class Migration(migrations.Migration):
    dependencies = [('student_profiles', '0009_dynamicgrowthprofile_direction_scores')]
    operations = []
    for name in PROTECTED_MODELS:
        operations.extend([
            migrations.AddField(model_name=name.lower(), name='security_uuid', field=models.UUIDField(null=True, editable=False)),
            migrations.AddField(model_name=name.lower(), name='security_revision', field=models.PositiveBigIntegerField(default=0, editable=False)),
            migrations.AddField(model_name=name.lower(), name='security_state', field=models.CharField(default='legacy-v0', editable=False, max_length=16)),
            migrations.AddField(model_name=name.lower(), name='security_envelopes', field=models.JSONField(default=dict, editable=False)),
        ])
    operations.append(migrations.RunPython(assign_object_ids, migrations.RunPython.noop))
    for name in PROTECTED_MODELS:
        operations.append(migrations.AlterField(model_name=name.lower(), name='security_uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True)))
    operations.extend([
        migrations.AddConstraint(model_name='onboardinginterview', constraint=models.CheckConstraint(
            condition=models.Q(security_state='legacy-v0') | models.Q(answers={}),
            name='interview_sealed_answers_no_plaintext')),
        migrations.AddConstraint(model_name='studentprofilereport', constraint=models.CheckConstraint(
            condition=models.Q(security_state='legacy-v0') | models.Q(raw_interview={}),
            name='profile_report_sealed_raw_no_plaintext')),
        migrations.RunPython(migrations.RunPython.noop, refuse_sealed_rollback),
    ])
