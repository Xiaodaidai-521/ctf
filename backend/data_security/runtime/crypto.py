"""Authenticated at-rest encryption with a persistent, service-private key file."""
import hashlib
import hmac
import os
from functools import lru_cache
from pathlib import Path
import secrets
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from data_security.adapters.private_permissions import is_private_path

MAGIC = b'ctf-aead-v1\x00'


def sync_directory(path):
    """Persist new key/backup directory entries before database writes commit."""
    if os.name == 'nt':
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def restrict_path(path, *, directory=False):
    if os.name != 'nt':
        path.chmod(0o700 if directory else 0o600)
        return
    import win32api
    import win32con
    import win32security as security
    token = security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = security.GetTokenInformation(token, security.TokenUser)[0]
    finally:
        token.Close()
    acl = security.ACL()
    acl.AddAccessAllowedAce(security.ACL_REVISION, 0x1F01FF, sid)  # FILE_ALL_ACCESS
    security.SetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
        security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, acl, None)


def create_private_directory(path):
    """Create the final directory with private permissions from the outset."""
    path = Path(path)
    if not path.exists():
        if not path.parent.exists():
            create_private_directory(path.parent)
        if os.name != 'nt':
            try:
                path.mkdir(mode=0o700)
            except FileExistsError:
                pass
        else:
            import pywintypes
            import win32api
            import win32con
            import win32file
            import win32security as security
            token = security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
            try:
                sid = security.GetTokenInformation(token, security.TokenUser)[0]
            finally:
                token.Close()
            acl = security.ACL()
            acl.AddAccessAllowedAce(security.ACL_REVISION, 0x1F01FF, sid)
            descriptor = security.SECURITY_DESCRIPTOR()
            descriptor.SetSecurityDescriptorDacl(True, acl, False)
            descriptor.SetSecurityDescriptorControl(security.SE_DACL_PROTECTED, security.SE_DACL_PROTECTED)
            attributes = pywintypes.SECURITY_ATTRIBUTES()
            attributes.SECURITY_DESCRIPTOR = descriptor
            try:
                win32file.CreateDirectory(str(path), attributes)
            except pywintypes.error as error:
                if error.winerror != 183:  # ERROR_ALREADY_EXISTS
                    raise
        sync_directory(path.parent)
    if not is_private_path(path, directory=True):
        raise ImproperlyConfigured('DATA_PROTECTION_KEY_DIRECTORY_PERMISSIONS')


def load_key(path):
    path = Path(path).absolute()
    # Keys may never be placed in public media or the source checkout.
    for forbidden in (Path(settings.MEDIA_ROOT).resolve(), Path(settings.BASE_DIR).resolve().parent):
        if path.resolve().is_relative_to(forbidden):
            raise ImproperlyConfigured('DATA_PROTECTION_KEY_FILE must be outside the source tree and media root')
    parent = path.parent
    create_private_directory(parent)
    # Packaged Windows processes may redirect a lexical C:\\AppData path to
    # another drive. Publishing through that alias can fail with EXDEV even
    # when both names share a parent. Use its verified physical directory for
    # both names; keep the final component unresolved so symlinks stay rejected.
    parent = parent.resolve()
    path = parent / path.name
    marker = parent / (path.name + '.initialized')
    if not path.exists():
        if marker.exists():
            raise ImproperlyConfigured('DATA_PROTECTION_KEY_MISSING: restore the existing key; do not regenerate it')
        # Publish a complete key atomically. Creating the final name before
        # writing it lets concurrent application workers observe an empty key
        # and fail startup. Windows rename is exclusive when the destination
        # exists, so a competing worker's existing key cannot be overwritten.
        # POSIX rename can overwrite, so use an exclusive hard link there.
        fd, staged_name = tempfile.mkstemp(prefix='.storage-key-', dir=parent)
        staged = Path(staged_name)
        try:
            with os.fdopen(fd, 'wb') as stream:
                restrict_path(staged)
                stream.write(secrets.token_bytes(64))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                if os.name == 'nt':
                    os.rename(staged, path)
                else:
                    os.link(staged, path)
            except FileExistsError:
                pass
            sync_directory(parent)
        finally:
            staged.unlink(missing_ok=True)
    if not is_private_path(path):
        raise ImproperlyConfigured('DATA_PROTECTION_KEY_PERMISSIONS')
    material = path.read_bytes()
    if len(material) != 64:
        raise ImproperlyConfigured('DATA_PROTECTION_KEY_INVALID')
    if not marker.exists():
        try:
            fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as stream:
                restrict_path(marker)
                stream.write(b'v1\n')
                stream.flush()
                os.fsync(stream.fileno())
            sync_directory(parent)
    return material


class RuntimeCipher:
    def __init__(self, material):
        if not isinstance(material, bytes) or len(material) != 64:
            raise ValueError('DATA_PROTECTION_KEY_INVALID')
        self._aes = AESGCM(material[:32])
        self._index_key = material[32:]

    def encrypt(self, value: bytes, context: str) -> bytes:
        nonce = secrets.token_bytes(12)
        return MAGIC + nonce + self._aes.encrypt(nonce, value, context.encode('utf-8'))

    def decrypt(self, value: bytes, context: str) -> bytes:
        if not value.startswith(MAGIC) or len(value) < len(MAGIC) + 28:
            raise ValueError('CIPHERTEXT_INVALID')
        offset = len(MAGIC)
        try:
            return self._aes.decrypt(value[offset:offset + 12], value[offset + 12:], context.encode('utf-8'))
        except InvalidTag:
            raise ValueError('CIPHERTEXT_INVALID') from None

    def email_index(self, normalized):
        return 'runtime-v1:' + hmac.new(self._index_key,
            b'ctf/email/exact/v1\x00' + normalized.encode('utf-8'), hashlib.sha256).hexdigest()


@lru_cache(maxsize=4)
def _cipher_for_path(path):
    return RuntimeCipher(load_key(path))


def get_cipher():
    return _cipher_for_path(str(settings.DATA_PROTECTION_KEY_FILE))
