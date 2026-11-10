"""Same-database short UoW. Files and network delivery are never enlisted."""
from django.db import transaction


class DjangoUnitOfWork:
    def __enter__(self):
        self._committed = False
        self._atomic = transaction.atomic()
        self._atomic.__enter__()
        return self

    def commit(self):
        # The database commits on a successful exit, not before the remaining work.
        self._committed = True

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None and not self._committed:
            transaction.set_rollback(True)
        return self._atomic.__exit__(exc_type, exc, traceback)
