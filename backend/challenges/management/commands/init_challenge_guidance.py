from django.core.management.base import BaseCommand, CommandError

from articles.models import Article
from challenges.models import Challenge, ChallengeArticleRelation, ChallengeResourceRelation
from resources.models import Resource


class Command(BaseCommand):
    help = 'Initialize challenge reading guidance for community articles and resources.'

    def handle(self, *args, **options):
        challenges = {
            challenge.id: challenge
            for challenge in Challenge.objects.filter(is_active=True).select_related('category')
        }
        articles = {
            article.id: article
            for article in Article.objects.filter(status='approved')
        }
        resources = {
            resource.id: resource
            for resource in Resource.objects.filter(status='approved')
        }

        if not challenges:
            raise CommandError('No active challenges found.')

        stats = {
            'article_created': 0,
            'article_updated': 0,
            'resource_created': 0,
            'resource_updated': 0,
        }

        def require_challenge(challenge_id):
            challenge = challenges.get(challenge_id)
            if not challenge:
                raise CommandError(f'Challenge {challenge_id} does not exist or is inactive.')
            return challenge

        def require_article(article_id):
            article = articles.get(article_id)
            if not article:
                raise CommandError(f'Article {article_id} does not exist or is not approved.')
            return article

        def require_resource(resource_id):
            resource = resources.get(resource_id)
            if not resource:
                raise CommandError(f'Resource {resource_id} does not exist or is not approved.')
            return resource

        def upsert_article_relation(
            challenge_id,
            article_id,
            relation_type,
            *,
            reason='',
            sort_order=0,
            is_active=True,
        ):
            challenge = require_challenge(challenge_id)
            article = require_article(article_id)
            _, created = ChallengeArticleRelation.objects.update_or_create(
                challenge=challenge,
                article=article,
                relation_type=relation_type,
                defaults={
                    'reason': reason,
                    'sort_order': sort_order,
                    'is_active': is_active,
                },
            )
            if created:
                stats['article_created'] += 1
            else:
                stats['article_updated'] += 1

        def upsert_resource_relation(
            challenge_id,
            resource_id,
            relation_type,
            *,
            reason='',
            sort_order=0,
            is_active=True,
        ):
            challenge = require_challenge(challenge_id)
            resource = require_resource(resource_id)
            _, created = ChallengeResourceRelation.objects.update_or_create(
                challenge=challenge,
                resource=resource,
                relation_type=relation_type,
                defaults={
                    'reason': reason,
                    'sort_order': sort_order,
                    'is_active': is_active,
                },
            )
            if created:
                stats['resource_created'] += 1
            else:
                stats['resource_updated'] += 1

        # Web
        for challenge_id in [26, 27, 28, 29, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60]:
            upsert_resource_relation(
                challenge_id,
                5,
                'recommended_reading',
                reason='适合作为 Web 安全基础阅读入口。',
                sort_order=10,
            )

        for challenge_id in [26, 51, 52, 57, 58, 59, 60]:
            upsert_resource_relation(
                challenge_id,
                10,
                'background',
                reason='适合在 SQL 注入专题练习后继续阅读攻击与防御思路。',
                sort_order=20,
            )

        upsert_resource_relation(27, 9, 'practice_extension', reason='XSS 题目适合搭配 XSS 原理与防护资料继续巩固。', sort_order=20)

        # Crypto
        for challenge_id in [23, 24, 30, 31, 32, 33]:
            upsert_resource_relation(
                challenge_id,
                15,
                'recommended_reading',
                reason='适合作为密码学方向的补充阅读材料。',
                sort_order=10,
            )
        upsert_resource_relation(32, 11, 'practice_extension', reason='RSA 解密题适合继续阅读 RSA 算法详解。', sort_order=20)
        upsert_resource_relation(32, 1, 'practice_extension', reason='可作为 RSA 题目的延伸参考资料。', sort_order=30)

        # Pwn
        for challenge_id in [37, 38, 39]:
            upsert_resource_relation(
                challenge_id,
                21,
                'recommended_reading',
                reason='适合作为二进制利用方向的补充资源。',
                sort_order=10,
            )
        upsert_resource_relation(37, 14, 'background', reason='缓冲区溢出入门后可继续阅读溢出攻击资料。', sort_order=20)

        # Reverse
        for challenge_id in [40, 41, 42]:
            upsert_resource_relation(
                challenge_id,
                19,
                'recommended_reading',
                reason='适合作为逆向方向的拓展阅读材料。',
                sort_order=10,
            )
        upsert_resource_relation(41, 17, 'background', reason='ARM/逆向题目可继续扩展到内核安全和底层分析。', sort_order=20)

        # Forensics
        upsert_article_relation(43, 5, 'background', reason='内存取证前后都适合搭配日志分析与安全监控阅读。', sort_order=10)
        upsert_article_relation(44, 5, 'background', reason='磁盘取证适合结合日志分析与监控文章一起理解。', sort_order=10)
        upsert_article_relation(45, 5, 'recommended_reading', reason='日志分析题目可直接配套日志分析与安全监控文章。', sort_order=10)
        upsert_article_relation(43, 4, 'practice_extension', reason='取证类题目适合进一步阅读安全事件响应流程。', sort_order=20)
        upsert_article_relation(44, 4, 'practice_extension', reason='取证类题目适合进一步阅读安全事件响应流程。', sort_order=20)
        upsert_article_relation(45, 4, 'practice_extension', reason='日志分析后适合阅读完整的应急响应流程。', sort_order=20)

        # General security articles
        for challenge_id in [26, 27, 28, 29, 46, 47, 48, 49, 50, 53]:
            upsert_article_relation(
                challenge_id,
                8,
                'official_reference',
                reason='适合从安全开发和防护视角补充理解漏洞成因。',
                sort_order=100,
            )
        for challenge_id in [26, 27, 28, 29, 46, 47, 48, 49, 50, 53]:
            upsert_article_relation(
                challenge_id,
                2,
                'background',
                reason='适合结合网络边界与规则配置理解攻击面。',
                sort_order=110,
            )

        article_total = ChallengeArticleRelation.objects.count()
        resource_total = ChallengeResourceRelation.objects.count()
        self.stdout.write(self.style.SUCCESS(
            'Challenge guidance initialized: '
            f'article_created={stats["article_created"]}, '
            f'article_updated={stats["article_updated"]}, '
            f'resource_created={stats["resource_created"]}, '
            f'resource_updated={stats["resource_updated"]}, '
            f'article_total={article_total}, '
            f'resource_total={resource_total}'
        ))
