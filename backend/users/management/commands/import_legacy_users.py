"""Import legacy users from a SQLite database without changing passwords."""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime


@dataclass(frozen=True)
class ImportSummary:
    """Summary for legacy user import."""

    created: int = 0
    updated: int = 0
    skipped: int = 0


class Command(BaseCommand):
    """Copy legacy users into the active Django database."""

    help = (
        'Import users_ctfuser rows from a legacy SQLite database into the '
        'currently configured Django database. Password hashes are preserved.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--sqlite-path',
            default='db.sqlite3',
            help='Path to the legacy SQLite database, relative to the current directory.',
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

        rows = self._read_users(sqlite_path)
        self.stdout.write(self.style.SUCCESS(f'Legacy users loaded: {len(rows)}'))
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry run only; no users were written.'))
            return

        with transaction.atomic():
            summary = self._import_users(rows)

        self.stdout.write(self.style.SUCCESS(
            f'Users imported: {summary.created} created, '
            f'{summary.updated} updated, {summary.skipped} skipped'
        ))

    def _resolve_sqlite_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return Path.cwd() / path

    def _read_users(self, sqlite_path: Path):
        connection = sqlite3.connect(sqlite_path)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.execute(
                "select 1 from sqlite_master where type = 'table' and name = ?",
                ['users_ctfuser'],
            )
            if cursor.fetchone() is None:
                raise CommandError('Legacy table not found: users_ctfuser')
            cursor = connection.execute('select * from users_ctfuser order by id')
            return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _import_users(self, rows) -> ImportSummary:
        User = get_user_model()
        created = 0
        updated = 0
        skipped = 0
        for row in rows:
            username = (row.get('username') or '').strip()
            password = row.get('password') or ''
            if not username or not password:
                skipped += 1
                continue

            defaults = self._build_defaults(row)
            user, was_created = User.objects.update_or_create(
                username=username,
                defaults=defaults,
            )
            self._restore_timestamps(
                user,
                {
                    'created_at': row.get('created_at'),
                    'updated_at': row.get('updated_at'),
                },
            )
            created += int(was_created)
            updated += int(not was_created)
        return ImportSummary(created=created, updated=updated, skipped=skipped)

    def _build_defaults(self, row: Dict[str, Any]) -> Dict[str, Any]:
        role = row.get('role') or ('admin' if row.get('is_superuser') else 'student')
        return {
            'password': row.get('password') or '',
            'last_login': self._parse_datetime(row.get('last_login')),
            'is_superuser': bool(row.get('is_superuser')),
            'first_name': row.get('first_name') or '',
            'last_name': row.get('last_name') or '',
            'email': row.get('email') or '',
            'is_staff': bool(row.get('is_staff')),
            'is_active': bool(row.get('is_active')),
            'date_joined': self._parse_datetime(row.get('date_joined')) or timezone.now(),
            'nickname': row.get('nickname') or '',
            'role': role,
            'score': row.get('score') or 0,
            'points': row.get('points') or 0,
            'bio': row.get('bio') or '',
            'avatar': row.get('avatar') or '',
            'team': row.get('team') or '',
            'class_name': row.get('class_name') or '',
            'student_id': row.get('student_id') or '',
            'enrollment_year': row.get('enrollment_year'),
        }

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
