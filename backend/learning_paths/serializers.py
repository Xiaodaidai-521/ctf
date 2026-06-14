from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db.models import Q
from .models import (
    LearningPath, PathModule, ModuleLab, UserPathProgress, UserModuleProgress,
    UserLabProgress, LabAttempt, KnowledgeConcept, ConceptRelation, ConceptResource,
    UserKnowledgeState, LearningPathRecommendation, ResourceRecommendation,
    UserLearningBehavior
)

User = get_user_model()


class LearningPathListSerializer(serializers.ModelSerializer):
    """学习路径列表序列化器"""
    total_modules = serializers.SerializerMethodField()
    total_labs = serializers.SerializerMethodField()
    modules = serializers.SerializerMethodField()

    class Meta:
        model = LearningPath
        fields = ['id', 'title', 'description', 'difficulty', 'estimated_hours',
                 'total_modules', 'total_labs', 'color', 'order', 'is_published',
                 'created_at', 'updated_at', 'modules']
        read_only_fields = ['created_at', 'updated_at']

    def get_total_modules(self, obj):
        return obj.modules.filter(is_required=True).count()

    def get_total_labs(self, obj):
        return ModuleLab.objects.filter(module__learning_path=obj).count()

    def get_modules(self, obj):
        modules = obj.modules.filter(parent_module=None).order_by('order')
        return PathModuleSerializer(modules, many=True, context=self.context).data


class PathModuleSerializer(serializers.ModelSerializer):
    module_type_display = serializers.CharField(source='get_module_type_display', read_only=True)
    sub_modules = serializers.SerializerMethodField()
    labs = serializers.SerializerMethodField()
    requires = serializers.PrimaryKeyRelatedField(
        many=True,
        read_only=True,
        source='requires_modules'
    )

    class Meta:
        model = PathModule
        fields = ['id', 'title', 'description', 'module_type', 'module_type_display',
                 'order', 'is_required', 'content', 'estimated_minutes', 'requires',
                 'sub_modules', 'labs', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_sub_modules(self, obj):
        sub_modules = obj.sub_modules.all().order_by('order')
        return PathModuleSerializer(sub_modules, many=True, context=self.context).data

    def get_labs(self, obj):
        module_labs = obj.module_labs.select_related('lab').order_by('order')
        return ModuleLabSerializer(module_labs, many=True).data


class ModuleLabSerializer(serializers.ModelSerializer):
    lab_title = serializers.CharField(source='lab.title', read_only=True)
    lab_description = serializers.CharField(source='lab.description', read_only=True)
    lab_difficulty = serializers.CharField(source='lab.difficulty', read_only=True)
    lab_score = serializers.IntegerField(source='lab.score', read_only=True)

    class Meta:
        model = ModuleLab
        fields = ['id', 'order', 'is_optional', 'lab_title', 'lab_description',
                 'lab_difficulty', 'lab_score']


class LearningPathDetailSerializer(serializers.ModelSerializer):
    """学习路径详情序列化器"""
    modules = serializers.SerializerMethodField()
    total_modules = serializers.SerializerMethodField()
    total_labs = serializers.SerializerMethodField()

    class Meta:
        model = LearningPath
        fields = ['id', 'title', 'description', 'difficulty', 'estimated_hours',
                 'total_modules', 'total_labs', 'color', 'order', 'is_published',
                 'created_at', 'updated_at', 'modules']
        read_only_fields = ['created_at', 'updated_at']

    def get_total_modules(self, obj):
        return obj.modules.filter(is_required=True).count()

    def get_total_labs(self, obj):
        return ModuleLab.objects.filter(module__learning_path=obj).count()

    def get_modules(self, obj):
        modules = obj.modules.filter(parent_module=None).order_by('order')
        return PathModuleSerializer(modules, many=True, context=self.context).data


class LearningPathCreateSerializer(serializers.ModelSerializer):
    """学习路径创建序列化器"""
    class Meta:
        model = LearningPath
        fields = ['title', 'description', 'difficulty', 'estimated_hours',
                 'color', 'order', 'is_active']


class PathModuleCreateSerializer(serializers.ModelSerializer):
    """模块创建序列化器"""
    requires = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=PathModule.objects.all(),
        write_only=True,
        required=False
    )

    class Meta:
        model = PathModule
        fields = ['title', 'description', 'module_type', 'order', 'is_required',
                 'theory_content', 'theory_url', 'estimated_minutes', 'requires']

    def create(self, validated_data):
        requires_data = validated_data.pop('requires', [])
        module = PathModule.objects.create(**validated_data)
        if requires_data:
            module.requires_modules.set(requires_data)
        return module


class UserPathProgressSerializer(serializers.ModelSerializer):
    """用户路径进度序列化器"""
    path_title = serializers.CharField(source='learning_path.title', read_only=True)
    path_difficulty = serializers.CharField(source='learning_path.difficulty', read_only=True)
    current_module_title = serializers.CharField(source='current_module.title', read_only=True)
    progress_percentage = serializers.SerializerMethodField()
    completed_labs = serializers.SerializerMethodField()
    total_labs = serializers.SerializerMethodField()

    class Meta:
        model = UserPathProgress
        fields = ['id', 'learning_path', 'path_title', 'path_difficulty',
                 'current_module', 'current_module_title', 'total_modules',
                 'completed_modules',
                 'progress_percentage', 'started_at', 'last_accessed',
                 'completed_at', 'completed_labs', 'total_labs']
        read_only_fields = ['started_at', 'last_accessed', 'completed_at']

    def get_progress_percentage(self, obj):
        if obj.total_modules == 0:
            return 0
        return int(obj.progress_percentage)

    def get_completed_labs(self, obj):
        """计算已完成的实验数"""
        from .models import UserLabProgress
        # 获取该学习路径的所有实验
        lab_ids = ModuleLab.objects.filter(
            module__learning_path=obj.learning_path
        ).values_list('lab_id', flat=True)
        # 计算已完成的实验数
        return UserLabProgress.objects.filter(
            user=obj.user,
            lab_id__in=lab_ids,
            status='COMPLETED'
        ).count()

    def get_total_labs(self, obj):
        """计算总实验数"""
        return ModuleLab.objects.filter(
            module__learning_path=obj.learning_path
        ).count()


class UserModuleProgressSerializer(serializers.ModelSerializer):
    """用户模块进度序列化器"""
    module_title = serializers.CharField(source='module.title', read_only=True)
    module_type = serializers.CharField(source='module.module_type', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = UserModuleProgress
        fields = ['id', 'module', 'module_title', 'module_type', 'status',
                 'status_display', 'started_at', 'completed_at']
        read_only_fields = ['started_at', 'completed_at']


class UserLabProgressSerializer(serializers.ModelSerializer):
    """用户实验进度序列化器"""
    lab_title = serializers.CharField(source='lab.title', read_only=True)
    lab_difficulty = serializers.CharField(source='lab.difficulty', read_only=True)
    lab_points = serializers.IntegerField(source='lab.points', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    attempts_count = serializers.SerializerMethodField()

    class Meta:
        model = UserLabProgress
        fields = ['id', 'lab', 'lab_title', 'lab_difficulty', 'lab_points',
                 'status', 'status_display', 'attempts_count',
                 'current_step', 'time_spent', 'hints_used', 'notes',
                 'first_completed_at', 'last_accessed', 'created_at']
        read_only_fields = ['first_completed_at', 'last_accessed', 'created_at']

    def get_attempts_count(self, obj):
        return obj.attempts.count()


class KnowledgeConceptSerializer(serializers.ModelSerializer):
    """知识概念序列化器"""
    related_concepts = serializers.SerializerMethodField()
    resources = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeConcept
        fields = ['id', 'name', 'description', 'concept_type', 'difficulty_level',
                 'importance', 'related_concepts', 'resources', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_related_concepts(self, obj):
        relations = ConceptRelation.objects.filter(
            Q(from_concept=obj) | Q(to_concept=obj)
        ).select_related('from_concept', 'to_concept')
        return ConceptRelationSerializer(relations, many=True).data

    def get_resources(self, obj):
        resources = obj.concept_resources.all()
        return [{'id': r.id, 'url': r.url, 'title': r.title} for r in resources]


class ConceptRelationSerializer(serializers.ModelSerializer):
    from_concept_name = serializers.CharField(source='from_concept.name', read_only=True)
    to_concept_name = serializers.CharField(source='to_concept.name', read_only=True)
    relation_type_display = serializers.CharField(source='get_relation_type_display', read_only=True)

    class Meta:
        model = ConceptRelation
        fields = ['id', 'from_concept', 'from_concept_name', 'to_concept',
                 'to_concept_name', 'relation_type', 'relation_type_display',
                 'created_at']
        read_only_fields = ['created_at']


class UserKnowledgeStateSerializer(serializers.ModelSerializer):
    """用户知识状态序列化器"""
    concept_name = serializers.CharField(source='concept.name', read_only=True)
    concept_category = serializers.CharField(source='concept.category', read_only=True)
    mastery_level_display = serializers.CharField(source='get_mastery_level_display', read_only=True)

    class Meta:
        model = UserKnowledgeState
        fields = ['id', 'concept', 'concept_name', 'concept_category',
                 'mastery_level', 'mastery_level_display', 'confidence_score',
                 'last_reviewed', 'created_at', 'updated_at']
        read_only_fields = ['last_reviewed', 'created_at', 'updated_at']


class LearningPathRecommendationSerializer(serializers.ModelSerializer):
    """学习路径推荐序列化器"""
    path_title = serializers.CharField(source='path.title', read_only=True)
    path_difficulty = serializers.CharField(source='path.difficulty', read_only=True)
    recommendation_type_display = serializers.CharField(
        source='get_recommendation_type_display', read_only=True
    )

    class Meta:
        model = LearningPathRecommendation
        fields = ['id', 'path', 'path_title', 'path_difficulty', 'score',
                 'recommendation_type', 'recommendation_type_display',
                 'reason', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class ResourceRecommendationSerializer(serializers.ModelSerializer):
    """资源推荐序列化器"""
    resource_title = serializers.CharField(source='resource.title', read_only=True)
    resource_type = serializers.CharField(source='resource.resource_type', read_only=True)
    resource_url = serializers.CharField(source='resource.url', read_only=True)

    class Meta:
        model = ResourceRecommendation
        fields = ['id', 'resource', 'resource_title', 'resource_type',
                 'resource_url', 'score', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class LabAttemptSerializer(serializers.ModelSerializer):
    """实验尝试序列化器"""
    lab_title = serializers.CharField(source='lab_progress.lab.title', read_only=True)
    lab_difficulty = serializers.CharField(source='lab_progress.lab.difficulty', read_only=True)

    class Meta:
        model = LabAttempt
        fields = ['id', 'lab_progress', 'lab_title', 'lab_difficulty', 'answer',
                 'is_correct', 'attempt_number', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {
            'answer': {'write_only': True}  # 答案不应该在前端暴露
        }
