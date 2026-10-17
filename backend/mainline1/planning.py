"""Internal proposed plan semantics. No execution, network, ORM or business writes.

Inputs.read must authenticate, authorize and read authoritative requirements,
policy, asset and review state each time. It must never accept these from a DTO.
Production owner composition is intentionally not installed. All private parse
material stays in the process; public match_ref contains identifiers only.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid5

from .classification import require
from .parsing import InputError, fingerprint
from .review import ReviewPrincipal, partition

CONTRACT = 'original-snapshot-v1-proposed'
OPS = ('mask_span', 'mask_cell', 'drop_column')
MAX_TARGETS = 1000
NS = UUID('2937d4af-8271-42bf-84d4-946f1f84fe43')


@dataclass(frozen=True)
class PlanPolicy:
    version: str = 'internal-redaction-v1-draft'
    uncertain: str = 'review'
    approved: bool = False
    contract_approved: bool = False
    requirements_approved: bool = False

    def __post_init__(self):
        require(type(self.version) is str and bool(self.version)
                and self.uncertain in ('review', 'mask_cell'), 'POLICY_INVALID')
        require(all(type(x) is bool for x in (self.approved, self.contract_approved,
                                             self.requirements_approved)), 'POLICY_INVALID')


@dataclass(frozen=True, repr=False)
class PlanInputs:
    bundle: dict
    parsed: object
    applicability: dict
    current_asset: dict
    asset_state: str
    asset_state_version: int
    current_policy_version: str
    requirements: list
    policy: PlanPolicy = field(default_factory=PlanPolicy)


class InputSource(Protocol):
    def read(self, principal, profile_id) -> PlanInputs: ...


def normalized_requirements(requirements, categories):
    require(type(requirements) is list and 0 < len(requirements) <= 100, 'REQUIREMENTS_INVALID')
    result, seen = [], set()
    fields = {'requirement_id', 'version', 'category_ids', 'allowed_operations',
              'allow_drop_column', 'require_complete_coverage', 'allow_unresolved'}
    for value in requirements:
        require(type(value) is dict and set(value) == fields, 'REQUIREMENTS_INVALID')
        item = deepcopy(value)
        require(all(type(item[k]) is str and 0 < len(item[k]) <= 128
                    for k in ('requirement_id', 'version')), 'REQUIREMENTS_INVALID')
        require(item['requirement_id'] not in seen, 'REQUIREMENTS_INVALID')
        seen.add(item['requirement_id'])
        for name, allowed in (('category_ids', categories), ('allowed_operations', OPS)):
            require(type(item[name]) is list and bool(item[name])
                    and all(type(v) is str and v in allowed for v in item[name]), 'REQUIREMENTS_INVALID')
            item[name] = sorted(set(item[name]))
        require(all(type(item[k]) is bool for k in ('allow_drop_column',
                    'require_complete_coverage', 'allow_unresolved')), 'REQUIREMENTS_INVALID')
        require('drop_column' not in item['allowed_operations'] or item['allow_drop_column'],
                'REQUIREMENTS_INVALID')
        result.append(item)
    return sorted(result, key=lambda r: r['requirement_id'])


def plan_digest(plan):
    value = deepcopy(plan)
    value.pop('plan_hash', None)
    value['meta'].pop('trace_id', None)
    return fingerprint(value)


def stable_id(value):
    return str(uuid5(NS, fingerprint(value)))


def cell_key(loc):
    return loc['sheet_id'], loc['row'], loc['column'], loc['channel']


def covers(target, location):
    if (target['sheet_id'], target['column']) != (location['sheet_id'], location['column']):
        return False
    if target['kind'] == 'column':
        return True
    if cell_key(target) != cell_key(location):
        return False
    if target['kind'] == 'cell':
        return True
    return (location['kind'] == 'span' and target['span']['start'] <= location['span']['start']
            and target['span']['end'] >= location['span']['end'])


def location_check(loc, parsed, *, structural=False):
    require(type(loc) is dict and set(loc) == {'kind', 'sheet_id', 'row', 'column', 'channel', 'span'},
            'LOCATION_MISMATCH')
    require(type(loc['sheet_id']) is str and type(loc['column']) is int and loc['column'] > 0
            and loc['channel'] in ('value', 'formula'), 'LOCATION_MISMATCH')
    if structural:
        require(loc['kind'] == 'column' and loc['row'] is None and loc['span'] is None
                and loc['channel'] == 'value', 'LOCATION_MISMATCH')
        structure = next((s for s in json.loads(parsed.structure_json) if s['sheet_id'] == loc['sheet_id']), None)
        selection = next((s for s in parsed.scope.selections if s.sheet_id == loc['sheet_id']), None)
        # A whole-column deletion includes headers, hidden rows and merged cells.
        # Reject unless the entire structural footprint is authorized and parsed.
        require(structure is not None and selection is not None and parsed.scope.include_header
                and selection.rows == ((1, structure['rows']),)
                and any(a <= loc['column'] <= b for a, b in selection.columns), 'SCOPE_MISMATCH')
        require(not structure.get('merged') and not parsed.excluded_contents
                and json.loads(parsed.config_json)['parser']['hidden_policy'] == 'include', 'SCOPE_MISMATCH')
        require(sum(c.sheet_id == loc['sheet_id'] and c.column == loc['column']
                    for c in parsed.cells) == structure['rows'], 'SCOPE_MISMATCH')
        return
    require(type(loc['row']) is int and loc['row'] > 0, 'LOCATION_MISMATCH')
    cell = next((c for c in parsed.cells if (c.sheet_id, c.row, c.column, c.channel) == cell_key(loc)), None)
    require(cell is not None, 'LOCATION_MISMATCH')
    if loc['kind'] == 'cell':
        require(loc['span'] is None, 'LOCATION_MISMATCH')
        return
    span = loc['span']
    require(loc['kind'] == 'span' and loc['channel'] == 'value' and type(span) is dict
            and set(span) == {'start', 'end'}, 'LOCATION_MISMATCH')
    require(type(span['start']) is int and type(span['end']) is int
            and 0 <= span['start'] < span['end'] <= len(cell.source_text), 'LOCATION_MISMATCH')
    _, mapping = cell.mapping()
    require(mapping is not None and span['start'] in {a for a, _ in mapping}
            and span['end'] in {b for _, b in mapping}, 'LOCATION_MISMATCH')


def context_errors(ctx):
    p, s, parsed, app = ctx.bundle['profile'], ctx.bundle['snapshot'], ctx.parsed, ctx.applicability
    errors = set()
    if ctx.asset_state != 'ready':
        errors.add('ASSET_UNAVAILABLE')
    if ctx.current_asset != p['asset'] or s['asset'] != p['asset'] or (
            parsed.asset_version_id, parsed.input_content_hash) != (
            p['asset']['asset_version_id'], p['asset']['content_hash']):
        errors.add('ASSET_VERSION_MISMATCH')
    if p['scope_hash'] != parsed.scope_hash or s['scope_hash'] != parsed.scope_hash or fingerprint(asdict(parsed.scope)) != parsed.scope_hash or s['scope'] != json.loads(json.dumps(asdict(parsed.scope))):
        errors.add('SCOPE_MISMATCH')
    if s['parser_version'] != parsed.parser_version or s['parser_config_hash'] != parsed.config_hash or fingerprint(json.loads(parsed.config_json)) != parsed.config_hash:
        errors.add('PARSER_MISMATCH')
    if s['parsed_cells_hash'] != fingerprint([asdict(c) for c in parsed.cells]) or s['parse_metadata_hash'] != fingerprint([
            parsed.structure_json, parsed.coverage_json, list(parsed.warnings), list(parsed.excluded_contents)]):
        errors.add('LOCATION_MISMATCH')
    if app['profile_id'] != p['profile_id'] or app['asset_version_id'] != p['asset']['asset_version_id'] or app['affected_scope_hash'] != p['scope_hash']:
        errors.add('APPLICABILITY_MISMATCH')
    if app['status'] != 'current':
        errors.add({'superseded': 'PROFILE_SUPERSEDED', 'reevaluation_required': 'PROFILE_REEVALUATION_REQUIRED',
                    'unverifiable_deleted': 'PROFILE_UNVERIFIABLE'}.get(app['status'], 'APPLICABILITY_UNAVAILABLE'))
    if app['usable_for_new_decision'] is not True:
        errors.add('PROFILE_NOT_USABLE')
    if not all((ctx.policy.approved, ctx.policy.contract_approved, ctx.policy.requirements_approved)):
        errors.add('PLAN_APPROVAL_REQUIRED')
    effective = ctx.bundle.get('regrade', {}).get('configuration', s['configuration'])
    if p['policy_version'] != effective['policy']['version'] or p['policy_version'] != ctx.current_policy_version:
        errors.add('POLICY_MISMATCH')
    if p['finding_ids'] != [f['finding_id'] for f in ctx.bundle['findings']] or len(set(p['finding_ids'])) != len(p['finding_ids']):
        errors.add('PROFILE_MISMATCH')
    return errors


def obligations(ctx, requirements):
    """Independent obligation enumeration; never trusts a plan's unresolved list."""
    pending, targets = set(), []
    profile = ctx.bundle['profile']
    for req in requirements:
        rid = req['requirement_id']
        if profile['combination_finding_ids']:
            pending.add(rid + ':COMBINATION_UNSUPPORTED')
        if profile['quality'] != 'complete':
            pending.add(rid + ':COVERAGE_INCOMPLETE')
        required_layers = ['parse', 'rule']
        for layer in ('semantic', 'combination'):
            if ctx.bundle['snapshot'].get(layer + '_required'):
                required_layers.append(layer)
        if any(profile['coverage'][layer]['status'] != 'complete' for layer in required_layers):
            pending.add(rid + ':COVERAGE_INCOMPLETE')
        for finding in ctx.bundle['findings']:
            if finding['category_id'] is None:
                pending.add(rid + ':CATEGORY_UNRESOLVED')
                continue
            if finding['category_id'] not in req['category_ids']:
                continue
            if not finding['locations'] or finding.get('kind') == 'combination':
                pending.add(rid + ':LOCATION_UNRESOLVED')
                continue
            for loc in finding['locations']:
                uncertain = finding['judgment'] != 'determined'
                try:
                    location_check(loc, ctx.parsed)
                except InputError:
                    # Downgrade is permitted only to a demonstrably exact cell.
                    uncertain = True
                    loc = dict(loc, kind='cell', span=None)
                    try:
                        location_check(loc, ctx.parsed)
                    except InputError:
                        pending.add(rid + ':LOCATION_UNRESOLVED')
                        continue
                if uncertain and ctx.policy.uncertain == 'review':
                    pending.add(rid + ':REVIEW_REQUIRED')
                    continue
                targets.append((req, finding, loc, uncertain))
                require(len(targets) <= MAX_TARGETS, 'RESOURCE_LIMIT')
    return targets, pending


def operation_allowed(op, req, loc, uncertain):
    return (op['type'] in req['allowed_operations']
            and (op['type'] != 'drop_column' or req['allow_drop_column'])
            and (not uncertain or op['type'] in ('mask_cell', 'drop_column'))
            and covers(op['target'], loc))


def binding(ctx, requirements):
    p, s = ctx.bundle['profile'], ctx.bundle['snapshot']
    return dict(meta=deepcopy(p['meta']), asset=deepcopy(p['asset']), scan_id=p['scan_id'],
        profile_id=p['profile_id'], scope_hash=p['scope_hash'], parser_version=s['parser_version'],
        parser_config_hash=s['parser_config_hash'], policy_version=p['policy_version'],
        redaction_policy_version=ctx.policy.version, requirements=requirements,
        requirements_hash=fingerprint(requirements), operation_contract_version=CONTRACT)


def inspect_operations(plan, ctx, requirements):
    errors, seen = set(), set()
    operations = plan['operations']
    require(type(operations) is list and len(operations) <= MAX_TARGETS, 'PLAN_INPUT_INVALID')
    targets, pending = obligations(ctx, requirements)
    reqs = {r['requirement_id']: r for r in requirements}
    findings = {f['finding_id']: f for f in ctx.bundle['findings']}
    valid_ops = []
    for op in operations:
        try:
            require(type(op) is dict and set(op) == {'operation_id', 'type', 'target', 'replacement',
                'match_ref', 'finding_ids', 'requirement_ids'}, 'PLAN_INPUT_INVALID')
            require(op['type'] in OPS, 'OPERATION_UNSUPPORTED')
            require(type(op['operation_id']) is str and str(UUID(op['operation_id'])) == op['operation_id'], 'PLAN_INPUT_INVALID')
            require(op['operation_id'] not in seen, 'PLAN_CONFLICT')
            seen.add(op['operation_id'])
            require(op['replacement'] == (None if op['type'] == 'drop_column' else '[REDACTED]'), 'OPERATION_PARAMETERS_INVALID')
            require(op['target']['kind'] == dict(mask_span='span', mask_cell='cell', drop_column='column')[op['type']], 'LOCATION_MISMATCH')
            location_check(op['target'], ctx.parsed, structural=op['type'] == 'drop_column')
            require(op['match_ref'] == 'private:plan-match:' + plan['plan_id'] + ':' + op['operation_id'], 'LOCATION_MISMATCH')
            for key, known in (('finding_ids', findings), ('requirement_ids', reqs)):
                require(type(op[key]) is list and bool(op[key]) and all(type(v) is str and v in known for v in op[key])
                        and op[key] == sorted(set(op[key])), 'PLAN_REFERENCE_INVALID')
            for rid in op['requirement_ids']:
                require(any(req['requirement_id'] == rid and f['finding_id'] in op['finding_ids']
                            and operation_allowed(op, req, loc, uncertain) for req, f, loc, uncertain in targets), 'PLAN_REFERENCE_INVALID')
            for fid in op['finding_ids']:
                require(any(f['finding_id'] == fid and req['requirement_id'] in op['requirement_ids']
                            and operation_allowed(op, req, loc, uncertain) for req, f, loc, uncertain in targets), 'PLAN_REFERENCE_INVALID')
            valid_ops.append(op)
        except (InputError, ValueError, TypeError, KeyError) as exc:
            errors.add(exc.code if isinstance(exc, InputError) else 'PLAN_INPUT_INVALID')
    for i, first in enumerate(valid_ops):
        a = first['target']
        for second in valid_ops[i + 1:]:
            b = second['target']
            if (a['sheet_id'], a['column']) != (b['sheet_id'], b['column']):
                continue
            if 'column' in (a['kind'], b['kind']):
                errors.add('PLAN_CONFLICT')
            elif cell_key(a) == cell_key(b) and ('cell' in (a['kind'], b['kind']) or
                    max(a['span']['start'], b['span']['start']) < min(a['span']['end'], b['span']['end'])):
                errors.add('PLAN_CONFLICT')
    for req, finding, loc, uncertain in targets:
        if not any(req['requirement_id'] in op['requirement_ids'] and finding['finding_id'] in op['finding_ids']
                   and operation_allowed(op, req, loc, uncertain) for op in valid_ops):
            pending.add(req['requirement_id'] + ':TARGET_UNCOVERED')
    return errors, pending


def status_for(errors, pending, requirements):
    if errors or (pending and not all(r['allow_unresolved'] for r in requirements)):
        return 'invalid'
    return 'partial' if pending else 'ready'


class PlanService:
    """Bounded process-local build replay/pagination; not a durable public service."""
    def __init__(self, source: InputSource, *, cursor_key, clock=None):
        require(type(cursor_key) is bytes and len(cursor_key) >= 32, 'CONFIG_INVALID')
        self.source, self.cursor_key = source, cursor_key
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._plans, self._keys, self._lock = {}, {}, RLock()

    def _read(self, principal, profile_id):
        require(isinstance(principal, ReviewPrincipal) and type(principal.actor_id) is int
                and principal.actor_id > 0, 'OBJECT_NOT_FOUND')
        ctx = self.source.read(principal, profile_id)
        require(isinstance(ctx, PlanInputs), 'AUTHORITY_UNAVAILABLE')
        p = ctx.bundle['profile']
        require(p['profile_id'] == profile_id and partition(p) == (
            principal.domain_id, principal.environment, principal.evaluation_run_id), 'OBJECT_NOT_FOUND')
        categories = {c['category_id'] for c in ctx.bundle['snapshot']['configuration']['policy']['categories']}
        return ctx, normalized_requirements(ctx.requirements, categories)

    def build(self, principal, profile_id, *, idempotency_key):
        require(type(idempotency_key) is str and 0 < len(idempotency_key) <= 128, 'PLAN_INPUT_INVALID')
        ctx, reqs = self._read(principal, profile_id)
        base = binding(ctx, reqs)
        # Never put private parsed-cell digests or raw values in public IDs/hashes.
        request = dict(binding=deepcopy(base), policy=asdict(ctx.policy), applicability=ctx.applicability['state_version'],
                       asset_state=ctx.asset_state, asset_state_version=ctx.asset_state_version,
                       current_asset=ctx.current_asset, current_policy_version=ctx.current_policy_version)
        request['binding']['meta'] = {k: v for k, v in base['meta'].items() if k != 'trace_id'}
        request_hash = fingerprint(request)
        key = (principal.domain_id, principal.environment, principal.evaluation_run_id, principal.actor_id, idempotency_key)
        with self._lock:
            if key in self._keys:
                prior, pid = self._keys[key]
                require(prior == request_hash, 'IDEMPOTENCY_CONFLICT')
                return deepcopy(self._plans[pid])
            require(len(self._plans) < 100, 'RESOURCE_LIMIT')
            pid = stable_id([list(key), request_hash])
            plan = dict(base, plan_id=pid, operations=[], operation_count=0, unresolved=[], validation_errors=[],
                        status='invalid', checked_applicability_version=ctx.applicability['state_version'],
                        validation_ref='private:plan-validation:' + pid)
            targets, _ = obligations(ctx, reqs)
            grouped = {}
            for req, finding, loc, uncertain in targets:
                for kind in OPS:
                    if kind not in req['allowed_operations'] or (uncertain and kind == 'mask_span'):
                        continue
                    if kind == 'mask_span' and loc['kind'] != 'span':
                        continue
                    target = dict(loc, kind={'mask_span': 'span', 'mask_cell': 'cell', 'drop_column': 'column'}[kind])
                    if kind != 'mask_span':
                        target['span'] = None
                    if kind == 'drop_column':
                        target.update(row=None, channel='value')
                    try:
                        location_check(target, ctx.parsed, structural=kind == 'drop_column')
                    except InputError:
                        continue
                    group = fingerprint([kind, target])
                    if group not in grouped:
                        oid = stable_id([pid, group])
                        grouped[group] = dict(operation_id=oid, type=kind, target=target,
                            replacement=None if kind == 'drop_column' else '[REDACTED]',
                            match_ref='private:plan-match:' + pid + ':' + oid, finding_ids=[], requirement_ids=[])
                    op = grouped[group]
                    op['finding_ids'] = sorted(set(op['finding_ids'] + [finding['finding_id']]))
                    op['requirement_ids'] = sorted(set(op['requirement_ids'] + [req['requirement_id']]))
                    break
            plan['operations'] = sorted(grouped.values(), key=lambda op: op['operation_id'])
            plan['operation_count'] = len(plan['operations'])
            errors, pending = inspect_operations(plan, ctx, reqs)
            errors |= context_errors(ctx)
            plan.update(unresolved=sorted(pending), validation_errors=sorted(errors), status=status_for(errors, pending, reqs))
            plan['plan_hash'] = plan_digest(plan)
            self._keys[key], self._plans[pid] = (request_hash, pid), deepcopy(plan)
            return deepcopy(plan)

    def validate(self, principal, plan):
        """Read authority each call. Return a fresh result; never mutate even a stale plan."""
        observed_asset = observed_app = None
        errors, pending = set(), set()
        try:
            ctx, reqs = self._read(principal, plan['profile_id'])
            observed_asset, observed_app = ctx.asset_state_version, ctx.applicability['state_version']
            errors |= context_errors(ctx)
            expected = binding(ctx, reqs)
            require(set(plan) == set(expected) | {'plan_id', 'plan_hash', 'operations', 'operation_count',
                'unresolved', 'validation_errors', 'status', 'checked_applicability_version', 'validation_ref'}, 'PLAN_INPUT_INVALID')
            require(type(plan['checked_applicability_version']) is int
                    and plan['checked_applicability_version'] > 0
                    and plan['status'] in ('ready', 'partial', 'invalid')
                    and all(type(plan[name]) is list and all(type(v) is str for v in plan[name])
                            for name in ('unresolved', 'validation_errors')), 'PLAN_INPUT_INVALID')
            for name, value in expected.items():
                actual = plan[name]
                if name == 'meta':
                    actual = {k: v for k, v in actual.items() if k != 'trace_id'}
                    value = {k: v for k, v in value.items() if k != 'trace_id'}
                if actual != value:
                    errors.add('PLAN_BINDING_MISMATCH')
            require(str(UUID(plan['plan_id'])) == plan['plan_id'], 'PLAN_INPUT_INVALID')
            if plan['plan_hash'] != plan_digest(plan):
                errors.add('PLAN_HASH_MISMATCH')
            if type(plan['operation_count']) is not int or plan['operation_count'] != len(plan['operations']):
                errors.add('PLAN_COUNT_MISMATCH')
            if plan['checked_applicability_version'] != observed_app:
                errors.add('APPLICABILITY_VERSION_MISMATCH')
            if plan['validation_ref'] != 'private:plan-validation:' + plan['plan_id']:
                errors.add('PLAN_REFERENCE_INVALID')
            op_errors, pending = inspect_operations(plan, ctx, reqs)
            errors |= op_errors
            if plan['unresolved'] != sorted(pending):
                errors.add('PLAN_COVERAGE_MISMATCH')
            # Historical errors/status never override the current independent result.
            if plan['validation_errors'] or plan['status'] != 'ready':
                errors.add('PLAN_NOT_READY')
            if pending:
                errors.add('COVERAGE_INCOMPLETE')
        except InputError as exc:
            if exc.code == 'OBJECT_NOT_FOUND':
                raise
            errors.add(exc.code)
        except (KeyError, TypeError, ValueError, AttributeError):
            errors.add('PLAN_INPUT_INVALID')
        except Exception:
            errors.add('AUTHORITY_UNAVAILABLE')
        return dict(valid=not errors and not pending, error_codes=sorted(errors),
            plan_hash=plan.get('plan_hash') if isinstance(plan, dict) else None,
            observed_asset_state_version=observed_asset, observed_applicability_version=observed_app,
            checked_at=self.clock().isoformat())

    def page(self, principal, plan_id, *, cursor=None, page_size=50):
        require(type(page_size) is int and 1 <= page_size <= 200, 'CURSOR_INVALID')
        with self._lock:
            require(plan_id in self._plans, 'OBJECT_NOT_FOUND')
            plan = deepcopy(self._plans[plan_id])
        # Reauthorize every page, but keep the old immutable plan even after review.
        self._read(principal, plan['profile_id'])
        scope = [principal.domain_id, principal.environment, principal.evaluation_run_id, principal.actor_id]
        now, offset = int(self.clock().timestamp()), 0
        expiry = now + 900
        if cursor is not None:
            try:
                payload, signature = cursor.rsplit('.', 1)
                require(hmac.compare_digest(hmac.new(self.cursor_key, payload.encode(), hashlib.sha256).hexdigest(), signature), 'CURSOR_INVALID')
                value = json.loads(bytes.fromhex(payload))
                require(value['scope'] == scope and value['plan_hash'] == plan['plan_hash']
                        and value['size'] == page_size, 'CURSOR_INVALID')
                require(value['expires'] > now, 'CURSOR_EXPIRED')
                offset, expiry = value['offset'], value['expires']
            except InputError:
                raise
            except (ValueError, KeyError, TypeError, AttributeError):
                raise InputError('CURSOR_INVALID') from None
        end = offset + page_size
        next_cursor = None
        if end < plan['operation_count']:
            payload = json.dumps(dict(scope=scope, plan_hash=plan['plan_hash'], size=page_size,
                offset=end, expires=expiry), sort_keys=True, separators=(',', ':')).encode().hex()
            next_cursor = payload + '.' + hmac.new(self.cursor_key, payload.encode(), hashlib.sha256).hexdigest()
        return dict(plan_header={k: v for k, v in plan.items() if k != 'operations'},
            operations_hash=fingerprint(plan['operations']), operations=plan['operations'][offset:end], next_cursor=next_cursor)
