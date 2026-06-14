from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .models import (
    LearningDirection,
    StudentProfile,
    LearningPreference,
    LearningPersona,
)
from .serializers import (
    LearningDirectionSerializer,
    StudentProfileSerializer,
    LearningPersonaSerializer,
    OnboardingSerializer,
)
from .persona_service import ensure_learning_persona


class LearningDirectionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        directions = LearningDirection.objects.filter(is_active=True)
        serializer = LearningDirectionSerializer(directions, many=True)
        return Response(serializer.data)


class StudentProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile, created = StudentProfile.objects.get_or_create(user=request.user)
        if created:
            LearningPreference.objects.create(profile=profile)
            LearningPersona.objects.create(profile=profile)
        else:
            self._ensure_related(profile)

        serializer = StudentProfileSerializer(profile)
        return Response(serializer.data)

    def put(self, request):
        profile, created = StudentProfile.objects.get_or_create(user=request.user)
        if created:
            LearningPreference.objects.create(profile=profile)
            LearningPersona.objects.create(profile=profile)
        else:
            self._ensure_related(profile)

        serializer = StudentProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @staticmethod
    def _ensure_related(profile):
        # get_or_create 而非 hasattr：OneToOne 反向不存在时抛出的是
        # RelatedObjectDoesNotExist（非 AttributeError），hasattr 兜不住
        LearningPreference.objects.get_or_create(profile=profile)
        LearningPersona.objects.get_or_create(profile=profile)


class OnboardingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = OnboardingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        profile, _ = StudentProfile.objects.get_or_create(user=request.user)
        preference, _ = LearningPreference.objects.get_or_create(profile=profile)
        persona, _ = LearningPersona.objects.get_or_create(profile=profile)

        # 映射到模型字段
        profile.learning_goals = data.get('learning_goals', '')
        profile.self_assessed_skills = data.get('skills', {})
        profile.onboarding_completed = True
        profile.save()

        preference.preferred_pace = data.get('pace', 'self_paced')
        preference.preferred_modality = data.get('modality', [])
        preference.prefers_diagrams = data.get('prefers_diagrams', True)
        preference.prefers_code_examples = data.get('prefers_code_examples', True)
        preference.daily_study_hours = data.get('daily_hours', 2)
        preference.difficulty_bias = data.get('difficulty_bias', 0)
        preference.save()

        ensure_learning_persona(request.user, force=False)

        response_serializer = StudentProfileSerializer(profile)
        return Response(response_serializer.data)


class PersonaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = StudentProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response(
                {'detail': '请先完成学习引导'},
                status=status.HTTP_404_NOT_FOUND,
            )

        result = ensure_learning_persona(request.user, force=False)
        persona = result['persona']
        serializer = LearningPersonaSerializer(persona)
        data = dict(serializer.data)
        data['from_cache'] = result.get('from_cache', False)
        data['generation_status'] = result.get('status') or data.get('generation_status')
        return Response(data)
