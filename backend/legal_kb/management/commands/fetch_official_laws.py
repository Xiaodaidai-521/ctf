"""Fetch official legal texts, import them, and build legal KB vectors."""

import json
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from legal_kb.models import LegalDocument
from legal_kb.services.flk_client import (
    DEFAULT_OFFICIAL_LAW_TARGETS,
    FlkClient,
    FlkClientError,
    OfficialLawTarget,
)
from legal_kb.services.hashing import sha256_text
from legal_kb.services.ingestion_service import LegalKbIngestionService


class Command(BaseCommand):
    """Fetch official laws from flk.npc.gov.cn and ingest them into Legal KB."""

    help = (
        'Fetch official laws from flk.npc.gov.cn, cache normalized JSON files, '
        'import LegalDocument rows, and vectorize legal clauses.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--cache-dir',
            default='data/legal_laws',
            help='Directory used to store fetched official legal JSON payloads.',
        )
        parser.add_argument(
            '--actor',
            default='',
            help='Username used as created_by/audit actor.',
        )
        parser.add_argument(
            '--cache-only',
            action='store_true',
            help='Fetch and cache official JSON files without importing/vectorizing.',
        )
        parser.add_argument(
            '--require-postgres',
            action='store_true',
            help='Abort unless Django is connected to PostgreSQL.',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=30,
            help='Network timeout in seconds for each FLK request.',
        )
        parser.add_argument(
            '--query',
            action='append',
            default=[],
            help='Custom law search query. Can be provided more than once.',
        )
        parser.add_argument(
            '--include-network-data-regulation',
            action='store_true',
            help='Also fetch 网络数据安全管理条例 if it is available from the official database.',
        )

    def handle(self, *args, **options):
        if options['require_postgres'] and connection.vendor != 'postgresql':
            raise CommandError(
                f'PostgreSQL is required, but current database vendor is {connection.vendor}. '
                'Set DATABASE_URL to a postgres:// URL and rerun migrate.'
            )
        self._ensure_migrated()

        actor = self._resolve_actor(options.get('actor'))
        cache_dir = Path(options['cache_dir'])
        cache_dir.mkdir(parents=True, exist_ok=True)

        client = FlkClient(timeout=options['timeout'])
        targets = self._build_targets(options)
        fetched = 0
        imported = 0

        for target in targets:
            try:
                payload = client.fetch_target(target)
            except FlkClientError as exc:
                if target.key == 'network_data_security_regulation':
                    self.stdout.write(self.style.WARNING(f'Skipped optional law: {exc}'))
                    continue
                raise CommandError(str(exc)) from exc

            fetched += 1
            output_path = cache_dir / f'{target.key}.json'
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
            self.stdout.write(self.style.SUCCESS(f'Fetched official law: {payload["title"]}'))
            self.stdout.write(f'Cached: {output_path}')

            if not options['cache_only']:
                document = self._upsert_document(payload, actor=actor)
                job = LegalKbIngestionService().ingest_document(document, actor=actor)
                imported += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Imported/vectorized: {document.title} '
                        f'({job.embedded_chunks} legal clause vectors)'
                    )
                )

        self.stdout.write(self.style.SUCCESS(f'Official laws fetched: {fetched}'))
        if options['cache_only']:
            self.stdout.write(self.style.WARNING('Cache-only mode enabled; database import was skipped.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Official laws imported and vectorized: {imported}'))

    def _ensure_migrated(self):
        existing_tables = set(connection.introspection.table_names())
        missing = sorted({LegalDocument._meta.db_table, 'legal_kb_legalknowledgeembedding'} - existing_tables)
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

    def _build_targets(self, options):
        if options['query']:
            return [
                OfficialLawTarget(
                    key=self._slugify(query),
                    search_content=query,
                    expected_title=query,
                )
                for query in options['query']
            ]

        targets = list(DEFAULT_OFFICIAL_LAW_TARGETS)
        if options['include_network_data_regulation']:
            targets.append(OfficialLawTarget(
                key='network_data_security_regulation',
                search_content='网络数据安全管理条例',
                expected_title='网络数据安全管理条例',
                document_type='regulation',
            ))
        return targets

    def _upsert_document(self, payload, *, actor=None):
        full_text = payload.get('full_text') or ''
        title = payload.get('title') or ''
        source_url = payload.get('source_url') or ''
        source_hash = sha256_text(f'{title}|{source_url}|{full_text}')
        document, _ = LegalDocument.objects.update_or_create(
            source_hash=source_hash,
            defaults={
                'title': title,
                'document_type': payload.get('document_type', 'law'),
                'jurisdiction': payload.get('jurisdiction', 'CN'),
                'issuing_authority': payload.get('issuing_authority', ''),
                'version_label': payload.get('version_label', ''),
                'source_url': source_url,
                'source_name': payload.get('source_name', '国家法律法规数据库'),
                'full_text': full_text,
                'status': payload.get('status', 'active'),
                'effective_date': payload.get('effective_date') or None,
                'published_date': payload.get('published_date') or None,
                'metadata': payload.get('metadata') or {},
                'created_by': actor,
            },
        )
        return document

    @staticmethod
    def _slugify(value):
        slug = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff]+', '-', value).strip('-')
        return slug or 'official-law'
