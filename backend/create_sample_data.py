"""
创建示例数据的脚本
运行命令: python manage.py shell < create_sample_data.py
"""

from django.contrib.auth import get_user_model
from challenges.models import Category, Challenge

User = get_user_model()

# 创建示例用户
print("创建示例用户...")
if not User.objects.filter(username='admin').exists():
    admin_user = User.objects.create_superuser(
        username='admin',
        email='admin@ctf.com',
        password='admin123456',
        nickname='管理员',
        team='CTF官方',
        role='admin'
    )
    print(f"✓ 创建管理员用户: {admin_user.username}")

for i in range(1, 6):
    username = f'user{i}'
    if not User.objects.filter(username=username).exists():
        user = User.objects.create_user(
            username=username,
            email=f'user{i}@ctf.com',
            password='user123456',
            nickname=f'用户{i}',
            team=f'战队{i}'
        )
        print(f"✓ 创建用户: {user.username}")

# 创建题目分类
print("\n创建题目分类...")
categories_data = [
    ('Web', 'Web安全相关题目'),
    ('Crypto', '密码学相关题目'),
    ('Misc', '杂项题目'),
    ('Pwn', '二进制漏洞利用题目'),
    ('Reverse', '逆向工程题目'),
    ('Forensics', '取证分析题目'),
]

for name, desc in categories_data:
    category, created = Category.objects.get_or_create(name=name, defaults={'description': desc})
    if created:
        print(f"✓ 创建分类: {category.name}")

# 创建示例题目
print("\n创建示例题目...")
challenges_data = [
    {
        'title': 'hello_world',
        'description': '这是一道入门级的Web题目，flag格式为 flag{...}',
        'category': 'Web',
        'difficulty': 'easy',
        'score': 10,
        'flag': 'flag{hello_world_ctf}',
        'hint': '查看页面源代码',
    },
    {
        'title': 'simple_login',
        'description': '简单的登录绕过题目，尝试绕过登录验证',
        'category': 'Web',
        'difficulty': 'easy',
        'score': 20,
        'flag': 'flag{login_bypass_success}',
        'hint': '尝试使用特殊字符绕过验证',
    },
    {
        'title': 'base64_decode',
        'description': '给定的密文是base64编码，请解密得到flag',
        'category': 'Crypto',
        'difficulty': 'easy',
        'score': 15,
        'flag': 'flag{crypto_base64}',
        'hint': '使用base64解码工具',
    },
    {
        'title': 'xor_encrypt',
        'description': '一段被XOR加密的数据，请找出密钥并解密',
        'category': 'Crypto',
        'difficulty': 'medium',
        'score': 50,
        'flag': 'flag{x0r_encryp7i0n}',
        'hint': '密钥是一个单字节',
    },
    {
        'title': 'misc_forensics',
        'description': '从一个被删除的文件中恢复隐藏信息',
        'category': 'Misc',
        'difficulty': 'medium',
        'score': 40,
        'flag': 'flag{file_recovery}',
        'hint': '使用文件恢复工具',
    },
    {
        'title': 'buffer_overflow',
        'description': '经典的缓冲区溢出漏洞，获取shell权限',
        'category': 'Pwn',
        'difficulty': 'hard',
        'score': 100,
        'flag': 'flag{b0f_exploit}',
        'hint': '计算准确的偏移量',
    },
    {
        'title': 'reverse_crackme',
        'description': '逆向分析这个程序，找到正确的注册码',
        'category': 'Reverse',
        'difficulty': 'medium',
        'score': 60,
        'flag': 'flag{r3v3rs3_3ng1n33r1ng}',
        'hint': '使用IDA或Ghidra分析',
    },
    {
        'title': 'sql_injection',
        'description': '利用SQL注入漏洞获取管理员密码',
        'category': 'Web',
        'difficulty': 'medium',
        'score': 50,
        'flag': 'flag{sqli_master}',
        'hint': '尝试联合查询注入',
    },
    {
        'title': 'steganography',
        'description': '图片中隐藏了信息，请提取出flag',
        'category': 'Misc',
        'difficulty': 'easy',
        'score': 30,
        'flag': 'flag{st3g0_h1dd3n}',
        'hint': '使用steghide工具',
    },
    {
        'title': 'shellcode',
        'description': '编写shellcode执行shell',
        'category': 'Pwn',
        'difficulty': 'expert',
        'score': 150,
        'flag': 'flag{sh3llc0d3_master}',
        'hint': '避免使用null字节',
    },
    {
        'title': 'rsa_low_exponent',
        'description': 'RSA加密，低指数攻击',
        'category': 'Crypto',
        'difficulty': 'hard',
        'score': 80,
        'flag': 'flag{rsa_low_e}',
        'hint': 'e=3的攻击方式',
    },
    {
        'title': 'memory_dump',
        'description': '分析内存转储文件，找到关键信息',
        'category': 'Forensics',
        'difficulty': 'medium',
        'score': 45,
        'flag': 'flag{m3m0ry_f0r3nsics}',
        'hint': '使用Volatility工具',
    },
]

for challenge_data in challenges_data:
    category = Category.objects.get(name=challenge_data['category'])
    if not Challenge.objects.filter(title=challenge_data['title']).exists():
        challenge = Challenge.objects.create(
            title=challenge_data['title'],
            description=challenge_data['description'],
            category=category,
            difficulty=challenge_data['difficulty'],
            score=challenge_data['score'],
            flag=challenge_data['flag'],
            hint=challenge_data['hint'],
            is_active=True
        )
        print(f"✓ 创建题目: {challenge.title} ({challenge.category.name})")

print("\n示例数据创建完成！")
print("\n测试账号信息：")
print("-" * 40)
print("管理员账号:")
print("  用户名: admin")
print("  密码: admin123456")
print("\n普通用户账号:")
print("  用户名: user1")
print("  密码: user123456")
print("\n管理后台: http://localhost:8000/admin/")
print("API文档: http://localhost:8000/api-auth/")
