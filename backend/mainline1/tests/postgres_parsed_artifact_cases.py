"""Phase-five private publication checks; run only against isolated PostgreSQL."""
import hashlib
import io
import json
from dataclasses import replace
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase
from openpyxl import Workbook

from data_security.contracts.payloads import BASELINE_LIMITS, TableSnapshot
from mainline1.models import ParseAttempt, ParsedArtifact, ParseRun
from mainline1.parsing import AssetRef, InputError, parse_table
from mainline1.repository import DjangoRunRepository
from mainline1.tasks import ParseTasks
from mainline1.worker import execute_one, parse_snapshot


class GovernedPublicationTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.content = b'header\nsynthetic\n'
        self.asset = AssetRef('synthetic-v1', 'test-domain', 'sha256:' + hashlib.sha256(self.content).hexdigest(),
                              'csv', len(self.content), 'private:synthetic')
        self.repository = DjangoRunRepository()
        self.tasks = ParseTasks(self.repository)
        self.run = self.tasks.create(domain='test-domain', environment='test', evaluation='synthetic',
                                     principal='synthetic-owner', idempotency_key='synthetic-publication',
                                     snapshot=parse_snapshot(self.asset))
        self.parsed = parse_table(self.content, self.asset)

    def active(self):
        return self.tasks.claim(self.run.run_id, now=100, lease_seconds=30)

    def publish(self, active, result=None, repository=None):
        return (repository or self.repository).publish(
            active.run_id, token=active.attempts[-1].token, now=101, result=result or self.parsed)

    def assert_no_publication(self, active):
        self.assertEqual(self.repository.get(active.run_id), active)
        self.assertEqual(ParsedArtifact.objects.count(), 0)
        self.assertEqual(ParseRun.objects.get(pk=active.run_id).status, 'running')
        self.assertEqual(ParseAttempt.objects.get(pk=active.attempts[-1].attempt_id).state['status'], 'running')

    def test_publication_persists_only_known_versioned_private_snapshot(self):
        active = self.active()
        final = self.publish(active)
        connection.close()
        artifact = ParsedArtifact.objects.get(run_id=active.run_id)
        value = artifact.payload
        self.assertEqual(set(value), {'schema_version', 'adapter_version', 'snapshot', 'source'})
        self.assertEqual(value['schema_version'], 'ds.parsed-artifact.v1')
        self.assertEqual(value['adapter_version'], 'parsed-artifact-2026-11-06.v1')
        snapshot = TableSnapshot.from_wire(value['snapshot'])
        self.assertEqual(snapshot.asset_version, self.asset.version_id)
        self.assertEqual(snapshot.input_hash, self.asset.content_hash[7:])
        self.assertEqual((snapshot.cells[0].source_row, snapshot.cells[0].column_id), (2, 'c1'))
        self.assertEqual(snapshot.cells[0].original_text, 'synthetic')
        self.assertEqual(value['source']['scope_hash'], self.parsed.scope_hash)
        self.assertEqual(value['source']['coverage']['semantic']['status'], 'not_run')
        self.assertNotIn('source_text', json.dumps(value))
        self.assertNotIn('cells', value['source'])
        self.assertLessEqual(len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()),
                             BASELINE_LIMITS.max_json_bytes)
        self.assertEqual((str(artifact.attempt_id), final.parsed_ref),
                         (active.attempts[-1].attempt_id, f'private:{artifact.pk}'))
        self.assertEqual(final.snapshot_json, self.run.snapshot_json)
        self.assertEqual(final.key, self.run.key)
        self.assertEqual(final.detection_status, 'not_run')

    def test_explicit_json_limit_rolls_back_success_attempt_and_revision(self):
        active = self.active()
        limited = DjangoRunRepository(artifact_limits=replace(BASELINE_LIMITS, max_json_bytes=1000))
        with self.assertRaisesMessage(InputError, 'RESOURCE_LIMIT'):
            self.publish(active, repository=limited)
        self.assert_no_publication(active)
        # A failed write does not consume the lease token or make the run unrecoverable.
        self.assertEqual(self.publish(active).status, 'succeeded')

    def test_explicit_row_cell_and_source_byte_limits_roll_back(self):
        active = self.active()
        for limits in (replace(BASELINE_LIMITS, max_rows=1), replace(BASELINE_LIMITS, max_cells=1),
                       replace(BASELINE_LIMITS, max_bytes=len(self.content) - 1)):
            with self.subTest(limits=limits), self.assertRaisesMessage(InputError, 'RESOURCE_LIMIT'):
                self.publish(active, repository=DjangoRunRepository(artifact_limits=limits))
            self.assert_no_publication(active)

    def test_full_metadata_is_subject_to_one_mebibyte_json_limit(self):
        book = Workbook()
        book.active.append(['h'] * 12)
        book.active.append([1] * 12)
        for cell in book.active[2]:
            cell.number_format = '数' * 30_000
        stream = io.BytesIO()
        book.save(stream)
        book.close()
        content = stream.getvalue()
        asset = replace(self.asset, format='xlsx', byte_size=len(content),
                        content_hash='sha256:' + hashlib.sha256(content).hexdigest())
        run = self.tasks.create(domain='test-domain', environment='test', evaluation='synthetic',
                                principal='synthetic-owner', idempotency_key='metadata-limit',
                                snapshot=parse_snapshot(asset))
        active = self.tasks.claim(run.run_id, now=100, lease_seconds=30)
        with self.assertRaisesMessage(InputError, 'RESOURCE_LIMIT'):
            self.publish(active, result=parse_table(content, asset))
        self.assert_no_publication(active)

    def test_unknown_source_schema_does_not_persist_raw_fallback(self):
        active = self.active()
        structures = json.loads(self.parsed.structure_json)
        structures[0]['raw_payload'] = 'synthetic secret never saved'
        value = replace(self.parsed, structure_json=json.dumps(structures))
        with self.assertRaisesMessage(InputError, 'PARSE_FAILED'):
            self.publish(active, result=value)
        self.assert_no_publication(active)
        self.assertNotIn('synthetic secret', json.dumps(ParseRun.objects.get(pk=active.run_id).state))

    def test_config_scope_and_asset_snapshots_remain_bound(self):
        active = self.active()
        for value, code in ((replace(self.parsed, config_hash='sha256:' + '0' * 64), 'CONFIG_INVALID'),
                            (replace(self.parsed, asset_version_id='other-version'), 'ASSET_VERSION_MISMATCH'),
                            (replace(self.parsed, scope_hash='sha256:' + '0' * 64), 'PARSE_FAILED')):
            with self.subTest(code=code), self.assertRaisesMessage(InputError, code):
                self.publish(active, result=value)
            self.assert_no_publication(active)

    def test_artifact_insert_failure_rolls_back_governed_payload_with_state(self):
        active = self.active()
        with patch('django.db.models.query.QuerySet.create', side_effect=RuntimeError('synthetic insert failure')):
            with self.assertRaisesMessage(RuntimeError, 'synthetic insert failure'):
                self.publish(active)
        self.assert_no_publication(active)

    def test_cancellation_does_not_govern_or_store_a_result(self):
        active = self.active()
        self.tasks.cancel(active.run_id)
        with patch('mainline1.repository.govern_parse_result', side_effect=AssertionError('must not publish')):
            final = self.publish(active)
        self.assertEqual(final.status, 'cancelled')
        self.assertEqual(ParsedArtifact.objects.count(), 0)

    def test_worker_limit_failure_contains_only_error_code_and_keeps_owner_acl(self):
        content = self.content
        accesses = []
        class Owner:
            def open_version(owner, asset, *, principal, domain_id):
                accesses.append((asset, principal, domain_id))
                return io.BytesIO(content)
        limited = DjangoRunRepository(artifact_limits=replace(BASELINE_LIMITS, max_json_nodes=10))
        final = execute_one(limited, self.run.run_id, Owner(), clock=lambda: 100)
        self.assertEqual(accesses, [(self.asset, 'synthetic-owner', 'test-domain')])
        self.assertEqual(final.status, 'failed')
        self.assertEqual(final.attempts[-1].error_code, 'RESOURCE_LIMIT')
        self.assertIsNone(final.parsed_ref)
        self.assertEqual(final.snapshot_json, self.run.snapshot_json)
        self.assertEqual(ParsedArtifact.objects.count(), 0)
        self.assertNotIn('source_text', json.dumps(ParseRun.objects.get(pk=self.run.run_id).state))
