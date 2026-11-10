"""Identical RiskPort cases for independent memory state and the original PG writer."""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

from data_security.contracts import ContractViolation, ExecutionBinding, ProtectionError, QuotaReceipt, ReasonCode
from data_security.tests.fixtures import AT, examples
from export_risk.contracts import (
    AuthorizationResult, AuthorizationSnapshot, ExecutionAuthorization, ExportRequestSnapshot,
    ExportRiskAssessment, Obligation, RecommendedAction, SourceMode,
)


class RiskContract:
    def setUp(self):
        super().setUp()
        self.now = AT
        self.binding = replace(examples()[ExecutionBinding], expires_at=AT + timedelta(seconds=900))
        self.request = ExportRequestSnapshot(request_id=self.binding.request_id, revision='1',
            subject_id=self.binding.subject_ref, asset_version=self.binding.asset_version,
            scope=('object/1',), operation='export', recipient_id='recipient/1',
            record_count=self.binding.quantity, request_fingerprint=self.binding.request_fingerprint,
            environment='test', source_mode=SourceMode.SYNTHETIC)
        self.assessment = ExportRiskAssessment(request_id=self.request.request_id,
            request_fingerprint=self.request.request_fingerprint, recommended_action=RecommendedAction.ALLOW,
            policy_version=self.binding.policy_binding.risk_version, profile_id='profile/1')
        self.grant = AuthorizationSnapshot(authority_source='test/owner', snapshot_id='grant/1',
            subject_id=self.request.subject_id, data_domain=self.binding.domain_ref,
            result=AuthorizationResult.AUTHORIZED, allowed_scope=self.request.scope,
            allowed_operations=('export',), allowed_recipients=('recipient/1',),
            observed_at=(AT - timedelta(seconds=1)).isoformat(),
            valid_until=(AT + timedelta(seconds=1200)).isoformat(), environment='test')
        self.assess_calls, self.authorize_calls, self.hold_calls = [], [], []
        self.approval_status = 'none'
        self.quota = self.make_quota()
        self.port = self.make_port()

    def port_options(self, changes):
        def assess(request, policy):
            self.assess_calls.append((request, policy))
            return self.assessment

        def authorize(request):
            self.authorize_calls.append(request)
            return self.grant

        def active_until(execution):
            self.hold_calls.append(execution)
            return self.quota.active_until(execution)

        options = dict(request=self.request, scope=self.binding.scope, domain_ref=self.binding.domain_ref,
            policy_binding=self.binding.policy_binding, environment='test', assess=assess,
            authorize=authorize, active_until=active_until,
            approval=SimpleNamespace(status=lambda decision, fingerprint: self.approval_status))
        options.update(changes)
        return options

    def assert_error(self, result, code=ReasonCode.AUTHORIZATION_DENIED, *, deciding=False, binding=None):
        self.assertIs(type(result), ProtectionError)
        self.assertEqual(result.code, code)
        self.assertFalse(result.retryable)
        self.assertEqual(result.trace_id, self.request.request_id if deciding else
                         (binding or self.binding).execution_id)

    def decide(self):
        decision = self.port.decide(self.request, self.binding.policy_binding)
        self.assertIs(type(decision), str)
        self.binding = replace(self.binding, decision_id=decision)
        return decision

    def reserve(self):
        self.decide()
        receipt = self.quota.reserve(self.binding)
        self.assertIs(type(receipt), QuotaReceipt)
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def issue(self):
        result = self.port.issue(self.binding)
        self.assertIs(type(result), ExecutionAuthorization)
        self.assertEqual(result, ExecutionAuthorization(authorization_id=self.binding.authorization_id,
            execution_id=self.binding.execution_id, decision_id=self.binding.decision_id,
            request_fingerprint=self.request.request_fingerprint, asset_version=self.request.asset_version,
            profile_id=self.assessment.profile_id, scope=self.request.scope,
            obligations=self.assessment.obligations, reservation_id=self.binding.reservation_id,
            valid_until=result.valid_until))
        return result

    def consume_and_commit(self):
        self.reserve()
        issued = self.issue()
        with self.work():
            self.assertEqual(self.port.consume(self.binding), issued)
            receipt = self.quota.commit(self.binding, self.binding.quantity)
            self.assertIs(type(receipt), QuotaReceipt)
        self.assertEqual(self.execution_state(), 'consumed')
        self.assertEqual(self.balances(), (1, 0, 0, 10))
        return issued

    def test_decide_replay_keeps_one_decision_deadline_and_never_reads_a_hold(self):
        decision = self.decide()
        expiry = self.decision_state()['expires_at']
        self.now += timedelta(seconds=20)
        rebuilt = self.make_port()
        self.assertEqual(rebuilt.decide(self.request, self.binding.policy_binding), decision)
        self.assertEqual(self.decision_state()['expires_at'], expiry)
        self.assertEqual(expiry, AT + timedelta(seconds=600))
        self.assertEqual(self.resources(), (1, 0, 1, 0))
        self.assertEqual(self.balances(), (0, 0, 0, 0))
        self.assertEqual(self.hold_calls, [])
        self.assertEqual(self.assess_calls, [(self.request, self.binding.policy_binding)] * 2)

    def test_changed_request_or_policy_clears_previous_admission(self):
        self.reserve()
        for request, policy in ((replace(self.request, recipient_id='recipient/other'), self.binding.policy_binding),
                                (self.request, replace(self.binding.policy_binding, risk_hash='2' * 64))):
            self.decide()
            self.assert_error(self.port.decide(request, policy), ReasonCode.IDEMPOTENCY_CONFLICT, deciding=True)
            self.assert_error(self.port.issue(self.binding))
        self.assertEqual(self.resources(), (1, 0, 1, 0))
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_unbound_assessment_and_changed_persisted_action_do_not_replace_decision(self):
        self.decide()
        original = self.assessment
        for changes, code in (({'request_id': 'request/other'}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'request_fingerprint': '1' * 64}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'policy_version': 'policy/other'}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'input_source_mode': SourceMode.PRODUCTION}, ReasonCode.SOURCE_NOT_APPROVED),
                ({'recommended_action': RecommendedAction.DENY}, ReasonCode.IDEMPOTENCY_CONFLICT)):
            with self.subTest(changes=changes):
                self.assessment = replace(original, **changes)
                self.assert_error(self.port.decide(self.request, self.binding.policy_binding), code, deciding=True)
                self.assert_error(self.port.issue(self.binding))
        self.assertEqual(self.resources(), (1, 0, 1, 0))
        self.assertEqual(self.hold_calls, [])

    def test_forbidden_admission_persists_evidence_but_no_hold_or_execution(self):
        original = self.grant
        self.grant = replace(original, result=AuthorizationResult.FORBIDDEN)
        self.assert_error(self.port.decide(self.request, self.binding.policy_binding), deciding=True)
        decision = self.decision_state()['id']
        self.assertEqual(self.resources(), (1, 0, 1, 0))
        self.assertEqual(self.hold_calls, [])
        self.grant = original
        self.assertEqual(self.decide(), decision)
        self.assertEqual(self.balances(), (0, 0, 0, 0))

    def test_approval_must_be_current_at_admission_and_recheck(self):
        self.assessment = replace(self.assessment, recommended_action=RecommendedAction.REQUIRE_APPROVAL)
        self.assert_error(self.port.decide(self.request, self.binding.policy_binding), deciding=True)
        self.approval_status = 'approved'
        self.reserve()
        self.issue()
        self.approval_status = 'revoked'
        self.assert_error(self.port.recheck(self.binding))
        self.assertEqual(self.execution_state(), 'claiming')
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_unsupported_obligation_is_not_executable(self):
        self.assessment = replace(self.assessment, obligations=(Obligation('duty/1', 'unsupported'),))
        self.assert_error(self.port.decide(self.request, self.binding.policy_binding), deciding=True)
        self.assertEqual(self.resources(), (1, 0, 1, 0))
        self.assertEqual(self.hold_calls, [])

    def test_issue_claims_once_recheck_preserves_dto_and_never_settles_quota(self):
        self.assessment = replace(self.assessment, obligations=(Obligation('duty/1', 'mask'),))
        self.reserve()
        issued = self.issue()
        self.assertEqual(issued.valid_until, (AT + timedelta(seconds=300)).isoformat())
        self.now += timedelta(seconds=10)
        self.assertEqual(self.port.recheck(self.binding), issued)
        self.assert_error(self.port.issue(self.binding))
        self.assertEqual(self.execution_state(), 'claiming')
        self.assertEqual(self.resources(), (1, 1, 1, 1))
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_rebuilt_port_requires_admission_but_does_not_reclaim(self):
        self.reserve()
        issued = self.issue()
        rebuilt = self.make_port()
        self.assert_error(rebuilt.recheck(self.binding))
        self.assertEqual(rebuilt.decide(self.request, self.binding.policy_binding), self.binding.decision_id)
        self.assertEqual(rebuilt.recheck(self.binding), issued)
        self.assertEqual(self.resources(), (1, 1, 1, 1))

    def test_complete_execution_binding_rejects_before_permission_lookup(self):
        self.reserve()
        count = len(self.authorize_calls)
        changes = ({'request_id': 'request/other'}, {'request_fingerprint': '1' * 64},
            {'asset_version': 'asset/other'}, {'subject_ref': 'actor/other'}, {'quantity': 9},
            {'environment': 'evaluation'}, {'domain_ref': 'domain/other'},
            {'policy_binding': replace(self.binding.policy_binding, risk_hash='2' * 64)},
            {'scope': replace(self.binding.scope, sheets=(replace(
                self.binding.scope.sheets[0], row_ranges=((1, 1),)),))})
        for change in changes:
            binding = replace(self.binding, **change)
            with self.subTest(field=next(iter(change))):
                self.assert_error(self.port.issue(binding), ReasonCode.IDEMPOTENCY_CONFLICT, binding=binding)
        self.assert_error(self.port.issue(replace(self.binding, decision_id='decision/other')))
        self.assertEqual(len(self.authorize_calls), count)
        self.assertEqual(self.resources(), (1, 0, 1, 0))

    def test_quota_owned_identity_and_deadline_cannot_be_changed(self):
        self.reserve()
        for change, code in (({'authorization_id': 'authorization/other'}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'execution_id': 'execution/other'}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'reservation_id': 'reservation/other'}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'expires_at': self.binding.expires_at + timedelta(seconds=1)}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'idempotency_key': 'key/other'}, ReasonCode.AUTHORIZATION_DENIED)):
            binding = replace(self.binding, **change)
            with self.subTest(field=next(iter(change))):
                self.assert_error(self.port.issue(binding), code, binding=binding)
        self.assertEqual(self.resources(), (1, 0, 1, 0))
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_each_recheck_requires_current_complete_authorization(self):
        self.reserve()
        issued = self.issue()
        original, count = self.grant, len(self.authorize_calls)
        for changes, code in (({'result': AuthorizationResult.FORBIDDEN}, ReasonCode.AUTHORIZATION_DENIED),
                ({'result': AuthorizationResult.UNKNOWN}, ReasonCode.AUTHORIZATION_DENIED),
                ({'subject_id': 'actor/other'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'allowed_scope': ()}, ReasonCode.AUTHORIZATION_DENIED),
                ({'allowed_operations': ()}, ReasonCode.AUTHORIZATION_DENIED),
                ({'allowed_recipients': ()}, ReasonCode.AUTHORIZATION_DENIED),
                ({'data_domain': 'domain/other'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'environment': 'evaluation'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'source_mode': SourceMode.PRODUCTION}, ReasonCode.SOURCE_NOT_APPROVED)):
            self.grant = replace(original, **changes)
            with self.subTest(field=next(iter(changes))):
                self.assert_error(self.port.recheck(self.binding), code)
            count += 1
        self.assertEqual(len(self.authorize_calls), count)
        self.grant = original
        self.assertEqual(self.port.recheck(self.binding), issued)
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_unknown_future_naive_and_expired_grant_times_never_allow(self):
        self.reserve()
        self.issue()
        original = self.grant
        for change in ({'valid_until': self.now.isoformat()}, {'valid_until': ''},
                {'valid_until': self.now.replace(tzinfo=None).isoformat()}, {'observed_at': ''},
                {'observed_at': (self.now + timedelta(seconds=1)).isoformat()}):
            self.grant = replace(original, **change)
            with self.subTest(change=change):
                self.assert_error(self.port.recheck(self.binding))
        self.assertEqual(self.execution_state(), 'claiming')
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_shorter_live_grant_tightens_persisted_deadline_without_revival(self):
        self.reserve()
        self.issue()
        original = self.grant
        expiry = AT + timedelta(seconds=40)
        self.grant = replace(original, valid_until=expiry.isoformat())
        short = self.port.recheck(self.binding)
        self.assertIs(type(short), ExecutionAuthorization)
        self.assertEqual(short.valid_until, expiry.isoformat())
        self.grant = original
        self.assertEqual(self.port.recheck(self.binding), short)
        self.now = expiry
        self.assert_error(self.port.recheck(self.binding))
        self.assertEqual(self.execution_state(), 'claiming')
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_hold_expiry_is_exclusive_and_does_not_release_capacity(self):
        self.reserve()
        self.issue()
        self.now = AT + timedelta(seconds=300)
        self.assert_error(self.port.recheck(self.binding))
        self.assertEqual(self.execution_state(), 'claiming')
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_decision_expiry_cannot_be_extended_by_replaying_admission(self):
        self.quota = self.make_quota(ttl_seconds=1200)
        self.reserve()
        self.assertEqual(self.issue().valid_until, (AT + timedelta(seconds=600)).isoformat())
        self.now = AT + timedelta(seconds=600)
        self.assert_error(self.port.recheck(self.binding))
        self.assert_error(self.port.decide(self.request, self.binding.policy_binding), deciding=True)
        self.assertEqual(self.decision_state()['expires_at'], self.now)
        self.assertEqual(self.resources(), (1, 1, 1, 1))
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_unknown_hold_and_invalidated_decision_do_not_reopen_execution(self):
        self.reserve()
        self.issue()
        self.quota.reconcile(self.binding, None, 'proof/unknown')
        self.assert_error(self.port.recheck(self.binding))
        self.invalidate_decision()
        self.assert_error(self.port.decide(self.request, self.binding.policy_binding), deciding=True)
        self.assert_error(self.port.issue(self.binding))
        self.assertEqual(self.resources(), (1, 1, 1, 1))
        self.assertEqual(self.balances(), (1, 0, 10, 0))

    def test_consume_requires_work_rechecks_permission_and_is_terminal(self):
        self.reserve()
        issued = self.issue()
        self.assert_error(self.port.consume(self.binding))
        original = self.grant
        self.grant = replace(original, result=AuthorizationResult.FORBIDDEN)
        with self.work():
            self.assert_error(self.port.consume(self.binding))
        self.assertEqual(self.execution_state(), 'claiming')
        self.grant = original
        with self.work():
            self.assertEqual(self.port.consume(self.binding), issued)
        self.assertEqual(self.execution_state(), 'consumed')
        with self.work():
            self.assert_error(self.port.consume(self.binding))
        self.assert_error(self.port.recheck(self.binding))
        self.assert_error(self.port.issue(self.binding))
        self.assertEqual(self.resources(), (1, 1, 1, 1))
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_provider_errors_preserve_exact_error_and_fail_without_execution(self):
        error = ProtectionError(schema_version=ProtectionError.SCHEMA,
            code=ReasonCode.AUTHORIZATION_DENIED, retryable=False, trace_id='owner/refusal')
        original = self.assessment
        self.assessment = error
        self.assertIs(self.port.decide(self.request, self.binding.policy_binding), error)
        self.assertEqual(self.resources(), (0, 0, 0, 0))
        self.assessment = original
        self.reserve()
        self.grant = error
        self.assertIs(self.port.issue(self.binding), error)
        self.assertEqual(self.resources(), (1, 0, 1, 0))
        self.assertEqual(self.balances(), (1, 10, 0, 0))

    def test_delivered_recheck_rebuilds_without_assessment_claim_or_active_hold(self):
        self.consume_and_commit()
        assesses, grants, holds = len(self.assess_calls), len(self.authorize_calls), len(self.hold_calls)
        rebuilt = self.make_port()
        self.assertIs(rebuilt.recheck_delivered(self.binding), True)
        self.now += timedelta(seconds=1)
        self.assertIs(rebuilt.recheck_delivered(self.binding), True)
        self.assertEqual((len(self.assess_calls), len(self.authorize_calls), len(self.hold_calls)),
                         (assesses, grants + 2, holds))
        self.assertEqual(self.execution_state(), 'consumed')
        self.assertEqual(self.resources(), (1, 1, 1, 1))
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    def test_delivered_recheck_requires_original_consumed_state(self):
        self.reserve()
        self.assert_error(self.port.recheck_delivered(self.binding))
        self.issue()
        self.assert_error(self.port.recheck_delivered(self.binding))
        with self.work():
            self.assertIs(type(self.port.consume(self.binding)), ExecutionAuthorization)
            self.assertIs(type(self.quota.commit(self.binding, 10)), QuotaReceipt)
        for state in ('valid', 'claiming', 'revoked', 'expired'):
            self.set_execution_state(state)
            with self.subTest(state=state):
                self.assert_error(self.port.recheck_delivered(self.binding))
                self.assertEqual(self.execution_state(), state)
        self.set_execution_state('consumed')
        self.assertIs(self.port.recheck_delivered(self.binding), True)
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    def test_delivered_recheck_binds_complete_execution_without_a_quota_read(self):
        self.consume_and_commit()
        grants, holds = len(self.authorize_calls), len(self.hold_calls)
        for changes in ({'request_id': 'request/other'}, {'request_fingerprint': '1' * 64},
                {'asset_version': 'asset/other'}, {'subject_ref': 'actor/other'}, {'quantity': 9},
                {'environment': 'evaluation'}, {'domain_ref': 'domain/other'},
                {'policy_binding': replace(self.binding.policy_binding, risk_hash='2' * 64)},
                {'scope': replace(self.binding.scope, sheets=(replace(
                    self.binding.scope.sheets[0], row_ranges=((1, 1),)),))}):
            binding = replace(self.binding, **changes)
            with self.subTest(field=next(iter(changes))):
                self.assert_error(self.port.recheck_delivered(binding), ReasonCode.IDEMPOTENCY_CONFLICT,
                                  binding=binding)
        self.assertEqual(len(self.authorize_calls), grants)
        for changes, code in (({'decision_id': 'decision/other'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'authorization_id': 'authorization/other'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'execution_id': 'execution/other'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'reservation_id': 'reservation/other'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'idempotency_key': 'key/other'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'expires_at': self.binding.expires_at + timedelta(seconds=1)}, ReasonCode.IDEMPOTENCY_CONFLICT),
                ({'expires_at': self.binding.expires_at - timedelta(seconds=1)}, ReasonCode.IDEMPOTENCY_CONFLICT)):
            binding = replace(self.binding, **changes)
            with self.subTest(field=next(iter(changes))):
                self.assert_error(self.port.recheck_delivered(binding), code, binding=binding)
        self.assertIs(self.port.recheck_delivered(self.binding), True)
        self.assertEqual(len(self.hold_calls), holds)
        self.assertEqual(self.resources(), (1, 1, 1, 1))
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    def test_delivered_recheck_requires_original_request_admission_not_just_fingerprint(self):
        self.consume_and_commit()
        calls = len(self.assess_calls)
        changed = self.make_port(request=replace(self.request, revision='2'))
        self.assert_error(changed.recheck_delivered(self.binding))
        self.assertEqual(len(self.assess_calls), calls)
        self.assertIs(self.make_port().recheck_delivered(self.binding), True)
        self.assertEqual(self.resources(), (1, 1, 1, 1))

    def test_delivered_recheck_requires_current_complete_grant_each_time(self):
        self.consume_and_commit()
        original, grants, holds = self.grant, len(self.authorize_calls), len(self.hold_calls)
        for changes, code in (({'result': AuthorizationResult.FORBIDDEN}, ReasonCode.AUTHORIZATION_DENIED),
                ({'result': AuthorizationResult.UNKNOWN}, ReasonCode.AUTHORIZATION_DENIED),
                ({'subject_id': 'actor/other'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'allowed_scope': ()}, ReasonCode.AUTHORIZATION_DENIED),
                ({'allowed_operations': ()}, ReasonCode.AUTHORIZATION_DENIED),
                ({'allowed_recipients': ()}, ReasonCode.AUTHORIZATION_DENIED),
                ({'data_domain': 'domain/other'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'environment': 'evaluation'}, ReasonCode.AUTHORIZATION_DENIED),
                ({'source_mode': SourceMode.PRODUCTION}, ReasonCode.SOURCE_NOT_APPROVED),
                ({'valid_until': self.now.isoformat()}, ReasonCode.AUTHORIZATION_DENIED),
                ({'valid_until': ''}, ReasonCode.AUTHORIZATION_DENIED),
                ({'valid_until': self.now.replace(tzinfo=None).isoformat()}, ReasonCode.AUTHORIZATION_DENIED),
                ({'observed_at': ''}, ReasonCode.AUTHORIZATION_DENIED),
                ({'observed_at': (self.now + timedelta(seconds=1)).isoformat()}, ReasonCode.AUTHORIZATION_DENIED)):
            self.grant = replace(original, **changes)
            with self.subTest(field=next(iter(changes))):
                self.assert_error(self.port.recheck_delivered(self.binding), code)
            grants += 1
        self.assertEqual((len(self.authorize_calls), len(self.hold_calls)), (grants, holds))
        self.grant = original
        self.assertIs(self.port.recheck_delivered(self.binding), True)
        self.assertEqual(self.execution_state(), 'consumed')
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    def test_delivered_recheck_preserves_provider_error_and_rejects_invalid_type(self):
        self.consume_and_commit()
        self.grant = ProtectionError(schema_version=ProtectionError.SCHEMA,
            code=ReasonCode.AUTHORIZATION_DENIED, retryable=False, trace_id='owner/refusal')
        self.assertIs(self.port.recheck_delivered(self.binding), self.grant)
        self.grant = True
        self.assert_error(self.port.recheck_delivered(self.binding), ReasonCode.INVALID_TYPE)
        self.assertEqual(self.execution_state(), 'consumed')
        self.assertEqual(self.resources(), (1, 1, 1, 1))

    def test_delivered_recheck_observes_current_approval_and_decision_status(self):
        self.assessment = replace(self.assessment, recommended_action=RecommendedAction.REQUIRE_APPROVAL)
        self.approval_status = 'approved'
        self.consume_and_commit()
        self.approval_status = 'revoked'
        self.assert_error(self.port.recheck_delivered(self.binding))
        self.approval_status = 'approved'
        self.assertIs(self.port.recheck_delivered(self.binding), True)
        self.invalidate_decision()
        self.assert_error(self.port.recheck_delivered(self.binding))
        self.assertEqual(self.execution_state(), 'consumed')
        self.assertEqual(self.resources(), (1, 1, 1, 1))
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    def test_delivered_recheck_never_renews_original_short_authorization(self):
        original = self.grant
        expiry = AT + timedelta(seconds=40)
        self.grant = replace(original, valid_until=expiry.isoformat())
        issued = self.consume_and_commit()
        self.assertEqual(issued.valid_until, expiry.isoformat())
        self.grant = original
        rebuilt = self.make_port()
        self.now = expiry - timedelta(seconds=1)
        self.assertIs(rebuilt.recheck_delivered(self.binding), True)
        self.now = expiry
        self.assert_error(rebuilt.recheck_delivered(self.binding))
        self.assertLess(self.now, self.binding.expires_at)
        self.assertEqual(self.execution_state(), 'consumed')
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    def test_delivered_recheck_tests_short_current_grant_again_at_final_call(self):
        self.consume_and_commit()
        expiry = AT + timedelta(seconds=40)
        self.grant = replace(self.grant, valid_until=expiry.isoformat())
        rebuilt = self.make_port()
        self.assertIs(rebuilt.recheck_delivered(self.binding), True)
        self.now = expiry
        self.assert_error(rebuilt.recheck_delivered(self.binding))
        self.assertLess(self.now, self.binding.expires_at)
        self.assertEqual(self.execution_state(), 'consumed')
        self.assertEqual(self.resources(), (1, 1, 1, 1))

    def test_delivered_recheck_cannot_extend_original_decision_deadline(self):
        self.quota = self.make_quota(ttl_seconds=1200)
        issued = self.consume_and_commit()
        expiry = AT + timedelta(seconds=600)
        self.assertEqual(issued.valid_until, expiry.isoformat())
        self.assertIs(self.port.recheck_delivered(self.binding), True)
        self.now = expiry
        self.assert_error(self.port.recheck_delivered(self.binding))
        self.assertEqual(self.decision_state()['expires_at'], expiry)
        self.assertEqual(self.resources(), (1, 1, 1, 1))
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    def test_delivered_recheck_checks_deadlines_after_current_approval_lookup(self):
        self.assessment = replace(self.assessment, recommended_action=RecommendedAction.REQUIRE_APPROVAL)
        self.approval_status = 'approved'
        self.consume_and_commit()
        expiry = AT + timedelta(seconds=40)
        self.grant = replace(self.grant, valid_until=expiry.isoformat())

        def approval_status(decision, fingerprint):
            self.now = expiry
            return 'approved'

        rebuilt = self.make_port(approval=SimpleNamespace(status=approval_status))
        self.assert_error(rebuilt.recheck_delivered(self.binding))
        self.assertEqual(self.execution_state(), 'consumed')
        self.assertEqual(self.balances(), (1, 0, 0, 10))

    def test_invalid_provider_types_and_unapproved_constructor_sources_are_rejected(self):
        original = self.assessment
        self.assessment = True
        self.assert_error(self.port.decide(self.request, self.binding.policy_binding),
                          ReasonCode.INVALID_TYPE, deciding=True)
        self.assessment = original
        self.reserve()
        self.grant = True
        self.assert_error(self.port.issue(self.binding), ReasonCode.INVALID_TYPE)
        for changes in ({'environment': 'production'},
                {'request': replace(self.request, source_mode=SourceMode.PRODUCTION)},
                {'request': replace(self.request, environment='evaluation')}):
            with self.subTest(changes=changes), self.assertRaises(ContractViolation) as caught:
                self.make_port(**changes)
            self.assertEqual(caught.exception.code, ReasonCode.SOURCE_NOT_APPROVED)
        self.assertEqual(self.resources(), (1, 0, 1, 0))
