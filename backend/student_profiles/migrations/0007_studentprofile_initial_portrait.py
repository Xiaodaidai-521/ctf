from django.db import migrations, models


def preserve_existing_profiles(apps, schema_editor):
    StudentProfile = apps.get_model('student_profiles', 'StudentProfile')
    for profile in StudentProfile.objects.filter(initial_self_assessed_skills={}):
        profile.initial_self_assessed_skills = profile.self_assessed_skills or {}
        profile.initial_profile_captured_at = profile.created_at
        profile.save(update_fields=['initial_self_assessed_skills', 'initial_profile_captured_at'])


class Migration(migrations.Migration):
    dependencies = [('student_profiles', '0006_learning_persona_source_report')]

    operations = [
        migrations.AddField(
            model_name='studentprofile',
            name='initial_self_assessed_skills',
            field=models.JSONField(blank=True, default=dict, verbose_name='初始能力画像'),
        ),
        migrations.AddField(
            model_name='studentprofile',
            name='initial_profile_captured_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='初始画像采集时间'),
        ),
        migrations.RunPython(preserve_existing_profiles, migrations.RunPython.noop),
    ]