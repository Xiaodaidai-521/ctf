"""Invalidate ResourceCache whenever source resource visibility can change."""

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Resource, ResourceCache


logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender=Resource)
def invalidate_tutor_resource_cache(sender, instance, **kwargs):
    try:
        ResourceCache.objects.all().delete()
    except Exception as exc:
        logger.warning("resource_cache_invalidation_failure", extra={
            "event": "resource_cache_invalidation_failure", "error_type": type(exc).__name__,
        })
