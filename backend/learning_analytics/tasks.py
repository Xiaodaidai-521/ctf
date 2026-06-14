from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.contrib.auth import get_user_model

from learning_paths.models import UserLearningBehavior, UserKnowledgeState

from .models import LearningInsight, WeeklyLearningSummary

User = get_user_model()

# CTF 六方向对应的 challenge category 名称
CTF_CATEGORIES = ['web', 'crypto', 'misc', 'pwn', 'reverse', 'forensics']


def generate_insights():
    """
    基于规则生成学习洞察（不依赖 AI API）：
    - mastery < 0.4 的概念 → weakness 洞察
    - 近7天学习时长 < 1h → warning 洞察
    - mastery > 0.7 的概念 → strength 洞察
    """
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    active_user_ids = (
        UserLearningBehavior.objects
        .filter(timestamp__gte=week_ago)
        .values_list('user_id', flat=True)
        .distinct()
    )

    created_count = 0

    for user_id in active_user_ids:
        student = User.objects.get(pk=user_id)

        # 薄弱概念：mastery < 0.4
        weak_states = UserKnowledgeState.objects.filter(
            user_id=user_id,
            mastery_level__lt=0.4
        ).select_related('concept')

        for state in weak_states:
            if not LearningInsight.objects.filter(
                student=student,
                insight_type='weakness',
                concept=state.concept,
                generated_at__gte=now - timedelta(hours=24)
            ).exists():
                LearningInsight.objects.create(
                    student=student,
                    insight_type='weakness',
                    concept=state.concept,
                    title=f'需要加强：{state.concept.name}',
                    description=f'你对「{state.concept.name}」的掌握程度较低（{state.mastery_level:.0%}），建议安排时间重点学习。',
                    severity='warning',
                    actionable=True,
                    action_link=f'/learning/concepts/{state.concept.slug}'
                )
                created_count += 1

        # 近7天学习时长不足
        total_seconds = (
            UserLearningBehavior.objects
            .filter(user_id=user_id, timestamp__gte=week_ago)
            .aggregate(total=Sum('time_spent'))['total'] or 0
        )
        if total_seconds < 3600:
            if not LearningInsight.objects.filter(
                student=student,
                insight_type='weakness',
                concept__isnull=True,
                title__startswith='本周学习时长不足',
                generated_at__gte=now - timedelta(hours=24)
            ).exists():
                minutes = total_seconds // 60
                LearningInsight.objects.create(
                    student=student,
                    insight_type='weakness',
                    concept=None,
                    title=f'本周学习时长不足（仅 {minutes} 分钟）',
                    description='近7天你的学习时间不足1小时，建议每天至少投入30分钟保持学习节奏。',
                    severity='warning',
                    actionable=True,
                    action_link='/learning-paths'
                )
                created_count += 1

        # 强势概念：mastery > 0.7
        strong_states = UserKnowledgeState.objects.filter(
            user_id=user_id,
            mastery_level__gt=0.7
        ).select_related('concept')

        for state in strong_states:
            if not LearningInsight.objects.filter(
                student=student,
                insight_type='strength',
                concept=state.concept,
                generated_at__gte=now - timedelta(hours=24)
            ).exists():
                LearningInsight.objects.create(
                    student=student,
                    insight_type='strength',
                    concept=state.concept,
                    title=f'掌握良好：{state.concept.name}',
                    description=f'你对「{state.concept.name}」的掌握达到 {state.mastery_level:.0%}，可以尝试更高难度的挑战。',
                    severity='info',
                    actionable=True,
                    action_link=f'/challenges?concept={state.concept.slug}'
                )
                created_count += 1

    return created_count


def compute_weekly_summaries():
    """按周聚合用户学习行为数据，批量创建 WeeklyLearningSummary。"""
    now = timezone.now()
    week_start = (now - timedelta(days=now.weekday())).date()

    active_user_ids = (
        UserLearningBehavior.objects
        .filter(timestamp__date__gte=week_start)
        .values_list('user_id', flat=True)
        .distinct()
    )

    created_count = 0

    for user_id in active_user_ids:
        student = User.objects.get(pk=user_id)
        behaviors = UserLearningBehavior.objects.filter(
            user_id=user_id,
            timestamp__date__gte=week_start
        )

        total_seconds = behaviors.aggregate(total=Sum('time_spent'))['total'] or 0
        modules_completed = behaviors.filter(behavior_type='complete_module').count()
        exercises_completed = behaviors.filter(behavior_type='submit_flag', success=True).count()

        # AI 交互次数
        from ai_assistant.models import AIConversation
        ai_interactions = AIConversation.objects.filter(
            user_id=user_id,
            created_at__date__gte=week_start
        ).count()

        # 沙箱执行次数
        from challenges.models import ChallengeContainer
        sandbox_executions = ChallengeContainer.objects.filter(
            user_id=user_id,
            created_at__date__gte=week_start
        ).count()

        # 概念掌握度快照
        concept_states = UserKnowledgeState.objects.filter(
            user_id=user_id
        ).select_related('concept')
        concepts_mastered = {
            state.concept.name: round(state.mastery_level, 2)
            for state in concept_states
        }

        summary, created = WeeklyLearningSummary.objects.update_or_create(
            student=student,
            week_start=week_start,
            defaults={
                'total_study_minutes': total_seconds // 60,
                'modules_completed': modules_completed,
                'exercises_completed': exercises_completed,
                'concepts_mastered': concepts_mastered,
                'ai_interactions': ai_interactions,
                'sandbox_executions': sandbox_executions,
            }
        )
        if created:
            created_count += 1

    return created_count


def compute_personas():
    """
    遍历已完成引导的 StudentProfile，调用 LearningOrchestrator.compute_persona()。
    由于 StudentProfile 和 LearningOrchestrator 尚未实现，此处仅在模型存在时执行。
    """
    try:
        from student_profiles.models import StudentProfile
    except ImportError:
        return 'StudentProfile 模型未就绪，跳过 persona 计算'

    try:
        from learning_paths.orchestrator import LearningOrchestrator
    except ImportError:
        return 'LearningOrchestrator 未就绪，跳过 persona 计算'

    processed = 0
    errors = 0
    profiles = StudentProfile.objects.filter(onboarding_completed=True)

    for profile in profiles:
        try:
            orchestrator = LearningOrchestrator(profile.student)
            orchestrator.compute_persona()
            processed += 1
        except Exception as e:
            errors += 1

    return f'已处理 {processed} 个用户画像，{errors} 个失败'
