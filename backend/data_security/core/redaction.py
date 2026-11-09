"""Three existing format detectors and source-coordinate transformations.

Credential confidentiality below is legacy compatibility, not a fourth detector.
No business policy, context lookup, implicit randomness, or external I/O lives here.
"""
import base64
from dataclasses import replace
import ipaddress
import re

from data_security.contracts import (Algorithm, BoundedPayload, Category, ContractViolation,
    Finding, FrozenJSON, Level, Limits, Location, LocationKind, PayloadKind,
    ProtectionError, ReasonCode, ResolvedAction, TableSnapshot)
from data_security.contracts.schema import canonical_bytes, require
from data_security.core.crypto import scoped_hmac

RULE_VERSION = 'existing-formats.v1'
EMAIL = re.compile(r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+")
IPV4 = re.compile(r'(?<![0-9A-Za-z_.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9A-Za-z_.])')
CARD = re.compile(r'(?<![0-9A-Za-z])[0-9]{13,19}(?![0-9A-Za-z])')
LEVELS = {Category.EMAIL: Level.L2, Category.IPV4: Level.L1,
          Category.CARD: Level.L3, Category.SECRET: Level.L3}
PRIORITY = {Category.IPV4: 0, Category.EMAIL: 1, Category.CARD: 2, Category.SECRET: 3}


def _matches(text):
    for match in EMAIL.finditer(text):
        value = match.group().rstrip('.')
        local, domain = value.split('@')
        labels = domain.split('.')
        if (len(local) <= 64 and not local.startswith('.') and not local.endswith('.') and '..' not in local
                and len(domain) <= 253 and len(labels) >= 2 and labels[-1].isalpha()
                and all(label and len(label) <= 63 and label[0].isalnum() and label[-1].isalnum() for label in labels)):
            yield Category.EMAIL, match.start(), match.start() + len(value)
    for match in IPV4.finditer(text):
        try:
            ipaddress.IPv4Address(match.group())
        except ipaddress.AddressValueError:
            continue
        yield Category.IPV4, match.start(), match.end()
    for match in CARD.finditer(text):
        digits = [int(char) for char in match.group()]
        total = sum((2 * digit - 9 if digit >= 5 else 2 * digit) if i % 2 else digit
                    for i, digit in enumerate(reversed(digits)))
        if len(set(digits)) > 1 and total % 10 == 0:
            yield Category.CARD, match.start(), match.end()


def _location(kind, *, path=(), start=None, end=None, cell=None):
    return Location(schema_version=Location.SCHEMA, kind=kind, json_path=path, start=start, end=end,
        sheet_id=cell.sheet_id if cell else None, column_id=cell.column_id if cell else None,
        source_row=cell.source_row if cell else None)


def _bounded(payload, limits):
    require(type(limits) is Limits, ReasonCode.INVALID_TYPE)
    require(type(payload) in (BoundedPayload, TableSnapshot), ReasonCode.INVALID_TYPE)
    # A caller cannot relax the limits embedded by the upstream boundary.
    for name in limits.__dataclass_fields__:
        if name.startswith('max_'):
            require(getattr(limits, name) <= getattr(payload.limits, name), ReasonCode.LIMIT_EXCEEDED)
    return replace(payload, limits=limits)


def detect(payload: BoundedPayload, limits: Limits):
    """M0 Detect: JSON fields are whole-field locations; binary needs a codec."""
    try:
        payload = _bounded(payload, limits)
        require(payload.kind is not PayloadKind.BINARY, ReasonCode.UNSUPPORTED_FORMAT)
        findings, seen = [], set()

        def scan(value, path=()):
            if type(value) is dict:
                for key in sorted(value):
                    # Never claim complete coverage while leaking sensitive keys.
                    require(not any(_matches(key)), ReasonCode.UNSUPPORTED_SCOPE)
                    scan(value[key], path + (key,))
            elif type(value) is list:
                for index, child in enumerate(value):
                    scan(child, path + (index,))
            elif type(value) in (str, int, float) and type(value) is not bool:
                text = value if type(value) is str else str(value)
                for category, start, end in _matches(text):
                    loc = _location(LocationKind.JSON_FIELD, path=path) if path else _location(
                        LocationKind.TEXT_SPAN, start=start, end=end)
                    hit = Finding(schema_version=Finding.SCHEMA, category=category, level=LEVELS[category],
                        rule_version=RULE_VERSION, location=loc, reason=ReasonCode.MATCHED_FORMAT)
                    if hit not in seen:
                        require(len(findings) < limits.max_findings, ReasonCode.LIMIT_EXCEEDED)
                        findings.append(hit)
                        seen.add(hit)
        scan(payload.text if payload.kind is PayloadKind.TEXT else payload.tree.to_value())
        return tuple(sorted(findings, key=lambda f: (canonical_bytes(f.location), -PRIORITY[f.category])))
    except ContractViolation as exc:
        return ProtectionError(schema_version=ProtectionError.SCHEMA, code=exc.code,
                               retryable=False, trace_id='core/detect')


def detect_table(snapshot, limits):
    """Only an already bounded snapshot; this is not a CSV/XLSX parser."""
    snapshot = _bounded(snapshot, limits)
    cov = snapshot.coverage
    require(cov.failed == cov.unknown == cov.unscanned == 0 and cov.processed == len(snapshot.cells),
            ReasonCode.SCOPE_INCOMPLETE)
    # Headers are not cell locations in v1: fail closed, never report them scanned.
    require(not any(any(_matches(c.label)) for c in snapshot.columns), ReasonCode.UNSUPPORTED_SCOPE)
    findings, seen = [], set()
    for cell in snapshot.cells:
        for category, start, end in _matches(cell.normalized_text):
            if cell.mapping_proven:
                loc = _location(LocationKind.CELL_SPAN, cell=cell,
                    start=cell.source_spans[start][0], end=cell.source_spans[end - 1][1])
            else:
                loc = _location(LocationKind.CELL, cell=cell)
            hit = Finding(schema_version=Finding.SCHEMA, category=category, level=LEVELS[category],
                rule_version=RULE_VERSION, location=loc, reason=ReasonCode.MATCHED_FORMAT)
            if hit not in seen:
                require(len(findings) < limits.max_findings, ReasonCode.LIMIT_EXCEEDED)
                findings.append(hit)
                seen.add(hit)
    return tuple(findings)


def fixed_replace(value, replacement):
    """Literal replacement shared with the retained column-v1 execution facade."""
    return replacement


def transform(value, spec, category, *, material=None, environment=None, domain=None, scope=None):
    """A single approved action. Truncate is deliberately not a primary action."""
    spec.validate_category(category)
    require(type(value) is str, ReasonCode.INVALID_TYPE)
    action = spec.algorithm
    if action is Algorithm.DROP:
        return ''
    if action is Algorithm.REPLACE:
        return fixed_replace(value, spec.replacement.value)
    if action is Algorithm.MASK:
        # Even short inputs must not be returned unchanged by keep counts.
        prefix = min(spec.keep_prefix, max(0, len(value) - 1))
        suffix = min(spec.keep_suffix, max(0, len(value) - prefix - 1))
        return value[:prefix] + spec.mask_symbol * max(1, len(value) - prefix - suffix) + (value[-suffix:] if suffix else '')
    if action is Algorithm.GENERALIZE:
        try:
            return str(ipaddress.IPv4Network((value, spec.ipv4_prefix), strict=False))
        except ipaddress.AddressValueError:
            raise ContractViolation(ReasonCode.INVALID_VALUE) from None
    require(material is not None and len(material) == 2, ReasonCode.KEY_UNAVAILABLE)
    key, root = material
    require(key.key_ref == spec.key_ref, ReasonCode.KEY_UNAVAILABLE)
    digest = scoped_hmac(value.encode('utf-8'), root, key, environment=environment, domain=domain, scope=scope)
    if action is Algorithm.HMAC:
        return digest.hex()
    return base64.urlsafe_b64encode(digest[:spec.pseudonym_bits // 8]).decode('ascii').rstrip('=')


def _rank(action):
    strength = {Algorithm.DROP: 6, Algorithm.REPLACE: 5, Algorithm.HMAC: 4,
                Algorithm.PSEUDONYM: 3, Algorithm.GENERALIZE: 2, Algorithm.MASK: 1}
    spec = action.algorithm
    retained = (spec.keep_prefix or 0) + (spec.keep_suffix or 0)
    return PRIORITY[action.category], strength[spec.algorithm], -retained, canonical_bytes(spec)


def _merged(actions):
    """Union overlapping source spans; choose strongest category then action."""
    ordered = sorted(actions, key=lambda a: (a.location.start, a.location.end, a.action_id))
    groups = []
    for action in ordered:
        start, end = action.location.start, action.location.end
        if not groups or start >= groups[-1][1]:
            groups.append([start, end, action])
        else:
            group = groups[-1]
            group[1] = max(group[1], end)
            old = group[2]
            if _rank(action) > _rank(old):
                group[2] = action
    return groups


def apply_actions(payload, actions, limits, *, materials=(), environment=None, domain=None, scope=None,
                  truncate=None):
    """Apply to the original snapshot, then optional length control. No delivery."""
    payload = _bounded(payload, limits)
    require(type(actions) is tuple and len(actions) <= limits.max_actions, ReasonCode.LIMIT_EXCEEDED)
    require(all(type(a) is ResolvedAction for a in actions), ReasonCode.INVALID_TYPE)
    require(len({a.action_id for a in actions}) == len(actions), ReasonCode.INVALID_VALUE)
    if truncate is not None:
        require(truncate.algorithm is Algorithm.TRUNCATE, ReasonCode.INVALID_VALUE)
    key_material = {key.key_ref: (key, root) for key, root in materials}
    require(len(key_material) == len(materials), ReasonCode.INVALID_VALUE)

    def apply(value, selected):
        # Whole-cell/field actions cannot preserve a guessed normalized fragment.
        whole = [a for a in selected if a.location.start is None]
        if whole:
            require(len(whole) == len(selected), ReasonCode.INVALID_COORDINATE)
            winner = max(whole, key=_rank)
            return bound_text(convert(value, winner), (winner,))
        for action in selected:
            require(action.location.end <= len(value), ReasonCode.INVALID_COORDINATE)
        parts, cursor = [], 0
        for start, end, action in _merged(selected):
            parts.extend((value[cursor:start], convert(value[start:end], action)))
            cursor = end
        parts.append(value[cursor:])
        return bound_text(''.join(parts), selected)

    def convert(value, action):
        return transform(value, action.algorithm, action.category,
            material=key_material.get(action.algorithm.key_ref), environment=environment, domain=domain, scope=scope)

    def bound_text(value, selected=()):
        if truncate is not None and len(value) > truncate.max_length:
            # v1 refuses shortened containers holding stable tokens rather than
            # guessing whether a truncation boundary splits their encoding.
            require(not any(a.algorithm.algorithm in (Algorithm.HMAC, Algorithm.PSEUDONYM)
                            for a in selected), ReasonCode.LIMIT_EXCEEDED)
            return value[:truncate.max_length]
        return value

    if type(payload) is TableSnapshot:
        column_keys = {(c.sheet_id, c.column_id) for c in payload.columns}
        cell_index = {(c.sheet_id, c.column_id, c.source_row): c for c in payload.cells}
        by_cell = {}
        for action in actions:
            loc = action.location
            require((loc.sheet_id, loc.column_id) in column_keys, ReasonCode.INVALID_COORDINATE)
            if loc.kind is LocationKind.COLUMN:
                require(action.algorithm.algorithm is Algorithm.DROP, ReasonCode.INVALID_COORDINATE)
                continue
            require(loc.kind in (LocationKind.CELL, LocationKind.CELL_SPAN), ReasonCode.INVALID_COORDINATE)
            key = (loc.sheet_id, loc.column_id, loc.source_row)
            require(key in cell_index, ReasonCode.INVALID_COORDINATE)
            cell = cell_index[key]
            if loc.kind is LocationKind.CELL:
                require(action.algorithm.algorithm in (Algorithm.DROP, Algorithm.REPLACE), ReasonCode.INVALID_COORDINATE)
            else:
                require(cell.mapping_proven and loc.end <= len(cell.original_text), ReasonCode.INVALID_COORDINATE)
            by_cell.setdefault(key, []).append(action)
        dropped = {(a.location.sheet_id, a.location.column_id) for a in actions
                   if a.location.kind is LocationKind.COLUMN}
        require(not any((a.location.sheet_id, a.location.column_id) in dropped and
                        a.location.kind is not LocationKind.COLUMN for a in actions), ReasonCode.INVALID_COORDINATE)
        columns = tuple(c for c in payload.columns if (c.sheet_id, c.column_id) not in dropped)
        require(all(any(c.sheet_id == sheet for c in columns) for sheet in payload.sheet_ids), ReasonCode.UNSUPPORTED_SCOPE)
        cells = []
        for cell in payload.cells:
            if (cell.sheet_id, cell.column_id) in dropped:
                continue
            chosen = by_cell.get((cell.sheet_id, cell.column_id, cell.source_row), ())
            text = apply(cell.original_text, chosen)
            cells.append(replace(cell, original_text=text, normalized_text=text, mapping_proven=True,
                                 source_spans=tuple((i, i + 1) for i in range(len(text)))))
        coverage = replace(payload.coverage, total=len(cells), eligible=len(cells), processed=len(cells), excluded=0)
        return replace(payload, columns=columns, cells=tuple(cells), coverage=coverage)
    require(payload.kind is not PayloadKind.BINARY, ReasonCode.UNSUPPORTED_FORMAT)
    if payload.kind is PayloadKind.TEXT:
        require(all(a.location.kind is LocationKind.TEXT_SPAN for a in actions), ReasonCode.INVALID_COORDINATE)
        return replace(payload, text=apply(payload.text, actions))
    root = payload.tree.to_value()
    groups = {}
    for action in actions:
        loc = action.location
        require(loc.kind in (LocationKind.JSON_FIELD, LocationKind.TEXT_SPAN), ReasonCode.INVALID_COORDINATE)
        groups.setdefault(loc.json_path, []).append(action)
    visited = set()
    dropped_value = object()

    def walk(value, path=()):
        selected = groups.get(path, ())
        if selected:
            visited.add(path)
            require(type(value) in (str, int, float), ReasonCode.INVALID_COORDINATE)
            whole = [a for a in selected if a.location.kind is LocationKind.JSON_FIELD]
            require(not whole or len(whole) == len(selected), ReasonCode.INVALID_COORDINATE)
            if whole and max(whole, key=_rank).algorithm.algorithm is Algorithm.DROP:
                return dropped_value
            value = apply(str(value), selected)
        if type(value) is dict:
            result = {}
            for key, child in value.items():
                protected = walk(child, path + (key,))
                if protected is not dropped_value:
                    result[key] = protected
            return result
        if type(value) is list:
            return [v for i, child in enumerate(value) if (v := walk(child, path + (i,))) is not dropped_value]
        return bound_text(value) if type(value) is str else value
    result = walk(root)
    require(visited == set(groups), ReasonCode.INVALID_COORDINATE)
    return replace(payload, tree=FrozenJSON(None if result is dropped_value else result))


def _legacy_complete_values(text, pattern, replacement, *, legal=False):
    parts, cursor = [], 0
    while (match := pattern.search(text, cursor)) is not None:
        end = match.end()
        value = match.group().split('=', 1)[-1].split(':', 1)[-1].lstrip()
        # An auth scheme/cookie or quoted value has no reliable whitespace
        # boundary here. Conservatively remove the remainder of that line.
        rest_of_line = (legal and match.group(1).lower() in ('authorization', 'cookie')) or value[:1] in ('"', "'")
        while end < len(text) and text[end] not in '\r\n' and (rest_of_line or not text[end].isspace()):
            end += 1
        label = match.group(1) + '=[REDACTED]' if legal else replacement
        parts.extend((text[cursor:match.start()], label))
        cursor = end
    parts.append(text[cursor:])
    return ''.join(parts)


def legacy_confidentiality(text, profile, *, secret_patterns, token_pattern, internal_patterns):
    """Complete matched values using explicitly supplied legacy business patterns."""
    require(type(text) is str and len(text) <= 65536, ReasonCode.LIMIT_EXCEEDED)
    require(profile in ('output-v1', 'legal-v1'), ReasonCode.UNKNOWN_SCHEMA)
    if profile == 'legal-v1':
        return _legacy_complete_values(text, token_pattern, None, legal=True), ()
    warnings = []
    for pattern, name in secret_patterns:
        if pattern.search(text):
            if name == '私钥文件':
                # The old header-only substitution left the body behind. Once a
                # known header matches, remove the complete block (or remainder).
                while (match := pattern.search(text)) is not None:
                    end_marker = '-----END ' + (match.group(1) or '') + 'PRIVATE KEY-----'
                    end = text.find(end_marker, match.end())
                    end = len(text) if end < 0 else end + len(end_marker)
                    text = text[:match.start()] + '[' + name + ' 已过滤]' + text[end:]
            else:
                text = _legacy_complete_values(text, pattern, '[' + name + ' 已过滤]')
            warnings.append('检测到真实' + name + '，已过滤')
    # Preserve the older output-only range/substrings behavior, including its
    # punctuation handling. This is not the validated M1 IPv4 candidate rule.
    for pattern, name in internal_patterns:
        if pattern.search(text):
            text = pattern.sub('[内网地址 已过滤]', text)
            warnings.append('检测到' + name + '，已过滤')
    return text, tuple(warnings)
