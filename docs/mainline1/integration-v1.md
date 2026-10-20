# 主线一接入说明 v1（backend-only，内部 Proposed）

日期：2026-10-16。本文把第3—9步已实现并已验证的内部组件整理成跨模块接入说明。`docs/mainline1/contracts/` 中的对象和事件仍是 Proposed；本文不发布 HTTP 路由、不批准公共契约、不授予外发权限。

## 适用范围和入口

本轮交付模式为 `backend_only`。服务端调用方在受管进程中构造可信 `ReviewPrincipal`、资产 owner 适配器、`ObjectAccess` 和持久化 repository，再使用 `backend/mainline1/operations.py` 的 `Operations` 组合器。它不是已注册的 Django URL 或生产后台任务。`execute_one` 必须由已有进程管理器显式驱动；`backend/mainline1/management/commands/run_parse_worker.py` 只处理受管的解析任务，缺少可信 `MAINLINE1_PRIVATE_SOURCE_FACTORY` 时拒绝运行。

最小合成运行方式是从 `backend/` 执行 `python -B -m mainline1.operations_smoke`。定向评测入口是 `python -B -m mainline1.evaluate_step09`；它只读取 `docs/mainline1/step-09-eval-set-v1.json`，不读取凭据、不访问网络、不发送原文。上述命令均不是生产发布或外发执行入口。

## 主线二接入

主线二消费 `SensitivityProfile`、`Finding`、分层 `coverage` 和 `ProfileApplicability`。每次消费必须同时核对 `asset.asset_version_id`、`asset.content_hash`、`scope_hash`、`scan_id`、`profile_id`、`policy_version`、解析/检测配置摘要和可信 `meta`，并按对象 ACL 读取。`Finding` 的位置是固定工作表/逻辑行/列、通道和 Unicode 码点半开区间；规则、语义、融合和人工来源要保持可区分，`unknown`、`pending`、`partial` 不能被当作一般数据或完整覆盖。

新决策前必须查询权威适用性：只有状态和业务条件都满足时，`usable_for_new_decision` 才可能为 true；该布尔值也不是放行或外发授权。`current`、历史可审计和可用于新决策是不同概念。遇到 `superseded`、`reevaluation_required` 或 `unverifiable_deleted`，主线二应停止沿用旧画像并按原因重新评估；查询失败应失败关闭或延后，不能因摘要相同而放行。重扫的 `ScanComparison` 将 `added`、`disappeared`、`category_changes` 和 `unmatched` 分开返回；不得用移动后的相同坐标继承结论。

主线二不应从 `plan_hash`、保护等级或画像状态推断法定分级、接收者授权或外发合法性。组合关系在本轮没有批准的业务政策和真值，相关覆盖为 N/A。

## 执行支线接入

执行支线从 `PlanService.build`/`validate` 消费 `RedactionPlan`。计划绑定资产版本、扫描、画像、范围、解析配置、分类/脱敏政策、规范化保护要求、`requirements_hash` 和 `operation_contract_version`；操作来自服务端白名单，目标均按同一不可变输入快照解释。`ready` 只表示当前纯校验无未解决项，`partial` 和 `invalid` 必须按 `unresolved`/`validation_errors` 处理。

执行前必须重新读取资产 owner 状态、画像适用性、要求和权限，并在执行方自己的原子使用边界内再次校验版本、范围、位置、参数、重叠和内容匹配。`plan_hash` 只证明计划内容一致，不是签名、授权、额度预占或共享令牌。`operation_contract_version=original-snapshot-v1-proposed` 尚未由执行方共同批准；执行方应先确认删除列、整格、字符区间和组合操作的语义，再决定是否接入。

执行支线应将稳定错误映射为可重试或终止状态，而不传播原文异常：`OBJECT_NOT_FOUND`、`DOMAIN_MISMATCH`、`ASSET_VERSION_MISMATCH`、`PROFILE_SUPERSEDED`、`PROFILE_REEVALUATION_REQUIRED`、`PROFILE_UNVERIFIABLE`、`PLAN_CONFLICT`、`PLAN_HASH_MISMATCH`、`COVERAGE_INSUFFICIENT`、`AUTHORITY_UNAVAILABLE`。本模块不生成交付副本、不创建共享、不预占额度，也不替执行支线作最终外发决定。

## 审计支线接入

审计支线消费追加的 `ReviewRecord`、画像替代关系和 `ProfileChangedEvent`。复核接受后生成新画像，旧画像和发现保持不可变；`supersedes_profile_id`、`successor_profile_id`、`state_version` 和原因码用于追溯。被拒请求不等于误报，人工发现必须标为 `source_type=manual` 并带 `created_by`/`review_id`，不能伪造检测器版本。

事件由同一事务写入私有 outbox；事件类型包括 `profile_superseded` 和 `profile_reevaluation_required`，至少含 `event_id`、旧/新画像、资产版本、影响范围、原因码、`aggregate_version` 和可信作用域。复核自由文本、原文单元格和低熵匹配值不得进入事件。正式适配器必须在持久确认后返回成功；消费者按 `event_id` 去重，并按旧画像和聚合版本拒绝倒退。当前 `ReviewOutbox(adapter=None)` 为 `not_connected`，没有真实事件中心或投递 SLA 证据。

## 评估支线接入

评估支线消费 `step-09-eval-config-v1.json`、`step-09-eval-set-v1.json`、`step-09-results.json` 和 `step-09-verification.json`。数据集状态是 `candidate_not_independent`；A 规则结果 `TP=6, FP=0, FN=0` 只描述本合成候选集，不能外推生产。B/C 的目标等价和输入预检通过，但真实模型调用为 0、`metrics=null`、上下文收益状态为 Blocked。评估支线不得把内存契约替身、规则指标、`ready` 或合成结果写成真实模型效果或外发阻断证据。

若未来申请真实实验，必须另行批准独立标注集、分组切分和冻结版本、provider/model/endpoint、凭据注入、本地 token 计数、数据范围与总 token/费用上限；不得修改冻结测试集来适应结果。

## 对象、版本、事件和私有引用

| 对象 | 所有者/消费者 | 关键版本与状态 | 私有引用和访问要求 |
|---|---|---|---|
| `AssetVersionRef` | 资产 owner；主线一/主线二/执行支线 | `asset_version_id`、`content_hash`、`state_version`、`ready/deleted/unavailable` | `private_storage_ref` 是不透明句柄，不是路径、URL 或授权；每次由 owner 鉴权 |
| `ScanResult`/任务 | 主线一；授权查询方 | `scan_id`、尝试、`queued/running/succeeded/failed/cancelled`、stage、覆盖；未知总量为 null | `snapshot_ref` 和解析产物仅私有存储；失败/取消不得伪造完整结果 |
| `SensitivityProfile`/`Finding` | 主线一；主线二、复核、评估 | `profile_id`、`scan_id`、政策/配置版本、质量和覆盖 | 位置和受控证据按 ACL 返回；通用日志不写原文或整包结构 |
| `ProfileApplicability` | 主线一提供权威状态；主线二/执行支线查询 | `state_version`、`current/superseded/reevaluation_required/unverifiable_deleted`、`usable_for_new_decision` | 查询失败不得沿用旧状态；历史可审计不等于新决策可用 |
| `RedactionPlan` | 主线一生成；执行支线共同维护操作语义 | `plan_id`、`plan_hash`、要求/政策/操作契约版本、`ready/partial/invalid` | `match_ref`、`validation_ref` 是受控内部引用；执行前再次校验 |
| `ProfileChangedEvent` | 主线一 outbox；审计/主线二/执行支线消费者 | `event_id`、事件类型、`aggregate_version`、旧新画像和范围 | 当前未连接真实事件中心；消费者必须去重和防倒退 |

所有对象均按 `domain_id`、`environment`、可选 `evaluation_run_id` 和经认证主体隔离。匿名、跨域或无 ACL 读取统一为稳定的 `OBJECT_NOT_FOUND`/认证错误；客户端不能自报主体、域或环境。现有对象、事件和错误目录见 `docs/mainline1/contracts/catalog.json` 与 `schema.json`，状态为 Proposed，跨线接入前须由 owner 共同批准。

## 运行限制和未验证边界

第3—8步的 157 项本地回归和 55 项隔离 PostgreSQL 检查，以及第9步的规则/契约替身检查已保留证据。尚未验证生产资产 owner、生产 ACL、HTTP 路由、跨进程计划仓储、正式 outbox 适配器、真实模型、独立效果、执行方原子写入和真实外发阻断。迁移文件只在隔离测试库验证；没有执行既有业务库迁移。解析的 CPU/RSS 硬隔离、生产累计费用/墙钟预算和正式保留期限也未建立。

## 回滚和接入前置

本轮文档和评测产物可按第10步交接撤回；撤回不删除第3—8步业务实现、数据库或业务数据。未来若获批生产启用，应先停止新任务和 outbox 消费，保留仍被引用的私有产物，按对象 owner 的迁移/失效流程处理，再回滚服务注册。已承载数据的迁移不可直接 reverse/drop；必须先保留审计、引用和最小失效标记。任何真实模型、公共契约、生产部署、业务库迁移、资产删除或外发执行都需要独立授权。
