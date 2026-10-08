from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_type', models.CharField(choices=[('learning', 'Learning'), ('ctf_assist', 'CTF Assist'), ('content', 'Content'), ('compliance', 'Compliance'), ('general', 'General')], max_length=40)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('current_step', models.CharField(blank=True, max_length=100)),
                ('plan', models.JSONField(blank=True, default=list)),
                ('retrieved_docs', models.JSONField(blank=True, default=list)),
                ('used_tools', models.JSONField(blank=True, default=list)),
                ('intermediate_result', models.JSONField(blank=True, default=dict)),
                ('final_result', models.JSONField(blank=True, default=dict)),
                ('verification_result', models.JSONField(blank=True, default=dict)),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_runs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='agentrun',
            index=models.Index(fields=['user', 'status'], name='agent_runti_user_id_7314b8_idx'),
        ),
        migrations.AddIndex(
            model_name='agentrun',
            index=models.Index(fields=['task_type', 'status'], name='agent_runti_task_ty_37a8eb_idx'),
        ),
    ]
