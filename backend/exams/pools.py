"""Only server-verifiable Flag challenges can be used in a scored exam."""
from challenges.models import Challenge


def gradable_challenges(difficulty):
    candidates = Challenge.objects.filter(
        difficulty=difficulty, is_active=True, submission_mode='flag',
    )
    # Sealed flags have an empty public column, so a database flag!='' filter
    # would incorrectly exclude every encrypted challenge.
    return [challenge for challenge in candidates
            if challenge.read_protected('flag').strip()]
