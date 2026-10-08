import hashlib
import json

from django.db import migrations, models
import django.db.models.deletion


def backfill_report_traceability(apps, schema_editor):
    Report = apps.get_model('student_profiles', 'StudentProfileReport')
    Interview = apps.get_model('student_profiles', 'OnboardingInterview')

    for report in Report.objects.all().iterator():
        payload = json.dumps(
            report.raw_interview or [],
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        )
        report.input_signature = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        report.generation_status = (
            'fallback'
            if isinstance(report.report_data, dict) and report.report_data.get('generation_error')
            else 'completed'
        )
        report.save(update_fields=['input_signature', 'generation_status'])

    for interview in Interview.objects.filter(status='completed').iterator():
        report = (
            Report.objects.filter(
                profile_id=interview.profile_id,
                report_type='initial',
                source_interview__isnull=True,
            )
            .order_by('-version', '-created_at')
            .first()
        )
        if report:
            report.source_interview_id = interview.id
            report.save(update_fields=['source_interview'])


class Migration(migrations.Migration):
    dependencies = [
        ('student_profiles', '0004_onboarding_interview_report'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentprofilereport',
            name='generation_status',
            field=models.CharField(
                choices=[('completed', '生成完成'), ('fallback', '规则兜底')],
                default='completed',
                max_length=20,
                verbose_name='生成状态',
            ),
        ),
        migrations.AddField(
            model_name='studentprofilereport',
            name='input_signature',
            field=models.CharField(blank=True, db_index=True, max_length=64, verbose_name='输入签名'),
        ),
        migrations.AddField(
            model_name='studentprofilereport',
            name='source_interview',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='report',
                to='student_profiles.onboardinginterview',
                verbose_name='来源访谈',
            ),
        ),
        migrations.RunPython(backfill_report_traceability, migrations.RunPython.noop),
    ]
