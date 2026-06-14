#!/usr/bin/env python
"""
测试 Django Admin 数据访问
模拟 Admin 访问并检查数据显示
"""
import os
import django

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.admin.sites import AdminSite
from resources.admin import ResourceAdmin
from resources.models import Resource
from articles.admin import ArticleAdmin
from articles.models import Article
from users.models import CTFUser
from django.contrib.auth.models import AnonymousUser

def create_mock_user(username='admin', is_staff=True, is_superuser=True):
    """创建模拟用户"""
    try:
        user = CTFUser.objects.get(username=username)
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.save()
        return user
    except CTFUser.DoesNotExist:
        user = CTFUser.objects.create_user(
            username=username,
            password='admin123',
            email=f'{username}@example.com',
            role='admin',
            is_staff=is_staff,
            is_superuser=is_superuser
        )
        return user

def test_admin_with_user():
    """测试使用管理员用户访问 Admin"""
    print("=" * 60)
    print("测试 Admin 数据访问")
    print("=" * 60)

    # 获取或创建管理员用户
    admin_user = create_mock_user('admin', True, True)
    print(f"✓ 管理员用户: {admin_user.username}")
    print(f"  - is_staff: {admin_user.is_staff}")
    print(f"  - is_superuser: {admin_user.is_superuser}")
    print()

    # 测试资源 Admin
    print("资源管理:")
    site = AdminSite()
    resource_admin = ResourceAdmin(Resource, site)

    factory = RequestFactory()
    request = factory.get('/admin/resources/resource/')
    request.user = admin_user

    try:
        queryset = resource_admin.get_queryset(request)
        print(f"✓ 查询结果: {queryset.count()} 条资源")

        # 检查是否有筛选器影响
        from django.contrib.admin import SimpleListFilter

        # 显示前 5 条
        for i, r in enumerate(queryset[:5], 1):
            print(f"  {i}. ID:{r.id} | {r.title} | 状态:{r.status} | 上传者:{r.uploader.username}")

        if queryset.count() == 0:
            print("  ⚠️ 警告: 没有找到资源数据")
            print(f"     数据库中实际有: {Resource.objects.count()} 条")

    except Exception as e:
        print(f"✗ 查询失败: {e}")
        import traceback
        traceback.print_exc()

    print()

    # 测试文章 Admin
    print("文章管理:")
    article_admin = ArticleAdmin(Article, site)

    request = factory.get('/admin/articles/article/')
    request.user = admin_user

    try:
        queryset = article_admin.get_queryset(request)
        print(f"✓ 查询结果: {queryset.count()} 篇文章")

        # 显示前 5 条
        for i, a in enumerate(queryset[:5], 1):
            print(f"  {i}. ID:{a.id} | {a.title} | 状态:{a.status} | 作者:{a.author.username}")

        if queryset.count() == 0:
            print("  ⚠️ 警告: 没有找到文章数据")
            print(f"     数据库中实际有: {Article.objects.count()} 篇")

    except Exception as e:
        print(f"✗ 查询失败: {e}")
        import traceback
        traceback.print_exc()

    print()

def test_admin_without_user():
    """测试无权限用户访问 Admin"""
    print("=" * 60)
    print("测试无权限用户访问")
    print("=" * 60)

    site = AdminSite()
    resource_admin = ResourceAdmin(Resource, site)

    factory = RequestFactory()
    request = factory.get('/admin/resources/resource/')
    request.user = AnonymousUser()

    try:
        queryset = resource_admin.get_queryset(request)
        print(f"✓ 查询结果: {queryset.count()} 条资源")
    except Exception as e:
        print(f"✗ 查询失败（预期）: {e}")

    print()

def test_admin_urls():
    """测试 Admin URL 配置"""
    print("=" * 60)
    print("测试 Admin URL 配置")
    print("=" * 60)

    from django.urls import reverse

    try:
        # 测试 Admin 首页
        admin_index = reverse('admin:index')
        print(f"✓ Admin 首页: {admin_index}")

        # 测试资源管理
        try:
            resource_list = reverse('admin:resources_resource_changelist')
            print(f"✓ 资源列表: {resource_list}")
        except:
            print("✗ 资源列表 URL 未找到")

        # 测试文章管理
        try:
            article_list = reverse('admin:articles_article_changelist')
            print(f"✓ 文章列表: {article_list}")
        except:
            print("✗ 文章列表 URL 未找到")

    except Exception as e:
        print(f"✗ URL 测试失败: {e}")

    print()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Django Admin 数据访问测试")
    print("=" * 60 + "\n")

    try:
        test_admin_urls()
        test_admin_with_user()
        test_admin_without_user()

        print("=" * 60)
        print("✓ 所有测试完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
