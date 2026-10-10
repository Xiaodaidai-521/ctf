"""Real PostgreSQL concurrency tests; SQLite must skip, not simulate row locks.

Run with DATABASE_BACKEND=postgres and a disposable DATABASE_URL:
    python manage.py test rag_ingestion.test_postgres_concurrency --noinput

Each worker has a separate Django connection/PostgreSQL backend PID. Events and
barriers force the contested ordering; all waits and SQL statements are bounded.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase

from legal_kb.models import LegalKnowledgeEmbedding

from .adapters.repository_legalkb import LegalKbChunkRepository
from .interfaces import Chunk, EmbeddedChunk, ParsedDocument
from .models import DocumentSource
from .pipeline import IngestionPipeline
from .services import IngestionService


@skipUnless(connection.vendor == 'postgresql', 'requires real PostgreSQL row locks')
class PostgresIngestionConcurrencyTests(TransactionTestCase):
    """Fence old tasks at index write and completion, across real connections."""

    WAIT_SECONDS = 20
    DATA = b'Concurrent upload fixture shared by independent PostgreSQL workers'

    def setUp(self):
        self.backend_pids = []
        self.pid_lock = Lock()
        # Avoid first-use ContentType creation being the unrelated race under test.
        from django.contrib.contenttypes.models import ContentType
        ContentType.objects.get_for_model(DocumentSource)

    def _wait(self, event, description):
        if not event.wait(self.WAIT_SECONDS):
            raise TimeoutError(description)

    def _worker(self, pipeline, *, filename, reingest=False, connected=None):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '20s'")
                cursor.execute("SET lock_timeout = '15s'")
                cursor.execute('SELECT pg_backend_pid()')
                pid = cursor.fetchone()[0]
            with self.pid_lock:
                self.backend_pids.append(pid)
            if connected is not None:
                connected.set()
            document = IngestionService(pipeline=pipeline).ingest_bytes(
                data=self.DATA, filename=filename, visibility='staff',
                reingest=reingest,
            )
            return document.pk
        finally:
            connections.close_all()

    @staticmethod
    def _pipeline(name, *, parse_hook=None, embed_hook=None, repository=None):
        class Parser:
            def parse(self, data, **kwargs):
                if parse_hook:
                    parse_hook()
                return ParsedDocument(text=name)

        parser = Parser()
        parser.name = name

        class Chunker:
            def split(self, text, **kwargs):
                return [Chunk(text=f'{text}:{index}', order=index + 1)
                        for index in range(2)]

        class Embedder:
            def embed(self, chunks):
                if embed_hook:
                    embed_hook()
                vector = [1.0] + [0.0] * 1023
                local = [1.0] + [0.0] * 127
                return [EmbeddedChunk(chunk, vector, local, 'concurrency-fixture', 1024)
                        for chunk in chunks]

        return IngestionPipeline(
            parser_selector=lambda filename, mime: parser,
            chunker=Chunker(), embedder=Embedder(), repository=repository,
        )

    def _assert_connections(self, count):
        self.assertEqual(len(self.backend_pids), count)
        self.assertEqual(len(set(self.backend_pids)), count)

    def _assert_winner(self, name, *, filename):
        self.assertEqual(DocumentSource.objects.count(), 1)
        document = DocumentSource.objects.get()
        self.assertEqual(document.status, 'completed')
        self.assertEqual(document.error_message, '')
        self.assertEqual(document.parser, name)
        self.assertEqual(document.filename, filename)
        self.assertEqual(document.chunk_count, 2)
        self.assertEqual(document.embedded_count, 2)
        self.assertIsNotNone(document.ingestion_token)
        chunks = LegalKnowledgeEmbedding.objects.filter(
            source_type='document', object_id=document.pk,
        ).order_by('chunk_index')
        self.assertEqual(list(chunks.values_list('text', flat=True)),
                         [f'{name}:0', f'{name}:1'])
        self.assertTrue(all(chunk.embedding_vector is not None for chunk in chunks))
        return document

    def test_four_identical_first_uploads_create_one_complete_index(self):
        barrier = Barrier(4, timeout=self.WAIT_SECONDS)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(
                self._worker,
                self._pipeline(f'worker-{index}', parse_hook=barrier.wait),
                filename=f'worker-{index}.txt',
            ) for index in range(4)]
            try:
                ids = [future.result(timeout=self.WAIT_SECONDS + 5) for future in futures]
            finally:
                barrier.abort()
        self._assert_connections(4)
        self.assertEqual(len(set(ids)), 1)
        document = DocumentSource.objects.get()
        self._assert_winner(document.parser, filename=f'{document.parser}.txt')

    def test_old_failure_cannot_overwrite_newer_first_upload_success(self):
        entered, release = Event(), Event()

        def delayed_failure():
            entered.set()
            self._wait(release, 'old parse was never released')
            raise RuntimeError('old parser failure after newer success')

        with ThreadPoolExecutor(max_workers=2) as pool:
            older = pool.submit(self._worker, self._pipeline('older', parse_hook=delayed_failure),
                                filename='older.txt')
            try:
                self._wait(entered, 'older task did not enter parsing')
                newer = pool.submit(self._worker, self._pipeline('newer'), filename='newer.txt')
                newer_id = newer.result(timeout=self.WAIT_SECONDS)
            finally:
                release.set()
            self.assertEqual(older.result(timeout=self.WAIT_SECONDS), newer_id)
        self._assert_connections(2)
        self._assert_winner('newer', filename='newer.txt')

    def test_old_success_cannot_replace_newer_index(self):
        entered, release = Event(), Event()

        def delayed_embedding():
            entered.set()
            self._wait(release, 'old embedding was never released')

        with ThreadPoolExecutor(max_workers=2) as pool:
            older = pool.submit(self._worker, self._pipeline('older', embed_hook=delayed_embedding),
                                filename='older.txt')
            try:
                self._wait(entered, 'older task did not enter embedding')
                newer = pool.submit(self._worker, self._pipeline('newer'), filename='newer.txt')
                newer_id = newer.result(timeout=self.WAIT_SECONDS)
            finally:
                release.set()
            self.assertEqual(older.result(timeout=self.WAIT_SECONDS), newer_id)
        self._assert_connections(2)
        self._assert_winner('newer', filename='newer.txt')

    def test_old_completion_cannot_overwrite_newer_statistics(self):
        stored, release = Event(), Event()
        owner = self

        class PausingRepository(LegalKbChunkRepository):
            def replace(self, **kwargs):
                count = super().replace(**kwargs)  # old index commits first
                stored.set()
                owner._wait(release, 'old completion was never released')
                return count

        with ThreadPoolExecutor(max_workers=2) as pool:
            older = pool.submit(
                self._worker, self._pipeline('older', repository=PausingRepository()),
                filename='older.txt',
            )
            try:
                self._wait(stored, 'older task did not commit its index')
                newer = pool.submit(self._worker, self._pipeline('newer'), filename='newer.txt')
                newer_id = newer.result(timeout=self.WAIT_SECONDS)
            finally:
                release.set()
            self.assertEqual(older.result(timeout=self.WAIT_SECONDS), newer_id)
        self._assert_connections(2)
        self._assert_winner('newer', filename='newer.txt')

    def test_old_success_cannot_undo_newer_failed_rebuild(self):
        # Seed a valid previous index without a worker; two subsequent workers race.
        document = IngestionService(pipeline=self._pipeline('original')).ingest_bytes(
            data=self.DATA, filename='original.txt',
        )
        entered, release = Event(), Event()

        def delayed_embedding():
            entered.set()
            self._wait(release, 'old embedding was never released')

        def newer_failure():
            raise RuntimeError('newer parser failure')

        with ThreadPoolExecutor(max_workers=2) as pool:
            older = pool.submit(self._worker, self._pipeline('older', embed_hook=delayed_embedding),
                                filename='older.txt', reingest=True)
            try:
                self._wait(entered, 'older rebuild did not enter embedding')
                newer = pool.submit(self._worker, self._pipeline('newer', parse_hook=newer_failure),
                                    filename='newer.txt', reingest=True)
                self.assertEqual(newer.result(timeout=self.WAIT_SECONDS), document.pk)
            finally:
                release.set()
            self.assertEqual(older.result(timeout=self.WAIT_SECONDS), document.pk)
        self._assert_connections(2)
        document.refresh_from_db()
        self.assertEqual(document.status, 'failed')
        self.assertEqual(document.filename, 'newer.txt')
        self.assertIn('newer parser failure', document.error_message)
        self.assertEqual(list(LegalKnowledgeEmbedding.objects.filter(
            source_type='document', object_id=document.pk,
        ).order_by('chunk_index').values_list('text', flat=True)),
                         ['original:0', 'original:1'])


    def test_new_claim_waits_for_atomic_index_write_row_lock(self):
        writing, release, newer_connected = Event(), Event(), Event()
        real_create = LegalKnowledgeEmbedding.objects.create
        paused = False

        def pause_inside_index_transaction(**kwargs):
            nonlocal paused
            if kwargs.get('text') == 'older:0' and not paused:
                paused = True
                writing.set()  # row lock held; old chunks already deleted
                self._wait(release, 'index write lock was never released')
            return real_create(**kwargs)

        with patch.object(LegalKnowledgeEmbedding.objects, 'create',
                          side_effect=pause_inside_index_transaction):
            with ThreadPoolExecutor(max_workers=2) as pool:
                older = pool.submit(self._worker, self._pipeline('older'), filename='older.txt')
                try:
                    self._wait(writing, 'older task did not enter atomic index write')
                    newer = pool.submit(
                        self._worker, self._pipeline('newer'), filename='newer.txt',
                        reingest=True, connected=newer_connected,
                    )
                    self._wait(newer_connected, 'newer worker did not open its connection')
                    with self.pid_lock:
                        old_pid, new_pid = self.backend_pids
                    deadline = monotonic() + self.WAIT_SECONDS
                    while monotonic() < deadline:
                        with connection.cursor() as cursor:
                            cursor.execute('SELECT pg_blocking_pids(%s)', [new_pid])
                            blockers = cursor.fetchone()[0]
                        if old_pid in blockers:
                            break
                        sleep(0.02)
                    else:
                        self.fail('PostgreSQL never reported the newer claim blocked by old index writer')
                    self.assertFalse(newer.done())
                finally:
                    release.set()
                older_id = older.result(timeout=self.WAIT_SECONDS)
                self.assertEqual(newer.result(timeout=self.WAIT_SECONDS), older_id)
        self._assert_connections(2)
        self._assert_winner('newer', filename='newer.txt')
