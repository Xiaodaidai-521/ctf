"""Isolated restore, content verification and explicit traffic opening; no I/O here."""
from datetime import datetime, timedelta

from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, FrozenJSON, ProtectionError, ReasonCode, StoredObject,
)
from data_security.contracts.schema import require, utc


class RecoveryFlow:
    def __init__(self, *, backups, journal, verify_owners, clock, replay_governance=None):
        self.backups, self.journal, self.verify_owners, self.clock = backups, journal, verify_owners, clock
        self.replay_governance = replay_governance

    def run(self, operation, context, *, backup=None, approved_run_ref=None):
        try:
            require(operation in ('close', 'restore', 'verify', 'open', 'status'), ReasonCode.INVALID_VALUE)
            if operation == 'close':
                return self.journal.start(context)
            state = self.journal.read(context)
            if operation == 'status':
                return FrozenJSON(state)
            if operation == 'restore':
                require(state['state'] == 'closed' and type(backup) is StoredObject,
                        ReasonCode.SOURCE_NOT_APPROVED)
                state.update(state='restoring', backup=backup.to_wire())
                state['stages']['restore_started_at'] = self.clock().isoformat()
                self.journal.save(state, context)
                receipt = self.backups.restore(backup, context)
                if isinstance(receipt, ProtectionError):
                    return receipt  # Never reopen, infer zero effects, or erase a partial target.
                restoration = self.backups.read_restoration(receipt, context)
                if isinstance(restoration, ProtectionError):
                    return restoration
                require(restoration['backup_ref'] == backup.object_ref and
                        restoration['ciphertext_hash'] == backup.ciphertext_hash, ReasonCode.REPORT_MISMATCH)
                state.update(state='restored', restoration=restoration, restore_receipt=receipt.to_wire())
                state['stages']['restored_at'] = self.clock().isoformat()
                self.journal.save(state, context)
                return receipt
            require(state['state'] in ('restored', 'verified'), ReasonCode.SOURCE_NOT_APPROVED)
            if operation == 'open':
                require(state['state'] == 'verified' and approved_run_ref == state['run_ref'],
                        ReasonCode.AUTHORIZATION_DENIED)
            governance = state.get('governance')
            if governance is not None:
                require(self.replay_governance is not None and governance['state'] == 'applied',
                        ReasonCode.SOURCE_NOT_APPROVED)
            current = self.backups.source_inventory(context)
            if isinstance(current, ProtectionError):
                return current
            restored = state['restoration']
            expected = (governance['inventory'] if governance is not None else {
                'schema': restored['full_inventory']['schema'], 'private_files': restored['private_files'],
                'pending_files': restored['full_inventory']['pending_files']})
            require(current == expected, ReasonCode.REPORT_MISMATCH)
            replay_receipt = None
            if self.replay_governance is not None and governance is None:
                require(operation == 'verify', ReasonCode.SOURCE_NOT_APPROVED)
                # A partial replay remains closed; never adopt its changed inventory on retry.
                state['governance'] = {'state': 'applying'}
                self.journal.save(state, context)
                replay_receipt = self.replay_governance(context)
                if isinstance(replay_receipt, ProtectionError):
                    return replay_receipt
                require(type(replay_receipt) is AuditReceipt
                        and replay_receipt.durability is Durability.LEDGER_CONFIRMED
                        and replay_receipt.chain_version == 'ds.audit.v2', ReasonCode.AUDIT_UNAVAILABLE)
            verification = self.verify_owners(context)
            if isinstance(verification, ProtectionError):
                return verification
            require(verification['complete'] is True, ReasonCode.SOURCE_NOT_APPROVED)
            if replay_receipt is not None:
                governed = self.backups.source_inventory(context)
                if isinstance(governed, ProtectionError):
                    return governed
                state['governance'] = {'state': 'applied', 'receipt': replay_receipt.to_wire(),
                                       'inventory': governed}
            if operation == 'open':
                require(verification.get('opening_allowed') is True, ReasonCode.SOURCE_NOT_APPROVED)
            now = self.clock()
            utc(now)
            state.setdefault('verified_at', now.isoformat())
            state.update(state='verified', verification=verification, rechecked_at=now.isoformat())
            receipt = AuditReceipt(schema_version=AuditReceipt.SCHEMA,
                event_id='recovery-verify/' + state['run_ref'].split('/')[1], durability=Durability.DURABLE,
                stored_at=datetime.fromisoformat(state['verified_at']), chain_version=None,
                entry_ref=None, sequence=None, entry_hash=None, checkpoint_ref=None)
            state['verification_receipt'] = receipt.to_wire()
            if operation == 'open':
                snapshot = datetime.fromisoformat(restored['full_inventory']['snapshot_at'])
                outage = datetime.fromisoformat(state['outage_at'])
                utc(snapshot)
                utc(outage)
                rpo, rto = (outage - snapshot).total_seconds(), (now - outage).total_seconds()
                require(rpo >= 0 and rto >= 0, ReasonCode.REPORT_MISMATCH)
                started = datetime.fromisoformat(state['stages']['restore_started_at'])
                recovered = datetime.fromisoformat(state['stages']['restored_at'])
                verified = datetime.fromisoformat(state['verified_at'])
                state['metrics'] = {'scope': 'isolated-deployment', 'rpo_seconds': rpo, 'rto_seconds': rto,
                    'outage_to_restore_seconds': (started - outage).total_seconds(),
                    'restore_seconds': (recovered - started).total_seconds(),
                    'verification_seconds': (verified - recovered).total_seconds(),
                    'review_and_open_seconds': (now - verified).total_seconds(),
                    'rpo_target_seconds': 86400, 'rto_target_seconds': 14400,
                    'passed': rpo <= 86400 and rto <= 14400}
                if state['metrics']['passed']:
                    state.update(state='opened', opened_at=now.isoformat())
                self.journal.save(state, context)
                require(state['state'] == 'opened', ReasonCode.SOURCE_NOT_APPROVED)
            else:
                self.journal.save(state, context)
            return receipt
        except ContractViolation as error:
            code = error.code
        except (OSError, ValueError, TypeError, KeyError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
            retryable=False, trace_id=context.trace_id)


class BackupCycle:
    """A scheduler invokes this explicit entry; retention deletion remains a separate approval."""
    def __init__(self, *, backups, recipient, limits, clock, identity):
        require(backups.full_inventory, ReasonCode.SOURCE_NOT_APPROVED)
        self.backups, self.recipient, self.limits = backups, recipient, limits
        self.clock, self.identity = clock, identity

    def run_due(self, context):
        inventory = self.backups.retention_inventory(context, self.limits, full_only=True)
        if isinstance(inventory, ProtectionError):
            return inventory
        now = self.clock()
        utc(now)
        created = []
        for cadence, interval in (('daily', timedelta(hours=24)), ('weekly', timedelta(days=7))):
            previous = max((record.created_at for record in inventory if record.cadence == cadence), default=None)
            if previous is not None and now - previous < interval:
                continue
            stored = self.backups.create('snapshot/' + self.identity(), self.recipient, context, cadence=cadence)
            if isinstance(stored, ProtectionError):
                return stored
            created.append(stored)
        return tuple(created)
