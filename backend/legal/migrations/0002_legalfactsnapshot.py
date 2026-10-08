import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('legal', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LegalFactSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_kind', models.CharField(choices=[('automated', 'Automated'), ('hybrid', 'Hybrid')], max_length=20)),
                ('scope', models.JSONField(default=dict)),
                ('automated_facts', models.JSONField(default=dict)),
                ('manual_notes', models.TextField(blank=True)),
                ('warnings', models.JSONField(blank=True, default=list)),
                ('evidence_refs', models.JSONField(blank=True, default=list)),
                ('preview_hash', models.CharField(db_index=True, max_length=64)),
                ('snapshot_hash', models.CharField(db_index=True, max_length=64)),
                ('extraction_version', models.CharField(default='v1', max_length=30)),
                ('redaction_version', models.CharField(default='v1', max_length=30)),
                ('confirmed_at', models.DateTimeField(auto_now_add=True)),
                (
                    'analysis_task',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='fact_snapshots',
                        to='legal.legalanalysistask',
                    ),
                ),
                (
                    'confirmed_by',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='confirmed_legal_fact_snapshots',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={'ordering': ['-confirmed_at']},
        ),
    ]
