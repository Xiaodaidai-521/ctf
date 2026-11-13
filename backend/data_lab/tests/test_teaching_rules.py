"""Synthetic markers cannot be repurposed as a production classification policy."""
from uuid import uuid4

from django.test import SimpleTestCase

from data_lab.catalog import TASK_A
from data_lab.scanning import configuration, scan_registered
from mainline1.classification import RuleConfiguration
from mainline1.parsing import InputError


class TeachingRuleBoundaryTests(SimpleTestCase):
    def test_synthetic_rules_reject_development_and_real_category_policy(self):
        value = configuration().data()
        value['allowed_environments'] = ['development']
        with self.assertRaisesRegex(InputError, 'RULE_IMPLEMENTATION_UNSUPPORTED'):
            RuleConfiguration.load(value)
        value = configuration().data()
        value['rules'][0]['category_id'] = 'EMAIL'
        with self.assertRaisesRegex(InputError, 'RULE_IMPLEMENTATION_UNSUPPORTED'):
            RuleConfiguration.load(value)

    def test_synthetic_scan_rejects_non_teaching_domain(self):
        request = dict(task_key=TASK_A, domain='production-customer-data',
                       scan_id=str(uuid4()), asset_id=str(uuid4()),
                       asset_version_id=str(uuid4()), actor_id=1,
                       created_at='2026-11-13T01:00:00Z')
        with self.assertRaisesRegex(InputError, 'RULE_IMPLEMENTATION_UNSUPPORTED'):
            scan_registered(request)
