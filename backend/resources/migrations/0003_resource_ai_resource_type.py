# Generated manually to introduce the AI resource category.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0002_resource_visibility_cache'),
    ]

    operations = [
        migrations.AlterField(
            model_name='resource',
            name='resource_type',
            field=models.CharField(
                choices=[
                    ('document', '文档'),
                    ('video', '视频'),
                    ('report', '报告'),
                    ('zip', '压缩包'),
                    ('ai_resource', 'AI资源'),
                ],
                max_length=20,
                verbose_name='资源类型',
            ),
        ),
    ]
