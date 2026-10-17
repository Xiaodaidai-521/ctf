"""Run one fully synthetic backend-only scan without a database or external service.

From backend/: ``python -B -m mainline1.operations_smoke``.
This is an API-shape demonstration, not a durable or production adapter.
"""
from dataclasses import asdict
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

from .classification import BusinessContext, load_baseline
from .operations import Operations
from .parsing import AssetRef, ParserConfig, fingerprint, parse_table
from .review import MemoryReviewRepository, ReviewPrincipal


class SyntheticAccess:
    def allowed(self, principal, asset, operation):
        return principal.domain_id == "synthetic-demo" and principal.environment == "test"


class SyntheticAssets:
    def __init__(self):
        self.rows = {}

    def add(self, content):
        version_id = str(uuid4())
        asset_id = str(uuid4())
        ref = AssetRef(version_id, "synthetic-demo", "sha256:" + sha256(content).hexdigest(),
                       "csv", len(content), "private:synthetic-demo")
        self.rows[version_id] = (asset_id, ref, content)
        return asset_id, ref

    def resolve(self, principal, version_id, operation):
        asset_id, ref, _ = self.rows[version_id]
        return asset_id, ref

    def open_version(self, ref, *, principal, domain_id):
        for _, candidate, content in self.rows.values():
            if candidate == ref and domain_id == "synthetic-demo":
                return BytesIO(content)
        raise KeyError("SYNTHETIC_ASSET_NOT_FOUND")


def main():
    content = b"contact\nsynthetic-person@example.invalid\n"
    assets = SyntheticAssets()
    asset_id, ref = assets.add(content)
    actor = ReviewPrincipal(7, "synthetic-demo", "test")
    parser = ParserConfig()
    parsed = parse_table(content, ref, config=parser)
    meta = dict(schema_version="mainline1.proposed.v1", trace_id=str(uuid4()),
                environment="test", evaluation_run_id=None, domain_id=actor.domain_id,
                created_at="2026-10-15T00:00:00Z")
    context = BusinessContext.create(meta=meta, context_id=str(uuid4()), version=1,
        asset_version_id=ref.version_id, scope_hash=fingerprint(asdict(parsed.scope)),
        source="user_input", scenario="synthetic smoke sample")
    operations = Operations(MemoryReviewRepository(), SyntheticAccess(), assets)
    queued = operations.create_scan(actor, ref.version_id, configuration=load_baseline(),
        context=context, idempotency_key="synthetic-operations-smoke", scope=parsed.scope,
        config=parser, semantic_required=False)
    finished = operations.execute_one(actor, queued["scan_id"])
    findings = operations.list_findings(actor, finished["profile_id"], pending_only=False,
                                        offset=0, limit=100)
    # Report only synthetic workflow status and a count; never print finding text.
    print({"asset_id": asset_id, "status": finished["status"],
           "profile_created": bool(finished["profile_id"]),
           "finding_count": len(findings["items"]),
           "next_offset": findings["next_offset"]})


if __name__ == "__main__":
    main()
