from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('challenges', '0007_add_compliance_category')]
    operations = [
        migrations.AddField(
            model_name='challenge', name='submission_mode',
            field=models.CharField(max_length=20, default='flag',
                                   choices=[('flag', 'Flag 计分'), ('practice', '自由练习')],
                                   verbose_name='练习模式'),
        ),
        migrations.AddField(
            model_name='challengecontainer', name='runtime_metadata',
            field=models.JSONField(default=dict, blank=True, verbose_name='运行资源'),
        ),
    ]
