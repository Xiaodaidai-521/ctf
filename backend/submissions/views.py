from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.db.models import Q
from .models import Submission
from .serializers import SubmissionSerializer


class IsAdminUser(BasePermission):
    """仅管理员权限"""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff


class MySubmissionListView(generics.ListAPIView):
    """我的提交记录"""
    serializer_class = SubmissionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Submission.objects.filter(user=self.request.user).order_by('-created_at')


class SubmissionListView(generics.ListAPIView):
    """所有提交记录（管理员）"""
    serializer_class = SubmissionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            queryset = Submission.objects.all()
        else:
            queryset = Submission.objects.filter(user=self.request.user)

        # 搜索
        search = self.request.GET.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(user__username__icontains=search) |
                Q(user__nickname__icontains=search) |
                Q(challenge__title__icontains=search)
            )

        # 状态筛选
        is_correct = self.request.GET.get('is_correct')
        if is_correct is not None:
            queryset = queryset.filter(is_correct=is_correct.lower() == 'true')

        # 用户筛选
        user_id = self.request.GET.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # 分类筛选
        category_id = self.request.GET.get('category_id')
        if category_id:
            queryset = queryset.filter(challenge__category_id=category_id)

        return queryset.order_by('-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # 分页
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 20))
        start = (page - 1) * page_size
        end = start + page_size

        total = queryset.count()
        paginated_queryset = queryset[start:end]

        serializer = self.get_serializer(paginated_queryset, many=True)

        return Response({
            'results': serializer.data,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def submission_stats_view(request):
    """提交统计 + 个人信息汇总"""
    user = request.user

    total_submissions = Submission.objects.filter(user=user).count()
    correct_submissions = Submission.objects.filter(user=user, is_correct=True).count()
    success_rate = (correct_submissions / total_submissions * 100) if total_submissions > 0 else 0

    # 收藏和点赞
    collects = 0; likes = 0
    try:
        from articles.models import ArticleCollect, ArticleLike
        collects = ArticleCollect.objects.filter(user=user).count()
        likes = ArticleLike.objects.filter(user=user).count()
    except: pass

    # 学习进度
    total_modules = 0; completed_modules = 0; completion_rate = 0
    try:
        from learning_paths.models import UserModuleProgress
        total_modules = UserModuleProgress.objects.filter(user=user).count()
        completed_modules = UserModuleProgress.objects.filter(user=user, status__iexact='completed').count()
        completion_rate = round(completed_modules / total_modules * 100) if total_modules > 0 else 0
    except: pass

    # 最近提交
    recent_submissions = []
    try:
        for sub in Submission.objects.filter(user=user).select_related('challenge').order_by('-created_at')[:5]:
            recent_submissions.append({
                'challenge': sub.challenge.title if sub.challenge else '未知',
                'is_correct': sub.is_correct,
                'submitted_at': sub.created_at.isoformat() if sub.created_at else None,
            })
    except: pass

    return Response({
        'total_submissions': total_submissions,
        'correct_submissions': correct_submissions,
        'success_rate': round(success_rate, 2),
        'score': user.score,
        'solved_challenges': user.get_solved_challenges_count(),
        'collects': collects,
        'likes': likes,
        'total_modules': total_modules,
        'completed_modules': completed_modules,
        'completion_rate': completion_rate,
        'recent_submissions': recent_submissions,
    })


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_submission_stats_view(request):
    """管理员提交统计"""
    total_submissions = Submission.objects.count()
    correct_submissions = Submission.objects.filter(is_correct=True).count()
    wrong_submissions = total_submissions - correct_submissions
    success_rate = (correct_submissions / total_submissions * 100) if total_submissions > 0 else 0

    # 按用户统计
    user_stats = {}
    submissions = Submission.objects.select_related('user').all()
    for submission in submissions:
        user_id = submission.user.id
        username = submission.user.username
        nickname = submission.user.nickname

        if user_id not in user_stats:
            user_stats[user_id] = {
                'user_id': user_id,
                'username': username,
                'nickname': nickname,
                'total': 0,
                'correct': 0,
                'wrong': 0
            }

        user_stats[user_id]['total'] += 1
        if submission.is_correct:
            user_stats[user_id]['correct'] += 1
        else:
            user_stats[user_id]['wrong'] += 1

    # 计算用户正确率
    user_stats_list = []
    for user_id, stats in user_stats.items():
        rate = (stats['correct'] / stats['total'] * 100) if stats['total'] > 0 else 0
        user_stats_list.append({
            **stats,
            'success_rate': round(rate, 2)
        })

    # 按正确提交数排序
    user_stats_list.sort(key=lambda x: x['correct'], reverse=True)

    return Response({
        'total_submissions': total_submissions,
        'correct_submissions': correct_submissions,
        'wrong_submissions': wrong_submissions,
        'success_rate': round(success_rate, 2),
        'user_stats': user_stats_list[:20]  # 返回前20名
    })
