"""Management command: ingest a file or directory into the shared RAG store."""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from rag_ingestion.services import IngestionService


class Command(BaseCommand):
    help = 'Ingest a document file or a directory of documents into the RAG store.'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to a file or a directory of files.')
        parser.add_argument('--actor', default='', help='Username recorded as uploader/audit actor.')
        parser.add_argument('--visibility', default='internal',
                            choices=['staff', 'internal', 'learner'],
                            help='Who may retrieve the ingested content.')
        parser.add_argument('--reingest', action='store_true',
                            help='Re-ingest even if identical content already exists.')

    def handle(self, *args, **options):
        root = Path(options['path'])
        if not root.exists():
            raise CommandError(f'Path does not exist: {root}')

        actor = self._resolve_actor(options.get('actor'))
        files = sorted(p for p in ([root] if root.is_file() else root.rglob('*')) if p.is_file())
        if not files:
            self.stdout.write(self.style.WARNING('No files found to ingest.'))
            return

        service = IngestionService()
        completed = 0
        failed = 0
        for file_path in files:
            try:
                data = file_path.read_bytes()
            except OSError as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f'Read failed: {file_path} ({exc})'))
                continue
            document = service.ingest_bytes(
                data=data,
                filename=file_path.name,
                title=file_path.stem,
                visibility=options['visibility'],
                uploaded_by=actor,
                reingest=options['reingest'],
            )
            if document.status == 'completed':
                completed += 1
                self.stdout.write(self.style.SUCCESS(
                    f'Ingested {file_path.name}: {document.embedded_count} chunks '
                    f'(parser={document.parser})'
                ))
            else:
                failed += 1
                self.stdout.write(self.style.ERROR(
                    f'Failed {file_path.name}: {document.error_message}'
                ))
        self.stdout.write(self.style.SUCCESS(
            f'RAG ingestion done: {completed} completed, {failed} failed.'
        ))

    def _resolve_actor(self, username):
        if not username:
            return None
        User = get_user_model()
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError(f'Actor user not found: {username}') from exc
