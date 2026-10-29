"""Persistent ReviewRepository port, isolated per teaching scan, with DB CAS."""
import copy
import json
from django.db import transaction
from django.db.models import F
from mainline1.review import ReviewPrincipal, ReviewService, ReviewState
from mainline1.review_repository import decode_state, encode_state
from .common import Conflict
from .models import ReviewLedger, LabAttempt


class TeachingRepository:
    def __init__(self, scan):
        self.scan = scan

    @transaction.atomic
    def atomic(self, operation):
        ledger = ReviewLedger.objects.select_for_update().get(scan=self.scan)
        state = decode_state(ledger.state) if ledger.state else ReviewState()
        result = operation(state)
        encoded = encode_state(state)
        if len(json.dumps(encoded, ensure_ascii=False, allow_nan=False).encode()) > 4 * 1024 * 1024:
            raise Conflict('教学复核历史达到上限，请由教师处理；历史不删除。')
        if encoded != ledger.state:
            if not ReviewLedger.objects.filter(pk=ledger.pk, revision=ledger.revision).update(
                    state=encoded, revision=F('revision') + 1):
                raise Conflict('复核并发冲突，请刷新。')
        return copy.deepcopy(result)

    def read(self, operation):
        ledger = ReviewLedger.objects.get(scan=self.scan)
        state = decode_state(ledger.state) if ledger.state else ReviewState()
        return copy.deepcopy(operation(state))


class TeachingAccess:
    def __init__(self, scan):
        self.scan = scan

    def allowed(self, principal, asset, operation):
        scan = self.scan
        return (operation in ('register', 'review', 'read', 'read_review')
                and principal.actor_id == scan.lab.attempt.student_id
                and principal.domain_id == 'data-lab:' + str(scan.lab.attempt.attempt_id)
                and principal.environment == 'test' and principal.evaluation_run_id is None
                and asset == dict(asset_id=str(scan.asset_id), asset_version_id=str(scan.asset_version_id),
                                  content_hash='sha256:' + scan.asset_digest)
                and LabAttempt.objects.filter(pk=scan.lab_id, attempt__student_id=principal.actor_id).exists())


def review_service(scan):
    principal = ReviewPrincipal(scan.lab.attempt.student_id, 'data-lab:' + str(scan.lab.attempt.attempt_id), 'test')
    return ReviewService(TeachingRepository(scan), TeachingAccess(scan)), principal
