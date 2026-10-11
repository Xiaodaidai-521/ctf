# Generated for review remediation F4: persist decision origin (environment,
# source_mode) so a production signing path can refuse an evaluation/synthetic
# decision instead of trusting a client-supplied snapshot label.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("export_risk", "0002_eventoutbox_executionauthorizationrecord_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="riskdecision",
            name="environment",
            field=models.CharField(default="production", max_length=20, verbose_name="环境"),
        ),
        migrations.AddField(
            model_name="riskdecision",
            name="source_mode",
            field=models.CharField(default="synthetic", max_length=20, verbose_name="来源模式"),
        ),
    ]
