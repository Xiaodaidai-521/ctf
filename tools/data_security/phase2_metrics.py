"""Synthetic, in-memory measurements; never serialize fixture payloads."""
from dataclasses import replace
import json

from data_security.contracts import (Category, Outlet, Purpose, ProtectedResult, ProtectionError,
    TeachingException, content_hash, canonical_bytes)
from data_security.application.protection import ProtectionService
from data_security.core.redaction import detect, RULE_VERSION
from data_security.tests.phase2_fixtures import (AT, BASELINE_LIMITS, Environment, MemoryPolicy,
    MemoryAudit, approval, context, examples, policy, text)
from data_security.tests.synthetic import dataset_fingerprint, samples


def ratio(numerator, denominator, reason=None):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None,
            'null_reason': reason if not denominator else None}


def measure():
    dataset = samples()
    rows, issues = [], []
    for outlet in Outlet:
        ctx = replace(context(), outlet=outlet)
        snapshot, binding = policy(ctx)
        versions = {binding.protection_hash}
        audit = MemoryAudit()
        def service(snap, field='content/body'):
            return ProtectionService(policies=MemoryPolicy(snap), audit=audit, clock=lambda: AT,
                random_bytes=lambda n: bytes(n), environment=Environment.TEST, limits=BASELINE_LIMITS, field_ref=field)
        protector = service(snapshot)
        processed = excluded = failed = leaked = 0
        for category in (Category.EMAIL, Category.IPV4, Category.CARD):
            positive = negative = correct = false_positive = family_leaks = 0
            for sample in dataset:
                if sample.category is not category or sample.teaching is not None:
                    continue
                findings = detect(text(sample.text), BASELINE_LIMITS)
                result = protector.protect(text(sample.text), ctx, binding)
                if isinstance(findings, ProtectionError) or not isinstance(result, ProtectedResult):
                    failed += 1
                    issues.append(sample.sample_id + ':' + outlet.value + ':failed')
                    continue
                processed += result.coverage.processed
                positive += sample.positive
                negative += not sample.positive
                correct += sample.positive and any(f.category is category for f in findings)
                false_positive += not sample.positive and result.payload.text != sample.text
                surfaces = result.payload.text + canonical_bytes(audit.events[-1]).decode('utf-8')
                for finding in findings:
                    loc = finding.location
                    family_leaks += sample.text[loc.start:loc.end] in surfaces
            leaked += family_leaks
            rows.append({'outlet': outlet.value, 'category': category.value, 'measurement_scope': 'M4 synthetic port only',
                'recall': ratio(correct, 50), 'false_positive': ratio(false_positive, 50),
                'positive_returned': positive, 'negative_returned': negative, 'forbidden_original_exposures': family_leaks})
            if (correct, false_positive, family_leaks) != (50, 0, 0):
                issues.append(outlet.value + ':' + category.value + ':metric')
        teaching_changed = teaching_retained = teaching_protected = 0
        for sample in dataset:
            if sample.teaching is None:
                continue
            source_hash = content_hash({'fixture_source': sample.source_ref, 'version': sample.source_version})
            teaching_ctx = replace(ctx, purpose=Purpose.TEACHING, scope_refs=('content/endpoint',),
                source_ref=sample.source_ref, source_version=sample.source_version, source_hash=source_hash)
            values = examples()[TeachingException].content()
            values.update(source_ref=sample.source_ref, source_version=sample.source_version, source_hash=source_hash,
                          outlet=outlet, field_refs=('content/endpoint',))
            approved = TeachingException(**values, approval=approval(content_hash(values)))
            # A self-asserted upload is never placed in the approved catalog.
            snap, bound = policy(teaching_ctx, exceptions=(approved,) if sample.expected_exception else ())
            versions.add(bound.protection_hash)
            result = service(snap, 'content/endpoint').protect(text(sample.text), teaching_ctx, bound)
            if not isinstance(result, ProtectedResult):
                failed += 1
                issues.append(sample.sample_id + ':' + outlet.value + ':failed')
                continue
            processed += result.coverage.processed
            excluded += result.coverage.excluded
            if sample.expected_exception:
                teaching_changed += result.payload.text != sample.text
                teaching_retained += result.payload.text == sample.text
            else:
                findings = detect(text(sample.text), BASELINE_LIMITS)
                surfaces = result.payload.text + canonical_bytes(audit.events[-1]).decode('utf-8')
                hits = sum(sample.text[f.location.start:f.location.end] in surfaces for f in findings)
                leaked += hits
                teaching_protected += hits == 0 and result.payload.text != sample.text
        rows.append({'outlet': outlet.value, 'category': 'teaching-source',
            'approved_teaching_damage': ratio(teaching_changed, 50), 'approved_retained': teaching_retained,
            'self_asserted_protected': ratio(teaching_protected, 50), 'forbidden_original_exposures': leaked,
            'coverage': {'unit': 'text', 'total': 400, 'eligible': 350, 'processed': processed,
                         'excluded': excluded, 'failed': failed, 'unknown': 0, 'unscanned': 0},
            'processing_ratio': ratio(processed, 350), 'policy_hashes': sorted(versions)})
        if (teaching_changed, teaching_retained, teaching_protected, leaked, processed, excluded, failed) != (0, 50, 50, 0, 350, 50, 0):
            issues.append(outlet.value + ':teaching-or-coverage')
        rows.append({'outlet': outlet.value, 'category': Category.SECRET.value,
            'recall': ratio(None, None, 'automatic fourth category explicitly excluded by PHASE2-BRIEF'),
            'dataset_rows_retained': 100, 'not_applicable': 100, 'automatic_detector_added': False})
    return {'version': 'ds.metrics.v1', 'dataset_version': 'synthetic-2026-11-04.v1',
        'dataset_count': 500, 'dataset_sha256': dataset_fingerprint(), 'rule_version': RULE_VERSION,
        'measurements': rows, 'real_outlets': [{'outlet': outlet.value, 'enabled_accepted': 0,
            'enabled_coverage': ratio(0, None, 'production denominator not verified; no real outlet integration'),
            'recall': None, 'leakage': None, 'unknown': True} for outlet in Outlet],
        'payloads_persisted': False, 'issues': issues}


def main():
    result = measure()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result['issues']))


if __name__ == '__main__':
    raise SystemExit(main())
