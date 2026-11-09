import uuid

from django.db import migrations, models


def assign_object_ids(apps, schema_editor):
    rows = apps.get_model('audit', 'AIAuditLog').objects.using(schema_editor.connection.alias)
    for pk in rows.filter(security_uuid__isnull=True).values_list('pk', flat=True).iterator():
        rows.filter(pk=pk, security_uuid__isnull=True).update(security_uuid=uuid.uuid4())


def refuse_sealed_rollback(apps, schema_editor):
    rows = apps.get_model('audit', 'AIAuditLog').objects.using(schema_editor.connection.alias)
    if rows.exclude(security_state='legacy-v0').exists():
        raise RuntimeError('SEALED_FIELD_SCHEMA_ROLLBACK_REFUSED')


class Migration(migrations.Migration):
    dependencies = [('audit', '0005_event_field_state')]
    operations = [
        migrations.AddField(model_name='aiauditlog', name='security_uuid', field=models.UUIDField(null=True, editable=False)),
        migrations.AddField(model_name='aiauditlog', name='security_revision', field=models.PositiveBigIntegerField(default=0, editable=False)),
        migrations.AddField(model_name='aiauditlog', name='security_state', field=models.CharField(default='legacy-v0', editable=False, max_length=16)),
        migrations.AddField(model_name='aiauditlog', name='security_envelopes', field=models.JSONField(default=dict, editable=False)),
        migrations.RunPython(assign_object_ids, migrations.RunPython.noop),
        migrations.AlterField(model_name='aiauditlog', name='security_uuid', field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
        migrations.AddConstraint(model_name='aiauditlog', constraint=models.CheckConstraint(
            condition=models.Q(security_state='legacy-v0') | models.Q(
                provider='withheld', model='withheld', user_message='', ai_response='', mode='',
                error_message='', duration_ms=0, token_estimate=0, ip_address__isnull=True),
            name='ai_audit_sealed_minimal')),
        migrations.RunPython(migrations.RunPython.noop, refuse_sealed_rollback),
    ]
