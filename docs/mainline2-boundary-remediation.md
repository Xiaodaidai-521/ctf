# 主线二第二轮边界修复记录（R1–R5）

日期：2026-10-11。对应 `mainline2-remediation-review.md`，对象为 `feature/mainline2-export-risk` 上未提交的修复。

## 1. 结论与验证口径

本轮先原样运行新增反例脚本，实测 **12 条中 11 失败、1 正向控制通过、0 错误**；五项报告均与代码相符。
修复后原审查 **22/22**、新增边界审查 **12/12** 均通过。正式测试新增 **27 条**，不是只改到外部脚本通过。
这些结果证明本次检查覆盖的反例不再成立，**不代表 M0–M5 全部安全契约通过验收**。

| 验证 | 最新实测 | 覆盖范围 |
|---|---|---|
| 原审查脚本（未修改） | 22 通过，0 失败/错误 | 保留原 F1–F13 反例及两项正向控制 |
| 第二轮边界脚本（未修改） | 12 通过，0 失败/错误 | 本轮 R1–R5 的顺序反例及有效领取控制 |
| 两 app 正式测试 | Ran 117，**116 通过、1 跳过** | 上轮 90 + 本轮 27；跳过为真实 PG 配额并发 |
| 六 app 组合回归 | Ran 232，**223 通过、9 跳过** | legal_kb/rag_ingestion/agent_runtime/ai_assistant/export_risk/export_quota |
| Django check + 迁移漂移检查 | 零问题；No changes detected | 显式 SQLite `:memory:` 配置，没有默认库一致性检查警告 |
| diff / 编码 | `diff --check` 通过；23 个新增/改动源码及文档通过 UTF-8、LF、无 BOM、Python AST 检查 | 不新增 schema 变更 |
| 真实 PostgreSQL 竞争 | **未运行** | 不据 SQLite 宣称并发闭环 |

六 app 日志仍出现既有 fallback 与 SQLite table locked 告警，退出码为 0、测试成功；未将告警掩去。
本轮未修改外部审查报告、两个反例脚本或其历史结果，未操作真实业务库，未提交或推送。

新原始结果分别保存为：
- `review-support/mainline2-boundary-fix-original-results.json`
- `review-support/mainline2-boundary-fix-followup-results.json`

新结果包含对应脚本的 SHA-256、退出码与真实 runner 输出统计，旧结果仍保留。

## 2. 逐项处理

### R1 [P1] 当前权限名单收紧后仍签发

- `decisions/service.py::_authorization_blocker` 首次与重放共用，复用纯 `evaluate_hard_constraints` 检查主体、范围、操作、接收者；不再以请求指纹代替当前权限校验。
- 保留来源准入与审批复核；补请求/授权快照/决定与调用执行环境一致性检查。
- 共用 `authorization_validity`，同时检查已观察时间、有效期及绝对时间可解析性。
- 修正正常测试 fixture 的允许名单，保留原断言而非取消权限检查。

证据：`test_review_safeguards.py::ExecutionRecheckTests`（首次三类名单收紧 + 接收者重放）；
`test_remediation_boundaries.py::PermissionBoundaryTests`（三类重放及准确原因码、环境/未来观察时间）。

### R2 [P1] 执行许可越过前置期限，重放遗漏预占状态

- `ReservationResult` 增加 `expires_at`。首次执行授权持久化与返回
  `min(决定有效期, 当前上游授权有效期, 预占有效期)`；无配额时不虚构预占期限。
- 返回契约读取执行授权记录的期限，而不是父决定期限。
- `QuotaService.require_active` 在**桶→预占**锁内检查存在、指纹绑定、状态、期限；`reserve` 的同键重放也验证期限。
- `prepare_execution` 重放与 `claim` 共用 `_recheck_record`，读取关联预占；即使重放不再传 quota 参数，也不会绕过既有预占检查。
- 重放只允许缩短已有许可，不会延长或复活旧许可；期限上界为半开 `now < expiry`，等号已失效。
- 决策端锁顺序统一为**决定→执行授权→配额桶→预占**，领取与重放按相同方向读取；锁等待后重新读取当前时间。
- 到期/未知预占只阻止执行，不自动释放账面占用。

证据：`test_remediation_boundaries.py::ExecutionDeadlineTests`（上游 grant、预占期限、契约/记录一致、
期限等号、已释放/未知/过期预占、旧许可不得延长、有效单次领取）；
`export_quota/tests.py::QuotaSafeguardTests::test_expired_reservation_replay_is_not_active`。
另有测试故意把许可记录期限设得晚于预占，隔离验证预占检查本身，而不只依赖最小期限挡住反例。

**边界**：上述检查针对已有数据库参考配额服务，不等于任意外部 owner 的事务协议已打通；
锁持有仅覆盖本地服务事务，不覆盖之后的真实交付。领取/撤销/释放竞争与跨服务边界仍须真实 PG/生产 owner 验证。

### R3 [P2] 全 naive 时间仍被当成有效授权

- 纯 `judgment/validity.py::parse_aware_timestamp` 显式要求有效 UTC offset；空白、格式错误、全 naive 均返回未知。
- `evaluation_time`、`observed_at`、`valid_until` 三者都必须建立绝对时间；观察时间晚于评价时间或与有效期构成无效窗口，不能确认为有效。
- UTC `Z` 和其他有效 offset 可以比较同一个绝对瞬间；不依赖 naive/aware 比较抛异常才拒绝。
- 生产准备复用该纯解析与校验；判断核心不读时钟/数据库，原 AST 纯度护栏不削弱。

证据：`CoreAuthorizationBindingTests::test_core_naive_validity_is_not_absolute_time`；
`test_remediation_boundaries.py::PureInputBoundaryTests`（格式、offset、空观察时间、到期等号）；零查询控制保持通过。

### R4 [P2] 已确认结清的回执重试抛错

- `reconcile` 在桶/预占锁内识别 committed：相同确认值返回成功，**不重复记账**；不同确认值抛 `QuotaConflict`，不可覆盖已有结算证据。
- 后来的 unknown 消息不能把 committed 回退为 unknown。
- 保持未知占用和超额交付保守处理，不扩建回执 ID 或真实执行闭环。

证据：`QuotaSafeguardTests::test_confirmed_reconcile_retry_is_idempotent`、
`::test_different_confirmed_reconcile_retry_conflicts`、`::test_unknown_retry_cannot_reopen_settled_reservation`。

### R5 [P2] 整份特征缺失被标为 OK

- 依赖累计/异常输入的 B/C/D 政策，当 `feature_snapshot=None` 时返回 **MISSING + defer**，并给出 `degrade.features_missing`。
- 不依赖行为特征的 policy-m0/A-v1 仍可按授权/单次数量判断，不强制所有策略拒绝 None。
- 已存在的 STALE 质量标记继续透传；这不表示个别特征缺失、全部输入时效已实现完整的生产降级政策。

证据：`PositiveControlTests` 的 B 缺失与基线对照；
`PureInputBoundaryTests::test_missing_snapshot_depends_on_policy_requirements`（B/C/D 与 A/基线政策，零查询）。

## 3. 复现命令

从仓库根目录运行原始审查保护：

```bash
PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python docs/review-support/mainline2_handoff_probes.py
```

运行第二轮边界保护：

```bash
PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python docs/review-support/mainline2_remediation_probes.py
```

正式两 app 测试（默认基础库也设为内存，测试 runner 使用独立测试库）：

```bash
PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH=:memory: DEBUG=true SECRET_KEY=dev-test-key python backend/manage.py test export_risk export_quota
```

六 app 回归：

```bash
PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH=:memory: DEBUG=true SECRET_KEY=dev-test-key python backend/manage.py test legal_kb rag_ingestion agent_runtime ai_assistant export_risk export_quota
```

## 4. 未关闭的范围

真实 PostgreSQL 并发仍未验证；完整快照证据链、实际交付/配额执行闭环、D 臂业务分支、完整生命周期事件/
领取凭证及原有生产 owner 接入仍未实现。本次未扩建这些已披露范围，不以顺序用例通过替代整体安全验收。
