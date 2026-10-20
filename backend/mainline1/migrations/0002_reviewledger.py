from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('mainline1', '0001_initial')]
    operations = [migrations.CreateModel(
        name='ReviewLedger',
        fields=[('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('state', models.JSONField())],
        options={'constraints': [models.CheckConstraint(condition=models.Q(id=1), name='ml1_review_single_ledger')]},
    )]
