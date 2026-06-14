"""
优化学习路径配置
优化模块描述、预计时长，并为缺少实验的模块创建实验
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_platform.settings')
django.setup()

from learning_paths.models import LearningPath, PathModule, ModuleLab
from challenges.models import Challenge, Category

# 优化模块配置
module_updates = {
    # CORS 路径
    1: {
        'description': '学习CORS的基本概念、工作原理以及同源策略的基础知识',
        'estimated_minutes': 45
    },
    2: {
        'description': '深入了解CORS配置错误导致的安全漏洞及攻击原理',
        'estimated_minutes': 60
    },
    3: {
        'description': '通过实际操作练习CORS漏洞的利用和防护',
        'estimated_minutes': 90
    },
    
    # SSRF 路径
    4: {
        'description': '了解SSRF漏洞的基本概念、攻击原理和潜在影响',
        'estimated_minutes': 45
    },
    5: {
        'description': '学习针对服务器的SSRF攻击技术和利用方法',
        'estimated_minutes': 60
    },
    6: {
        'description': '通过实践学习攻击后端系统的SSRF技术',
        'estimated_minutes': 90
    },
    7: {
        'description': '掌握绕过常见SSRF防御措施的高级技术',
        'estimated_minutes': 60
    },
    
    # WebSocket 路径
    8: {
        'description': '学习WebSocket协议的基础知识和安全注意事项',
        'estimated_minutes': 45
    },
    9: {
        'description': '使用Burp Suite操作WebSocket流量进行安全测试',
        'estimated_minutes': 75
    },
    10: {
        'description': '了解WebSocket通信中常见的安全漏洞类型',
        'estimated_minutes': 60
    },
    
    # Web缓存欺骗 路径
    11: {
        'description': '理解Web缓存的工作原理和缓存键机制',
        'estimated_minutes': 45
    },
    12: {
        'description': '学习不同类型的缓存规则和缓存控制头',
        'estimated_minutes': 60
    },
    13: {
        'description': '通过实践构建Web缓存欺骗攻击并利用路径映射差异',
        'estimated_minutes': 90
    },
    
    # SQL注入 路径
    14: {
        'description': '了解SQL注入漏洞的基本概念和潜在影响',
        'estimated_minutes': 45
    },
    15: {
        'description': '学习手动和自动检测SQL注入漏洞的各种方法',
        'estimated_minutes': 60
    },
    16: {
        'description': '通过实践学习利用SQL注入检索隐藏数据',
        'estimated_minutes': 90
    },
    17: {
        'description': '掌握SQL注入在不同查询位置和场景中的利用技术',
        'estimated_minutes': 75
    },
}

print("开始优化模块配置...")
print("="*60)

# 更新模块配置
for module_id, updates in module_updates.items():
    try:
        module = PathModule.objects.get(id=module_id)
        module.description = updates['description']
        module.estimated_minutes = updates['estimated_minutes']
        module.save()
        print(f"✓ 模块 {module_id}: {module.title}")
        print(f"  描述: {module.description[:50]}...")
        print(f"  时长: {module.estimated_minutes} 分钟")
    except PathModule.DoesNotExist:
        print(f"✗ 模块 {module_id} 不存在")
    except Exception as e:
        print(f"✗ 模块 {module_id} 更新失败: {e}")

print("\n" + "="*60)
print("模块配置优化完成！")
print("\n开始检查模块实验关联...")
print("="*60)

# 检查哪些模块缺少实验
modules_without_labs = []
for path in LearningPath.objects.all():
    print(f"\n路径: {path.title}")
    for module in path.modules.all().order_by('order'):
        lab_count = module.module_labs.count()
        if lab_count == 0:
            modules_without_labs.append(module)
            print(f"  ⚠ {module.title} - 无实验关联")
        else:
            print(f"  ✓ {module.title} - {lab_count} 个实验")

if modules_without_labs:
    print(f"\n共有 {len(modules_without_labs)} 个模块缺少实验关联")
    print("\n建议创建的实验：")
    for module in modules_without_labs:
        print(f"\n模块: {module.title}")
        print(f"  路径: {module.learning_path.title}")
        print(f"  类型: {module.get_module_type_display()}")
        print(f"  建议创建实验:")
        print(f"    1. {module.title} - 基础练习")
        print(f"      难度: Easy")
        print(f"      分数: 100")
else:
    print("\n✓ 所有模块都有关联的实验")

print("\n" + "="*60)
print("优化完成！")
