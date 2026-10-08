from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q, Count, F
from django.utils import timezone
from .models import Article, Category, Comment, ArticleLike, CommentLike, ArticleCollect
from .serializers import (
    ArticleListSerializer, ArticleDetailSerializer, ArticleCreateSerializer,
    ArticleUpdateSerializer, ArticleReviewSerializer, CommentSerializer,
    CommentCreateSerializer, CategorySerializer, ArticleHotSerializer
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """文章分类视图"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class ArticleViewSet(viewsets.ModelViewSet):
    """文章视图"""
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = Article.objects.select_related('author', 'category')

        # 管理员可以查看所有状态的文章
        if self.request.user.is_staff:
            # 对于detail action，需要传递status参数或者不过滤
            if self.action == 'retrieve' or self.action == 'review':
                # 不应用状态过滤
                pass
            else:
                # list action根据status参数过滤
                status_filter = self.request.query_params.get('status', 'all')
                if status_filter != 'all':
                    queryset = queryset.filter(status=status_filter)
        else:
            # 普通用户只能查看已发布的文章（除非是作者查看自己的文章）
            status_filter = self.request.query_params.get('status', 'approved')
            if status_filter == 'all':
                queryset = queryset.filter(status='approved')
            else:
                queryset = queryset.filter(status=status_filter)

        # 搜索
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(content__icontains=search) |
                Q(tags__icontains=search)
            )

        # 分类筛选
        category_id = self.request.query_params.get('category')
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        # 标签筛选
        tag = self.request.query_params.get('tag')
        if tag:
            queryset = queryset.filter(tags__icontains=tag)

        # 作者筛选
        author_id = self.request.query_params.get('author')
        if author_id:
            queryset = queryset.filter(author_id=author_id)

        # 排序
        ordering = self.request.query_params.get('ordering', '-created_at')
        if ordering == 'hot':
            # 热度排序：综合浏览、点赞、评论
            queryset = queryset.annotate(
                heat_score=F('view_count') * 1 + F('like_count') * 5 + F('comment_count') * 3
            ).order_by('-heat_score', '-created_at')
        elif ordering == 'recommend':
            # 推荐排序：推荐 + 热度
            queryset = queryset.filter(is_recommend=True).annotate(
                heat_score=F('view_count') * 1 + F('like_count') * 5 + F('comment_count') * 3
            ).order_by('-heat_score', '-created_at')
        elif ordering == 'view':
            queryset = queryset.order_by('-view_count', '-created_at')
        elif ordering == 'like':
            queryset = queryset.order_by('-like_count', '-created_at')
        else:
            queryset = queryset.order_by(ordering)

        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return ArticleListSerializer
        elif self.action == 'create':
            return ArticleCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ArticleUpdateSerializer
        return ArticleDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        """获取文章详情，增加浏览次数"""
        instance = self.get_object()
        instance.view_count += 1
        instance.save(update_fields=['view_count'])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        if serializer.instance.author != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied('Only the author or an administrator can update an article.')
        serializer.save()

    def perform_destroy(self, instance):
        """删除文章时需要检查权限"""
        if instance.author != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied('Only the author or an administrator can delete an article.')
            return Response(
                {'error': '只有作者和管理员可以删除文章'},
                status=status.HTTP_403_FORBIDDEN
            )
        instance.delete()

    @action(detail=False, methods=['get'])
    def my(self, request):
        """获取我的文章"""
        queryset = self.get_queryset().filter(author=request.user)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def hot(self, request):
        """获取热门文章（热度排行）"""
        limit = int(request.query_params.get('limit', 10))
        queryset = self.get_queryset().filter(status='approved').annotate(
            heat_score=F('view_count') * 1 + F('like_count') * 5 + F('comment_count') * 3
        ).order_by('-heat_score', '-created_at')[:limit]

        serializer = ArticleListSerializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'count': queryset.count()
        })

    @action(detail=False, methods=['get'])
    def my_favorites(self, request):
        """获取我的收藏文章"""
        queryset = Article.objects.filter(
            id__in=ArticleCollect.objects.filter(user=request.user).values('article_id')
        ).select_related('author', 'category').order_by('-created_at')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def recommend(self, request):
        """获取推荐文章"""
        limit = int(request.query_params.get('limit', 10))
        queryset = self.get_queryset().filter(status='approved')
        candidates = list(
            queryset.filter(is_recommend=True)
            .order_by('-published_at', '-view_count')[: max(limit * 5, 20)]
        )

        if len(candidates) < limit:
            seen_ids = {article.id for article in candidates}
            fallback = queryset.exclude(id__in=seen_ids).order_by('-view_count', '-published_at')[
                : max(limit * 3, 12)
            ]
            candidates.extend(list(fallback))

        if request.user.is_authenticated:
            try:
                from learning_paths.sequence_recommender import KnowledgeSequenceRecommender

                candidates = KnowledgeSequenceRecommender(request.user).rank_articles(
                    candidates,
                    limit=limit,
                )
            except Exception:
                candidates = candidates[:limit]
        else:
            candidates = candidates[:limit]

        serializer = ArticleListSerializer(candidates, many=True)
        return Response({
            'results': serializer.data,
            'count': len(candidates),
            'provider': 'knowledge_tracking_sequence_recommender' if request.user.is_authenticated else 'editorial_hot',
        })

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        """点赞/取消点赞"""
        article = self.get_object()
        like, created = ArticleLike.objects.get_or_create(
            article=article,
            user=request.user
        )

        if created:
            article.like_count += 1
            article.save(update_fields=['like_count'])
            return Response({'liked': True, 'like_count': article.like_count})
        else:
            like.delete()
            article.like_count -= 1
            article.save(update_fields=['like_count'])
            return Response({'liked': False, 'like_count': article.like_count})

    @action(detail=True, methods=['post'])
    def collect(self, request, pk=None):
        """收藏/取消收藏"""
        article = self.get_object()
        collect, created = ArticleCollect.objects.get_or_create(
            article=article,
            user=request.user
        )

        if created:
            article.collect_count += 1
            article.save(update_fields=['collect_count'])
            return Response({'collected': True, 'collect_count': article.collect_count})
        else:
            collect.delete()
            article.collect_count -= 1
            article.save(update_fields=['collect_count'])
            return Response({'collected': False, 'collect_count': article.collect_count})

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """审核文章（管理员）"""
        if not request.user.is_staff:
            return Response(
                {'error': '只有管理员可以审核文章'},
                status=status.HTTP_403_FORBIDDEN
            )

        article = self.get_object()
        serializer = ArticleReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        article.status = serializer.validated_data['status']
        if article.status == 'approved' and not article.published_at:
            article.published_at = timezone.now()
        article.save()

        return Response({
            'status': article.status,
            'message': f'文章已{article.get_status_display()}'
        })


class CommentViewSet(viewsets.ModelViewSet):
    """评论视图"""
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = Comment.objects.select_related('author', 'article', 'parent')

        # 文章筛选
        article_id = self.request.query_params.get('article')
        if article_id:
            queryset = queryset.filter(article_id=article_id, parent=None)  # 只返回一级评论

        # 排序
        ordering = self.request.query_params.get('ordering', '-created_at')
        queryset = queryset.order_by(ordering)

        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return CommentCreateSerializer
        return CommentSerializer

    def create(self, request, *args, **kwargs):
        """创建评论并增加文章评论数"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()

        # 增加文章的评论数
        article = comment.article
        article.comment_count += 1
        article.save(update_fields=['comment_count'])

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        """删除评论时需要检查权限"""
        if instance.author != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied('Only the author or an administrator can delete a comment.')
            return Response(
                {'error': '只有评论者和管理员可以删除评论'},
                status=status.HTTP_403_FORBIDDEN
            )

        # 减少文章评论数
        article = instance.article
        article.comment_count -= 1
        article.save(update_fields=['comment_count'])

        instance.delete()

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        """点赞/取消点赞评论"""
        comment = self.get_object()
        like, created = CommentLike.objects.get_or_create(
            comment=comment,
            user=request.user
        )

        if created:
            comment.like_count += 1
            comment.save(update_fields=['like_count'])
            return Response({'liked': True, 'like_count': comment.like_count})
        else:
            like.delete()
            comment.like_count -= 1
            comment.save(update_fields=['like_count'])
            return Response({'liked': False, 'like_count': comment.like_count})

    @action(detail=True, methods=['get'])
    def replies(self, request, pk=None):
        """获取评论的所有回复"""
        comment = self.get_object()
        replies = comment.replies.all()
        serializer = CommentSerializer(replies, many=True, context={'request': request})
        return Response(serializer.data)
