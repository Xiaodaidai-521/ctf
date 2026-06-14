from django.core.management.base import BaseCommand

from ai_assistant.models import ChallengeKnowledgePack, CategoryKnowledgePack
from ai_assistant.service import MultiAgentChatService
from challenges.models import Challenge


class Command(BaseCommand):
    help = 'Rebuild challenge-centric and category-centric knowledge packs.'

    def handle(self, *args, **options):
        service = MultiAgentChatService()

        challenges = list(
            Challenge.objects.filter(is_active=True).select_related('category').order_by('id')
        )
        self.stdout.write(f'Rebuilding challenge packs for {len(challenges)} active challenges...')

        category_names = set()
        rebuilt_challenges = 0
        for challenge in challenges:
            payload = service.build_challenge_knowledge_pack_payload(challenge)
            ChallengeKnowledgePack.objects.update_or_create(
                challenge=challenge,
                defaults={
                    'category_name': payload.get('category_name', ''),
                    'difficulty': payload.get('difficulty', ''),
                    'score': payload.get('score', 0),
                    'keywords': payload.get('keywords', []),
                    'summary': payload.get('summary', ''),
                    'challenge_snapshot': payload.get('challenge_snapshot', {}),
                    'related_challenges': payload.get('related_challenges', []),
                    'related_articles': payload.get('related_articles', []),
                    'related_resources': payload.get('related_resources', []),
                    'context_text': payload.get('context_text', ''),
                    'pack_version': payload.get('pack_version', 1),
                    'metadata': payload.get('metadata', {}),
                },
            )
            rebuilt_challenges += 1
            if challenge.category and challenge.category.name:
                category_names.add(challenge.category.name)

        self.stdout.write(f'Rebuilt {rebuilt_challenges} challenge packs.')

        self.stdout.write(f'Rebuilding category packs for {len(category_names)} categories...')
        rebuilt_categories = 0
        for category_name in sorted(category_names):
            payload = service.build_category_knowledge_pack_payload(category_name)
            CategoryKnowledgePack.objects.update_or_create(
                category_name=category_name,
                defaults={
                    'keywords': payload.get('keywords', []),
                    'featured_challenges': payload.get('featured_challenges', []),
                    'featured_articles': payload.get('featured_articles', []),
                    'featured_resources': payload.get('featured_resources', []),
                    'context_text': payload.get('context_text', ''),
                    'pack_version': payload.get('pack_version', 1),
                    'metadata': payload.get('metadata', {}),
                },
            )
            rebuilt_categories += 1

        self.stdout.write(self.style.SUCCESS(
            f'Knowledge pack rebuild complete: {rebuilt_challenges} challenges, {rebuilt_categories} categories.'
        ))
