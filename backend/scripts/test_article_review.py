#!/usr/bin/env python
"""
测试文章审核功能
验证API是否正常工作
"""

import os
import sys
import django
import requests
import json

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from articles.models import Article
from django.contrib.auth import get_user_model

User = get_user_model()

# 测试配置
BASE_URL = 'http://localhost:8000/api'
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

def login():
    """登录获取token"""
    print("=== 1. 登录管理员账户 ===")
    response = requests.post(
        f'{BASE_URL}/users/login/',
        data={
            'username': ADMIN_USERNAME,
            'password': ADMIN_PASSWORD
        }
    )
    
    if response.status_code == 200:
        token = response.json().get('token')
        print(f"✓ 登录成功，Token: {token[:20]}...")
        return token
    else:
        print(f"✗ 登录失败: {response.status_code}")
        print(f"  响应: {response.text}")
        return None

def get_articles(token, status='pending'):
    """获取文章列表"""
    print(f"\n=== 2. 获取待审核文章列表 (status={status}) ===")
    headers = {'Authorization': f'Token {token}'}
    
    response = requests.get(
        f'{BASE_URL}/articles/articles/',
        params={'status': status},
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        # 处理可能返回列表或分页对象的情况
        if isinstance(data, list):
            articles = data
        else:
            articles = data.get('results', [])
        print(f"✓ 获取成功，共 {len(articles)} 篇文章")
        for article in articles[:3]:  # 只显示前3篇
            print(f"  - ID: {article['id']}, 标题: {article['title'][:30]}...")
            # 打印完整信息用于调试
            print(f"    完整数据: {json.dumps(article, ensure_ascii=False, indent=2)[:200]}")
        return articles
    else:
        print(f"✗ 获取失败: {response.status_code}")
        print(f"  响应: {response.text}")
        return []

def review_article(token, article_id, status):
    """审核文章"""
    print(f"\n=== 3. 审核文章 ID={article_id}, 状态={status} ===")
    headers = {'Authorization': f'Token {token}'}
    
    response = requests.post(
        f'{BASE_URL}/articles/articles/{article_id}/review/',
        json={'status': status},
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ 审核成功: {data.get('message')}")
        return True
    else:
        print(f"✗ 审核失败: {response.status_code}")
        print(f"  响应: {response.text}")
        return False

def main():
    print("开始测试文章审核API...\n")
    
    # 检查管理员账户
    admin = User.objects.filter(username=ADMIN_USERNAME).first()
    if not admin:
        print(f"✗ 管理员账户 '{ADMIN_USERNAME}' 不存在")
        return
    
    print(f"管理员账户: {admin.username} (is_staff={admin.is_staff})\n")
    
    # 登录
    token = login()
    if not token:
        return
    
    # 获取待审核文章
    pending_articles = get_articles(token, 'pending')
    if not pending_articles:
        print("\n没有待审核的文章，跳过测试")
        return
    
    # 审核第一篇文章（通过）
    first_article = pending_articles[0]
    success = review_article(token, first_article['id'], 'approved')
    
    if success:
        # 再次获取待审核文章，确认文章状态已更新
        print("\n=== 4. 验证文章状态更新 ===")
        updated_articles = get_articles(token, 'pending')
        print(f"✓ 剩余待审核文章数: {len(updated_articles)}")
        
        # 检查已发布的文章
        approved_articles = get_articles(token, 'approved')
        print(f"✓ 已发布文章数: {len(approved_articles)}")
    
    print("\n✅ 测试完成！")

if __name__ == '__main__':
    main()
