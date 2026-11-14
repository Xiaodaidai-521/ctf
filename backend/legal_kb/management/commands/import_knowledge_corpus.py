"""Offline import of the bundled, audited knowledge corpus into the existing KB."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from legal_kb.services.corpus_import import import_corpus, validate_corpus


class Command(BaseCommand):
    help = 'Import audited OWASP documents and official legal clauses; never crawl or publish course materials.'

    def add_arguments(self, parser):
        parser.add_argument('--path', type=Path, default=settings.BASE_DIR / 'data' / 'knowledge_corpus')
        parser.add_argument('--actor', type=int, help='Existing active administrator user ID.')
        parser.add_argument('--local-index', action='store_true', help='Explicit deterministic offline index; no remote embedding calls.')
        parser.add_argument('--validate-only', action='store_true', help='Check corpus files without database writes.')
        parser.add_argument('--report', type=Path, help='Write import counts and document IDs to JSON.')

    def handle(self, *args, **options):
        try:
            if options['validate_only']:
                corpus = validate_corpus(options['path'])
                self.stdout.write(f'Validated {len(corpus["owasp"])} OWASP documents, '
                                  f'{len(corpus["chinese_laws"])} legal documents, {len(corpus["clauses"])} articles')
                return
            if not options['actor']:
                raise CommandError('--actor must identify an existing active administrator')
            result = import_corpus(options['path'], options['actor'], local_index=options['local_index'],
                                   progress=self.stdout.write)
        except CommandError:
            raise
        except Exception as exc:
            # Public source text and credentials should not appear in failure logs.
            raise CommandError(f'Knowledge corpus import failed ({type(exc).__name__}); batch rolled back.') from exc
        if options['report']:
            options['report'].parent.mkdir(parents=True, exist_ok=True)
            options['report'].write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        self.stdout.write(self.style.SUCCESS(
            f'Imported {result["total_documents"]} documents / {result["total_index_chunks"]} index chunks; '
            f'created={result["created_documents"]}, updated_laws={result["updated_legal_documents"]}, '
            f'skipped={result["skipped_documents"]}, index_mode={result["index_mode"]}'))
