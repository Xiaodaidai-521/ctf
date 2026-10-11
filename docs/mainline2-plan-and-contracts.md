# 主线二：数据敏感度与行为联合研判 — 方案与契约（Stage 2）

> 本文件是「数据敏感度与行为联合研判」主线的 Stage 2 交付：源码核查结论、架构、
> 里程碑、公共契约草案、验证计划、实验预注册与 Stage 1 结构化 HANDOFF。
>
> **文件性质**：方案文档。**不含业务代码、未新建 app、未改 `settings.py`、未建迁移。**
> 任何实现动作需另行 gate。与 `agent-rag-*` 系列并列，互不覆盖。
>
> 约束遵循任务规格 Facet A–Q（证据纪律 K、变更政策 L、安全 M、验证 N、停止规则 O）。

---

## 0. TL;DR

同一份数据，在不同主体、接收者、业务用途、操作范围与历史行为下，产生**有依据的
不同处理结果**，并输出下游可实施、可审计、可回放的决策——而不是「显示一个风险分数」。

- 落点：新建 `backend/export_risk/`（研判与决策）+ `backend/export_quota/`（配额参考实现）。
- 首期零新生产依赖；异常检测后端懒加载，缺库报 `Blocked` 不静默跳过。
- 判断核心是纯函数，纯度由 `assertNumQueries(0)` + AST 扫描**机器校验**。
- 四组对照 A/B/C/D 共用同一政策引擎，仅融合层版本不同，差异可归因。
- quota 建 DB 参考实现 + 真实行锁并发测试；approval 仅内存测试适配器。
- 全程区分：设计目标 / 已实现能力 / 已验证效果 / 尚未证明的研究假设。

---

## 1. 环境约束（实测，影响测试与并发验证）

| 项 | 实测值 | 影响 |
|---|---|---|
| Shell | Git Bash (MINGW64) / bash 5.2 | 路径用 POSIX，`E:\` 反斜杠不可靠 |
| Python | 3.12.8，`D:\python\python.exe`；无 `python3`/`py` | 命令用 `python` |
| 控制台编码 | 活动代码页 936 / GBK，`stdout=gbk`，`utf8_mode=0` | 跑 Python 前置 `PYTHONUTF8=1`；`open()` 一律带 `encoding="utf-8"` |
| Node / Docker | v22.22 / Docker 29.5 + Compose v5.1 | 真实 PG 验证走 docker-compose 或 pgserver |
| 代码格式 | `.editorconfig`：UTF-8 无 BOM、LF、末尾换行、去行尾空白（`.md` 例外） | 写入固定遵守；全项目无 formatter/linter，就地匹配邻近风格 |

> **观测说明**：上表为 2026-10-11 在 Git Bash（本会话 harness shell）下的一次观测，非通用前提。
> 用户交互式 shell 可能为 PowerShell，环境变量设置等命令前缀会不同；跨 shell 执行以各自语法为准。

**关键并发约束**：Django `base/features.py` 默认 `has_select_for_update = False`，SQLite 的
features 未覆盖 → **`select_for_update()` 在 SQLite 上是空操作**。因此规格 N 节必测的
「并发争用额度」在 CLAUDE.md 默认 SQLite 测试路径上**无法验证，会假绿**。配额并发测试
必须照 `rag_ingestion/test_postgres_concurrency.py:28` 的 `@skipUnless(connection.vendor
== 'postgresql')` 走真实 PG。

---

## 2. Stage 1 源码核查结论（只读，带证据）

规格 D3 的复用线索目录在 `backend/` 下**全部存在**（`legal`、`learning_analytics`、
`users`、`audit`、`resources` 均在 `INSTALLED_APPS`，见 `ctf_backend/settings.py:63-90`），
说明规格确系针对本仓库。本主线=在此 CTF 平台内新增一条主线，复用现有合规/审计基础设施。

### 2.1 能力清单

| 能力 | 现状 | 证据 | 复用判定 |
|---|---|---|---|
| 现存记录哈希链一致性校验 | Implemented（**非完整防篡改**） | `audit/services.py` append_entry：串行追加 + 链校验。局限（实测，见 review R6）：`created_at` 未入哈希、`verify_chain` 无锚定链尾/条数 → 改时间戳、删链尾仍校验通过 | reuse（仅决策级上链，不重构 audit） |
| 通用审计事件 | Implemented | `audit/models.py` `AuditEvent.log`，已有 `data_processing`/`violation_record`/`risk_override` 类别 | reuse（只上链决策级） |
| 版本化不可变内容 + hash | Implemented | `legal` `LegalProtocolVersion.content_hash`、`LegalFactSnapshot`（`snapshot_hash`+`extraction_version`） | **adapt**（政策/快照范式） |
| 幂等键范式 | Implemented | `learning_analytics` `LearningAuditJob.idempotency_key`（unique） | adapt |
| 版本化统计快照范式 | Implemented | `DailyLearningStat`/`LearningEffectSnapshot` + `algorithm_version` + UniqueConstraint | adapt |
| 法律风险「评分」 | Implemented 但**不符** | `legal/services/risk_evaluator.py`：关键词打分；`RiskAssessment` dataclass **同名不同义** | **不复用其评分**；命名需区分 |
| 满足外发需求的联合权威授权源 | **Missing**（非「全无对象级隔离」） | `users.CTFUser` 仅 `role`；`permissions.py` 仅角色级。仓库**有**按属主过滤（`resources.views.ResourceMyListView.get_queryset`、`legal.views.UserConsentRecordViewSet.get_queryset`），但无对象×字段×接收者×外发的联合授权源 | **new** |
| 敏感画像 SensitivityProfile | Missing（本主线不负责算法） | 仅 `fact_redactor.py` token/flag 正则；无 `protection_level` 模型 | 依赖主线一；本主线建 Ref 契约 |
| 配额/预占 quota | **Missing** | grep 无外发配额实现 | **new**（`export_quota`） |
| 审批 approval | **Missing** | 无 | **new**（内存适配器） |
| 行为事件→安全计数 | Partial/不符 | `learning_analytics` 是学习行为，非外发安全计数语义 | adapt/new |
| 实际交付量遥测 | **Missing** | `resources` 仅 `download_count`（点击计数，非原子 `increment_download_count`） | **new**，禁止复用 |
| 异常模型（IF 等） | Missing | `requirements.txt` 无 sklearn | new，懒加载 |

### 2.2 D3 四条核查要点的落地结论

- **关键词评分 ≠ 结构化联合研判**：`risk_evaluator.RiskAssessment` 只有
  `severity/likelihood/impact/score/matched_keywords`，无快照引用、硬约束、义务、
  原因码、版本——与规格 H3 的 `RiskAssessment` 完全不同义。证据充分，判定 confirmed。
- **学习行为分数 ≠ 安全行为基线**：`learning_analytics` 建模的是学习活跃度，无外发/接收者语义。
- **普通事件写入 ≠ 可靠安全计数**：`AuditEvent` 无去重、无水位、无「当前请求是否计入」语义。
- **下载记录 ≠ 交付完成**：`resources.download_count` 是点击计数，印证 E5「不能用下载点击次数代替实际交付量」。

### 2.3 依赖关系

- **incoming**（调用本主线）：支线一受控外发（调 `prepare_execution`）、研判详情前端、支线三评估。
- **outgoing**（本主线依赖）：主线一敏感画像（`SensitivityProfileRef`）、`authorization_source`、`behavior_source`、`quota_owner`、`approval_owner`。
- **implicit**：时区/窗口口径、幂等语义、audit 台账单锁的全平台串行化、SQLite 无行锁。

---

## 3. 四项已批准决策（修订终版）

| # | 决策 | 要点 | 回滚 |
|---|---|---|---|
| 1 | **两个 app** | `export_risk`（研判+决策）+ `export_quota`（配额参考实现）。**不叫 `export_guard`**——guard 暗示执行拦截，而拦截/交付属支线一；本主线只研判与决策。拆 app 是为 D2「配额唯一权威」便于日后移交（挪目录 vs 跨 app 搬表）。 | 删两 app + 撤迁移 |
| 2 | **零新生产依赖** | 首期纯 Python/ORM 做统计基线（A/B 组）。异常后端（sklearn，BSD-3）**懒加载**、照 `pdfplumber` 惯例**不入 `requirements.txt`**，实验依赖另置 `requirements-experiments.txt`；缺库 C 组报 `Blocked` **不静默跳过**。 | 无（未改 requirements） |
| 3 | **quota/approval 区别对待** | 判据=是否需 DB 级原子性。quota：reserve/commit/release/reconcile 端口 + 内存适配器（单测）+ **DB 参考实现**（真实行锁并发测试，`@skipUnless(postgresql)`）。approval：仅查询端口 + **内存测试适配器**，不建表。两者显式标注**非生产权威源**。 | 删 `export_quota` |
| 4 | **gate 保留** | docs/M0 零迁移可回滚，但不自行启动，等用户指令。 | — |

> 决策一的连带影响：拆 app 后 `INSTALLED_APPS` 加两项，属规格 L「生产配置」。
> 仅新增、不改语义，且**推迟到 M1（首次需迁移时）才动 `settings.py`**；M0 不碰。

---

## 4. 三层架构

```
输入准备层                判断核心（纯函数）              生产决策层
prepare_risk_inputs  →   assess_risk(显式输入)      →   create_risk_decision
读请求/画像/权限/        仅据快照+模型+政策返回          持久化、复核时效/撤销/
行为/基线，构建           RiskAssessment。              审批/请求一致性，
固定输入快照。            不读时间/DB/配额，            经配额服务准备
                        不写状态、不签发授权。          ExecutionAuthorization。
```

处理顺序（E2）：请求⇄画像一致性 → **硬约束** → 行为特征与基线 → 异常程度 → 敏感度+
业务上下文融合 → 动作/义务/原因/证据。**明确越权直接 deny，不等模型**。

包布局：

```
export_risk/
  contracts/      # frozen dataclass：快照、RiskAssessment、RiskDecision、授权结果（无 Django 依赖）
  judgment/       # 纯函数核心：硬约束、异常、融合、动作映射、解释。受 AST 纯度扫描约束
  features/       # 声明式特征注册表 + 快照构建器
  baselines/      # 统计基线 + 冷启动回退
  policies/       # 版本化政策表（hash 寻址，封闭谓词集，无 eval）
  decisions/      # 决策持久化、幂等、事件 outbox（Django models 在此）
  adapters/       # SensitivityProfile/Authorization/Behavior Provider 协议 + 合成实现
  experiments/    # 场景脚本（版本化数据）、回放、四组对照。仅测试支撑
export_quota/     # QuotaReservation 模型 + reserve/commit/release/reconcile + 并发测试
```

---

## 5. 里程碑（按 P0 优先级重排）

规格 P 的 P0 是**越权放行**，而硬约束不需任何特征/基线/模型 → 把它提到零迁移阶段。

| 里程碑 | 内容 | schema | 可验证的规格要求 |
|---|---|---|---|
| **M0** | 契约 dataclass + 判断核心骨架 + 硬约束 + 请求⇄画像纯度校验 | **零迁移** | 场景四（未获准接收者）、不变量「越权不被低分抵消」、E2「越权不等模型」 |
| **M1** | 行为事件接入 + 三类计数三张表 + 特征注册表 | 迁移起点 | E4 特征元数据完整性、E5 三类计数分离、去重/水位/当前请求计入 |
| **M2** | 本人基线 + 群体基线 + 冷启动回退 + 版本管理 | +迁移 | E6 冷启动、场景五（新账号）、无历史不等于正常 |
| **M3** | 融合政策表 + 义务 + 原因码 + 结构化解释 | +政策数据 | 场景一/三、C2 三段式解释、动作映射 |
| **M4** | 决策持久化 + 幂等 + quota/approval 适配器 + 事件 outbox | +迁移 | H6 幂等、场景六（决策后变化）、审批后撤权、并发额度（PG） |
| **M5** | 场景脚本 + 带状态回放 + 四组对照 + 消融 | 无 | I2–I7 全部实验要求 |

每个里程碑产出结构化 HANDOFF（Facet J），独立可回滚。

---

## 6. 关键设计点（相对朴素实现的改进，均有规格依据）

### 6.1 判断核心纯度 = 机器校验

E1 要求核心不隐式读时间/DB/配额。约定会烂，改两道可执行检查：

1. `assertNumQueries(0)` 包住 `assess_risk(...)` 全路径（Level 2）。
2. AST 扫描测试遍历 `export_risk/judgment/`，断言不出现 `timezone.now`/`datetime.now`/
   `.objects`/`settings.`/未播种 `random`（Level 1 + Level 5）。

收益：E1 约束变成验证项；核心一纯，M5 回放只是循环，无需 mock 时间。

### 6.2 四组对照 = 同一引擎的四个政策版本

I4 警告「避免弱化对照组」。改为**一个政策引擎 + 四个版本化政策配置**，硬约束阶段四组
**共用同一段代码**（结构保证「所有组执行相同硬性权限」），差异只在融合层，可归因。

- A：单次数量阈值　B：多窗口累计规则　C：行为异常模型　D：敏感画像+行为+业务上下文
- 政策是版本化数据（hash 寻址，照 `LegalProtocolVersion.content_hash`）；谓词是**封闭集合**，无 `eval`、不执行任意表达式（规格 M）。
- 预注册比较假设见 §9；**不预设 D 最好，无提升照报**。

### 6.3 特征：声明式注册表

E4 对每特征强制 11 项元数据（名称版本、来源可信度、单位、窗口开闭区间、发生 vs 接收
时间、数据水位、去重方式、当前请求是否计入、缺失/迟到处理、方法/限制）。每个特征是一个
带全部元数据的声明对象，构建器遍历注册表。收益：元数据完整性可单测枚举校验；特征集
版本 hash 自动算出；**消融按 tag 选子集**，直接服务 I4。

### 6.4 三类计数：三张表、三条写入路径

E5 要求请求量/预占量/交付量分别定义维护：

- 请求量 → `ExportRequestLog`，**含被拒请求**（描述尝试行为）
- 预占量 → `QuotaReservation`（`export_quota`），带期限 + reserve/commit/release/reconcile 状态机
- 交付量 → `DeliveryRecord`，**只由执行层遥测写入**；执行层不属本主线 → 适配器带 `is_simulated` 字段

`is_simulated` 让 I6「只有模拟账本时标注为模拟值」成为**数据属性**，而非报告时靠人记得
加免责声明。绝不复用 `resources.download_count`（非原子、点击数非交付）。

### 6.5 台账复用：零改动 audit，只上链决策级事件

证据：`AuditLedgerEntry.event_category` 是自由 CharField（无 choices），`AuditEvent.category`
有固定 choices。故走 `AuditLedgerService.append_entry` 可**零修改** audit app（改枚举会违反
规格 L）。但 `append_entry` 用单例锁行串行化**全平台**台账 → 只有决策级事件
（`decision.issued`/`decision.invalidated`/`execution.authorized`）上链；研判记录进本主线自己的表。

### 6.6 幂等与失效复核的交互

H6 两条会打架：「同键同请求返回同一逻辑结果」vs「授权失效后不能靠旧幂等结果绕过复核」。
解法：`prepare_execution` 幂等记录存 `authorization_id` **而非最终裁决**；重放同键返回同一
id，但**重跑当前条件复核**，故可能从 executable 变 `NotExecutable`。同键不同
`request_fingerprint` → 冲突错误。事件用**事务性 outbox 表**（与业务状态同事务提交），
满足 H7 可靠事务边界，不引入消息中间件。

### 6.7 群体基线分组：不复用 CTFUser.role

E6 要「同岗位/同任务群体基线」，但 `CTFUser` 仅 `role`（student/teacher/admin）、`class_name`、
`team`——全是教学语义，不是外发岗位。把教学角色当安全岗位正是 D3 警告的偷换。
方案：合成数据自带独立 `position`/`business_function`，**不复用 `CTFUser.role`**；真实接入由
`authorization_source` 提供。故群体基线在拿到真实授权源前**只能在合成数据上验证**，如实标注，不冒充生产效果。

---

## 7. 公共契约草案（H 节，待正式 contract_spec 核对）

> 均为 frozen dataclass 草案，未落地。正式 `contract_spec` 到位后以其为准，不自建同名不同义对象。

**通用字段**：`schema_version`、`trace_id`（非授权依据）、`environment`、`evaluation_run_id`、
组织/数据域、不可变引用、带时区时间、原因码/错误码。身份与 `request_fingerprint` 由服务端构建。

**输入对象**：
- `ExportRequestSnapshot`：请求 ID/修订号/主体、资产版本/范围/范围摘要、操作/接收者/用途/业务任务、共享期限/下载许可、服务端 `request_fingerprint`。
- `AuthorizationSnapshot`：权威来源/快照 ID、主体/数据域/允许范围/操作、接收者/业务约束、政策版本/观察时间/有效期、`authorized|forbidden|unknown`、证据引用。
- `SensitivityProfileRef`：画像/资产版本/范围、分类/保护等级/组合敏感性、覆盖/状态/检测器/等级政策版本。
- `FeatureSnapshot`：快照/特征定义版本、`as_of_time`/数据水位/窗口、特征值+单位、缺失/完整性、来源+当前请求计入方式、基线引用。
- `BehaviorBaseline`：基线 ID/版本、主体/群体定义、训练窗口/样本数、方法/模型摘要、适用范围/质量状态。

**判断与决策**：
- `ExportRiskAssessment`（**定名**，与 `legal.risk_evaluator.RiskAssessment` 区分；后者是 dataclass 非模型，无 DB 冲突）：输入快照引用、硬约束结果、敏感性摘要、异常分量、风险分数+含义（适用时）、风险等级、`recommended_action`、`obligations`、`reason_codes`+`evidence_refs`、输入质量/不确定性、模型/政策/特征版本。
- 动作集：`allow | mask | require_approval | deny | defer`。
- 每项义务：`obligation_id`、`type`、`parameters`、适用范围、执行阶段、所需证据。
- `RiskDecision`：`decision_id`/`assessment_id`、请求/资产/画像/范围绑定、action/obligations、政策版本、`issued_at`/`valid_until`/`status`、被替代决策引用。**历史决策不可覆盖**，更正产生新关联记录。

**执行准备结果**：
- `NotExecutable`：`kind=not_executable`、`disposition∈{deny,require_approval,defer}`、`reason_codes`、`approval_request_id`（适用时）。
- `ExecutionAuthorization`：`kind=executable`、`authorization_id`/`execution_id`/`decision_id`、请求/资产/画像/范围绑定、`plan_id`/`plan_hash`（适用时）、`obligations`、`reservation_id`、`valid_until`。
- 审批通过仍需复核当前条件；普通客户端不能提交 `action=allow` 或任意研判对象取得授权。

**候选服务接口**（实现前核对调用方）：
```
prepare_risk_inputs(...) -> RiskInputBundle
assess_risk(request_snapshot, sensitivity_profile, authorization_snapshot,
            feature_snapshot, model_version, policy_version, evaluation_time) -> ExportRiskAssessment
create_risk_decision(export_request_id, actor_context, idempotency_key) -> RiskDecision
prepare_execution(export_request_id, decision_id, actor_context, idempotency_key)
            -> NotExecutable | ExecutionAuthorization
```

**事件**（核对公共事件目录后用）：`risk.assessed`、`risk.deferred`、`decision.issued`、
`decision.invalidated`、`approval.requested`、`execution.authorized`。事件是事实非授权凭证；
事件消费去重不替代授权幂等。

---

## 8. 五级验证计划（N 节）

| 级 | 覆盖 | 本主线重点用例 |
|---|---|---|
| L1 语法 | 导入、类型、迁移检查 | AST 纯度扫描（判断核心无副作用符号） |
| L2 行为 | 特征/基线/硬约束/融合/动作/幂等 | `assertNumQueries(0)` 包核心；三类计数不互相污染 |
| L3 契约 | 画像/授权/义务/错误/版本/事件兼容 | Provider 协议、`is_simulated` 透传、版本绑定可追溯 |
| L4 边界 | 空历史/极值/乱序/重复/晚到/并发/过期/撤销/部分失败/重试 | 迟到事件不重复计入、水位截断、同键重试 |
| L5 安全 | 越权/伪造输入/环境混用/动作注入/义务绕过/泄露/额度绕过 | 低分但越权→deny；客户端自授 allow 被拒；未支持义务不签发 |

**必测清单**（N 节逐条）：低分但越权、高异常但有效授权、冷启动、画像不足、请求变更、
审批后撤权、同键重试、同键不同内容、并发争用额度（**仅 PG 有效**）、预占后超时、
部分交付/未知结果、历史回放不读未来、评估不污染生产、未支持义务不签发。

缺口记为 Open Question，不以「看起来正确」替代证据。

---

## 9. 实验设计与预注册（I 节）

**两类数据分工**：CERT 内部威胁合成数据仅用于行为聚合/异常模型研究，**不替代**本平台的
敏感画像/接收者授权/审批/执行标注；本平台合成外发数据用于验证完整业务契约。**不得**把
任意敏感画像拼接到 CERT 记录再宣称获得真实联合研判标签。

**合成场景**（I2，覆盖规格全部要求）：正常批量、连续分批+范围扩大、高敏感字段组合、
未获准接收者、新账号正常操作、任务/审批到期、审批后撤权、并发额度竞争、画像不完整、
行为事件重复/晚到/缺失。标注区分：异常行为 / 违反政策 / 预期动作 / 需复核 / 信息不足。
若标签直接来自政策生成器 → 明确其主要验证**政策符合性**，不据此证明识别未知恶意。

**数据切分**（I3）：按用户/时间/业务实体/场景模板分组，防同模板改写跨训练测试；拟合/
预处理/阈值/调参只用训练或验证部分；测试集独立。记录数据/标注/生成器/场景版本。

**四组对照 + 消融**（I4）：A↔B 判断累计统计是否带来改进；B↔C 判断模型学习是否增值；
C↔D 判断敏感性+业务上下文是否改善处理。消融：去敏感输入 / 去本人基线 / 去群体基线 / 去业务上下文。

**预注册假设**（I7 反事后解释，先登记后跑，不达标照报）：
- H1：B 组在场景二（连续分批）首次限制位置**早于** A 组。
- H2：D 组在场景一（正常批量）正常业务误拦率**不劣于** C 组。
- H3：D 组在场景三（同数量不同敏感性）对高敏感组合施加更强义务，正常组不受牵连。
- H4：C 组相对 B 组的增益（若有）集中在范围累积类场景，而非单次大批量。

**带状态序列回放**（I5）：连续分批场景含初始历史/额度状态、请求顺序、虚拟时间、每步已知
信息、决策后状态更新。不同政策共用相同外部请求序列，各自维护模拟执行状态。固定回放只证
对应历史输入下的判断差异；闭环模拟须披露动作如何影响后续状态的假设。

**指标**（I6）：精确率/召回率、正常业务误拦率、动作分布、审批率/defer 比例、冷启动子集
表现、首次限制位置/检测延迟、额外请求延迟、重复预占/并发超额次数。标明单位（按请求/用户/
序列/事件）。真实交付量需执行遥测，仅模拟账本时标 `is_simulated`。失败/缺失/模型不可用
**不移出分母**。不只报总体准确率，不靠「全部转人工」制造低误拦假象。

---

## 10. Open Questions（不阻塞，用合成数据继续并标注）

| id | 问题 | blocking_scope | 处理 |
|---|---|---|---|
| OQ-1 | 主线一 `SensitivityProfileRef` 真实字段契约 | 画像对接的生产可用性 | 建自有 frozen dataclass + Provider 协议隔离，合成 Provider 先行 |
| OQ-2 | `behavior_source` 真实事件来源与完整性 | 真实行为基线 | 全合成验证，群体基线标「未在生产数据验证」 |
| OQ-3 | 正式 `product_spec` / `contract_spec` 文本 | 公共契约最终定型 | 以本任务规格为准推进，正式契约到位再校对 |
| OQ-4 | quota/approval 的真实生产 owner（是否在支线一） | 生产权威归属 | 本主线只建端口 + 参考实现 + 测试适配器，标注非权威 |
| OQ-5 | 并发额度在默认 SQLite 路径无法验证 | 「并发争用额度」必测项 | 配额并发测试 `@skipUnless(postgresql)`，走 docker/pgserver |

---

## 11. 变更与回滚政策（L 节）

- **允许**（本主线范围内）：`export_risk`/`export_quota` 内实现、测试、合成数据、docs。
- **待批准**：M1 起对 `settings.py` `INSTALLED_APPS` 的新增两行（属生产配置）。此前将其列为「允许」有误——
  当前两份材料无法确认跨会话批准事实；在收到明确批准来源前统一记为待批准，与 HANDOFF 的 `authorization_remaining` 一致。
- **禁止自动修改**：其他任务线公共语义（含 `audit`/`legal`/`users` 的模型与枚举）、未授权的
  API/schema/依赖/生产配置、用户已有修改、无关模块、生产政策与真实业务数据。
- **最小改动**：保持邻近风格，优先内部适配，不做无关重构。
- **回滚**：
  - **空库原型撤销**（无待保留业务状态时）：M0 删 `export_risk/contracts`+`judgment` 即净身；M1+ 在确认无待保留数据且迁移依赖允许时 `migrate <app> zero` 反向迁移。
  - **已产生业务状态的降级**（M4+ 已有预占/授权/回执/决定）：迁移可逆 ≠ 业务状态可无损回滚。须先停止签发/写入 → 核对在途执行 → 保留台账与事件引用 → 按批准的数据保留方案恢复代码或前向修复。**`migrate zero` 不作为通用生产回滚步骤。**
  - 删 app + 撤 `INSTALLED_APPS` 两行仅在空库原型下等于完全回滚；审计链已写事件不因删 app 消失。
  - 不整体 reset 覆盖用户工作；schema 变化评估可逆性；不可逆操作执行前请求决策。
- **安全（M 节）**：无硬编码凭证、服务端构建权威身份与 `request_fingerprint`、检查快照来源/版本/
  作用域/时效、组织/对象/环境隔离、未知权限不默认放行、不执行模型生成代码或任意规则表达式、
  模型不直接操作授权/配额、执行点再次复核当前权限、全程合成测试数据。

---

## 12. Stage 1 结构化 HANDOFF（Facet J）

```json
{
  "stage": "stage-1-source-audit",
  "mission": {
    "solved": [
      "确认复用能力、缺口与调用关系（只读）",
      "定位直接依赖，解释主要复用决定"
    ],
    "not_solved": [
      "主线一画像/授权/行为真实契约（无源可读，OQ-1/2）",
      "正式 product_spec/contract_spec（未提供，OQ-3）"
    ]
  },
  "findings": [
    {
      "id": "F1", "claim": "审计哈希链可复用为决策级证据设施",
      "capability_status": "Implemented", "evidence_status": "Verified",
      "verification_status": "Untested", "confidence": "High",
      "evidence_refs": [{
        "source": "audit/services.py", "location": "AuditLedgerService.append_entry",
        "observation": "单例锁行 select_for_update + 哈希链 append",
        "supports": "决策级事件上链",
        "does_not_support": "高频研判上链（全平台单锁会与 legal 抢锁）"
      }]
    },
    {
      "id": "F2", "claim": "legal.RiskAssessment 与规格 H3 同名不同义，不可复用其评分",
      "capability_status": "Implemented", "evidence_status": "Verified",
      "verification_status": "Passed", "confidence": "High",
      "evidence_refs": [{
        "source": "legal/services/risk_evaluator.py", "location": "class RiskAssessment / KEYWORD_RULES",
        "observation": "仅关键词打分，无快照引用/硬约束/义务/原因码/版本",
        "supports": "本主线用 ExportRiskAssessment 另立契约",
        "does_not_support": "直接复用为联合研判输出"
      }]
    },
    {
      "id": "F3", "claim": "无对象/字段/接收者级授权；users 仅角色级",
      "capability_status": "Missing", "evidence_status": "Verified",
      "verification_status": "Passed", "confidence": "High",
      "evidence_refs": [{
        "source": "users/models.py, users/permissions.py", "location": "CTFUser.role / IsAdminRole",
        "observation": "role∈{student,teacher,admin}，权限类仅角色级",
        "supports": "AuthorizationSnapshot 需由外部 authorization_source 提供",
        "does_not_support": "登录权限当作外发/接收者授权"
      }]
    },
    {
      "id": "F4", "claim": "下载计数非交付量，不可复用",
      "capability_status": "Partial", "evidence_status": "Verified",
      "verification_status": "Passed", "confidence": "High",
      "evidence_refs": [{
        "source": "resources/models.py", "location": "increment_download_count",
        "observation": "download_count 点击计数，非原子 read-modify-write",
        "supports": "DeliveryRecord 需执行层遥测 + is_simulated",
        "does_not_support": "用下载点击代替实际交付量"
      }]
    },
    {
      "id": "F5", "claim": "SQLite 下 select_for_update 为空操作，并发额度无法验证",
      "capability_status": "Partial", "evidence_status": "Verified",
      "verification_status": "Passed", "confidence": "High",
      "evidence_refs": [{
        "source": "django base/features.py + rag_ingestion/test_postgres_concurrency.py",
        "location": "has_select_for_update=False / @skipUnless(postgresql)",
        "observation": "SQLite 未覆盖行锁；仓库已有 PG-only 并发测试先例",
        "supports": "配额并发测试走真实 PG",
        "does_not_support": "默认 SQLite 测试路径证明并发正确性"
      }]
    }
  ],
  "artifacts": ["docs/mainline2-plan-and-contracts.md"],
  "approved_decisions": [
    "两个 app：export_risk + export_quota（不叫 export_guard）",
    "首期零新生产依赖；异常后端懒加载、不入 requirements.txt",
    "quota 建 DB 参考实现 + PG 并发测试；approval 仅内存适配器；均标注非生产权威",
    "docs/M0 零迁移，等用户 gate 再启动"
  ],
  "open_questions": [
    {"id": "OQ-1", "status": "Unknown", "blocking_scope": "画像对接生产可用性", "resolution_needed": "主线一 SensitivityProfileRef 字段契约"},
    {"id": "OQ-2", "status": "Unknown", "blocking_scope": "真实行为基线", "resolution_needed": "behavior_source 来源与完整性"},
    {"id": "OQ-3", "status": "Unknown", "blocking_scope": "公共契约定型", "resolution_needed": "正式 product_spec/contract_spec"},
    {"id": "OQ-4", "status": "Unknown", "blocking_scope": "生产权威归属", "resolution_needed": "quota/approval 真实 owner"},
    {"id": "OQ-5", "status": "Known", "blocking_scope": "并发额度必测项", "resolution_needed": "PG 测试环境（docker/pgserver）"}
  ],
  "judgment_changes": [
    {"previous": "app 命名 export_guard", "current": "export_risk + export_quota 两 app",
     "new_evidence": "D2 配额唯一权威 + guard 暗示执行拦截（属支线一）", "affected_decisions": ["决策一"]},
    {"previous": "quota/approval 均内存适配器占位", "current": "quota 需 DB 参考实现 + PG 并发测试",
     "new_evidence": "F5：内存适配器=进程内锁，违反 H6 且 SQLite 无法验证并发", "affected_decisions": ["决策三"]}
  ],
  "next_stage_constraints": [
    "M0 零迁移、纯 dataclass、不碰 settings.py",
    "判断核心受 assertNumQueries(0) + AST 纯度扫描约束",
    "四组对照共用同一政策引擎，仅融合层版本不同"
  ],
  "authorization_remaining": [
    "M1 起 INSTALLED_APPS 新增两行（生产配置，推迟到首次迁移）",
    "实验依赖 requirements-experiments.txt（非生产 requirements）"
  ]
}
```

---

## 13. 下一步

用户 gate 保留中。收到「开始」后：**M0** — 在 `export_risk/contracts` 与 `judgment` 落
frozen dataclass 契约 + 判断核心骨架 + 硬约束 + 纯度校验测试，零迁移、不碰 `settings.py`，
产出 M0 HANDOFF 供审。

---

## 15. 实现进度（M0–M5 原型及审查修复，2026-10-11）

分支 `feature/mainline2-export-risk`。两个 app：`backend/export_risk/`（研判+决策）、
`backend/export_quota/`（配额参考实现）。`settings.py` 仅新增两行 `INSTALLED_APPS`。

| 里程碑 | 交付 | 验证 |
|---|---|---|
| M0 | `contracts/`（frozen dataclass，零 Django）+ `judgment/`（纯函数：一致性、硬约束、assess_risk 骨架）| 纯度 AST 扫描 + 递归不可变 + 硬约束越权 deny |
| M1 | `models`（BehaviorEvent/ExportRequestLog/DeliveryRecord，三类计数三表）+ `features/`（声明式注册表 11 元数据 + 纯窗口计算）+ `adapters/`（Provider 协议 + 合成/Django 实现）| 迁移 + event_id 去重 + 窗口半开区间 + 缺失非零 + 水位 |
| M2 | `baselines/`（鲁棒分位统计 + 本人/群体基线 + 冷启动回退 + 回放截断）| 无历史不伪造正常 + 回放不读未来 + 退化 IQR 返回 None |
| M3 | `policies/`（版本化政策表 + hash + 四臂 A/B/C/D）+ `judgment/fusion`+`anomaly`+`explanation` | 基础保护下限全臂适用（R4）+ 四臂融合 + 模型缺失显式暴露（非静默）+ 三段式解释 |
| M4 | `decisions/`（create_risk_decision、prepare_execution、幂等、授权状态机、准入、审批适配器、outbox）+ `export_quota/services`（reserve/commit/release/reconcile 桶锁）| 幂等重放复核（撤销后不可执行，R1）+ 单次领取 + 准入拒合成（R3）+ 配额桶计量 + outbox→台账链校验 |
| M5 | `experiments/`（**4 类场景** normal_bulk/continuous_batch/unapproved_recipient/new_account、单臂判断回放、四臂对照、指标、预注册 H1/H2）| harness 可跑 + H1（B 早于 A 限制）+ 硬 deny 全臂一致 + 冷启动不误拦 + 分母完整 |

**最新测试**：`export_risk` + `export_quota` **Ran 117：116 通过、1 跳过**（PG 并发）；与 RAG 基线
四 app 合跑 **Ran 232：223 通过、9 跳过**，本次测试未发现回归；`manage.py check` 零问题。
命令：`PYTHONUTF8=1 DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH=:memory: DEBUG=true SECRET_KEY=dev-test-key python backend/manage.py test export_risk export_quota`。

> **审查修复（2026-10-11）**：第一轮原 22 条反例通过后，`mainline2-remediation-review.md` 又确认 F1/F2/F3/F7/F13
> 的 5 项边界仍未覆盖；已追加第二轮修复与 27 条正式边界测试。原反例脚本 **22/22**，第二轮脚本 **12/12** 均通过，
> 详见 `mainline2-boundary-remediation.md`；第一轮历史证据保留于 `mainline2-remediation.md`。
> 本结果只关闭测试覆盖的具体反例，不等于整个安全契约验收。原「M0–M5 安全契约闭环」属**过度声明**；
> 实际范围为 **4 类场景**、**单臂判断回放**（不含交付/配额执行状态闭环）、**D 臂暂无业务判定分支**、
> 决策**未存完整快照链**。本轮未扩建这些功能。

**未验证项（如实披露）**：`QuotaConcurrencyTests`（并发 60+60 争用 100 额度，仅一个成功）
已按 `@skipUnless(postgresql)` 写好，但**未在真实 PostgreSQL 上运行**——本机 Docker 守护
未启动，pgserver 可引导但其最简捆绑在本中文 Windows 主机上拒绝 `TimeZone=UTC`。因此配额
行锁的并发正确性目前仅有**锁设计 + SQLite 顺序逻辑测试**，不是实测并发保证；PG 并发仍为 Blocked。
上述历史环境原因未在本轮重新诊断，不用于覆盖顺序逻辑缺陷。

**能力状态**：以上为**已实现 + 已在 SQLite 验证**。真实敏感画像源、授权源、行为流、
配额/审批生产 owner 仍为 OQ-1~4，合成 Provider/测试适配器显式标注非生产权威。合成实验
仅证明机制，不等于生产效果。

---

## 14. 审查回应与契约补齐（对应 `mainline2-review.md` R1–R8）

审查结论**整体接受**。R6/R7 的边界结论经审查方对现有源码的最小实证确认（改时间戳/删链尾仍
通过校验、frozen dataclass 嵌套值可变），我原方案中「防篡改证据链」「migrate zero 即完全
回滚」等表述确属过强，已在 §1/§2.1/§11 就地更正。以下补齐 R1–R3 的 P1 安全契约与 R4–R8
的设计/口径，参数未批准者标 **DRAFT**。门槛沿用审查 §补齐顺序：**均不阻塞 M0**。

### 14.1（R1）执行授权状态机与领取/消费契约

- **幂等键作用域**绑定对象（服务端构建，不留给调用方解释）：可信主体/组织/环境 + 操作 +
  请求修订 + `request_fingerprint` + `decision_id` + `plan_hash` + 义务摘要。
- **授权状态**：`valid → claiming → consumed`，另有 `expired`(TTL) / `revoked`。
  原子领取保证 `claiming` 单一赢家。**终态（consumed/expired/revoked）不得回到 valid**；
  需重评时签发**新** `authorization_id`，经 `supersedes` 关联旧记录。
- **claim/consume 端口**（与执行支线共同定义，本主线只给契约不实现交付）：原子 `claim`
  返回唯一 `execution_token`；`consume` 以执行结果引用标记已消费；**领取后失败 → reconcile
  先核对执行结果再决定是否重试，不盲目再交付**。数据库事务 ≠ 跨网络 exactly-once。
- **验收反例**：同授权双消费者仅一个领取成功；已消费授权重放不再交付；同键换 decision/plan
  有确定响应；撤权后恢复权限不复活旧授权；多次共享访问按约定分别授权或受明确次数约束。

### 14.2（R2）配额契约

- **配额键** = (主体|组织, 数据域, 接收者类?, 操作)，含计量单位与窗口开闭区间。
- **共同锁定对象**：`QuotaBucket` 行即锁对象。`reserve` 对 **bucket 行**做条件原子更新
  (`reserved + delta ≤ limit`) 或 `select_for_update(bucket)`，**不是锁各自的 reservation 行**
  （锁预占记录不等于锁共同额度）。首次创建桶用 `get_or_create` + `unique(key, window)` + 重试；
  **锁顺序：先 bucket 后 reservation**。
- **计量**：`limit ≥ 已结算 + 有效占用 + 结果未知占用`。`commit` 以实际交付量
  (≤ 预占) 从 reserved 转 settled；`release` 只释放有效占用；`reconcile` 对未知结果**先核对
  交付再决定释放**。**TTL 到期 ≠ 未交付**：到期且结果未知 → reconcile，不自动全额释放。
- 授权有效期与预占有效期关系明确；执行启动时复确认预占仍有效，阻止「释放后旧执行者继续交付」。
- 同库说明本地原子边界；未来跨服务移交说明恢复/核对责任，不声称全局原子。
- **验收反例**：100 额度并发 60+60（仅一个成功）；空桶首次并发创建；跨窗口边界；领取与到期
  释放竞争；部分交付 + 回执丢失；重复结算。行锁用例用真实 PG 独立连接 + 受控交错。

### 14.3（R3）可信来源准入契约

- 每个 Provider 携带**权威身份、来源模式**(`production|evaluation|synthetic`)**、环境、作用域、
  版本**，由**可信注册/装配层服务端确定**；**绝不信任客户端传入的 `is_simulated=false`**。
- **生产签发**（`create_risk_decision`/`prepare_execution` 生产路径）只接受已配置的生产权威源
  + 服务端读取的决定；**评估环境无权访问生产签发与生产配额写端口**（装配/能力隔离）。
- 生产配置中出现测试适配器、生产 owner 缺失或依赖不可用 → **显式拒绝/降级，不回退到内存适配器**。
- **验收反例**：合成授权接生产入口被拒；跨环境重放决定被拒；伪造环境字段；缺失 owner；评估
  参数调用签发。通过判据 = **没有授权、没有生产配额写入**，而非仅返回了警告字段。

### 14.4（R4）共同保护下限 + 实验口径收紧

- **不可消融层**：共同权限检查 + 基础保护下限（受保护类别的强制脱敏等）对 A/B/C/D 及所有
  消融组**一律适用**；各组只变化特征/基线/模型/阈值/融合层。测试断言：无论分组，共同义务
  均在场——否则 D 的优势可能只是「多实现了必需安全政策」，无法归因于联合研判。
- **预注册口径**（替代 §9 定性假设的可计算定义）：
  - 分析单位：首次限制位置按**请求序列**计，拦截率按**请求**计；分母预先固定。
  - 永不限制的臂（如 A 在某场景）记为**删失**（censored），**不移出分母**。
  - 「不劣于」须二选一并写明：描述性比较（给置信区间）**或**预指定容忍差 δ 的统计结论；
    **不得事后声称统计不劣**。
  - 动作代价映射：`deny/defer/require_approval/mask` 各自如何计入误拦率、延迟、业务代价，预先定义。
  - 「更强义务」**不构成单一强弱序**（脱敏 / 限有效期 / 增审批互不可比）→ 按维度分别比较。
  - 固定随机种子/序列；切分遵 I3；失败计入分母。

### 14.5（R5）Stage 2 可冻结附件（草案，参数 DRAFT）

补齐审查要求的六类附件。因篇幅与「参数需方案阶段确认」，此处给出**可冻结骨架**，
完整 `feature_catalog`/`baseline_plan` 的逐特征 11 项元数据作为 **M1/M2 入口交付**。

**(1) 服务所有权表**

| 对象 | 生产者 | 消费者 | 权威源 | 缺失行为 |
|---|---|---|---|---|
| ExportRequestSnapshot | 支线一外发入口 | 本主线 | 服务端请求指纹 | 拒绝（无快照不研判） |
| SensitivityProfileRef | 主线一 | 本主线 | 主线一画像服务 | 降级：标画像不足，不默认不敏感 |
| AuthorizationSnapshot | authorization_source | 本主线 | 外部权威授权源 | `unknown`，不默认允许 |
| 行为事件 | behavior_source | 特征层 | 可信事件流 | 标完整性不足，冷启动回退 |
| QuotaReservation | export_quota | 执行支线 | 配额桶（本地库） | 预占失败→不签发 |
| 审批状态 | approval_owner | 决策层 | 外部审批（测试期内存适配器） | 缺审批→require_approval |
| DeliveryRecord | 执行支线遥测 | 交付量指标 | 执行遥测（`is_simulated` 标注） | 无遥测→不报真实交付量 |
| 决策级事件 | 决策层 outbox | audit/支线二审计 | 事务 outbox | 见 14.6 去重 |

**(2) 决策表骨架**（输入 → 动作 + 义务 + 原因码；**义务不支持时结果确定**）

| 优先级 | 条件 | 动作 | 义务/原因 |
|---|---|---|---|
| 1 | 硬约束：明确越权（接收者/范围/操作 forbidden） | `deny` | reason=`hard.forbidden`，不等模型 |
| 2 | 关键输入不足（画像/授权 unknown 且不可降级） | `defer`/`require_approval` | 按既定降级政策 |
| 3 | 必需审批缺失 | `require_approval` | reason=`approval.missing` |
| 4 | 已授权 + 业务匹配 + 行为正常 | `allow`/`mask` | 基础保护义务（恒含） |
| 5 | 高敏感 + 行为异常 | 按政策 `require_approval`/限制 | 敏感义务 + 异常证据 |

> **义务不支持处理**：若下游声明无法执行某义务 → 该路径结果降级为 `require_approval` 或
> `deny`，**绝不签发带无法兑现义务的授权**（N 节必测）。

**(3) 基线回退表（DRAFT）**：本人基线（最小样本 DRAFT）→ 同岗位/同任务群体（群体定义由
`authorization_source` 提供，**不复用 `CTFUser.role`**）→ 明确降级政策。记录训练窗口、历史截止、
污染处理；均标 DRAFT 待批准。

**(4) 字段契约**：每对象给类型/必填可空/枚举/`scope` 与 `fingerprint` 规范化方式/版本拒绝规则 +
≥1 对请求/响应样例——作为 M0 契约冻结的产出项。

**(5) Stage 2 HANDOFF**：待 R1–R5 契约 + 字段样例落定后产出，分区标注 `frozen` /
`pending_approval` / `prototype_only`，并映射到 N 节测试用例。当前仅有 Stage 1 HANDOFF（§12）。

> **OQ 范围收窄**：OQ-1~4 的「不阻塞」仅限**不阻塞合成原型**；主线一字段、正式公共契约、
> 生产 owner 缺失**仍阻塞对应公共接口冻结与生产接入**。B3 的 `acceptance_targets` /
> `resource_budget` / `data_policy` 记为 **Unknown**，不默认已解决。

### 14.6（R6）审计复用边界 + outbox 去重

- 能力表述收窄为「**现存记录的哈希链一致性校验**」。可证明：现存序列的 payload/链接哈希自洽。
  **不可证明**：防删除（无锚定链尾/条数）、防改时间戳（`created_at` 未入哈希）。更强保证属
  另行设计，**不为本主线重构 audit**。
- **重要事件时间纳入受哈希保护的 payload**，不依赖台账 `created_at`。
- **outbox 去重**：本地同库台账，outbox 行领取 + 台账追加 + 完成标记置于**同一事务**，或采用
  业务 `event_id` 唯一去重（`current_hash` 唯一 ≠ 事件唯一，因 `previous_hash` 会变）。外部
  消费者自行处理至少一次投递。
- **验收反例**：追加与完成标记间故障；多消费者竞争同一 outbox 行；相同 `event_id` 重投。

### 14.7（R7）不可变与纯度的真实兑现

- `frozen=True` 不递归冻结嵌套 dict/list（实测可变）。**边界处深拷贝 + 递归规范化**快照为
  不可变集合/序列化内容寻址载荷；摘要对应实际内容。
- `assess_risk` 仅收 `model_version/policy_version` 不足：**输入准备层解析并校验模型/政策工件**，
  再显式提供固定推理依赖或内容寻址句柄；绑定版本/哈希/预处理/特征顺序，**回放期不偷换为 latest**。
- AST + `assertNumQueries(0)` 定性为**工程护栏（非证明）**；补测：嵌套输入篡改、间接时钟/IO、
  同输入重放确定性、模型缺失、版本不匹配。

### 14.8（R8）回滚的数据保留边界

见 §11 已更正：区分空库原型撤销与已产生业务状态的降级；`migrate zero` 非通用生产回滚。

### 14.9 补齐顺序与通过条件（采纳审查 §补齐顺序）

1. **M0 契约冻结前**：明确 `scope`/`fingerprint` 规范化、可信来源准入、不可变输入、硬约束与
   未知输入行为；产出最小字段表 + 请求/响应样例。
2. **M1/M2 前**：批准特征/窗口/去重与基线回退表；落实版本、水位、冷启动验收。
3. **M3/M5 前**：固定共同基础保护下限、各实验臂差异与指标口径；不预设算法提升。
4. **M4 接入前**：R1–R3 闭环；真实 owner 或明确仅测试模式；PG 并发与故障恢复验证通过；
   outbox 与消费方责任清晰。
5. **生产启用前**：真实权威源、真实执行方、真实数据边界集成验收；落实数据保留回滚方案。

达到对应条件逐阶段推进，不等所有研究完成才做内部原型；未达生产条件时交付状态为
**partial/prototype**，不标 ready for production。




