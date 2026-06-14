from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from django.db.models import Q

from .models import Announcement
from .serializers import (
    AnnouncementSerializer,
    AnnouncementListSerializer,
    AnnouncementCreateSerializer,
    AnnouncementUpdateSerializer,
)


class AnnouncementViewSet(viewsets.ModelViewSet):
    """公告视图集"""

    def get_queryset(self):
        """获取查询集"""
        queryset = Announcement.objects.select_related('author').all()

        # 非管理员或未登录用户只能看到已发布的公告
        if not self.request.user.is_authenticated or (
            not self.request.user.is_admin and not self.request.user.is_staff
        ):
            queryset = queryset.filter(status='published')

        # 状态筛选
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # 优先级筛选
        priority_filter = self.request.query_params.get('priority')
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter)

        # 搜索
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(content__icontains=search)
            )

        return queryset

    def get_serializer_class(self):
        """获取序列化器类"""
        if self.action == 'list':
            return AnnouncementListSerializer
        elif self.action == 'create':
            return AnnouncementCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AnnouncementUpdateSerializer
        return AnnouncementSerializer

    def get_permissions(self):
        """获取权限"""
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'publish', 'unpublish']:
            permission_classes = [IsAuthenticated, IsAdminUser]
        elif self.action in ['list', 'retrieve', 'latest', 'pinned']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def retrieve(self, request, *args, **kwargs):
        """获取公告详情并增加浏览次数"""
        instance = self.get_object()
        instance.increment_view()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def latest(self, request):
        """获取最新公告"""
        announcements = self.get_queryset()[:5]
        serializer = AnnouncementListSerializer(announcements, many=True)
        return Response({
            'results': serializer.data,
            'count': announcements.count()
        })

    @action(detail=False, methods=['get'])
    def pinned(self, request):
        """获取置顶公告"""
        announcements = self.get_queryset().filter(is_pinned=True)
        serializer = AnnouncementListSerializer(announcements, many=True)
        return Response({
            'results': serializer.data,
            'count': announcements.count()
        })

    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        """发布公告"""
        announcement = self.get_object()
        from django.utils import timezone
        announcement.status = 'published'
        announcement.published_at = timezone.now()
        announcement.save()
        serializer = AnnouncementSerializer(announcement)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def unpublish(self, request, pk=None):
        """取消发布"""
        announcement = self.get_object()
        announcement.status = 'draft'
        announcement.published_at = None
        announcement.save()
        serializer = AnnouncementSerializer(announcement)
        return Response(serializer.data)
