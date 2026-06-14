from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate, login
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db.models import Q
from .models import CTFUser
from .serializers import (
    UserSerializer, UserRegisterSerializer, UserLoginSerializer, LeaderboardSerializer,
    AdminUserCreateSerializer, AdminUserUpdateSerializer
)


class IsAdminUser(BasePermission):
    """仅管理员权限"""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.role == 'admin')
        )


@method_decorator(csrf_exempt, name='dispatch')
class RegisterView(generics.CreateAPIView):
    """用户注册"""
    queryset = CTFUser.objects.all()
    permission_classes = [AllowAny]
    serializer_class = UserRegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # 创建token
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'user': UserSerializer(user).data,
            'token': token.key,
            'message': '注册成功'
        }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def login_view(request):
    """用户登录"""
    serializer = UserLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = authenticate(
        username=serializer.validated_data['username'],
        password=serializer.validated_data['password']
    )

    if user:
        login(request, user)
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'user': UserSerializer(user).data,
            'token': token.key,
            'message': '登录成功'
        })
    else:
        return Response({
            'error': '用户名或密码错误'
        }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def profile_view(request):
    """获取当前用户信息"""
    return Response(UserSerializer(request.user).data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def profile_update_view(request):
    """更新用户信息"""
    serializer = UserSerializer(request.user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response({
        'user': serializer.data,
        'message': '更新成功'
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def leaderboard_view(request):
    """排行榜"""
    users = CTFUser.objects.filter(score__gt=0).order_by('-score', '-created_at')

    # 分页
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 50))
    start = (page - 1) * page_size
    end = start + page_size

    paginated_users = users[start:end]

    serializer = LeaderboardSerializer(
        paginated_users,
        many=True,
        context={'rank': start + 1}
    )

    return Response({
        'rankings': serializer.data,
        'total': users.count(),
        'page': page,
        'page_size': page_size
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_user_list_view(request):
    """管理员 - 用户列表"""
    users = CTFUser.objects.all().order_by('-created_at')

    # 搜索
    search = request.GET.get('search', '')
    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(nickname__icontains=search) |
            Q(email__icontains=search)
        )

    # 角色筛选
    role = request.GET.get('role', '')
    if role:
        users = users.filter(role=role)

    # 分页
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    start = (page - 1) * page_size
    end = start + page_size

    paginated_users = users[start:end]

    serializer = UserSerializer(paginated_users, many=True)

    return Response({
        'users': serializer.data,
        'total': users.count(),
        'page': page,
        'page_size': page_size
    })


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def admin_user_delete_view(request, user_id):
    """管理员 - 删除用户"""
    try:
        user = CTFUser.objects.get(id=user_id)
        if user.id == request.user.id:
            return Response({'error': '不能删除自己'}, status=400)
        username = user.username
        user.delete()
        return Response({'message': f'用户 {username} 已删除'})
    except CTFUser.DoesNotExist:
        return Response({'error': '用户不存在'}, status=404)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_user_create_view(request):
    """管理员 - 创建用户"""
    serializer = AdminUserCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response({
        'user': UserSerializer(user).data,
        'message': '用户创建成功'
    }, status=status.HTTP_201_CREATED)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAdminUser])
def admin_user_update_view(request, user_id):
    """管理员 - 更新用户"""
    try:
        user = CTFUser.objects.get(id=user_id)
    except CTFUser.DoesNotExist:
        return Response({'error': '用户不存在'}, status=404)

    serializer = AdminUserUpdateSerializer(user, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response({
        'user': UserSerializer(user).data,
        'message': '用户更新成功'
    })
