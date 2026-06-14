"""
清理过期容器的管理命令
使用方法: python manage.py cleanup_containers
"""

from django.core.management.base import BaseCommand
from challenges.container_manager import get_container_manager


class Command(BaseCommand):
    help = '清理过期的题目容器'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只显示将要清理的容器，不实际执行',
        )

    def handle(self, *args, **options):
        """执行清理任务"""
        container_manager = get_container_manager()

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry-run 模式：只显示将要清理的容器'))

        # 清理过期容器
        count = container_manager.cleanup_expired_containers()

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'将清理 {count} 个过期容器'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✅ 已清理 {count} 个过期容器'))
