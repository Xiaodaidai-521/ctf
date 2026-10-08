from django.db import migrations


def seed_legal_reviewer_preset(apps, schema_editor):
    AgentPreset = apps.get_model('ai_assistant', 'AgentPreset')
    AgentPreset.objects.update_or_create(
        preset_id='legal-review',
        defaults={
            'name': '法律合规审查',
            'icon': '⚖',
            'agent_ids': ['analyst', 'security', 'legal_reviewer', 'xiaohei'],
            'sort_order': 75,
            'is_active': True,
        },
    )


def unseed_legal_reviewer_preset(apps, schema_editor):
    AgentPreset = apps.get_model('ai_assistant', 'AgentPreset')
    AgentPreset.objects.filter(preset_id='legal-review').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0004_categoryknowledgepack_challengeknowledgepack'),
    ]

    operations = [
        migrations.RunPython(seed_legal_reviewer_preset, unseed_legal_reviewer_preset),
    ]
