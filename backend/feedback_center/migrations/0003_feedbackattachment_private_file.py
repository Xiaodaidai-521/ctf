from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('feedback_center', '0002_feedbackcandidate_feedbackcandidateevent_and_more')]

    operations = [
        migrations.AddField(
            model_name='feedbackattachment',
            name='private_file',
            field=models.JSONField(blank=True, default=dict, editable=False),
        ),
    ]
