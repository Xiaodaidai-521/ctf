# 主线二 M0–M5 审核交接（供外部智能体审查）

> 目的：让审查方**不信任我的结论**也能独立核验。每条能力都给出代码位置 + 对应测试 +
> 复现命令；并主动列出**未验证项**与**应重点质疑处**。遵循证据纪律：不夸大、不缩小。

## 0. 基本事实

- 仓库：`E:\xianmu\ctf`（后端 Django 6.0.3 + DRF，Python 3.12）。
- 分支：`feature/mainline2-export-risk`（从 `main`=`185f66da` 切出）。**纯本地,未推送。**
- 提交：`b978b8d7`，作者 `xiaodd <2296509004@qq.com>`（复用仓库既有身份,未改 git config），
  62 文件 / +4920 行。co-author 署名 Claude。
- 改动面：新增 `backend/export_risk/`、`backend/export_quota/` 两个 app；`settings.py`
  仅新增两行 `INSTALLED_APPS`（diff 可核：只有 `+ 'export_risk'`、`+ 'export_quota'`）。
- 方案与审查背景：`docs/mainline2-plan-and-contracts.md`（§15 为实现进度）、`docs/mainline2-review.md`。

## 1. 任务目标（审查应据此判对错）

同一份数据，在不同主体/接收者/用途/操作范围/历史行为下，产生**有依据的不同处理结果**，
并输出下游可实施、可审计、可回放的决策；**不**做实际脱敏、文件输出与交付（那属支线一）。

动作集：`allow / mask / require_approval / deny / defer`。三层：输入准备 → 纯判断核心 →
生产决策。判断核心必须是纯函数（不读时钟/DB/配额、不写状态、不签发授权）。

## 2. 复现（请审查方亲自跑）

```bash
cd backend
PYTHONUTF8=1 DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  python manage.py test export_risk export_quota
```

预期：`Ran 66 tests ... OK (skipped=1)`。回归（含 RAG 基线四 app，确认未破坏既有）：

```bash
cd backend
PYTHONUTF8=1 DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  python manage.py test legal_kb rag_ingestion agent_runtime ai_assistant export_risk export_quota
```

预期：`Ran 181 tests ... OK (skipped=9)`，`System check identified no issues`。

> 环境注意：本机 shell 为 Git Bash，控制台代码页 GBK，故命令前置 `PYTHONUTF8=1`。
> 需 `pip install pgvector langchain-text-splitters`（requirements.txt 已列，本机原先缺）。

## 3. 文件地图（审查导航）

**`export_risk/contracts/`**（frozen dataclass，零 Django，可独立 import）
- `enums.py` 动作/处置/授权结果/来源模式/风险等级/质量状态（封闭枚举）
- `freezing.py` `deep_freeze` 递归冻结（dict→MappingProxyType, list→tuple, set→frozenset）
- `snapshots.py` 输入快照：ExportRequestSnapshot / AuthorizationSnapshot / SensitivityProfileRef / FeatureSnapshot / BehaviorBaseline
- `assessment.py` 输出 ExportRiskAssessment（与 `legal.risk_evaluator.RiskAssessment` 刻意区分）+ Obligation
- `execution.py` NotExecutable / ExecutionAuthorization
- `reason_codes.py` 原因码常量表

**`export_risk/judgment/`**（纯函数核心，受 AST 纯度扫描约束）
- `consistency.py` 请求⇄画像⇄环境一致性
- `hard_constraints.py` 硬约束（越权→deny，仅产 deny，从不 allow）
- `anomaly.py` 异常信号选择（注入模型分 or 偏离聚合；模型缺失显式报告）
- `fusion.py` 融合层（基础保护下限 + 四臂 A/B/C/D）
- `explanation.py` 三段式解释（观察/模型描述/政策驱动）
- `core.py` `assess_risk(...)` 编排：一致性→硬约束→降级→融合

**`export_risk/features/`** `registry.py`(11 元数据声明式注册表+指纹) · `compute.py`(纯窗口计算)
**`export_risk/baselines/`** `statistics.py`(鲁棒分位) · `baseline.py`(本人/群体+冷启动回退+回放截断)
**`export_risk/policies/`** `catalog.py`(版本化四臂政策,hash 寻址,封闭谓词,无 eval)
**`export_risk/adapters/`** `behavior.py`(Provider 协议 + 合成 + Django 实现)
**`export_risk/decisions/`** `service.py`(create_risk_decision/prepare_execution/claim/consume/revoke) ·
`admission.py`(R3 准入) · `approval.py`(内存审批适配器,非生产) · `serde.py`(序列化+摘要) · `outbox.py`(事务 outbox→审计台账)
**`export_risk/models.py`** BehaviorEvent / ExportRequestLog / DeliveryRecord / RiskDecision / IdempotencyRecord / ExecutionAuthorizationRecord / EventOutbox
**`export_risk/experiments/`** `scenarios.py` · `replay.py`(带状态回放) · `metrics.py` · `comparison.py`(四臂+预注册假设)
**`export_quota/`** `models.py`(QuotaBucket/QuotaReservation) · `services.py`(reserve/commit/release/reconcile,桶行锁)

## 4. 声明 → 证据映射（逐条可核）

每行：声明 → 代码位置 → 证明它的测试（`文件::方法`）。审查方可只跑单测核验。

| 声明 | 代码 | 测试 |
|---|---|---|
| 明确越权直接 deny，不经模型 | `judgment/hard_constraints.py` | `test_hard_constraints.py::test_recipient_not_allowed_denies` / `::test_scope_exceeded_denies` / `::test_forbidden_result_denies` |
| 未知授权不默认放行（defer） | `judgment/core.py` step3 | `test_hard_constraints.py::test_unknown_authorization_defers` |
| 画像不完整→require_approval（不等于不敏感） | `core.py` step4 | `test_hard_constraints.py::test_incomplete_profile_requires_approval` |
| 资产版本/环境不一致→defer（不融合） | `judgment/consistency.py` | `::test_asset_version_mismatch_defers` / `::test_environment_mismatch_defers` |
| 判断核心纯（无时钟/DB/settings/ORM/未播种随机） | `judgment/*` | `test_purity_ast.py::test_judgment_modules_are_pure`（扫描器自带「有牙」反例校验 `::test_scanner_finds_at_least_the_core`） |
| 递归不可变，构造后改原容器不泄漏（R7） | `contracts/freezing.py` | `test_contracts_immutability.py`（4 项，含嵌套 mapping 只读） |
| 特征 11 元数据完整 + 内容指纹 + 当前请求不计入历史 | `features/registry.py` | `test_feature_registry.py`（5 项） |
| 窗口半开 `[start,as_of)` / 缺失非零 / 水位标陈旧 | `features/compute.py` | `test_feature_compute.py`（5 项） |
| 行为事件 event_id 去重 + Django Provider + 水位=max(received_at) | `models.py`,`adapters/behavior.py` | `test_models_ingestion.py`（3 项） |
| 无历史不伪造正常 / 回放不读未来 / 退化 IQR 返回 None | `baselines/baseline.py`,`statistics.py` | `test_baselines.py`（含 `::test_no_history_is_not_normal` / `::test_replay_excludes_future_samples`） |
| 基础保护下限对四臂一律适用（R4，不可消融） | `policies/catalog.py::base_protection_obligations`,`judgment/fusion.py` | `test_fusion.py::test_base_protection_applied_in_every_arm` |
| 四臂融合；异常模型缺失显式暴露，不静默清零（I6） | `judgment/fusion.py`,`anomaly.py` | `test_fusion.py::test_arm_*` / `::test_arm_c_model_unavailable_is_surfaced_not_silent` |
| 决策不可覆盖 + 幂等（同键同请求同决策；同键异请求冲突） | `decisions/service.py::create_risk_decision` | `test_decisions.py::DecisionPersistenceTests` |
| 准入拒绝生产路径里的合成输入（R3） | `decisions/admission.py` | `test_decisions.py::test_admission_rejects_synthetic_in_production` |
| allow/approval/deny/quota/未支持义务 各自门控 | `decisions/service.py::prepare_execution` | `test_decisions.py::PrepareExecutionTests`（5 项） |
| 幂等重放仍复核当前态（撤销后不可执行，R1）+ 单次领取 + outbox→台账链校验且重放幂等 | `decisions/service.py`,`outbox.py` | `test_decisions.py::StateMachineAndOutboxTests`（4 项） |
| 配额锁共同桶行；三类计量；reconcile 未知结果不释放（R2） | `export_quota/services.py` | `export_quota/tests.py::QuotaAccountingTests`（5 项） |
| 实验 harness 可跑；H1（累计臂 B 早于单阈值臂 A 限制）；硬 deny 全臂一致；冷启动不误拦；分母完整 | `experiments/*` | `test_experiments.py`（5 项） |

## 5. 未验证 / Blocked（如实披露，勿当已验证）

- **PG 并发额度**：`export_quota/tests.py::QuotaConcurrencyTests`（并发 60+60 争 100，仅一个成功）
  已写好并 `@skipUnless(connection.vendor=='postgresql')`。**未在真实 PostgreSQL 上运行**：
  本机 Docker 守护未启动；pgserver 可引导但其最简捆绑在本中文 Windows 拒绝 `TimeZone=UTC`。
  故配额行锁并发正确性目前 = **设计保证（锁共同桶行）+ SQLite 逻辑测试**，并发层 **Blocked**。
  复核办法：启动 Docker 用 `pgvector/pgvector:pg16` 建库后去掉 skip 跑该测试。
- **纯度是工程护栏，非证明**：AST 扫描 + 解耦 import 能抓常见违规，不能证明无一切副作用
  （别名调用、间接 I/O 等）。`assertNumQueries(0)` 尚未加（判断核心当前零 Django import，
  入 DB 查询无从发生，但未来接 provider 时需补）。
- **合成数据只证机制**：所有实验在合成场景上跑，标签主要验证**政策符合性**，不等于识别未知
  恶意，也不等于生产效果。真实画像源/授权源/行为流/配额·审批生产 owner 为 OQ-1~4，未接入。
- **决策模型版本仅传字符串**：`assess_risk` 收 `model_version`/`policy_version` 字符串，政策由
  `policies.catalog` 的纯数据按版本解析（确定、非 latest）；真实模型工件钉版/预处理绑定未做（R7 后续）。

## 6. 请审查方重点质疑处（我主动标注的薄弱点）

1. **四臂里 C 臂没有「学习模型」**：首期零新依赖、未装 sklearn，C 臂异常信号退化为「鲁棒
   偏离聚合」（`anomaly.py`）。因此 **B↔C 对照当前无法支持「模型学习带来增益」的结论**——
   C 不是训练模型。请核查我是否在任何地方把它冒充为模型效果（不应有）。
2. **预注册假设 H1/H2 是机制演示，非统计结论**：H1（B 早于 A 限制）在 `continuous_batch` 上
   成立是因为场景被设计成「单次小、累计大」，使机制可见；H2（normal_bulk 上 D 误拦不劣于 C）
   在合成数据上两者皆 0，**平凡成立**。请核查 `comparison.py` 未把它们表述成有功效的统计不劣。
3. **回放里的偏离注入是否循环论证**：`replay.py` 用场景自带 `baseline_observations` 建基线、
   对 `req_count_long` 算偏离并注入 `dev::`。请核查这不是「用将要触发的量反推异常」的循环。
4. **单次领取/撤销复核的并发真伪**：`claim`/`consume` 的单赢家依赖 `select_for_update`，
   **仅 PG 真生效**；committed 测试只验证**顺序**单领取，未验证并发。与 §5 第一条同源。
5. **outbox 崩溃安全只论证未注入**：`relay_pending` 把「领取行+写台账+标记已发」放同一事务，
   论证了崩溃不产生半态；但没有真的注入「写台账后标记前崩溃」的测试，只测了重放幂等。
6. **审计台账的完整性边界**：复用 `audit.AuditLedgerService` 做链校验，但该设施本身
   `created_at` 未入哈希、无锚定链尾（见 review R6）——我只上链决策级事件、未重构 audit，
   请确认我没有把「链校验通过」说成「事件历史完整/防删除」。
7. **SensitivityProfileRef 等输入契约是我方猜测**：主线一正式契约未到（OQ-1），字段形状是
   占位。请把它当 draft，不要据此认为已与主线一对接。
8. **义务「支持类型」白名单极小**：`SUPPORTED_OBLIGATION_TYPES={'mask','approval'}`，其余
   义务一律挡在授权之外（安全侧保守）。请核查这是否过严到影响正常 allow 路径。

## 7. 设计决策与偏离（相对原方案）

- app 由 `export_guard` 改名 `export_risk`（guard 暗示执行拦截，属支线一）；拆 `export_quota`
  独立 app 以便配额权威日后移交。
- 首期零新生产依赖；sklearn 不入 `requirements.txt`（故 C 臂无训练模型，见 §6.1）。
- quota 建 DB 参考实现（需行锁）；approval 仅内存适配器（查询无需并发原子性）；两者标非生产权威。
- `settings.py` 的 `INSTALLED_APPS` +2 行属生产配置，先前方案标「待批准」，本轮用户授权「全部做完」
  后执行；审查方若认为该授权不足，可回退这两行 + 删两 app 即完全还原（空库，无业务数据）。

## 8. 非目标（本主线刻意不做，审查勿按缺失计）

文件解析与敏感定位算法、实际脱敏/文件输出/交付、共享令牌与接收者认证、完整审计中心与评估
平台、自动发布生产政策、改动其他任务线（audit/legal/users）的公共语义。

## 9. 审查建议顺序

先 §2 复现跑绿 → §4 抽查几条声明的单测 → §5/§6 逐条质疑（这是最可能发现问题处）→
§7 判断偏离是否可接受。发现问题请落到「声明 vs 证据」的具体行,便于定位修正。



