#!/usr/bin/env python
"""
为学习路径创建知识概念数据
每个学习路径都有其特定的知识概念，而不是通用的知识概念
"""

import os
import sys
import django

# 设置Django环境
sys.path.append('/workspace/projects/ctf-platform/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from learning_paths.models import LearningPath, KnowledgeConcept, ConceptRelation

# 知识概念数据 - 每个路径有自己独特的概念
KNOWLEDGE_CONCEPTS = {
    'CORS跨域资源共享安全': [
        {
            'name': '同源策略 (SOP)',
            'slug': 'same-origin-policy',
            'description': '浏览器安全策略，限制文档或脚本从不同源加载资源',
            'concept_type': 'def',
            'difficulty_level': 2,
            'importance': 0.9
        },
        {
            'name': 'CORS 跨域资源共享',
            'slug': 'cross-origin-resource-sharing',
            'description': '一种使用HTTP头让浏览器获得跨域资源访问权限的机制',
            'concept_type': 'tech',
            'difficulty_level': 3,
            'importance': 0.95
        },
        {
            'name': 'Access-Control-Allow-Origin',
            'slug': 'access-control-allow-origin',
            'description': 'CORS响应头，指定哪些源可以访问资源',
            'concept_type': 'tech',
            'difficulty_level': 2,
            'importance': 0.85
        },
        {
            'name': 'Origin 反射漏洞',
            'slug': 'origin-reflection-vulnerability',
            'description': '错误地反射Origin头导致的CORS漏洞',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.9
        },
        {
            'name': 'JSONP 劫持',
            'slug': 'jsonp-hijacking',
            'description': '利用JSONP回调功能窃取跨域数据',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.8
        },
        {
            'name': 'CORS 白名单绕过',
            'slug': 'cors-whitelist-bypass',
            'description': '绕过CORS白名单验证的技术',
            'concept_type': 'vul',
            'difficulty_level': 5,
            'importance': 0.85
        }
    ],
    'SSRF服务端请求伪造攻击': [
        {
            'name': 'SSRF 服务端请求伪造',
            'slug': 'server-side-request-forgery',
            'description': '攻击者迫使服务器向非预期位置发出请求的漏洞',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.95
        },
        {
            'name': '本地回环访问',
            'slug': 'localhost-access',
            'description': '通过SSRF访问本地服务器和内部服务',
            'concept_type': 'vul',
            'difficulty_level': 3,
            'importance': 0.9
        },
        {
            'name': '内网端口扫描',
            'slug': 'internal-port-scanning',
            'description': '使用SSRF扫描内网开放端口',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.85
        },
        {
            'name': '云元数据服务攻击',
            'slug': 'cloud-metadata-attack',
            'description': '通过SSRF访问云服务商的元数据服务',
            'concept_type': 'vul',
            'difficulty_level': 5,
            'importance': 0.95
        },
        {
            'name': 'DNS 重绑定',
            'slug': 'dns-rebinding',
            'description': '绕过SSRF防护的DNS重绑定攻击技术',
            'concept_type': 'tech',
            'difficulty_level': 4,
            'importance': 0.8
        },
        {
            'name': 'SSRF 防御技术',
            'slug': 'ssrf-defenses',
            'description': '有效防御SSRF攻击的方法和技术',
            'concept_type': 'def',
            'difficulty_level': 3,
            'importance': 0.9
        }
    ],
    'WebSocket安全漏洞': [
        {
            'name': 'WebSocket 协议',
            'slug': 'websocket-protocol',
            'description': '全双工通信协议，允许客户端和服务器进行实时数据传输',
            'concept_type': 'tech',
            'difficulty_level': 2,
            'importance': 0.85
        },
        {
            'name': 'WebSocket 握手劫持',
            'slug': 'websocket-handshake-hijacking',
            'description': '劫持WebSocket连接建立过程的攻击',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.85
        },
        {
            'name': '跨站点WebSocket劫持 (CSWSH)',
            'slug': 'cross-site-websocket-hijacking',
            'description': '类似CSRF但针对WebSocket连接的攻击',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.9
        },
        {
            'name': 'WebSocket 消息注入',
            'slug': 'websocket-message-injection',
            'description': '向WebSocket连接中注入恶意消息',
            'concept_type': 'vul',
            'difficulty_level': 3,
            'importance': 0.85
        },
        {
            'name': 'WebSocket Origin 验证绕过',
            'slug': 'websocket-origin-bypass',
            'description': '绕过WebSocket的Origin头验证',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.8
        },
        {
            'name': 'WebSocket 安全最佳实践',
            'slug': 'websocket-security-best-practices',
            'description': 'WebSocket应用的安全防护措施',
            'concept_type': 'def',
            'difficulty_level': 3,
            'importance': 0.9
        }
    ],
    'Web缓存欺骗': [
        {
            'name': 'Web 缓存机制',
            'slug': 'web-caching-mechanism',
            'description': '浏览器和代理服务器缓存Web资源的工作原理',
            'concept_type': 'tech',
            'difficulty_level': 2,
            'importance': 0.85
        },
        {
            'name': '缓存投毒',
            'slug': 'cache-poisoning',
            'description': '污染缓存内容，将恶意内容提供给其他用户',
            'concept_type': 'vul',
            'difficulty_level': 5,
            'importance': 0.95
        },
        {
            'name': '缓存键操控',
            'slug': 'cache-key-manipulation',
            'description': '操控缓存键来投毒缓存',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.9
        },
        {
            'name': 'Web缓存欺骗',
            'slug': 'web-cache-deception',
            'description': '欺骗缓存机制，使缓存存储非预期内容',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.9
        },
        {
            'name': '未参数化的请求',
            'slug': 'unkeyed-port',
            'description': '缓存键未包含某些参数导致的漏洞',
            'concept_type': 'vul',
            'difficulty_level': 3,
            'importance': 0.85
        },
        {
            'name': '缓存污染防御',
            'slug': 'cache-poisoning-defenses',
            'description': '防止缓存投毒的防御措施',
            'concept_type': 'def',
            'difficulty_level': 3,
            'importance': 0.9
        }
    ],
    'SQL注入': [
        {
            'name': 'SQL 注入',
            'slug': 'sql-injection',
            'description': '通过恶意SQL查询操纵数据库的攻击',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.95
        },
        {
            'name': 'UNION 查询注入',
            'slug': 'union-based-sql-injection',
            'description': '使用UNION操作符合并查询结果',
            'concept_type': 'vul',
            'difficulty_level': 3,
            'importance': 0.85
        },
        {
            'name': '布尔盲注',
            'slug': 'boolean-blind-sql-injection',
            'description': '通过布尔响应推断数据库信息',
            'concept_type': 'vul',
            'difficulty_level': 4,
            'importance': 0.85
        },
        {
            'name': '时间盲注',
            'slug': 'time-based-blind-sql-injection',
            'description': '通过响应时间延迟推断数据库信息',
            'concept_type': 'vul',
            'difficulty_level': 5,
            'importance': 0.9
        },
        {
            'name': '错误注入',
            'slug': 'error-based-sql-injection',
            'description': '利用数据库错误消息获取信息',
            'concept_type': 'vul',
            'difficulty_level': 3,
            'importance': 0.85
        },
        {
            'name': '二阶SQL注入',
            'slug': 'second-order-sql-injection',
            'description': '在存储和后续检索时触发的SQL注入',
            'concept_type': 'vul',
            'difficulty_level': 5,
            'importance': 0.9
        },
        {
            'name': '预编译语句',
            'slug': 'prepared-statements',
            'description': '使用参数化查询防止SQL注入',
            'concept_type': 'def',
            'difficulty_level': 2,
            'importance': 0.95
        },
        {
            'name': '输入验证',
            'slug': 'input-validation',
            'description': '验证和清理用户输入防止注入',
            'concept_type': 'def',
            'difficulty_level': 3,
            'importance': 0.9
        }
    ]
}

# 概念关系数据
CONCEPT_RELATIONS = {
    'CORS跨域资源共享安全': [
        ('同源策略 (SOP)', 'CORS 跨域资源共享', 'TEACHES'),
        ('CORS 跨域资源共享', 'Access-Control-Allow-Origin', 'REQUIRES'),
        ('CORS 跨域资源共享', 'Origin 反射漏洞', 'SIMILAR'),
        ('Origin 反射漏洞', 'JSONP 劫持', 'SIMILAR'),
        ('CORS 跨域资源共享', 'CORS 白名单绕过', 'PART_OF'),
    ],
    'SSRF服务端请求伪造攻击': [
        ('SSRF 服务端请求伪造', '本地回环访问', 'REQUIRES'),
        ('SSRF 服务端请求伪造', '内网端口扫描', 'REQUIRES'),
        ('SSRF 服务端请求伪造', '云元数据服务攻击', 'SIMILAR'),
        ('SSRF 服务端请求伪造', 'DNS 重绑定', 'SIMILAR'),
        ('SSRF 服务端请求伪造', 'SSRF 防御技术', 'TEACHES'),
    ],
    'WebSocket安全漏洞': [
        ('WebSocket 协议', 'WebSocket 握手劫持', 'PART_OF'),
        ('WebSocket 握手劫持', '跨站点WebSocket劫持 (CSWSH)', 'SIMILAR'),
        ('WebSocket 协议', 'WebSocket 消息注入', 'REQUIRES'),
        ('WebSocket 协议', 'WebSocket Origin 验证绕过', 'PART_OF'),
        ('WebSocket 协议', 'WebSocket 安全最佳实践', 'TEACHES'),
    ],
    'Web缓存欺骗': [
        ('Web 缓存机制', '缓存投毒', 'PART_OF'),
        ('缓存投毒', '缓存键操控', 'REQUIRES'),
        ('缓存投毒', 'Web缓存欺骗', 'SIMILAR'),
        ('缓存键操控', '未参数化的请求', 'REQUIRES'),
        ('Web 缓存机制', '缓存污染防御', 'TEACHES'),
    ],
    'SQL注入': [
        ('SQL 注入', 'UNION 查询注入', 'PART_OF'),
        ('SQL 注入', '布尔盲注', 'PART_OF'),
        ('SQL 注入', '时间盲注', 'PART_OF'),
        ('SQL 注入', '错误注入', 'PART_OF'),
        ('SQL 注入', '二阶SQL注入', 'PART_OF'),
        ('SQL 注入', '预编译语句', 'TEACHES'),
        ('SQL 注入', '输入验证', 'TEACHES'),
        ('预编译语句', '输入验证', 'SIMILAR'),
    ]
}

def import_knowledge_concepts():
    """导入知识概念数据"""
    print("开始导入知识概念数据...")

    for path_title, concepts in KNOWLEDGE_CONCEPTS.items():
        try:
            path = LearningPath.objects.get(title=path_title)
            print(f"\n处理学习路径: {path_title}")

            # 创建知识概念
            created_concepts = {}
            for concept_data in concepts:
                concept, created = KnowledgeConcept.objects.get_or_create(
                    slug=concept_data['slug'],
                    defaults=concept_data
                )
                if created:
                    print(f"  创建概念: {concept.name}")
                else:
                    print(f"  概念已存在: {concept.name}")
                created_concepts[concept.name] = concept

            # 创建概念关系
            if path_title in CONCEPT_RELATIONS:
                for from_name, to_name, relation_type in CONCEPT_RELATIONS[path_title]:
                    if from_name in created_concepts and to_name in created_concepts:
                        relation, created = ConceptRelation.objects.get_or_create(
                            from_concept=created_concepts[from_name],
                            to_concept=created_concepts[to_name],
                            defaults={'relation_type': relation_type}
                        )
                        if created:
                            print(f"  创建关系: {from_name} -> {to_name} ({relation_type})")

        except LearningPath.DoesNotExist:
            print(f"警告: 学习路径 '{path_title}' 不存在，跳过")

    print("\n知识概念数据导入完成！")

if __name__ == '__main__':
    import_knowledge_concepts()
