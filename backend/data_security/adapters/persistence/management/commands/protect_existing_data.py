"""Inventory or migrate old plaintext, retaining authenticated encrypted backups."""
import json
import os
from pathlib import Path
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from data_security.adapters.persistence import fields
from data_security.adapters.persistence.fields import ProtectedModel
from data_security.runtime.crypto import create_private_directory, get_cipher, restrict_path, sync_directory
from data_security.runtime.fields import RuntimeFieldStorage


class Command(BaseCommand):
    help = 'Inventory legacy fields; --apply encrypts them with a durable encrypted rollback copy per row.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--model', action='append', default=[], help='Optional app.Model filters')
        parser.add_argument('--files', action='store_true', help='Also migrate resource, cover and feedback files')

    def handle(self, *args, **options):
        if not isinstance(fields._adapter, RuntimeFieldStorage):
            raise CommandError('Regular runtime protection must be enabled; formal deployments use their existing migration tool.')
        models = [model for model in apps.get_models() if issubclass(model, ProtectedModel)]
        selected = {label.lower() for label in options['model']}
        if selected - {model._meta.label_lower for model in models}:
            raise CommandError('Unknown protected model')
        models = [model for model in models if not selected or model._meta.label_lower in selected]
        tables = set(connection.introspection.table_names())
        if any(model._meta.db_table not in tables for model in models):
            raise CommandError('Run manage.py migrate before protecting existing data.')
        result = {model._meta.label_lower: {'legacy': model.objects.filter(security_state='legacy-v0').count(),
                    'migrated': 0} for model in models}
        if options['apply']:
            cipher = get_cipher()
            backup_root = Path(settings.DATA_PROTECTION_ROOT) / 'migration-backups' / uuid4().hex
            create_private_directory(backup_root)
            for model in models:
                # Evaluate IDs only; rows are re-read and locked immediately before migration.
                ids = model.objects.filter(security_state='legacy-v0').values_list('pk', flat=True)
                for pk in ids.iterator(chunk_size=100):
                    with transaction.atomic():
                        obj = model.objects.select_for_update().get(pk=pk)
                        if obj.security_state != 'legacy-v0':
                            continue
                        before = {name: getattr(obj, name) for name in obj.encrypted_fields}
                        original = serializers.serialize('json', [obj]).encode('utf-8')
                        name = f'{model._meta.label_lower}-{pk}.aead'
                        encrypted = cipher.encrypt(original, 'migration-backup/v1/' + name)
                        if cipher.decrypt(encrypted, 'migration-backup/v1/' + name) != original:
                            raise CommandError('Backup verification failed')
                        path = backup_root / name
                        with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as stream:
                            restrict_path(path)
                            stream.write(encrypted)
                            stream.flush()
                            os.fsync(stream.fileno())
                        sync_directory(backup_root)
                        # Skip business save side effects such as grading or score updates.
                        ProtectedModel.save(obj, _legacy_migration=True)
                        obj.refresh_from_db()
                        for name, value in before.items():
                            expected = fields.normalize_email(value) if name == 'email' else value
                            if obj.read_protected(name) != expected or getattr(obj, name) not in ('', {}):
                                raise CommandError('Round-trip verification failed; row rolled back')
                        result[model._meta.label_lower]['migrated'] += 1
            result['backup_directory'] = str(backup_root)
        if options['files']:
            from data_security.runtime.storage import migrate_private_files
            result['files'] = migrate_private_files(apply=options['apply'])
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
