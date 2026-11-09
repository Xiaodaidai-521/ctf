"""Run with the built wheel in an empty venv: no Django and no repository imports."""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import sys

assert importlib.util.find_spec('django') is None


def fence(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise RuntimeError('STANDALONE_NETWORK_FORBIDDEN')


sys.addaudithook(fence)
from data_security.adapters.tabular.codec import TableCodec
from data_security.adapters.tabular.source_plans import SourcePlanAdapter
from data_security.contracts import (ActionPlan, Approval, BASELINE_LIMITS, BoundedPayload,
    FrozenJSON, MediaType, PayloadKind, PolicyBinding, SheetScope, SourceDocument, SourceFormat,
    SourcePlanBinding, SourceTrust, TableScope, content_hash)


def dto(cls, **values):
    return cls(schema_version=cls.SCHEMA, **values)


codec = TableCodec(asset_version='isolated-wheel-v1')
payload = dto(BoundedPayload, kind=PayloadKind.BINARY, media_type=MediaType.CSV,
              text=None, tree=None, binary=b'name,note\nsynthetic,=1+1\n', limits=BASELINE_LIMITS)
snapshot = codec.parse(payload, BASELINE_LIMITS)
source_doc = {'version': '1', 'format': 'csv', 'scope': {'columns': ['name', 'note']},
              'operations': [{'type': 'sanitize_formulas'}]}
hash_json = lambda value: hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                                   separators=(',', ':')).encode()).hexdigest()
source_hash = hash_json(source_doc)
retained = dto(SourcePlanBinding, source_format=SourceFormat.COLUMN_V1, source_version='1',
    source_plan_hash=source_hash, source_record_ref='synthetic/plan', source_record_version='v1',
    source_trust=SourceTrust.SYNTHETIC, provenance_ref='synthetic/provenance',
    approval_basis_ref='synthetic/approval', approval_basis_version='v1', source_state='not-declared',
    source_environment='test', source_domain='synthetic', evaluation_ref=None,
    scope_hash=hash_json(source_doc['scope']), parser_version=None, parser_config_hash=None,
    requirements_hash=None, operation_contract_version=None)
at = datetime(2026, 11, 6, 4, 12, tzinfo=timezone.utc)
approval = dto(Approval, approval_ref='synthetic/approval', requested_by='synthetic/requester',
    approved_by='synthetic/reviewer', approved_at=at, content_hash=source_hash)
scope = dto(TableScope, coordinate_version='source-codepoint-half-open.v1', sheets=(dto(SheetScope,
    sheet_id='csv:0', column_ids=('c1', 'c2'), row_ranges=((1, 2),), includes_header=True),))
binding = dto(PolicyBinding, protection_version='synthetic-v1', protection_hash=content_hash('synthetic'),
    risk_version='synthetic-risk-v1', risk_hash=content_hash('synthetic-risk'), contract_version='ds.m0.v1')
adapter = SourcePlanAdapter(source_binding=retained, source_approval=approval, scope=scope,
    asset_version=snapshot.asset_version, input_hash=snapshot.input_hash,
    plan_id='synthetic/target', created_at=at, expires_at=at + timedelta(minutes=30))
source = dto(SourceDocument, source_format=SourceFormat.COLUMN_V1, source_version='1', document=FrozenJSON(source_doc))
plan = adapter.to_action_plan(source, snapshot, binding, ())
assert isinstance(plan, ActionPlan) and plan.approval is None
assert plan == adapter.to_action_plan(source, snapshot, binding, ())
output = codec.serialize(snapshot, BASELINE_LIMITS)
assert output.binary == b"name,note\nsynthetic,'=1+1\n"
assert not any(name == 'django' or name.startswith('django.') for name in sys.modules)
assert all('ctf-data-security/backend' not in value for value in sys.path)
print(json.dumps({'installed_wheel': True, 'django_available': False, 'network_connections': 0,
    'source_hash': source_hash, 'target_plan_hash': plan.plan_hash,
    'output_hash': hashlib.sha256(output.binary).hexdigest(), 'target_approval': False}))
