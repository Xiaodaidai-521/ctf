from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('security_policies', '0016_export_retention_intent'),
    ]

    operations = [
        migrations.AddField(
            model_name='revealrequest',
            name='retention_scope',
            field=models.CharField(max_length=160, null=True),
        ),
        migrations.AddField(
            model_name='revealrequest',
            name='retention_registration',
            field=models.JSONField(null=True),
        ),
        migrations.CreateModel(
            name='RevealFieldRetention',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scope_ref', models.CharField(max_length=160)),
                ('object_ref', models.CharField(max_length=160)),
                ('field_ref', models.CharField(max_length=160)),
                ('context_document', models.JSONField()),
                ('generated_at', models.DateTimeField()),
                ('ciphertext_hash', models.CharField(max_length=64)),
                ('registration', models.JSONField()),
            ],
        ),
    ]
