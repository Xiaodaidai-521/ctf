"""D8 isolated retention: seven daily slots plus four weekly slots, not a TTL."""
from datetime import timezone

from data_security.contracts import ProtectionError, ReasonCode


class BackupRetention:
    def __init__(self, *, backups, limits):
        self.backups, self.limits = backups, limits

    def preview(self, context):
        inventory = self.backups.retention_inventory(context, self.limits)
        if isinstance(inventory, ProtectionError):
            return inventory
        slots = {'daily': set(), 'weekly': set()}
        capacities = {'daily': 7, 'weekly': 4}
        expired = []
        for record in sorted(inventory,
                key=lambda item: (item.created_at, item.backup.object_ref), reverse=True):
            day = record.created_at.astimezone(timezone.utc).date()
            slot = day if record.cadence == 'daily' else day.isocalendar()[:2]
            retained = slots[record.cadence]
            if slot not in retained and len(retained) < capacities[record.cadence]:
                retained.add(slot)
            else:
                expired.append(record)
        return tuple(reversed(expired))

    def apply(self, approved, context):
        """Re-read before an explicitly approved batch; stop on any unknown result."""
        current = self.preview(context)
        if isinstance(current, ProtectionError):
            return current
        if current != approved:
            return ProtectionError(schema_version=ProtectionError.SCHEMA,
                code=ReasonCode.REPORT_MISMATCH, retryable=False, trace_id=context.trace_id)
        receipts = []
        for record in current:
            result = self.backups.retire(record, context)
            if isinstance(result, ProtectionError):
                return result
            receipts.append(result)
        return tuple(receipts)
