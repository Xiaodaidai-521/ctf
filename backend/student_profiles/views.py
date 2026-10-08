from django.db import transaction
from datetime import timedelta

from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .models import (
    LearningDirection,
    StudentProfile,
    LearningPreference,
    LearningPersona,
    OnboardingInterview,
    StudentProfileReport,
)
from .serializers import (
    LearningDirectionSerializer,
    StudentProfileSerializer,
    LearningPersonaSerializer,
    OnboardingSerializer,
    StudentProfileReportSerializer,
)
from .persona_service import ensure_learning_persona
from .onboarding_service import ONBOARDING_QUESTIONS, complete_interview
from .growth_service import refresh_dynamic_growth



DIRECTION_KEYS = ('web', 'crypto', 'pwn', 'reverse', 'forensics', 'misc')
DIRECTION_LABELS = {
    'web': 'Web 安全',
    'crypto': '密码学',
    'pwn': '二进制安全',
    'reverse': '逆向工程',
    'forensics': '电子取证',
    'misc': '安全杂项',
}
VALID_SCORE_DAYS = 90
MIN_SCORE_INTERVAL_DAYS = 7


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_dimension_scores(raw, assume_percent=False):
    if not isinstance(raw, dict):
        return {}
    normalized = {}
    for key in DIRECTION_KEYS:
        value = raw.get(key)
        if value is None:
            continue
        score = _to_float(value, 0.0)
        if assume_percent or score > 5:
            normalized[key] = round(max(0, min(score, 100)), 1)
        else:
            normalized[key] = round(max(0, min(score, 5)) * 20, 1)
    return normalized


def _average_score(scores):
    values = [float(v) for v in scores.values() if isinstance(v, (int, float))]
    return round(sum(values) / len(values), 2) if values else 0.0


def _get_effective_admin_scores(student, limit=8):
    try:
        from learning_analytics.models import AdminLearningScore
    except Exception:
        return []

    today = timezone.localdate()
    cutoff = today - timedelta(days=VALID_SCORE_DAYS)
    candidates = AdminLearningScore.objects.filter(
        student=student,
        measured_at__gte=cutoff,
        measured_at__lte=today,
    ).order_by('-measured_at', '-created_at')

    effective = []
    for score in candidates:
        if not effective:
            effective.append(score)
        else:
            interval = (effective[-1].measured_at - score.measured_at).days
            if interval >= MIN_SCORE_INTERVAL_DAYS:
                effective.append(score)
        if len(effective) == limit:
            break
    return effective


def _build_growth_recommendation(user, dimensions, current_score):
    weakest = sorted(dimensions, key=lambda item: item['current_score']) if dimensions else []
    weakest_label = weakest[0]['label'] if weakest else '基础能力'
    recommendation = {
        'title': f'优先强化{weakest_label}',
        'content': f'建议围绕 {weakest_label} 做一轮针对性练习，并结合学习路径补齐概念与题型。',
        'action_text': '查看学习路径',
        'route': '/learning-paths',
    }

    try:
        from learning_analytics.models import LearningRecommendation
        latest = LearningRecommendation.objects.filter(
            user=user,
            status='active',
        ).order_by('priority', '-generated_at').first()
        if latest:
            target_type = (latest.target_type or '').lower()
            route = '/learning-paths'
            if 'resource' in target_type:
                route = '/resources'
            elif 'challenge' in target_type:
                route = '/challenges'
            recommendation = {
                'title': latest.title or recommendation['title'],
                'content': latest.content or latest.reason or recommendation['content'],
                'action_text': latest.action_text or recommendation['action_text'],
                'route': route,
            }
    except Exception:
        pass

    if current_score >= 85 and not weakest:
        recommendation = {
            'title': '保持高阶训练节奏',
            'content': '当前画像表现稳定，建议继续挑战综合题并沉淀复盘记录。',
            'action_text': '查看学习路径',
            'route': '/learning-paths',
        }

    return recommendation

class CanReviewStudentProfileReports(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or getattr(request.user, 'role', '') in ('admin', 'teacher'))
        )


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
        if not profile.initial_self_assessed_skills:
            profile.initial_self_assessed_skills = dict(profile.self_assessed_skills or {})
        if not profile.initial_profile_captured_at:
            profile.initial_profile_captured_at = timezone.now()
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

        growth = refresh_dynamic_growth(request.user)
        persona, _ = LearningPersona.objects.get_or_create(profile=profile)
        result = {'persona': persona, 'status': 'initial', 'from_cache': True}
        if growth['eligible_for_ai']:
            result = ensure_learning_persona(request.user, force=False)
            persona = result['persona']
        serializer = LearningPersonaSerializer(persona)
        data = dict(serializer.data)
        data['from_cache'] = result.get('from_cache', False)
        data['generation_status'] = result.get('status') or data.get('generation_status')
        data['dynamic_growth'] = growth
        report = StudentProfileReport.objects.filter(profile=profile, report_type='initial').first()
        data['source_report'] = StudentProfileReportSerializer(report).data if report else None
        return Response(data)



class DynamicGrowthProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(refresh_dynamic_growth(request.user))


class OnboardingInterviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_interview(self, user):
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        LearningPreference.objects.get_or_create(profile=profile)
        LearningPersona.objects.get_or_create(profile=profile)
        interview, _ = OnboardingInterview.objects.get_or_create(profile=profile)
        return interview

    def get(self, request):
        interview = self._get_interview(request.user)
        report = StudentProfileReport.objects.filter(profile=interview.profile, report_type='initial').first()
        return Response({
            'questions': ONBOARDING_QUESTIONS,
            'answers': interview.answers,
            'current_question': interview.current_question,
            'status': interview.status,
            'report': StudentProfileReportSerializer(report).data if report else None,
        })

    def post(self, request):
        try:
            question_id = int(request.data.get('question_id'))
        except (TypeError, ValueError):
            return Response({'question_id': ['问题编号无效']}, status=status.HTTP_400_BAD_REQUEST)
        if question_id < 1 or question_id > len(ONBOARDING_QUESTIONS):
            return Response({'question_id': ['问题编号超出范围']}, status=status.HTTP_400_BAD_REQUEST)

        answer = str(request.data.get('answer') or '').strip()
        if len(answer) < 2:
            return Response({'answer': ['请至少输入两个字']}, status=status.HTTP_400_BAD_REQUEST)
        if len(answer) > 4000:
            return Response({'answer': ['单题回答不能超过 4000 字']}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            interview = self._get_interview(request.user)
            interview = OnboardingInterview.objects.select_for_update().get(pk=interview.pk)
            if interview.status == 'completed':
                report = StudentProfileReport.objects.filter(source_interview=interview).first()
                if report is None:
                    report = StudentProfileReport.objects.filter(
                        profile=interview.profile,
                        report_type='initial',
                    ).first()
                if report is not None:
                    return Response({
                        'completed': True,
                        'report': StudentProfileReportSerializer(report).data,
                    })

            answers = dict(interview.answers or {})
            answers[str(question_id)] = answer
            next_question = next(
                (item for item in ONBOARDING_QUESTIONS if str(item['id']) not in answers),
                None,
            )
            interview.answers = answers
            interview.current_question = next_question['id'] if next_question else len(ONBOARDING_QUESTIONS) + 1
            interview.save(update_fields=['answers', 'current_question', 'updated_at'])

            if next_question is None:
                report = complete_interview(interview)
                return Response({
                    'completed': True,
                    'assistant_message': '初始学习画像已经生成。我会在后续学习中持续用真实数据校正这份画像。',
                    'report': StudentProfileReportSerializer(report).data,
                })

        return Response({
            'completed': False,
            'assistant_message': '收到，我会把这部分作为画像分析依据。',
            'current_question': interview.current_question,
            'next_question': next_question,
        })


class StudentProfileReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = StudentProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response([], status=status.HTTP_200_OK)
        reports = StudentProfileReport.objects.filter(profile=profile)
        return Response(StudentProfileReportSerializer(reports, many=True).data)


class PersonaGrowthView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = StudentProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response(None, status=status.HTTP_200_OK)

        initial_report = StudentProfileReport.objects.filter(
            profile=profile,
            report_type='initial',
        ).order_by('created_at').first()
        report_data = initial_report.report_data if initial_report and isinstance(initial_report.report_data, dict) else {}
        baseline_raw = report_data.get('ability_scores') if isinstance(report_data.get('ability_scores'), dict) else {}
        baseline_scores = _normalize_dimension_scores(baseline_raw, assume_percent=True)
        if not baseline_scores:
            baseline_scores = _normalize_dimension_scores(profile.initial_self_assessed_skills or {}, assume_percent=False)
        if not baseline_scores:
            baseline_scores = _normalize_dimension_scores(profile.self_assessed_skills or {}, assume_percent=False)
        if not baseline_scores:
            return Response(None, status=status.HTTP_200_OK)

        effective_scores = _get_effective_admin_scores(request.user)
        latest_score = effective_scores[0] if effective_scores else None
        current_scores = {}
        current_updated_at = profile.updated_at
        current_source = 'self_assessment'
        if latest_score and isinstance(latest_score.dimension_scores, dict) and latest_score.dimension_scores:
            current_scores = _normalize_dimension_scores(latest_score.dimension_scores, assume_percent=True)
            current_updated_at = latest_score.updated_at
            current_source = 'admin_score'
        else:
            current_scores = _normalize_dimension_scores(profile.self_assessed_skills or {}, assume_percent=False)
        if not current_scores:
            current_scores = dict(baseline_scores)

        dimensions = []
        for key in DIRECTION_KEYS:
            baseline_value = baseline_scores.get(key, 0.0)
            current_value = current_scores.get(key, baseline_value)
            dimensions.append({
                'key': key,
                'label': DIRECTION_LABELS.get(key, key),
                'baseline_score': round(baseline_value, 1),
                'current_score': round(current_value, 1),
                'change': round(current_value - baseline_value, 1),
            })

        baseline_score = _average_score(baseline_scores)
        current_score = round(float(latest_score.total_score), 2) if latest_score else _average_score(current_scores)
        history = []
        baseline_at = initial_report.created_at if initial_report else (profile.initial_profile_captured_at or profile.created_at)
        if baseline_at:
            history.append({
                'date': baseline_at.date().isoformat(),
                'score': baseline_score,
                'label': 'initial',
            })
        for score in reversed(effective_scores[:7]):
            history.append({
                'date': score.measured_at.isoformat(),
                'score': round(float(score.total_score), 2),
                'label': 'admin_score',
            })

        return Response({
            'baseline': {
                'score': baseline_score,
                'updated_at': baseline_at.isoformat() if baseline_at else None,
                'source_report_id': initial_report.id if initial_report else None,
            },
            'current': {
                'score': current_score,
                'updated_at': current_updated_at.isoformat() if current_updated_at else None,
                'source': current_source,
            },
            'dimensions': dimensions,
            'history': history[-8:],
            'recommendation': _build_growth_recommendation(request.user, dimensions, current_score),
            'meta': {
                'update_rule': '动态画像取最近90天评分，每两次有效评分间隔不少于7天',
            },
        })


class StudentProfileReportReviewView(APIView):
    permission_classes = [CanReviewStudentProfileReports]

    def get(self, request):
        try:
            student_id = int(request.query_params.get('student_id'))
        except (TypeError, ValueError):
            return Response({'student_id': ['请提供有效的学生 ID']}, status=status.HTTP_400_BAD_REQUEST)

        reports = StudentProfileReport.objects.select_related('profile__user').filter(
            profile__user_id=student_id,
        )
        return Response({
            'student_id': student_id,
            'reports': StudentProfileReportSerializer(reports, many=True).data,
        })
