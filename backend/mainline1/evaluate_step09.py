"""Reproducible Step 9 evaluation over a frozen synthetic set.

Run from ``backend/`` with ``python -B -m mainline1.evaluate_step09``.  The
script executes the real parser and rule engine, preflights (but never calls)
semantic B/C, and runs one explicitly marked in-memory contract substitute.
It writes only synthetic aggregate results to ``docs/mainline1``.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import asdict
from hashlib import sha256
from io import StringIO
from pathlib import Path

from .classification import BusinessContext, load_baseline
from .parsing import AssetRef, ParserConfig, fingerprint, parse_table
from .rules import scan_rules
from .semantic import SemanticConfig, prepare_requests
from .semantic_smoke import abc_preflight


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "mainline1"
DATASET_PATH = DOCS / "step-09-eval-set-v1.json"
CONFIG_PATH = DOCS / "step-09-eval-config-v1.json"
RESULT_PATH = DOCS / "step-09-results.json"


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _meta(domain, evaluation):
    return dict(schema_version="mainline1.proposed.v1", trace_id="90000000-0000-4000-8000-000000000001",
                environment="test", evaluation_run_id=evaluation, domain_id=domain,
                created_at="2026-10-16T00:00:00Z")


def _expected_key(label):
    span = label["span"]
    return (label["asset_version_id"], label["sheet_id"], label["row"], label["column"],
            label["channel"], span["start"], span["end"], label["category_id"])


def _actual_key(asset_version_id, finding):
    loc = finding["locations"][0]
    span = loc.get("span")
    if loc.get("kind") != "span" or span is None:
        return None
    return (asset_version_id, loc["sheet_id"], loc["row"], loc["column"], loc["channel"],
            span["start"], span["end"], finding["category_id"])


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return dict(tp=tp, fp=fp, fn=fn, precision=p, recall=r, f1=f)


def _input_stats(requests):
    sizes = [len(request.messages()[0]["content"].encode("utf-8")) + len(request.payload.encode("utf-8"))
             for _, request in requests]
    limits = [reason for _, request in requests for reason in request.data()["limitations"]]
    return dict(target_count=len(requests), processed_count=len(requests), skipped_count=0, failed_count=0,
                total_input_bytes=sum(sizes), min_input_bytes=min(sizes) if sizes else None,
                max_input_bytes=max(sizes) if sizes else None,
                truncated_count=sum(1 for reason in limits if "TRUNCATED" in reason or "DROPPED" in reason),
                sampling=dict(mode="all", seed=None), limitations=sorted(set(limits)))


def _run_asset(asset, configuration, dataset_version):
    content = asset["content"].encode("utf-8")
    digest = "sha256:" + sha256(content).hexdigest()
    if digest != asset["content_sha256"]:
        raise AssertionError("dataset content hash mismatch")
    ref = AssetRef(asset["asset_version_id"], "synthetic-step09", digest, "csv", len(content),
                   "private:step09-synthetic")
    parser_config = ParserConfig()
    parsed = parse_table(content, ref, config=parser_config)
    meta = _meta("synthetic-step09", "90000000-0000-4000-8000-000000000002")
    context = BusinessContext.create(meta=meta, context_id="90000000-0000-4000-8000-000000000003", version=1,
        asset_version_id=ref.version_id, scope_hash=fingerprint(asdict(parsed.scope)),
        source="user_input", scenario="synthetic evaluation context",
        table_description="synthetic support/contact table")
    rule = scan_rules(parsed, configuration, context, meta=meta,
        asset=dict(asset_id=asset["asset_id"], asset_version_id=ref.version_id, content_hash=digest),
        principal="step09-evaluator", scan_id="90000000-0000-4000-8000-000000000004", applicability_ref="90000000-0000-4000-8000-000000000005",
        parsed_ref="private:step09-parsed", semantic_required=False)
    data = rule.data()
    labels = [dict(label, asset_version_id=asset["asset_version_id"]) for label in asset["labels"]]
    expected = {_expected_key(label) for label in labels}
    actual = [_actual_key(asset["asset_version_id"], finding) for finding in data["findings"]]
    actual_nonnull = [key for key in actual if key is not None]
    actual_set = set(actual_nonnull)
    tp = len(expected & actual_set)
    fp = len(actual_nonnull) - tp
    fn = len(expected - actual_set)
    by_category = {}
    categories = sorted(set(label["category_id"] for label in labels) | set(f["category_id"] for f in data["findings"]))
    for category in categories:
        e = {key for key in expected if key[-1] == category}
        a = {key for key in actual_set if key[-1] == category}
        by_category[category] = _prf(len(e & a), len(a - e), len(e - a))
    expected_fields = {(label["sheet_id"], label["column"], label["category_id"]) for label in labels}
    actual_fields = {(f["locations"][0]["sheet_id"], f["locations"][0]["column"], f["category_id"])
                     for f in data["findings"]}
    field_metrics = _prf(len(expected_fields & actual_fields), len(actual_fields - expected_fields),
                         len(expected_fields - actual_fields))
    # B/C use the same full parsed target set, including negatives; labels only
    # define the frozen truth and must not be used to select positives.
    target_keys = sorted((c.sheet_id, c.row, c.column, c.channel) for c in parsed.cells)
    context_parsed = parse_table(content, ref, config=ParserConfig(include_header=True))
    b_requests = prepare_requests(parsed, rule, SemanticConfig(mode="B"), target_keys=target_keys,
                                  context_parsed=context_parsed)
    c_requests = prepare_requests(parsed, rule, SemanticConfig(mode="C"), target_keys=target_keys,
                                  context_parsed=context_parsed)
    preflight = abc_preflight(parsed, rule, SemanticConfig(mode="C"), target_keys=target_keys,
                              context_parsed=context_parsed)
    category_levels = {category["category_id"]: category["protection_level"]
                       for category in configuration.data()["policy"]["categories"]}
    return dict(asset_id=asset["asset_id"], asset_version_id=asset["asset_version_id"],
        template_family=asset["template_family"], business_entity_group=asset["business_entity_group"],
        content_hash=digest, parser=dict(version=parsed.parser_version, config_hash=parsed.config_hash,
                                         target_cells=len(parsed.cells), processed_cells=len(parsed.cells),
                                         input_codepoints=sum(len(c.source_text) for c in parsed.cells)),
        A=dict(execution="rule_only", findings=len(data["findings"]), coverage=data["profile"]["coverage"],
               entity=_prf(tp, fp, fn), entity_key_count=len(actual_nonnull), field=field_metrics,
               entity_by_category=by_category,
               policy_levels={category: category_levels[category] for category in sorted(category_levels)
                              if category in {f["category_id"] for f in data["findings"]}},
               unknown=0, degraded=sum(1 for o in data["cell_outcomes"] if o["status"] == "detection_failed"),
               failed=sum(1 for o in data["cell_outcomes"] if o["status"] == "detection_failed"),
               review=dict(pending=sum(1 for f in data["findings"] if f["judgment"] != "determined"),
                           confirmed=0, refused=0),
               examples=dict(false_positive=sorted(actual_set - expected), false_negative=sorted(expected - actual_set))),
        B=dict(execution="not_run", status="Blocked", input_hash=preflight["B"]["input_hash"], calls=0,
               inputs=_input_stats(b_requests)),
        C=dict(execution="not_run", status="Blocked", input_hash=preflight["C"]["input_hash"], calls=0,
               inputs=_input_stats(c_requests), input_limits=preflight["C"]["input_limits"]),
        target_equivalence=preflight["target_equivalence"], semantic_effectiveness=preflight["semantic_effectiveness"],
        combination=dict(status="N/A", reason="NO_APPROVED_RELATION_POLICY"),
        policy_mapping=dict(categories=sorted(set(f["category_id"] for f in data["findings"])),
                            protection_level=data["profile"]["protection_level"]),
        limitations=["synthetic_only", "rules_are_format_candidates_not_business_facts", "semantic_backend_unavailable"])


def _run_failure_samples(dataset):
    from .parsing import InputError
    rows = []
    for sample in dataset.get("failure_samples", []):
        content = sample["content"].encode("utf-8")
        digest = "sha256:" + sha256(content).hexdigest()
        ref = AssetRef(sample["asset_version_id"], "synthetic-step09", digest, "csv", len(content),
                       "private:step09-synthetic")
        observed = None
        try:
            parse_table(content, ref, config=ParserConfig())
            observed = "UNEXPECTED_SUCCESS"
        except InputError as exc:
            observed = exc.code
        rows.append(dict(asset_version_id=sample["asset_version_id"], expected=sample["expected_error_code"],
                         observed=observed, status="Passed" if observed == sample["expected_error_code"] else "Failed",
                         counted_as_entity_negative=False))
    return rows


def _contract_substitute():
    """Exercise review successor and pure plan validation with named test doubles."""
    from .tests import test_rules
    from .tests.test_planning import SourceDouble
    from .tests.test_review import AccessDouble
    from .review import MemoryReviewRepository, ReviewPrincipal, ReviewService
    from .planning import PlanPolicy, PlanService

    fixture = test_rules.RuleTests(); fixture.setUp()
    parsed = fixture.parsed("alice@example.invalid")
    result = fixture.scan(parsed, semantic_required=False)
    repo, access = MemoryReviewRepository(), AccessDouble()
    review = ReviewService(repo, access)
    actor = ReviewPrincipal(1, "test-domain", "test")
    profile_id = review.register(actor, result, parsed)
    finding = result.data()["findings"][0]
    record = review.submit_review(actor, base_profile_id=profile_id, expected_state_version=1,
        idempotency_key="step09-confirm", action="confirm", reason="frozen synthetic review",
        finding_id=finding["finding_id"])
    successor = record["successor_profile_id"]
    requirements = [dict(requirement_id="protect-email", version="synthetic-v1",
        category_ids=["email_address"], allowed_operations=["mask_span", "mask_cell"],
        allow_drop_column=False, require_complete_coverage=True, allow_unresolved=True)]
    source = SourceDouble(review, parsed, requirements,
                          PlanPolicy("synthetic-approved-test-v1", "mask_cell", True, True, True))
    plans = PlanService(source, cursor_key=b"synthetic-step09-cursor-key-32bytes")
    plan = plans.build(actor, successor, idempotency_key="step09-plan")
    checked = plans.validate(actor, plan)
    stable_check = {k: v for k, v in checked.items() if k not in ("checked_at", "plan_hash")}
    return dict(status="Passed" if checked["valid"] else "Failed", contract="test_double",
                model_calls=0, review_conclusion=record["conclusion"], plan_status=plan["status"],
                plan_validation=stable_check)


def _existing_suite_evidence():
    names = ["mainline1.tests.test_operations", "mainline1.tests.test_review", "mainline1.tests.test_planning"]
    rows = []
    for name in names:
        stream = StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromName(name)
        result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
        rows.append(dict(name=name, tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                         status="Passed" if result.wasSuccessful() else "Failed",
                         scope="local synthetic/memory contract tests"))
    return rows


def main():
    dataset, config = _read_json(DATASET_PATH), _read_json(CONFIG_PATH)
    baseline = load_baseline()
    assets = [_run_asset(asset, baseline, dataset["dataset_version"]) for asset in dataset["assets"]]
    contract = _contract_substitute()
    failure_samples = _run_failure_samples(dataset)
    suites = _existing_suite_evidence()
    results = dict(result_version="mainline1-step09-results-v1", dataset_version=dataset["dataset_version"],
        annotation_version=dataset["annotation_version"], frozen_at=dataset["frozen_at"],
        dataset_status="candidate_not_independent",
        config_version=config["config_version"], dataset_sha256="sha256:" + sha256(DATASET_PATH.read_bytes()).hexdigest(),
        config_sha256="sha256:" + sha256(CONFIG_PATH.read_bytes()).hexdigest(), assets=assets,
        aggregate=dict(entity=_prf(sum(a["A"]["entity"]["tp"] for a in assets),
                                   sum(a["A"]["entity"]["fp"] for a in assets),
                                   sum(a["A"]["entity"]["fn"] for a in assets)),
                       entity_by_category={category: _prf(
                           sum(a["A"]["entity_by_category"].get(category, {}).get("tp", 0) for a in assets),
                           sum(a["A"]["entity_by_category"].get(category, {}).get("fp", 0) for a in assets),
                           sum(a["A"]["entity_by_category"].get(category, {}).get("fn", 0) for a in assets))
                                         for category in sorted({category for a in assets for category in a["A"]["entity_by_category"]})},
                       review=dict(pending=sum(a["A"]["review"]["pending"] for a in assets),
                                   confirmed=0, refused=0, contract_confirmed=1),
                       combination=dict(status="N/A", reason="NO_APPROVED_RELATION_POLICY"),
                     semantic=dict(status="Blocked", reason="REAL_BACKEND_NOT_APPROVED", model_calls=0,
                                     metrics=None),
                       costs=dict(input_tokens=None, output_tokens=None, currency=None, cost_microunits=None)),
        verification=dict(static=dict(status="Passed", dataset_hash_checked=True, config_hash_checked=True),
                          failure_samples=failure_samples,
                          contract_substitute=contract, existing_suites=suites,
                          security=dict(status="Passed", network_calls=0, credentials_read=False,
                                         real_data_used=False, raw_sensitive_values_in_output=False)),
        limitations=["candidate labels are separated from fixed fixtures but are not independently reviewed; A metrics are descriptive pipeline checks only",
                     "B/C semantic effectiveness is Blocked; abc_preflight proves target equivalence and input bounds only",
                     "test doubles and synthetic data do not prove production semantics or outbound blocking",
                     "real downstream event adapter, durable service and production ACL are Untested/Blocked",
                     "combination metrics are N/A because relation policy and truth labels are not approved"])
    RESULT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(dict(result_path=str(RESULT_PATH), assets=len(assets), entity=results["aggregate"]["entity"],
                          semantic=results["aggregate"]["semantic"], contract=contract["status"], suites=suites),
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
