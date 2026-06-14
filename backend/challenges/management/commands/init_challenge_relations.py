from django.core.management.base import BaseCommand, CommandError

from ai_assistant.management.commands.rebuild_knowledge_packs import Command as RebuildKnowledgePacksCommand
from challenges.models import Challenge, ChallengeRelation


class Command(BaseCommand):
    help = 'Initialize explicit challenge-to-challenge relations for the current question bank.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-rebuild-packs',
            action='store_true',
            help='Skip rebuilding knowledge packs after initializing challenge relations.',
        )

    def handle(self, *args, **options):
        index = {
            challenge.id: challenge
            for challenge in Challenge.objects.filter(is_active=True).select_related('category')
        }
        if not index:
            raise CommandError('No active challenges found.')

        stats = {
            'created': 0,
            'updated': 0,
            'unchanged': 0,
        }

        def require(challenge_id):
            challenge = index.get(challenge_id)
            if not challenge:
                raise CommandError(f'Challenge {challenge_id} does not exist or is inactive.')
            return challenge

        def upsert_relation(
            source_id,
            target_id,
            relation_type,
            *,
            strength=3,
            sort_order=0,
            reason='',
            is_bidirectional=False,
            is_active=True,
        ):
            source = require(source_id)
            target = require(target_id)
            relation, created = ChallengeRelation.objects.update_or_create(
                source_challenge=source,
                target_challenge=target,
                relation_type=relation_type,
                defaults={
                    'strength': strength,
                    'sort_order': sort_order,
                    'reason': reason,
                    'is_bidirectional': is_bidirectional,
                    'is_active': is_active,
                },
            )
            if created:
                stats['created'] += 1
                return relation

            changed = False
            for field, value in {
                'strength': strength,
                'sort_order': sort_order,
                'reason': reason,
                'is_bidirectional': is_bidirectional,
                'is_active': is_active,
            }.items():
                if getattr(relation, field) != value:
                    changed = True
                    break

            if changed:
                stats['updated'] += 1
            else:
                stats['unchanged'] += 1
            return relation

        def add_bidirectional_same_topic(left_id, right_id, *, strength=4, sort_order=0, reason='同一知识主题'):
            upsert_relation(
                left_id,
                right_id,
                'same_topic',
                strength=strength,
                sort_order=sort_order,
                reason=reason,
                is_bidirectional=True,
            )
            upsert_relation(
                right_id,
                left_id,
                'same_topic',
                strength=strength,
                sort_order=sort_order,
                reason=reason,
                is_bidirectional=True,
            )

        def add_bidirectional_similar(left_id, right_id, *, strength=5, sort_order=0, reason='相似题型，适合对照练习'):
            upsert_relation(
                left_id,
                right_id,
                'similar',
                strength=strength,
                sort_order=sort_order,
                reason=reason,
                is_bidirectional=True,
            )
            upsert_relation(
                right_id,
                left_id,
                'similar',
                strength=strength,
                sort_order=sort_order,
                reason=reason,
                is_bidirectional=True,
            )

        def add_progression_pair(
            current_id,
            next_id,
            *,
            progression_reason,
            prerequisite_reason,
            progression_strength=4,
            prerequisite_strength=4,
            sort_order=0,
        ):
            upsert_relation(
                current_id,
                next_id,
                'progression',
                strength=progression_strength,
                sort_order=sort_order,
                reason=progression_reason,
            )
            upsert_relation(
                next_id,
                current_id,
                'prerequisite',
                strength=prerequisite_strength,
                sort_order=sort_order,
                reason=prerequisite_reason,
            )

        # SQL 注入专题链
        add_progression_pair(
            57,
            26,
            progression_reason='先建立 SQL 注入基础认知，再进入入门利用。',
            prerequisite_reason='理解入门题前，建议先掌握 SQL 注入基础认知。',
            sort_order=10,
        )
        add_progression_pair(
            26,
            58,
            progression_reason='完成入门利用后，继续做检测实践巩固注入点识别。',
            prerequisite_reason='在做检测实践前，建议先掌握 SQL 注入入门。',
            sort_order=20,
        )
        add_progression_pair(
            58,
            52,
            progression_reason='检测实践后，适合进入绕过登录类 SQL 注入练习。',
            prerequisite_reason='做绕过登录前，建议先完成 SQL 注入检测实践。',
            sort_order=30,
        )
        add_progression_pair(
            52,
            51,
            progression_reason='绕过登录后，继续进入 UNION 查询利用。',
            prerequisite_reason='掌握 UNION 查询前，建议先练习 SQL 注入绕过登录。',
            sort_order=40,
        )
        add_progression_pair(
            51,
            59,
            progression_reason='UNION 查询后，进一步进入数据检索场景。',
            prerequisite_reason='在数据检索前，建议先掌握 SQL 注入 UNION 查询。',
            sort_order=50,
        )
        add_progression_pair(
            59,
            60,
            progression_reason='完成数据检索后，可以进入高级利用阶段。',
            prerequisite_reason='进入高级利用前，建议先完成 SQL 注入数据检索。',
            sort_order=60,
        )
        for left_id, right_id in [(57, 26), (26, 58), (58, 52), (52, 51), (51, 59), (59, 60)]:
            add_bidirectional_same_topic(
                left_id,
                right_id,
                strength=5,
                sort_order=100,
                reason='同属 SQL 注入专题训练链。',
            )
        upsert_relation(
            26,
            51,
            'recommended',
            strength=4,
            sort_order=110,
            reason='完成 SQL 注入入门后，适合继续尝试 UNION 查询利用。',
        )
        upsert_relation(
            26,
            59,
            'recommended',
            strength=4,
            sort_order=120,
            reason='完成 SQL 注入入门后，适合继续做数据检索练习。',
        )

        # SSRF 专题链
        add_progression_pair(
            47,
            29,
            progression_reason='先掌握访问本地服务，再进入通用 SSRF 利用。',
            prerequisite_reason='做 SSRF 漏洞利用前，建议先完成 SSRF 攻击本地服务器。',
            sort_order=10,
        )
        add_progression_pair(
            29,
            48,
            progression_reason='通用利用之后，进入后端系统场景。',
            prerequisite_reason='做 SSRF 攻击后端系统前，建议先掌握 SSRF 漏洞利用。',
            sort_order=20,
        )
        add_progression_pair(
            48,
            53,
            progression_reason='后端系统利用后，继续学习黑名单绕过。',
            prerequisite_reason='做 SSRF 绕过黑名单过滤前，建议先掌握 SSRF 攻击后端系统。',
            sort_order=30,
        )
        for left_id, right_id in [(47, 29), (29, 48), (48, 53)]:
            add_bidirectional_same_topic(
                left_id,
                right_id,
                strength=5,
                sort_order=100,
                reason='同属 SSRF 专题训练链。',
            )
        upsert_relation(
            29,
            53,
            'recommended',
            strength=4,
            sort_order=110,
            reason='掌握 SSRF 常规利用后，建议继续练习黑名单绕过。',
        )

        # Web 缓存专题链
        add_progression_pair(
            54,
            55,
            progression_reason='先完成缓存基础练习，再识别缓存规则。',
            prerequisite_reason='识别缓存规则前，建议先完成 Web 缓存基础练习。',
            sort_order=10,
        )
        add_progression_pair(
            55,
            56,
            progression_reason='识别规则后，进入缓存欺骗实战。',
            prerequisite_reason='进入缓存欺骗实战前，建议先练习缓存规则识别。',
            sort_order=20,
        )
        add_progression_pair(
            56,
            50,
            progression_reason='完成实战后，继续挑战更高难度的缓存欺骗攻击。',
            prerequisite_reason='做高级缓存欺骗攻击前，建议先完成 Web 缓存欺骗攻击实战。',
            sort_order=30,
        )
        for left_id, right_id in [(54, 55), (55, 56), (56, 50)]:
            add_bidirectional_same_topic(
                left_id,
                right_id,
                strength=5,
                sort_order=100,
                reason='同属 Web 缓存专题训练链。',
            )

        # Pwn 训练链
        add_progression_pair(
            37,
            38,
            progression_reason='掌握缓冲区溢出入门后，再进入格式化字符串。',
            prerequisite_reason='学习格式化字符串前，建议先完成缓冲区溢出入门。',
            sort_order=10,
        )
        add_progression_pair(
            38,
            39,
            progression_reason='格式化字符串后，继续进入 Shellcode 注入。',
            prerequisite_reason='做 Shellcode 注入前，建议先掌握格式化字符串。',
            sort_order=20,
        )
        add_bidirectional_same_topic(
            37,
            38,
            strength=4,
            sort_order=100,
            reason='同属二进制利用基础训练。',
        )
        add_bidirectional_same_topic(
            38,
            39,
            strength=4,
            sort_order=110,
            reason='同属二进制利用进阶训练。',
        )

        # Reverse 训练链
        add_progression_pair(
            40,
            41,
            progression_reason='简单逆向之后，继续学习 ARM 汇编分析。',
            prerequisite_reason='做 ARM 汇编分析前，建议先完成简单逆向。',
            sort_order=10,
        )
        add_progression_pair(
            41,
            42,
            progression_reason='掌握 ARM 汇编分析后，再进入 APK 逆向。',
            prerequisite_reason='做 Android APK 逆向前，建议先掌握 ARM 汇编分析。',
            sort_order=20,
        )
        add_bidirectional_same_topic(
            40,
            41,
            strength=4,
            sort_order=100,
            reason='同属逆向分析训练链。',
        )
        add_bidirectional_same_topic(
            41,
            42,
            strength=4,
            sort_order=110,
            reason='同属逆向分析训练链。',
        )

        # 取证训练链
        add_progression_pair(
            45,
            43,
            progression_reason='先做日志分析，再进入内存取证。',
            prerequisite_reason='做内存取证前，建议先完成日志分析。',
            sort_order=10,
        )
        add_progression_pair(
            43,
            44,
            progression_reason='内存取证之后，继续挑战磁盘取证。',
            prerequisite_reason='做磁盘取证前，建议先掌握内存取证。',
            sort_order=20,
        )
        add_bidirectional_same_topic(
            45,
            43,
            strength=4,
            sort_order=100,
            reason='同属数字取证训练链。',
        )
        add_bidirectional_same_topic(
            43,
            44,
            strength=4,
            sort_order=110,
            reason='同属数字取证训练链。',
        )

        # 常见重复/相似题
        add_bidirectional_similar(23, 30, sort_order=10, reason='同为 Base64 编码练习，适合对照巩固。')
        add_bidirectional_similar(24, 31, sort_order=20, reason='同为凯撒密码练习，适合对照巩固。')
        add_bidirectional_similar(25, 36, sort_order=30, reason='同为二维码解码练习，适合对照巩固。')

        total = ChallengeRelation.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'Challenge relations initialized: created={stats["created"]}, '
            f'updated={stats["updated"]}, unchanged={stats["unchanged"]}, total={total}'
        ))

        if not options['skip_rebuild_packs']:
            self.stdout.write('Rebuilding knowledge packs to include explicit relations...')
            RebuildKnowledgePacksCommand().handle()
