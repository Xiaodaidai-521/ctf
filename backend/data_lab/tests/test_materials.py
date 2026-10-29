import csv
import io
from unittest import TestCase

from data_lab.catalog import CASES, TASK_A, TASK_B, asset_bytes, digest, student_material
from data_lab.teacher_material import TARGETS, NEGATIVES


class MaterialTests(TestCase):
    def test_registered_assets_have_pinned_hashes_and_six_rows(self):
        for key, spec in CASES.items():
            raw = asset_bytes(key)
            self.assertEqual(digest(raw), spec['sha256'])
            rows = list(csv.reader(io.StringIO(raw.decode())))
            self.assertEqual(len(rows), 7)
            self.assertTrue(all(len(row) == 4 for row in rows))

    def test_customer_newline_empty_and_repeated_contact(self):
        rows = list(csv.reader(io.StringIO(asset_bytes(TASK_A).decode())))
        self.assertEqual(rows[1][2], rows[5][2])
        self.assertIn('\n', rows[5][3])
        self.assertIn('😀', rows[5][3])
        self.assertEqual(rows[6][3], '')
        self.assertEqual(rows[4][0], 'DEMO-U-9001')

    def test_teacher_positions_are_logical_and_distinct(self):
        for key in CASES:
            rows = list(csv.reader(io.StringIO(asset_bytes(key).decode())))
            for row, col, text, entity in TARGETS[key]:
                self.assertIn(text, rows[row - 1][col - 1])
            for row, col, text in NEGATIVES[key]:
                self.assertIn(text, rows[row - 1][col - 1])
                self.assertNotIn((row, col, text, 'DEMO_PERSON_REF'), TARGETS[key])

    def test_log_retest_is_separate_nested_scenario(self):
        raw = asset_bytes(TASK_B).decode()
        self.assertIn('actor', raw)
        self.assertIn('device', raw)
        self.assertIn('ＤＥＭＯ', raw)
        self.assertNotEqual(CASES[TASK_A]['validator_version'], CASES[TASK_B]['validator_version'])
        self.assertIn('DEMO-OPS-B', CASES[TASK_B]['facts']['F-AUTH'])

    def test_student_contract_does_not_include_answers_or_hints(self):
        for key in CASES:
            material = student_material(key)
            self.assertNotIn('answer_version', material)
            self.assertNotIn('hints', material)
            self.assertFalse(material['requires_milestone_i'])
            self.assertEqual(material['execution_mode'], 'readonly_decision')
            self.assertEqual(len(material['classification']), 3)
            self.assertEqual(len(CASES[key]['hints']), 4)

    def test_resource_reference_is_closed(self):
        for key in ['../customer-v1.csv', 'https://example.invalid/file', '/etc/passwd']:
            with self.assertRaises(ValueError):
                asset_bytes(key)
