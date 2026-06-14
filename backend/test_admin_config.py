#!/usr/bin/env python
"""
测试 Django Admin 配置
验证资源和文章管理界面是否正常工作
"""
import os
import django

# 设置 Django 环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from django.contrib.admin.sites import AdminSite
from resources.admin import ResourceAdmin
from resources.models import Resource
from articles.admin import ArticleAdmin
from articles.models import Article
from django.test import RequestFactory

def test_resource_admin():
    """测试资源管理 Admin 配置"""
    print("=" * 60)
    print("测试资源管理 Admin 配置")
    print("=" * 60)

    # 创建 Admin 实例
    site = AdminSite()
    admin = ResourceAdmin(Resource, site)

    # 检查配置
    print(f"✓ list_display: {admin.list_display}")
    print(f"✓ list_editable: {admin.list_editable}")
    print(f"✓ list_filter: {admin.list_filter}")
    print(f"✓ search_fields: {admin.search_fields}")

    # 测试查询
    try:
        factory = RequestFactory()
        request = factory.get('/admin/resources/resource/')
        qs = admin.get_queryset(request)
        print(f"✓ 查询结果: {qs.count()} 条资源")

        # 显示前 5 条
        for r in qs[:5]:
            print(f"  - ID:{r.id} | {r.title} | 状态:{r.status}")
    except Exception as e:
        print(f"✗ 查询失败: {e}")

    # 验证 list_editable 配置
    for field in admin.list_editable:
        if field not in admin.list_display:
            print(f"✗ 错误: list_editable 中的 '{field}' 不在 list_display 中")
        else:
            print(f"✓ list_editable['{field}'] 配置正确")

    print()

def test_article_admin():
    """测试文章管理 Admin 配置"""
    print("=" * 60)
    print("测试文章管理 Admin 配置")
    print("=" * 60)

    # 创建 Admin 实例
    site = AdminSite()
    admin = ArticleAdmin(Article, site)

    # 检查配置
    print(f"✓ list_display: {admin.list_display}")
    print(f"✓ list_editable: {admin.list_editable}")
    print(f"✓ list_filter: {admin.list_filter}")
    print(f"✓ search_fields: {admin.search_fields}")

    # 测试查询
    try:
        factory = RequestFactory()
        request = factory.get('/admin/articles/article/')
        qs = admin.get_queryset(request)
        print(f"✓ 查询结果: {qs.count()} 篇文章")

        # 显示前 5 条
        for a in qs[:5]:
            print(f"  - ID:{a.id} | {a.title} | 状态:{a.status}")
    except Exception as e:
        print(f"✗ 查询失败: {e}")

    # 验证 list_editable 配置
    for field in admin.list_editable:
        if field not in admin.list_display:
            print(f"✗ 错误: list_editable 中的 '{field}' 不在 list_display 中")
        else:
            print(f"✓ list_editable['{field}'] 配置正确")

    print()

def test_data_statistics():
    """测试数据统计"""
    print("=" * 60)
    print("数据统计")
    print("=" * 60)

    # 资源统计
    from django.db.models import Count
    resource_stats = Resource.objects.values('status').annotate(count=Count('id'))
    print(f"资源总数: {Resource.objects.count()} 条")
    for stat in resource_stats:
        print(f"  - {stat['status']}: {stat['count']} 条")

    print()

    # 文章统计
    article_stats = Article.objects.values('status').annotate(count=Count('id'))
    print(f"文章总数: {Article.objects.count()} 篇")
    for stat in article_stats:
        print(f"  - {stat['status']}: {stat['count']} 篇")

    print()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Django Admin 配置测试")
    print("=" * 60 + "\n")

    try:
        test_resource_admin()
        test_article_admin()
        test_data_statistics()

        print("=" * 60)
        print("✓ 所有测试完成")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
