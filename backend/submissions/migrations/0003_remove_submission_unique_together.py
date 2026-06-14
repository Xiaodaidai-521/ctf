from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0002_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='submission',
            unique_together=set(),
        ),
    ]
