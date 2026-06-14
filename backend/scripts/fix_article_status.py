#!/usr/bin/env python
"""
修复文章审核状态脚本
将部分文章设置为待审核状态，用于测试审核功能
"""

import os
import sys
import django

# 添加项目路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from articles.models import Article

def fix_article_status():
    """修复文章状态，创建待审核文章"""
    print("开始修复文章状态...")
    
    # 获取所有已发布的文章
    approved_articles = Article.objects.filter(status='approved')
    total_approved = approved_articles.count()
    
    print(f"当前已发布文章数: {total_approved}")
    
    if total_approved == 0:
        print("没有已发布的文章，无需修复")
        return
    
    # 将一半的文章改为待审核状态
    pending_count = max(1, total_approved // 2)
    pending_articles = approved_articles[:pending_count]
    
    print(f"将 {pending_count} 篇文章改为待审核状态...")
    
    for i, article in enumerate(pending_articles):
        article.status = 'pending'
        article.published_at = None  # 清除发布时间
        article.save()
        print(f"✓ [{i+1}/{pending_count}] {article.title}")
    
    # 统计结果
    print("\n=== 修复后的状态 ===")
    for status in ['pending', 'approved', 'rejected']:
        count = Article.objects.filter(status=status).count()
        print(f"{status:12s}: {count} 篇")
    
    print("\n✅ 文章状态修复完成！")

if __name__ == '__main__':
    fix_article_status()
