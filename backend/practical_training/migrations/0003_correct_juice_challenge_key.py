from django.db import migrations, models


def correct_key_and_require_review(apps, schema_editor):
    mapping = apps.get_model('practical_training', 'ChallengeMapping')
    mapping.objects.filter(challenge_key='confidentialDocumentChallenge').update(
        challenge_key='directoryListingChallenge', paused=True,
        reviewed_by=None, reviewed_at=None, review_hash='',
        review_ref='r2:corrected-real-api-key-requires-teacher-review',
    )


class Migration(migrations.Migration):
    dependencies = [('practical_training', '0002_challengemapping_review_hash')]

    operations = [
        migrations.AlterField(
            model_name='challengemapping', name='challenge_key',
            field=models.CharField(default='directoryListingChallenge', max_length=80),
        ),
        migrations.RunPython(correct_key_and_require_review, migrations.RunPython.noop),
    ]
