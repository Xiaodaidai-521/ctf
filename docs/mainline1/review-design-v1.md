# 第6步内部复核、适用性与通知接入说明

日期：2026-10-14。内部实现已验证；跨模块契约仍 **Proposed**，本文件不构成批准。
沿用 design.md 第7节及未修改的 contracts/schema.json；不新增公共 HTTP 入口。

## 服务和输入

`ReviewService(repository, access)` 由可信服务端构造。`ReviewPrincipal` 的 actor/domain/environment/evaluation 来自认证上下文，不接受请求 JSON 身份。`ObjectAccess.allowed(principal, asset, operation)` 必须对具体资产版本鉴权；每次读取、复核、幂等重放均重新调用，未知/越权统一 OBJECT_NOT_FOUND。生产 owner 未接入，测试中的 AccessDouble 不是正式权限实现。

- `register(principal, RuleResult, ParseResult)`：内部扫描入库边界，检查固定资产、解析指纹、政策和发现引用；不能给普通客户端开放。初次建立唯一 head；已有链的新扫描需第8步正式重扫/CAS设计，不可借 register 抢占。
- `list_findings(principal, profile_id, pending_only=True, offset=0, limit=50)`：固定不可变画像分页，limit≤100；整格展示 `[REDACTED]`，返回位置、原判断、类别、来源及允许的机器依据码，不返回原文、上下文、任意原因文本或私有证据内容。
- `submit_review`：必填 base_profile_id、expected_state_version、idempotency_key、action、reason。confirm/false_positive 指定 finding_id；correct 另指定 category_id；add_manual 指定 category_id 和单个实际已解析单元格/字符位置。位置与原契约相同，字符为零基 Unicode 码点半开区间，span 仅 start/end，不引入新字段。
- `add_manual_finding`：同一提交路径的显式入口。
- `get_review`：额外 read_review 对象权限下读取追加记录和依据；reason 是受控私有文本，不能写日志或事件。
- `get_profile` / `get_profile_applicability`：返回隔离副本；后者读取事务存储的权威状态，不依赖事件是否收到。
- `review_reuse_eligibility`：只返回严格匹配资格及原因，不自动应用结论或发布重扫。

每次接受提交同时生成追加 ReviewRecord、人工后继 Finding（误报除外）、新 Profile 和替代关系。原始 rule/semantic/fusion 发现及所有历史画像保留，人工发现 source_type=manual，detector_id/version=null，created_by/review_id 必填；确认及修正通过 source_finding_ids 指回原发现。保护等级按固定版本政策从全部活动类别重算，不接受客户端等级。质量、覆盖、限制不因人工确认而升级。多条发现逐条复核，每次绑定新的 head。

同步服务只有 accepted/completed 记录；校验、权限或版本失败不写假记录，不将被拒请求记为 false_positive。未实现异步申请/驳回工作流。组合策略仍未批准；画像含组合发现时明确 COMBINATION_REVIEW_UNSUPPORTED，避免删掉关系等级或误算总等级。真实规则发现与默认关闭组合的第5步画像可以消费；真实模型有效性不是本步前置。

## 并发、持久化和适用性

幂等键作用域是 domain/environment/evaluation/actor/operation；同键同规范化请求返回同一记录，同键不同内容 IDEMPOTENCY_CONFLICT。请求绑定 head 和适用性版本；两位复核者只有一个成功，另一方 REVIEW_VERSION_CONFLICT。最新画像引用须再次鉴权才返回。

`DjangoReviewRepository` 使用既有 Django/PostgreSQL，以新增 ReviewLedger 单行和 select_for_update 串行化跨范围事务；单行主键及 check 约束限制 id=1，原子检查保证逻辑 head/key 唯一。历史、head、适用性变化日志和 outbox 一起提交或回滚。全量 JSON 私有 aggregate 上限16 MiB，超限拒绝写入；该方案偏向小规模内部验证，不宣称高吞吐。分区/分表为后续独立设计，不能直接换成无跨范围锁的实现。`MemoryReviewRepository` 只用于本地验证，进程结束即丢失。

新增迁移 `0002_reviewledger` 只在新建合成 PostgreSQL 集群执行并回退验证。未修改历史迁移、未注册生产应用、未运行既有业务库迁移。持久化存储内含私有运行上下文和复核原因；生产启用前必须由 owner 确定 ACL、保留和删除策略。

旧画像状态变为 superseded，含 successor_profile_id、原因、递增 state_version 和时间；历史内容不改。新画像 current 仅表示本链当前版本。现有政策全为 development draft，`usable_for_new_decision` 始终 false；不能将 current 解释为生产可授权。

任何人工复核都保守地将同域/环境/评估身份、同资产版本的其他 current 画像标为 reevaluation_required，并追加通知；不确定范围交集时不冒险保留 current。复核后的同版本新范围不能通过 register 绕开人工结论，返回 REVIEW_REVALIDATION_REQUIRED。此实现可能要求不相交范围也重评估，是明确的保守内部选择。不同资产版本不混为同一份数据。

下游须检查 `status`、`state_version`、`usable_for_new_decision`、资产及政策条件；仅有旧画像/旧计划摘要一致不够。历史审计可用与新授权可用分别返回。查询失败或不可用时不得自行把旧结果视为通过；跨模块最终拒绝/延后规则与检查后变化的处理仍需共同批准。主线一不撤销外部决策、不修改外部数据库。本步未实现第7步计划验证器。

## 通知和人工结论复用

`ReviewOutbox(repository, adapter=None)` 默认 not_connected，零投递、零尝试计数。事件遵守现有 Proposed ProfileChangedEvent 字段：固定 event_id、旧新画像、资产版本、scope、原因码、aggregate_version、作用域及时间；复核自由文本/单元格原文不进入事件。

可信事件适配器 `publish(event) -> bool` 只有收到持久化确认才返回 True。正式事件中心信封和服务地址未批准，未实现或声称真实远程投递。显式 `dispatch(limit≤100)` 在事务外调用适配器，失败重试沿用相同 event_id；默认3次后 dead_letter 保留待运维处理，不删除已提交复核。投递成功而本地确认提交失败可能重投，消费者按 event_id 去重，并按 old_profile_id+aggregate_version 防止状态倒退。需 owner 的受管调度接入；没有在 Web 中启动后台线程。死信重驱动/告警/SLA 未接入，不把草案30秒/60秒写成实测保证。

后续扫描的人工结论资格要求固定资产/hash、范围、解析版本/配置/内容及元数据指纹、上下文、分类政策/规则配置、语义配置、融合/组合/扫描政策均一致；原复核的后继必须仍是 current head。否则重新复核，绝不只按相同坐标迁移。比较材料保持在私有存储，不向调用者暴露逐格低熵摘要。当前仅资格查询，不自动修改新扫描结果；一次后续复核也会保守取消之前记录的自动复用资格。

## 正式接入待决方案（未批准）

推荐先保留内部使用，消费已验证规则画像；需要正式接入时，由资产 owner、主线二/执行层及事件支线确认：

1. 按现有 design.md 第7节及 schema.json 的 ReviewRecord/ProfileApplicability/ProfileChangedEvent 语义批准，或指出具体字段变更；现有实现不擅自发布新版本。
2. 指定真实资产 ACL adapter，给出部署环境、生产政策和受控数据保留范围；授权迁移执行需单独明确目标环境。本步隔离测试批准不能外推。
3. 指定正式事件信封/接收适配器及受管投递机制；共同确认不可查询时失败关闭/延后、状态版本检查和通知延迟目标。

这些待决项只阻塞正式接入，不撤销已有内部实现和隔离验证授权。D04真实语义/数据路径/费用、D05组合策略等前序待决仍独立存在。

## 验证与回滚

仓库根：`python -B docs/mainline1/verify_step06.py`。backend目录：`python -B -m mainline1.tests.run_review_postgres`。前者记录本地回归及文件摘要保护，后者复用已有隔离集群生命周期，单独写 step-06-postgres-verification.json，不覆盖第3步证据。

撤回仅限本步新增源码、迁移和文档，以及 models.py 的 ReviewLedger 增量、隔离验证器可选参数、README 和 HANDOFF 增量。历史交接留存。没有业务库回滚动作；将来若迁移已获准应用并承载数据，必须先保留审计和引用，不能直接 reverse/drop。
