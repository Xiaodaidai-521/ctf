"""Additive reveal sources, without changing the frozen grant/consume boundary."""
from dataclasses import FrozenInstanceError, replace
import inspect
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase

from data_security.contracts import (
    CONTRACT_TYPES, CONTRACT_VERSION, PORT_TYPES, ContractViolation, ReasonCode,
    RevealRepository, RevealSource, RevealSourcePort,
)
from data_security.tests.fixtures import examples
from data_security.tests import test_import_isolation as isolation_fixture


class RevealSourceContractTests(TestCase):
    def setUp(self):
        self.source = examples()[RevealSource]

    def test_additive_source_and_port_leave_the_existing_consume_signature(self):
        self.assertEqual(CONTRACT_VERSION, 'ds.m0.v1')
        self.assertIn(RevealSource, CONTRACT_TYPES)
        self.assertIn(RevealSourcePort, PORT_TYPES)
        self.assertEqual(set(examples()), set(CONTRACT_TYPES))
        self.assertEqual(list(inspect.signature(RevealRepository.consume).parameters),
                         ['self', 'grant', 'context', 'expected_version', 'at'])
        self.assertEqual(list(inspect.signature(RevealSourcePort.read).parameters),
                         ['self', 'grant', 'context'])
        self.assertIn('RevealGrant', str(inspect.signature(RevealRepository.consume).return_annotation))

    def test_sources_are_immutable_server_only_and_not_implicitly_serializable(self):
        with self.assertRaises(FrozenInstanceError):
            self.source.object_version = 'v2'
        for operation, code in (
            (lambda: self.source.to_wire(), ReasonCode.SENSITIVE_SERIALIZATION_FORBIDDEN),
            (lambda: RevealSource.from_wire(self.source.to_wire(include_payload=True)),
             ReasonCode.TRUSTED_CONSTRUCTION_REQUIRED),
            (lambda: replace(self.source, fields=list(self.source.fields)), ReasonCode.INVALID_TYPE),
        ):
            with self.subTest(code=code), self.assertRaises(ContractViolation) as error:
                operation()
            self.assertIs(error.exception.code, code)

    def test_source_boundary_rejects_duplicate_or_other_object_fields(self):
        context, envelope = self.source.fields[0]
        cases = (
            ({'fields': ()}, ReasonCode.INVALID_VALUE),
            ({'fields': self.source.fields * 2}, ReasonCode.DUPLICATE_FIELD),
            ({'fields': self.source.fields * 17}, ReasonCode.INVALID_VALUE),
            ({'fields': ((replace(context, object_uuid='11111111-1111-4111-8111-111111111111'), envelope),)},
             ReasonCode.AUTHORIZATION_DENIED),
        )
        for changes, code in cases:
            with self.subTest(code=code), self.assertRaises(ContractViolation) as error:
                replace(self.source, **changes)
            self.assertIs(error.exception.code, code)
        newer = replace(self.source, object_version='v4')
        self.assertEqual(newer.fields[0][0], context)
        self.assertEqual(newer.fields[0][1], envelope)

    def test_new_contracts_still_import_with_no_environment_or_site_packages(self):
        root = Path(__file__).resolve().parents[3]
        program = isolation_fixture.PROBE + '\nassert contracts.RevealSourcePort._is_protocol\n'
        with tempfile.TemporaryDirectory(prefix='reveal-source-import-') as directory:
            result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', program, str(root / 'backend')],
                                    cwd=directory, env={}, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('"imported_contracts": 49', result.stdout)
            self.assertIn('"ports": 23', result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])
