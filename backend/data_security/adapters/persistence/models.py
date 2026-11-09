from django.db import models


class PolicyVersion(models.Model):
    version = models.CharField(max_length=128, unique=True)
    document = models.JSONField()

    class Meta:
        ordering = ('id',)
