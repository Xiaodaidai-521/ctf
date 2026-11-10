"""The three synthetic business targets and their authenticated, retained directory.

Only the dedicated encrypted field is written. Knowledge drafts, inactive empty
challenges and the current user's empty database cache row must be explicitly
selected by the configured CanarySeed; no existing body is replaced or published.
"""
import hashlib
from uuid import UUID

from django.db import DatabaseError, connection, transaction

from challenges.models import Challenge
from legal_kb.models import LegalDocument
from resources.models import ResourceCache
from users.models import CTFUser
from data_security.contracts import (
    AuditReceipt, CanarySeed, CipherEnvelope, ContractViolation, Durability, Environment,
    EventKind, ObjectContext, Outcome, Outlet, ProtectionContext, ProtectionError,
    Purpose, ReasonCode, Role, SecurityEventV2, canonical_bytes, content_hash,
)
from data_security.contracts.schema import require
from .canary_catalog import CanaryRegistration


class DjangoCanaryTargets:
    def __init__(self, *, seeds, crypto, data_key, project_ref, environment, domain,
                 audit, read_event, recovery_events, policy_binding, clock, limits,
                 admission=None, read_flag=None):
        self.seeds = {seed.seed_id: seed for seed in seeds}
        self.crypto, self.data_key, self.project_ref = crypto, data_key, project_ref
        self.environment, self.domain = environment, domain
        self.audit, self.read_event, self.recovery_events = audit, read_event, recovery_events
        self.policy_binding, self.clock, self.limits = policy_binding, clock, limits
        self.admission, self.read_flag = admission, read_flag
        self.targets = {'knowledge': (LegalDocument, 'legal_kb', 'legaldocument'),
                        'database': (ResourceCache, 'resources', 'resourcecache'),
                        'challenge': (Challenge, 'challenges', 'challenge')}
        for seed in seeds:
            parts = seed.target_ref.split('/')
            require(len(parts) == 2 and parts[0] == seed.target_kind and
                    parts[1].isascii() and parts[1].isdigit() and int(parts[1]) > 0,
                    ReasonCode.SOURCE_NOT_APPROVED)

    def _admitted(self):
        if self.admission is not None:
            result = self.admission()
            require(result is True, result.code if type(result) is ProtectionError
                    else ReasonCode.SOURCE_NOT_APPROVED)

    def _target(self, seed, *, locked=False):
        model = self.targets[seed.target_kind][0]
        query = model.objects.select_for_update() if locked else model.objects
        target = query.filter(pk=int(seed.target_ref.split('/')[1])).first()
        require(target is not None, ReasonCode.SOURCE_NOT_APPROVED)
        return target

    def _synthetic_scope(self, seed, target, actor):
        if seed.target_kind == 'knowledge':
            require(target.created_by_id == actor.pk and target.status == 'draft' and
                    target.document_type == 'other' and target.full_text == '' and
                    not target.source_url and not target.clauses.exists(), ReasonCode.SOURCE_NOT_APPROVED)
        elif seed.target_kind == 'database':
            require(target.studentId == actor.pk and target.resourceList == [], ReasonCode.AUTHORIZATION_DENIED)
        else:
            require(actor.is_staff and not target.is_active and target.description == '' and
                    not target.hint and not target.attachment and not target.docker_image,
                    ReasonCode.SOURCE_NOT_APPROVED)
            if target.security_envelopes:
                require(self.read_flag is not None, ReasonCode.KEY_UNAVAILABLE)
                require(self.read_flag(target) == '', ReasonCode.SOURCE_NOT_APPROVED)
            else:
                require(target.flag == '', ReasonCode.SOURCE_NOT_APPROVED)

    def _principal(self, operation, seed, user_id, *, target=None):
        actor = CTFUser.objects.filter(pk=user_id, is_active=True).first()
        require(actor is not None, ReasonCode.AUTHORIZATION_DENIED)
        capability = {'plant': 'add', 'check': 'view', 'retire': 'change'}[operation]
        require(actor.has_perm('security_policies.' + capability + '_canaryregistration'),
                ReasonCode.AUTHORIZATION_DENIED)
        _, app, model = self.targets[seed.target_kind]
        require(actor.has_perm(app + '.' + ('view' if operation == 'check' else 'change') + '_' + model),
                ReasonCode.AUTHORIZATION_DENIED)
        target = self._target(seed) if target is None else target
        self._synthetic_scope(seed, target, actor)
        return ProtectionContext(schema_version=ProtectionContext.SCHEMA,
            actor_ref='user/' + str(actor.pk), authorization_ref='canary/' + operation + '/' + seed.seed_id,
            scope_refs=(seed.target_ref,), environment=self.environment, domain=self.domain,
            outlet=Outlet.EXPORT if operation == 'check' else Outlet.AUDIT,
            purpose=Purpose.SECURITY_AUDIT, role=Role(actor.role), object_ref=seed.target_ref,
            object_version=seed.target_version, source_ref=None, source_version=None,
            source_hash=None, trace_id='canary/' + seed.seed_id)

    def resolve_context(self, name, ref, user):
        self._admitted()
        operation = 'plant' if name == 'canary.plant' else 'check'
        if operation == 'check':
            require(ref.startswith('canary/') and ref.count('/') == 1, ReasonCode.SOURCE_NOT_APPROVED)
            ref = ref.split('/')[1]
        require(ref in self.seeds, ReasonCode.SOURCE_NOT_APPROVED)
        seed = self.seeds[ref]
        principal = self._principal(operation, seed, user.pk)
        if operation == 'check':
            registration = CanaryRegistration.objects.filter(seed_id=ref, state='planted').first()
            require(registration is not None and registration.actor_ref == principal.actor_ref,
                    ReasonCode.AUTHORIZATION_DENIED)
        return principal

    def authorize(self, name, context, seed):
        self._admitted()
        if name == 'canary.check' and context.role is Role.SERVICE:
            require(context.actor_ref == 'service/security' and
                    context.authorization_ref == 'authorization/phase3-isolated' and
                    context.environment is self.environment and context.domain == self.domain and
                    context.outlet in (Outlet.MODEL, Outlet.EMBEDDING, Outlet.LOG),
                    ReasonCode.AUTHORIZATION_DENIED)
            return context
        operation = 'plant' if name == 'canary.plant' else 'check'
        seed = self.seeds.get(context.authorization_ref.split('/')[-1]) if seed is None else seed
        require(seed is not None and context.actor_ref.startswith('user/'), ReasonCode.AUTHORIZATION_DENIED)
        principal = self._principal(operation, seed, int(context.actor_ref.split('/')[1]))
        require(principal == context, ReasonCode.AUTHORIZATION_DENIED)
        return principal

    def _object_context(self, seed):
        return ObjectContext(schema_version=ObjectContext.SCHEMA, project_ref=self.project_ref,
            environment=self.environment, object_uuid=str(UUID(hex=seed.seed_id)),
            object_version=seed.target_version, field_ref='canary/' + seed.target_kind,
            authorization_ref='canary/plant/' + seed.seed_id)

    def _metadata(self, registration):
        return {name: getattr(registration, name) for name in (
            'seed_id', 'seed_document', 'target_pk', 'actor_ref', 'packet_hash', 'state',
            'plant_event_id', 'retire_event_id')}

    def _verified(self, registration, seed, target, *, read_event=None):
        require(registration.seed_document == seed.to_wire() and
                registration.target_pk == str(target.pk) and registration.state in ('planted', 'retired'),
                ReasonCode.REPORT_MISMATCH)
        envelope = CipherEnvelope.from_wire(target.canary_payload)
        payload = self.crypto.open(envelope, self._object_context(seed), envelope.key)
        require(type(payload) is not ProtectionError, payload.code if type(payload) is ProtectionError
                else ReasonCode.CIPHERTEXT_INVALID)
        require(hashlib.sha256(canonical_bytes(payload, include_payload=True)).hexdigest() ==
                registration.packet_hash, ReasonCode.HASH_MISMATCH)
        packet = payload.tree.to_value()
        require(packet['schema_version'] == 'ds.synthetic-canary.v1' and packet['synthetic'] is True and
                packet['seed'] == seed.to_wire(), ReasonCode.REPORT_MISMATCH)
        event = (read_event or self.read_event)(registration.retire_event_id if registration.state == 'retired'
                                               else registration.plant_event_id)
        require(type(event) is SecurityEventV2 and event.kind is EventKind.PROTECTION and
                event.actor_ref == registration.actor_ref and event.object_ref == seed.target_ref and
                event.object_version == seed.target_version and event.outcome is Outcome.SUCCEEDED and
                event.algorithm_versions == ('canary-target.v1', registration.state) and
                event.evidence_hashes == (('ciphertext', content_hash(envelope)),
                                          ('report', content_hash(self._metadata(registration)))),
                ReasonCode.AUDIT_UNAVAILABLE)
        return payload

    def _record(self, registration, seed):
        event_id = registration.retire_event_id if registration.state == 'retired' else registration.plant_event_id
        target = self._target(seed)
        envelope = CipherEnvelope.from_wire(target.canary_payload)
        event = SecurityEventV2(schema_version=SecurityEventV2.SCHEMA,
            event_id=event_id, kind=EventKind.PROTECTION, actor_ref=registration.actor_ref,
            object_ref=seed.target_ref, object_version=seed.target_version, outcome=Outcome.SUCCEEDED,
            occurred_at=self.clock(), counts=(('records', 1),), policy_binding=self.policy_binding,
            algorithm_versions=('canary-target.v1', registration.state), key_versions=(envelope.key.key_ref,),
            correlation_ref='canary/' + seed.seed_id, reason=None,
            evidence_hashes=(('ciphertext', content_hash(envelope)),
                             ('report', content_hash(self._metadata(registration)))))
        receipt = self.audit.record(event, Durability.LEDGER_CONFIRMED)
        require(type(receipt) is AuditReceipt and receipt.event_id == event_id and
                receipt.chain_version == 'ds.audit.v2' and receipt.durability is Durability.LEDGER_CONFIRMED,
                receipt.code if type(receipt) is ProtectionError else ReasonCode.AUDIT_UNAVAILABLE)

    def plant_target(self, seed, packet, context):
        try:
            require(connection.get_autocommit() and not connection.in_atomic_block,
                    ReasonCode.SOURCE_NOT_APPROVED)
            registration = CanaryRegistration.objects.filter(seed_id=seed.seed_id).first()
            if registration is not None:
                require(registration.state == 'planted' and registration.actor_ref == context.actor_ref,
                        ReasonCode.AUTHORIZATION_DENIED)
                self._verified(registration, seed, self._target(seed))
                return seed
            envelope = self.crypto.seal(packet, self._object_context(seed), self.data_key)
            require(type(envelope) is CipherEnvelope, envelope.code if type(envelope) is ProtectionError
                    else ReasonCode.CIPHERTEXT_INVALID)
            with transaction.atomic():
                target = self._target(seed, locked=True)
                principal = self._principal('plant', seed, int(context.actor_ref.split('/')[1]), target=target)
                require(principal == context, ReasonCode.AUTHORIZATION_DENIED)
                registration = CanaryRegistration.objects.filter(seed_id=seed.seed_id).first()
                if registration is not None:
                    require(registration.state == 'planted' and registration.actor_ref == context.actor_ref,
                            ReasonCode.AUTHORIZATION_DENIED)
                    self._verified(registration, seed, target)
                else:
                    require(not target.canary_payload, ReasonCode.SOURCE_NOT_APPROVED)
                    require(CanaryRegistration.objects.count() < self.limits.max_findings, ReasonCode.LIMIT_EXCEEDED)
                    target.canary_payload = envelope.to_wire()
                    target.save(update_fields=['canary_payload'])
                    registration = CanaryRegistration.objects.create(seed_id=seed.seed_id,
                        seed_document=seed.to_wire(), target_pk=str(target.pk), actor_ref=principal.actor_ref,
                        packet_hash=hashlib.sha256(canonical_bytes(packet, include_payload=True)).hexdigest(),
                        plant_event_id='canary/plant/' + seed.seed_id)
                    self._record(registration, seed)
            return seed
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='canary/plant')

    def load_output(self, ref, context):
        self._admitted()
        seed = self.seeds[ref.split('/')[1]]
        target = self._target(seed)
        principal = self._principal('check', seed, int(context.actor_ref.split('/')[1]), target=target)
        require(principal == context, ReasonCode.AUTHORIZATION_DENIED)
        registration = CanaryRegistration.objects.filter(seed_id=seed.seed_id, state='planted').first()
        require(registration is not None and registration.actor_ref == principal.actor_ref,
                ReasonCode.AUTHORIZATION_DENIED)
        return self._verified(registration, seed, target)

    def retire(self, *, seed_id, user):
        """Explicit metadata retirement keeps ciphertext, seeds and historical detection."""
        try:
            self._admitted()
            require(seed_id in self.seeds and connection.get_autocommit() and not connection.in_atomic_block,
                    ReasonCode.SOURCE_NOT_APPROVED)
            seed = self.seeds[seed_id]
            with transaction.atomic():
                target = self._target(seed, locked=True)
                principal = self._principal('retire', seed, user.pk, target=target)
                registration = CanaryRegistration.objects.select_for_update().filter(seed_id=seed_id).first()
                require(registration is not None and registration.actor_ref == principal.actor_ref,
                        ReasonCode.AUTHORIZATION_DENIED)
                self._verified(registration, seed, target)
                if registration.state != 'retired':
                    registration.state, registration.retire_event_id = 'retired', 'canary/retire/' + seed_id
                    registration.save(update_fields=['state', 'retire_event_id'])
                    self._record(registration, seed)
            return {'status': 'retired'}
        except ContractViolation as error:
            code = error.code
        except DatabaseError:
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='canary/retire')

    def catalog_inventory(self):
        """Configuration cannot silently drop already planted or retired seeds."""
        query = CanaryRegistration.objects.all()
        require(query.count() <= self.limits.max_findings, ReasonCode.LIMIT_EXCEEDED)
        for registration in query.iterator(chunk_size=1):
            seed = self.seeds.get(registration.seed_id)
            require(seed is not None and registration.seed_document == seed.to_wire() and
                    registration.state in ('planted', 'retired'), ReasonCode.SOURCE_NOT_APPROVED)

    def restore_catalog(self):
        """Read-only target/chain validation; never repair, replant or open B3 traffic."""
        try:
            require(connection.vendor == 'postgresql' and connection.get_autocommit() and
                    not connection.in_atomic_block, ReasonCode.SOURCE_NOT_APPROVED)
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                audit = self.recovery_events()
                require(type(audit) is dict, ReasonCode.AUDIT_UNAVAILABLE)
                query = CanaryRegistration.objects.all()
                require(query.count() <= self.limits.max_findings, ReasonCode.LIMIT_EXCEEDED)
                planted, retired, data_keys = 0, 0, set()
                registered_targets = set()
                for registration in query.iterator(chunk_size=1):
                    seed = self.seeds.get(registration.seed_id)
                    require(seed is not None, ReasonCode.SOURCE_NOT_APPROVED)
                    target = self._target(seed)
                    self._verified(registration, seed, target,
                        read_event=lambda event_id: audit['events'].get(event_id, (None,))[0])
                    registered_targets.add((seed.target_kind, target.pk))
                    data_keys.add(target.canary_payload['key']['key_ref'])
                    planted += registration.state == 'planted'
                    retired += registration.state == 'retired'
                # A lost directory row must not make retained business ciphertext invisible.
                for kind, (model, _, _) in self.targets.items():
                    retained = model.objects.exclude(canary_payload={})
                    require(retained.count() <= self.limits.max_findings, ReasonCode.LIMIT_EXCEEDED)
                    for target in retained.iterator(chunk_size=1):
                        require((kind, target.pk) in registered_targets, ReasonCode.REPORT_MISMATCH)
            return {'schema_version': 'ds.canary-catalog-recovery.v1', 'planted': planted,
                    'retired': retired, 'data_key_refs': sorted(data_keys),
                    'traffic_opened': False, 'key_retirement_allowed': False}
        except ContractViolation as error:
            code = error.code
        except (DatabaseError, KeyError, TypeError, ValueError):
            code = ReasonCode.DELIVERY_UNKNOWN
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=code,
                               retryable=False, trace_id='canary/restore')
