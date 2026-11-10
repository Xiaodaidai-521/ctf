"""Persistent metadata for the existing canary mechanism; values stay with target owners."""
from django.db import models


class CanaryRegistration(models.Model):
    seed_id = models.CharField(max_length=32, unique=True)
    seed_document = models.JSONField()
    target_pk = models.CharField(max_length=160)
    actor_ref = models.CharField(max_length=160)
    packet_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=16, default='planted')
    plant_event_id = models.CharField(max_length=160)
    retire_event_id = models.CharField(max_length=160, blank=True)

    class Meta:
        app_label = 'security_policies'
