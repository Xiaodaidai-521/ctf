"""Real protected-provider / native PostgreSQL evaluation on an isolated corpus copy.

Runs on Windows with PostgreSQL 16 + pgvector and pywin32 installed. Business
SQLite is read only; keys stay in a current-user-only temporary directory.
Evidence labels are loaded unchanged from the original diagnostic evaluation.
"""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))


def private(path, directory=False):
    if os.name != 'nt':
        path.chmod(0o700 if directory else 0o600)
        return
    import win32api
    import win32con
    import win32security as security
    token = security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = security.GetTokenInformation(token, security.TokenUser)[0]
    finally:
        token.Close()
    acl = security.ACL()
    acl.AddAccessAllowedAceEx(security.ACL_REVISION,
        security.OBJECT_INHERIT_ACE | security.CONTAINER_INHERIT_ACE if directory else 0,
        win32con.GENERIC_ALL, sid)
    security.SetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
        security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, acl, None)


def setup_providers(directory, operational):
    from data_security.contracts import KeyPurpose, KeyReference, KeyStatus, PolicyBinding, PolicySnapshot
    from data_security.contracts.schema import content_hash
    from data_security.adapters.llm.official import ENDPOINTS
    entries, refs = [], {}
    providers = [('qwen', operational.get('EMBEDDING_API_KEY'), operational.get('EMBEDDING_MODEL')),
                 ('volcano', operational.get('ARK_API_KEY'), operational.get('ARK_MODEL')),
                 ('deepseek', operational.get('DEEPSEEK_API_KEY'), operational.get('DEEPSEEK_MODEL'))]
    materials = [('framework_key', KeyPurpose.FRAMEWORK, secrets.token_hex(32).encode()),
                 ('data_key', KeyPurpose.DATA, secrets.token_bytes(32)),
                 ('audit_key', KeyPurpose.AUDIT, secrets.token_bytes(32))]
    materials += [(name, KeyPurpose.PROVIDER, value.encode()) for name, value, model in providers if value and model]
    for name, purpose, material in materials:
        ref = KeyReference(schema_version=KeyReference.SCHEMA,
            key_ref=f'provider/{name}/v1' if purpose is KeyPurpose.PROVIDER else purpose.value + '/v1',
            purpose=purpose, version='v1', status=KeyStatus.ACTIVE)
        path = directory / (name + '.key')
        path.write_bytes(material)
        private(path)
        entries.append({'reference': ref.to_wire(), 'file': path.name, 'identities': ['service/security']})
        refs[name] = ref
    manifest = directory / 'manifest.json'
    manifest.write_text(json.dumps({'schema_version': 'ds.key-manifest.v1', 'environment': 'evaluation', 'entries': entries}))
    private(manifest)
    policy = directory / 'approved-policy.json'
    policy.write_bytes((ROOT / 'docs/data-security/phase3-policy.json').read_bytes())
    private(policy)
    snapshot = PolicySnapshot.from_json(policy.read_bytes())
    binding = PolicyBinding(schema_version=PolicyBinding.SCHEMA, protection_version=snapshot.version,
        protection_hash=snapshot.content_hash, risk_version='risk/disabled-phase3',
        risk_hash=content_hash({'risk': 'disabled-phase3'}), contract_version='ds.m0.v1')
    config = {'schema_version': 'ds.bootstrap.v1', 'environment': 'evaluation',
        'key_manifest': str(manifest), 'policy_file': str(policy), 'policy_binding': binding.to_wire(),
        **{name: refs[name].to_wire() for name in ('framework_key', 'data_key', 'audit_key')},
        'providers': [{'endpoint_ref': name, 'base_url': ENDPOINTS[name], 'models': [model],
                       'key_ref': refs[name].to_wire()} for name, value, model in providers if name in refs], 'backup': None}
    path = directory / 'bootstrap.json'
    path.write_text(json.dumps(config))
    private(path)
    # These two readers also check the POSIX write bits; readonly on Windows.
    if os.name == 'nt':
        policy.chmod(0o400)
        path.chmod(0o400)
    from ctf_backend.security_bootstrap import assemble
    from ai_providers import bind_manager
    components = assemble(config_path=str(path))
    bind_manager(components['manager'])
    return components


def metrics(rows):
    latencies = sorted(row['latency_ms'] for row in rows)
    return {'count': len(rows), 'hits': sum(row['hit_at_5'] for row in rows),
        'hit_at_5': statistics.mean(row['hit_at_5'] for row in rows),
        'mrr': statistics.mean(row['reciprocal_rank'] for row in rows),
        'p50_ms': statistics.median(latencies), 'p95_ms': latencies[min(len(latencies)-1, int(len(latencies)*.95))]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT.parent / 'database/db.sqlite3')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/knowledge-remote-pg-evaluation.json')
    parser.add_argument('--pg-bin', type=Path, default=Path('C:/Program Files/PostgreSQL/16/bin'))
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--reuse-workspace', type=Path, help='Reuse only a cluster previously created by this script.')
    parser.add_argument('--env-file', type=Path, default=ROOT/'.env')
    parser.add_argument('--postgres-tests', action='store_true', help='Run synthetic ANN regressions on a separate test database.')
    args = parser.parse_args()
    from dotenv import dotenv_values
    operational = dotenv_values(args.env_file)
    os.environ.pop('DATA_SECURITY_CONFIG', None)
    os.environ.pop('DATABASE_URL', None)
    os.environ.update(SECRET_KEY='isolated-remote-pg-evaluation-framework-key-20261112',
        DATABASE_BACKEND='postgres', DB_HOST='127.0.0.1', DB_NAME='knowledge_eval', DB_USER='knowledge_eval',
        DB_PASSWORD='', DB_TRANSPORT='local', DB_SSLMODE='disable', DEBUG='true',
        DJANGO_SETTINGS_MODULE='ctf_backend.settings', PYTHONUTF8='1')
    for name in ('EMBEDDING_PROVIDER', 'EMBEDDING_MODEL', 'EMBEDDING_DIMENSION'):
        os.environ[name] = operational[name]
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    os.environ['DB_PORT'] = str(port)
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'source_database': str(args.database.resolve()),
        'source_access': 'read-only; isolated native PostgreSQL cluster', 'postgres_port': port,
        'providers': [], 'retrieval': {}, 'answers': [], 'errors': [], 'production_settings_changed': False}
    workspace = args.reuse_workspace.resolve() if args.reuse_workspace else Path(tempfile.mkdtemp(prefix='knowledge-remote-pg-')).resolve()
    if args.reuse_workspace and (not workspace.name.startswith('knowledge-remote-pg-') or not (workspace/'pgdata/PG_VERSION').exists()):
        parser.error('Not an isolated evaluation cluster')
    data, keydir = workspace / 'pgdata', workspace / 'keys'
    keydir.mkdir()
    private(keydir, directory=True)
    started_pg = False

    def command(arguments):
        # pg_ctl's server inherits handles on Windows: pipes would keep
        # communicate() waiting after pg_ctl itself has returned.
        with (workspace / 'commands.log').open('ab') as log:
            result = subprocess.run([str(args.pg_bin / arguments[0]), *arguments[1:]],
                stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode:
            raise RuntimeError('postgres command failed: ' + arguments[0])

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    try:
        print('Initializing isolated PostgreSQL...', flush=True)
        if not args.reuse_workspace:
            command(['initdb.exe', '-D', str(data), '-U', 'knowledge_eval', '--auth=trust', '--encoding=UTF8', '--locale=C'])
        command(['pg_ctl.exe', '-D', str(data), '-l', str(workspace/'postgres.log'), '-o',
                 f'-h 127.0.0.1 -p {port}', '-w', 'start'])
        started_pg = True
        if not args.reuse_workspace:
            command(['createdb.exe', '-h', '127.0.0.1', '-p', str(port), '-U', 'knowledge_eval', 'knowledge_eval'])
        import django
        django.setup()
        from django.core.management import call_command
        from django.db import connection, connections
        print('Migrating disposable database...', flush=True)
        call_command('migrate', verbosity=0, interactive=False)
        with connection.cursor() as cursor:
            cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
            cursor.execute('SELECT version(), (SELECT extversion FROM pg_extension WHERE extname=\'vector\')')
            report['postgres_version'], report['pgvector_version'] = cursor.fetchone()
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import AnonymousUser
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import JSONField
        from legal_kb.models import LegalDocument, LegalClause, LegalKnowledgeEmbedding
        from rag_ingestion.models import DocumentSource
        from legal_kb.services.embedding_service import EmbeddingService
        from legal_kb.services.retrieval_service import LegalRetrievalService
        from legal_kb.services.visibility import apply_embedding_visibility
        admin = get_user_model().objects.get_or_create(username='evaluation-admin', defaults={'role':'admin','is_staff':True})[0]
        teacher = get_user_model().objects.get_or_create(username='evaluation-teacher', defaults={'role':'teacher'})[0]
        student = get_user_model().objects.get_or_create(username='evaluation-student', defaults={'role':'student'})[0]
        with closing(sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro', uri=True)) as source:
            source.row_factory = sqlite3.Row
            ctypes = {row['id']: ContentType.objects.get(app_label=row['app_label'], model=row['model']).pk
                      for row in source.execute('SELECT * FROM django_content_type')}
            for model in (DocumentSource, LegalDocument, LegalClause, LegalKnowledgeEmbedding):
                if args.reuse_workspace:
                    continue
                instances = []
                for raw in source.execute('SELECT * FROM '+model._meta.db_table):
                    values = {}
                    for field in model._meta.concrete_fields:
                        value = raw[field.column]
                        if isinstance(field, JSONField) and value is not None:
                            value = json.loads(value)
                        if field.column in ('uploaded_by_id', 'created_by_id'):
                            value = None
                        if field.column == 'content_type_id':
                            value = ctypes[value]
                        values[field.attname] = value
                    instances.append(model(**values))
                model.objects.bulk_create(instances, batch_size=100)
        docs = dict(DocumentSource.objects.values_list('pk', 'title'))
        clauses = {row.pk: row for row in LegalClause.objects.select_related('document')}
        mapping = json.loads((ROOT/'artifacts/knowledge-import.json').read_text(encoding='utf-8'))
        imported_ids = {row['document_id'] for row in mapping['owasp_documents']}
        law_ids = {row['corpus_id']: row['document_id'] for row in mapping['legal_documents']}
        golden = json.loads((ROOT/'artifacts/knowledge-retrieval-evaluation.json').read_text(encoding='utf-8'))['queries']
        rows = list(LegalKnowledgeEmbedding.objects.order_by('id'))
        report['corpus'] = {'all_chunks': len(rows), 'public_remote_chunks': sum(
            row.source_type == 'legal_clause' or row.source_type == 'document' and row.object_id in imported_ids for row in rows)}
        report['initial_index'] = {'remote_vectors': LegalKnowledgeEmbedding.objects.exclude(embedding_vector=None).count()}
        try:
            EmbeddingService().embed_text('SQL injection prevention')
        except RuntimeError as error:
            report['initial_index']['unbound_remote_error'] = str(error)
        print('Assembling protected real providers...', flush=True)
        components = setup_providers(keydir, operational)
        embedder = EmbeddingService()
        from ai_providers import Message
        # Observe status only; all content/authentication still flows through
        # OfficialAI. Never retain headers, keys, provider bodies or error messages.
        import requests
        from urllib.parse import urlparse
        original_post = requests.Session.post
        def observed_post(session, url, **kwargs):
            start = time.perf_counter()
            try:
                response = original_post(session, url, **kwargs)
                observation = {'host':urlparse(url).hostname, 'status':response.status_code,
                    'latency_ms':round((time.perf_counter()-start)*1000,2)}
                if response.status_code != 200:
                    # Only a fixed category leaves the adapter observation. Bound
                    # the error read and discard all body text and provider values.
                    raw = bytearray()
                    for chunk in response.iter_content(1024):
                        raw.extend(chunk)
                        if len(raw)>=4096:
                            break
                    try:
                        envelope = json.loads(raw[:4096])
                        code = str((envelope.get('error') or {}).get('code','')).lower()
                        if any(v in code for v in ('overdue','quota','balance','arrear')):
                            observation['error_category'] = 'account_or_quota'
                        elif any(v in code for v in ('ratelimit','rate_limit','throttl')):
                            observation['error_category'] = 'rate_limit'
                        elif any(v in code for v in ('invalidapikey','invalid_api_key','authentication')):
                            observation['error_category'] = 'invalid_credentials'
                        else:
                            observation['error_category'] = 'other'
                    except (ValueError,AttributeError):
                        observation['error_category'] = 'unclassified'
                report.setdefault('http_observations', []).append(observation)
                return response
            except requests.RequestException as error:
                report.setdefault('http_observations', []).append({'host':urlparse(url).hostname,
                    'transport_error_type':type(error).__name__})
                raise
        requests.Session.post = observed_post
        for name in ('qwen', 'volcano', 'deepseek'):
            handle = components['manager'].get_provider(name)
            if not handle:
                report['providers'].append({'provider': name, 'status': 'not_configured'})
                continue
            start = time.perf_counter()
            try:
                if name == 'qwen':
                    vector = embedder.embed_text('SQL injection prevention')
                    detail = {'dimension': len(vector), 'finite': all(__import__('math').isfinite(v) for v in vector)}
                else:
                    answer = asyncio.run(handle.chat([Message('user', '仅回复：连接成功')], temperature=0, max_tokens=256))
                    detail = {'content': answer.content, 'usage': answer.usage}
                report['providers'].append({'provider': name, 'model': handle.model, 'status': 'success',
                    'latency_ms': round((time.perf_counter()-start)*1000, 2), **detail})
            except Exception as error:
                report['providers'].append({'provider': name, 'model': handle.model, 'status': 'failed',
                    'error_type': type(error).__name__, 'error_code': str(error)[:120],
                    'latency_ms': round((time.perf_counter()-start)*1000, 2)})
            print('Provider probe:', report['providers'][-1], flush=True)
            save()
        remote_available = any(r['provider']=='qwen' and r['status']=='success' for r in report['providers'])
        if not remote_available:
            report['errors'].append({'type':'RuntimeError','code':'REAL_EMBEDDING_PROBE_FAILED'})
        print('Embedding public merged corpus...', flush=True)
        selected = [row for row in rows if remote_available and row.embedding_vector is None and
                    (row.source_type=='legal_clause' or row.source_type=='document' and row.object_id in imported_ids)]
        batches = [selected[i:i+10] for i in range(0, len(selected), 10)]
        embedding_start = time.perf_counter()
        done = 0

        def embed_batch(batch):
            try:
                return batch, embedder.embed_many([row.text for row in batch])
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(embed_batch, batch) for batch in batches]
            for future in as_completed(futures):
                batch, vectors = future.result()
                for row, vector in zip(batch, vectors):
                    row.embedding_vector = vector
                    row.embedding_model, row.embedding_dimension = embedder.model, embedder.dimension
                    row.metadata = {**row.metadata, 'vector_space': embedder.vector_space}
                LegalKnowledgeEmbedding.objects.bulk_update(batch, ['embedding_vector', 'embedding_model', 'embedding_dimension', 'metadata'])
                done += len(batch)
                if done % 200 == 0 or done == len(selected):
                    print(f'Real vectors: {done}/{len(selected)}, elapsed {time.perf_counter()-embedding_start:.1f}s', flush=True)
                    report['embedding_index'] = {'completed': done, 'total': len(selected), 'batches': len(batches),
                        'dimension': embedder.dimension, 'vector_space': embedder.vector_space,
                        'elapsed_seconds': round(time.perf_counter()-embedding_start, 2)}
                    save()

        def match(result, expected):
            if expected.get('titles'):
                return result['source_type']=='document' and docs.get(result['object_id']) in expected['titles']
            clause = clauses.get(result['object_id']) if result['source_type']=='legal_clause' else None
            return bool(clause and clause.document_id==law_ids[expected['law']] and clause.article_number==expected['article'])

        query_vectors = {}
        for case in golden if remote_available else []:
            query = case['query']
            if query not in query_vectors:
                start = time.perf_counter()
                query_vectors[query] = (embedder.embed_text(query), (time.perf_counter()-start)*1000)
        service = LegalRetrievalService(embedding_service=embedder)
        for mode in (('pg_bm25', 'remote_exact', 'remote_hnsw', 'production_hybrid') if remote_available else ('pg_bm25',)):
            evaluations = []
            negatives = []
            if mode == 'remote_exact':
                with connection.cursor() as cursor:
                    cursor.execute('SET enable_seqscan=on')
                    cursor.execute('SET enable_indexscan=off')
                    cursor.execute('SET enable_bitmapscan=off')
            if mode == 'remote_hnsw':
                with connection.cursor() as cursor:
                    cursor.execute("CREATE INDEX IF NOT EXISTS knowledge_eval_hnsw ON legal_kb_legalknowledgeembedding USING hnsw (embedding_vector vector_cosine_ops)")
                    cursor.execute('ANALYZE legal_kb_legalknowledgeembedding')
                    cursor.execute('SET enable_seqscan=off')
                    cursor.execute('SET enable_indexscan=on')
                    cursor.execute('SET enable_bitmapscan=on')
                    cursor.execute('SET hnsw.ef_search=100')
            for case in golden:
                query, scope = case['query'], case['scope']
                qs = apply_embedding_visibility(LegalKnowledgeEmbedding.objects.all(), admin)
                if scope != 'unfiltered':
                    qs = qs.filter(source_type=scope)
                vector, remote_ms = query_vectors.get(query, ([],0))
                start = time.perf_counter()
                if mode == 'pg_bm25':
                    results = service._retrieve_portable(query, [], qs, 5)
                elif mode == 'production_hybrid':
                    results = service._retrieve_with_pgvector(query, vector, qs, 5) or []
                else:
                    from pgvector.django import CosineDistance
                    results = [{'id': row.id, 'object_id': row.object_id, 'source_type': row.source_type,
                                'title': row.title, 'text': row.text, 'score': 1-float(row.distance), 'metadata': row.metadata}
                               for row in qs.exclude(embedding_vector=None).annotate(distance=CosineDistance('embedding_vector', vector)).order_by('distance')[:5]]
                latency = (time.perf_counter()-start)*1000
                ranks = [rank for rank, row in enumerate(results, 1) if match(row, case['expected'])]
                evaluations.append({'query': query, 'scope': scope, 'expected': case['expected'],
                    'hit_at_5': bool(ranks), 'reciprocal_rank': 1/ranks[0] if ranks else 0,
                    'latency_ms': round(latency,2), 'remote_query_embedding_ms': round(remote_ms,2),
                    'results': [{**{k:v for k,v in row.items() if k not in ('text','metadata')},
                                 'excerpt': row['text'][:300]} for row in results]})
            report['retrieval'][mode] = {'metrics': metrics(evaluations), 'queries': evaluations}
            print(mode, report['retrieval'][mode]['metrics'], flush=True)
            save()
        for query in ('zxqv987654_no_matching_corpus', '火星量子香蕉税法'):
            vector = embedder.embed_text(query) if remote_available else []
            for scope in ('document','legal_clause'):
                qs = apply_embedding_visibility(LegalKnowledgeEmbedding.objects.filter(source_type=scope), admin)
                results = ((service._retrieve_with_pgvector(query, vector, qs, 5) or []) if remote_available
                           else service._retrieve_portable(query,[],qs,5))
                report.setdefault('unanswerable', []).append({'query':query,'scope':scope,'returned':len(results),
                    'scores':[r['score'] for r in results]})
        for role, user in [('admin',admin),('teacher',teacher),('student',student),('anonymous',AnonymousUser())]:
            results = (service.retrieve(query='SQL Injection Prevention Cheat Sheet', filters={'source_type':'document'}, top_k=5, user=user)
                       if remote_available else service._retrieve_portable('SQL Injection Prevention Cheat Sheet',[],
                           apply_embedding_visibility(LegalKnowledgeEmbedding.objects.filter(source_type='document'),user),5))
            report.setdefault('permissions', []).append({'role':role,'returned':len(results),
                'internal_returned':len(results) if role in ('student','anonymous') else None})
        print('Evaluating grounded answers...', flush=True)
        answer_cases = [
            ('如何防止SQL注入？', 'SQL注入防护', ['参数', '预编译', 'parameter', 'prepared']),
            ('什么是敏感个人信息？请指出法条。', '敏感个人信息', ['第二十八条','28']),
            ('处理不满十四周岁未成年人的个人信息，需要谁的同意？', '不满十四周岁未成年人的个人信息', ['监护人','父母']),
            ('个人信息处理者应在什么情况下主动删除个人信息？', '个人信息删除', ['删除']),
            ('数据分类分级保护制度依据什么制定？', '数据分类分级保护制度', ['重要','危害']),
            ('火星量子香蕉税法规定的税率是多少？', '火星量子香蕉税法', []),
        ]
        for name in ('volcano','deepseek'):
            if not remote_available:
                continue
            handle = components['manager'].get_provider(name)
            if not any(r['provider']==name and r['status']=='success' for r in report['providers']):
                continue
            for question, query, terms in answer_cases:
                # Evaluate the actual production retrieval arm; do not replace bad
                # retrieval with gold snippets before asking the model.
                results = service.retrieve(query=query, top_k=5, user=admin)
                context = '\n\n'.join(f'[{i}] {r["title"]}\n{r["text"]}' for i,r in enumerate(results,1))
                start = time.perf_counter()
                try:
                    response = asyncio.run(handle.chat([
                        Message('system','你是知识库助手。只根据提供的证据回答，逐项标注引用编号如[1]；不应推测。证据不能回答问题时明确说知识库证据不足。用简洁中文回答。'),
                        Message('user',f'问题：{question}\n\n知识库证据：\n{context or "无检索结果"}')], temperature=0, max_tokens=800))
                    import re
                    cites = [int(v) for v in re.findall(r'\[(\d+)\]', response.content)]
                    report['answers'].append({'provider':name,'model':handle.model,'question':question,
                        'answer':response.content,'usage':response.usage,
                        'latency_ms':round((time.perf_counter()-start)*1000,2), 'retrieved_count':len(results),
                        'citations_in_range':bool(cites) and all(1<=v<=len(results) for v in cites),
                        'keyword_check':any(t.lower() in response.content.lower() for t in terms) if terms else None,
                        'evidence': [{'citation':i,'title':r['title'],'text':r['text']} for i,r in enumerate(results,1)]})
                except Exception as error:
                    report['answers'].append({'provider':name,'question':question,'error_type':type(error).__name__,
                                             'error_code':str(error)[:120]})
                print('Answer completed:',name,question,flush=True)
                save()
        report['completed'] = True
        report['remote_quality_evaluated'] = remote_available
        report['status'] = 'complete' if remote_available else 'partial_remote_unavailable'
        if args.postgres_tests:
            print('Running real PostgreSQL tests with synthetic vectors (not model quality)...',flush=True)
            try:
                call_command('test','legal_kb.tests.PgvectorAnnRetrievalTests',
                    'legal_kb.test_retrieval_regressions',verbosity=1,interactive=False)
            except SystemExit:
                report['completed'] = False
                raise RuntimeError('POSTGRES_REGRESSIONS_FAILED') from None
            report['postgres_regressions'] = 'passed; synthetic ANN tests and corpus/permission regressions'
    except Exception as error:
        report['errors'].append({'type':type(error).__name__,'code':str(error)[:1500]})
        print('Evaluation stopped:',type(error).__name__,str(error)[:300],flush=True)
        report['completed'] = False
    finally:
        if 'original_post' in locals():
            requests.Session.post = original_post
        if started_pg:
            try:
                from django.db import connections
                connections.close_all()
                command(['pg_ctl.exe','-D',str(data),'-m','fast','-w','stop'])
                report['isolated_postgres_stopped'] = True
            except Exception as error:
                report['isolated_postgres_stopped'] = False
                report['errors'].append({'type':type(error).__name__,'code':'PG_STOP_FAILED'})
        # Preserve isolated nonsecret DB/cache for diagnosis; destroy credential files.
        for path in keydir.iterdir():
            path.chmod(0o600)
            path.unlink()
        keydir.rmdir()
        report['temporary_keys_deleted'] = True
        report['isolated_workspace'] = str(workspace)
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        save()
    return 0 if report.get('completed') else 1


if __name__=='__main__':
    sys.exit(main())
