from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count, F, Sum, Avg, Max
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
import json

from .models import (
    LearningPath, PathModule, ModuleLab, UserPathProgress, UserModuleProgress,
    UserLabProgress, LabAttempt, KnowledgeConcept, ConceptRelation, ConceptResource,
    UserKnowledgeState, LearningPathRecommendation, ResourceRecommendation,
    UserLearningBehavior
)
from .serializers import (
    LearningPathListSerializer, LearningPathDetailSerializer,
    LearningPathCreateSerializer, PathModuleSerializer, PathModuleCreateSerializer,
    ModuleLabSerializer, UserPathProgressSerializer, UserModuleProgressSerializer,
    UserLabProgressSerializer, KnowledgeConceptSerializer, ConceptRelationSerializer,
    UserKnowledgeStateSerializer, LearningPathRecommendationSerializer,
    ResourceRecommendationSerializer, LabAttemptSerializer
)


class LearningPathViewSet(viewsets.ModelViewSet):
    """学习路径视图"""
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = LearningPath.objects.filter(is_published=True)

        # 搜索
        search = self.request.query_params.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )

        # 排序
        ordering = self.request.query_params.get('ordering', 'order')
        if ordering == 'difficulty':
            difficulty_order = {'AP': 0, 'PR': 1, 'EX': 2}
            queryset = sorted(queryset, key=lambda x: difficulty_order[x.difficulty])
        else:
            queryset = queryset.order_by(ordering)

        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return LearningPathListSerializer
        elif self.action == 'create':
            return LearningPathCreateSerializer
        return LearningPathDetailSerializer

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """开始学习路径"""
        learning_path = self.get_object()
        user_path, created = UserPathProgress.objects.get_or_create(
            user=request.user,
            learning_path=learning_path,
            defaults={
                'total_modules': learning_path.modules.filter(is_required=True).count()
            }
        )

        if created:
            # 记录行为
            UserLearningBehavior.objects.create(
                user=request.user,
                behavior_type='start_path',
                content_object=learning_path
            )

        serializer = UserPathProgressSerializer(user_path)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def progress(self, request, pk=None):
        """获取用户在路径上的进度"""
        learning_path = self.get_object()
        try:
            user_path = UserPathProgress.objects.get(
                user=request.user,
                learning_path=learning_path
            )
            serializer = UserPathProgressSerializer(user_path)
            return Response(serializer.data)
        except UserPathProgress.DoesNotExist:
            return Response({'error': '尚未开始学习此路径'}, status=404)


class PathModuleViewSet(viewsets.ModelViewSet):
    """路径模块视图"""
    serializer_class = PathModuleSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = PathModule.objects.select_related('learning_path', 'parent_module').prefetch_related('requires_modules', 'module_labs__lab')

        # 学习路径筛选
        path_id = self.request.query_params.get('learning_path') or self.request.query_params.get('path')
        if path_id:
            queryset = queryset.filter(learning_path_id=path_id)

        # 模块类型筛选
        module_type = self.request.query_params.get('module_type')
        if module_type:
            queryset = queryset.filter(module_type=module_type)

        # 只显示顶层模块
        top_level = self.request.query_params.get('top_level')
        if top_level:
            queryset = queryset.filter(parent_module=None)

        return queryset.order_by('order', 'id')

    def get_serializer_class(self):
        if self.action == 'create':
            return PathModuleCreateSerializer
        return PathModuleSerializer

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """开始学习模块"""
        module = self.get_object()
        user = request.user

        # 获取或创建用户模块进度
        user_module, created = UserModuleProgress.objects.get_or_create(
            user=user,
            module=module,
            defaults={'status': 'AVAILABLE'}
        )

        # 检查前置条件
        if not user_module.check_prerequisites():
            return Response({'error': '请先完成前置模块'}, status=400)

        # 更新状态
        if created or user_module.status == 'AVAILABLE':
            user_module.status = 'IN_PROGRESS'
            user_module.started_at = timezone.now()
            user_module.save()

            # 更新路径进度
            try:
                user_path = UserPathProgress.objects.get(
                    user=user,
                    learning_path=module.learning_path
                )
                if not user_path.current_module:
                    user_path.current_module = module
                    user_path.last_accessed = timezone.now()
                    user_path.save()
            except UserPathProgress.DoesNotExist:
                pass

            # 记录行为
            UserLearningBehavior.objects.create(
                user=user,
                behavior_type='view_theory',
                content_object=module
            )

        serializer = UserModuleProgressSerializer(user_module)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """完成模块"""
        module = self.get_object()
        user = request.user

        try:
            user_module = UserModuleProgress.objects.get(user=user, module=module)
        except UserModuleProgress.DoesNotExist:
            return Response({'error': '未找到模块进度'}, status=404)

        # 更新状态
        user_module.status = 'COMPLETED'
        user_module.completed_at = timezone.now()
        user_module.save()

        # 更新路径进度
        try:
            user_path = UserPathProgress.objects.get(
                user=user,
                learning_path=module.learning_path
            )
            user_path.update_progress()
        except UserPathProgress.DoesNotExist:
            pass

        # 记录行为
        UserLearningBehavior.objects.create(
            user=user,
            behavior_type='complete_module',
            content_object=module
        )

        serializer = UserModuleProgressSerializer(user_module)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def labs(self, request, pk=None):
        """获取模块关联的实验"""
        module = self.get_object()
        module_labs = module.module_labs.select_related('lab').order_by('order')
        serializer = ModuleLabSerializer(module_labs, many=True)
        return Response(serializer.data)


class UserProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """用户进度视图"""
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        """获取用户的所有进度"""
        user_paths = UserPathProgress.objects.filter(
            user=request.user
        ).select_related('learning_path', 'current_module')

        # 序列化
        data = []
        for user_path in user_paths:
            serializer = UserPathProgressSerializer(user_path)
            data.append(serializer.data)

        return Response(data)


class RecommendationViewSet(viewsets.ViewSet):
    """推荐视图"""
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        """获取个性化推荐"""
        from .recommendations import RecommendationEngine

        engine = RecommendationEngine()
        recommendations = engine.get_recommendations(request.user)

        return Response({
            'recommendations': recommendations
        })

    def _challenge_payload(self, challenge):
        if not challenge:
            return None

        return {
            'id': challenge.id,
            'title': challenge.title,
            'difficulty': challenge.difficulty,
            'difficulty_display': challenge.get_difficulty_display(),
            'category': challenge.category_id,
            'category_name': challenge.category.name if challenge.category_id else '',
        }

    def _find_practice_challenge(self, concept):
        from challenges.models import Challenge

        challenge_ct = ContentType.objects.get_for_model(Challenge)
        linked_challenge_id = ConceptResource.objects.filter(
            concept=concept,
            content_type=challenge_ct,
            role__in=['practice', 'assessment']
        ).values_list('object_id', flat=True).first()

        if linked_challenge_id:
            challenge = Challenge.objects.filter(
                id=linked_challenge_id,
                is_active=True
            ).select_related('category').first()
            if challenge:
                return challenge

        challenge = Challenge.objects.filter(
            is_active=True
        ).filter(
            Q(title__icontains=concept.name) |
            Q(description__icontains=concept.name)
        ).select_related('category').first()

        return challenge or Challenge.objects.filter(
            is_active=True
        ).select_related('category').first()

    def _review_payload(self, state):
        challenge = self._find_practice_challenge(state.concept)
        action_link = f'/challenge/{challenge.id}' if challenge else '/challenges'

        return {
            'id': state.id,
            'concept_id': state.concept_id,
            'concept_name': state.concept.name,
            'mastery_level': state.mastery_level,
            'recall_probability': state.recall_probability,
            'next_review_at': state.next_review_at,
            'last_reviewed': state.last_reviewed,
            'challenge': self._challenge_payload(challenge),
            'action_link': action_link,
        }

    @action(detail=False, methods=['get'], url_path='review-reminders')
    def review_reminders(self, request):
        """返回待复习知识点，并提供对应题目入口"""
        now = timezone.now()
        states = UserKnowledgeState.objects.filter(
            user=request.user
        ).filter(
            Q(next_review_at__lte=now) |
            Q(next_review_at__isnull=True) |
            Q(recall_probability__lt=0.65) |
            Q(mastery_level__lt=0.5)
        ).select_related('concept').order_by(
            F('next_review_at').asc(nulls_first=True),
            'recall_probability',
            'mastery_level',
            'id'
        )[:3]

        return Response({
            'results': [self._review_payload(state) for state in states]
        })

    @action(detail=False, methods=['post'], url_path='complete-review')
    @transaction.atomic
    def complete_review(self, request):
        """标记复习完成，并更新遗忘曲线"""
        state_id = request.data.get('state_id') or request.data.get('id')
        if not state_id:
            return Response({'error': 'state_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            state = UserKnowledgeState.objects.select_for_update().select_related('concept').get(
                id=state_id,
                user=request.user
            )
        except UserKnowledgeState.DoesNotExist:
            return Response({'error': 'review item not found'}, status=status.HTTP_404_NOT_FOUND)

        success = request.data.get('success', True)
        if isinstance(success, str):
            success = success.lower() not in ('false', '0', 'no')

        try:
            time_spent = int(request.data.get('time_spent', 0) or 0)
        except (TypeError, ValueError):
            time_spent = 0

        state.update_mastery(success=success, time_spent=time_spent)
        state.refresh_from_db()

        return Response(self._review_payload(state))


class KnowledgeConceptViewSet(viewsets.ModelViewSet):
    """知识概念视图"""
    serializer_class = KnowledgeConceptSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = KnowledgeConcept.objects.all()

        # 搜索
        search = self.request.query_params.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search)
            )

        return queryset.order_by('concept_type', 'name')


class LabAttemptViewSet(viewsets.ModelViewSet):
    """实验尝试视图"""
    serializer_class = LabAttemptSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return LabAttempt.objects.filter(user=self.request.user).select_related('lab_progress', 'user')

    def create(self, request):
        """提交实验答案"""
        lab_id = request.data.get('lab_id')
        answer = request.data.get('answer')
        user = request.user

        if not lab_id or not answer:
            return Response({'error': '缺少必要参数'}, status=400)

        try:
            lab_progress = UserLabProgress.objects.get(
                user=user,
                lab_id=lab_id,
                status='IN_PROGRESS'
            )
        except UserLabProgress.DoesNotExist:
            return Response({'error': '未找到进行中的实验'}, status=404)

        # 创建尝试记录
        attempt = LabAttempt.objects.create(
            lab_progress=lab_progress,
            user=user,
            answer=answer,
            is_correct=answer == lab_progress.lab.expected_answer
        )

        # 如果正确，更新进度
        if attempt.is_correct:
            lab_progress.status = 'COMPLETED'
            lab_progress.completed_at = timezone.now()
            lab_progress.save()

            # 记录行为
            UserLearningBehavior.objects.create(
                user=user,
                behavior_type='complete_lab',
                content_object=lab_progress.lab
            )

        serializer = LabAttemptSerializer(attempt)
        return Response(serializer.data)
