from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('learning_analytics', '0004_learning_effect_pipeline')]

    operations = [
        migrations.AddField(model_name='learningauditjob', name='attempt_count', field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name='learningauditjob', name='idempotency_key', field=models.CharField(default='', max_length=160, unique=True), preserve_default=False),
    ]
