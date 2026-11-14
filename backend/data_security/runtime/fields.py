"""Regular deployment adapter for the existing ProtectedModel business owners."""
import base64
import json

from data_security.runtime.crypto import get_cipher
from data_security.runtime.redaction import redact


class RuntimeFieldStorage:
    legacy_reads = True
    migrate_on_write = True
    protect_value = staticmethod(redact)

    def __init__(self, cipher=None):
        self.cipher = cipher or get_cipher()

    @staticmethod
    def context(instance, name, revision):
        return f'field/v1/{instance._meta.label_lower}/{instance.security_uuid}/{name}/{revision}'

    def seal(self, instance, name, value, revision, *, enroll=True):
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        ciphertext = self.cipher.encrypt(encoded, self.context(instance, name, revision))
        return {'revision': revision, 'envelope': {'format': 'runtime-aead-v1',
            'ciphertext': base64.b64encode(ciphertext).decode('ascii')}}

    def read(self, instance, name):
        if name not in instance.encrypted_fields:
            raise ValueError('FIELD_NOT_PROTECTED')
        if instance.security_state == 'legacy-v0':
            return getattr(instance, name)
        if not isinstance(instance.security_envelopes, dict):
            raise ValueError('CIPHERTEXT_INVALID')
        entry = instance.security_envelopes.get(name)
        if (instance.security_state != 'sealed-v1' or not isinstance(entry, dict)
                or set(entry) != {'revision', 'envelope'}
                or type(entry.get('revision')) is not int
                or not 0 < entry['revision'] <= instance.security_revision):
            raise ValueError('CIPHERTEXT_INVALID')
        envelope = entry.get('envelope', {})
        if not isinstance(envelope, dict) or set(envelope) != {'format', 'ciphertext'}:
            raise ValueError('CIPHERTEXT_INVALID')
        if envelope.get('format') != 'runtime-aead-v1':
            raise ValueError('FIELD_KEY_CONFIG_MISMATCH')
        try:
            encoded = base64.b64decode(envelope['ciphertext'], validate=True)
            value = self.cipher.decrypt(encoded, self.context(instance, name, entry['revision']))
            return json.loads(value.decode('utf-8'))
        except (KeyError, TypeError, UnicodeError) as error:
            raise ValueError('CIPHERTEXT_INVALID') from error

    def email_indexes(self, instance, normalized):
        return (self.cipher.email_index(normalized), '') if normalized else ('', '')
