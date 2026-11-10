import uuid

from django.db import migrations, models


def assign_object_ids(apps, schema_editor):
    Message = apps.get_model('ai_assistant', 'AIMessage')
    for pk in Message.objects.filter(security_uuid__isnull=True).values_list('pk', flat=True).iterator():
        Message.objects.filter(pk=pk, security_uuid__isnull=True).update(security_uuid=uuid.uuid4())


def refuse_sealed_rollback(apps, schema_editor):
    rows = apps.get_model('ai_assistant', 'AIMessage').objects.using(schema_editor.connection.alias)
    if rows.exclude(security_state='legacy-v0').exists():
        raise RuntimeError('SEALED_FIELD_SCHEMA_ROLLBACK_REFUSED')


class Migration(migrations.Migration):
    dependencies = [('ai_assistant', '0005_legal_reviewer_preset')]
    operations = [
        migrations.AddField(model_name='aimessage', name='security_uuid', field=models.UUIDField(null=True, editable=False)),
        migrations.AddField(model_name='aimessage', name='security_revision', field=models.PositiveBigIntegerField(default=0, editable=False)),
        migrations.AddField(model_name='aimessage', name='security_state', field=models.CharField(default='legacy-v0', editable=False, max_length=16)),
        migrations.AddField(model_name='aimessage', name='security_envelopes', field=models.JSONField(default=dict, editable=False)),
        migrations.RunPython(assign_object_ids, migrations.RunPython.noop),
        migrations.AlterField(model_name='aimessage', name='security_uuid', field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
        migrations.AddConstraint(model_name='aimessage', constraint=models.CheckConstraint(
            condition=models.Q(security_state='legacy-v0') | models.Q(content='', metadata={}),
            name='message_sealed_fields_no_plaintext')),
        migrations.RunPython(migrations.RunPython.noop, refuse_sealed_rollback),
    ]
