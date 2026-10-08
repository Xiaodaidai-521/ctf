from rest_framework import generics, status, viewsets, pagination
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import FileResponse
from .models import Resource
from .serializers import (
    ResourceSerializer,
    ResourceUploadSerializer,
    ResourceReviewSerializer
)


class ResourceAdminListView(generics.ListAPIView):
    """管理员资源列表（用于审核）"""
    queryset = Resource.objects.all()
    serializer_class = ResourceSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = pagination.PageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()

        # 状态筛选
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # 搜索
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(tags__icontains=search)
            )

        # 资源类型筛选
        resource_type = self.request.query_params.get('resource_type', None)
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)

        # 分类筛选
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category=category)

        # 排序
        ordering = self.request.query_params.get('ordering', '-created_at')
        if ordering:
            queryset = queryset.order_by(ordering)

        return queryset


class ResourceListView(generics.ListAPIView):
    """资源列表"""
    queryset = Resource.objects.filter(status='approved', is_tutoring_reserved=False)
    serializer_class = ResourceSerializer
    permission_classes = [AllowAny]
    filterset_fields = ['resource_type', 'category']
    search_fields = ['title', 'description', 'tags']

    def get_queryset(self):
        queryset = super().get_queryset()
        highlight_resource_id = self._highlight_resource_id()
        highlight_resource_ids = self._highlight_resource_ids()
        
        # 搜索
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(tags__icontains=search)
            )
        
        # 资源类型筛选
        resource_type = self.request.query_params.get('resource_type', None)
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        
        # 分类筛选
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category=category)

        if highlight_resource_ids:
            highlighted = Resource.objects.filter(id__in=highlight_resource_ids, status='approved')
            queryset = (queryset | highlighted).distinct()
        
        # 排序
        ordering = self.request.query_params.get('ordering', '-created_at')
        if highlight_resource_ids:
            whens = [
                When(id=resource_id, then=Value(index))
                for index, resource_id in enumerate(highlight_resource_ids)
            ]
            queryset = queryset.annotate(
                _highlight_order=Case(
                    *whens,
                    default=Value(len(highlight_resource_ids)),
                    output_field=IntegerField(),
                )
            )
            if ordering:
                queryset = queryset.order_by('_highlight_order', ordering)
            else:
                queryset = queryset.order_by('_highlight_order')
        elif ordering:
            queryset = queryset.order_by(ordering)
        
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['highlight_resource_id'] = self._highlight_resource_id()
        context['highlight_resource_ids'] = self._highlight_resource_ids()
        return context

    def _highlight_resource_id(self):
        raw_value = self.request.query_params.get('highlight_resource')
        try:
            value = int(raw_value)
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None

    def _highlight_resource_ids(self):
        values = []
        single_value = self._highlight_resource_id()
        if single_value:
            values.append(single_value)
        raw_values = self.request.query_params.get('highlight_resources')
        if raw_values:
            for raw_item in str(raw_values).split(','):
                try:
                    value = int(raw_item.strip())
                except (TypeError, ValueError):
                    continue
                if value > 0 and value not in values:
                    values.append(value)
        return values


class ResourceDetailView(generics.RetrieveAPIView):
    """资源详情"""
    queryset = Resource.objects.filter(status='approved')
    serializer_class = ResourceSerializer
    permission_classes = [AllowAny]
    lookup_field = 'id'

    def get_queryset(self):
        queryset = Resource.objects.filter(status='approved')
        highlight_resource_id = self._highlight_resource_id()
        requested_id = self.kwargs.get(self.lookup_field)
        if highlight_resource_id and str(highlight_resource_id) == str(requested_id):
            return queryset
        return queryset.filter(is_tutoring_reserved=False)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['highlight_resource_id'] = self._highlight_resource_id()
        return context

    def _highlight_resource_id(self):
        raw_value = self.request.query_params.get('highlight_resource')
        try:
            value = int(raw_value)
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.increment_view_count()
        if request.user.is_authenticated:
            from learning_analytics.events import record_learning_event
            record_learning_event(request.user, 'resource_retrieved', {'resource_id': instance.id})
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class ResourceUploadView(generics.CreateAPIView):
    """资源上传（仅教师和管理员）"""
    queryset = Resource.objects.all()
    serializer_class = ResourceUploadSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # 检查用户权限
        if request.user.role not in ['teacher', 'admin']:
            return Response(
                {'error': '只有教师和管理员可以上传资源'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = serializer.save()
        
        return Response({
            'message': '资源上传成功，等待审核',
            'resource': ResourceSerializer(resource).data
        }, status=status.HTTP_201_CREATED)


class ResourceMyListView(generics.ListAPIView):
    """我的资源列表（教师和管理员）"""
    serializer_class = ResourceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Resource.objects.filter(uploader=self.request.user)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsAdminUser])
def resource_review_view(request):
    """资源审核（仅管理员）"""
    serializer = ResourceReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    try:
        resource = Resource.objects.get(id=serializer.validated_data['resource_id'])
    except Resource.DoesNotExist:
        return Response(
            {'error': '资源不存在'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # 更新审核状态
    resource.status = serializer.validated_data['status']
    resource.reviewer = request.user
    resource.review_comment = serializer.validated_data.get('review_comment', '')
    resource.save()
    
    return Response({
        'message': '审核完成',
        'resource': ResourceSerializer(resource).data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def resource_download_view(request, resource_id):
    """资源下载"""
    try:
        resource = Resource.objects.get(id=resource_id, status='approved')
    except Resource.DoesNotExist:
        return Response(
            {'error': '资源不存在或未通过审核'},
            status=status.HTTP_404_NOT_FOUND
        )

    raw_highlight = request.query_params.get('highlight_resource')
    try:
        highlight_resource_id = int(raw_highlight)
    except (TypeError, ValueError):
        highlight_resource_id = None
    if resource.is_tutoring_reserved and highlight_resource_id != resource.id:
        return Response(
            {'error': '资源不存在或未通过审核'},
            status=status.HTTP_404_NOT_FOUND
        )

    if not resource.file:
        return Response({'error': 'The resource file is unavailable.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        resource.file.open('rb')
    except OSError:
        return Response({'error': 'The resource file is unavailable.'}, status=status.HTTP_404_NOT_FOUND)

    resource.increment_download_count()
    from learning_analytics.events import record_learning_event
    record_learning_event(request.user, 'resource_downloaded', {'resource_id': resource.id})

    response = FileResponse(resource.file, as_attachment=True, filename=resource.file.name.rsplit('/', 1)[-1])
    response['Content-Type'] = 'application/octet-stream'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
