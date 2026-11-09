import uuid

from django.db import migrations, models
import users.models


def assign_object_ids(apps, schema_editor):
    User = apps.get_model('users', 'CTFUser')
    for pk in User.objects.filter(security_uuid__isnull=True).values_list('pk', flat=True).iterator():
        User.objects.filter(pk=pk, security_uuid__isnull=True).update(security_uuid=uuid.uuid4())


def refuse_sealed_rollback(apps, schema_editor):
    rows = apps.get_model('users', 'CTFUser').objects.using(schema_editor.connection.alias)
    if rows.exclude(security_state='legacy-v0').exists():
        raise RuntimeError('SEALED_FIELD_SCHEMA_ROLLBACK_REFUSED')


class Migration(migrations.Migration):
    dependencies = [('users', '0005_ctfuser_is_course_owner')]
    operations = [
        migrations.AlterModelManagers(name='ctfuser', managers=[('objects', users.models.CTFUserManager())]),
        migrations.AddField(model_name='ctfuser', name='security_uuid', field=models.UUIDField(null=True, editable=False)),
        migrations.AddField(model_name='ctfuser', name='security_revision', field=models.PositiveBigIntegerField(default=0, editable=False)),
        migrations.AddField(model_name='ctfuser', name='security_state', field=models.CharField(default='legacy-v0', editable=False, max_length=16)),
        migrations.AddField(model_name='ctfuser', name='security_envelopes', field=models.JSONField(default=dict, editable=False)),
        migrations.AddField(model_name='ctfuser', name='email_index', field=models.CharField(blank=True, default='', max_length=100, db_index=True, editable=False)),
        migrations.AddField(model_name='ctfuser', name='email_index_previous', field=models.CharField(blank=True, default='', max_length=100, db_index=True, editable=False)),
        migrations.RunPython(assign_object_ids, migrations.RunPython.noop),
        migrations.AlterField(model_name='ctfuser', name='security_uuid', field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
        migrations.AddConstraint(model_name='ctfuser', constraint=models.CheckConstraint(
            condition=models.Q(security_state='legacy-v0') | models.Q(email=''), name='user_sealed_email_no_plaintext')),
        migrations.RunPython(migrations.RunPython.noop, refuse_sealed_rollback),
    ]
