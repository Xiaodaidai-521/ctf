from django.db import migrations, models
import django.db.models.deletion


def backfill_persona_source_report(apps, schema_editor):
    Persona = apps.get_model('student_profiles', 'LearningPersona')
    Report = apps.get_model('student_profiles', 'StudentProfileReport')

    for persona in Persona.objects.all().iterator():
        traits = persona.persona_traits if isinstance(persona.persona_traits, dict) else {}
        meta = traits.get('_meta') if isinstance(traits.get('_meta'), dict) else {}
        report_id = meta.get('report_id')
        report = None
        if report_id:
            report = Report.objects.filter(id=report_id, profile_id=persona.profile_id).first()
        if report is None:
            report = (
                Report.objects.filter(profile_id=persona.profile_id, report_type='initial')
                .order_by('-version', '-created_at')
                .first()
            )
        if report:
            persona.source_report_id = report.id
            persona.save(update_fields=['source_report'])


class Migration(migrations.Migration):
    dependencies = [
        ('student_profiles', '0005_profile_report_traceability'),
    ]

    operations = [
        migrations.AddField(
            model_name='learningpersona',
            name='source_report',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='derived_personas',
                to='student_profiles.studentprofilereport',
                verbose_name='来源报表',
            ),
        ),
        migrations.RunPython(backfill_persona_source_report, migrations.RunPython.noop),
    ]
