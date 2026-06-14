#!/usr/bin/env python
"""
测试前后端文章显示功能
验证社区页面和管理后台是否能正常显示文章
"""

import requests
import json

BASE_URL = 'http://localhost:8000'

def test_api_endpoints():
    """测试所有相关的API端点"""
    print("=== 测试API端点 ===\n")

    # 1. 测试文章列表（未登录）
    print("1. 测试文章列表（未登录）")
    response = requests.get(f'{BASE_URL}/api/articles/articles/')
    data = response.json()
    print(f"   状态码: {response.status_code}")
    print(f"   数据类型: {type(data).__name__}")
    print(f"   总数量: {data.get('count', 'N/A')}")
    print(f"   文章数量: {len(data.get('results', []))}")
    if data.get('results'):
        print(f"   第一篇文章: {data['results'][0]['title']}")
    print()

    # 2. 测试文章列表（指定分页）
    print("2. 测试文章列表（分页参数）")
    response = requests.get(f'{BASE_URL}/api/articles/articles/', params={'page': 1, 'page_size': 10})
    data = response.json()
    print(f"   状态码: {response.status_code}")
    print(f"   count: {data.get('count')}")
    print(f"   results: {len(data.get('results', []))}")
    print()

    # 3. 测试热门文章
    print("3. 测试热门文章")
    response = requests.get(f'{BASE_URL}/api/articles/articles/hot/', params={'limit': 10})
    data = response.json()
    print(f"   状态码: {response.status_code}")
    print(f"   数据类型: {type(data).__name__}")
    print(f"   结果数量: {len(data.get('results', []))}")
    if data.get('results'):
        print(f"   第一篇: {data['results'][0]['title']}")
    print()

    # 4. 测试推荐文章
    print("4. 测试推荐文章")
    response = requests.get(f'{BASE_URL}/api/articles/articles/recommend/', params={'limit': 6})
    data = response.json()
    print(f"   状态码: {response.status_code}")
    print(f"   数据类型: {type(data).__name__}")
    print(f"   结果数量: {len(data.get('results', []))}")
    if data.get('results'):
        print(f"   第一篇: {data['results'][0]['title']}")
    print()

    # 5. 测试分类列表
    print("5. 测试分类列表")
    response = requests.get(f'{BASE_URL}/api/articles/categories/')
    data = response.json()
    print(f"   状态码: {response.status_code}")
    print(f"   数据类型: {type(data).__name__}")
    print(f"   数据内容: {data}")

    if isinstance(data, list):
        print(f"   分类数量: {len(data)}")
        for i, cat in enumerate(data):
            if isinstance(cat, dict):
                print(f"   - {cat.get('name', cat)}")
            else:
                print(f"   - {cat}")
    else:
        print(f"   数据: {data}")
    print()

    # 6. 测试登录和待审核文章
    print("6. 测试登录和待审核文章")
    login_response = requests.post(
        f'{BASE_URL}/api/users/login/',
        data={'username': 'admin', 'password': 'admin123'}
    )
    if login_response.status_code == 200:
        token = login_response.json()['token']
        print(f"   登录成功")

        # 获取待审核文章
        headers = {'Authorization': f'Token {token}'}
        response = requests.get(
            f'{BASE_URL}/api/articles/articles/',
            params={'status': 'pending', 'page': 1, 'page_size': 10},
            headers=headers
        )
        data = response.json()
        print(f"   待审核文章: {data.get('count')} 篇")
        for article in data.get('results', []):
            print(f"   - {article['title']}")

        # 获取已发布文章
        response = requests.get(
            f'{BASE_URL}/api/articles/articles/',
            params={'status': 'approved', 'page': 1, 'page_size': 10},
            headers=headers
        )
        data = response.json()
        print(f"   已发布文章: {data.get('count')} 篇")
    else:
        print(f"   登录失败: {login_response.status_code}")
    print()

    print("✅ API测试完成！")
    print("\n=== 前端集成检查 ===")
    print("请确认以下内容：")
    print("1. 前端开发服务器是否在运行 (http://localhost:5173)")
    print("2. 浏览器控制台是否有错误信息")
    print("3. 网络请求是否正常（检查F12 -> Network标签）")
    print("4. 数据是否正确返回并显示在页面上")

if __name__ == '__main__':
    test_api_endpoints()
