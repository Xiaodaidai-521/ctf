# 主线二 M0–M5 审查修复记录（F1–F13）

> 对应审查报告 `mainline2-handoff-review.md`（审查对象提交 `b978b8d7`）。本文件记录对其 6 项 P1 +
> 7 项 P2 的逐条修复、补测与复核证据。修复**只在 `export_risk` / `export_quota` 两个新 app 内**
> （空库、无业务数据），未改 audit/legal/users 的公共语义。

> 本文描述第一轮 F1–F13 修复，但 `mainline2-remediation-review.md` 随后确认 F1/F2/F3/F7/F13
> 仍有 5 项边界遗漏，不能仅据原 22 条通过关闭全部发现。已按该复核完成第二轮修复，最新证据见
> `mainline2-boundary-remediation.md`：原 22/22 + 新边界 12/12；正式两 app Ran 117（116 通过、1 跳过），
> 六 app Ran 232（223 通过、9 跳过）。真实 PG 并发及已披露功能缺口仍未关闭。

## 0. 复核命令（第一轮历史命令与结果）

```bash
# 1) 审查方自己的隔离反例脚本（未改动）——原 20 失败，现 0 失败
PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python docs/review-support/mainline2_handoff_probes.py
# 期望：{"tests": 22, "failures": 0, "errors": 0, "passed": 22}

# 2) 两 app 单测（含 24 条新「反例转正式」用例）
cd backend && PYTHONUTF8=1 DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  python manage.py test export_risk export_quota
# 期望：Ran 90 tests ... OK (skipped=1)   # skip=PG 并发

# 3) 六 app 合跑回归
cd backend && PYTHONUTF8=1 DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  python manage.py test legal_kb rag_ingestion agent_runtime ai_assistant export_risk export_quota
# 期望：Ran 205 tests ... OK (skipped=9)，System check 零问题
```

## 1. 验证结果（本机实测，上一轮记录）

> 本文保留上一轮修复的历史结果；第二轮边界复核与最新统计见
> `docs/mainline2-boundary-remediation.md`。上一轮数字不可用于本轮验收。

| 验证 | 结果 | 证明范围 |
|---|---|---|
| 审查方隔离反例脚本（原样） | 22/22 通过、0 失败（原 20 失败） | 当时脚本的原始反例不再复现，不证明全部边界关闭 |
| `export_risk`+`export_quota` 单测 | Ran 90、89 通过、1 跳过 | 既有 66 + 新增 24 条安全反例用例 |
| 六 app 合跑回归 | Ran 205、196 通过、9 跳过 | 其余四 RAG app 无回归 |
| `makemigrations --check` | No changes detected | 手写迁移 `0003` 与模型一致、无漂移 |
| 真实 PG 并发 | 仍未运行（环境所限） | 不据 SQLite 宣称行锁并发正确性（不变） |

> 「Ran 90 / 205」含跳过项，不表述为全部实际通过。PG 并发 `QuotaConcurrencyTests`
> （`@skipUnless(postgresql)`）仍为 **Blocked**，独立于本轮全部修复，复核办法见审查报告 §修复顺序 5。

## 2. 逐条修复（发现 → 修复 → 代码 → 测试）

每行：审查发现 → 修复要点 → 代码位置 → 证明用例。所有「测试」列既含审查方脚本中的同名反例，也含
`backend/export_risk/tests/test_review_safeguards.py` / `backend/export_quota/tests.py::QuotaSafeguardTests` 的正式用例。

| # | 发现（P） | 修复要点 | 代码 | 测试 |
|---|---|---|---|---|
| F1 | P1 执行准备不复核当前权限、幂等重放跳过审批复核 | `prepare_execution` 重构：首次与重放都先过「活授权复核 + 审批复核」再返回；授权快照的 result/主体/时效全部参与 | `decisions/service.py::prepare_execution`（step4/5）、`_authorization_blocker`、`_recheck_record` | `test_prepare_rechecks_forbidden_authorization`、`test_replay_rechecks_revoked_approval` |
| F2 | P1 纯核心接受他主体 / 已过期授权 | 硬约束加主体绑定（主体不符→deny）；新增 `validity.py` 用注入 `evaluation_time` 做带时区校验（过期/空白时效→defer，不默认长期有效） | `judgment/hard_constraints.py`、`judgment/validity.py`、`judgment/core.py`（step2.5） | `test_core_rejects_other_subject_authorization`、`test_core_rejects_expired_authorization`、`test_core_blank_validity_is_not_valid_forever` |
| F3 | P1 claim 只看 state，过期/决定失效/预占释放后仍可领取；consumed 重放仍报可执行 | `claim` 加到期、父决定状态、预占活性复核；`_recheck_record` 把非 valid 记录（含 consumed/claiming）一律判不可执行 | `decisions/service.py::claim`、`_recheck_record` | `test_claim_rejects_expiration`、`test_claim_rejects_invalidated_decision`、`test_claim_rejects_released_reservation`、`test_consumed_authorization_not_reported_executable` |
| F4 | P1 生产准入不查审批权威与决定来源 | 生产路径校验 `approval.is_production_authority`；决定持久化 `source_mode`/`environment`，生产签发拒绝非生产来源决定 | `decisions/service.py`（step3、`_approval_blocker`）、`models.py::RiskDecision`、迁移 `0003` | `test_production_rejects_test_approval_provider`、`test_production_rejects_synthetic_decision` |
| F5 | P1 评估可错绑到另一请求 | `create_risk_decision` 先校验 assessment 与 request 的 id+指纹一致，否则抛 `AssessmentBindingError` | `decisions/service.py::create_risk_decision` | `test_create_rejects_assessment_for_other_request` |
| F6 | P1 配额幂等重放不校验绑定、返回错误 bucket | 命中 reservation_id 时比对 bucket/fingerprint/amount/state，不符抛 `QuotaConflict`，返回真实桶 | `export_quota/services.py::reserve` | `QuotaSafeguardTests::test_replay_rejects_changed_binding` |
| F7 | P2 unknown 预占无法结清 | `reconcile` 支持 `unknown`→（收到回执）结算，重复 unknown 幂等 | `export_quota/services.py::reconcile` | `::test_unknown_can_be_reconciled_after_receipt`、`::test_repeated_unknown_result_is_idempotent` |
| F8 | P2 允许负预占、静默截断超额交付 | reserve 拒负数；commit/reconcile 用 `_validated_delivery`，超额抛 `QuotaConflict` 不再截断 | `export_quota/services.py` | `::test_rejects_negative_amount`、`::test_over_delivery_is_not_silently_clamped` |
| F9 | P2 历史特征读到未来才收到的事件 | 计算与两个 Provider 均按 `received_at < as_of` 双时间截止 | `features/compute.py`、`adapters/behavior.py` | `test_late_received_event_excluded_from_historical_inputs` |
| F10 | P2 请求次数混入生命周期事件 | 行为特征仅计 `event_type=='export_request'` | `features/compute.py` | `test_request_count_does_not_count_lifecycle_events` |
| F11 | P2 模拟事件污染真实特征 | 行为计算默认排除 `is_simulated`（与交付计算对齐） | `features/compute.py` | `test_simulated_behavior_excluded_by_default` |
| F12 | P2 零本人历史时群体基线不可用 | 群体样本足量即可用；「本人历史不足」改由独立 `cold_start` 标记表达 | `baselines/baseline.py::build_baseline`、`BaselineBundle.cold_start` | `test_complete_cohort_baseline_usable_for_zero_history_user` |
| F13 | P2 核心把陈旧/缺失特征重标为 OK | 融合路径 `input_quality` 透传 `feature_snapshot.quality`，不再硬置 OK | `judgment/core.py` | `test_core_preserves_stale_feature_quality` |

正向控制（审查补做、本轮保留并转入正式集）：`test_outbox_failure_rolls_back_and_retries_once`、
`test_core_performs_zero_database_queries`。

## 3. 纯度护栏的改动（主动披露）

F2 需在纯判断层做带时区的时效比较，故 `judgment` 的 AST 纯度扫描（`tests/test_purity_ast.py`）
放行 `datetime` 导入，同时把时钟访问 `now`/`utcnow`/`today` 全部列入 `BANNED_ATTRS`——即「可做纯值
解析/比较、但不得读时钟」。`judgment/validity.py` 仅用 `datetime.fromisoformat` 解析注入的时间串，
不触时钟；`judgment` 仍零 Django 导入。

## 4. 据审查收窄的能力声明（非反例，单列）

以下为交付范围/措辞收紧，已同步到 `mainline2-plan-and-contracts.md` 的 M5 行与进度段：

1. **M5 实为 4 类场景**（normal_bulk/continuous_batch/unapproved_recipient/new_account），非方案曾写的「10 类」。
2. **回放是单臂判断回放**，每步 deliveries 传空、动作不更新额度/交付状态——不是 I5 的执行状态闭环模拟。
3. **D 臂暂无业务（purpose/business_task）判定分支**；D-v1 现为累计+异常+敏感性叠加。
4. **决策仅持久化版本串**，未落完整 assessment/特征/授权快照与原因证据链；`policy_hash`/`registry_fingerprint`
   函数存在不等于决策已内容哈希绑定（当前主要在测试中调用）。
5. **生命周期事件/领取凭证未完整**：invalidate/revoke 未发失效事件；`claim` 仍返回 bool、`consume` 未用执行结果引用。

以上第 2–5 项属**后续里程碑范围**（审查亦将其与 13 项反例分列），本轮不实现，仅如实收窄声明。
原已准确披露的限制（真实来源未接入、C 臂无训练模型、PG 并发未验证、审计链边界）维持不变。

