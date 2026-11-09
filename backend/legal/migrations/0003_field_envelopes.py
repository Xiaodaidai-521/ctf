import uuid

from django.db import migrations, models


OWNERS = ('legalanalysistask', 'legalevidence', 'legalreport', 'complianceagentrun', 'legalfactsnapshot')


def assign_object_ids(apps, schema_editor):
    for name in OWNERS:
        Owner = apps.get_model('legal', name)
        for pk in Owner.objects.filter(security_uuid__isnull=True).values_list('pk', flat=True).iterator():
            Owner.objects.filter(pk=pk, security_uuid__isnull=True).update(security_uuid=uuid.uuid4())


def refuse_sealed_rollback(apps, schema_editor):
    for name in OWNERS:
        Owner = apps.get_model('legal', name)
        if Owner.objects.using(schema_editor.connection.alias).exclude(security_state='legacy-v0').exists():
            raise RuntimeError('SEALED_FIELD_SCHEMA_ROLLBACK_REFUSED')


class Migration(migrations.Migration):
    dependencies = [('legal', '0002_legalfactsnapshot')]
    operations = [
        operation
        for name in OWNERS
        for operation in (
            migrations.AddField(model_name=name, name='security_uuid', field=models.UUIDField(null=True, editable=False)),
            migrations.AddField(model_name=name, name='security_revision', field=models.PositiveBigIntegerField(default=0, editable=False)),
            migrations.AddField(model_name=name, name='security_state', field=models.CharField(default='legacy-v0', editable=False, max_length=16)),
            migrations.AddField(model_name=name, name='security_envelopes', field=models.JSONField(default=dict, editable=False)),
        )
    ] + [migrations.RunPython(assign_object_ids, migrations.RunPython.noop)] + [
        migrations.AlterField(model_name=name, name='security_uuid', field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True))
        for name in OWNERS
    ] + [
        migrations.AddConstraint(model_name='legalanalysistask', constraint=models.CheckConstraint(
            condition=models.Q(security_state='legacy-v0') | models.Q(input_text=''), name='legal_task_sealed_no_plaintext')),
        migrations.AddConstraint(model_name='legalreport', constraint=models.CheckConstraint(
            condition=models.Q(security_state='legacy-v0') | models.Q(content=''), name='legal_report_sealed_no_plaintext')),
        migrations.AddConstraint(model_name='legalfactsnapshot', constraint=models.CheckConstraint(
            condition=models.Q(security_state='legacy-v0') | models.Q(manual_notes=''), name='legal_fact_sealed_no_plaintext')),
        migrations.RunPython(migrations.RunPython.noop, refuse_sealed_rollback),
    ]
