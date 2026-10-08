from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('student_profiles', '0007_studentprofile_initial_portrait')]

    operations = [
        migrations.CreateModel(
            name='DynamicGrowthProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_learning_seconds', models.PositiveIntegerField(default=0)),
                ('completed_question_count', models.PositiveIntegerField(default=0)),
                ('correct_question_count', models.PositiveIntegerField(default=0)),
                ('correct_rate', models.FloatField(default=0)),
                ('knowledge_mastery', models.JSONField(blank=True, default=dict)),
                ('ability_level', models.FloatField(default=0)),
                ('risk_level', models.CharField(default='pending', max_length=20)),
                ('recommendation_preferences', models.JSONField(blank=True, default=dict)),
                ('analysis_status', models.CharField(choices=[('insufficient_data', 'Insufficient data'), ('ready', 'Ready for analysis'), ('completed', 'Completed'), ('failed', 'Failed')], default='insufficient_data', max_length=24)),
                ('analysis', models.JSONField(blank=True, default=dict)),
                ('analysis_input_signature', models.CharField(blank=True, db_index=True, max_length=64)),
                ('last_analyzed_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('profile', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='dynamic_growth', to='student_profiles.studentprofile')),
            ],
        ),
    ]
