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
from django.shortcuts import get_object_or_404
from asgiref.sync import async_to_sync, sync_to_async
import concurrent.futures

def _run_async(coro):
    """Run a coroutine safely from sync or async contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # 宸插湪浜嬩欢寰幆涓紝鐢ㄧ嚎绋嬮殧绂绘墽琛?    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result(timeout=300)

from .models import AgentPreset, AIConversation, AIMessage
from .service import (
    get_ai_assistant_service,
    solve_challenge_hybrid_async,
    AGENT_CONFIGS,
    LEARNING_AGENT_CONFIGS,
    MultiAgentChatService,
    _handle_preset_solution,
)
from .challenge_detector import (
    detect_challenge,
    auto_select_agents,
)
from .security import audit_event, SecurityLevel
from challenges.models import Challenge


def _normalize_ai_content(content):
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False)
    if content is None:
        return ''
    return str(content)


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


# ==================== 鍩虹瀵硅瘽 API ====================

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
        """鍗曟櫤鑳戒綋瀵硅瘽"""
        conversation = self.get_object()
        user_message = request.data.get('message', '').strip()

        if not user_message:
            return Response(
                {'error': '娑堟伅涓嶈兘涓虹┖'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 淇濆瓨鐢ㄦ埛娑堟伅
        AIMessage.objects.create(
            conversation=conversation,
            role='user',
            content=user_message
        )

        # 鑾峰彇瀵硅瘽鍘嗗彶
        messages = list(conversation.messages.all().order_by('created_at'))
        conversation_history = [
            {'role': msg.role, 'content': msg.content}
            for msg in messages[:-1]
        ]

        # 鑾峰彇棰樼洰淇℃伅
        challenge_info = None
        if conversation.challenge:
            challenge_info = {
                'title': conversation.challenge.title,
                'category': conversation.challenge.category.name if conversation.challenge.category else None,
                'category_name': conversation.challenge.category.name if conversation.challenge.category else '鏈煡',
                'difficulty': conversation.challenge.difficulty,
                'description': conversation.challenge.description,
                'hint': conversation.challenge.hint,
            }
        else:
            # 鑷姩妫€娴嬮鐩?            detected, method = detect_challenge(user_message, request.user.id)
            if detected:
                challenge_info = detected
                try:
                    conversation.challenge = Challenge.objects.get(id=detected['id'])
                    conversation.save(update_fields=['challenge'])
                except Challenge.DoesNotExist:
                    pass

        # 璋冪敤AI鍔╂墜
        service = get_ai_assistant_service()
        ai_response = service.chat(
            user_message=user_message,
            conversation_history=conversation_history,
            challenge_info=challenge_info
        )

        # 淇濆瓨AI鍥炲
        AIMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=ai_response
        )

        return Response({
            'role': 'assistant',
            'content': ai_response,
            'challenge_info': challenge_info,
            'timestamp': AIMessage.objects.filter(
                conversation=conversation,
                role='assistant'
            ).order_by('-created_at').first().created_at.isoformat()
        })


# ==================== 澶氭櫤鑳戒綋 API ====================

@api_view(['GET'])
@permission_classes([])  # 鍏紑鎺ュ彛
def list_agents(request):
    """
    鑾峰彇鎵€鏈夋櫤鑳戒綋閰嶇疆
    
    GET /api/ai/multi-agent/agents/
    """
    # 鑾峰彇鍙敤鍘傚晢
    manager = None
    available_providers = []
    try:
        from ai_providers import get_manager
        manager = get_manager()
        available_providers = [name for name, p in manager._instances.items() if p.is_available()]
    except Exception:
        pass

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
    鑾峰彇澶氭櫤鑳戒綋鍗忎綔棰勮

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
    """
    澶氭櫤鑳戒綋瀵硅瘽 API锛堝鍘傚晢鐗堟湰锛?    
    POST /api/ai/multi-agent/chat/
    {
        "message": "绗?棰樻€庝箞鍋氾紵",
        "agent_ids": ["analyst", "security"],
        "mode": "collaborative",  // collaborative | sequential | competitive
        "challenge_id": 1,
        "force_ai": false
    }
    
    鍝嶅簲鏍煎紡锛?    {
        "mode": "collaborative",
        "responses": [
            {
                "agent_id": "analyst",
                "agent_name": "鍒嗘瀽甯?,
                "content": "...",
                "provider": "wenxin",  // 瀹為檯璋冪敤鐨勫巶鍟?                "icon": "馃搳",
                "color": "#00f5ff"
            },
            ...
        ],
        "challenge_info": {...}
    }
    """
    message = request.data.get('message', '').strip()
    agent_ids = request.data.get('agent_ids', [])
    # 鍏煎鍓嶇鍗曚釜 agent_id 瀛楁
    if not agent_ids:
        single_agent = request.data.get('agent_id')
        if single_agent:
            agent_ids = [single_agent]
    mode = request.data.get('mode', 'collaborative')
    challenge_id = request.data.get('challenge_id')
    force_ai = request.data.get('force_ai', False)
    knowledge_scope = request.data.get('knowledge_scope', 'category')
    
    if not message:
        return Response({'error': 'message涓嶈兘涓虹┖'}, status=status.HTTP_400_BAD_REQUEST)

    # Ensure agent_ids is a list.
    if isinstance(agent_ids, str):
        agent_ids = [agent_ids]

    # ========== 棰樼洰璇嗗埆 ==========
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
                'category_name': challenge.category.name if challenge.category else '鏈煡',
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

    # ========== 鑷姩閫夋嫨鏅鸿兘浣?==========
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
                concept_name = f"第{challenge_info.get('id')}题：{challenge_info.get('title')}"
            else:
                concept_name = message
        student_level = request.data.get('student_level', 'beginner')

        conversation = _get_or_create_ai_conversation(request, challenge_info)
        AIMessage.objects.create(
            conversation=conversation,
            role='user',
            content=message,
            agent_id='tutor',
            agent_name='教学智能体',
            metadata={
                'mode': 'tutoring',
                'agent_ids': agent_ids,
                'challenge_info': challenge_info,
                'detection_method': detection_method,
                'concept_name': concept_name,
                'student_level': student_level,
            },
        )

        async def _run_tutor():
            orchestrator = LearningOrchestrator()
            return await orchestrator.tutoring_session(
                student_id=request.user.id,
                concept_name=concept_name,
                question=message,
                student_level=student_level,
            )

        tutor_result = _run_async(_run_tutor())
        formatted_responses = []
        tutor_config = LEARNING_AGENT_CONFIGS.get('tutor', AGENT_CONFIGS.get('tutor', {}))
        for index, step in enumerate(tutor_result.get('steps', [])):
            content = _normalize_ai_content(step.get('content', ''))
            provider = step.get('provider', 'unknown')
            step_no = step.get('step') or index + 1
            step_name = step.get('step_name')
            formatted_responses.append({
                'agent_id': 'tutor',
                'agent_name': tutor_config.get('name', '教学智能体'),
                'content': content,
                'provider': provider,
                'icon': tutor_config.get('icon', ''),
                'color': tutor_config.get('color', '#4fc3f7'),
                'step': step_no,
                'step_name': step_name,
            })
            if content.strip() and provider != 'error':
                AIMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=content,
                    agent_id='tutor',
                    agent_name=tutor_config.get('name', '教学智能体'),
                    provider=provider,
                    metadata={
                        'mode': 'tutoring',
                        'challenge_info': challenge_info,
                        'detection_method': detection_method,
                        'concept_name': concept_name,
                        'student_level': student_level,
                        'step': step_no,
                        'step_name': step_name,
                    },
                )

        return Response({
            'conversation_id': conversation.id,
            'mode': 'tutoring',
            'responses': formatted_responses,
            'challenge_info': challenge_info,
            'detection_method': detection_method,
            'knowledge_scope': knowledge_scope,
        })

    if challenge_info and not tutor_only:
        # Non-tutor challenge questions use the knowledge-base specialist workflow.
        # The tutor agent keeps the teaching flow when explicitly selected.
        agent_ids = ['analyst', 'security', 'developer', 'tester', 'xiaohei']
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
            'mode': mode,
            'agent_ids': agent_ids,
            'challenge_info': challenge_info,
            'detection_method': detection_method,
            'knowledge_scope': knowledge_scope,
        },
    )

    # ========== 璋冪敤澶氬巶鍟嗘湇鍔?==========
    try:
        # 鐢?async_to_sync 鍖呰寮傛璋冪敤
        result = async_to_sync(solve_challenge_hybrid_async)(
            question=message,
            challenge_id=challenge_info.get('id') if challenge_info else None,
            agent_ids=agent_ids,
            mode=mode,
            force_ai=force_ai,
            context={
                'challenge_info': challenge_info,
                'knowledge_scope': knowledge_scope,
            } if challenge_info else {
                'knowledge_scope': knowledge_scope,
            }
        )
        
        # Format responses.
        responses = result.get('responses', [])

        # 瀹夊叏瀹¤鏃ュ織
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
        except Exception:
            pass  # 瀹¤澶辫触涓嶅奖鍝嶄富娴佺▼

        # 纭繚姣忎釜鍝嶅簲閮芥湁瀹屾暣鐨?agent 淇℃伅
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
                        'mode': result.get('mode', mode),
                        'step': resp.get('step'),
                        'step_name': resp.get('step_name'),
                        'handoff': resp.get('handoff'),
                        'knowledge_scope': result.get('knowledge_scope'),
                        'knowledge_cache_hit': result.get('knowledge_cache_hit', False),
                        'response_cache_hit': result.get('response_cache_hit', False),
                    },
                )
        
        return Response({
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
            # 瀹夊叏瀛楁
            'security_alert': result.get('security_alert'),
            'security_detail': result.get('security_detail'),
            'consistency_score': result.get('consistency_score'),
        })
        
    except Exception as e:
        import traceback
        print(f"[ERROR] multi_agent_chat: {e}")
        print(traceback.format_exc())
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
        except Exception:
            pass
        return Response(
            {'error': f'澶勭悊澶辫触: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== 鍏煎鏃т唬鐮佺殑鍚屾鍖呰 ====================

# 娉ㄦ剰锛欴jango 4.x+ 鍜?DRF 3.15+ 宸叉敮鎸?async 瑙嗗浘
# 涓婇潰鐨?async def multi_agent_chat 宸茬粡鍙互鐩存帴宸ヤ綔
# 涓嶉渶瑕侀澶栫殑鍚屾鍖呰

# 淇濈暀 sync 鐗堟湰渚涘叾浠栧湴鏂硅皟鐢紙濡傛灉鏈夛級
multi_agent_chat_sync = async_to_sync(multi_agent_chat)


# ==================== 鍏朵粬 API锛堜繚鎸佸吋瀹癸級 ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def solve_challenge(request):
    """Solve a challenge with the hybrid multi-agent service."""
    challenge_id = request.data.get('challenge_id')
    message = request.data.get('message', '').strip()

    if not challenge_id:
        return Response({'error': 'challenge_id涓嶈兘涓虹┖'}, status=status.HTTP_400_BAD_REQUEST)
    if not message:
        return Response({'error': 'message涓嶈兘涓虹┖'}, status=status.HTTP_400_BAD_REQUEST)

    challenge = get_object_or_404(Challenge, id=challenge_id)

    # 寮傛璋冪敤
    async def _async_solve():
        return await solve_challenge_hybrid_async(
            question=message,
            challenge_id=challenge_id,
            agent_ids=['analyst'],
            mode='single'
        )
    
    result = async_to_sync(_async_solve)()
    
    return Response(result)


# ==================== 缂哄け鐨?API锛堣ˉ鍏咃級 ====================

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
        return Response({'error': 'to_agent_id涓嶈兘涓虹┖'}, status=status.HTTP_400_BAD_REQUEST)
    if not message:
        return Response({'error': 'message涓嶈兘涓虹┖'}, status=status.HTTP_400_BAD_REQUEST)

    to_config = AGENT_CONFIGS.get(to_agent_id, {})
    
    return Response({
        'agent_id': to_agent_id,
        'agent_name': to_config.get('name', '智能体'),
        'content': f'已委托给 {to_config.get("name", "智能体")} 处理',
        'icon': to_config.get('icon', ''),
        'color': to_config.get('color', '#00f5ff'),
    })


# ==================== 杈呭姪鍑芥暟 ====================

def _get_challenge_keywords(title: str) -> list:
    """Extract keywords from a challenge title."""
    stop_words = {'的', '了', '和', '是', '在', '有', '我', '都', '一', '不', '也', '对', '能', '而', '可'}
    
    words = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z0-9]+', title.lower())
    
    keywords = []
    for word in words:
        if len(word) > 1 and word not in stop_words:
            keywords.append(word)
        if any(term in word for term in ['sql', '娉ㄥ叆', 'xss', 'csrf', 'ssrf', 'rce', '鏂囦欢涓婁紶', '鏂囦欢鍖呭惈', '鍙嶅簭鍒楀寲']):
            keywords.append(word)
    
    if not keywords:
        return [title.lower()]

    return keywords


# ==================== 瀛︿範鏅鸿兘浣?API ====================

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

        if not concept_name or not question:
            return Response(
                {'error': 'concept_name and question are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sec_check = check_input_security(question)
        if sec_check.is_blocked:
            return Response(
                {'error': 'Input contains unsafe content', 'detail': sec_check.reason},
                status=status.HTTP_400_BAD_REQUEST,
            )

        async def _run():
            from .learning_orchestrator import LearningOrchestrator
            orchestrator = LearningOrchestrator()
            return await orchestrator.tutoring_session(
                student_id=request.user.id,
                concept_name=concept_name,
                question=question,
                student_level=student_level,
            )

        conversation = _get_or_create_ai_conversation(request)
        AIMessage.objects.create(
            conversation=conversation,
            role='user',
            content=question,
            agent_id='tutor',
            agent_name='教学智能体',
            metadata={
                'mode': 'tutoring',
                'concept_name': concept_name,
                'student_level': student_level,
            },
        )

        result = _run_async(_run())
        for index, step in enumerate(result.get('steps', [])):
            content = _normalize_ai_content(step.get('content', ''))
            provider = step.get('provider', 'unknown')
            if content.strip() and provider != 'error':
                AIMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=content,
                    agent_id='tutor',
                    agent_name='教学智能体',
                    provider=provider,
                    metadata={
                        'mode': 'tutoring',
                        'concept_name': concept_name,
                        'student_level': student_level,
                        'step': step.get('step') or index + 1,
                        'step_name': step.get('step_name'),
                    },
                )

        result['conversation_id'] = conversation.id
        return Response(result)


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
                f'请生成关于「{topic}」的学习内容。'
                f'类型：{content_type}，难度：{difficulty}。'
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

