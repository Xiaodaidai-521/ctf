"""Path recommendations require an actual registered concept-to-module link."""
from django.contrib.contenttypes.models import ContentType

from .models import ConceptResource, PathModule
from .sequence_recommender import KnowledgeSequenceRecommender


class RecommendationEngine:
    def get_recommendations(self, user, limit=3):
        scores = KnowledgeSequenceRecommender(user).build_concept_scores()
        module_type = ContentType.objects.get_for_model(PathModule)
        links = ConceptResource.objects.filter(
            concept_id__in=[item.concept.pk for item in scores], content_type=module_type,
        ).order_by('id')
        modules = {module.pk: module for module in PathModule.objects.filter(
            pk__in=links.values('object_id'), learning_path__is_published=True,
        ).select_related('learning_path')}
        score_by_concept = {item.concept.pk: item for item in scores}
        recommendations = {}
        for link in links:
            module = modules.get(link.object_id)
            if module is None:
                continue
            item = score_by_concept[link.concept_id]
            path = module.learning_path
            existing = recommendations.get(path.pk)
            if existing and existing['rule_score'] >= item.score:
                continue
            recommendations[path.pk] = {
                'path_id': path.pk, 'title': path.title, 'difficulty': path.difficulty,
                'estimated_hours': path.estimated_hours,
                'reason': f'这条航线包含“{item.concept.name}”的关联章节。',
                'rule_score': item.score, 'source': 'deterministic_learning_rules',
            }
        return sorted(recommendations.values(), key=lambda row: (-row['rule_score'], row['path_id']))[:limit]
