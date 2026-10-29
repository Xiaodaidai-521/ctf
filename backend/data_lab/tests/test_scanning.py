from unittest.mock import patch
from django.db import IntegrityError
from rest_framework.exceptions import NotFound
from data_lab.catalog import TASK_B
from data_lab.common import Conflict
from data_lab.models import Scan, ReviewLedger
from data_lab.repository import review_service
from data_lab.scanning import ScanFailure, restore_parsed
from data_lab.services import scan_dto, start_scan, submit_review, owned_scan
from .base import LabTestCase


class ScanningTests(LabTestCase):
    def review(self, scan, action='confirm', **extra):
        scan.refresh_from_db()
        dto = scan_dto(scan)
        data = {'expected_state_version': dto['state_version'], 'idempotency_key': 'review-' + str(dto['profile_id']),
            'action': action, 'reason': '根据业务事实复核', 'fact_ids': ['F-PERSON'], 'basis_ids': ['BC-DS-001'],
            'finding_id': dto['findings']['items'][0]['finding_id']}
        data.update(extra)
        return submit_review(self.student, dto['profile_id'], data)

    def test_scanner_has_partial_coverage_and_unicode_roundtrip(self):
        scan = self.scan()
        dto = scan_dto(scan)
        self.assertEqual(dto['coverage']['parse']['processed_count'], 24)
        self.assertEqual(dto['coverage']['rule']['processed_count'], 18)
        self.assertEqual(dto['coverage']['rule']['ratio'], .75)
        self.assertEqual(dto['coverage']['semantic']['status'], 'not_run')
        parsed = restore_parsed(scan.parsed)
        cell = next(c for c in parsed.cells if c.row == 6 and c.column == 4)
        self.assertIn('😀', cell.source_text)
        for finding in scan.original['findings']:
            loc = finding['locations'][0]
            source = next(c.source_text for c in parsed.cells if c.row == loc['row'] and c.column == loc['column'])
            span = loc['span']
            self.assertTrue(source[span['start']:span['end']])
            self.assertEqual(finding['score_meaning'], 'uncalibrated_rule_score')

    def test_four_actions_persist_and_original_is_immutable(self):
        scan = self.scan()
        original = scan.original
        for action, args in [('confirm', {}), ('correct', {'category_id': 'DEMO_CONTACT'}), ('false_positive', {})]:
            record = self.review(scan, action, **args)
            self.assertEqual(record['action'], action)
        loc = {'kind': 'span', 'sheet_id': scan.parsed['cells'][0]['sheet_id'], 'row': 4, 'column': 4,
               'channel': 'value', 'span': {'start': 8, 'end': 19}}
        # Use the actual codepoint offset; the fourth column was parsed but not scanned.
        source = next(c['source_text'] for c in scan.parsed['cells'] if c['row'] == 4 and c['column'] == 4)
        loc['span'] = {'start': source.index('DEMO-U-0003'), 'end': source.index('DEMO-U-0003') + 11}
        self.review(scan, 'add_manual', finding_id=None, category_id='DEMO_PERSON_REF', locations=[loc])
        scan.refresh_from_db()
        self.assertEqual(scan.original, original)
        dto = scan_dto(scan)
        self.assertEqual(dto['counts']['manual_additions'], 1)
        self.assertEqual(dto['coverage']['rule']['ratio'], .75)
        self.assertEqual(len(dto['review_history']), 4)
        self.assertEqual(ReviewLedger.objects.get(scan=scan).revision, 5)

    def test_idempotency_and_stale_profile_conflicts(self):
        scan = self.scan()
        pid = str(scan.current_profile_id)
        data = {'expected_state_version': 1, 'idempotency_key': 'same', 'action': 'confirm', 'reason': '事实已核查',
                'fact_ids': ['F-PERSON'], 'basis_ids': ['BC-DS-001'], 'finding_id': scan.original['findings'][0]['finding_id']}
        first = submit_review(self.student, pid, data)
        self.assertEqual(submit_review(self.student, pid, data), first)
        with self.assertRaises(Conflict):
            submit_review(self.student, pid, {**data, 'reason': '不同内容'})
        with self.assertRaises(Conflict):
            submit_review(self.student, pid, {**data, 'idempotency_key': 'different'})

    def test_rescan_does_not_inherit_reviews(self):
        scan = self.scan()
        self.review(scan)
        second = self.scan(key='rescan')
        self.assertEqual(scan_dto(second)['review_history'], [])
        with self.assertRaises(Conflict):
            self.review(scan)

    def test_foreign_scans_and_profiles_are_not_found(self):
        scan = self.scan(self.new_lab(self.other))
        with self.assertRaises(NotFound):
            owned_scan(self.student, scan.scan_id)
        with self.assertRaises(NotFound):
            self.review(scan)

    def test_parse_failure_is_saved_not_knowledge_error(self):
        self.basis()
        with patch('data_lab.services.run_worker', side_effect=ScanFailure('PARSER_TIMEOUT_OR_UNAVAILABLE')):
            scan = start_scan(self.student, self.lab.attempt.attempt_id, {'fixture_id': 'customer-v1', 'idempotency_key': 'failed'})
        self.assertEqual(scan.status, 'failed')
        self.assertIn('受环境影响', scan_dto(scan)['message'])

    def test_event_failure_rolls_back_scan_request(self):
        self.basis()
        with patch('data_lab.common.events.emit_event', side_effect=IntegrityError('fault')):
            with self.assertRaises(IntegrityError):
                start_scan(self.student, self.lab.attempt.attempt_id, {'fixture_id': 'customer-v1', 'idempotency_key': 'fault'})
        self.assertFalse(Scan.objects.exists())

    def test_log_has_hard_negative_and_fullwidth_gap(self):
        scan = self.scan(self.new_lab(task_key=TASK_B))
        dto = scan_dto(scan)
        self.assertEqual(dto['coverage']['rule']['ratio'], 1)
        self.assertEqual(len(scan.original['findings']), 6)
        self.assertTrue(any(f['locations'][0]['row'] == 3 for f in scan.original['findings']))
        self.assertFalse(any(f['locations'][0]['row'] == 6 for f in scan.original['findings']))
