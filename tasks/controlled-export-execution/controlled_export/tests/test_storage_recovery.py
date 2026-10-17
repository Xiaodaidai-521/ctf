import os
import time
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from controlled_export.errors import ContractError
from controlled_export.storage import PrivateStorage

from .helpers import IsolatedStorageMixin


class StorageRecoveryTests(IsolatedStorageMixin, TestCase):
    def test_path_traversal_and_absolute_references_are_rejected(self):
        storage = PrivateStorage()
        for reference in ("../outside.csv", "/absolute.csv", "a/../../outside.csv"):
            with self.subTest(reference=reference), self.assertRaises(ContractError):
                storage.path(reference)

    def test_finalized_orphan_is_reported_before_optional_cleanup(self):
        storage = PrivateStorage()
        orphan = storage.path("artifacts/orphan/output.csv")
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b"synthetic")
        old = time.time() - 7200
        os.utime(orphan, (old, old))

        dry_output = StringIO()
        call_command(
            "reconcile_orphan_candidates",
            grace_seconds=3600,
            stdout=dry_output,
        )
        self.assertIn("orphan_private_files=1 deleted=0", dry_output.getvalue())
        self.assertTrue(orphan.exists())

        delete_output = StringIO()
        call_command(
            "reconcile_orphan_candidates",
            grace_seconds=3600,
            delete=True,
            stdout=delete_output,
        )
        self.assertIn("orphan_private_files=1 deleted=1", delete_output.getvalue())
        self.assertFalse(orphan.exists())
