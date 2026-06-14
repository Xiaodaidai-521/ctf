from django.db import migrations, models


DEFAULT_LEVEL_RULES = [
    ('S', '大师', 'CTF 界的传奇人物', 90, 10),
    ('A', '专家', 'CTF 领域的顶尖高手', 80, 20),
    ('B', '高手', '经验丰富的安全专家', 70, 30),
    ('C', '进阶', '具备一定的安全技能', 60, 40),
    ('D', '初学者', '继续努力，多加练习', 0, 50),
]


def seed_exam_level_rules(apps, schema_editor):
    ExamLevelRule = apps.get_model('exams', 'ExamLevelRule')
    for grade, title, description, min_score, sort_order in DEFAULT_LEVEL_RULES:
        ExamLevelRule.objects.update_or_create(
            grade=grade,
            defaults={
                'title': title,
                'description': description,
                'min_score': min_score,
                'sort_order': sort_order,
                'is_active': True,
            },
        )


def unseed_exam_level_rules(apps, schema_editor):
    ExamLevelRule = apps.get_model('exams', 'ExamLevelRule')
    ExamLevelRule.objects.filter(
        grade__in=[grade for grade, _, _, _, _ in DEFAULT_LEVEL_RULES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExamLevelRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grade', models.CharField(max_length=10, unique=True, verbose_name='等级')),
                ('title', models.CharField(max_length=100, verbose_name='标题')),
                ('description', models.TextField(blank=True, verbose_name='描述')),
                ('min_score', models.PositiveIntegerField(verbose_name='最低分数')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='排序')),
                ('is_active', models.BooleanField(default=True, verbose_name='启用')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '考试等级规则',
                'verbose_name_plural': '考试等级规则',
                'db_table': 'exam_level_rules',
                'ordering': ['-min_score', 'sort_order'],
            },
        ),
        migrations.RunPython(seed_exam_level_rules, unseed_exam_level_rules),
    ]
