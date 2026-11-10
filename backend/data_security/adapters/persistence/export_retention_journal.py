"""Out-of-database export deletion facts, authenticated by the original audit key."""
from dataclasses import replace
import json
import os
from pathlib import Path
import stat

from data_security.contracts import (
    ContractViolation, Environment, FrozenJSON, KeyReference, KeyStatus, ProtectionError, ReasonCode,
)
from data_security.contracts.schema import digest, require
from .recovery_state import _read


class ExportRetentionJournal:
    FILE = '.export-retention.json'

    def __init__(self, *, root, scope_ref, sink, limits):
        self.root = Path(root)
        info = self.root.lstat()
        require(self.root.is_absolute() and self.root == self.root.resolve() and stat.S_ISDIR(info.st_mode)
                and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                ReasonCode.SOURCE_NOT_APPROVED)
        require(sink.crypto is not None and sink.checkpoint_root is not None
                and sink.context.environment is Environment.EVALUATION, ReasonCode.SOURCE_NOT_APPROVED)
        self.scope_ref, self.sink, self.limits = scope_ref, sink, limits
        self.context = replace(sink.context, field_ref='exports/retention-journal.v1')

    def start(self):
        # Explicit first use only. A missing journal during restore is never an empty deletion list.
        require(not any(self.root.iterdir()), ReasonCode.SOURCE_NOT_APPROVED)
        return self.save([])

    def read(self):
        document = FrozenJSON(json.loads(_read(self.root / self.FILE, self.limits.max_json_bytes)),
                              max_bytes=self.limits.max_json_bytes).to_value()
        require(type(document) is dict and set(document) == {
            'schema_version', 'scope_ref', 'facts', 'audit', 'key', 'authentication'}, ReasonCode.UNKNOWN_FIELD)
        require(document['schema_version'] in ('ds.export-retention-journal.v1', 'ds.export-retention-journal.v2')
                and document['scope_ref'] == self.scope_ref, ReasonCode.SOURCE_NOT_APPROVED)
        version = document['schema_version'].rsplit('.', 1)[1]
        context = replace(self.context, field_ref='exports/retention-journal.' + version)
        authentication = bytes.fromhex(document.pop('authentication'))
        signed = KeyReference.from_wire(document['key'])
        key = self.sink.keys.get(signed.key_ref)
        require(key is not None and signed == replace(key, status=KeyStatus.ACTIVE), ReasonCode.KEY_UNAVAILABLE)
        encoded = json.dumps(document, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')
        require(len(authentication) == 32 and self.sink.crypto.verify_authentication(
            encoded, authentication, context, key) is True, ReasonCode.AUDIT_UNAVAILABLE)
        facts = document['facts']
        require(type(facts) is list and len(facts) <= self.limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
        for fact in facts:
            require(type(fact) is dict and (set(fact) == {'export', 'delivery', 'intent'} or
                    (version == 'v2' and set(fact) == {'export', 'delivery', 'intent', 'candidate'})),
                    ReasonCode.UNKNOWN_FIELD)
            item = fact['export']
            require(type(item) is dict and set(item) == {
                'execution_id', 'binding_hash', 'report_hash', 'object_ref', 'object_version', 'ciphertext_hash',
                'size_bytes', 'created_at', 'expires_at', 'owner_state', 'registration_event_ref', 'delivery_hash'},
                ReasonCode.UNKNOWN_FIELD)
            require(('candidate' in fact) == (item['report_hash'] is None)
                    and ('candidate' not in fact or fact['delivery'] is None), ReasonCode.REPORT_MISMATCH)
            require(type(item['object_ref']) is str and item['object_ref'].startswith('private/'),
                    ReasonCode.SOURCE_NOT_APPROVED)
            digest(item['object_ref'].removeprefix('private/'))
        require(len({fact['export']['execution_id'] for fact in facts}) == len(facts),
                ReasonCode.REPORT_MISMATCH)
        return document

    def save(self, facts):
        require(len(facts) <= self.limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
        mirror = self.sink.capture_recovery(self.limits)
        if isinstance(mirror, ProtectionError):
            raise ContractViolation(mirror.code)
        version = 'v2' if any('candidate' in fact for fact in facts) else 'v1'
        context = replace(self.context, field_ref='exports/retention-journal.' + version)
        document = {'schema_version': 'ds.export-retention-journal.' + version, 'scope_ref': self.scope_ref,
                    'facts': facts, 'audit': mirror.to_value(), 'key': self.sink.key.to_wire()}
        encoded = json.dumps(document, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')
        authentication = self.sink.crypto.authenticate(encoded, context, self.sink.key)
        require(type(authentication) is bytes and len(authentication) == 32, ReasonCode.AUDIT_UNAVAILABLE)
        persisted = FrozenJSON({**document, 'authentication': authentication.hex()},
                               max_bytes=self.limits.max_json_bytes)
        encoded = json.dumps(persisted.to_value(), sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf-8')
        partial = self.root / (self.FILE + '.partial')
        with os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        partial.replace(self.root / self.FILE)
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return document
