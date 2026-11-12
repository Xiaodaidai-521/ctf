"""Evaluate the merged corpus on a disposable snapshot of the SQLite database.

Run from backend: python scripts/evaluate_merged_knowledge.py
The source database is opened read-only. Retrieval logs and API audit writes
exist only in the temporary copy. No remote embeddings or LLM calls are made.
The embedding selection mirrors non-secret operational settings in root .env;
SQLite retrieval itself uses the current portable implementation unchanged.
"""

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT.parent / 'database/db.sqlite3')
    parser.add_argument('--baseline', type=Path, help='Optional pre-merge SQLite backup, read-only inventory comparison only.')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/knowledge-retrieval-evaluation.json')
    args = parser.parse_args()
    baseline = None
    if args.baseline:
        with closing(sqlite3.connect(args.baseline.resolve().as_uri() + '?mode=ro', uri=True)) as source:
            counts = dict(source.execute('SELECT source_type, count(*) FROM legal_kb_legalknowledgeembedding GROUP BY source_type'))
        baseline = {'database': str(args.baseline.resolve()), 'index_counts': counts,
                    'total_chunks': sum(counts.values()),
                    'scope': 'inventory comparison only; baseline query ranking was not evaluated'}
    if os.environ.get('DATA_SECURITY_CONFIG'):
        parser.error('Use a separate local process; formal bootstrap is outside this SQLite evaluation.')
    from dotenv import dotenv_values
    operational = dotenv_values(ROOT / '.env')
    for name in ('EMBEDDING_PROVIDER', 'EMBEDDING_MODEL', 'EMBEDDING_DIMENSION'):
        if operational.get(name) is not None:
            os.environ.setdefault(name, operational[name])
    os.environ.setdefault('SECRET_KEY', 'disposable-knowledge-evaluation-framework-key-20261112')
    os.environ['DATABASE_BACKEND'] = 'sqlite'
    os.environ['DEBUG'] = 'true'
    os.environ['ALLOWED_HOSTS'] = 'localhost,127.0.0.1,testserver'
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
    with tempfile.TemporaryDirectory(prefix='knowledge-evaluation-') as tmp:
        snapshot = Path(tmp) / 'snapshot.sqlite3'
        with closing(sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
        os.environ['SQLITE_DATABASE_PATH'] = str(snapshot)
        import django
        django.setup()
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import AnonymousUser
        from django.db import connections
        from django.test import override_settings
        from rest_framework.test import APIClient
        from legal_kb.models import LegalClause, LegalDocument, LegalKnowledgeEmbedding
        from legal_kb.services.corpus_import import validate_corpus
        from legal_kb.services.knowledge_retrieval_service import SafeKnowledgeRetrievalService
        from legal_kb.services.retrieval_service import LegalRetrievalService
        from legal_kb.services.visibility import apply_embedding_visibility
        from rag_ingestion.models import DocumentSource

        try:
            corpus = validate_corpus(ROOT / 'backend/data/knowledge_corpus')
            mapping = json.loads((ROOT / 'artifacts/knowledge-import.json').read_text(encoding='utf-8'))
            docs = {doc.pk: doc for doc in DocumentSource.objects.all()}
            laws = {doc.pk: doc for doc in LegalDocument.objects.all()}
            clauses = {clause.pk: clause for clause in LegalClause.objects.all()}
            users = {role: get_user_model().objects.filter(role=role, is_active=True).order_by('pk').first()
                     for role in ('admin', 'teacher', 'student')}
            if not all(users.values()):
                raise RuntimeError('Existing active admin, teacher and student are required in the snapshot.')
            users['anonymous'] = AnonymousUser()
            embeddings = list(LegalKnowledgeEmbedding.objects.all())
            index_counts = Counter(row.source_type for row in embeddings)
            expected_laws = {row['corpus_id']: row['document_id'] for row in mapping['legal_documents']}
            law_records = {row['id']: row for row in corpus['chinese_laws']}
            exact_clauses = all(
                [clause.text for clause in sorted(clauses.values(), key=lambda c: c.order)
                 if clause.document_id == expected_laws[record['id']]] ==
                [row['text'] for row in corpus['clauses'] if row['document_id'] == record['id']]
                for record in corpus['chinese_laws'])
            owasp_hashes = {row['id']: row['source_hash'] for row in corpus['owasp']}
            imported_hashes_match = all(
                row['document_id'] in docs and
                docs[row['document_id']].source_hash == owasp_hashes[row['corpus_id']]
                for row in mapping['owasp_documents'])
            report = {
                'evaluated_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                'database': str(args.database.resolve()), 'database_access': 'read-only source, temporary SQLite snapshot',
                'django_version': django.get_version(),
                'embedding_provider_setting': settings.EMBEDDING_PROVIDER,
                'embedding_model_setting': settings.EMBEDDING_MODEL,
                'actual_retrieval': 'portable lexical BM25 with source titles and explicit terminology aliases',
                'remote_calls': 0, 'llm_answer_quality_evaluated': False,
                'integrity': {
                    'owasp_documents': len(mapping['owasp_documents']),
                    'legal_documents': len(mapping['legal_documents']),
                    'legal_articles': len(corpus['clauses']), 'index_counts': dict(index_counts),
                    'original_clause_texts_match': exact_clauses,
                    'owasp_source_hashes_match': imported_hashes_match,
                    'indexed_text_hashes_match': all(hashlib.sha256(row.text.encode()).hexdigest() == row.text_hash for row in embeddings),
                    'owasp_internal_documents': sum(doc.visibility == 'internal' for doc in docs.values()),
                },
                'candidate_coverage': {}, 'queries': [], 'api_checks': [], 'permissions': [], 'learning_agent': [],
                'metric_definition': 'hit@5 means an explicitly labelled source document or exact legal article is in the first five chunks; MRR uses its first rank. This is a small diagnostic sample, not a corpus-wide quality estimate.',
            }
            if baseline:
                report['pre_merge_inventory'] = baseline

            def normalized(results):
                rows = []
                for result in results:
                    source_title = ''
                    article_label = ''
                    if result['source_type'] == 'document':
                        source_title = docs[result['object_id']].title
                    elif result['source_type'] == 'legal_clause':
                        clause = clauses[result['object_id']]
                        source_title = laws[clause.document_id].title
                        article_label = clause.article_number
                    rows.append({
                        'id': result['id'], 'object_id': result['object_id'],
                        'source_type': result['source_type'], 'title': result['title'],
                        'source_title': source_title, 'article_label': article_label,
                        'score': result['score'], 'retrieval': result['retrieval'],
                        'excerpt': ' '.join(result['text'].split())[:280],
                        'source_url': (result.get('metadata') or {}).get('source_url', ''),
                    })
                return rows

            def source_match(result, expected):
                if expected.get('titles'):
                    return result['source_title'] in expected['titles']
                clause = clauses.get(result['object_id']) if result['source_type'] == 'legal_clause' else None
                return bool(clause and clause.document_id == expected_laws[expected['law']] and
                            clause.article_number == expected['article'])

            for scope in ('unfiltered', 'document', 'legal_clause'):
                qs = apply_embedding_visibility(LegalKnowledgeEmbedding.objects.all(), users['admin'])
                if scope != 'unfiltered':
                    qs = qs.filter(source_type=scope)
                available = list(qs)
                considered = available
                report['candidate_coverage'][scope] = {
                    'available_chunks': len(available), 'considered_chunks': len(considered),
                    'considered_source_types': dict(Counter(row.source_type for row in considered)),
                    'represented_document_ids': sorted({row.object_id for row in considered if row.source_type == 'document'}),
                }

            document_queries = [
                ('SQL injection', ['Testing for SQL Injection', 'SQL Injection Prevention Cheat Sheet']),
                ('SQL Injection Prevention Cheat Sheet', ['SQL Injection Prevention Cheat Sheet']),
                ('Cross Site Scripting Prevention Cheat Sheet', ['Cross Site Scripting Prevention Cheat Sheet']),
                ('Cross-Site Request Forgery Prevention Cheat Sheet', ['Cross-Site Request Forgery Prevention Cheat Sheet']),
                ('Cryptographic Storage Cheat Sheet', ['Cryptographic Storage Cheat Sheet']),
                ('Authentication Cheat Sheet', ['Authentication Cheat Sheet']),
                ('Server-Side Request Forgery Prevention Cheat Sheet', ['Server-Side Request Forgery Prevention Cheat Sheet']),
                ('XML External Entity Prevention Cheat Sheet', ['XML External Entity Prevention Cheat Sheet']),
                ('LLM Prompt Injection Prevention Cheat Sheet', ['LLM Prompt Injection Prevention Cheat Sheet']),
                ('Zero Trust Architecture Cheat Sheet', ['Zero Trust Architecture Cheat Sheet']),
                ('gRPC Security Cheat Sheet', ['gRPC Security Cheat Sheet']),
                ('SQL注入防护', ['Testing for SQL Injection', 'SQL Injection Prevention Cheat Sheet']),
                ('跨站脚本攻击防护', ['Cross Site Scripting Prevention Cheat Sheet', 'Testing for Reflected Cross Site Scripting']),
            ]
            law_queries = [
                ('敏感个人信息', 'cn-personal-information-protection-law', '第二十八条'),
                ('行踪轨迹', 'cn-personal-information-protection-law', '第二十八条'),
                ('个人信息删除', 'cn-personal-information-protection-law', '第四十七条'),
                ('不满十四周岁未成年人的个人信息', 'cn-personal-information-protection-law', '第三十一条'),
                ('数据分类分级保护制度', 'cn-data-security-law', '第二十一条'),
                ('重要数据风险评估报告', 'cn-data-security-law', '第三十条'),
                ('隐私权 私人生活安宁', 'cn-civil-code-privacy-excerpt', '第一千零三十二条'),
                ('个人信息跨境提供', 'cn-personal-information-protection-law', '第三十八条'),
            ]
            cases = [(query, 'document', {'titles': titles}) for query, titles in document_queries]
            cases += [(query, 'legal_clause', {'law': law, 'article': article}) for query, law, article in law_queries]
            # Verify labels against actual source objects before calculating metrics.
            for query, kind, expected in cases:
                if expected.get('titles') and not set(expected['titles']).issubset({doc.title for doc in docs.values()}):
                    raise ValueError(f'Unknown expected source: {query}')
                if expected.get('law'):
                    if expected['law'] not in law_records:
                        raise ValueError(f'Unknown expected law: {query}')
                    if not any(row['document_id'] == expected['law'] and row['article_label'] == expected['article']
                               for row in corpus['clauses']):
                        raise ValueError(f'Unknown expected article: {query}')
            service = LegalRetrievalService()
            for query, kind, expected in cases:
                for scope in ('unfiltered', kind):
                    started = time.perf_counter()
                    rows = normalized(service.retrieve(query=query, top_k=5,
                                      filters={} if scope == 'unfiltered' else {'source_type': scope}, user=users['admin']))
                    elapsed = round((time.perf_counter() - started) * 1000, 2)
                    ranks = [rank for rank, row in enumerate(rows, 1) if source_match(row, expected)]
                    report['queries'].append({'query': query, 'category': kind, 'scope': scope,
                        'expected': expected, 'hit_at_5': bool(ranks),
                        'reciprocal_rank': 1 / ranks[0] if ranks else 0, 'latency_ms': elapsed, 'results': rows})

            # Unanswerable probes are separated from positive metrics.
            for query in ('zxqv987654_no_matching_corpus', '火星量子香蕉税法'):
                for kind in ('document', 'legal_clause'):
                    rows = normalized(service.retrieve(query=query, top_k=5, filters={'source_type': kind}, user=users['admin']))
                    report.setdefault('unanswerable_probes', []).append({'query': query, 'scope': kind,
                        'returned': len(rows), 'results': rows})

            # A source-id filter before the limit isolates candidate omission
            # from missing ingestion. These probes do not change the ranker.
            report['targeted_probes'] = []
            for query, source_title in (
                ('SQL Injection Prevention Cheat Sheet', 'SQL Injection Prevention Cheat Sheet'),
                ('Zero Trust Architecture Cheat Sheet', 'Zero Trust Architecture Cheat Sheet'),
            ):
                document = next(doc for doc in docs.values() if doc.title == source_title)
                rows = normalized(service.retrieve(query=query, top_k=5,
                    filters={'source_type': 'document', 'object_id': document.pk}, user=users['admin']))
                report['targeted_probes'].append({'query': query, 'object_id': document.pk,
                    'returned': len(rows), 'expected_source_returned': any(row['source_title'] == source_title for row in rows),
                    'results': rows})
            query = '敏感个人信息'
            clause = next(clause for clause in clauses.values()
                          if clause.document_id == expected_laws['cn-personal-information-protection-law']
                          and clause.article_number == '第二十八条')
            rows = normalized(service.retrieve(query=query, top_k=5,
                filters={'source_type': 'legal_clause', 'object_id': clause.pk}, user=users['admin']))
            report['targeted_probes'].append({'query': query, 'object_id': clause.pk, 'returned': len(rows),
                'expected_source_returned': any(row['object_id'] == clause.pk for row in rows), 'results': rows})
            deep = normalized(service.retrieve(query=query, top_k=50,
                filters={'source_type': 'legal_clause'}, user=users['admin']))
            report['sensitive_definition_rank_at_50'] = next(
                (rank for rank, row in enumerate(deep, 1) if row['object_id'] == clause.pk), None)

            for role, user in users.items():
                rows = normalized(service.retrieve(query='SQL injection', top_k=5,
                                  filters={'source_type': 'document'}, user=user))
                report['permissions'].append({'role': role, 'returned_document_chunks': len(rows),
                    'expected_access': role in ('admin', 'teacher'),
                    'passed': bool(rows) == (role in ('admin', 'teacher'))})
            safe = SafeKnowledgeRetrievalService()
            for role in ('admin', 'student'):
                for query in ('SQL injection', '敏感个人信息'):
                    rows = safe.retrieve(query=query, top_k=5, user=users[role])
                    report['learning_agent'].append({'role': role, 'query': query,
                        'safe_source_types': list(safe.safe_source_types),
                        'returned_types': dict(Counter(row['source_type'] for row in rows)),
                        'imported_owasp_returned': any(row['source_type'] == 'document' for row in rows)})

            with override_settings(LEGAL_KB_RAG_USE_LLM=False):
                client = APIClient()
                for role in ('admin', 'teacher', 'student', 'anonymous'):
                    client.force_authenticate(user=None if role == 'anonymous' else users[role])
                    response = client.post('/api/legal-kb/retrieve/', {
                        'query': '敏感个人信息', 'filters': {'source_type': 'legal_clause'},
                        'top_k': 5, 'include_raw': True}, format='json')
                    data = response.data if hasattr(response, 'data') else {}
                    report['api_checks'].append({'role': role, 'endpoint': '/api/legal-kb/retrieve/',
                        'status': response.status_code, 'citations': len(data.get('citations', [])),
                        'raw_results_present': 'results' in data, 'provider': data.get('provider'),
                        'answer_nonempty': bool(data.get('answer'))})
                client.force_authenticate(user=users['teacher'])
                detail_id = next(doc.pk for doc in docs.values() if doc.title == 'SQL Injection Prevention Cheat Sheet')
                for endpoint in ('/api/legal-kb/library/', '/api/legal-kb/documents/',
                                 f'/api/legal-kb/library/document/{detail_id}/'):
                    response = client.get(endpoint)
                    report['api_checks'].append({'role': 'teacher', 'endpoint': endpoint, 'status': response.status_code})

            report['metrics'] = {}
            for category in ('document', 'legal_clause'):
                for scope in ('unfiltered', category):
                    rows = [row for row in report['queries'] if row['category'] == category and row['scope'] == scope]
                    durations = sorted(row['latency_ms'] for row in rows)
                    report['metrics'][f'{category}/{scope}'] = {
                        'questions': len(rows), 'hits_at_5': sum(row['hit_at_5'] for row in rows),
                        'hit_rate_at_5': statistics.mean(row['hit_at_5'] for row in rows),
                        'mrr_at_5': statistics.mean(row['reciprocal_rank'] for row in rows),
                        'p50_ms': statistics.median(durations),
                        'p95_ms': durations[min(len(durations) - 1, int(len(durations) * .95))],
                    }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps({key: report[key] for key in ('integrity', 'metrics', 'permissions', 'api_checks')},
                             ensure_ascii=False, indent=2))
            print(f'Report: {args.output.resolve()}')
        finally:
            connections.close_all()


if __name__ == '__main__':
    main()
