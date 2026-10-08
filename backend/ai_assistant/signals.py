"""Cache invalidation hooks for tutoring inputs."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from exams.models import ExamRecord
from learning_analytics.models import AdminLearningScore
from learning_paths.models import UserKnowledgeState, UserPathProgress
from student_profiles.models import LearningPersona, LearningPreference, StudentProfile
from submissions.models import Submission

from .cache_services import invalidate_diagnosis, invalidate_profile


def _profile_user_id(instance):
    if isinstance(instance, StudentProfile):
        return instance.user_id
    profile = getattr(instance, "profile", None)
    return getattr(profile, "user_id", None)


def _diagnosis_user_id(instance):
    return getattr(instance, "user_id", None) or getattr(instance, "student_id", None)


@receiver([post_save, post_delete], sender=StudentProfile)
@receiver([post_save, post_delete], sender=LearningPreference)
@receiver([post_save, post_delete], sender=LearningPersona)
def invalidate_profile_on_change(sender, instance, **kwargs):
    invalidate_profile(_profile_user_id(instance))


@receiver([post_save, post_delete], sender=Submission)
@receiver([post_save, post_delete], sender=ExamRecord)
@receiver([post_save, post_delete], sender=UserPathProgress)
@receiver([post_save, post_delete], sender=UserKnowledgeState)
@receiver([post_save, post_delete], sender=AdminLearningScore)
def invalidate_diagnosis_on_learning_change(sender, instance, **kwargs):
    invalidate_diagnosis(_diagnosis_user_id(instance))
