"""Deterministic format-rule baseline over authorized ParseResult objects.

Public-shaped findings/profiles remain Proposed; snapshot and outcome are internal.
No semantic call, external authorization, profile-head mutation or policy activation.
"""
import ipaddress
import json
import re
import time
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass, field
from uuid import UUID, uuid5

from .classification import BusinessContext, RuleConfiguration, canonical, identifier, require, validate_meta
from .parsing import InputError, fingerprint

ENGINE_VERSION = 'format-rule-engine-v1'
EMAIL = re.compile(r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+")
IPV4 = re.compile(r'(?<![0-9A-Za-z_.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9A-Za-z_.])')
CARD = re.compile(r'(?<![0-9A-Za-z])[0-9]{13,19}(?![0-9A-Za-z])')


def candidates(implementation, text):
    if implementation == 'email_ascii_v1':
        for match in EMAIL.finditer(text):
            value = match.group().rstrip('.')
            local, domain = value.split('@')
            labels = domain.split('.')
            if (len(local) <= 64 and not local.startswith('.') and not local.endswith('.') and '..' not in local
                    and len(domain) <= 253 and len(labels) >= 2 and labels[-1].isalpha()
                    and all(label and len(label) <= 63 and label[0].isalnum() and label[-1].isalnum() for label in labels)):
                yield match.start(), match.start() + len(value), 'ASCII_EMAIL_SYNTAX'
    elif implementation == 'ipv4_v1':
        for match in IPV4.finditer(text):
            try:
                ipaddress.IPv4Address(match.group())
            except ipaddress.AddressValueError:
                continue
            yield match.start(), match.end(), 'IPV4_OCTETS_VALID'
    elif implementation == 'luhn_candidate_v1':
        for match in CARD.finditer(text):
            digits = [int(char) for char in match.group()]
            total = sum((2 * digit - 9 if digit >= 5 else 2 * digit) if i % 2 else digit
                        for i, digit in enumerate(reversed(digits)))
            if len(set(digits)) > 1 and total % 10 == 0:
                yield match.start(), match.end(), 'LUHN_VALID_NOT_ACCOUNT_PROOF'
    else:
        raise InputError('RULE_IMPLEMENTATION_UNSUPPORTED')


@dataclass(frozen=True)
class RuleResult:
    payload: str = field(repr=False)

    def data(self):
        return json.loads(self.payload)

    def resolve_private(self, reference):
        """Resolve in-bundle manifests/config only; source access belongs to the asset owner."""
        value = self.data()
        if reference in value['manifests']:
            return value['manifests'][reference]
        prefix = 'private:rule-config:' + value['request_fingerprint'] + ':'
        if reference.startswith(prefix):
            for rule in value['snapshot']['configuration']['rules']:
                if rule['rule_id'] == reference[len(prefix):]:
                    return rule
        raise InputError('OBJECT_NOT_FOUND')


class RuleCache:
    """Opt-in private process cache. No global instance, filesystem or raw-text key.

    Capacity and TTL are explicit; expired entries are purged on access or clear().
    Internal single-worker use only; no distributed idempotency claim.
    """
    def __init__(self, *, ttl_seconds, max_entries, max_bytes=4 * 1024 * 1024, clock=time.monotonic):
        require(type(ttl_seconds) is int and 0 < ttl_seconds <= 3600)
        require(type(max_entries) is int and 0 < max_entries <= 100)
        require(type(max_bytes) is int and 0 < max_bytes <= 64 * 1024 * 1024)
        self.ttl, self.capacity, self.clock = ttl_seconds, max_entries, clock
        self.max_bytes = max_bytes
        self.rows = OrderedDict()

    def clear(self):
        self.rows.clear()

    def get(self, key):
        now = self.clock()
        for expired in [k for k, (deadline, _) in self.rows.items() if deadline <= now]:
            del self.rows[expired]
        found = self.rows.get(key)
        return RuleResult(found[1]) if found else None

    def put(self, key, result):
        self.get(key)
        if len(result.payload.encode('utf-8')) > self.max_bytes:
            return
        self.rows[key] = (self.clock() + self.ttl, result.payload)
        self.rows.move_to_end(key)
        while (len(self.rows) > self.capacity
               or sum(len(value[1].encode('utf-8')) for value in self.rows.values()) > self.max_bytes):
            self.rows.popitem(last=False)


def scan_rules(parsed, configuration: RuleConfiguration, context: BusinessContext, *, meta, asset,
               principal, scan_id, applicability_ref, parsed_ref, semantic_required=True,
               max_findings=10000, cancelled=lambda: False, cache=None):
    """Trusted internal boundary; callers must authorize asset and refs before EVERY call.

    applicability_ref is an owner-reserved ID, NOT proof an applicability service exists.
    Configuration is development-only. No arbitrary regex/code can be supplied.
    """
    validate_meta(meta)
    identifier(scan_id)
    identifier(applicability_ref)
    require(isinstance(principal, str) and principal, 'OBJECT_NOT_FOUND')
    require(type(semantic_required) is bool and type(max_findings) is int and 0 < max_findings <= 10000)
    require(isinstance(parsed_ref, str) and parsed_ref.startswith('private:') and len(parsed_ref) > 8)
    require(set(asset) == {'asset_id', 'asset_version_id', 'content_hash'})
    identifier(asset['asset_id'])
    identifier(asset['asset_version_id'])
    require(asset['asset_version_id'] == parsed.asset_version_id and asset['content_hash'] == parsed.input_content_hash, 'ASSET_VERSION_MISMATCH')
    cfg = RuleConfiguration.load(configuration.data()).data()
    policy, rules = cfg['policy'], cfg['rules']
    require(meta['environment'] in cfg['allowed_environments'], 'POLICY_NOT_ACTIVE')
    ctx = context.data()
    require(ctx['content_hash'] == fingerprint({k: v for k, v in ctx.items() if k != 'content_hash'}), 'CONTEXT_INVALID')
    receipt = None
    if ctx['confirmation'] == 'confirmed':
        from .classification import ConfirmationReceipt
        receipt = ConfirmationReceipt(ctx['confirmed_by'], ctx['confirmed_at'])
    # Revalidate the immutable object instead of trusting direct dataclass construction.
    rebuilt = BusinessContext.create(**{k: v for k, v in ctx.items() if k not in ('content_hash', 'confirmed_by', 'confirmed_at')},
                                     confirmation_receipt=receipt)
    require(rebuilt.data() == ctx, 'CONTEXT_INVALID')
    require(all(ctx['meta'][k] == meta[k] for k in ('domain_id', 'environment', 'evaluation_run_id')), 'DOMAIN_MISMATCH')
    require(ctx['asset_version_id'] == parsed.asset_version_id and ctx['scope_hash'] == parsed.scope_hash, 'CONTEXT_SCOPE_MISMATCH')
    require(parsed.scope.asset_version_id == parsed.asset_version_id
            and fingerprint(asdict(parsed.scope)) == parsed.scope_hash, 'SCOPE_INVALID')
    parse_config = json.loads(parsed.config_json)
    require(fingerprint(parse_config) == parsed.config_hash, 'CONFIG_HASH_MISMATCH')
    parse_cov = json.loads(parsed.coverage_json)['parse']
    locations = [(c.sheet_id, c.row, c.column) for c in parsed.cells]
    require(len(locations) == len(set(locations)) and len(parsed.cells) <= 200000, 'PARSED_ASSET_INVALID')
    require(parse_cov['status'] == 'complete' and parse_cov['target_count'] == len(parsed.cells)
            and parse_cov['processed_count'] == len(parsed.cells)
            and parse_cov['failed_count'] == 0 and parse_cov['skipped_count'] == 0
            and parse_cov['processed_locations'] == [list(x) for x in locations], 'PARSED_ASSET_INVALID')
    # The sealed parse output is part of the key, even if a faulty caller reuses a reference.
    snapshot = dict(engine_version=ENGINE_VERSION, scan_id=scan_id, meta=meta, principal=principal,
                    asset=asset, scope=asdict(parsed.scope), scope_hash=parsed.scope_hash,
                    parser_version=parsed.parser_version, parser_config=parse_config,
                    parser_config_hash=parsed.config_hash, parsed_ref=parsed_ref,
                    parsed_cells_hash=fingerprint([asdict(c) for c in parsed.cells]),
                    parse_metadata_hash=fingerprint([parsed.structure_json, parsed.coverage_json,
                                                     list(parsed.warnings), list(parsed.excluded_contents)]),
                    context=ctx, configuration=cfg, applicability_ref=applicability_ref,
                    model=None, fusion_version='not_run', sampling={'mode': 'all', 'seed': None},
                    semantic_required=semantic_required, combination_required=False,
                    scan_policy_version='rule-baseline-scan-v1', max_findings=max_findings)
    request_hash = fingerprint(snapshot)
    if cancelled():
        raise InputError('TASK_CANCELLED')
    if cache:
        found = cache.get(request_hash)
        if found:
            return found
    categories = {c['category_id']: c for c in policy['categories']}
    findings, outcomes, processed, failed, skipped = [], [], [], [], []
    active = [rule for rule in rules if rule['enabled']]
    disabled = len(active) != len(rules)
    prefix = f'private:rule-run:{scan_id}'
    for cell in parsed.cells:
        if cancelled():
            raise InputError('TASK_CANCELLED')
        base = dict(sheet_id=cell.sheet_id, row=cell.row, column=cell.column, channel=cell.channel)
        if not active:
            skipped.append(base)
            outcomes.append(dict(location=base, status='not_detected', category_ids=[], reason_codes=['RULES_DISABLED']))
            continue
        hits, errors = {}, []
        for rule in active:
            try:
                require(len(cell.source_text) <= 32768, 'RESOURCE_LIMIT')
                text = cell.normalized_text
                require(len(text) <= 32768, 'RESOURCE_LIMIT')
                for start, end, reason in candidates(rule['implementation'], text):
                    try:
                        first, last = cell.source_span(start, end)
                        loc = dict(base, kind='span', span=dict(start=first, end=last))
                        uncertain = ['FORMAT_MATCH_NOT_BUSINESS_FACT']
                    except InputError:
                        loc = dict(base, kind='cell', span=None)
                        uncertain = ['FORMAT_MATCH_NOT_BUSINESS_FACT', 'LOCATION_UNRELIABLE']
                    key = (rule['category_id'], canonical(loc))
                    if key not in hits:
                        require(len(findings) + len(hits) < max_findings, 'RESOURCE_LIMIT')
                        hits[key] = dict(category=rule['category_id'], location=loc, reasons=uncertain, evidence=[])
                    hits[key]['evidence'].append(dict(evidence_ref=f"private:rule-config:{request_hash}:{rule['rule_id']}",
                                                      kind='rule', reason_code=reason))
            except InputError as exc:
                errors.append('RESOURCE_LIMIT' if exc.code == 'RESOURCE_LIMIT' else 'RULE_DETECTION_FAILED')
            except Exception:
                errors.append('RULE_DETECTION_FAILED')  # Never persist exception text or raw matches.
        if errors:
            failed.append(base)
        else:
            processed.append(base)
        def overlaps(a, b):
            left, right = a['location']['span'], b['location']['span']
            return left is None or right is None or max(left['start'], right['start']) < min(left['end'], right['end'])
        conflicted = {key for key, hit in hits.items() if any(
            hit['category'] != other['category'] and overlaps(hit, other) for other in hits.values())}
        conflict = bool(conflicted)
        ids = sorted({hit['category'] for hit in hits.values()})
        for key, hit in sorted(hits.items()):
            reasons = set(hit['reasons']) | set(categories[hit['category']]['review_conditions'])
            if ctx['confirmation'] == 'conflicted':
                reasons.add('CONTEXT_CONFLICT')
            elif not ctx['scenario'] and not ctx['field_descriptions'] and not ctx['table_description']:
                reasons.add('CONTEXT_MISSING')
            elif ctx['confirmation'] != 'confirmed':
                reasons.add('CONTEXT_UNCONFIRMED')
            if key in conflicted:
                reasons.add('CATEGORY_CONFLICT')
            reasons.update(errors)
            fid = str(uuid5(UUID(scan_id), request_hash + canonical([ENGINE_VERSION, key])))
            findings.append(dict(meta=meta, finding_id=fid, scan_id=scan_id, kind='entity', locations=[hit['location']],
                category_id=hit['category'], judgment='conflict' if key in conflicted or ctx['confirmation'] == 'conflicted'
                else 'insufficient' if 'LOCATION_UNRELIABLE' in reasons else 'pending_review', source_type='rule',
                detector_id=ENGINE_VERSION, detector_version=policy['ruleset_version'], source_finding_ids=[],
                relation_type=None, evidence=hit['evidence'] + [dict(evidence_ref=parsed_ref, kind='cell', reason_code='FIXED_PARSED_CELL')],
                uncertainty_reasons=sorted(reasons), raw_score=None, score_meaning=None,
                calibrated_probability=None, calibration_version=None, created_by=None, review_id=None))
        status = 'detection_failed' if errors else 'conflict' if conflict else 'insufficient_evidence' if hits else 'no_match'
        outcomes.append(dict(location=base, status=status, category_ids=ids,
                             reason_codes=sorted(set(errors)) if errors else ['FORMAT_CANDIDATE'] if hits else ['EMPTY_VALUE'] if not cell.source_text else ['NO_RULE_MATCH']))
    def layer(status, count, done, skipped_count=0, failed_count=0, reasons=(), name='rule', unit='cell'):
        return dict(status=status, unit=unit, target_count=count, processed_count=done,
                    skipped_count=skipped_count, failed_count=failed_count, ratio=done / count if count else None,
                    target_scope_ref=prefix + ':' + name + ':target',
                    processed_scope_ref=prefix + ':' + name + ':processed' if done else None,
                    skipped_scope_ref=prefix + ':' + name + ':skipped' if skipped_count else None,
                    failed_scope_ref=prefix + ':' + name + ':failed' if failed_count else None,
                    reason_codes=list(reasons))
    rule_status = 'not_run' if not active else 'partial' if failed or disabled else 'complete'
    rule_reasons = sorted(({'RULES_DISABLED'} if disabled else set()) | {
        reason for outcome in outcomes if outcome['status'] == 'detection_failed' for reason in outcome['reason_codes']})
    coverage = dict(parse=layer('complete', len(parsed.cells), len(parsed.cells), name='parse'),
                    rule=layer(rule_status, len(parsed.cells), len(processed), len(skipped), len(failed),
                               rule_reasons),
                    semantic=layer('not_run', None, 0, reasons=['SEMANTIC_NOT_RUN'], name='semantic'),
                    combination=layer('not_run', None, 0, reasons=['COMBINATION_NOT_RUN'], name='combination', unit='relation'))
    counts = Counter(f['category_id'] for f in findings)
    selected_levels = [categories[c]['protection_level'] for c in counts]
    level = max(selected_levels, key=policy['levels'].index) if selected_levels else None
    profile = dict(meta=meta, profile_id=str(uuid5(UUID(scan_id), 'profile:' + request_hash)), asset=asset,
        scan_id=scan_id, scope_hash=parsed.scope_hash,
        quality='complete' if rule_status == 'complete' and not semantic_required else 'partial',
        coverage=coverage, finding_ids=[f['finding_id'] for f in findings],
        category_counts=[dict(category_id=c, count=counts[c]) for c in sorted(counts)],
        combination_finding_ids=[], protection_level=level, policy_version=policy['version'],
        detector_versions=[ENGINE_VERSION, policy['ruleset_version']],
        review_status='pending' if findings or failed else 'not_required', supersedes_profile_id=None,
        applicability_ref=applicability_ref,
        limitations=['DEVELOPMENT_POLICY_DRAFT', 'FORMAT_ONLY_NOT_BUSINESS_FACT', 'SEMANTIC_NOT_RUN',
                     'COMBINATION_NOT_RUN', 'APPLICABILITY_NOT_PUBLISHED', 'NO_OUTBOUND_AUTHORIZATION'], person_count=None)
    # Private lists resolve the in-bundle coverage references; no invented remote storage.
    manifests = {prefix + ':parse:target': locations, prefix + ':parse:processed': locations,
                 prefix + ':parse:excluded': parse_cov['excluded_locations'],
                 prefix + ':rule:target': [o['location'] for o in outcomes],
                 prefix + ':rule:processed': processed, prefix + ':rule:failed': failed,
                 prefix + ':rule:skipped': skipped, prefix + ':semantic:target': None,
                 prefix + ':combination:target': None}
    result = RuleResult(json.dumps(dict(snapshot=snapshot, request_fingerprint=request_hash, findings=findings,
                                       profile=profile, cell_outcomes=outcomes, manifests=manifests),
                                  ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False))
    if cache and rule_status == 'complete':
        cache.put(request_hash, result)
    return result
