from django.db import migrations, models


DEFAULT_DIRECTIONS = [
    ('web', 'Web 安全', 'Web 漏洞、攻防与代码审计', 10),
    ('crypto', '密码学', '编码、古典密码与现代密码基础', 20),
    ('pwn', '二进制安全', '栈、堆、格式化字符串与漏洞利用', 30),
    ('reverse', '逆向工程', '程序分析、反汇编与算法还原', 40),
    ('forensics', '电子取证', '流量分析、内存取证与文件取证', 50),
    ('misc', '安全杂项', '隐写、脚本、综合分析与其他题型', 60),
]


def seed_learning_directions(apps, schema_editor):
    LearningDirection = apps.get_model('student_profiles', 'LearningDirection')
    for key, label, description, sort_order in DEFAULT_DIRECTIONS:
        LearningDirection.objects.update_or_create(
            key=key,
            defaults={
                'label': label,
                'description': description,
                'sort_order': sort_order,
                'is_active': True,
            },
        )


def unseed_learning_directions(apps, schema_editor):
    LearningDirection = apps.get_model('student_profiles', 'LearningDirection')
    LearningDirection.objects.filter(
        key__in=[key for key, _, _, _ in DEFAULT_DIRECTIONS],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('student_profiles', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LearningDirection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.SlugField(max_length=50, unique=True, verbose_name='标识')),
                ('label', models.CharField(max_length=100, verbose_name='名称')),
                ('description', models.TextField(blank=True, verbose_name='说明')),
                ('sort_order', models.PositiveIntegerField(default=0, verbose_name='排序')),
                ('is_active', models.BooleanField(default=True, verbose_name='启用')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
            ],
            options={
                'verbose_name': '学习方向',
                'verbose_name_plural': '学习方向',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.RunPython(seed_learning_directions, unseed_learning_directions),
    ]
