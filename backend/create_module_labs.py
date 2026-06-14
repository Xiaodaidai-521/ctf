"""
为缺少实验的模块创建实验关联
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_platform.settings')
django.setup()

from learning_paths.models import PathModule, ModuleLab
from challenges.models import Challenge, Category

# 为每个缺少实验的模块创建或关联实验
# 格式: 模块ID -> [(挑战ID, 顺序, 是否可选)]

module_lab_mapping = {
    # Web缓存欺骗路径的模块
    11: [
        # 创建一个新的Web缓存欺骗实验
        {'title': 'Web缓存基础练习', 'description': '理解Web缓存的工作原理', 'difficulty': 'easy', 'score': 100},
    ],
    12: [
        {'title': '缓存规则识别练习', 'description': '学习识别和分析缓存规则', 'difficulty': 'easy', 'score': 100},
    ],
    13: [
        {'title': 'Web缓存欺骗攻击实战', 'description': '构建并执行Web缓存欺骗攻击', 'difficulty': 'medium', 'score': 200},
    ],
    
    # SQL注入路径的模块
    14: [
        {'title': 'SQL注入基础认知', 'description': '识别和理解基本的SQL注入漏洞', 'difficulty': 'easy', 'score': 100},
    ],
    15: [
        {'title': 'SQL注入检测实践', 'description': '使用各种方法检测SQL注入漏洞', 'difficulty': 'easy', 'score': 100},
    ],
    16: [
        {'title': 'SQL注入数据检索', 'description': '利用SQL注入检索隐藏数据', 'difficulty': 'medium', 'score': 200},
    ],
    17: [
        {'title': 'SQL注入高级利用', 'description': '在不同查询位置利用SQL注入', 'difficulty': 'hard', 'score': 300},
    ],
}

# 获取或创建Web分类
web_category, _ = Category.objects.get_or_create(
    name='Web',
    defaults={'description': 'Web安全相关题目'}
)

print("开始为缺少实验的模块创建实验关联...")
print("="*60)

created_challenges = []
created_module_labs = []

for module_id, labs in module_lab_mapping.items():
    try:
        module = PathModule.objects.get(id=module_id)
        print(f"\n处理模块 {module_id}: {module.title}")
        
        for order, lab_info in enumerate(labs):
            # 检查是否已经存在同名挑战
            existing_challenge = Challenge.objects.filter(
                title=lab_info['title']
            ).first()
            
            if existing_challenge:
                challenge = existing_challenge
                print(f"  ✓ 使用现有挑战: {challenge.title}")
            else:
                # 创建新挑战
                challenge = Challenge.objects.create(
                    title=lab_info['title'],
                    description=lab_info['description'],
                    category=web_category,
                    difficulty=lab_info['difficulty'],
                    score=lab_info['score'],
                    flag=f'FLAG{{{"test_flag_{module_id}_{order}"}}}',  # 生成测试flag
                    is_active=True,
                )
                created_challenges.append(challenge)
                print(f"  ✓ 创建新挑战: {challenge.title} (ID: {challenge.id})")
            
            # 检查是否已经存在模块-实验关联
            existing_ml = ModuleLab.objects.filter(
                module=module,
                lab=challenge
            ).first()
            
            if existing_ml:
                print(f"    → 模块-实验关联已存在")
            else:
                # 创建模块-实验关联
                module_lab = ModuleLab.objects.create(
                    module=module,
                    lab=challenge,
                    order=order,
                    is_optional=False
                )
                created_module_labs.append(module_lab)
                print(f"    → 创建模块-实验关联 (顺序: {order})")
                
    except PathModule.DoesNotExist:
        print(f"✗ 模块 {module_id} 不存在")
    except Exception as e:
        print(f"✗ 处理模块 {module_id} 时出错: {e}")

print("\n" + "="*60)
print(f"总结:")
print(f"  创建新挑战: {len(created_challenges)} 个")
print(f"  创建模块-实验关联: {len(created_module_labs)} 个")

# 显示创建的挑战列表
if created_challenges:
    print("\n新创建的挑战:")
    for ch in created_challenges:
        print(f"  - {ch.title} (ID: {ch.id}, 难度: {ch.difficulty}, 分数: {ch.score})")

# 验证所有模块现在都有实验关联
print("\n" + "="*60)
print("验证模块实验关联:")
print("="*60)

modules_without_labs = []
for path in PathModule.objects.all().order_by('learning_path_id', 'order'):
    lab_count = module.module_labs.count()
    if lab_count == 0:
        modules_without_labs.append(module)
        print(f"  ⚠ {module.learning_path.title} - {module.title} - 无实验")
    else:
        print(f"  ✓ {module.learning_path.title} - {module.title} - {lab_count} 个实验")

if modules_without_labs:
    print(f"\n⚠ 仍有 {len(modules_without_labs)} 个模块缺少实验关联")
else:
    print("\n✓ 所有模块都有关联的实验！")

print("\n" + "="*60)
print("完成！")
