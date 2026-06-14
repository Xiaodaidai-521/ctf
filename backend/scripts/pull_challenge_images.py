#!/usr/bin/env python
"""
拉取CTF题目所需的所有Docker镜像
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
from challenges.container_manager import get_container_manager


def pull_all_images():
    """拉取所有题目所需的Docker镜像"""
    challenges = Challenge.objects.exclude(docker_image='').distinct('docker_image')

    if not challenges:
        print("❌ 没有配置Docker镜像的题目")
        return

    print(f"找到 {len(challenges)} 个需要拉取镜像的题目\n")

    container_manager = get_container_manager()
    success_count = 0
    fail_count = 0
    skipped_count = 0

    for challenge in challenges:
        if not challenge.docker_image:
            continue

        # 检查镜像是否已存在
        if container_manager.get_docker_image_status(challenge.docker_image):
            print(f"⏭️  跳过: {challenge.docker_image} (已存在)")
            skipped_count += 1
            continue

        # 拉取镜像
        print(f"\n{'='*50}")
        print(f"📦 正在拉取: {challenge.docker_image}")
        print(f"   题目: {challenge.title}")
        print(f"{'='*50}")

        if container_manager.pull_docker_image(challenge.docker_image):
            success_count += 1
        else:
            fail_count += 1

    print(f"\n{'='*50}")
    print(f"拉取完成！")
    print(f"  成功: {success_count} 个")
    print(f"  失败: {fail_count} 个")
    print(f"  跳过: {skipped_count} 个")
    print(f"{'='*50}")


def main():
    print("=" * 50)
    print("CTF 题目Docker镜像拉取工具")
    print("=" * 50)
    print()

    confirm = input("确认拉取所有题目的Docker镜像？(y/n): ")
    if confirm.lower() == 'y':
        pull_all_images()
    else:
        print("❌ 操作已取消")


if __name__ == '__main__':
    main()
