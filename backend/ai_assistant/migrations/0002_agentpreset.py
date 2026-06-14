from django.db import migrations, models


DEFAULT_AGENT_PRESETS = [
    ('code-review', '代码审查', '🔍', ['analyst', 'developer', 'tester', 'security'], 10),
    ('architecture', '架构设计', '📐', ['analyst', 'architect', 'developer'], 20),
    ('security', '安全审计', '🛡️', ['analyst', 'security', 'tester'], 30),
    ('full', '全流程', '🔄', ['xiaohei', 'analyst', 'architect', 'developer', 'tester', 'security'], 40),
    ('teaching', '教学辅导', '🎓', ['tutor'], 50),
    ('knowledge', '知识库问答', '🧠', ['xiaohei'], 60),
    ('ai-kb', 'AI+知识库', '[!]', ['analyst', 'security', 'xiaohei'], 70),
]


def seed_agent_presets(apps, schema_editor):
    AgentPreset = apps.get_model('ai_assistant', 'AgentPreset')
    for preset_id, name, icon, agent_ids, sort_order in DEFAULT_AGENT_PRESETS:
        AgentPreset.objects.update_or_create(
            preset_id=preset_id,
            defaults={
                'name': name,
                'icon': icon,
                'agent_ids': agent_ids,
                'sort_order': sort_order,
                'is_active': True,
            },
        )


def unseed_agent_presets(apps, schema_editor):
    AgentPreset = apps.get_model('ai_assistant', 'AgentPreset')
    AgentPreset.objects.filter(
        preset_id__in=[preset_id for preset_id, _, _, _, _ in DEFAULT_AGENT_PRESETS],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentPreset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('preset_id', models.SlugField(max_length=50, unique=True, verbose_name='预设标识')),
                ('name', models.CharField(max_length=100, verbose_name='名称')),
                ('icon', models.CharField(blank=True, max_length=20, verbose_name='图标')),
                ('agent_ids', models.JSONField(default=list, verbose_name='智能体标识列表')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='排序')),
                ('is_active', models.BooleanField(default=True, verbose_name='启用')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '智能体预设',
                'verbose_name_plural': '智能体预设',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.RunPython(seed_agent_presets, unseed_agent_presets),
    ]
