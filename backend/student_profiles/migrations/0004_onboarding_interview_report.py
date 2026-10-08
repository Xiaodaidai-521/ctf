from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('student_profiles', '0003_rename_student_labels')]

    operations = [
        migrations.CreateModel(
            name='OnboardingInterview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('answers', models.JSONField(default=dict, verbose_name='原始问答记录')),
                ('current_question', models.PositiveSmallIntegerField(default=1, verbose_name='当前问题')),
                ('status', models.CharField(choices=[('in_progress', '进行中'), ('completed', '已完成'), ('failed', '分析失败')], default='in_progress', max_length=20, verbose_name='状态')),
                ('ai_analysis', models.JSONField(default=dict, verbose_name='AI结构化分析')),
                ('generation_provider', models.CharField(blank=True, max_length=50, verbose_name='生成模型')),
                ('started_at', models.DateTimeField(auto_now_add=True, verbose_name='开始时间')),
                ('completed_at', models.DateTimeField(blank=True, null=True, verbose_name='完成时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('profile', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='onboarding_interview', to='student_profiles.studentprofile', verbose_name='用户画像')),
            ],
            options={'verbose_name': '入学画像问答', 'verbose_name_plural': '入学画像问答'},
        ),
        migrations.CreateModel(
            name='StudentProfileReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_type', models.CharField(default='initial', max_length=20, verbose_name='报表类型')),
                ('version', models.PositiveIntegerField(default=1, verbose_name='版本')),
                ('raw_interview', models.JSONField(default=list, verbose_name='原始问答快照')),
                ('report_data', models.JSONField(default=dict, verbose_name='结构化报表')),
                ('summary', models.TextField(blank=True, verbose_name='画像摘要')),
                ('generation_provider', models.CharField(blank=True, max_length=50, verbose_name='生成模型')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='生成时间')),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='student_profiles.studentprofile', verbose_name='用户画像')),
            ],
            options={'verbose_name': '学生画像报表', 'verbose_name_plural': '学生画像报表', 'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='studentprofilereport',
            constraint=models.UniqueConstraint(fields=('profile', 'report_type', 'version'), name='unique_profile_report_version'),
        ),
    ]
