import asyncio
import logging
import hashlib
import json
import os
import re

from django.db import transaction
from django.utils import timezone

from .models import LearningPersona, LearningPreference, StudentProfileReport


logger = logging.getLogger(__name__)


ONBOARDING_QUESTIONS = [
    {'id': 1, 'title': '学习目标', 'question': '你为什么想学习网络安全或 CTF？希望通过这段学习获得什么能力，或者解决什么实际问题？'},
    {'id': 2, 'title': '技术基础', 'question': '你以前接触过哪些计算机知识或技术？例如编程语言、Linux、计算机网络、数据库等。请简单说说你实际使用它们做过什么。'},
    {'id': 3, 'title': 'Web 安全', 'question': '如果让你检查一个网站是否存在安全问题，你会从哪里开始？你了解或使用过哪些 Web 安全知识和工具？'},
    {'id': 4, 'title': '密码学', 'question': '你如何理解编码、加密和哈希之间的区别？如果遇到一段无法识别的字符串，你通常会怎样分析？'},
    {'id': 5, 'title': '二进制、逆向与取证', 'question': '你是否分析过程序文件、可执行文件、日志、流量包或磁盘文件？如果遇到这类任务，你会怎样寻找线索？'},
    {'id': 6, 'title': '问题解决方式', 'question': '当你遇到一道完全陌生、尝试多次仍然没有解决的题目时，你通常会怎么做？请按实际处理顺序描述。'},
    {'id': 7, 'title': '学习方式与节奏', 'question': '什么样的学习方式最适合你？你希望先听讲解还是先动手？每周大约能安排多少时间？希望学习进度快一些还是稳一些？'},
    {'id': 8, 'title': '辅导期待与困难', 'question': '你目前学习网络安全最大的困难是什么？希望 AI 在你答错、卡住或理解不清时怎样帮助你？一个月后你最希望看到哪方面的提升？'},
]

DIRECTION_KEYS = ('web', 'crypto', 'pwn', 'reverse', 'forensics', 'misc')


def serialize_answers(answers):
    rows = []
    for item in ONBOARDING_QUESTIONS:
        answer = str((answers or {}).get(str(item['id']), '')).strip()
        rows.append({**item, 'answer': answer})
    return rows


def _extract_json(text):
    if not text:
        return {}
    cleaned = text.strip()
    fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.S)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start, end = cleaned.find('{'), cleaned.rfind('}')
        if start >= 0 and end > start:
            cleaned = cleaned[start:end + 1]
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        logger.warning(
            'student_profiles_onboarding_json_parse_failed',
            extra={
                'event': 'student_profiles_onboarding_json_parse_failed',
                'error_type': type(exc).__name__,
            },
        )
        return {}


def _clamp_score(value, default=30):
    try:
        return int(max(0, min(100, round(float(value)))))
    except (TypeError, ValueError):
        return default


def _fallback_analysis(rows, provider='local_rule'):
    text = ' '.join(row['answer'].lower() for row in rows)
    keyword_map = {
        'web': ['http', 'sql', 'xss', 'burp', '网站', '浏览器', '请求', '注入'],
        'crypto': ['编码', '加密', '哈希', 'base64', 'rsa', 'aes', '密码'],
        'pwn': ['pwn', '溢出', 'gdb', '二进制', '栈', '堆'],
        'reverse': ['逆向', 'ida', '反编译', '汇编', '调试'],
        'forensics': ['取证', 'wireshark', '流量', '日志', '磁盘', '文件'],
        'misc': ['python', 'linux', '网络', '数据库', '脚本', '编程'],
    }
    scores = {}
    evidence = {}
    confidence = {}
    for key, words in keyword_map.items():
        hits = [word for word in words if word in text]
        scores[key] = min(75, 24 + len(hits) * 9)
        evidence[key] = f"回答中提及：{'、'.join(hits[:4])}" if hits else '回答中暂未发现可验证的相关实践证据'
        confidence[key] = 0.62 if hits else 0.42
    answer7 = rows[6]['answer']
    pace = 'intensive' if any(x in answer7 for x in ['快', '冲刺', '集中']) else ('scheduled' if any(x in answer7 for x in ['稳', '计划', '每天']) else 'self_paced')
    modality = []
    for word, value in [('视频', 'video'), ('阅读', 'reading'), ('讲解', 'explanation'), ('动手', 'hands_on'), ('实验', 'hands_on'), ('讨论', 'discussion')]:
        if word in answer7 and value not in modality:
            modality.append(value)
    weakest = sorted(scores, key=scores.get)[:2]
    strongest = sorted(scores, key=scores.get, reverse=True)[:2]
    return {
        'ability_scores': scores,
        'evidence': evidence,
        'confidence': confidence,
        'learning_goal': rows[0]['answer'][:500],
        'learning_style': '、'.join(modality) or '先进行简短讲解，再通过实践确认理解',
        'preferred_pace': pace,
        'preferred_modality': modality or ['hands_on', 'explanation'],
        'weekly_hours': 5,
        'preferred_support': rows[7]['answer'][:300],
        'strengths': strongest,
        'weaknesses': weakest,
        'recommended_path': [f'{key.upper()} 基础' for key in weakest],
        'summary': '已根据入学自然问答生成初始学习画像；当前结论将由后续测验与真实学习行为持续校正。',
        'provider': provider,
    }


def _normalize_analysis(value, rows, provider):
    fallback = _fallback_analysis(rows, provider)
    raw_scores = value.get('ability_scores') if isinstance(value.get('ability_scores'), dict) else {}
    scores = {key: _clamp_score(raw_scores.get(key), fallback['ability_scores'][key]) for key in DIRECTION_KEYS}
    evidence = value.get('evidence') if isinstance(value.get('evidence'), dict) else fallback['evidence']
    confidence = value.get('confidence') if isinstance(value.get('confidence'), dict) else fallback['confidence']
    return {
        'ability_scores': scores,
        'evidence': {key: str(evidence.get(key, fallback['evidence'][key]))[:300] for key in DIRECTION_KEYS},
        'confidence': {key: max(0.1, min(1, float(confidence.get(key, fallback['confidence'][key])))) for key in DIRECTION_KEYS},
        'learning_goal': str(value.get('learning_goal') or fallback['learning_goal'])[:500],
        'learning_style': str(value.get('learning_style') or fallback['learning_style'])[:300],
        'preferred_pace': value.get('preferred_pace') if value.get('preferred_pace') in {'self_paced', 'scheduled', 'intensive'} else fallback['preferred_pace'],
        'preferred_modality': [str(x)[:40] for x in (value.get('preferred_modality') or fallback['preferred_modality'])][:6],
        'weekly_hours': max(0, min(80, float(value.get('weekly_hours') or fallback['weekly_hours']))),
        'preferred_support': str(value.get('preferred_support') or fallback['preferred_support'])[:300],
        'strengths': [str(x)[:80] for x in (value.get('strengths') or fallback['strengths'])][:4],
        'weaknesses': [str(x)[:80] for x in (value.get('weaknesses') or fallback['weaknesses'])][:4],
        'recommended_path': [str(x)[:100] for x in (value.get('recommended_path') or fallback['recommended_path'])][:6],
        'summary': str(value.get('summary') or fallback['summary'])[:1000],
        'provider': provider,
    }


async def _analyze_with_ai(rows):
    from ai_assistant.service import MultiAgentChatService

    prompt = (
        '你是 CTF 学习画像分析师。根据学生注册后的自然问答生成初始学习画像。'
        '只能输出 JSON，不要 Markdown。能力分数是初始推断而非考试成绩，必须结合回答证据。'
        '字段：ability_scores(web,crypto,pwn,reverse,forensics,misc，均为0-100整数)、'
        'evidence(六方向文字依据)、confidence(六方向0-1)、learning_goal、learning_style、'
        'preferred_pace(self_paced/scheduled/intensive)、preferred_modality(数组)、weekly_hours、'
        'preferred_support、strengths、weaknesses、recommended_path、summary。\n问答：'
        + json.dumps(rows, ensure_ascii=False)
    )
    service = MultiAgentChatService()
    result = await asyncio.wait_for(
        service.chat_with_agent('analyst', prompt, {'agent_task_instruction': '只返回合法 JSON 对象。'}),
        timeout=max(20, int(os.getenv('PERSONA_GENERATION_TIMEOUT', '60') or '60')),
    )
    provider = result.get('provider') or 'model'
    if provider in {'fallback', 'none', 'error', 'timeout'}:
        raise RuntimeError(result.get('provider_error') or 'AI 分析不可用')
    parsed = _extract_json(result.get('content') or '')
    if not parsed:
        raise RuntimeError('AI 返回内容不是有效 JSON')
    return _normalize_analysis(parsed, rows, provider)


def analyze_answers(answers):
    rows = serialize_answers(answers)
    try:
        analysis = asyncio.run(_analyze_with_ai(rows))
    except Exception as exc:
        analysis = _fallback_analysis(rows)
        analysis['generation_error'] = str(exc)[:240]
    return rows, analysis


def _build_input_signature(rows):
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@transaction.atomic
def complete_interview(interview):
    interview = (
        interview.__class__.objects.select_for_update()
        .select_related('profile')
        .get(pk=interview.pk)
    )
    existing_report = StudentProfileReport.objects.filter(source_interview=interview).first()
    if existing_report:
        return existing_report

    missing_question_ids = [
        item['id'] for item in ONBOARDING_QUESTIONS
        if not str(interview.answers.get(str(item['id']), '')).strip()
    ]
    if missing_question_ids:
        raise ValueError(f'访谈尚未完成，缺少问题：{missing_question_ids}')

    rows, analysis = analyze_answers(interview.answers)
    analysis = dict(analysis)
    input_signature = _build_input_signature(rows)
    generation_status = 'fallback' if analysis.get('generation_error') else 'completed'
    generated_at = timezone.now()
    analysis['_meta'] = {
        'input_signature': input_signature,
        'generation_status': generation_status,
        'provider': analysis.get('provider', ''),
        'generated_at': generated_at.isoformat(),
    }
    profile = interview.profile
    preference, _ = LearningPreference.objects.get_or_create(profile=profile)

    profile.learning_goals = analysis['learning_goal']
    profile.self_assessed_skills = {
        key: round(score / 20, 2) for key, score in analysis['ability_scores'].items()
    }
    profile.onboarding_completed = True
    update_fields = ['learning_goals', 'self_assessed_skills', 'onboarding_completed', 'updated_at']
    if not profile.initial_self_assessed_skills:
        profile.initial_self_assessed_skills = dict(profile.self_assessed_skills or {})
        update_fields.append('initial_self_assessed_skills')
    if not profile.initial_profile_captured_at:
        profile.initial_profile_captured_at = generated_at
        update_fields.append('initial_profile_captured_at')
    profile.save(update_fields=update_fields)

    preference.preferred_pace = analysis['preferred_pace']
    preference.preferred_modality = analysis['preferred_modality']
    preference.daily_study_hours = round(analysis['weekly_hours'] / 7, 2)
    preference.save(update_fields=['preferred_pace', 'preferred_modality', 'daily_study_hours'])

    previous_version = StudentProfileReport.objects.filter(profile=profile, report_type='initial').order_by('-version').values_list('version', flat=True).first() or 0
    report = StudentProfileReport.objects.create(
        profile=profile,
        source_interview=interview,
        report_type='initial',
        version=previous_version + 1,
        raw_interview=rows,
        report_data=analysis,
        summary=analysis['summary'],
        generation_provider=analysis.get('provider', ''),
        generation_status=generation_status,
        input_signature=input_signature,
    )

    interview.ai_analysis = analysis
    interview.generation_provider = analysis.get('provider', '')
    interview.status = 'completed'
    interview.current_question = len(ONBOARDING_QUESTIONS) + 1
    interview.completed_at = timezone.now()
    interview.save()

    persona, _ = LearningPersona.objects.get_or_create(profile=profile)
    persona.source_report = report
    persona.persona_label = 'initial_interview'
    persona.confidence_score = round(sum(analysis['confidence'].values()) / len(DIRECTION_KEYS), 2)
    persona.persona_traits = {
        'summary': analysis['summary'],
        'strengths': analysis['strengths'],
        'weaknesses': analysis['weaknesses'],
        'learning_style': analysis['learning_style'],
        'next_actions': analysis['recommended_path'],
        'score_basis': '注册后 AI 自然问答初始评估',
        'ability_scores': analysis['ability_scores'],
        'evidence': analysis['evidence'],
        '_meta': {
            'provider': analysis.get('provider', ''),
            'report_id': report.id,
            'input_signature': input_signature,
            'generation_status': generation_status,
            'generated_at': generated_at.isoformat(),
        },
    }
    persona.last_computed = generated_at
    persona.save()
    return report
