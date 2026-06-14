#!/usr/bin/env python
"""
添加真实CTF题目 - 包含Docker镜像和FRP代理配置
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

from challenges.models import Challenge, Category

# 分类映射（根据需要调整）
CATEGORY_MAP = {
    'web': 1,      # Web
    'crypto': 2,   # Crypto
    'misc': 3,     # Misc
    'pwn': 4,      # Pwn
    'reverse': 5,  # Reverse
    'forensics': 6 # Forensics
}

# 20道CTF题目数据（包含Docker镜像配置）
CHALLENGES = [
    # ==================== Web题目 (4题) ====================
    {
        'title': 'SQL注入入门',
        'description': '''这是一个经典的SQL注入题目。

你需要找到一个能够绕过登录验证的方法，获取管理员权限。

提示：尝试在用户名字段使用单引号，看看会发生什么。

目标：获取管理员账户的flag。''',
        'category': CATEGORY_MAP['web'],
        'difficulty': 'easy',
        'score': 100,
        'flag': 'flag{sql_injection_is_dangerous}',
        'hint': '尝试使用 \' OR 1=1 -- 来绕过登录验证',
        'docker_image': 'ctf/web-sql-injection-easy:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': 'XSS攻击实战',
        'description': '''在一个留言板应用中发现了XSS漏洞。

目标是构造一个恶意脚本，当管理员访问页面时触发，从而获取cookie。

提示：查看输入过滤机制，尝试绕过。''',
        'category': CATEGORY_MAP['web'],
        'difficulty': 'medium',
        'score': 200,
        'flag': 'flag{xss_reflected_stored_attack}',
        'hint': '尝试使用HTML实体编码或者大小写绕过过滤',
        'docker_image': 'ctf/web-xss-medium:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': '文件上传漏洞',
        'description': '''网站允许用户上传头像，但存在文件上传漏洞。

目标：上传一个webshell并获取服务器权限。

注意：需要绕过文件类型检查和内容过滤。''',
        'category': CATEGORY_MAP['web'],
        'difficulty': 'medium',
        'score': 250,
        'flag': 'flag{file_upload_webshell_success}',
        'hint': '尝试使用双文件名技巧或者修改Content-Type',
        'docker_image': 'ctf/web-file-upload-medium:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': 'SSRF漏洞利用',
        'description': '''发现一个可以发起HTTP请求的功能点，可能存在SSRF漏洞。

目标：利用SSRF访问内网服务，获取flag。

提示：尝试访问 localhost 或者内网IP地址。''',
        'category': CATEGORY_MAP['web'],
        'difficulty': 'hard',
        'score': 350,
        'flag': 'flag{ssrf_internal_network_access}',
        'hint': '尝试使用 file:// 协议读取本地文件',
        'docker_image': 'ctf/web-ssrf-hard:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },

    # ==================== Crypto题目 (4题) ====================
    {
        'title': 'Base64编码',
        'description': '''这是一个简单的编码题目。

给你一段Base64编码的字符串，解码即可获得flag。

密文：ZmxhZ3tiYXNlNjRfZGVjb2RpbmdfaXNfZWFzeX0=''',
        'category': CATEGORY_MAP['crypto'],
        'difficulty': 'easy',
        'score': 50,
        'flag': 'flag{base64_decoding_is_easy}',
        'hint': '使用 base64 -d 命令或者在线工具解码',
        'docker_image': None,
        'redirect_port': None,
        'redirect_type': None,
        'is_active': True
    },
    {
        'title': '凯撒密码',
        'description': '''截获了一段加密信息，已知使用的是凯撒密码。

密文：khoor zruog

提示：偏移量为3''',
        'category': CATEGORY_MAP['crypto'],
        'difficulty': 'easy',
        'score': 100,
        'flag': 'flag{hello world}',
        'hint': '将每个字母向后偏移3位即可解密',
        'docker_image': None,
        'redirect_port': None,
        'redirect_type': None,
        'is_active': True
    },
    {
        'title': 'RSA解密',
        'description': '''获得了RSA的公钥和加密后的密文。

n = 3233
e = 17
c = 2790

请解密获取原始信息。''',
        'category': CATEGORY_MAP['crypto'],
        'difficulty': 'medium',
        'score': 300,
        'flag': 'flag{rsa_decryption_success}',
        'hint': '需要分解n获取p和q，然后计算私钥d',
        'docker_image': 'ctf/crypto-rsa-medium:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': '异或加密',
        'description': '''使用异或加密了一段信息，密钥是单字节。

密文（十六进制）：0c1f1a1310110a1b1b

找出密钥并解密。''',
        'category': CATEGORY_MAP['crypto'],
        'difficulty': 'hard',
        'score': 400,
        'flag': 'flag{xor_key_found}',
        'hint': '尝试暴力破解所有可能的单字节密钥',
        'docker_image': 'ctf/crypto-xor-hard:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },

    # ==================== Misc题目 (3题) ====================
    {
        'title': '图片隐写',
        'description': '''一张看似普通的图片，但隐藏着秘密信息。

下载图片并找出隐藏的flag。''',
        'category': CATEGORY_MAP['misc'],
        'difficulty': 'easy',
        'score': 100,
        'flag': 'flag{steganography_in_image}',
        'hint': '尝试使用 steghide 工具或者查看图片的LSB位',
        'docker_image': 'ctf/misc-stego-easy:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': '流量分析',
        'description': '''捕获了一个网络流量包，里面可能包含敏感信息。

分析pcap文件，找到flag。''',
        'category': CATEGORY_MAP['misc'],
        'difficulty': 'medium',
        'score': 250,
        'flag': 'flag{packet_analysis_complete}',
        'hint': '使用 Wireshark 打开文件，查看HTTP流量',
        'docker_image': 'ctf/misc-pcap-medium:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': '二维码解码',
        'description': '''二维码图像似乎有些模糊，但可能包含flag信息。

尝试解码这个二维码。''',
        'category': CATEGORY_MAP['misc'],
        'difficulty': 'easy',
        'score': 80,
        'flag': 'flag{qr_code_decoded}',
        'hint': '使用 zbarimg 或在线二维码解码工具',
        'docker_image': None,
        'redirect_port': None,
        'redirect_type': None,
        'is_active': True
    },

    # ==================== Pwn题目 (3题) ====================
    {
        'title': '缓冲区溢出入门',
        'description': '''一个存在缓冲区溢出漏洞的程序。

目标：利用溢出获取shell或者读取flag文件。

提示：需要覆盖返回地址。''',
        'category': CATEGORY_MAP['pwn'],
        'difficulty': 'easy',
        'score': 200,
        'flag': 'flag{buffer_overflow_basic}',
        'hint': '使用 pattern_create 和 pattern_find 确定偏移量',
        'docker_image': 'ctf/pwn-bof-easy:latest',
        'redirect_port': 8888,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': '格式化字符串',
        'description': '''程序使用了不安全的printf函数，存在格式化字符串漏洞。

目标：泄露内存地址并执行任意代码。''',
        'category': CATEGORY_MAP['pwn'],
        'difficulty': 'medium',
        'score': 350,
        'flag': 'flag{format_string_exploit}',
        'hint': '使用 %p 泄露栈上数据，%n 写入任意地址',
        'docker_image': 'ctf/pwn-fmtstr-medium:latest',
        'redirect_port': 8888,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': 'Shellcode注入',
        'description': '''程序允许输入并执行，但没有做长度检查。

目标：注入shellcode并执行。''',
        'category': CATEGORY_MAP['pwn'],
        'difficulty': 'hard',
        'score': 450,
        'flag': 'flag{shellcode_injection}',
        'hint': '注意NX保护是否开启',
        'docker_image': 'ctf/pwn-shellcode-hard:latest',
        'redirect_port': 8888,
        'redirect_type': 'path',
        'is_active': True
    },

    # ==================== Reverse题目 (3题) ====================
    {
        'title': '简单逆向',
        'description': '''一个简单的ELF程序，输入正确的密码即可获得flag。

使用GDB或者IDA分析程序逻辑。''',
        'category': CATEGORY_MAP['reverse'],
        'difficulty': 'easy',
        'score': 150,
        'flag': 'flag{reverse_engineering_start}',
        'hint': '使用 strings 命令查看字符串，或者用 gdb 调试',
        'docker_image': 'ctf/reverse-simple-easy:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': 'ARM汇编分析',
        'description': '''一个ARM架构的程序，需要分析汇编代码。

目标：找出正确的输入序列。''',
        'category': CATEGORY_MAP['reverse'],
        'difficulty': 'medium',
        'score': 300,
        'flag': 'flag{arm_assembly_mastered}',
        'hint': '使用 IDA Pro 或者 Ghidra 反编译',
        'docker_image': 'ctf/reverse-arm-medium:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': 'Android APK逆向',
        'description': '''一个Android应用，包含flag验证逻辑。

反编译APK并找出flag。''',
        'category': CATEGORY_MAP['reverse'],
        'difficulty': 'hard',
        'score': 400,
        'flag': 'flag{android_reversing_complete}',
        'hint': '使用 apktool 反编译，jadx 查看Java代码',
        'docker_image': 'ctf/reverse-android-hard:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },

    # ==================== Forensics题目 (3题) ====================
    {
        'title': '内存取证',
        'description': '''从一个崩溃的系统中获取了内存镜像。

分析内存文件，找到隐藏的flag。''',
        'category': CATEGORY_MAP['forensics'],
        'difficulty': 'medium',
        'score': 300,
        'flag': 'flag{memory_forensics_done}',
        'hint': '使用 Volatility 工具分析内存镜像',
        'docker_image': 'ctf/forensics-memory-medium:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': '磁盘取证',
        'description': '''发现了一个损坏的磁盘镜像文件。

目标：恢复被删除的文件，找出flag。''',
        'category': CATEGORY_MAP['forensics'],
        'difficulty': 'hard',
        'score': 450,
        'flag': 'flag{disk_recovery_success}',
        'hint': '使用 TestDisk 或者 foremost 工具',
        'docker_image': 'ctf/forensics-disk-hard:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    },
    {
        'title': '日志分析',
        'description': '''系统日志文件中记录了可疑活动。

分析日志，找到攻击者的flag。''',
        'category': CATEGORY_MAP['forensics'],
        'difficulty': 'easy',
        'score': 100,
        'flag': 'flag{log_analysis_complete}',
        'hint': '使用 grep 命令搜索关键字',
        'docker_image': 'ctf/forensics-log-easy:latest',
        'redirect_port': 80,
        'redirect_type': 'path',
        'is_active': True
    }
]

def add_challenges():
    """添加题目"""
    success_count = 0
    error_count = 0

    for idx, challenge_data in enumerate(CHALLENGES, 1):
        try:
            # 验证分类是否存在
            category_id = challenge_data.pop('category')
            category = Category.objects.filter(id=category_id).first()
            if not category:
                print(f"❌ 第 {idx} 个题目: 分类ID {category_id} 不存在")
                error_count += 1
                continue

            # 设置category对象
            challenge_data['category'] = category

            # 如果没有docker_image，移除这些字段
            if not challenge_data['docker_image']:
                challenge_data.pop('docker_image', None)
                challenge_data.pop('redirect_port', None)
                challenge_data.pop('redirect_type', None)

            # 创建题目
            challenge = Challenge.objects.create(**challenge_data)

            docker_info = ""
            if challenge.docker_image:
                docker_info = f" | 镜像: {challenge.docker_image}:{challenge.redirect_port}"

            print(f"✅ 第 {idx} 个题目: '{challenge.title}' 创建成功 (ID: {challenge.id}){docker_info}")
            success_count += 1

        except Exception as e:
            print(f"❌ 第 {idx} 个题目: 创建失败 - {str(e)}")
            error_count += 1

    print(f"\n{'='*50}")
    print(f"添加完成！成功: {success_count} 个, 失败: {error_count} 个")
    print(f"当前题目总数: {Challenge.objects.count()}")

    # 统计各分类数量
    print(f"\n{'='*50}")
    print("题目分类统计：")
    for category in Category.objects.all():
        count = Challenge.objects.filter(category=category).count()
        print(f"  {category.name}: {count} 题")

def list_categories():
    """列出所有分类"""
    print("\n可用分类：")
    print("-" * 50)
    for category in Category.objects.all():
        print(f"  ID: {category.id} | 名称: {category.name} | 描述: {category.description}")
    print("-" * 50)

def list_challenges():
    """列出所有题目"""
    print("\n当前题目列表：")
    print("-" * 50)
    for challenge in Challenge.objects.all():
        status = "✓" if challenge.is_active else "✗"
        docker_info = f" | 镜像: {challenge.docker_image}" if challenge.docker_image else ""
        print(f"  [{status}] {challenge.title} | {challenge.category.name} | {challenge.get_difficulty_display()} | {challenge.score}分{docker_info}")
    print("-" * 50)

def clear_all_challenges():
    """清除所有题目（危险操作）"""
    from submissions.models import Submission

    print("\n⚠️  警告：此操作将删除所有题目和提交记录！")
    confirm = input("确认删除？输入 'YES' 继续: ")

    if confirm == 'YES':
        submission_count = Submission.objects.all().delete()[0]
        challenge_count = Challenge.objects.all().delete()[0]
        print(f"✅ 已删除 {challenge_count} 道题目和 {submission_count} 条提交记录")
    else:
        print("❌ 操作已取消")

def main():
    print("=" * 50)
    print("CTF 题目管理工具 - 包含Docker镜像配置")
    print("=" * 50)

    print("\n可用操作:")
    print("  1. 列出分类")
    print("  2. 列出题目")
    print("  3. 添加20道题目")
    print("  4. 清除所有题目")
    print("  5. 退出")

    while True:
        choice = input("\n请选择操作 (1-5): ").strip()

        if choice == '1':
            list_categories()
        elif choice == '2':
            list_challenges()
        elif choice == '3':
            confirm = input("\n确认添加20道题目到数据库？(y/n): ")
            if confirm.lower() == 'y':
                add_challenges()
        elif choice == '4':
            clear_all_challenges()
        elif choice == '5':
            print("退出")
            break
        else:
            print("❌ 无效选择")

if __name__ == '__main__':
    main()
