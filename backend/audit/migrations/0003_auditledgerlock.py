from django.db import migrations, models


def seed_default_lock(apps, schema_editor):
    AuditLedgerLock = apps.get_model('audit', 'AuditLedgerLock')
    AuditLedgerLock.objects.get_or_create(key='default')


def remove_default_lock(apps, schema_editor):
    AuditLedgerLock = apps.get_model('audit', 'AuditLedgerLock')
    AuditLedgerLock.objects.filter(key='default').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0002_alter_auditevent_category_auditledgerentry'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLedgerLock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(default='default', max_length=50, unique=True)),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
            ],
            options={
                'verbose_name': 'Audit ledger lock',
                'verbose_name_plural': 'Audit ledger locks',
            },
        ),
        migrations.RunPython(seed_default_lock, remove_default_lock),
    ]
