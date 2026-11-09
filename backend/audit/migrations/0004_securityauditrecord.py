from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('audit', '0003_auditledgerlock')]

    operations = [
        migrations.CreateModel(
            name='SecurityAuditRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_id', models.CharField(max_length=64, unique=True)),
                ('event', models.JSONField()),
                ('stored_at', models.DateTimeField()),
                ('audit_event', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to='audit.auditevent')),
                ('ledger_entry', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='audit.auditledgerentry')),
            ],
        ),
    ]
