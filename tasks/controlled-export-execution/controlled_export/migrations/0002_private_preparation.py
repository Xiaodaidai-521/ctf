from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("controlled_export", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="executionattempt",
            name="private_candidate",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="executionattempt",
            name="status",
            field=models.CharField(
                choices=[("running", "running"), ("prepared", "prepared"), ("unknown", "unknown"),
                         ("succeeded", "succeeded"), ("failed", "failed"), ("cancelled", "cancelled"),
                         ("stale", "stale")],
                db_index=True, default="running", max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="exportexecution",
            name="state",
            field=models.CharField(
                choices=[("queued", "queued"), ("running", "running"), ("prepared", "prepared"),
                         ("succeeded", "succeeded"), ("failed", "failed"), ("cancelled", "cancelled"),
                         ("repair_required", "repair_required")],
                db_index=True, default="queued", max_length=24,
            ),
        ),
    ]
