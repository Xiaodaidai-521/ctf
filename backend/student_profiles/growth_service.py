"""Server-side aggregation and AI gate for dynamic learning profiles."""
from hashlib import sha256
import json

from django.db.models import Count, Q, Sum

from learning_analytics.models import LearningBehaviorEvent, LearningEvent
from submissions.models import Submission

from .models import DynamicGrowthProfile, StudentProfile, StudentProfileReport


MIN_COMPLETED_QUESTIONS = 3
MIN_LEARNING_SECONDS = 10 * 60
DIRECTION_KEYS = ('web', 'crypto', 'pwn', 'reverse', 'forensics', 'misc')


def _score(value):
    try:
        return round(max(0, min(float(value), 100)), 2)
    except (TypeError, ValueError):
        return 0


def _initial_score(value):
    """Normalize legacy 0–5 self-assessments and 0–100 report scores."""
    score = _score(value)
    return _score(score * 20) if 0 < score <= 5 else score


def _initial_scores(profile):
    report = (
        StudentProfileReport.objects
        .filter(profile=profile, report_type='initial')
        .order_by('-created_at')
        .first()
    )
    report_scores = (report.report_data or {}).get('ability_scores', {}) if report else {}
    if not isinstance(report_scores, dict):
        report_scores = {}
    fallback_scores = profile.initial_self_assessed_skills or profile.self_assessed_skills or {}
    if not isinstance(fallback_scores, dict):
        fallback_scores = {}
    return {
        key: _initial_score(report_scores[key] if key in report_scores else fallback_scores.get(key, 0))
        for key in DIRECTION_KEYS
    }


def _direction_key(category):
    raw = str(
        getattr(category, 'key', '') or getattr(category, 'name', '') or ''
    ).lower()
    aliases = {
        'web': ('web', '网站'),
        'crypto': ('crypto', '密码'),
        'pwn': ('pwn', '二进制'),
        'reverse': ('reverse', '逆向'),
        'forensics': ('forensics', '取证'),
        'misc': ('misc', '杂项'),
    }
    return next(
        (key for key, values in aliases.items() if any(value in raw for value in values)),
        None,
    )


def build_dynamic_growth_summary(user):
    """Return the single, traceable source for growth UI and AI input."""
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    submissions = Submission.objects.filter(user=user).select_related('challenge__category')
    behavior = LearningBehaviorEvent.objects.filter(student=user)
    total_seconds = int(
        (LearningEvent.objects.filter(user=user, page_visible=True).aggregate(
            total=Sum('duration_ms')
        )['total'] or 0) / 1000
    )
    completed = max(submissions.count(), behavior.filter(event_type='challenge_submitted').count())
    correct = max(
        submissions.filter(is_correct=True).count(),
        behavior.filter(event_type='challenge_submitted', metadata__success=True).count(),
    )
    correct_rate = round(correct / completed * 100, 2) if completed else 0
    initial = _initial_scores(profile)
    by_direction = {key: {'attempts': 0, 'correct': 0} for key in DIRECTION_KEYS}
    for item in submissions:
        key = _direction_key(item.challenge.category)
        if key:
            by_direction[key]['attempts'] += 1
            by_direction[key]['correct'] += int(bool(item.is_correct))

    eligible = completed >= MIN_COMPLETED_QUESTIONS or total_seconds >= MIN_LEARNING_SECONDS
    dynamic, deltas, evidence = {}, {}, {}
    for key, values in by_direction.items():
        attempts, successes = values['attempts'], values['correct']
        if not eligible or not attempts:
            dynamic[key] = 0
            deltas[key] = 0
            evidence[key] = {
                'status': 'insufficient_data',
                'attempts': attempts,
                'correct': successes,
            }
            continue

        rate = successes / attempts * 100
        gain = min(
            25,
            round(successes * 5 + rate * 0.08 + min(total_seconds / 3600, 1) * 5, 2),
        )
        dynamic[key] = _score(initial[key] + gain)
        deltas[key] = round(dynamic[key] - initial[key], 2)
        evidence[key] = {
            'status': 'grown',
            'attempts': attempts,
            'correct': successes,
            'correct_rate': round(rate, 2),
            'learning_seconds': total_seconds,
        }

    knowledge = {
        str(item['knowledge_point_id']): round(
            (item['correct'] or 0) / item['total'] * 100,
            2,
        )
        for item in LearningEvent.objects.filter(
            user=user,
            knowledge_point__isnull=False,
        ).values('knowledge_point_id').annotate(
            total=Count('id'),
            correct=Count('id', filter=Q(metadata__success=True)),
        )
        if item['total']
    }
    return {
        'total_learning_seconds': total_seconds,
        'completed_question_count': completed,
        'correct_question_count': correct,
        'correct_rate': correct_rate,
        'knowledge_mastery': knowledge,
        'initial_scores': initial,
        'dynamic_scores': dynamic,
        'growth_deltas': deltas,
        'growth_evidence': evidence,
        'eligible_for_ai': eligible,
    }


def _zero_payload():
    return {
        'total_learning_seconds': 0,
        'completed_question_count': 0,
        'correct_question_count': 0,
        'correct_rate': 0,
        'knowledge_mastery': {},
        'ability_level': 0,
        'risk_level': 'pending',
        'recommendation_preferences': {},
        'analysis_status': 'insufficient_data',
        'analysis': {},
    }


def refresh_dynamic_growth(user, allow_ai=True):
    """Persist a snapshot built only from server-side learning records."""
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    growth, _ = DynamicGrowthProfile.objects.get_or_create(profile=profile)
    summary = build_dynamic_growth_summary(user)
    completed = summary['completed_question_count']
    total_seconds = summary['total_learning_seconds']
    correct_rate = summary['correct_rate']
    eligible = summary['eligible_for_ai']
    payload = {
        **summary,
        'ability_level': (
            round((correct_rate * 0.7) + min(total_seconds / MIN_LEARNING_SECONDS, 1) * 30, 2)
            if eligible else 0
        ),
        'risk_level': 'pending' if not eligible else ('at_risk' if correct_rate < 50 else 'normal'),
        'recommendation_preferences': {},
    }
    signature = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if not eligible:
        payload.update({
            **_zero_payload(),
            **{
                key: payload[key]
                for key in (
                    'total_learning_seconds',
                    'completed_question_count',
                    'correct_question_count',
                    'correct_rate',
                    'knowledge_mastery',
                )
            },
        })
        growth.analysis = {}
        growth.analysis_status = 'insufficient_data'
    elif allow_ai and (
        growth.analysis_input_signature != signature
        or growth.analysis_status in ('insufficient_data', 'failed')
    ):
        growth.analysis = {
            'summary': '已达到分析门槛，等待或执行 AI 学习分析。',
            'input_summary': payload,
        }
        growth.analysis_status = 'ready'

    growth.total_learning_seconds = payload['total_learning_seconds']
    growth.completed_question_count = payload['completed_question_count']
    growth.correct_question_count = payload['correct_question_count']
    growth.correct_rate = payload['correct_rate']
    growth.knowledge_mastery = payload['knowledge_mastery']
    growth.initial_scores = payload['initial_scores']
    growth.dynamic_scores = payload['dynamic_scores']
    growth.growth_deltas = payload['growth_deltas']
    growth.growth_evidence = payload['growth_evidence']
    growth.ability_level = payload.get('ability_level', 0)
    growth.risk_level = payload.get('risk_level', 'pending')
    growth.recommendation_preferences = payload.get('recommendation_preferences', {})
    growth.analysis_input_signature = signature if eligible else ''
    growth.save()

    return {
        **payload,
        'analysis_status': growth.analysis_status,
        'analysis': growth.analysis or {},
        'eligible_for_ai': eligible,
        'minimum_requirements': {
            'completed_questions': MIN_COMPLETED_QUESTIONS,
            'learning_seconds': MIN_LEARNING_SECONDS,
        },
        'remaining': {
            'completed_questions': max(0, MIN_COMPLETED_QUESTIONS - completed),
            'learning_seconds': max(0, MIN_LEARNING_SECONDS - total_seconds),
        },
        'updated_at': growth.updated_at,
    }
