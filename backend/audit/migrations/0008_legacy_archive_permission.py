from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('audit', '0007_authenticated_entry')]

    operations = [
        migrations.AlterModelOptions(
            name='auditledgerentry',
            options={'ordering': ['id'], 'verbose_name': 'Audit ledger entry',
                     'verbose_name_plural': 'Audit ledger entries',
                     'permissions': [('archive_auditledgerentry', '可批准历史审计加密归档')]},
        ),
    ]
