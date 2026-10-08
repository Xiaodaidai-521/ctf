from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('agent_runtime', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserMemory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('memory_type', models.CharField(choices=[('preference', 'User Preference'), ('learning_insight', 'Learning Insight'), ('interaction_pattern', 'Interaction Pattern'), ('fact', 'Fact'), ('temporary', 'Temporary')], max_length=40)),
                ('memory_key', models.CharField(db_index=True, max_length=200)),
                ('memory_value', models.JSONField()),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_memories', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='usermemory',
            index=models.Index(fields=['user', 'memory_type'], name='agent_runti_user_id_e8c13c_idx'),
        ),
        migrations.AddIndex(
            model_name='usermemory',
            index=models.Index(fields=['user', 'memory_key'], name='agent_runti_user_id_b9679d_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='usermemory',
            unique_together={('user', 'memory_type', 'memory_key')},
        ),
    ]
