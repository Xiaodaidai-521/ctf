"""export_risk — 数据敏感度与行为联合研判主线.

M0 scope: pure-Python contracts (`contracts/`) and the deterministic judgment
core (`judgment/`). This package intentionally has **no Django import** so the
judgment core stays decoupled from persistence, settings and the request cycle.

Nothing here is wired into INSTALLED_APPS yet; M0 is zero-migration. The Django
model / decision / quota layers arrive in later milestones (M1+).
"""
