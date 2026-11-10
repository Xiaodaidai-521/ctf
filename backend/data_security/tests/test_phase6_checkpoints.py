from dataclasses import replace
from datetime import timedelta
from unittest import TestCase

from data_security.contracts import AuditCheckpoint, ContractViolation, KeyStatus, canonical_bytes
from data_security.tests.fixtures import examples


class AuditCheckpointContractTests(TestCase):
    def test_closed_wire_roundtrip_and_content_excludes_authentication(self):
        value = examples()[AuditCheckpoint]
        self.assertEqual(AuditCheckpoint.from_json(canonical_bytes(value)), value)
        self.assertNotIn('authentication', value.content())
        with self.assertRaises(ContractViolation):
            AuditCheckpoint.from_wire(dict(value.to_wire(), raw_report='not accepted'))

    def test_requires_exact_v2_receipt_active_signing_metadata_and_digest(self):
        value = examples()[AuditCheckpoint]
        for change in ({'chain_identity': 'not-a-digest'}, {'authentication': b''},
                       {'checkpointed_at': value.receipt.stored_at - timedelta(seconds=1)},
                       {'key': replace(value.key, status=KeyStatus.READ_ONLY)},
                       {'receipt': replace(value.receipt, chain_version='v1')},
                       {'receipt': replace(value.receipt, checkpoint_ref='checkpoint/recursive')}):
            with self.assertRaises(ContractViolation):
                replace(value, **change)
