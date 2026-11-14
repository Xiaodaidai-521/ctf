"""Validate and import an already bundled corpus; never collect external content."""

import hashlib
import json
from datetime import date
from pathlib import Path, PurePosixPath

from django.contrib.auth import get_user_model
from django.db import transaction

from ctf_backend.security_bootstrap import assemble_rag
from rag_ingestion.adapters.embedder_legalkb import LegalKbEmbedder
from rag_ingestion.models import DocumentSource
from rag_ingestion.services import IngestionService

from legal_kb.models import LegalDocument, LegalKnowledgeEmbedding
from legal_kb.permissions import IsLegalKbAdmin
from legal_kb.services.chunking_service import TextChunk
from legal_kb.services.embedding_service import EmbeddingService
from legal_kb.services.hashing import sha256_text
from legal_kb.services.ingestion_service import LegalKbIngestionService


def digest(content):
    return hashlib.sha256(content).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def validate_corpus(root):
    """Reject incomplete/tampered bundles before any database changes."""
    root = Path(root).resolve()
    bundles = {}
    for name in ('owasp', 'chinese_laws'):
        bundle = root / name
        report = json.loads((bundle / 'quality_report.json').read_text(encoding='utf-8'))
        content = (bundle / 'documents.jsonl').read_bytes()
        if digest(content) != report['documents_sha256']:
            raise ValueError('Corpus JSONL hash mismatch')
        documents = read_rows(bundle / 'documents.jsonl')
        if len(documents) != report['accepted'] or not documents:
            raise ValueError('Corpus document count mismatch')
        ids = set()
        paths = set()
        for record in documents:
            if record['id'] in ids:
                raise ValueError('Duplicate corpus document id')
            ids.add(record['id'])
            relative = PurePosixPath(record['markdown_path'])
            if relative.is_absolute() or '..' in relative.parts or '\\' in record['markdown_path'] or ':' in record['markdown_path']:
                raise ValueError('Invalid corpus Markdown path')
            path = (bundle / str(relative)).resolve()
            path.relative_to(bundle.resolve())
            paths.add(path)
            body = path.read_bytes()
            if digest(body) != record['source_hash'] or body != record['source_snapshot'].encode('utf-8'):
                raise ValueError('Corpus Markdown hash mismatch')
            license_id = record['source_id'] if name == 'owasp' else 'cn-official-laws'
            if not all(char.isalnum() or char in '-.' for char in license_id):
                raise ValueError('Invalid corpus source id')
            if digest((bundle / 'licenses' / (license_id + '.txt')).read_bytes()) != record['license_sha256']:
                raise ValueError('Corpus license hash mismatch')
        if paths != {path.resolve() for path in (bundle / 'markdown').glob('*.md')}:
            raise ValueError('Unexpected or missing corpus Markdown files')
        bundles[name] = documents
    bundle = root / 'chinese_laws'
    report = json.loads((bundle / 'quality_report.json').read_text(encoding='utf-8'))
    if digest((bundle / 'clauses.jsonl').read_bytes()) != report['clauses_sha256']:
        raise ValueError('Corpus clauses hash mismatch')
    clauses = read_rows(bundle / 'clauses.jsonl')
    if len(clauses) != report['article_count']:
        raise ValueError('Corpus article count mismatch')
    known_ids = {record['id'] for record in bundles['chinese_laws']}
    if any(clause['document_id'] not in known_ids for clause in clauses):
        raise ValueError('Unknown corpus clause document')
    for record in bundles['chinese_laws']:
        date.fromisoformat(record['effective_date'])
        date.fromisoformat(record['published_date'])
        selected = [clause for clause in clauses if clause['document_id'] == record['id']]
        start, end = record['article_range']
        if [clause['article_number'] for clause in selected] != list(range(start, end + 1)):
            raise ValueError('Corpus article sequence mismatch')
        if len(selected) != record['article_count']:
            raise ValueError('Corpus per-document article count mismatch')
        for clause in selected:
            if digest(clause['text'].encode('utf-8')) != clause['text_hash'] or clause['text'] not in record['source_snapshot']:
                raise ValueError('Corpus clause differs from the full text')
    bundles['clauses'] = clauses
    return bundles


def source_metadata(record):
    # Body belongs in the existing document/chunk store, not duplicated in metadata.
    metadata = {key: value for key, value in record.items() if key != 'source_snapshot'}
    metadata['corpus_id'] = record['id']
    metadata['corpus_bundle'] = 'harvested-2026-11-12'
    return metadata


def import_corpus(root, actor_id, *, local_index=False, progress=None):
    corpus = validate_corpus(root)
    actor = get_user_model().objects.get(pk=actor_id)
    if not IsLegalKbAdmin.allows(actor):
        raise PermissionError('An existing active administrator is required')
    embedding = EmbeddingService(local_only=True) if local_index else None
    ingestion = IngestionService(pipeline=assemble_rag(embedder=LegalKbEmbedder(embedding))) if embedding else IngestionService()
    legal_ingestion = LegalKbIngestionService(embedding_service=embedding)
    result = {'owasp_documents': [], 'legal_documents': [], 'legal_articles': 0,
              'created_documents': 0, 'updated_legal_documents': 0, 'skipped_documents': 0,
              'index_mode': 'deterministic' if local_index else 'configured',
              'course_materials_published': 0}
    with transaction.atomic():
        for index, record in enumerate(corpus['owasp'], start=1):
            content = record['source_snapshot'].encode('utf-8')
            existing = DocumentSource.objects.filter(source_hash=digest(content)).first()
            if existing and existing.status == 'completed':
                document = existing
                result['skipped_documents'] += 1
            else:
                document = ingestion.ingest_bytes(data=content,
                    filename=PurePosixPath(record['markdown_path']).name, mime='text/markdown',
                    title=record['title'], metadata=source_metadata(record), uploaded_by=actor,
                    visibility=existing.visibility if existing else 'internal')
                if document.status != 'completed':
                    raise RuntimeError('Corpus document ingestion failed; batch rolled back')
                result['created_documents'] += int(existing is None)
            result['owasp_documents'].append({'corpus_id': record['id'], 'document_id': document.pk,
                                             'chunks': document.embedded_count})
            if progress and index % 25 == 0:
                progress(f'OWASP documents indexed: {index}/{len(corpus["owasp"])}')
        for record in corpus['chinese_laws']:
            matching = LegalDocument.objects.filter(source_url=record['source_url'])
            if record['scope'] == 'excerpt':
                matching = matching.filter(title__contains='节选')
            else:
                matching = matching.filter(title=record['original_title'])
            if matching.count() > 1:
                raise ValueError('Multiple existing legal documents match one corpus version')
            existing = matching.first()
            content_hash = sha256_text(f'{record["title"]}|{record["source_url"]}|{record["source_snapshot"]}')
            selected = [clause for clause in corpus['clauses'] if clause['document_id'] == record['id']]
            unchanged = (existing and existing.source_hash == content_hash
                         and existing.metadata.get('corpus_id') == record['id']
                         and existing.clauses.count() == len(selected)
                         and LegalKnowledgeEmbedding.objects.filter(source_type='legal_clause',
                             metadata__document_id=existing.pk).count() == len(selected))
            if unchanged:
                document = existing
                result['skipped_documents'] += 1
            else:
                defaults = {'title': record['title'], 'document_type': record['document_type'],
                    'jurisdiction': 'CN', 'issuing_authority': record['publisher'],
                    'version_label': record['version_label'], 'source_url': record['source_url'],
                    'source_name': record['source_name'], 'source_hash': content_hash,
                    'full_text': record['source_snapshot'], 'status': existing.status if existing else 'active',
                    'effective_date': record['effective_date'], 'published_date': record['published_date'],
                    'metadata': {**(existing.metadata if existing else {}), **source_metadata(record)}}
                if existing:
                    for key, value in defaults.items():
                        setattr(existing, key, value)
                    existing.save()
                    document = existing
                    result['updated_legal_documents'] += 1
                else:
                    document = LegalDocument.objects.create(created_by=actor, **defaults)
                    result['created_documents'] += 1
                chunks = [TextChunk(clause_key=clause['article_label'], title=clause['article_label'],
                    text=clause['text'], order=order, article_number=clause['article_label'],
                    chapter=clause.get('chapter', '')) for order, clause in enumerate(selected, start=1)]
                legal_ingestion.ingest_document(document, actor=actor, source_chunks=chunks)
            result['legal_articles'] += len(selected)
            result['legal_documents'].append({'corpus_id': record['id'], 'document_id': document.pk,
                                             'articles': len(selected)})
            if progress:
                progress(f'Official legal document indexed: {record["title"]}')
    result['total_documents'] = len(result['owasp_documents']) + len(result['legal_documents'])
    result['total_index_chunks'] = sum(item['chunks'] for item in result['owasp_documents']) + result['legal_articles']
    return result
