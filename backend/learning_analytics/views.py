from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta

from learning_paths.models import UserKnowledgeState, ConceptRelation, UserPathProgress

from .models import AdminLearningScore, LearningInsight, TeachingInterventionPlan, WeeklyLearningSummary
from .serializers import (
    AdminLearningScoreSerializer,
    LearningInsightSerializer,
    TeachingInterventionPlanSerializer,
    WeeklyLearningSummarySerializer,
)


VALID_SCORE_DAYS = 90
MIN_SCORE_INTERVAL_DAYS = 7
SELF_ASSESSMENT_WEIGHT = 0.3
ADMIN_SCORE_WEIGHT = 0.7
DIRECTION_KEYS = ('web', 'crypto', 'pwn', 'reverse', 'forensics', 'misc')


class IsAnalyticsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or getattr(request.user, 'role', '') == 'admin')
        )


def get_effective_admin_scores(student):
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
        if len(effective) == 2:
            break
    return effective


def build_score_status_map(student):
    today = timezone.localdate()
    cutoff = today - timedelta(days=VALID_SCORE_DAYS)
    effective_ids = {score.id for score in get_effective_admin_scores(student)}
    status_map = {}
    for score in AdminLearningScore.objects.filter(student=student):
        if score.measured_at > today:
            status_map[score.id] = {'status': 'invalid', 'reason': '测评日期晚于系统当前日期'}
        elif score.measured_at < cutoff:
            status_map[score.id] = {'status': 'expired', 'reason': '超过90天时效窗口'}
        elif score.id in effective_ids:
            status_map[score.id] = {'status': 'effective', 'reason': '已纳入AI分析基准'}
        else:
            status_map[score.id] = {'status': 'filtered', 'reason': '与较新有效评分间隔不足7天或不是最新两次'}
    return status_map


def _score_payload(score):
    return {
        'id': score.id,
        'total_score': float(score.total_score),
        'dimension_scores': score.dimension_scores or {},
        'tags': score.tags or [],
        'remark': score.remark,
        'measured_at': score.measured_at.isoformat(),
        'created_at': score.created_at.isoformat(),
    }


def _normalize_self_assessed_skill(value):
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0, min(rating, 5)) / 5 * 100, 2)


def build_score_summary(student):
    if not student:
        return None

    profile = getattr(student, 'student_profile', None)
    raw_skills = profile.self_assessed_skills if profile else {}
    self_dimension_scores = {}
    for key in DIRECTION_KEYS:
        score = _normalize_self_assessed_skill(raw_skills.get(key))
        if score is not None:
            self_dimension_scores[key] = score

    self_score = None
    if self_dimension_scores:
        self_score = round(sum(self_dimension_scores.values()) / len(self_dimension_scores), 2)

    effective_scores = get_effective_admin_scores(student)
    latest_admin_score = effective_scores[0] if effective_scores else None
    admin_score = float(latest_admin_score.total_score) if latest_admin_score else None

    final_score = None
    if self_score is not None and admin_score is not None:
        final_score = round(
            self_score * SELF_ASSESSMENT_WEIGHT + admin_score * ADMIN_SCORE_WEIGHT,
            2,
        )

    return {
        'weights': {
            'self_assessment': SELF_ASSESSMENT_WEIGHT,
            'admin': ADMIN_SCORE_WEIGHT,
        },
        'self_assessment': {
            'score': self_score,
            'dimension_scores': self_dimension_scores,
            'raw_skills': raw_skills or {},
            'updated_at': profile.updated_at.isoformat() if profile else None,
        },
        'admin': {
            'score': admin_score,
            'score_id': latest_admin_score.id if latest_admin_score else None,
            'measured_at': latest_admin_score.measured_at.isoformat() if latest_admin_score else None,
            'dimension_scores': latest_admin_score.dimension_scores if latest_admin_score else {},
        },
        'final_score': final_score,
        'status': 'ready' if final_score is not None else 'incomplete',
    }


def _direction_label(key):
    labels = {
        'web': 'Web安全',
        'crypto': '密码学',
        'pwn': '二进制安全',
        'reverse': '逆向工程',
        'forensics': '数字取证',
        'misc': '综合杂项',
    }
    return labels.get(key, key)


def generate_teaching_plan(student):
    profile = getattr(student, 'student_profile', None)
    self_assessment = profile.self_assessed_skills if profile else {}
    effective_scores = get_effective_admin_scores(student)
    score_payloads = [_score_payload(score) for score in effective_scores]
    source_ids = [score.id for score in effective_scores]

    latest = score_payloads[0] if score_payloads else None
    previous = score_payloads[1] if len(score_payloads) > 1 else None
    data_age_days = None
    validity_label = '暂无有效管理员评分，基于用户自评生成'
    if latest:
        data_age_days = (timezone.localdate() - effective_scores[0].measured_at).days
        validity_label = f'基于最近{data_age_days}天评分数据'

    dimensions = latest.get('dimension_scores', {}) if latest else {}
    if not dimensions and self_assessment:
        dimensions = {
            key: round(max(0, min(float(value), 5)) / 5 * 100, 2)
            for key, value in self_assessment.items()
        }

    weak_dimensions = sorted(
        [(key, float(value)) for key, value in dimensions.items()],
        key=lambda item: item[1],
    )[:3]

    trend_text = '暂无两次有效评分对比'
    score_comparison = None
    if latest and previous:
        delta = latest['total_score'] - previous['total_score']
        trend_text = f'较上次有效评分{"提升" if delta >= 0 else "下降"} {abs(delta):.1f} 分'
        score_comparison = {
            'latest': latest,
            'previous': previous,
            'delta_total_score': round(delta, 2),
            'trend': 'up' if delta >= 0 else 'down',
        }

    focus_labels = [_direction_label(key) for key, _ in weak_dimensions]
    focus_text = '、'.join(focus_labels) if focus_labels else '基础能力巩固'
    latest_remark = latest.get('remark', '') if latest else ''
    latest_tags = latest.get('tags', []) if latest else []

    plan_items = [
        {
            'phase': '第1阶段',
            'title': '定位薄弱项并复盘错因',
            'duration': '1-3天',
            'actions': [
                f'围绕{focus_text}整理最近错题和卡点',
                '用管理员备注和自评差异确认优先级',
                '每天记录一次复盘结论，避免重复训练低收益内容',
            ],
        },
        {
            'phase': '第2阶段',
            'title': '专项训练与即时反馈',
            'duration': '4-10天',
            'actions': [
                f'优先完成{focus_text}相关学习路径和题库练习',
                '每次练习后记录解题思路、失败原因和补救动作',
                '教师根据最新评分标签调整题目难度和讲解深度',
            ],
        },
        {
            'phase': '第3阶段',
            'title': '阶段复测与方案更新',
            'duration': '11-14天',
            'actions': [
                '完成一次阶段复测，测评日期必须使用实际当天日期',
                '若距离上次有效评分不足7天，仅记录历史，不进入AI分析',
                '下一轮方案仅使用90天内且间隔合规的最新两次评分',
            ],
        },
    ]

    summary_parts = [
        f'当前教学重点为{focus_text}。',
        trend_text,
    ]
    if latest_tags:
        summary_parts.append(f'管理员标签：{"、".join(latest_tags)}。')
    if latest_remark:
        summary_parts.append(f'关键备注：{latest_remark[:80]}')

    input_snapshot = {
        'effective_scores': score_payloads,
        'score_comparison': score_comparison,
        'self_assessment': self_assessment,
        'filter_rules': {
            'valid_score_days': VALID_SCORE_DAYS,
            'min_interval_days': MIN_SCORE_INTERVAL_DAYS,
        },
        'excluded_policy': 'Expired, future-dated, and too-frequent scores are excluded before plan generation.',
        'generated_at': timezone.now().isoformat(),
    }

    plan, _ = TeachingInterventionPlan.objects.update_or_create(
        student=student,
        defaults={
            'title': '个性化教学干预方案',
            'summary': ' '.join(summary_parts),
            'plan_items': plan_items,
            'source_score_ids': source_ids,
            'self_assessment_snapshot': self_assessment,
            'input_snapshot': input_snapshot,
            'data_age_days': data_age_days,
            'validity_label': validity_label,
        },
    )
    return plan


class InsightsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 优先使用规则引擎生成洞察，回退到数据库已存储的洞察
        try:
            from ai_assistant.learning_orchestrator import LearningOrchestrator
            orchestrator = LearningOrchestrator()
            rule_insights = orchestrator.get_insights(student_id=request.user.id)
            if rule_insights:
                # 同时检查数据库中的洞察
                db_insights = LearningInsight.objects.filter(
                    student=request.user, acknowledged_at__isnull=True
                ).order_by('-generated_at')[:5]
                db_data = LearningInsightSerializer(db_insights, many=True).data
                # 合并：规则洞察在前，数据库洞察在后，去重
                existing_titles = {i['title'] for i in rule_insights}
                for di in db_data:
                    if di.get('title') not in existing_titles:
                        rule_insights.append({
                            'insight_type': di.get('insight_type', 'recommendation'),
                            'severity': di.get('severity', 'info'),
                            'title': di.get('title', ''),
                            'description': di.get('description', ''),
                            'actionable': di.get('actionable', True),
                            'action_link': di.get('action_link', ''),
                        })
                return Response(rule_insights[:12])
        except Exception:
            pass

        insights = LearningInsight.objects.filter(
            student=request.user,
            acknowledged_at__isnull=True
        ).order_by('-generated_at')[:20]
        serializer = LearningInsightSerializer(insights, many=True)
        return Response(serializer.data)


class WeeklySummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        summary = WeeklyLearningSummary.objects.filter(
            student=request.user
        ).order_by('-week_start').first()

        if not summary:
            return Response(None)

        serializer = WeeklyLearningSummarySerializer(summary)
        return Response(serializer.data)


class ProgressReportView(APIView):
    """综合进度报告：CTF 六方向得分 + 模块完成 + 概念掌握"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # 按 challenge category 分组统计正确提交
        category_scores = {}
        from submissions.models import Submission
        category_stats = (
            Submission.objects
            .filter(user=user, is_correct=True)
            .values('challenge__category__name')
            .annotate(count=Count('id'))
        )
        for entry in category_stats:
            name = entry['challenge__category__name']
            if name:
                category_scores[name] = entry['count']

        # 模块完成情况
        from learning_paths.models import UserModuleProgress
        total_modules = UserModuleProgress.objects.filter(user=user).count()
        completed_modules = UserModuleProgress.objects.filter(
            user=user, status__iexact='completed'
        ).count()
        completion_rate = (completed_modules / total_modules) if total_modules > 0 else 0

        # 概念得分
        concept_states = UserKnowledgeState.objects.filter(
            user=user
        ).select_related('concept')
        concept_scores = {
            state.concept.name: round(state.mastery_level, 2)
            for state in concept_states
        }

        return Response({
            'category_scores': category_scores,
            'total_modules': total_modules,
            'completed_modules': completed_modules,
            'completion_rate': round(completion_rate, 4),
            'concept_scores': concept_scores,
        })


class KnowledgeMapView(APIView):
    """知识图谱：节点（概念+掌握度）+ 边（概念关系）"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        states = UserKnowledgeState.objects.filter(
            user=user
        ).select_related('concept')

        concept_ids = list(states.values_list('concept_id', flat=True))
        mastery_map = {
            state.concept_id: round(state.mastery_level, 2)
            for state in states
        }

        nodes = [
            {
                'id': state.concept_id,
                'name': state.concept.name,
                'type': state.concept.concept_type,
                'mastery': mastery_map.get(state.concept_id, 0),
                'importance': state.concept.importance,
            }
            for state in states
        ]

        relations = ConceptRelation.objects.filter(
            Q(from_concept_id__in=concept_ids) | Q(to_concept_id__in=concept_ids)
        ).select_related('from_concept', 'to_concept')

        edges = [
            {
                'source': rel.from_concept_id,
                'target': rel.to_concept_id,
                'relation': rel.relation_type,
                'strength': rel.strength,
            }
            for rel in relations
        ]

        return Response({'nodes': nodes, 'edges': edges})


class AdminLearningScoreView(APIView):
    permission_classes = [IsAnalyticsAdmin]

    def get(self, request):
        student_id = request.query_params.get('student_id')
        queryset = AdminLearningScore.objects.select_related('student', 'scored_by')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        queryset = queryset.order_by('-measured_at', '-created_at')[:100]

        student = queryset[0].student if student_id and queryset else None
        if student_id and not student:
            from users.models import CTFUser
            student = CTFUser.objects.filter(id=student_id).first()
        status_map = build_score_status_map(student) if student else {}
        eligible_score_ids = [
            score.id for score in get_effective_admin_scores(student)
        ] if student else []
        serializer = AdminLearningScoreSerializer(
            queryset,
            many=True,
            context={
                'eligible_score_ids': eligible_score_ids,
                'score_status_map': status_map,
            },
        )
        return Response({
            'results': serializer.data,
            'effective_score_ids': eligible_score_ids,
            'score_summary': build_score_summary(student) if student else None,
            'filter_rules': {
                'valid_score_days': VALID_SCORE_DAYS,
                'min_interval_days': MIN_SCORE_INTERVAL_DAYS,
            },
        })

    def post(self, request):
        serializer = AdminLearningScoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        score = serializer.save(scored_by=request.user)
        status_map = build_score_status_map(score.student)
        eligible_score_ids = [item.id for item in get_effective_admin_scores(score.student)]
        output = AdminLearningScoreSerializer(
            score,
            context={
                'eligible_score_ids': eligible_score_ids,
                'score_status_map': status_map,
            },
        )
        generate_teaching_plan(score.student)
        try:
            from student_profiles.persona_service import ensure_learning_persona
            ensure_learning_persona(score.student, force=False)
        except Exception:
            pass
        return Response(output.data, status=status.HTTP_201_CREATED)


class TeachingPlanView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plan = generate_teaching_plan(request.user)
        serializer = TeachingInterventionPlanSerializer(plan)
        return Response(serializer.data)


class AdminTeachingPlanView(APIView):
    permission_classes = [IsAnalyticsAdmin]

    def get(self, request, student_id):
        from users.models import CTFUser
        student = CTFUser.objects.get(id=student_id)
        plan = generate_teaching_plan(student)
        serializer = TeachingInterventionPlanSerializer(plan)
        return Response(serializer.data)


class AdminStudentReportView(APIView):
    """管理员视图 — 学生进度与掌握报表"""
    permission_classes = [IsAnalyticsAdmin]

    def get(self, request):
        from users.models import CTFUser
        from student_profiles.models import StudentProfile
        from learning_paths.models import UserKnowledgeState
        from submissions.models import Submission

        students = CTFUser.objects.filter(role='student')
        results = []
        for user in students:
            profile = getattr(user, 'student_profile', None)
            skills = profile.self_assessed_skills if profile else {}
            onboarded = profile.onboarding_completed if profile else False
            goals = profile.learning_goals if profile else ''

            # 知识状态
            ks = UserKnowledgeState.objects.filter(user=user).select_related('concept')
            concepts = [{'name': k.concept.name, 'mastery': round(k.mastery_level, 2)} for k in ks]
            avg_m = round(sum(c['mastery'] for c in concepts) / len(concepts) * 100) if concepts else 0

            if not concepts and skills:
                concepts = [
                    {'name': self._direction_label(key), 'mastery': self._normalize_skill(value)}
                    for key, value in skills.items()
                ]
                valid_mastery = [c['mastery'] for c in concepts]
                avg_m = round(sum(valid_mastery) / len(valid_mastery) * 100) if valid_mastery else 0

            # 解题统计
            solved_count = Submission.objects.filter(user=user, is_correct=True).count()
            effective_scores = get_effective_admin_scores(user)
            latest_score = effective_scores[0] if effective_scores else None
            score_age = (timezone.localdate() - latest_score.measured_at).days if latest_score else None

            results.append({
                'id': user.id, 'username': user.username,
                'role': user.role, 'enrollment_year': user.enrollment_year,
                'score': user.score, 'solved_count': solved_count,
                'onboarded': onboarded, 'skills': skills,
                'mastery': avg_m, 'concepts': concepts, 'goals': goals,
                'self_assessed_at': profile.updated_at.isoformat() if profile and onboarded else None,
                'latest_admin_score': float(latest_score.total_score) if latest_score else None,
                'effective_score_count': len(effective_scores),
                'score_data_age_days': score_age,
                'score_validity_label': f'基于最近{score_age}天评分数据' if score_age is not None else '暂无有效管理员评分',
            })

        results.sort(key=lambda x: x['mastery'], reverse=True)
        return Response(results)

    @staticmethod
    def _normalize_skill(value):
        try:
            rating = float(value)
        except (TypeError, ValueError):
            rating = 0
        return round(max(0, min(rating, 5)) / 5, 2)

    @staticmethod
    def _direction_label(key):
        labels = {
            'web': 'Web安全',
            'crypto': '密码学',
            'pwn': '二进制安全',
            'reverse': '逆向工程',
            'forensics': '数字取证',
            'misc': '综合杂项',
        }
        return labels.get(key, key)
