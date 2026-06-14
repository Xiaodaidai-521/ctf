#!/usr/bin/env python
"""
直接测试 Admin HTML 输出
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from django.test import Client, RequestFactory
from django.contrib.auth import get_user_model
from resources.models import Resource
from articles.models import Article

def test_admin_html_output():
    """测试 Admin 页面的 HTML 输出"""
    print("=" * 60)
    print("测试 Admin 页面 HTML 输出")
    print("=" * 60)

    # 创建客户端
    client = Client()

    # 获取管理员用户
    User = get_user_model()
    try:
        admin_user = User.objects.get(username='admin')
    except User.DoesNotExist:
        print("✗ 找不到 admin 用户")
        return

    # 登录
    logged_in = client.login(username='admin', password='admin123')
    if not logged_in:
        print("✗ 登录失败，请检查密码")
        return

    print("✓ 管理员登录成功")
    print()

    # 测试资源列表页
    print("测试资源列表页...")
    response = client.get('/admin/resources/resource/')

    if response.status_code == 200:
        content = response.content.decode('utf-8')

        # 检查是否包含"没有数据"文本
        if '暂无资源' in content or 'No resources' in content or '0 resources' in content:
            print("✗ 页面显示'没有数据'")
        else:
            print("✓ 页面没有显示'没有数据'")

        # 检查是否有数据行
        if '<tr class="row1">' in content or '<tr class="row2">' in content:
            print("✓ 页面包含数据行")
            # 提取前几条数据
            import re
            pattern = r'<td class="field-id">\s*(\d+)\s*</td>'
            matches = re.findall(pattern, content)
            if matches:
                print(f"  找到 {len(matches)} 条数据记录")
                print(f"  ID: {', '.join(matches[:5])}")
        else:
            print("✗ 页面不包含数据行")

        # 检查总数据量提示
        import re
        total_pattern = r'(\d+)\s*resource'
        total_match = re.search(total_pattern, content, re.IGNORECASE)
        if total_match:
            print(f"✓ 页面显示总数: {total_match.group(1)}")
        else:
            print("✗ 页面没有显示总数")
    else:
        print(f"✗ 请求失败，状态码: {response.status_code}")

    print()

    # 测试文章列表页
    print("测试文章列表页...")
    response = client.get('/admin/articles/article/')

    if response.status_code == 200:
        content = response.content.decode('utf-8')

        # 检查是否包含"没有数据"文本
        if '暂无' in content or 'No articles' in content or '0 article' in content:
            print("✗ 页面显示'没有数据'")
        else:
            print("✓ 页面没有显示'没有数据'")

        # 检查是否有数据行
        if '<tr class="row1">' in content or '<tr class="row2">' in content:
            print("✓ 页面包含数据行")
        else:
            print("✗ 页面不包含数据行")

        # 检查总数据量提示
        import re
        total_pattern = r'(\d+)\s*article'
        total_match = re.search(total_pattern, content, re.IGNORECASE)
        if total_match:
            print(f"✓ 页面显示总数: {total_match.group(1)}")
        else:
            print("✗ 页面没有显示总数")
    else:
        print(f"✗ 请求失败，状态码: {response.status_code}")

    print()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("Admin HTML 输出测试")
    print("=" * 60 + "\n")

    test_admin_html_output()
