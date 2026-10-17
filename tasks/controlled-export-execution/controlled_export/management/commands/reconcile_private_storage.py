from django.core.management.base import BaseCommand, CommandError

from controlled_export.models import ProtectedArtifact
from controlled_export.storage import PrivateStorage


class Command(BaseCommand):
    help = "Verify that every registered private artifact exists and matches its immutable digest."

    def handle(self, *args, **options):
        storage = PrivateStorage()
        failures = []
        checked = 0
        for artifact in ProtectedArtifact.objects.order_by("created_at").iterator():
            checked += 1
            try:
                storage.ensure_integrity(artifact.private_storage_ref, artifact.output_content_hash)
            except Exception as exc:
                failures.append((str(artifact.output_asset_version_id), type(exc).__name__))
        self.stdout.write(f"checked={checked} failures={len(failures)}")
        for artifact_id, error in failures:
            self.stdout.write(f"artifact={artifact_id} error={error}")
        if failures:
            raise CommandError("Private storage reconciliation failed; access must remain paused")
