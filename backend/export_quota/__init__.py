"""export_quota — 外发配额预占参考实现（主线二）.

Separate app so the quota authority can be handed to the controlled-export
subline later by moving a directory, not by a cross-app table surgery
(see docs/mainline2-plan-and-contracts.md decision 1). This is a **reference
implementation / non-production authority** until a real quota owner is wired.
"""
