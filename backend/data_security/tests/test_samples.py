from collections import Counter
import ipaddress
import unittest

from data_security.contracts import Category, Metric, ReasonCode
from .fixtures import dto
from .synthetic import dataset_fingerprint, samples


class SampleTests(unittest.TestCase):
    def test_four_families_have_fifty_positive_and_negative_cases_each(self):
        data = [case for case in samples() if case.teaching is None]
        counts = Counter((case.category, case.positive) for case in data)
        self.assertEqual(len(data), 400)
        for category in Category:
            for positive in (True, False):
                self.assertEqual(counts[category, positive], 50)
                self.assertEqual(len({s.text for s in data if (s.category, s.positive) == (category, positive)}), 50)

    def test_teaching_has_separate_trusted_and_self_asserted_provenance(self):
        data = [case for case in samples() if case.teaching is not None]
        self.assertEqual(len(data), 100)
        self.assertEqual(Counter(case.expected_exception for case in data), {True: 50, False: 50})
        for case in data:
            self.assertEqual(case.expected_exception, case.teaching == 'trusted-published')
            self.assertIsNotNone(case.source_ref)
            self.assertIsNotNone(case.source_version)

    def test_all_ids_are_unique_and_generation_is_deterministic(self):
        data = samples()
        self.assertEqual(len({case.sample_id for case in data}), 500)
        self.assertEqual(samples(), data)
        self.assertEqual(dataset_fingerprint(), dataset_fingerprint())
        self.assertEqual(len(dataset_fingerprint()), 64)

    def test_positive_email_and_ip_values_use_reserved_documentation_space(self):
        for case in samples():
            if not case.positive:
                continue
            if case.category is Category.EMAIL:
                self.assertTrue(case.text.endswith('.invalid'))
            if case.category is Category.IPV4:
                address = ipaddress.ip_address(case.text.rsplit(' ', 1)[1])
                self.assertTrue(any(address in ipaddress.ip_network(cidr) for cidr in
                                    ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24')))

    def test_card_candidate_fixture_labels_match_checksum_not_region(self):
        for case in samples():
            if case.category is not Category.CARD:
                continue
            digits = [int(char) for char in reversed(case.text)]
            doubled = [number * 2 if i % 2 else number for i, number in enumerate(digits)]
            valid = sum(number - 9 if number > 9 else number for number in doubled) % 10 == 0
            self.assertEqual(valid, case.positive)
            self.assertTrue(13 <= len(case.text) <= 19)

    def test_secret_samples_are_generated_never_activated_and_repr_redacted(self):
        for case in samples():
            if case.category is Category.SECRET and case.positive:
                self.assertTrue(case.text.startswith('api_key=DS_TEST_ONLY_'))
            self.assertNotIn(case.text, repr(case))

    def test_metrics_use_explicit_version_and_null_for_no_observations(self):
        metric = dto(Metric, numerator=0, denominator=0, version='dataset-only-v1',
                     zero_reason=ReasonCode.UNSUPPORTED_SCOPE)
        self.assertIsNone(metric.ratio)
        # Phase 1 supplies fixtures and metric definitions, never detector scores.
        self.assertEqual(metric.numerator, metric.denominator)
