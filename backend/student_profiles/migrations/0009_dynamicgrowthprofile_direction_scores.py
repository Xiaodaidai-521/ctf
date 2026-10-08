from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('student_profiles', '0008_dynamicgrowthprofile')]

    operations = [
        migrations.AddField(
            model_name='dynamicgrowthprofile',
            name='initial_scores',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='dynamicgrowthprofile',
            name='dynamic_scores',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='dynamicgrowthprofile',
            name='growth_deltas',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='dynamicgrowthprofile',
            name='growth_evidence',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
