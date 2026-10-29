from django.test import SimpleTestCase

from evaluation_center.metrics import SOURCE_STATUS, metric


class MetricContractTests(SimpleTestCase):
    def test_empty_is_not_zero(self):
        value = metric(0, 0)
        self.assertIsNone(value['value'])
        self.assertEqual(value['status'], 'no_data')

    def test_expected_but_unobserved_is_not_empty(self):
        value = metric(None, 0, missing=2)
        self.assertEqual(value['status'], 'not_connected')
        self.assertIsNone(value['value'])

    def test_unknown_cost_is_not_zero(self):
        value = metric(None, 3, missing=3)
        self.assertIsNone(value['numerator'])
        self.assertIsNone(value['value'])
        self.assertEqual(value['missing'], 3)

    def test_envelope_keeps_scope_and_provenance(self):
        value = metric(2, 4, 1, window={'start': '2026-01-01', 'end': '2026-02-01'},
                       versions={'task': 'v1', 'catalog': 'c1'}, source='offline')
        self.assertEqual(value['value'], .5)
        self.assertEqual(value['versions']['catalog'], 'c1')
        self.assertEqual(value['source'], 'offline')
        self.assertEqual(value['status'], 'partial')

    def test_stage_boundaries_are_not_successes(self):
        self.assertEqual(SOURCE_STATUS['module3'], 'not_connected')
        self.assertEqual(SOURCE_STATUS['module4'], 'not_connected')
        self.assertEqual(SOURCE_STATUS['module5'], 'not_connected')
        self.assertEqual(SOURCE_STATUS['actual_protection'], 'not_evaluated')

    def test_invalid_counts_rejected(self):
        with self.assertRaises(ValueError):
            metric(0, -1)
        with self.assertRaises(ValueError):
            metric(0, 1, -1)
