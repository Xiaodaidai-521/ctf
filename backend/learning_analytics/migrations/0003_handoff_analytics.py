from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('learning_analytics', '0002_teachinginterventionplan_adminlearningscore'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('resources', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LearningBehaviorEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('resource_retrieved', 'Resource retrieved'), ('resource_downloaded', 'Resource downloaded'), ('module_completed', 'Module completed'), ('challenge_submitted', 'Challenge submitted'), ('exam_submitted', 'Exam submitted')], max_length=32)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('occurred_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='learning_behavior_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-occurred_at']},
        ),
        migrations.CreateModel(
            name='ResourceLearningFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveSmallIntegerField()),
                ('helpful', models.BooleanField(default=True)),
                ('comment', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('resource', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='learning_feedback', to='resources.resource')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='resource_learning_feedback', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='LearningAdjustmentProposal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('rationale', models.TextField(blank=True)),
                ('adjustments', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('active', 'Active'), ('completed', 'Completed'), ('dismissed', 'Dismissed')], default='draft', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='received_learning_adjustments', to=settings.AUTH_USER_MODEL)),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='learning_adjustment_proposals', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(model_name='learningbehaviorevent', index=models.Index(fields=['student', 'event_type', '-occurred_at'], name='learning_an_student_afc79c_idx')),
        migrations.AddIndex(model_name='learningbehaviorevent', index=models.Index(fields=['-occurred_at'], name='learning_an_occurre_2d70f8_idx')),
        migrations.AddIndex(model_name='resourcelearningfeedback', index=models.Index(fields=['resource', '-updated_at'], name='learning_an_resourc_cbebaf_idx')),
        migrations.AddIndex(model_name='learningadjustmentproposal', index=models.Index(fields=['teacher', '-created_at'], name='learning_an_teacher_88577a_idx')),
        migrations.AddIndex(model_name='learningadjustmentproposal', index=models.Index(fields=['student', '-created_at'], name='learning_an_student_2dc79f_idx')),
        migrations.AddConstraint(model_name='resourcelearningfeedback', constraint=models.UniqueConstraint(fields=('student', 'resource'), name='unique_resource_learning_feedback')),
        migrations.AddConstraint(model_name='resourcelearningfeedback', constraint=models.CheckConstraint(condition=models.Q(('rating__gte', 1), ('rating__lte', 5)), name='resource_feedback_rating_1_5')),
    ]
