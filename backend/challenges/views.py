from rest_framework import generics, status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.db.models import Min
from django.http import HttpResponse, StreamingHttpResponse
from .models import Category, Challenge, ChallengeContainer
from .serializers import CategorySerializer, ChallengeSerializer, ChallengeListSerializer, SubmissionSerializer
from .container_manager import get_container_manager
import requests

# 使用端口池直接访问，不通过FRP
FRP_SERVER = 'http://localhost:8000'


class IsTeacherOrAdmin(IsAuthenticated):
    """教师或管理员权限"""
    def has_permission(self, request, view):
        return (
            super().has_permission(request, view)
            and (
                request.user.is_staff
                or getattr(request.user, 'role', None) in ('teacher', 'admin')
            )
        )


class CategoryListView(generics.ListAPIView):
    """分类列表"""
    queryset = Category.objects.all()
    permission_classes = [AllowAny]
    serializer_class = CategorySerializer


class ChallengeViewSet(viewsets.ModelViewSet):
    """题目视图集"""
    def get_permissions(self):
        """列表操作允许匿名访问，增删改需要教师或管理员权限"""
        if self.action == 'list':
            return [AllowAny()]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            # 增删改操作需要教师或管理员权限
            return [IsTeacherOrAdmin()]
        return [IsAuthenticated()]

    queryset = Challenge.objects.filter(is_active=True)

    def get_serializer_class(self):
        if self.action == 'list':
            return ChallengeListSerializer
        return ChallengeSerializer

    def get_queryset(self):
        """支持按分类和难度筛选，管理员可以看到所有题目"""
        # 管理员可以看到所有题目，普通用户只能看到已激活的题目
        if self.request.user.is_authenticated and self.request.user.is_staff:
            queryset = Challenge.objects.all()
        else:
            queryset = Challenge.objects.filter(is_active=True)

        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        difficulty = self.request.query_params.get('difficulty')
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        # 支持按状态筛选（管理员专用）
        is_active = self.request.query_params.get('is_active')
        if is_active is not None and self.request.user.is_authenticated and self.request.user.is_staff:
            queryset = queryset.filter(is_active=(is_active == 'true'))

        return queryset

    @action(detail=False, methods=['get'])
    def my_solved(self, request):
        """获取我已解决的题目"""
        from submissions.models import Submission

        # 获取第一次正确解决的时间
        solved_data = Submission.objects.filter(
            user=request.user,
            is_correct=True
        ).values('challenge_id').annotate(
            solved_at=Min('created_at')
        )

        solved_challenge_ids = [item['challenge_id'] for item in solved_data]
        solved_map = {item['challenge_id']: item['solved_at'] for item in solved_data}

        queryset = Challenge.objects.filter(
            id__in=solved_challenge_ids
        ).select_related('category').order_by('id')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ChallengeListSerializer(page, many=True, context={'request': request})
            # 添加solved_at字段
            data = serializer.data
            for item in data:
                item['solved_at'] = solved_map.get(item['id'])
            return self.get_paginated_response(data)

        serializer = ChallengeListSerializer(queryset, many=True, context={'request': request})
        data = serializer.data
        for item in data:
            item['solved_at'] = solved_map.get(item['id'])
        return Response(data)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """提交Flag"""
        from submissions.models import Submission
        from submissions.serializers import SubmissionCreateSerializer

        challenge = self.get_object()
        data = request.data.copy() if hasattr(request.data, 'copy') else {'flag': request.data}
        data['challenge_id'] = challenge.id
        serializer = SubmissionCreateSerializer(
            data=data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        submission = Submission.objects.create(
            user=request.user,
            challenge=challenge,
            flag=serializer.validated_data['flag'],
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        if submission.is_correct:
            self.update_review_progress(request.user, challenge)
            return Response({
                'success': True,
                'message': 'Flag正确！',
                'score': challenge.score,
                'total_score': request.user.score
            })
        else:
            return Response({
                'success': False,
                'message': 'Flag错误，请再试一次'
            }, status=status.HTTP_400_BAD_REQUEST)

    def update_review_progress(self, user, challenge):
        """Update concept mastery when a linked practice challenge is solved."""
        from django.contrib.contenttypes.models import ContentType
        from learning_paths.models import ConceptResource, UserKnowledgeState

        challenge_ct = ContentType.objects.get_for_model(Challenge)
        concept_ids = ConceptResource.objects.filter(
            content_type=challenge_ct,
            object_id=challenge.id,
            role__in=['practice', 'assessment']
        ).values_list('concept_id', flat=True).distinct()

        for concept_id in concept_ids:
            state, _ = UserKnowledgeState.objects.get_or_create(
                user=user,
                concept_id=concept_id
            )
            state.update_mastery(success=True, time_spent=0)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """启动题目容器"""
        challenge = self.get_object()

        # 检查题目是否有Docker镜像
        if not challenge.docker_image:
            return Response({
                'success': False,
                'message': '该题目没有配置Docker镜像，无法启动容器'
            }, status=status.HTTP_400_BAD_REQUEST)

        container_manager = get_container_manager()

        # 启动容器
        success, message, container = container_manager.start_container(
            request.user,
            challenge
        )

        if success and container:
            return Response({
                'success': True,
                'message': message,
                'container': {
                    'container_id': container.container_id,
                    'status': container.status,  # 使用英文状态码，不是显示文本
                    'status_display': container.get_status_display(),  # 添加显示文本
                    'access_url': container.access_url,
                    'expires_at': container.expires_at.isoformat() if container.expires_at else None,
                    'is_running': container.is_running,
                    'is_expired': container.is_expired
                }
            })
        else:
            return Response({
                'success': False,
                'message': message
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """停止题目容器"""
        challenge = self.get_object()
        container_manager = get_container_manager()

        # 获取用户的容器
        container = ChallengeContainer.objects.filter(
            user=request.user,
            challenge=challenge,
            status='running'
        ).first()

        if not container:
            return Response({
                'success': False,
                'message': '没有运行中的容器'
            }, status=status.HTTP_404_NOT_FOUND)

        # 停止容器
        if container_manager.stop_container(container):
            return Response({
                'success': True,
                'message': '容器已停止'
            })
        else:
            return Response({
                'success': False,
                'message': '停止容器失败'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def container(self, request, pk=None):
        """获取容器状态"""
        challenge = self.get_object()
        container_manager = get_container_manager()

        # 获取容器状态
        container = container_manager.get_container_status(
            request.user,
            challenge
        )

        if not container:
            return Response({
                'container_id': None,
                'status': 'not_started',
                'message': '容器未启动'
            })

        return Response({
            'container_id': container.container_id,
            'status': container.status,
            'status_display': container.get_status_display(),
            'access_url': container.access_url,
            'is_expired': container.is_expired,
            'is_running': container.is_running,
            'created_at': container.created_at.isoformat(),
            'started_at': container.started_at.isoformat() if container.started_at else None,
            'expires_at': container.expires_at.isoformat() if container.expires_at else None
        })

    def get_client_ip(self, request):
        """获取客户端IP"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def challenge_detail_view(request, pk):
    """题目详情"""
    try:
        challenge = Challenge.objects.get(id=pk, is_active=True)
        serializer = ChallengeSerializer(challenge, context={'request': request})
        return Response(serializer.data)
    except Challenge.DoesNotExist:
        return Response({'error': '题目不存在'}, status=status.HTTP_404_NOT_FOUND)


# ==================== CTF代理视图 ====================

@api_view(['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'])
@permission_classes([AllowAny])
def proxy_challenge_view(request, path):
    """
    代理/challenge/路径到对应的容器端口
    路径格式：/challenge/<user_id>-<container_uuid>/ -> http://localhost:<port>/
    """
    # 解析路径获取容器UUID
    # path格式可能是 "1-abc123/" 或 "1-abc123/static/style.css"
    parts = path.split('/')
    if not parts:
        return HttpResponse("Invalid path", status=400)

    container_id_part = parts[0]
    try:
        user_id, container_uuid = container_id_part.split('-')
        user_id = int(user_id)
    except (ValueError, IndexError):
        return HttpResponse("Invalid container ID format", status=400)

    # 查找容器记录
    try:
        from .port_pool import get_port_pool
        from .coze_injector import is_html_response, inject_coze_sdk
        from django.conf import settings

        port_pool = get_port_pool()
        pool_port = port_pool.get_port(container_uuid)

        if not pool_port:
            return HttpResponse("Container not found or expired", status=404)

        # 构建目标URL（直接转发到容器的端口）
        target_url = f"http://localhost:{pool_port}/"

        # 添加剩余路径
        if len(parts) > 1:
            target_url += '/'.join(parts[1:])

        # 转发查询参数
        if request.META.get('QUERY_STRING'):
            target_url += f"?{request.META.get('QUERY_STRING')}"

        # 准备请求头
        headers = {}
        for key, value in request.META.items():
            if key.startswith('HTTP_'):
                header_name = key[5:].replace('_', '-')
                if header_name.lower() != 'host':
                    headers[header_name] = value

        try:
            # 转发请求
            resp = requests.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=request.body,
                cookies=request.COOKIES,
                allow_redirects=False,
                timeout=30,
                stream=False  # 不使用流式，以便注入 Coze SDK
            )

            # 检查是否为 HTML 响应且启用了 Coze SDK
            content_type = resp.headers.get('content-type', '')
            is_html = is_html_response(content_type)
            coze_enabled = getattr(settings, 'COZE_SDK_ENABLED', False)

            if is_html and coze_enabled:
                # 读取内容并注入 Coze SDK
                content = resp.content
                encoding = resp.encoding or 'utf-8'

                try:
                    # 解码内容
                    text_content = content.decode(encoding)
                    # 注入 Coze SDK
                    modified_content = inject_coze_sdk(text_content)
                    # 重新编码
                    final_content = modified_content.encode(encoding)
                except UnicodeDecodeError:
                    # 如果解码失败，直接返回原始内容
                    final_content = content
            else:
                final_content = resp.content

            # 构建响应头
            excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
            response_headers = []
            for key, value in resp.headers.items():
                if key.lower() not in excluded_headers:
                    response_headers.append((key, value))

            # 返回响应
            return HttpResponse(
                final_content,
                status=resp.status_code,
                headers=dict(response_headers)
            )

        except requests.exceptions.Timeout:
            return HttpResponse("Gateway Timeout", status=504)
        except requests.exceptions.RequestException as e:
            return HttpResponse(f"Proxy Error: {str(e)}", status=502)

    except Exception as e:
        return HttpResponse(f"Internal Error: {str(e)}", status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check_view(request):
    """代理健康检查"""
    return HttpResponse("healthy\n", content_type="text/plain")
