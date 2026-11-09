"""L1 is conversation/challenge scoped; L2 observations are user/concept scoped.

UserMemory and student profiles remain the existing L2 stores. Every service
access checks the current user (L3); no dialogue enters the L2 tables.
"""

from django.conf import settings
from django.db import models


class KnowledgeObservation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    concept = models.ForeignKey('learning_paths.KnowledgeConcept', on_delete=models.CASCADE)
    score = models.FloatField(default=0)
    hits = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'concept'], name='memory_user_concept_unique'),
        ]


class ConversationLedger(models.Model):
    conversation = models.ForeignKey('ai_assistant.AIConversation', on_delete=models.CASCADE)
    challenge_key = models.CharField(max_length=80)
    first_question = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['conversation', 'challenge_key'], name='memory_conversation_pair_unique'),
        ]


class LedgerEntry(models.Model):
    ledger = models.ForeignKey(ConversationLedger, on_delete=models.CASCADE, related_name='entries')
    facts = models.JSONField(default=dict)
    # Links stored messages to their segment without copying their dialogue.
    user_message = models.ForeignKey('ai_assistant.AIMessage', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
