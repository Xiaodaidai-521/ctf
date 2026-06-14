# 生成测试题库数据的脚本
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
django.setup()

from exams.models import TheoryQuestion
from challenges.models import Challenge, Category
from users.models import CTFUser

def create_theory_questions():
    """创建理论测试题目"""
    print("创建理论测试题目...")

    # 单选题
    single_choice_questions = [
        {
            "question_text": "TCP协议中，SYN标志位的作用是什么？",
            "options": ["建立连接", "断开连接", "数据传输", "流量控制"],
            "correct_answer": "建立连接",
            "difficulty": "easy",
            "category": "网络安全基础"
        },
        {
            "question_text": "以下哪个协议运行在UDP协议之上？",
            "options": ["HTTP", "HTTPS", "DNS", "FTP"],
            "correct_answer": "DNS",
            "difficulty": "easy",
            "category": "网络安全基础"
        },
        {
            "question_text": "MD5哈希算法的输出长度是多少位？",
            "options": ["128位", "256位", "512位", "160位"],
            "correct_answer": "128位",
            "difficulty": "easy",
            "category": "密码学"
        },
        {
            "question_text": "以下哪种攻击属于DDoS攻击？",
            "options": ["SQL注入", "XSS攻击", "SYN Flood", "CSRF攻击"],
            "correct_answer": "SYN Flood",
            "difficulty": "easy",
            "category": "网络攻击"
        },
        {
            "question_text": "HTTPS协议使用的默认端口是多少？",
            "options": ["80", "443", "8080", "8443"],
            "correct_answer": "443",
            "difficulty": "easy",
            "category": "网络安全基础"
        },
        {
            "question_text": "以下哪种加密算法是对称加密？",
            "options": ["RSA", "ECC", "AES", "DSA"],
            "correct_answer": "AES",
            "difficulty": "easy",
            "category": "密码学"
        },
        {
            "question_text": "SQL注入攻击的主要目的是什么？",
            "options": ["窃取用户密码", "获取数据库信息", "修改网页内容", "删除服务器文件"],
            "correct_answer": "获取数据库信息",
            "difficulty": "easy",
            "category": "Web安全"
        },
        {
            "question_text": "以下哪个HTTP方法通常用于更新资源？",
            "options": ["GET", "POST", "PUT", "DELETE"],
            "correct_answer": "PUT",
            "difficulty": "easy",
            "category": "Web安全"
        },
        {
            "question_text": "防火墙的主要功能是什么？",
            "options": ["加密数据", "过滤网络流量", "存储数据", "压缩数据"],
            "correct_answer": "过滤网络流量",
            "difficulty": "easy",
            "category": "网络安全基础"
        },
        {
            "question_text": "XSS攻击的全称是什么？",
            "options": ["跨站请求伪造", "跨站脚本攻击", "SQL注入", "远程代码执行"],
            "correct_answer": "跨站脚本攻击",
            "difficulty": "easy",
            "category": "Web安全"
        }
    ]

    # 创建更多单选题以凑够30道
    for i in range(20):
        single_choice_questions.append({
            "question_text": f"网络安全测试单选题 {i+11}：下列哪项是常见的安全漏洞类型？",
            "options": ["缓冲区溢出", "正常功能", "性能优化", "用户体验"],
            "correct_answer": "缓冲区溢出",
            "difficulty": "easy",
            "category": "网络安全基础"
        })

    # 多选题
    multiple_choice_questions = [
        {
            "question_text": "以下哪些属于常见的Web攻击类型？",
            "options": ["SQL注入", "XSS攻击", "CSRF攻击", "缓冲区溢出"],
            "correct_answer": "SQL注入,XSS攻击,CSRF攻击,缓冲区溢出",
            "difficulty": "medium",
            "category": "Web安全"
        },
        {
            "question_text": "对称加密算法的特点包括？",
            "options": ["加密和解密使用相同密钥", "加密速度快", "适合大数据量加密", "密钥管理复杂"],
            "correct_answer": "加密和解密使用相同密钥,加密速度快,适合大数据量加密",
            "difficulty": "medium",
            "category": "密码学"
        },
        {
            "question_text": "以下哪些是常见的服务器配置安全措施？",
            "options": ["关闭不必要的服务", "定期更新系统补丁", "使用强密码", "安装杀毒软件"],
            "correct_answer": "关闭不必要的服务,定期更新系统补丁,使用强密码,安装杀毒软件",
            "difficulty": "medium",
            "category": "系统安全"
        },
        {
            "question_text": "网络防火墙可以过滤哪些信息？",
            "options": ["IP地址", "端口号", "协议类型", "数据内容"],
            "correct_answer": "IP地址,端口号,协议类型",
            "difficulty": "medium",
            "category": "网络安全基础"
        },
        {
            "question_text": "以下哪些是SQL注入的防护措施？",
            "options": ["使用参数化查询", "输入验证", "最小权限原则", "使用ORM"],
            "correct_answer": "使用参数化查询,输入验证,最小权限原则,使用ORM",
            "difficulty": "medium",
            "category": "Web安全"
        }
    ]

    # 创建更多多选题以凑够20道
    for i in range(15):
        multiple_choice_questions.append({
            "question_text": f"网络安全测试多选题 {i+6}：下列哪些是安全最佳实践？",
            "options": ["定期备份", "访问控制", "日志审计", "加密传输"],
            "correct_answer": "定期备份,访问控制,日志审计,加密传输",
            "difficulty": "medium",
            "category": "网络安全基础"
        })

    # 判断题
    true_false_questions = [
        {
            "question_text": "HTTP协议是加密的传输协议。",
            "correct_answer": "False",
            "difficulty": "easy",
            "category": "网络安全基础"
        },
        {
            "question_text": "SSL/TLS协议用于在传输层提供安全通信。",
            "correct_answer": "True",
            "difficulty": "easy",
            "category": "网络安全基础"
        },
        {
            "question_text": "MD5算法是安全的哈希算法，适合存储密码。",
            "correct_answer": "False",
            "difficulty": "easy",
            "category": "密码学"
        },
        {
            "question_text": "VPN可以提供安全的远程访问。",
            "correct_answer": "True",
            "difficulty": "easy",
            "category": "网络安全基础"
        },
        {
            "question_text": "XSS攻击只能通过GET请求触发。",
            "correct_answer": "False",
            "difficulty": "medium",
            "category": "Web安全"
        },
        {
            "question_text": "CSRF攻击利用了用户的已登录状态。",
            "correct_answer": "True",
            "difficulty": "medium",
            "category": "Web安全"
        },
        {
            "question_text": "HTTPS不需要证书。",
            "correct_answer": "False",
            "difficulty": "easy",
            "category": "网络安全基础"
        },
        {
            "question_text": "公钥加密算法中，公钥可以加密，私钥可以解密。",
            "correct_answer": "True",
            "difficulty": "medium",
            "category": "密码学"
        }
    ]

    # 创建更多判断题以凑够20道
    for i in range(12):
        true_false_questions.append({
            "question_text": f"网络安全测试判断题 {i+9}：定期更新密码是良好的安全习惯。",
            "correct_answer": "True",
            "difficulty": "easy",
            "category": "网络安全基础"
        })

    # 插入数据
    created_count = 0

    for q in single_choice_questions:
        TheoryQuestion.objects.create(
            question_type='single_choice',
            question_text=q['question_text'],
            options=q['options'],
            correct_answer=q['correct_answer'],
            difficulty=q['difficulty'],
            category=q['category'],
            is_active=True
        )
        created_count += 1

    for q in multiple_choice_questions:
        TheoryQuestion.objects.create(
            question_type='multiple_choice',
            question_text=q['question_text'],
            options=q['options'],
            correct_answer=q['correct_answer'],
            difficulty=q['difficulty'],
            category=q['category'],
            is_active=True
        )
        created_count += 1

    for q in true_false_questions:
        TheoryQuestion.objects.create(
            question_type='true_false',
            question_text=q['question_text'],
            options=['True', 'False'],
            correct_answer=q['correct_answer'],
            difficulty=q['difficulty'],
            category=q['category'],
            is_active=True
        )
        created_count += 1

    print(f"✓ 创建了 {created_count} 道理论测试题目")


def create_practice_challenges():
    """创建实战测试题目"""
    print("\n创建实战测试题目...")

    # 获取或创建分类
    category, _ = Category.objects.get_or_create(
        name='Web',
        defaults={'description': 'Web 安全题目'}
    )

    challenges = []

    # 简单题目
    easy_challenges = [
        {
            "title": "简单计算",
            "description": "计算 123 + 456 = ?",
            "flag": "flag{579}",
            "difficulty": "easy",
            "score": 100,
            "category": category
        },
        {
            "title": "字符串反转",
            "description": "将 'hello' 反转后的结果是？",
            "flag": "flag{olleh}",
            "difficulty": "easy",
            "score": 100,
            "category": category
        },
        {
            "title": "ASCII码转换",
            "description": "字符 'A' 的ASCII码值是？",
            "flag": "flag{65}",
            "difficulty": "easy",
            "score": 100,
            "category": category
        }
    ]

    # 中等题目
    medium_challenges = [
        {
            "title": "Base64解码",
            "description": "解码这段Base64: 'SGVsbG8gV29ybGQ='",
            "flag": "flag{Hello World}",
            "difficulty": "medium",
            "score": 200,
            "category": category
        },
        {
            "title": "凯撒密码",
            "description": "凯撒密码(偏移量3)解密: 'Khoor Zruog'",
            "flag": "flag{Hello World}",
            "difficulty": "medium",
            "score": 200,
            "category": category
        }
    ]

    # 困难题目
    hard_challenges = [
        {
            "title": "综合挑战",
            "description": "这是一个综合性题目，需要运用多种技能。",
            "flag": "flag{CTF_master_2024}",
            "difficulty": "hard",
            "score": 500,
            "category": category
        }
    ]

    # 插入数据
    for ch in easy_challenges + medium_challenges + hard_challenges:
        challenge, created = Challenge.objects.get_or_create(
            title=ch['title'],
            defaults={
                'description': ch['description'],
                'flag': ch['flag'],
                'difficulty': ch['difficulty'],
                'score': ch['score'],
                'category': ch['category'],
                'is_active': True
            }
        )
        if created:
            challenges.append(challenge)

    print(f"✓ 创建了 {len(easy_challenges)} 道简单题目")
    print(f"✓ 创建了 {len(medium_challenges)} 道中等题目")
    print(f"✓ 创建了 {len(hard_challenges)} 道困难题目")
    print(f"总计创建 {len(challenges)} 道实战题目")


if __name__ == '__main__':
    print("=" * 50)
    print("开始生成测试题库数据")
    print("=" * 50)

    try:
        create_theory_questions()
        create_practice_challenges()

        print("\n" + "=" * 50)
        print("✓ 测试数据生成完成！")
        print("=" * 50)

        # 统计数据
        theory_count = TheoryQuestion.objects.filter(is_active=True).count()
        challenge_count = Challenge.objects.filter(is_active=True).count()

        print(f"\n当前题库统计：")
        print(f"  理论题库: {theory_count} 道")
        print(f"  实战题库: {challenge_count} 道")

    except Exception as e:
        print(f"\n✗ 生成数据时出错: {e}")
        import traceback
        traceback.print_exc()
