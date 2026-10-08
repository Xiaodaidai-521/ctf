"""Prepare legal KB documents and platform embeddings."""

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from challenges.models import Category as ChallengeCategory, Challenge
from legal_kb.models import LegalDocument
from legal_kb.services.hashing import sha256_text
from legal_kb.services.ingestion_service import LegalKbIngestionService
from legal_kb.services.platform_indexing_service import PlatformContentIndexingService


SQL_EXERCISE_SEEDS = [
    {
        'title': 'SQL Injection Basics',
        'description': (
            'A login form concatenates user input into a SQL WHERE clause. '
            'Analyze why parameterized queries are required and identify the injection point.'
        ),
        'difficulty': 'easy',
        'score': 100,
        'flag': 'flag{sql_injection_basics}',
        'hint': 'Focus on quote closure, boolean conditions, and SQL comments.',
        'docker_image': 'ctf-platform/sql-injection-basics:latest',
    },
    {
        'title': 'SQL UNION Query Practice',
        'description': (
            'A product search page exposes a UNION-based SQL injection path. '
            'Determine the column count and retrieve hidden training data.'
        ),
        'difficulty': 'medium',
        'score': 200,
        'flag': 'flag{sql_union_query_practice}',
        'hint': 'Start with ORDER BY or UNION NULL probes, then align text columns.',
        'docker_image': 'ctf-platform/sql-union-query:latest',
    },
    {
        'title': 'Blind SQL Injection Timing',
        'description': (
            'The target does not show database errors, but response latency changes when SQL predicates are true. '
            'Use timing behavior to reason about blind SQL injection and defensive logging.'
        ),
        'difficulty': 'hard',
        'score': 300,
        'flag': 'flag{blind_sql_timing}',
        'hint': 'Compare true and false predicates with database-specific sleep functions.',
        'docker_image': 'ctf-platform/blind-sql-timing:latest',
    },
]


class Command(BaseCommand):
    """Import legal documents and vectorize platform content."""

    help = (
        'Import legal documents from JSON files and vectorize challenges, '
        'articles, and resources into the unified legal KB embedding table.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--laws-dir',
            default='',
            help='Directory containing legal document JSON files.',
        )
        parser.add_argument(
            '--actor',
            default='',
            help='Username used as created_by/audit actor.',
        )
        parser.add_argument(
            '--laws-only',
            action='store_true',
            help='Only import and ingest legal documents.',
        )
        parser.add_argument(
            '--platform-only',
            action='store_true',
            help='Only vectorize platform challenges/articles/resources.',
        )
        parser.add_argument(
            '--seed-sql-exercises',
            action='store_true',
            help='Create or update built-in SQL injection exercises before platform indexing.',
        )
        parser.add_argument(
            '--require-postgres',
            action='store_true',
            help='Abort unless Django is connected to PostgreSQL.',
        )

    def handle(self, *args, **options):
        if options['laws_only'] and options['platform_only']:
            raise CommandError('--laws-only and --platform-only cannot be used together.')
        if options['require_postgres'] and connection.vendor != 'postgresql':
            raise CommandError(
                f'PostgreSQL is required, but current database vendor is {connection.vendor}. '
                'Set DATABASE_URL to a postgres:// URL and rerun migrate.'
            )
        self._ensure_migrated()

        actor = self._resolve_actor(options.get('actor'))
        if not options['platform_only']:
            self._import_laws(options.get('laws_dir'), actor=actor)
        if options['seed_sql_exercises']:
            self._seed_sql_exercises()
        if not options['laws_only']:
            self._index_platform(actor=actor)

    def _ensure_migrated(self):
        required_tables = {
            LegalDocument._meta.db_table,
            'legal_kb_legalknowledgeembedding',
        }
        existing_tables = set(connection.introspection.table_names())
        missing = sorted(required_tables - existing_tables)
        if missing:
            raise CommandError(
                'Legal KB tables are missing. Run "python manage.py migrate" first. '
                f'Missing tables: {", ".join(missing)}'
            )

    def _resolve_actor(self, username):
        if not username:
            return None
        User = get_user_model()
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f'Actor user not found: {username}') from exc

    def _import_laws(self, laws_dir, *, actor=None):
        if not laws_dir:
            self.stdout.write(self.style.WARNING('No --laws-dir provided, skipped legal document import.'))
            return
        directory = Path(laws_dir)
        if not directory.exists() or not directory.is_dir():
            raise CommandError(f'Laws directory does not exist: {directory}')

        imported = 0
        for file_path in sorted(directory.glob('*.json')):
            payload = json.loads(file_path.read_text(encoding='utf-8-sig'))
            full_text = payload.get('full_text') or payload.get('content') or ''
            title = payload.get('title') or file_path.stem
            metadata = payload.get('metadata') or {}
            if payload.get('source_name') == '国家法律法规数据库' and not metadata.get('target_key'):
                self.stdout.write(self.style.WARNING(
                    f'Skipped non-standard official cache without target_key: {file_path.name}'
                ))
                continue
            if not full_text.strip():
                self.stdout.write(self.style.WARNING(f'Skipped empty legal document: {file_path.name}'))
                continue
            document, _ = LegalDocument.objects.update_or_create(
                source_hash=sha256_text(f'{title}|{payload.get("source_url", "")}|{full_text}'),
                defaults={
                    'title': title,
                    'document_type': payload.get('document_type', 'law'),
                    'jurisdiction': payload.get('jurisdiction', 'CN'),
                    'issuing_authority': payload.get('issuing_authority', ''),
                    'version_label': payload.get('version_label', ''),
                    'source_url': payload.get('source_url', ''),
                    'source_name': payload.get('source_name', file_path.name),
                    'full_text': full_text,
                    'status': payload.get('status', 'active'),
                    'effective_date': payload.get('effective_date') or None,
                    'published_date': payload.get('published_date') or None,
                    'metadata': metadata,
                    'created_by': actor,
                },
            )
            LegalKbIngestionService().ingest_document(document, actor=actor)
            imported += 1
            self.stdout.write(self.style.SUCCESS(f'Imported and ingested: {document.title}'))
        self.stdout.write(self.style.SUCCESS(f'Legal documents prepared: {imported}'))

    def _index_platform(self, *, actor=None):
        results = PlatformContentIndexingService().index_all(actor=actor)
        for result in results:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Indexed {result.source_type}: '
                    f'{result.indexed_objects} objects, {result.embedded_chunks} chunks'
                )
            )

    def _seed_sql_exercises(self):
        category, _ = ChallengeCategory.objects.get_or_create(
            name='Web',
            defaults={'description': 'Web security and SQL injection exercises.'},
        )
        created = 0
        updated = 0
        for payload in SQL_EXERCISE_SEEDS:
            challenge, was_created = Challenge.objects.update_or_create(
                title=payload['title'],
                defaults={
                    'description': payload['description'],
                    'category': category,
                    'difficulty': payload['difficulty'],
                    'score': payload['score'],
                    'flag': payload['flag'],
                    'hint': payload['hint'],
                    'docker_image': payload['docker_image'],
                    'redirect_port': 80,
                    'redirect_type': 'path',
                    'is_active': True,
                },
            )
            created += int(was_created)
            updated += int(not was_created)
            self.stdout.write(self.style.SUCCESS(f'SQL exercise ready: {challenge.title}'))
        self.stdout.write(self.style.SUCCESS(f'SQL exercises seeded: {created} created, {updated} updated'))
