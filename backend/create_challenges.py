#!/usr/bin/env python
"""
创建容器题目并关联到学习路径
"""

import os
import sys
import django

# 设置Django环境
sys.path.append('/workspace/projects/ctf-platform/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from learning_paths.models import LearningPath, PathModule, ModuleLab
from challenges.models import Challenge, Category

# 容器题目数据
CONTAINER_CHALLENGES = [
    {
        'title': 'CORS基本反射攻击',
        'description': '这个网站有一个不安全的CORS配置，它信任所有源。构造一些JavaScript，使用CORS来检索管理员的API密钥。',
        'category': 'Web',
        'difficulty': 'easy',
        'score': 100,
        'flag': 'flag{cors_basic_reflection_success}',
        'hint': '查看响应头中的Access-Control-Allow-Origin，尝试构造恶意的JavaScript代码。',
        'docker_image': 'ctf-platform/cors-basic:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'path_slug': 'cors',
        'modules': ['cors', 'CORS漏洞实践']
    },
    {
        'title': 'SSRF攻击本地服务器',
        'description': '这个实验室有一个库存检查功能，可以从内部系统获取数据。修改库存检查URL以访问http://localhost/admin的管理界面并删除用户carlos。',
        'category': 'Web',
        'difficulty': 'medium',
        'score': 200,
        'flag': 'flag{ssrf_localhost_attack_success}',
        'hint': '查看stockApi参数，尝试修改它指向本地地址。',
        'docker_image': 'ctf-platform/ssrf-localhost:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'path_slug': 'ssrf-local',
        'modules': ['ssrf', '针对服务器的SSRF攻击']
    },
    {
        'title': 'SSRF攻击后端系统',
        'description': '使用库存检查功能扫描内部192.168.0.X范围，在端口8080上查找管理界面，然后使用它删除用户carlos。',
        'category': 'Web',
        'difficulty': 'hard',
        'score': 300,
        'flag': 'flag{ssrf_backend_scan_success}',
        'hint': '使用Burp Intruder扫描IP范围，找到可访问的管理界面。',
        'docker_image': 'ctf-platform/ssrf-backend:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'path_slug': 'ssrf-backend',
        'modules': ['ssrf', '针对后端系统的SSRF攻击']
    },
    {
        'title': 'WebSocket消息注入',
        'description': '这个应用程序使用WebSocket进行实时聊天。利用WebSocket消息中的注入漏洞来获取敏感信息。',
        'category': 'Web',
        'difficulty': 'medium',
        'score': 200,
        'flag': 'flag{websocket_injection_success}',
        'hint': '使用Burp Suite拦截WebSocket消息，尝试修改消息内容。',
        'docker_image': 'ctf-platform/websocket-inject:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'path_slug': 'websocket',
        'modules': ['websocket', '操作WebSocket流量']
    },
    {
        'title': 'Web缓存欺骗攻击',
        'description': '识别缓存和源服务器解析URL路径的差异，构造一个恶意URL，欺骗缓存存储动态响应以获取受害者的数据。',
        'category': 'Web',
        'difficulty': 'expert',
        'score': 400,
        'flag': 'flag{cache_deception_success}',
        'hint': '查找URL路径解析的差异，尝试使用不同的路径格式。',
        'docker_image': 'ctf-platform/cache-deception:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'path_slug': 'cache',
        'modules': ['web-cache', '构建Web缓存欺骗攻击']
    },
    {
        'title': 'SQL注入入门',
        'description': '这个应用程序存在SQL注入漏洞。通过注入SQL语句来检索所有产品，包括未发布的产品。未发布产品的flag就是答案。',
        'category': 'Web',
        'difficulty': 'easy',
        'score': 100,
        'flag': 'flag{sql_injection_basic_success}',
        'hint': '尝试使用单引号和注释符来绕过WHERE条件。',
        'docker_image': 'ctf-platform/sql-inject-basic:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'path_slug': 'sql-inject',
        'modules': ['sql-injection', '检索隐藏数据']
    },
    {
        'title': 'SQL注入UNION查询',
        'description': '使用UNION查询攻击来检索用户表中的用户名和密码。管理员账户的密码是flag。',
        'category': 'Web',
        'difficulty': 'medium',
        'score': 200,
        'flag': 'flag{sql_union_admin_password}',
        'hint': '使用UNION SELECT合并查询，先确定列数，再检索数据。',
        'docker_image': 'ctf-platform/sql-union:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'path_slug': 'sql-union',
        'modules': ['sql-injection', '检索隐藏数据']
    },
    {
        'title': 'SQL注入绕过登录',
        'description': '绕过应用程序的登录验证，以管理员身份登录。flag在管理员账户信息中。',
        'category': 'Web',
        'difficulty': 'medium',
        'score': 150,
        'flag': 'flag{sql_bypass_login_success}',
        'hint': '尝试在用户名字段中使用OR条件，如admin OR 1=1--',
        'docker_image': 'ctf-platform/sql-bypass:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'path_slug': 'sql-bypass',
        'modules': ['sql-injection', '检索隐藏数据']
    },
    {
        'title': 'SSRF绕过黑名单过滤',
        'description': '这个应用程序有SSRF漏洞但实现了黑名单过滤。绕过过滤器来访问http://localhost/admin并删除用户carlos。',
        'category': 'Web',
        'difficulty': 'hard',
        'score': 300,
        'flag': 'flag{ssrf_bypass_filter_success}',
        'hint': '尝试使用IP地址的不同表示形式或URL编码来绕过黑名单。',
        'docker_image': 'ctf-platform/ssrf-bypass:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'path_slug': 'ssrf-bypass',
        'modules': ['ssrf', '绕过常见的SSRF防御']
    }
]

def create_challenges():
    """创建容器题目并关联到学习路径"""
    web_category = Category.objects.get(name='Web')

    created_count = 0
    for challenge_data in CONTAINER_CHALLENGES:
        # 创建或更新题目
        challenge, created = Challenge.objects.update_or_create(
            title=challenge_data['title'],
            defaults={
                'description': challenge_data['description'],
                'category': web_category,
                'difficulty': challenge_data['difficulty'],
                'score': challenge_data['score'],
                'flag': challenge_data['flag'],
                'hint': challenge_data['hint'],
                'docker_image': challenge_data['docker_image'],
                'redirect_port': challenge_data['redirect_port'],
                'redirect_type': challenge_data['redirect_type'],
                'is_active': True
            }
        )

        print(f"{'创建' if created else '更新'}题目: {challenge.title}")

        # 关联到学习路径模块
        for module_name in challenge_data['modules']:
            # 查找包含该名称的学习路径
            paths = LearningPath.objects.filter(title__icontains=module_name)
            for path in paths:
                # 查找模块
                modules = path.modules.filter(title__icontains=module_name.split('-')[-1])
                for module in modules:
                    # 创建模块-题目关联
                    lab, lab_created = ModuleLab.objects.get_or_create(
                        module=module,
                        lab=challenge,
                        defaults={'order': 0, 'is_optional': False}
                    )
                    if lab_created:
                        print(f"  关联到模块: {path.title} - {module.title}")
                        created_count += 1

    print("\n✅ 容器题目创建并关联完成！")
    print(f"\n已创建/更新 {len(CONTAINER_CHALLENGES)} 个容器题目")
    print(f"已创建 {created_count} 个模块-题目关联")

if __name__ == '__main__':
    create_challenges()
