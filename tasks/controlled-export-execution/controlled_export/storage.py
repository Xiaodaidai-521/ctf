import hashlib
import hmac
import os
from pathlib import Path, PurePosixPath

from django.conf import settings

from .errors import ArtifactIntegrityError, ContractError


class PrivateStorage:
    def __init__(self, root=None):
        self.root = Path(root or settings.CONTROLLED_EXPORT_PRIVATE_ROOT).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _absolute(self, reference):
        if not isinstance(reference, str) or not reference:
            raise ContractError("Storage reference is required", code="STORAGE_REF_INVALID")
        pure = PurePosixPath(reference)
        if pure.is_absolute() or ".." in pure.parts or "" in pure.parts:
            raise ContractError("Storage reference escapes the private root", code="STORAGE_REF_INVALID")
        target = (self.root / Path(*pure.parts)).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ContractError("Storage reference escapes the private root", code="STORAGE_REF_INVALID") from exc
        current = self.root
        for part in pure.parts[:-1]:
            current = current / part
            if current.exists() and current.is_symlink():
                raise ContractError("Symlinks are not allowed in private storage", code="STORAGE_SYMLINK_REJECTED")
        return target

    @staticmethod
    def _reference(*parts):
        return PurePosixPath(*(str(part) for part in parts)).as_posix()

    def write_candidate(self, execution_id, attempt_id, suffix, content):
        reference = self._reference("candidates", execution_id, f"{attempt_id}{suffix}")
        target = self._absolute(reference)
        target.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(target, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return reference

    def finalize_candidate(self, candidate_reference, execution_id, output_id, suffix):
        candidate = self._absolute(candidate_reference)
        if not candidate.is_file() or candidate.is_symlink():
            raise ArtifactIntegrityError("Candidate file is unavailable", code="CANDIDATE_MISSING")
        reference = self._reference("artifacts", execution_id, f"{output_id}{suffix}")
        target = self._absolute(reference)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ExecutionError("Artifact target already exists")
        os.replace(candidate, target)
        return reference

    def sha256(self, reference):
        target = self._absolute(reference)
        if not target.is_file() or target.is_symlink():
            raise ArtifactIntegrityError("Private artifact is missing", code="ARTIFACT_MISSING")
        digest = hashlib.sha256()
        with target.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def ensure_integrity(self, reference, expected_hash):
        actual = self.sha256(reference)
        if not hmac.compare_digest(actual, expected_hash):
            raise ArtifactIntegrityError("Private artifact digest mismatch")
        return self._absolute(reference)

    def open(self, reference):
        target = self._absolute(reference)
        if not target.is_file() or target.is_symlink():
            raise ArtifactIntegrityError("Private artifact is missing", code="ARTIFACT_MISSING")
        return target.open("rb")

    def path(self, reference):
        return self._absolute(reference)


class ExecutionError(RuntimeError):
    pass
