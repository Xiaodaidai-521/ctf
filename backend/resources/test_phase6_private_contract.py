"""The shared PrivateStore contract against isolated PostgreSQL and private files."""
from pathlib import Path
import tempfile

from django.db import connection
from django.test import TestCase

from data_security.adapters.persistence.models import PrivateObject
from data_security.adapters.persistence.private_store import DjangoPrivateStore
from data_security.contracts import Environment
from data_security.tests.private_store_contract import PrivateStoreContract


class PostgresPrivateStoreContractTests(PrivateStoreContract, TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        temporary = tempfile.TemporaryDirectory(prefix='private-contract-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.root.chmod(0o700)
        super().setUp()

    def make_store(self):
        return DjangoPrivateStore(root=self.root, crypto=self.crypto, environment=Environment.TEST)

    def path(self, stored):
        return self.root / (stored.object_ref.removeprefix('private/') + '.sealed')

    def blob(self, stored):
        return self.path(stored).read_bytes()

    def replace_blob(self, stored, encoded):
        self.path(stored).write_bytes(encoded)

    def remove_blob(self, stored):
        self.path(stored).unlink()

    def remove_record(self, stored):
        PrivateObject.objects.filter(object_ref=stored.object_ref).delete()

    def resources(self):
        files = list(self.root.iterdir())
        return PrivateObject.objects.count(), len(files), sum(path.stat().st_size for path in files)
