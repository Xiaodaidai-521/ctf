"""Register the pinned standalone practice environment without pulling at request time."""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from challenges.models import Category, Challenge


class Command(BaseCommand):
    help = '幂等导入 Juice Shop 自由练习靶场（镜像须预先拉取或 docker load）'

    @transaction.atomic
    def handle(self, *args, **options):
        category, _ = Category.objects.get_or_create(name='Web')
        challenge, created = Challenge.objects.update_or_create(
            docker_image=settings.JUICE_SHOP_IMAGE,
            defaults={
                'title': 'OWASP Juice Shop · 数据安全综合靶场',
                'category': category, 'difficulty': 'medium', 'score': 0,
                'flag': '', 'submission_mode': 'practice', 'is_active': True,
                'redirect_port': 3000, 'redirect_type': 'direct',
                'description': (
                    '在模拟电商系统中练习机密文档暴露、销售备份泄露、用户数据保护等场景。\n'
                    '点击启动容器，等待环境就绪后打开访问地址；每位用户拥有独立环境。\n'
                    '可按“发现暴露数据 → 判断数据类型 → 分析影响 → 提出整改方案”记录练习过程。\n'
                    '此入口为自由练习，不提交统一 Flag，不自动同步靶场积分或生成评分报告。\n'
                    '停止、到期回收后再次启动会清空该环境中的练习数据。'
                ),
                'hint': '进入 Juice Shop 后可访问 /#/score-board 查看挑战进度。AI、Web3 及依赖外网的挑战不在本次支持范围。',
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f'Juice Shop {"created" if created else "updated"}: challenge_id={challenge.pk}'
        ))
