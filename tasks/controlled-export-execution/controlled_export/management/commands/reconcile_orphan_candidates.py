from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from controlled_export.models import ExecutionAttempt, ProtectedArtifact
from controlled_export.storage import PrivateStorage


class Command(BaseCommand):
    help = "List unreferenced private files; optionally delete them after a lease-safe grace period."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="Delete confirmed stale candidates")
        parser.add_argument("--grace-seconds", type=int, default=3600)

    def handle(self, *args, **options):
        if options["grace_seconds"] < settings.CONTROLLED_EXPORT_LEASE_SECONDS:
            raise ValueError("grace-seconds must cover the configured lease window")
        storage = PrivateStorage()
        cutoff = timezone.now() - timedelta(seconds=options["grace_seconds"])
        protected_candidates = set(
            ExecutionAttempt.objects.filter(
                status="running", lease_expires_at__gt=timezone.now()
            ).exclude(candidate_storage_ref="").values_list("candidate_storage_ref", flat=True)
        )
        registered_artifacts = set(
            ProtectedArtifact.objects.values_list("private_storage_ref", flat=True)
        )
        orphans = []
        for area, protected in (
            (storage.root / "candidates", protected_candidates),
            (storage.root / "artifacts", registered_artifacts),
        ):
            if not area.exists():
                continue
            for path in area.rglob("*"):
                if not path.is_file() or path.is_symlink():
                    continue
                reference = path.relative_to(storage.root).as_posix()
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                if reference not in protected and modified <= cutoff:
                    orphans.append(path)
        deleted = 0
        if options["delete"]:
            for path in orphans:
                path.unlink()
                deleted += 1
        self.stdout.write(f"orphan_private_files={len(orphans)} deleted={deleted}")
