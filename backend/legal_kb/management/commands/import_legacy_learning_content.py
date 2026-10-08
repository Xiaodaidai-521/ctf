"""Import legacy learning articles and resources from a SQLite database."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from articles.models import Article, Category as ArticleCategory
from resources.models import Resource


@dataclass(frozen=True)
class ImportSummary:
    """Summary for one imported legacy table."""

    created: int = 0
    updated: int = 0
    skipped: int = 0


class Command(BaseCommand):
    """Copy legacy article/resource data into the active Django database."""

    help = (
        'Import articles, article categories, and learning resources from a legacy '
        'SQLite database into the currently configured Django database.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--sqlite-path',
            default='db.sqlite3',
            help='Path to the legacy SQLite database, relative to BASE_DIR by default.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate source data and print counts without writing records.',
        )

    def handle(self, *args, **options):
        sqlite_path = self._resolve_sqlite_path(options['sqlite_path'])
        if not sqlite_path.exists():
            raise CommandError(f'Legacy SQLite database not found: {sqlite_path}')

        source = self._read_source(sqlite_path)
        self.stdout.write(self.style.SUCCESS(
            'Legacy source loaded: '
            f'{len(source["categories"])} article categories, '
            f'{len(source["articles"])} articles, '
            f'{len(source["resources"])} resources'
        ))

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry run only; no records were written.'))
            return

        with transaction.atomic():
            import_user = self._get_import_user()
            category_map = self._import_categories(source['categories'])
            articles = self._import_articles(source['articles'], category_map, import_user)
            resources = self._import_resources(source['resources'], import_user)

        self.stdout.write(self.style.SUCCESS(
            f'Article categories imported: {len(category_map)} total mapped'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'Articles imported: {articles.created} created, '
            f'{articles.updated} updated, {articles.skipped} skipped'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'Resources imported: {resources.created} created, '
            f'{resources.updated} updated, {resources.skipped} skipped'
        ))

    def _resolve_sqlite_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return Path.cwd() / path

    def _read_source(self, sqlite_path: Path) -> Dict[str, Iterable[Dict[str, Any]]]:
        connection = sqlite3.connect(sqlite_path)
        connection.row_factory = sqlite3.Row
        try:
            return {
                'categories': self._fetch_all(connection, 'articles_category'),
                'articles': self._fetch_all(connection, 'articles_article'),
                'resources': self._fetch_all(connection, 'resources_resource'),
            }
        finally:
            connection.close()

    def _fetch_all(self, connection: sqlite3.Connection, table_name: str):
        if not self._table_exists(connection, table_name):
            raise CommandError(f'Legacy table not found: {table_name}')
        cursor = connection.execute(f'select * from "{table_name}" order by id')
        return [dict(row) for row in cursor.fetchall()]

    def _table_exists(self, connection: sqlite3.Connection, table_name: str) -> bool:
        cursor = connection.execute(
            "select 1 from sqlite_master where type = 'table' and name = ?",
            [table_name],
        )
        return cursor.fetchone() is not None

    def _get_import_user(self):
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username='legacy_import',
            defaults={
                'email': 'legacy-import@example.invalid',
                'nickname': 'Legacy Import',
                'role': 'teacher',
                'is_active': False,
            },
        )
        if user.has_usable_password():
            user.set_unusable_password()
            user.save(update_fields=['password'])
        return user

    def _import_categories(self, rows):
        category_map = {}
        for row in rows:
            category, _ = ArticleCategory.objects.update_or_create(
                name=row['name'],
                defaults={
                    'description': row.get('description') or '',
                    'icon': row.get('icon') or '',
                    'order': row.get('order') or 0,
                },
            )
            self._restore_timestamps(
                category,
                {
                    'created_at': row.get('created_at'),
                },
            )
            category_map[row['id']] = category
        return category_map

    def _import_articles(self, rows, category_map, import_user) -> ImportSummary:
        created = 0
        updated = 0
        skipped = 0
        for row in rows:
            title = (row.get('title') or '').strip()
            content = row.get('content') or ''
            if not title or not content.strip():
                skipped += 1
                continue
            category = category_map.get(row.get('category_id'))
            article, was_created = Article.objects.update_or_create(
                title=title,
                defaults={
                    'content': content,
                    'author': import_user,
                    'category': category,
                    'status': row.get('status') or 'pending',
                    'tags': row.get('tags') or '',
                    'cover': row.get('cover') or '',
                    'summary': row.get('summary') or '',
                    'view_count': row.get('view_count') or 0,
                    'like_count': row.get('like_count') or 0,
                    'comment_count': row.get('comment_count') or 0,
                    'collect_count': row.get('collect_count') or 0,
                    'is_recommend': bool(row.get('is_recommend')),
                    'is_top': bool(row.get('is_top')),
                    'published_at': self._parse_datetime(row.get('published_at')),
                },
            )
            self._restore_timestamps(
                article,
                {
                    'created_at': row.get('created_at'),
                    'updated_at': row.get('updated_at'),
                },
            )
            created += int(was_created)
            updated += int(not was_created)
        return ImportSummary(created=created, updated=updated, skipped=skipped)

    def _import_resources(self, rows, import_user) -> ImportSummary:
        created = 0
        updated = 0
        skipped = 0
        for row in rows:
            title = (row.get('title') or '').strip()
            if not title:
                skipped += 1
                continue
            resource, was_created = Resource.objects.update_or_create(
                title=title,
                description=row.get('description') or '',
                category=row.get('category') or '',
                resource_type=row.get('resource_type') or 'document',
                defaults={
                    'file': row.get('file') or '',
                    'file_size': row.get('file_size') or 0,
                    'cover_image': row.get('cover_image') or '',
                    'tags': row.get('tags') or '',
                    'status': row.get('status') or 'pending',
                    'uploader': import_user,
                    'reviewer': None,
                    'review_comment': row.get('review_comment') or '',
                    'view_count': row.get('view_count') or 0,
                    'download_count': row.get('download_count') or 0,
                    'reviewed_at': self._parse_datetime(row.get('reviewed_at')),
                },
            )
            self._restore_timestamps(
                resource,
                {
                    'created_at': row.get('created_at'),
                    'updated_at': row.get('updated_at'),
                },
            )
            created += int(was_created)
            updated += int(not was_created)
        return ImportSummary(created=created, updated=updated, skipped=skipped)

    def _parse_datetime(self, value: Optional[str]):
        if not value:
            return None
        parsed = parse_datetime(value)
        if parsed is None:
            return None
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    def _restore_timestamps(self, instance, values: Dict[str, Optional[str]]):
        update_values = {
            field: self._parse_datetime(value)
            for field, value in values.items()
            if value
        }
        update_values = {field: value for field, value in update_values.items() if value}
        if update_values:
            instance.__class__.objects.filter(pk=instance.pk).update(**update_values)
