import unittest

from django.test import SimpleTestCase

from evaluation_center.acceptance import FACTOR_SETS, SCENARIOS, VERSION, test_labels


class AcceptanceManifestTests(SimpleTestCase):
    def test_scenarios_one_to_ten_are_versioned_and_dependencies_explicit(self):
        self.assertEqual(VERSION, 'm8-phase1-acceptance/2')
        self.assertEqual([row['id'] for row in SCENARIOS], list(range(1, 11)))
        for row in SCENARIOS:
            self.assertTrue(row['tests'])
            self.assertIn('dependencies', row)
        self.assertTrue(SCENARIOS[7]['dependencies'])
        self.assertTrue(SCENARIOS[9]['dependencies'])

    def test_every_fixed_selector_resolves_to_real_tests(self):
        for label in {label for row in SCENARIOS for label in row['tests']}:
            with self.subTest(label=label):
                loader = unittest.TestLoader()
                suite = loader.loadTestsFromName(label)
                self.assertFalse(loader.errors, loader.errors)
                self.assertGreater(suite.countTestCases(), 0)

    def test_original_synthetic_collection_remains_byte_equivalent(self):
        from evaluation_center.evaluation_fixtures import DATASET_VERSION, regression_cases
        from evaluation_center.evaluations import digest_of
        self.assertEqual(DATASET_VERSION, 'm8-synthetic-regression/1')
        self.assertEqual(digest_of(regression_cases()), '4de3c74803971973b2028c4d1600175120e6f640aafd389bf2f1a942790ff5b1')
        self.assertEqual(len(regression_cases()), 25)

    def test_live_factor_registration_matches_server_collection(self):
        from evaluation_center import live_fixtures
        original, live = FACTOR_SETS
        self.assertFalse(original['provider_calls'])
        self.assertEqual(live['dataset_version'], live_fixtures.DATASET_VERSION)
        self.assertEqual(live['case_count'], len(live_fixtures.regression_cases()))
        self.assertEqual(set(live['factors']), set(live_fixtures.FACTORS))
        self.assertEqual(set(live['models']), set(live_fixtures.MODELS))
        self.assertEqual(set(live['prompts']), set(live_fixtures.PROMPTS))
        self.assertTrue(live['automated_tests_use_mock_transport'])
        for label in live['tests']:
            self.assertIn(label, test_labels())

    def test_runner_labels_do_not_repeat_nested_suites(self):
        labels = test_labels()
        self.assertTrue(labels)
        self.assertEqual(len(labels), len(set(labels)))
        self.assertFalse(any(a.startswith(b + '.') for a in labels for b in labels if a != b))
