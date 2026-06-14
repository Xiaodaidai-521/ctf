#!/usr/bin/env python
"""
更新CTF题目配置，使用真实可用的Docker镜像
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

from challenges.models import Challenge

# 镜像映射
IMAGE_MAP = {
    'web-sql-injection-easy': 'ctf/web-simple:latest',
    'web-xss-medium': 'ctf/web-flask:latest',
    'web-file-upload-medium': 'ctf/web-simple:latest',
    'web-ssrf-hard': 'ctf/web-flask:latest',
    'crypto-rsa-medium': 'ctf/crypto-base64:latest',
    'crypto-xor-hard': 'ctf/crypto-base64:latest',
    'misc-stego-easy': 'ctf/misc-static:latest',
    'misc-pcap-medium': 'ctf/misc-static:latest',
    'pwn-bof-easy': 'ctf/pwn-basic:latest',
    'pwn-fmtstr-medium': 'ctf/pwn-basic:latest',
    'pwn-shellcode-hard': 'ctf/pwn-basic:latest',
    'reverse-simple-easy': 'ctf/reverse-simple:latest',
    'reverse-arm-medium': 'ctf/reverse-simple:latest',
    'reverse-android-hard': 'ctf/reverse-simple:latest',
    'forensics-memory-medium': 'ctf/forensics-log:latest',
    'forensics-disk-hard': 'ctf/forensics-log:latest',
    'forensics-log-easy': 'ctf/forensics-log:latest',
}

def update_challenges():
    """更新题目配置"""
    updated = 0
    skipped = 0

    for challenge in Challenge.objects.all():
        if challenge.docker_image:
            # 提取镜像名称部分
            old_image = challenge.docker_image
            old_name = old_image.split(':')[0] if ':' in old_image else old_image

            # 查找对应的真实镜像
            real_image = None
            for key, value in IMAGE_MAP.items():
                if key in old_name:
                    real_image = value
                    break

            if real_image:
                challenge.docker_image = real_image
                challenge.save()
                print(f"✅ 已更新: {challenge.title}")
                print(f"   {old_image} → {real_image}")
                updated += 1
            else:
                print(f"⏭️  跳过: {challenge.title} (无对应镜像)")
                skipped += 1
        else:
            print(f"⏭️  跳过: {challenge.title} (无Docker镜像)")
            skipped += 1

    print(f"\n{'='*50}")
    print(f"更新完成！")
    print(f"  更新: {updated} 个")
    print(f"  跳过: {skipped} 个")
    print(f"{'='*50}")

def list_challenges():
    """列出所有题目"""
    print("\n当前题目列表：")
    print("-" * 80)
    print(f"{'ID':<5} {'题目名称':<30} {'Docker镜像':<30}")
    print("-" * 80)
    for challenge in Challenge.objects.all():
        docker_info = challenge.docker_image if challenge.docker_image else "无"
        print(f"{challenge.id:<5} {challenge.title[:29]:<30} {docker_info[:29]:<30}")
    print("-" * 80)

if __name__ == '__main__':
    print("=" * 50)
    print("CTF 题目镜像更新工具")
    print("=" * 50)

    print("\n当前题目状态：")
    list_challenges()

    print("\n可用镜像：")
    print("-" * 50)
    for image, real in IMAGE_MAP.items():
        print(f"  {image:<30} → {real}")
    print("-" * 50)

    confirm = input("\n确认更新题目配置？(y/n): ")
    if confirm.lower() == 'y':
        update_challenges()
        print("\n更新后的题目列表：")
        list_challenges()
    else:
        print("❌ 操作已取消")
