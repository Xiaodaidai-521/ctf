"""AI assistant views."""


import os
import asyncio
import re
import json
from datetime import datetime

from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.conf import settings
from asgiref.sync import async_to_sync, sync_to_async
import concurrent.futures
import logging
import math
from typing import Any, Dict, List, Mapping

def _run_async(coro):
    """Run a coroutine safely from sync or async contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result(timeout=300)

from .models import AgentPreset, AIConversation, AIMessage
from .service import (
    get_ai_assistant_service,
    solve_challenge_hybrid_async,
    AGENT_CONFIGS,
    LEARNING_AGENT_CONFIGS,
    MultiAgentChatService,
    get_multi_agent_service,
    _handle_preset_solution,
)
from .challenge_detector import (
    detect_challenge,
    auto_select_agents,
)
from .security import audit_event, SecurityLevel
from .response_contracts import (
    ChatResourcePayload,
    CompatibleChatResponsePayload,
    JSONValue,
    RecommendationPayload,
)
from challenges.models import Challenge
from agents.context import TeachingContextBuilder
from agents.router import AgentRouter
from agents.specialists import SpecialistAgentExecutor
from .response_adapter import build_compatible_chat_response
from .tutor_request_orchestrator import TutorRequestOrchestrator

logger = logging.getLogger(__name__)
_AGENT_ROUTER = AgentRouter()
_SPECIALIST_AGENT_EXECUTOR = SpecialistAgentExecutor()
_TUTOR_REQUEST_ORCHESTRATOR = TutorRequestOrchestrator()

_INTERNAL_REQUEST_KEYS = {'workflowId', 'workflow_id', 'agentContext', 'agent_context'}


def _json_safe_public_value(value: Any) -> JSONValue:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else 0
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return _clean_public_mapping(value)
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_public_value(item) for item in value]
    return str(value)


def _clean_public_mapping(value: Any) -> Dict[str, JSONValue]:
    if not isinstance(value, Mapping):
        return {}
    cleaned: Dict[str, JSONValue] = {}
    for key, item in value.items():
        key_text = str(key)
        if key_text in _INTERNAL_REQUEST_KEYS:
            continue
        cleaned[key_text] = _json_safe_public_value(item)
    return cleaned


def _safe_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _internal_request_context_from_request(request) -> Dict[str, Any]:
    workflow_id = request.data.get('workflowId') or request.data.get('workflow_id')
    agent_context = request.data.get('agentContext') or request.data.get('agent_context')

    internal_context: Dict[str, Any] = {}
    if workflow_id is not None:
        internal_context['workflow_id'] = str(workflow_id)
    if isinstance(agent_context, Mapping):
        internal_context['agent_context'] = _clean_public_mapping(agent_context)
    return internal_context


def _answer_from_responses(responses: Any) -> str:
    if not isinstance(responses, list):
        return ''

    candidates = []
    for response in responses:
        if not isinstance(response, Mapping):
            continue
        content = str(response.get('content') or '')
        if content.strip():
            candidates.append((str(response.get('agent_id') or ''), content))

    if not candidates:
        return ''

    for preferred_agent in ('xiaohei', 'tutor'):
        for agent_id, content in reversed(candidates):
            if agent_id == preferred_agent:
                return content
    return candidates[-1][1]


def _safe_public_resource_entry(entry: Any) -> str:
    value = str(entry or '').strip()
    if not value:
        return ''
    if re.match(r'^[A-Za-z]:[\\/]', value) or '\\' in value:
        return ''
    if value.startswith(('/var/', '/home/', '/usr/', '/opt/', '/tmp/')):
        return ''
    if value.startswith('/') or value.startswith(('http://', 'https://')):
        return value[:240]
    return ''

def _public_resources_from_preparation(resource_preparation: Any) -> List[ChatResourcePayload]:
    if not isinstance(resource_preparation, Mapping):
        return []

    raw_resources = resource_preparation.get('resourceList')
    if not isinstance(raw_resources, list):
        raw_resources = resource_preparation.get('resources')
    if not isinstance(raw_resources, list):
        return []

    resources: List[ChatResourcePayload] = []
    for item in raw_resources:
        if not isinstance(item, Mapping):
            continue
        title = str(item.get('title') or '').strip()
        entry = _safe_public_resource_entry(item.get('entry') or item.get('url') or '')
        if not title or not entry:
            continue
        resource_type = str(item.get('type') or item.get('resource_type') or 'resource')
        label = str(item.get('ai_generated_label') or '').strip()
        if not label and resource_type not in {'article', 'challenge'} and entry.startswith('/resources'):
            label = 'AI多模态生成'
        location = str(item.get('location') or '').strip()
        if not location:
            if label:
                location = f'资源中心 / {label} / {title}'
            elif resource_type == 'article':
                location = f'社区 / 文章 / {title}'
            elif resource_type == 'challenge':
                location = f'题库 / 题目 / {title}'
            else:
                location = f'资源中心 / {title}'
        resources.append({
            'id': str(item.get('id') or item.get('object_id') or item.get('resource_id') or ''),
            'title': title,
            'type': resource_type,
            'entry': entry,
            'summary': str(item.get('summary') or item.get('description') or item.get('text') or ''),
            'ai_generated_label': label,
            'location': location,
        })
    return resources


def _resource_metadata_from_preparation(resource_preparation: Any) -> Dict[str, JSONValue]:
    if not isinstance(resource_preparation, Mapping):
        return {}
    has_resource_signal = any(
        key in resource_preparation for key in ('resourceList', 'resources', 'noMatchedResource')
    )
    if not has_resource_signal:
        return {}
    resources = _public_resources_from_preparation(resource_preparation)
    if not resources and 'noMatchedResource' not in resource_preparation:
        return {}
    no_matched = bool(resource_preparation.get('noMatchedResource', not resources))
    return {
        'resources': resources,
        'resourceList': resources,
        'noMatchedResource': no_matched,
    }


def _assistant_metadata_from_preparation(
    preparation: Any,
    resource_preparation: Any = None,
    *,
    include_resources: bool = False,
) -> Dict[str, JSONValue]:
    metadata = _TUTOR_REQUEST_ORCHESTRATOR.metadata_summary(preparation)
    if include_resources:
        if resource_preparation is None and isinstance(preparation, Mapping):
            resource_preparation = _resource_preparation_from_context(preparation.get('specialists'))
        metadata.update(_resource_metadata_from_preparation(resource_preparation))
    return metadata


def _public_recommendations_from_payloads(*payloads: Any) -> List[RecommendationPayload]:
    recommendations: List[RecommendationPayload] = []
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        raw_items = payload.get('recommendations')
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    recommendations.append(text)
            elif isinstance(item, Mapping):
                cleaned = _clean_public_mapping(item)
                if cleaned:
                    recommendations.append(cleaned)
    return recommendations


def _with_compatible_chat_response(
    payload: Dict[str, Any],
    *,
    responses: List[Mapping[str, Any]],
    resource_preparation: Any = None,
    specialist_context: Any = None,
    recommendations_source: Any = None,
) -> Dict[str, Any]:
    specialist = dict(specialist_context or {}) if isinstance(specialist_context, Mapping) else {}
    if resource_preparation and not specialist.get('resources'):
        specialist['resources'] = resource_preparation
    base = dict(payload)
    recommendations = _public_recommendations_from_payloads(
        recommendations_source, specialist_context, resource_preparation,
    )
    if recommendations:
        base['recommendations'] = recommendations
    return build_compatible_chat_response(
        base,
        responses=responses,
        conversation_id=base.get('conversation_id'),
        challenge_info=base.get('challenge_info'),
        specialist_result=specialist,
    )


def _route_agent_request(message):
    try:
        return _AGENT_ROUTER.route(message)
    except Exception as exc:
        logger.warning('Agent router failed, falling back to old flow: %s', exc)
        return {
            'taskType': AgentRouter.QUESTION_ANSWER,
            'requiredAgents': [],
        }


def _resource_preparation_from_context(specialist_context):
    if not isinstance(specialist_context, dict):
        return {}
    value = specialist_context.get('resourcePreparation')
    if not isinstance(value, dict):
        value = specialist_context.get('resources')
    return value if isinstance(value, dict) else {}


def _run_specialist_agents(
    agent_route,
    request,
    message,
    challenge_info=None,
    student_level=None,
    knowledge_point=None,
    existing_rag_context=None,
):
    try:
        student_id = request.user.id if request.user.is_authenticated else None
        challenge_id = None
        if challenge_info:
            challenge_id = challenge_info.get('id')
        if not challenge_id:
            challenge_id = request.data.get('challenge_id')
        return _SPECIALIST_AGENT_EXECUTOR.execute(
            agent_route=agent_route,
            student_id=student_id,
            query=message,
            challenge_id=challenge_id,
            student_level=student_level,
            knowledge_point=knowledge_point,
            existing_rag_context=existing_rag_context,
        )
    except Exception as exc:
        logger.warning('Specialist agents failed, continuing old flow: %s', exc)
        return SpecialistAgentExecutor.DEFAULT_RESULT.copy()


def _build_teaching_context(agent_route, request, message, specialist_context=None):
    try:
        student_id = request.user.id if request.user.is_authenticated else ''
        task_type = (agent_route or {}).get('taskType') or ''
        return (
            TeachingContextBuilder()
            .with_student(student_id)
            .with_question(message)
            .with_task_type(task_type)
            .with_specialist_results(specialist_context or {})
            .build_dict()
        )
    except Exception as exc:
        logger.warning('Teaching context build failed, using empty context: %s', exc)
        return TeachingContextBuilder().build_dict()


async def _persist_stream_message(**kwargs):
    try:
        await sync_to_async(AIMessage.objects.create, thread_sensitive=True)(**kwargs)
    except Exception as exc:
        logger.warning('Unable to persist streamed AI message: %s', exc)


def _normalize_ai_content(content):
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False)
    if content is None:
        return ''
    return str(content)


def _sse_event(event_name, payload):
    data = json.dumps(payload, ensure_ascii=False)
    return f'event: {event_name}\ndata: {data}\n\n'


def _sync_from_async_stream(async_stream):
    loop = asyncio.new_event_loop()
    try:
        while True:
            try:
                yield loop.run_until_complete(async_stream.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


def _format_agent_response(resp, service, fallback_agent_id=None, fallback_agent_name=None):
    agent_id = resp.get('agent_id') or fallback_agent_id or 'unknown'
    agent_config = service.get_agent_config(agent_id)
    content = _normalize_ai_content(resp.get('content', ''))
    agent_name = resp.get('agent_name') or fallback_agent_name or agent_config.get('name', agent_id)
    return {
        'agent_id': agent_id,
        'agent_name': agent_name,
        'content': content,
        'provider': resp.get('provider', 'unknown'),
        'model': resp.get('model'),
        'icon': agent_config.get('icon', ''),
        'color': agent_config.get('color', '#00f5ff'),
        'step': resp.get('step'),
        'step_name': resp.get('step_name'),
        'handoff': resp.get('handoff'),
        'legal_evidence_count': resp.get('legal_evidence_count'),
        'challenge_knowledge_count': resp.get('challenge_knowledge_count'),
        'legal_sources': resp.get('legal_sources'),
        'image_url': resp.get('image_url'),
        'rag_mode': resp.get('rag_mode'),
        'rag_sources': resp.get('rag_sources', []),
    }


def _get_or_create_ai_conversation(request, challenge_info=None):
    conversation_id = request.data.get('conversation_id')
    challenge = None
    challenge_id = challenge_info.get('id') if challenge_info else request.data.get('challenge_id')

    if challenge_id:
        try:
            challenge = Challenge.objects.get(id=challenge_id)
        except Challenge.DoesNotExist:
            challenge = None

    if conversation_id:
        conversation = get_object_or_404(
            AIConversation,
            id=conversation_id,
            user=request.user,
        )
        if challenge and not conversation.challenge_id:
            conversation.challenge = challenge
            conversation.save(update_fields=['challenge', 'updated_at'])
        return conversation

    return AIConversation.objects.create(
        user=request.user,
        challenge=challenge,
    )


# Base conversation API

class AIConversationViewSet(viewsets.ModelViewSet):
    """AI conversation viewset."""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AIConversation.objects.filter(
            user=self.request.user
        ).select_related('challenge', 'user')

    def get_serializer_class(self):
        from rest_framework import serializers

        class ConversationSerializer(serializers.ModelSerializer):
            messages = serializers.SerializerMethodField()

            class Meta:
                model = AIConversation
                fields = ['id', 'challenge_id', 'created_at', 'updated_at', 'messages']

            def get_messages(self, obj):
                return [
                    {
                        'id': msg.id,
                        'role': msg.role,
                        'content': msg.content,
                        'agent_id': msg.agent_id,
                        'agent_name': msg.agent_name,
                        'provider': msg.provider,
                        'metadata': msg.metadata or {},
                        'created_at': msg.created_at.isoformat(),
                    }
                    for msg in obj.messages.all().order_by('created_at')
                ]

        return ConversationSerializer

    def create(self, request, *args, **kwargs):
        """Create a new conversation."""
        challenge_id = request.data.get('challenge_id')
        challenge = None

        if challenge_id:
            challenge = get_object_or_404(Challenge, id=challenge_id)

        conversation = AIConversation.objects.create(
            user=request.user,
            challenge=challenge
        )

        return Response({
            'id': conversation.id,
            'challenge_id': challenge_id,
            'created_at': conversation.created_at.isoformat(),
            'messages': []
        })

    @action(detail=True, methods=['post'])
    def chat(self, request, pk=None):
        """Single-agent chat."""
        conversation = self.get_object()
        user_message = request.data.get('message', '').strip()

        if not user_message:
            return Response(
                {'error': 'message is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        AIMessage.objects.create(
            conversation=conversation,
            role='user',
            content=user_message
        )

        # Build conversation history.
        messages = list(conversation.messages.all().order_by('created_at'))
        conversation_history = [
            {'role': msg.role, 'content': msg.content}
            for msg in messages[:-1]
        ]

        challenge_info = None
        if conversation.challenge:
            challenge_info = {
                'title': conversation.challenge.title,
                'category': conversation.challenge.category.name if conversation.challenge.category else None,
                'category_name': conversation.challenge.category.name if conversation.challenge.category else 'unknown',
                'difficulty': conversation.challenge.difficulty,
                'description': conversation.challenge.description,
                'hint': conversation.challenge.hint,
            }
        else:
            detected, method = detect_challenge(user_message, request.user.id)
            if detected:
                challenge_info = detected
                try:
                    conversation.challenge = Challenge.objects.get(id=detected['id'])
                    conversation.save(update_fields=['challenge'])
                except Challenge.DoesNotExist:
                    pass

        preparation = _TUTOR_REQUEST_ORCHESTRATOR.prepare(
            user=request.user,
            message=user_message,
            conversation=conversation,
            challenge_info=challenge_info,
            conversation_history=conversation_history,
            existing_request_data=dict(request.data),
        )
        ai_response = _TUTOR_REQUEST_ORCHESTRATOR.call_legacy_answer(
            message=user_message,
            conversation_history=conversation_history,
            challenge_info=challenge_info,
            teaching_context=preparation.get('teachingContext'),
        )

        # æ·æ¿ç¨AIé¥ç²
        assistant_message = AIMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=ai_response,
            metadata=_assistant_metadata_from_preparation(preparation, include_resources=True),
        )

        payload = {
            'role': 'assistant',
            'content': ai_response,
            'answer': ai_response,
            'conversation_id': conversation.id,
            'responses': [],
            'challenge_info': challenge_info,
            'timestamp': assistant_message.created_at.isoformat(),
        }
        return Response(_TUTOR_REQUEST_ORCHESTRATOR.adapt_response(
            preparation,
            payload,
            conversation_id=conversation.id,
            challenge_info=challenge_info,
            metadata=_assistant_metadata_from_preparation(preparation, include_resources=True),
        ))


# ==================== æ¾¶æ°­æ«¤é³æç¶ API ====================

@api_view(['GET'])
@permission_classes([])
def list_agents(request):
    """
    é¾å³°å½éµâ¬éå¤æ«¤é³æç¶é°å¶ç
    
    GET /api/ai/multi-agent/agents/
    """
    # é¾å³°å½éæ¤éåæ¢
    manager = None
    available_providers = []
    try:
        from ai_providers import get_manager
        manager = get_manager()
        available_providers = [name for name, p in manager._instances.items() if p.is_available()]
    except Exception as exc:
        logger.warning(
            'ai_assistant_list_agents_provider_probe_failed',
            extra={
                'event': 'ai_assistant_list_agents_provider_probe_failed',
                'error_type': type(exc).__name__,
            },
        )

    agents_list = []
    agent_configs = {
        **AGENT_CONFIGS,
        'tutor': LEARNING_AGENT_CONFIGS.get('tutor', {}),
    }

    for agent_id, config in agent_configs.items():
        if not config:
            continue
        agents_list.append({
            'id': agent_id,
            'name': config['name'],
            'role': config['role'],
            'icon': config['icon'],
            'color': config['color'],
            'capabilities': config['capabilities'],
            'provider': config.get('provider', 'volcano'),
        })

    return Response({
        'agents': agents_list,
        'api_available': bool(available_providers),
        'available_providers': available_providers,
    })


@api_view(['GET'])
@permission_classes([])
def list_agent_presets(request):
    """
    é¾å³°å½æ¾¶æ°­æ«¤é³æç¶éå¿ç¶æ£°å®

    GET /api/ai/multi-agent/presets/
    """
    presets = AgentPreset.objects.filter(is_active=True)
    return Response([
        {
            'id': preset.preset_id,
            'name': preset.name,
            'icon': preset.icon,
            'agents': preset.agent_ids,
            'sort_order': preset.sort_order,
        }
        for preset in presets
    ])


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def multi_agent_chat(request):
    """Multi-agent chat API."""
    message = request.data.get('message', '').strip()
    agent_ids = request.data.get('agent_ids', [])
    # Backward-compatible single agent_id support.
    if not agent_ids:
        single_agent = request.data.get('agent_id')
        if single_agent:
            agent_ids = [single_agent]
    mode = request.data.get('mode', 'collaborative')
    challenge_id = request.data.get('challenge_id')
    force_ai = request.data.get('force_ai', False)
    knowledge_scope = request.data.get('knowledge_scope', 'category')
    selected_model = request.data.get('selected_model')
    selected_provider = request.data.get('selected_provider')
    context_summary = request.data.get('context_summary', '').strip()
    student_level = str(request.data.get('student_level') or request.data.get('studentLevel') or 'beginner').strip()
    requested_knowledge_point = str(
        request.data.get('knowledge_point')
        or request.data.get('knowledgePoint')
        or request.data.get('concept_name')
        or ''
    ).strip()
    internal_request_context = _internal_request_context_from_request(request)
    
    if not message:
        return Response({'error': 'message is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Ensure agent_ids is a list.
    if isinstance(agent_ids, str):
        agent_ids = [agent_ids]

    agent_route = None

    # ========== æ£°æ¨¼æ´°çåå ==========
    challenge_info = None
    detection_method = None

    if challenge_id:
        try:
            challenge = Challenge.objects.select_related('category').get(
                id=challenge_id, is_active=True
            )
            challenge_info = {
                'id': challenge.id,
                'title': challenge.title,
                'category': challenge.category.name if challenge.category else None,
                'category_name': challenge.category.name if challenge.category else 'unknown',
                'difficulty': challenge.difficulty,
                'description': challenge.description,
                'hint': challenge.hint,
            }
            detection_method = 'explicit'
        except Challenge.DoesNotExist:
            pass
    else:
        # Auto-detect challenge context.
        user_id = request.user.id if request.user.is_authenticated else None
        challenge_info, detection_method = detect_challenge(message, user_id)

    knowledge_point = requested_knowledge_point
    if not knowledge_point and challenge_info:
        knowledge_point = challenge_info.get('title') or challenge_info.get('category_name') or ''

    preparation = _TUTOR_REQUEST_ORCHESTRATOR.prepare(
        user=request.user,
        message=message,
        challenge_info=challenge_info,
        conversation_history=request.data.get('conversation_history') or [],
        existing_request_data=dict(request.data),
    )
    agent_route = preparation['route']
    specialist_context = preparation['specialists']
    resource_preparation = _resource_preparation_from_context(specialist_context)
    teaching_context = preparation.get('teachingContext')

    # Auto-select tutoring mode.
    tutor_only = set(agent_ids) == {'tutor'}
    if tutor_only:
        from .learning_orchestrator import LearningOrchestrator
        from .security import check_input_security

        sec_check = check_input_security(message)
        if sec_check.is_blocked:
            return Response(
                {'error': 'Input contains unsafe content', 'detail': sec_check.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

        concept_name = request.data.get('concept_name')
        if not concept_name:
            if challenge_info:
                concept_name = f"ç¬¬{challenge_info.get('id')}é¢ï¼{challenge_info.get('title')}"
            else:
                concept_name = message
        student_level = student_level or 'beginner'

        conversation = _get_or_create_ai_conversation(request, challenge_info)
        AIMessage.objects.create(
            conversation=conversation,
            role='user',
            content=message,
            agent_id='tutor',
            agent_name='\u6559\u5b66\u667a\u80fd\u4f53',
            metadata={
                **_TUTOR_REQUEST_ORCHESTRATOR.metadata_summary(preparation),
                'mode': 'tutoring',
                'agent_ids': agent_ids,
                'challenge_info': challenge_info,
                'detection_method': detection_method,
                'concept_name': concept_name,
                'student_level': student_level,
                'selected_model': selected_model,
                'selected_provider': selected_provider,
            },
        )

        async def _run_tutor(current_teaching_context):
            orchestrator = LearningOrchestrator()
            return await orchestrator.tutoring_session(
                student_id=request.user.id,
                concept_name=concept_name,
                question=message,
                student_level=student_level,
                model_id=selected_model,
                teaching_context=current_teaching_context,
                context_summary=context_summary,
            )

        tutor_result = _TUTOR_REQUEST_ORCHESTRATOR.call_existing_answer_chain(
            preparation,
            lambda current_context: _run_async(_run_tutor(current_context)),
        )
        formatted_responses = []
        tutor_config = LEARNING_AGENT_CONFIGS.get('tutor', AGENT_CONFIGS.get('tutor', {}))
        tutor_steps = tutor_result.get('steps', [])
        last_resource_step_index = max((
            step_index
            for step_index, step_item in enumerate(tutor_steps)
            if _normalize_ai_content(step_item.get('content', '')).strip()
            and step_item.get('provider', 'unknown') != 'error'
        ), default=-1)
        for index, step in enumerate(tutor_steps):
            content = _normalize_ai_content(step.get('content', ''))
            provider = step.get('provider', 'unknown')
            step_no = step.get('step') or index + 1
            step_name = step.get('step_name')
            formatted_responses.append({
                'agent_id': 'tutor',
                'agent_name': tutor_config.get('name', '\u6559\u5b66\u667a\u80fd\u4f53'),
                'content': content,
                'provider': provider,
                'icon': tutor_config.get('icon', ''),
                'color': tutor_config.get('color', '#4fc3f7'),
                'step': step_no,
                'step_name': step_name,
                'image_url': step.get('image_url'),
                'rag_mode': step.get('rag_mode'),
                'rag_sources': step.get('rag_sources', []),
            })
            if content.strip() and provider != 'error':
                AIMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=content,
                    agent_id='tutor',
                    agent_name=tutor_config.get('name', '\u6559\u5b66\u667a\u80fd\u4f53'),
                    provider=provider,
                    metadata={
                        **_assistant_metadata_from_preparation(
                            preparation,
                            resource_preparation,
                            include_resources=index == last_resource_step_index,
                        ),
                        'mode': 'tutoring',
                        'challenge_info': challenge_info,
                        'detection_method': detection_method,
                        'concept_name': concept_name,
                        'student_level': student_level,
                        'step': step_no,
                        'step_name': step_name,
                        'image_url': step.get('image_url'),
                        'rag_mode': step.get('rag_mode'),
                        'rag_sources': step.get('rag_sources', []),
                        'selected_model': selected_model,
                        'selected_provider': selected_provider,
                    },
                )

        response_payload = {
            'conversation_id': conversation.id,
            'mode': 'tutoring',
            'responses': formatted_responses,
            'challenge_info': challenge_info,
            'detection_method': detection_method,
            'knowledge_scope': knowledge_scope,
            'resourcePreparation': resource_preparation,
            'metadata': _assistant_metadata_from_preparation(preparation, resource_preparation, include_resources=True),
        }
        return Response(_with_compatible_chat_response(
            response_payload,
            responses=formatted_responses,
            resource_preparation=resource_preparation,
            specialist_context=specialist_context,
            recommendations_source=tutor_result,
        ))

    if challenge_info and not tutor_only:
        # Keep the user's explicit agent selection. Challenge context only narrows
        # retrieval scope; it must not silently add Xiaohei or other specialists.
        if not agent_ids:
            agent_ids = ['xiaohei']
        mode = 'challenge_solution'
        knowledge_scope = 'current'
    elif not agent_ids:
        agent_ids = ['xiaohei']

    conversation = _get_or_create_ai_conversation(request, challenge_info)
    AIMessage.objects.create(
        conversation=conversation,
        role='user',
        content=message,
        metadata={
                **_TUTOR_REQUEST_ORCHESTRATOR.metadata_summary(preparation),
            'mode': mode,
            'agent_ids': agent_ids,
            'challenge_info': challenge_info,
            'detection_method': detection_method,
            'knowledge_scope': knowledge_scope,
        },
    )

    # Call multi-agent service.
    try:
        runtime_context = {
            'knowledge_scope': knowledge_scope,
            'model_id': selected_model,
            'agent_route': agent_route,
            'specialist_context': specialist_context,
            'teaching_context': teaching_context,
        }
        if challenge_info:
            runtime_context['challenge_info'] = challenge_info
        if internal_request_context:
            runtime_context.update(internal_request_context)

        def _run_existing_multi_agent_chain(current_teaching_context):
            current_context = dict(runtime_context)
            if current_teaching_context:
                current_context['teaching_context'] = current_teaching_context
            else:
                current_context.pop('teaching_context', None)
            return async_to_sync(solve_challenge_hybrid_async)(
                question=message,
                challenge_id=challenge_info.get('id') if challenge_info else None,
                agent_ids=agent_ids,
                mode=mode,
                force_ai=force_ai,
                context=current_context,
            )

        result = _TUTOR_REQUEST_ORCHESTRATOR.call_existing_answer_chain(
            preparation, _run_existing_multi_agent_chain,
        )
        
        # Format responses.
        responses = result.get('responses', [])

        # ç¹å¤åç¹Â¤éã¥ç¹
        try:
            from .security import SecurityAuditRecord, SecurityLevel
            user_id = request.user.id if request.user.is_authenticated else None
            ip_addr = request.META.get('REMOTE_ADDR', 'unknown') if hasattr(request, 'META') else 'unknown'
            audit_record = SecurityAuditRecord(
                timestamp=datetime.now().isoformat(),
                event_type='ai_chat',
                user_id=user_id,
                ip_address=ip_addr,
                input_preview=message[:200],
                result=SecurityLevel.SAFE,
                detail=json.dumps({
                    'challenge_id': challenge_info.get('id') if challenge_info else None,
                    'response_count': len(responses),
                    'mode': result.get('mode'),
                    'knowledge_scope': result.get('knowledge_scope'),
                    'knowledge_resolved_scope': result.get('knowledge_resolved_scope'),
                    'knowledge_cache_hit': result.get('knowledge_cache_hit'),
                    'response_cache_hit': result.get('response_cache_hit'),
                    'consistency_score': result.get('consistency_score'),
                    'security_warnings': result.get('security_warnings'),
                    'security_alert': result.get('security_alert'),
                }, ensure_ascii=False),
            )
            audit_event(audit_record)
        except Exception as audit_error:
            logger.warning('multi_agent_chat_audit_failure', extra={
                'event': 'multi_agent_chat_audit_failure',
                'error_type': type(audit_error).__name__,
            })
        formatted_responses = []
        for resp in responses:
            agent_id = resp.get('agent_id', 'unknown')
            agent_config = AGENT_CONFIGS.get(agent_id, {})
            content = _normalize_ai_content(resp.get('content', ''))
            provider = resp.get('provider', 'unknown')
            agent_name = resp.get('agent_name') or agent_config.get('name', agent_id)
            
            formatted_responses.append({
                'agent_id': agent_id,
                'agent_name': agent_name,
                'content': content,
                'provider': provider,
                'icon': agent_config.get('icon', ''),
                'color': agent_config.get('color', '#00f5ff'),
                'legal_evidence_count': resp.get('legal_evidence_count'),
                'challenge_knowledge_count': resp.get('challenge_knowledge_count'),
                'legal_sources': resp.get('legal_sources'),
                'image_url': resp.get('image_url'),
                'rag_mode': resp.get('rag_mode'),
                'rag_sources': resp.get('rag_sources', []),
            })

            if content.strip():
                AIMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=content,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    provider=provider,
                    metadata={
                        **_assistant_metadata_from_preparation(
                            preparation,
                            resource_preparation,
                            include_resources=agent_id == 'tutor',
                        ),
                        'mode': result.get('mode', mode),
                        'step': resp.get('step'),
                        'step_name': resp.get('step_name'),
                        'handoff': resp.get('handoff'),
                        'knowledge_scope': result.get('knowledge_scope'),
                        'knowledge_cache_hit': result.get('knowledge_cache_hit', False),
                        'response_cache_hit': result.get('response_cache_hit', False),
                        'legal_evidence_count': resp.get('legal_evidence_count'),
                        'challenge_knowledge_count': resp.get('challenge_knowledge_count'),
                        'legal_sources': resp.get('legal_sources'),
        'image_url': resp.get('image_url'),
        'rag_mode': resp.get('rag_mode'),
        'rag_sources': resp.get('rag_sources', []),
                    },
                )
        
        response_payload = {
            'conversation_id': conversation.id,
            'mode': result.get('mode', mode),
            'responses': formatted_responses,
            'challenge_info': challenge_info,
            'detection_method': detection_method,
            'knowledge_scope': result.get('knowledge_scope', knowledge_scope),
            'knowledge_resolved_scope': result.get('knowledge_resolved_scope'),
            'knowledge_keywords': result.get('knowledge_keywords', []),
            'knowledge_items': result.get('knowledge_items', []),
            'knowledge_cache_hit': result.get('knowledge_cache_hit', False),
            'response_cache_hit': result.get('response_cache_hit', False),
            'resourcePreparation': resource_preparation,
            'metadata': _assistant_metadata_from_preparation(preparation, resource_preparation, include_resources=True),
            # Security fields.
            'security_alert': result.get('security_alert'),
            'security_detail': result.get('security_detail'),
            'consistency_score': result.get('consistency_score'),
        }
        return Response(_with_compatible_chat_response(
            response_payload,
            responses=formatted_responses,
            resource_preparation=resource_preparation,
            specialist_context=specialist_context,
            recommendations_source=result,
        ))
        
    except Exception as e:
        logger.exception("multi_agent_chat_error", extra={
            "event": "multi_agent_chat_error",
            "error_type": type(e).__name__,
            "user_id": request.user.id if getattr(request, "user", None) and request.user.is_authenticated else None,
            "agent_ids": agent_ids,
            "mode": mode,
        })
        try:
            from .security import SecurityAuditRecord, SecurityLevel
            user_id = request.user.id if request.user.is_authenticated else None
            ip_addr = request.META.get('REMOTE_ADDR', 'unknown') if hasattr(request, 'META') else 'unknown'
            audit_record = SecurityAuditRecord(
                timestamp=datetime.now().isoformat(),
                event_type='ai_chat_error',
                user_id=user_id,
                ip_address=ip_addr,
                input_preview=message[:200],
                result=SecurityLevel.SUSPICIOUS,
                detail=json.dumps({'error': str(e)}, ensure_ascii=False),
            )
            audit_event(audit_record)
        except Exception as audit_error:
            logger.warning("multi_agent_chat_audit_failure", extra={
                "event": "multi_agent_chat_audit_failure",
                "error_type": type(audit_error).__name__,
            })
        return Response(
            {'error': f'æ¾¶å­ææ¾¶è¾«è§¦: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def multi_agent_chat_stream(request):
    """Stream multi-agent chat responses as server-sent events."""
    message = request.data.get('message', '').strip()
    agent_ids = request.data.get('agent_ids', [])
    if not agent_ids:
        single_agent = request.data.get('agent_id')
        if single_agent:
            agent_ids = [single_agent]
    mode = request.data.get('mode', 'collaborative')
    challenge_id = request.data.get('challenge_id')
    knowledge_scope = request.data.get('knowledge_scope', 'category')
    selected_model = request.data.get('selected_model')
    selected_provider = request.data.get('selected_provider')
    context_summary = request.data.get('context_summary', '').strip()
    student_level = str(request.data.get('student_level') or request.data.get('studentLevel') or 'beginner').strip()
    requested_knowledge_point = str(
        request.data.get('knowledge_point')
        or request.data.get('knowledgePoint')
        or request.data.get('concept_name')
        or ''
    ).strip()

    if not message:
        return Response({'error': 'message is required'}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(agent_ids, str):
        agent_ids = [agent_ids]

    agent_route = None

    challenge_info = None
    detection_method = None
    if challenge_id:
        try:
            challenge = Challenge.objects.select_related('category').get(
                id=challenge_id, is_active=True
            )
            challenge_info = {
                'id': challenge.id,
                'title': challenge.title,
                'category': challenge.category.name if challenge.category else None,
                'category_name': challenge.category.name if challenge.category else 'unknown',
                'difficulty': challenge.difficulty,
                'description': challenge.description,
                'hint': challenge.hint,
            }
            detection_method = 'explicit'
        except Challenge.DoesNotExist:
            pass
    else:
        user_id = request.user.id if request.user.is_authenticated else None
        challenge_info, detection_method = detect_challenge(message, user_id)

    knowledge_point = requested_knowledge_point
    if not knowledge_point and challenge_info:
        knowledge_point = challenge_info.get('title') or challenge_info.get('category_name') or ''

    preparation = _TUTOR_REQUEST_ORCHESTRATOR.prepare(
        user=request.user,
        message=message,
        challenge_info=challenge_info,
        conversation_history=request.data.get('conversation_history') or [],
        existing_request_data=dict(request.data),
    )
    agent_route = preparation['route']
    specialist_context = preparation['specialists']
    resource_preparation = _resource_preparation_from_context(specialist_context)
    teaching_context = preparation.get('teachingContext')

    tutor_only = set(agent_ids) == {'tutor'}
    if challenge_info and not tutor_only:
        if not agent_ids:
            agent_ids = ['xiaohei']
        mode = 'challenge_solution'
        knowledge_scope = 'current'
    elif not agent_ids:
        agent_ids = ['xiaohei']

    conversation = _get_or_create_ai_conversation(request, challenge_info)
    AIMessage.objects.create(
        conversation=conversation,
        role='user',
        content=message,
        agent_id='tutor' if tutor_only else None,
        agent_name='\u6559\u5b66\u667a\u80fd\u4f53' if tutor_only else None,
        metadata={
                **_TUTOR_REQUEST_ORCHESTRATOR.metadata_summary(preparation),
            'mode': 'tutoring' if tutor_only else mode,
            'agent_ids': agent_ids,
            'challenge_info': challenge_info,
            'detection_method': detection_method,
            'knowledge_scope': knowledge_scope,
            'selected_model': selected_model,
            'selected_provider': selected_provider,
            'stream': True,
        },
    )

    async def stream_response():
        service = MultiAgentChatService()
        yield _sse_event('conversation', {
            'conversation_id': conversation.id,
            'mode': 'tutoring' if tutor_only else mode,
            'challenge_info': challenge_info,
            'detection_method': detection_method,
            'knowledge_scope': knowledge_scope,
            'resourcePreparation': resource_preparation,
        })

        if tutor_only:
            from .learning_orchestrator import LearningOrchestrator
            from .security import check_input_security

            sec_check = check_input_security(message)
            if sec_check.is_blocked:
                yield _sse_event('error', {
                    'error': 'Input contains unsafe content',
                    'detail': sec_check.reason,
                })
                return

            concept_name = request.data.get('concept_name')
            if not concept_name:
                concept_name = (
                    f"ç¬¬{challenge_info.get('id')}é¢ï¼{challenge_info.get('title')}"
                    if challenge_info else message
                )
            tutor_student_level = student_level or 'beginner'
            tutor_config = LEARNING_AGENT_CONFIGS.get('tutor', AGENT_CONFIGS.get('tutor', {}))
            yield _sse_event('agent_start', {
                'agent_id': 'tutor',
                'agent_name': tutor_config.get('name', '\u6559\u5b66\u667a\u80fd\u4f53'),
            })
            orchestrator = LearningOrchestrator()
            async def _run_stream_tutor(current_teaching_context):
                return await orchestrator.tutoring_session(
                    student_id=request.user.id,
                    concept_name=concept_name,
                    question=message,
                    student_level=tutor_student_level,
                    model_id=selected_model,
                    teaching_context=current_teaching_context,
                    context_summary=context_summary,
                )

            tutor_result = await _TUTOR_REQUEST_ORCHESTRATOR.call_existing_answer_chain_async(
                preparation, _run_stream_tutor,
            )
            responses = []
            for index, step in enumerate(tutor_result.get('steps', [])):
                formatted = _format_agent_response({
                    'agent_id': 'tutor',
                    'agent_name': tutor_config.get('name', '\u6559\u5b66\u667a\u80fd\u4f53'),
                    'content': _normalize_ai_content(step.get('content', '')),
                    'provider': step.get('provider', 'unknown'),
                    'step': step.get('step') or index + 1,
                    'step_name': step.get('step_name'),
                    'image_url': step.get('image_url'),
                    'rag_mode': step.get('rag_mode'),
                    'rag_sources': step.get('rag_sources', []),
                }, service, 'tutor', tutor_config.get('name', '\u6559\u5b66\u667a\u80fd\u4f53'))
                responses.append(formatted)
                if formatted['content'].strip() and formatted['provider'] != 'error':
                    await _persist_stream_message(
                        conversation=conversation,
                        role='assistant',
                        content=formatted['content'],
                        agent_id='tutor',
                        agent_name=formatted['agent_name'],
                        provider=formatted['provider'],
                        metadata={
                            **_TUTOR_REQUEST_ORCHESTRATOR.metadata_summary(preparation),
                            'mode': 'tutoring',
                            'challenge_info': challenge_info,
                            'detection_method': detection_method,
                            'concept_name': concept_name,
                            'student_level': tutor_student_level,
                            'step': formatted.get('step'),
                            'step_name': formatted.get('step_name'),
                            'image_url': formatted.get('image_url'),
                            'rag_mode': formatted.get('rag_mode'),
                            'rag_sources': formatted.get('rag_sources', []),
                            'selected_model': selected_model,
                            'selected_provider': selected_provider,
                            'stream': True,
                        },
                    )
                yield _sse_event('agent_response', formatted)

            done_payload = _TUTOR_REQUEST_ORCHESTRATOR.adapt_response(
                preparation,
                {
                    'conversation_id': conversation.id,
                    'mode': 'tutoring',
                    'responses': responses,
                    'challenge_info': challenge_info,
                    'detection_method': detection_method,
                    'knowledge_scope': knowledge_scope,
                    'resourcePreparation': resource_preparation,
                },
                responses=responses,
                conversation_id=conversation.id,
                challenge_info=challenge_info,
            )
            yield _sse_event('done', done_payload)
            return

        service = MultiAgentChatService()
        runtime_context = {
            'knowledge_scope': knowledge_scope,
            'model_id': selected_model,
            'agent_route': agent_route,
            'specialist_context': specialist_context,
            'teaching_context': teaching_context,
        }
        if challenge_info:
            runtime_context['challenge_info'] = challenge_info

        try:
            if settings.DATABASES['default']['ENGINE'].endswith('sqlite3'):
                knowledge_package = service.build_knowledge_context(
                    message,
                    challenge_info,
                    knowledge_scope,
                    5,
                )
            else:
                knowledge_package = await sync_to_async(service.build_knowledge_context)(
                    message,
                    challenge_info,
                    knowledge_scope,
                    5,
                )
        except Exception as exc:
            logger.warning(
                'ai_assistant_knowledge_package_build_failed',
                extra={
                    'event': 'ai_assistant_knowledge_package_build_failed',
                    'error_type': type(exc).__name__,
                },
            )
            knowledge_package = {
                'context_text': '',
                'scope': knowledge_scope,
                'resolved_scope': knowledge_scope,
                'items': [],
                'keywords': [],
                'cache_hit': False,
            }
        runtime_context['knowledge_context'] = knowledge_package.get('context_text')
        runtime_context['knowledge_retrieval'] = knowledge_package

        if challenge_info:
            requested_agents = [agent_id for agent_id in agent_ids if agent_id != 'tutor']
            allowed_order = ['analyst', 'security', 'developer', 'tester', 'legal_reviewer', 'xiaohei']
            agent_ids_for_run = [agent_id for agent_id in allowed_order if agent_id in requested_agents]
            if not agent_ids_for_run:
                agent_ids_for_run = ['xiaohei']
        else:
            agent_ids_for_run = [agent_id for agent_id in agent_ids if agent_id != 'tutor'] or ['xiaohei']

        async def run_agent(agent_id):
            config = service.get_agent_config(agent_id)
            start_event = _sse_event('agent_start', {
                'agent_id': agent_id,
                'agent_name': config.get('name', agent_id),
            })
            async def _run_stream_agent(current_teaching_context):
                current_context = dict(runtime_context)
                if current_teaching_context:
                    current_context['teaching_context'] = current_teaching_context
                else:
                    current_context.pop('teaching_context', None)
                if agent_id == 'legal_reviewer':
                    return await service.run_legal_reviewer(
                        question=message,
                        challenge_info=challenge_info,
                        context=current_context,
                    )
                return await service.chat_with_agent(agent_id, message, current_context)

            raw = await _TUTOR_REQUEST_ORCHESTRATOR.call_existing_answer_chain_async(
                preparation, _run_stream_agent,
            )
            formatted = _format_agent_response(raw, service, agent_id, config.get('name', agent_id))
            if formatted['content'].strip():
                await _persist_stream_message(
                    conversation=conversation,
                    role='assistant',
                    content=formatted['content'],
                    agent_id=formatted['agent_id'],
                    agent_name=formatted['agent_name'],
                    provider=formatted['provider'],
                    metadata={
                **_TUTOR_REQUEST_ORCHESTRATOR.metadata_summary(preparation),
                        'mode': mode,
                        'knowledge_scope': knowledge_package.get('scope', knowledge_scope),
                        'knowledge_cache_hit': knowledge_package.get('cache_hit', False),
                        'legal_evidence_count': formatted.get('legal_evidence_count'),
                        'challenge_knowledge_count': formatted.get('challenge_knowledge_count'),
                        'legal_sources': formatted.get('legal_sources'),
                        'stream': True,
                    },
                )
            return [
                start_event,
                _sse_event('agent_response', formatted),
            ], formatted

        responses = []
        if mode == 'sequential':
            for agent_id in agent_ids_for_run:
                events, formatted = await run_agent(agent_id)
                for event in events:
                    yield event
                responses.append(formatted)
        else:
            tasks = [asyncio.create_task(run_agent(agent_id)) for agent_id in agent_ids_for_run]
            for task in asyncio.as_completed(tasks):
                try:
                    events, formatted = await task
                    for event in events:
                        yield event
                    responses.append(formatted)
                except Exception as exc:
                    yield _sse_event('error', {'error': str(exc)})

        done_payload = _TUTOR_REQUEST_ORCHESTRATOR.adapt_response(
            preparation,
            {
                'conversation_id': conversation.id,
                'mode': mode,
                'responses': responses,
                'challenge_info': challenge_info,
                'detection_method': detection_method,
                'knowledge_scope': knowledge_package.get('scope', knowledge_scope),
                'knowledge_resolved_scope': knowledge_package.get('resolved_scope'),
                'knowledge_keywords': knowledge_package.get('keywords', []),
                'knowledge_items': knowledge_package.get('items', []),
                'knowledge_cache_hit': knowledge_package.get('cache_hit', False),
                'response_cache_hit': False,
                'resourcePreparation': resource_preparation,
            },
            responses=responses,
            conversation_id=conversation.id,
            challenge_info=challenge_info,
        )
        yield _sse_event('done', done_payload)

    response = StreamingHttpResponse(
        _sync_from_async_stream(stream_response()),
        content_type='text/event-stream; charset=utf-8',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# Compatibility alias for callers that expect the legacy sync name.
multi_agent_chat_sync = multi_agent_chat


# ==================== éæµç²?APIéå ç¹é¸ä½¸åç¹ç¸ç´?====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def solve_challenge(request):
    """Solve a challenge with the hybrid multi-agent service."""
    challenge_id = request.data.get('challenge_id')
    message = request.data.get('message', '').strip()

    if not challenge_id:
        return Response({'error': 'challenge_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    if not message:
        return Response({'error': 'message is required'}, status=status.HTTP_400_BAD_REQUEST)

    challenge = get_object_or_404(Challenge, id=challenge_id)

    async def _async_solve():
        return await solve_challenge_hybrid_async(
            question=message,
            challenge_id=challenge_id,
            agent_ids=['analyst'],
            mode='single'
        )
    
    result = async_to_sync(_async_solve)()
    
    return Response(result)


# ==================== ç¼åãé¨?APIéå £Ëéåç´?====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_conversations(request):
    """List conversations for the current user."""
    conversations = AIConversation.objects.filter(
        user=request.user
    ).select_related('challenge').order_by('-updated_at')

    result = []
    for conv in conversations:
        result.append({
            'id': conv.id,
            'challenge_id': conv.challenge_id,
            'challenge_title': conv.challenge.title if conv.challenge else None,
            'category': conv.challenge.category.name if conv.challenge and conv.challenge.category else None,
            'created_at': conv.created_at.isoformat(),
            'updated_at': conv.updated_at.isoformat(),
            'message_count': conv.messages.count()
        })

    return Response(result)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def multi_agent_handoff(request):
    """Handle manual multi-agent handoff."""
    message = request.data.get('message', '').strip()
    to_agent_id = request.data.get('to_agent_id')
    
    if not to_agent_id:
        return Response({'error': 'to_agent_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    if not message:
        return Response({'error': 'message is required'}, status=status.HTTP_400_BAD_REQUEST)

    to_config = AGENT_CONFIGS.get(to_agent_id, {})
    
    return Response({
        'agent_id': to_agent_id,
        'agent_name': to_config.get('name', '???'),
        'content': f'???? {to_config.get("name", "???")} ??',
        'icon': to_config.get('icon', ''),
        'color': to_config.get('color', '#00f5ff'),
    })


# ==================== æå­å§ªéè¥æ ====================

def _get_challenge_keywords(title: str) -> list:
    """Extract keywords from a challenge title."""
    stop_words = {'\u7684', '\u4e86', '\u548c', '\u662f', '\u5728', '\u6709', '\u6211', '\u90fd', '\u4e00', '\u4e0d', '\u4e5f', '\u5bf9', '\u80fd', '\u800c', '\u53ef'}
    
    words = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z0-9]+', title.lower())
    
    keywords = []
    for word in words:
        if len(word) > 1 and word not in stop_words:
            keywords.append(word)
        if any(term in word for term in ['sql', '\u6ce8\u5165', 'xss', 'csrf', 'ssrf', 'rce', '\u6587\u4ef6\u4e0a\u4f20', '\u6587\u4ef6\u5305\u542b', '\u53cd\u5e8f\u5217\u5316']):
            keywords.append(word)
    
    if not keywords:
        return [title.lower()]

    return keywords


# Learning agents API

from rest_framework.views import APIView


class LearningAgentsView(APIView):
    """List learning agents."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .service import LEARNING_AGENT_CONFIGS

        agents = {}
        for agent_id, config in LEARNING_AGENT_CONFIGS.items():
            agents[agent_id] = {
                'id': agent_id,
                'name': config['name'],
                'role': config['role'],
                'icon': config['icon'],
                'color': config['color'],
                'capabilities': config['capabilities'],
                'provider': config['provider'],
                'model': config['model'],
            }
        return Response({'agents': agents})


class TutoringSessionView(APIView):
    """Run a tutoring session."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .security import check_input_security

        concept_name = request.data.get('concept_name', '').strip()
        question = request.data.get('question', '').strip()
        student_level = request.data.get('student_level', 'beginner').strip()
        selected_model = request.data.get('selected_model')
        selected_provider = request.data.get('selected_provider')
        context_summary = request.data.get('context_summary', '').strip()

        if not concept_name or not question:
            return Response(
                {'error': 'concept_name and question are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        agent_route = None

        sec_check = check_input_security(question)
        if sec_check.is_blocked:
            return Response(
                {'error': 'Input contains unsafe content', 'detail': sec_check.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

        preparation = _TUTOR_REQUEST_ORCHESTRATOR.prepare(
            user=request.user,
            message=question,
            challenge_info=None,
            conversation_history=request.data.get('conversation_history') or [],
            existing_request_data=dict(request.data),
        )
        agent_route = preparation['route']
        specialist_context = preparation['specialists']
        resource_preparation = _resource_preparation_from_context(specialist_context)
        teaching_context = preparation.get('teachingContext')

        async def _run(current_teaching_context):
            from .learning_orchestrator import LearningOrchestrator
            orchestrator = LearningOrchestrator()
            return await orchestrator.tutoring_session(
                student_id=request.user.id,
                concept_name=concept_name,
                question=question,
                student_level=student_level,
                model_id=selected_model,
                teaching_context=current_teaching_context,
                context_summary=context_summary,
            )

        conversation = _get_or_create_ai_conversation(request)
        AIMessage.objects.create(
            conversation=conversation,
            role='user',
            content=question,
            agent_id='tutor',
            agent_name='\u6559\u5b66\u667a\u80fd\u4f53',
            metadata={
                **_TUTOR_REQUEST_ORCHESTRATOR.metadata_summary(preparation),
                'mode': 'tutoring',
                'concept_name': concept_name,
                'student_level': student_level,
                'selected_model': selected_model,
                'selected_provider': selected_provider,
            },
        )

        result = _TUTOR_REQUEST_ORCHESTRATOR.call_existing_answer_chain(
            preparation,
            lambda current_context: _run_async(_run(current_context)),
        )
        tutor_steps = result.get('steps', [])
        last_resource_step_index = max((
            step_index
            for step_index, step_item in enumerate(tutor_steps)
            if _normalize_ai_content(step_item.get('content', '')).strip()
            and step_item.get('provider', 'unknown') != 'error'
        ), default=-1)
        for index, step in enumerate(tutor_steps):
            content = _normalize_ai_content(step.get('content', ''))
            provider = step.get('provider', 'unknown')
            if content.strip() and provider != 'error':
                AIMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=content,
                    agent_id='tutor',
                    agent_name='\u6559\u5b66\u667a\u80fd\u4f53',
                    provider=provider,
                    metadata={
                        **_assistant_metadata_from_preparation(
                            preparation,
                            resource_preparation,
                            include_resources=index == last_resource_step_index,
                        ),
                        'mode': 'tutoring',
                        'concept_name': concept_name,
                        'student_level': student_level,
                        'step': step.get('step') or index + 1,
                        'step_name': step.get('step_name'),
                        'image_url': step.get('image_url'),
                        'rag_mode': step.get('rag_mode'),
                        'rag_sources': step.get('rag_sources', []),
                        'selected_model': selected_model,
                        'selected_provider': selected_provider,
                    },
                )

        result['conversation_id'] = conversation.id
        result['resourcePreparation'] = resource_preparation
        return Response(_TUTOR_REQUEST_ORCHESTRATOR.adapt_response(
            preparation,
            result,
            responses=result.get('steps') or [],
            conversation_id=conversation.id,
            metadata=_assistant_metadata_from_preparation(preparation, resource_preparation, include_resources=True),
        ))


class GenerateContentView(APIView):
    """Generate learning content."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        content_type = request.data.get('type', '').strip()
        topic = request.data.get('topic', '').strip()
        difficulty = request.data.get('difficulty', 'beginner').strip()

        if not content_type or not topic:
            return Response(
                {'error': 'type and topic are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from .learning_orchestrator import LearningOrchestrator
            orchestrator = LearningOrchestrator()
            prompt = (
                f'\u8bf7\u751f\u6210\u5173\u4e8e\u300c{topic}\u300d\u7684\u5b66\u4e60\u5185\u5bb9\u3002'
                f'\u7c7b\u578b\uff1a{content_type}\uff0c\u96be\u5ea6\uff1a{difficulty}\u3002'
            )

            async def _gen():
                return await orchestrator.service.chat_with_agent('content_gen', prompt)

            result = _run_async(_gen())

            return Response({
                'status': 'ok',
                'content_type': content_type,
                'topic': topic,
                'difficulty': difficulty,
                'content': result.get('content', ''),
                'agent': result.get('agent_id', 'content_gen'),
                'provider': result.get('provider', ''),
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'message': f'Generation failed: {str(e)}',
            }, status=500)


class AssessKnowledgeView(APIView):
    """Assess knowledge for selected concepts."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        concepts = request.data.get('concepts', [])

        if not concepts:
            return Response(
                {'error': 'concepts are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(concepts, str):
            concepts = [c.strip() for c in concepts.split(',') if c.strip()]

        async def _run():
            from .learning_orchestrator import LearningOrchestrator
            orchestrator = LearningOrchestrator()
            return await orchestrator.assess_knowledge(
                student_id=request.user.id,
                concept_names=concepts,
            )

        result = _run_async(_run())
        return Response(result)
class LearningRecommendView(APIView):
    """Get next-step learning recommendations without calling AI."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .learning_orchestrator import LearningOrchestrator
        orchestrator = LearningOrchestrator()
        result = orchestrator.recommend_next_step(student_id=request.user.id)
        return Response(result)

