from django.db import migrations


def add_compliance_category(apps, schema_editor):
    Category = apps.get_model('challenges', 'Category')
    Category.objects.get_or_create(
        name='Compliance',
        defaults={
            'description': 'Legal compliance exercises for privacy, data security, consent, audit, and risk scenarios.',
        },
    )


def remove_compliance_category(apps, schema_editor):
    Category = apps.get_model('challenges', 'Category')
    Category.objects.filter(name='Compliance', challenge__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('challenges', '0006_challengearticlerelation_challengeresourcerelation'),
    ]

    operations = [
        migrations.RunPython(add_compliance_category, remove_compliance_category),
    ]
