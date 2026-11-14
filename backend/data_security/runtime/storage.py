"""Private at-rest storage for resource files, covers and feedback attachments."""
import os
from pathlib import Path, PurePosixPath
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible

from .crypto import create_private_directory, get_cipher, restrict_path, sync_directory
from data_security.adapters.private_permissions import is_private_path


def enabled():
    return bool(getattr(settings, 'DATA_PROTECTION_ENABLED', False))


@deconstructible
class EncryptedFileSystemStorage(Storage):
    """Only ciphertext is written; callers read through the existing authorized APIs.

    Old names remain readable during the resumable migration. Public media serving
    excludes these namespaces, including their legacy files.
    """

    @staticmethod
    def _name(name):
        path = PurePosixPath(str(name).replace('\\', '/'))
        if path.is_absolute() or '..' in path.parts or not path.parts or ':' in str(path):
            raise SuspiciousFileOperation('Invalid private file name')
        return str(path)

    @staticmethod
    def _legacy():
        return FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)

    @staticmethod
    def _private():
        return FileSystemStorage(location=Path(settings.DATA_PROTECTION_ROOT) / 'files')

    def _path(self, name):
        return Path(self._private().path(self._name(name)))

    def _prepare_directory(self, directory):
        root = Path(settings.DATA_PROTECTION_ROOT).absolute()
        if root.resolve().is_relative_to(Path(settings.MEDIA_ROOT).resolve()):
            raise SuspiciousFileOperation('Private storage must be outside public media')
        for current in reversed((directory, *directory.parents)):
            if not current.is_relative_to(root):
                continue
            try:
                create_private_directory(current)
            except ImproperlyConfigured:
                raise SuspiciousFileOperation('Private storage permissions are invalid') from None

    def _write_exact(self, name, value):
        path = self._path(name)
        self._prepare_directory(path.parent)
        encrypted = get_cipher().encrypt(value, 'ctf/private-file/' + name)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, 'wb') as target:
                restrict_path(path)
                target.write(encrypted)
                target.flush()
                os.fsync(target.fileno())
            sync_directory(path.parent)
        except BaseException:
            # A retry must not inherit an incomplete file created by this write.
            # The legacy migration source remains untouched until verification.
            path.unlink(missing_ok=True)
            raise

    def _save(self, name, content):
        if not enabled():
            return self._legacy().save(name, content)
        original = PurePosixPath(self._name(name))
        # Avoid storing personal information from filenames in storage paths.
        suffix = '.tar.gz' if original.name.lower().endswith('.tar.gz') else original.suffix[-20:]
        name = str(original.parent / (uuid4().hex + suffix))
        content.seek(0)
        self._write_exact(name, content.read())
        return name

    def _open(self, name, mode='rb'):
        if mode not in ('r', 'rb'):
            raise ValueError('Private files are immutable; save a new file instead')
        name = self._name(name)
        if not enabled():
            return self._legacy().open(name, mode)
        path = self._path(name)
        if not path.exists():
            return self._legacy().open(name, mode)
        if not is_private_path(path) or path.stat().st_nlink != 1:
            raise SuspiciousFileOperation('Private file permissions are invalid')
        value = get_cipher().decrypt(path.read_bytes(), 'ctf/private-file/' + name)
        return ContentFile(value, name=name)

    def exists(self, name):
        name = self._name(name)
        return (enabled() and self._private().exists(name)) or self._legacy().exists(name)

    def size(self, name):
        with self.open(name) as stream:
            return stream.size

    def delete(self, name):
        name = self._name(name)
        if enabled() and self._private().exists(name):
            self._private().delete(name)
        else:
            self._legacy().delete(name)

    def path(self, name):
        name = self._name(name)
        if enabled() and self._private().exists(name):
            return self._private().path(name)
        return self._legacy().path(name)

    def url(self, name):
        if enabled():
            name = self._name(name)
            from resources.models import Resource
            from feedback_center.models import FeedbackAttachment
            for field, suffix in (('file', 'download/'), ('cover_image', 'cover/download/')):
                resource = Resource.objects.filter(**{field: name}).only('pk').first()
                if resource is not None:
                    return f'/api/resources/{resource.pk}/{suffix}'
            attachment = FeedbackAttachment.objects.filter(file=name).select_related('ticket').first()
            if attachment is not None:
                return f'/api/feedback/{attachment.ticket.feedback_id}/attachments/{attachment.attachment_id}/download/'
            raise ValueError('Private files require an authenticated download endpoint')
        return self._legacy().url(self._name(name))

    def protection_status(self, name, *, verify=True):
        if not name:
            return {'storage': 'empty', 'present': False}
        if not enabled() or not self._path(name).exists():
            return {'storage': 'legacy', 'present': True}
        try:
            if verify:
                with self.open(name):
                    pass
            else:
                # List projections check the envelope and filesystem permissions;
                # authorized downloads still authenticate the entire ciphertext.
                from .crypto import MAGIC
                path = self._path(name)
                if not is_private_path(path) or path.stat().st_nlink != 1:
                    raise SuspiciousFileOperation('Private file permissions are invalid')
                with path.open('rb') as stream:
                    if stream.read(len(MAGIC)) != MAGIC:
                        raise ValueError('CIPHERTEXT_INVALID')
        except (OSError, ValueError, SuspiciousFileOperation):
            return {'storage': 'unknown', 'present': True}
        return {'storage': 'encrypted', 'present': True}

    def migrate(self, name, *, apply=False):
        """Preserve the DB name and remove legacy bytes only after exact verification."""
        if not enabled():
            raise ValueError('DATA_PROTECTION_ENABLED is required')
        name = self._name(name)
        legacy = self._legacy()
        path = self._path(name)
        if not legacy.exists(name):
            with self.open(name):
                pass
            return 'encrypted'
        if not apply:
            return 'legacy'
        with legacy.open(name, 'rb') as stream:
            value = stream.read()
        if not path.exists():
            self._write_exact(name, value)
        with self.open(name) as verified:
            if verified.read() != value:
                raise ValueError('PRIVATE_FILE_MIGRATION_MISMATCH')
        # The encrypted copy is authenticated before deleting this exact source.
        legacy.delete(name)
        return 'migrated'


def protected_storage():
    return EncryptedFileSystemStorage()


def migrate_private_files(*, apply=False):
    from resources.models import Resource
    from feedback_center.models import FeedbackAttachment
    result = {'encrypted': 0, 'legacy': 0, 'migrated': 0, 'missing': 0, 'failed': 0}
    for model, fields in ((Resource, ('file', 'cover_image')), (FeedbackAttachment, ('file',))):
        for row in model.objects.only('pk', *fields).iterator(chunk_size=100):
            for field in fields:
                file = getattr(row, field)
                if not file:
                    continue
                try:
                    state = file.storage.migrate(file.name, apply=apply)
                except FileNotFoundError:
                    state = 'missing'
                except (OSError, ValueError, SuspiciousFileOperation):
                    state = 'failed'
                result[state] += 1
    return result
