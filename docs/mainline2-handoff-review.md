# 主线二 M0–M5 交接代码审查

审查日期：2026-10-11。源码提交：`b978b8d7efaf6b1263d2a16c3aa87974b9ad6e5f`。

审查输入：`docs/mainline2-handoff-for-review.md`，并对照 `docs/mainline2-plan-and-contracts.md`、上一轮 `docs/mainline2-review.md` 和实际实现。

## 结论

**存在需要修正的实现问题，不建议按“安全契约已闭环、M0–M5 完整交付”通过验收。** 适合标记为有测试的内部原型。作者对真实 PG 未验证、C 臂没有训练模型、主线一与生产 owner 尚未接入的披露是正确的；但除此之外，当前代码还有可确定复现的授权、生命周期、配额恢复和特征计算缺陷。

本轮归并为 **6 项 P1、7 项 P2**。这些是服务函数/判断函数层面的错误，不是仅从“没有生产接入”推断出的问题。新模块未提供公开外发 API，本审查不据此声称匿名客户端已能从网络直接利用。

本轮只新增审查报告、隔离验证脚本和验证结果，没有修复或修改业务源码，没有访问真实业务数据库。以下优先级使用常规代码审查口径：P1 应优先修正；P2 应在相应功能验收前修正。

## 实际运行结果

| 验证 | 结果 | 能证明的范围 |
|---|---|---|
| 原有 `export_risk export_quota` | Ran 66；65 通过、1 跳过 | 现有测试可复现 |
| 原有六 app 组合回归 | Ran 181；172 通过、9 跳过 | 现有测试下未见回归失败 |
| 独立保护条件验证 | Ran 22；20 个断言失败、2 通过、0 运行错误 | 20 个反例归并为下列 13 项问题 |
| outbox 写台账后、标记 sent 前故障注入 | 通过 | 当前同库事务能够一起回滚，重试只追加一次 |
| 判断核心 `assertNumQueries(0)` | 通过 | 本次代表性判断路径不执行数据库查询 |
| 真实 PG 并发 | 本轮未运行 | 不据 SQLite 结果宣称行锁/并发正确性 |

“Ran 66 / Ran 181”均包含跳过用例，不能表述成 66 或 181 项全部实际通过。组合回归进程成功；日志中出现既有回退及 SQLite 锁相关告警，没有导致该次测试失败。

独立脚本显式配置 SQLite `:memory:`，使用真实模型和服务函数，不读取项目 `settings.DATABASES`，不创建真实业务库。脚本位于正常 Django 测试发现范围之外，其断言描述**应该具备的保护行为**；退出码 1 表示发现反例，不能把这些失败说成测试通过。

复现命令（仓库根目录）：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'E:\xianmu\.review-venv\Scripts\python.exe' 'docs/review-support/mainline2_handoff_probes.py'
```

原始结果：`docs/review-support/mainline2-handoff-probe-results.json`。

## 发现

### F1 [P1] 执行准备没有复核当前权限，幂等分支还跳过审批复核

**代码：**`backend/export_risk/decisions/service.py:100–137`，尤其 106、118–125 行。

`authorization_snapshot` 在整个函数中只被用于读取 `source_mode`。没有检查授权结果、主体、范围、操作、接收者、有效期等。因此已有 allow 决定后，把新的权限快照改为 `FORBIDDEN`，首次执行准备仍返回 `kind=executable`。

幂等命中时还会在动作与审批检查前直接返回；`_recheck` 仅检查决定/授权记录的部分状态。审批先 approved、成功准备授权，再改为 revoked，同键重试依然 executable。这与交接说明“复核当前态”的声明不一致；既有测试仅调用 `revoke_authorization`，没有模拟上游权限或审批撤销。

**修正：**首次和重放共用完整的当前条件复核，验证可信快照绑定与时效、最新审批状态及其他执行前提；失效时返回 NotExecutable。不要仅检查旧授权表是否被人显式改成 revoked。

**失败验证：**`test_prepare_rechecks_forbidden_authorization`、`test_replay_rechecks_revoked_approval`。

### F2 [P1] 判断核心接受其他主体的授权，也忽略已过期授权

**代码：**`backend/export_risk/judgment/consistency.py:13–32`、`hard_constraints.py:26–46`、`core.py:40–100`。

一致性检查只有资产版本与环境，硬约束只检查总体 forbidden 以及接收者/操作/范围名单。`AuthorizationSnapshot.subject_id` 未与请求主体比较；`valid_until`、`observed_at` 未结合显式 `evaluation_time` 校验，后者实际未被使用。

**复现：**保持允许名单一致，把授权主体改为另一个用户，结果是 allow；把 valid_until 改为评价时刻前一天，结果仍是 allow。两种反例直接经过真实判断核心，不涉及伪造 assessment 或绕过生产入口。

**修正：**在纯判断层校验主体、作用域和时间绑定。用注入的评价时刻进行带时区比较；未知/空白关键授权信息按明确降级政策处理，不默认为长期有效。此修复与 F1 不可互相替代，两个入口都需要正确。

**失败验证：**`test_core_rejects_other_subject_authorization`、`test_core_rejects_expired_authorization`。

### F3 [P1] claim 只看 state，过期或决定失效后仍可领取

**代码：**`backend/export_risk/decisions/service.py:171–183`；相关 `_recheck:67–77`、`invalidate_decision:203–207`。

`claim` 只锁授权行并检查 `state == valid`，不检查授权/决定到期，也不读取父决定状态。`invalidate_decision` 只改决定，不级联失效授权。故正常签发后推进到次日，或显式 invalidate 父决定，claim 仍返回 True。配额预占被 release 后同样可以领取。

合同注释要求执行方再次确认预占，但当前领取端口没有承接这一原子边界；外部先查再 claim 仍需明确与到期/撤销竞争的处理，不能用“PG 行锁”代替被遗漏的条件。

另外，consumed 授权的幂等重放仍被 `_recheck` 判为 executable。正确再次调用 claim 会拒绝，因此本审查**不把这单独等同于已经发生二次交付**；但返回契约的可执行状态已经错误。

**修正：**在受控锁顺序/一致性边界内领取时检查必要状态与期限、关联决定和预占，拒绝终态或失效记录；重放不能把 consumed/claiming 当作新的可执行许可。完善领取者凭证与结果绑定，当前 claim 仅返回 bool、consume 的 execution_result 被忽略，尚未兑现方案 §14.1 的执行令牌契约。

**失败验证：**`test_claim_rejects_expiration`、`test_claim_rejects_invalidated_decision`、`test_claim_rejects_released_reservation`、`test_consumed_authorization_not_reported_executable`。

### F4 [P1] 生产准入没有覆盖审批权威与决定来源

**代码：**`backend/export_risk/decisions/service.py:105–108,132–135`、`approval.py:20–32`；`models.py:110–136`。

`InMemoryApprovalProvider.is_production_authority=False` 从未被检查。只要 request 与 authorization_snapshot 的 source_mode 是 production，即使显式传入非生产内存审批器，生产路径也会签发执行授权。

另一个反例是：用 evaluation/synthetic 输入创建决定，随后提供对应请求的 production 快照，持原 decision_id 调用生产 prepare_execution，仍返回 executable。决定没有持久化环境、来源或完整输入链，入口因此无法拒绝这种跨环境重放。

这不是要求现在接入真实生产 owner，而是要求 owner 尚未接入时，生产分支兑现其宣称的 fail-closed；文档“非生产权威”或来源枚举不足以构成保护。

**修正：**可信装配层验证全部相关 Provider 的权威属性，持久化并校验决定的来源/环境/输入绑定；生产缺少真实 owner 时显式拒绝。测试适配器仅在隔离模式使用，不能通过更换两张输入快照的来源标签让旧评估决定获得生产执行权。

**失败验证：**`test_production_rejects_test_approval_provider`、`test_production_rejects_synthetic_decision`。

### F5 [P1] create_risk_decision 可以把一个请求的评估挂到另一个请求

**代码：**`backend/export_risk/decisions/service.py:35–56`。

函数独立接收 assessment 与 request，却不比对二者的 request_id/request_fingerprint。持久化时使用 request 的请求指纹/范围，结合 assessment 的 allow/action/画像，生成一个新的“有效决定”。

**复现：**用真实核心评估 review-request，再把不同 ID 和不同指纹的请求传给 create_risk_decision，创建成功，决定 request_id 变成 other-request。这会使后续只按决定指纹比较请求的检查失去作用，因为错误绑定已经被写入库。

**修正：**先校验 assessment 与 request 的身份、摘要和输入引用一致；更优的服务边界是从可信持久快照重新读取或统一构建评估与决定。不能把任意可构造 dataclass 当作已经对当前请求完成研判的证明。

**失败验证：**`test_create_rejects_assessment_for_other_request`。

### F6 [P1] 配额幂等重放不检查绑定，还可能返回错误 bucket_id

**代码：**`backend/export_quota/services.py:50–60`。

reserve 先按本次参数取桶，然后仅按全局 reservation_id 查询已有记录，命中即返回。没有核对已有记录的 bucket、fingerprint、amount 或状态。返回值甚至组合了“本次新桶 ID”和“旧预占 amount”。

**复现：**用户 A 在桶 1 预占 60；用户 B 在桶 2 以相同 reservation_id、不同 fingerprint 和 amount=90 再请求，返回成功重放，报告 bucket=2，但实际预占仍在 bucket=1，桶 2 没有对应占用。同一 ID 对已释放预占也没有活跃性校验。

**修正：**比较完整幂等绑定，异请求/异桶/异金额返回明确冲突；返回实际记录的桶；结合状态定义重放结果，不能把 released/unknown/committed 都当作新的一次有效预占。

**失败验证：**`test_quota_replay_rejects_changed_binding`。

### F7 [P2] 预占进入 unknown 后永远无法核对结清

**代码：**`backend/export_quota/services.py:108–134`，尤其 119–120 行。

`reconcile(delivered_amount=None)` 把预占从 reserved 改为 unknown，但 commit、release、reconcile 随后都只接受 reserved。后续即便补到了可靠交付回执，也没有服务端口能够扣减 unknown_reserved、结算实际交付或释放确认未交付的部分。

**复现：**预占 60 → 结果未知 → 收到交付 40 的回执 → 再 reconcile(40)，报 `cannot reconcile from state unknown`，额度永久卡住。既有测试只验证进入 unknown，没有验证从 unknown 恢复。

**修正：**定义未知结果的后续核对转换，在同一桶锁事务内更新 unknown_reserved/settled，并使相同结果重试幂等；仍应保守拒绝未经确认的全额释放。

**失败验证：**`test_quota_unknown_can_be_reconciled_after_receipt`。

### F8 [P2] 配额允许负预占，并静默截断超额交付量

**代码：**`backend/export_quota/services.py:47–74,85,128`；`models.py:22–25,58–59`。

reserve 没有非负数量校验或相应约束。直接调用预占 -50 后，100 上限的桶可接受正数 150。prepare_execution 当前对其调用做了 max(0, record_count)，但这不能替代可独立复用的 QuotaService 自身的输入契约。

commit/reconcile 用 `max(0, min(delivered_amount, res.amount))` 静默截断报告值。预占 60、回执 90 被记成 60，隐藏了数据异常或实际超额。正确行为可以是拒绝不合法回执并进入核对，也可以明确记账/告警，但不能悄悄改写证据。

**修正：**校验数量类型、范围、期限与上限，补数据库约束作为最后防线；交付回执超出预占时进入明确异常处理流程。

**失败验证：**`test_quota_rejects_negative_amount`、`test_quota_does_not_silently_clamp_actual_delivery`。

### F9 [P2] 历史特征使用了当时尚未收到的事件

**代码：**`backend/export_risk/adapters/behavior.py:50–60`、`features/compute.py:49–64`；合成 Provider 同样只过滤 occurred_at。

两层都只按发生时间过滤，忽略 received_at。即便 watermark 的查询按接收时间做了限制，也不影响 fetch_events 已经返回的未来到达事件。

**复现：**事件发生于评价时刻前 1 分钟、实际收到于评价时刻后 1 小时；在该历史时刻读取 Django Provider 并构建特征，req_count_long=1，预期为 0。这直接违反“严格回放仅使用当时已收到信息”，会污染回放与基线输入。

**修正：**明确发生窗口与知识截止时刻的双时间语义，查询/计算按 received_at 截止过滤，并对迟到、重放和外部 Provider 保持同一规则；不能只给快照贴一个水位标签。

**失败验证：**`test_late_received_event_excluded_from_historical_inputs`。

### F10 [P2] 请求次数把拒绝、交付和共享访问事件一起算入

**代码：**`backend/export_risk/features/compute.py:52–56`；特征定义 `features/registry.py:55–69`。

特征单位是 requests、描述为外发尝试量，但计算对窗口内所有 event_type 直接 len。一个请求的不同生命周期事件拥有不同 event_id，因此数据库 event_id 唯一不能消除这种业务层重复。

**复现：**输入 export_request、denial、delivery、share_access 四条事件，外发请求次数得到 4，而外发请求事件只有 1。接入真实多类行为流后，累计阈值与基线偏离都会被放大，正常业务可能被误送审批。

**修正：**每个特征明确选择事件类型与业务去重键；被拒尝试仍计一次外发请求，拒绝结果不另加一次请求。若需要查询次数/共享访问次数，应独立定义特征。

**失败验证：**`test_request_count_does_not_count_lifecycle_events`。

### F11 [P2] 模拟行为数据会进入默认真实特征路径

**代码：**`backend/export_risk/adapters/behavior.py:50–60`、`features/compute.py:49–64`。

is_simulated 被完整带到 EventRecord，但行为特征计算不读取它，也没有选择模式的参数。交付计算有默认排除模拟值的开关，行为计算没有对应保护。

**复现：**同一主体只有一条 is_simulated=True 的数据库行为事件，按默认 Provider→build_feature_snapshot 路径，真实请求计数仍为 1。

**修正：**在数据源装配与查询中隔离评估和生产数据，或者提供显式、默认排除模拟值的计算模式，并在快照中保留来源。不能依赖调用方记住手动过滤一个当前服务自身不处理的标记。

**失败验证：**`test_simulated_behavior_excluded_by_default`。

### F12 [P2] 零个人历史时，即使群体样本充足也无法使用群体基线

**代码：**`backend/export_risk/baselines/baseline.py:54–56,92–95,126–127`。

同群体样本达到阈值后，本应回退使用群体基线。但 own 为 0 时，返回值被标记 INSUFFICIENT_HISTORY，而 usable 据此直接返回 False，compute_deviations 返回空字典。

**复现：**新用户 0 条本人历史、同群体 25 条有正常分布的历史；scope 确实是 cohort、统计也已经构造，但 usable=False，无法生成偏离。既有“冷启动回退”测试包含 1 条本人历史，恰好避开该分支。

**修正：**把“本人历史不足”与“选中的群体基线可用”分开表达；仍可附带冷启动不确定性，不能因此丢弃满足要求的群体证据。

**失败验证：**`test_complete_cohort_baseline_usable_for_zero_history_user`。

### F13 [P2] 核心把陈旧、缺失的特征重新标为 OK

**代码：**`backend/export_risk/judgment/core.py:98–109`。

核心只取 feature_snapshot.values，忽略 quality、missing、as_of_time、水位与当前请求计入标记，融合返回时固定传 QualityState.OK。缺失特征在融合中被跳过，陈旧的低计数因此可能形成 allow，并被错误解释为输入质量正常。

**复现：**输入 quality=STALE、missing 含 req_count_long 的快照，经 B-v1 判断，返回 input_quality=OK。是否必须 defer 可以由批准的降级政策决定，但把已知陈旧信息改写成 OK 本身就是错误。

**修正：**保留并校验输入质量与时效，在必要特征缺失时按明确政策处理，将不可用分量与已确认的正常分量区分；不要让模型缺失的通用 uncertainty 文本替代真实输入质量。

**失败验证：**`test_core_preserves_stale_feature_quality`。

## 对主动披露问题的核验

- **真实 PG 未运行：**披露正确，本轮继续记未验证。22 项额外检查不模拟数据库行锁；上述失败均不依赖竞争才能复现。
- **C 臂无学习模型：**代码确实是注入分数或鲁棒偏离聚合。可以交付统计基线，但不能用 B↔C 证明训练模型增益。无需把 sklearn 的缺席重复报成新漏洞。
- **H1/H2：**当前 comparison.py 明确 H2 是合成数据上的描述性比较，没有把它写成有统计功效的不劣检验；这一表述可以接受。
- **偏离注入：**内置 baseline_observations 是固定的历史值，未发现直接把当前标签作为模型输入。它仍是人为设定的机制演示；F9 所示的迟到过滤缺陷需要独立修复。
- **outbox 故障安全：**补做了作者尚未做的故障注入。写入台账后、保存 sent 前抛异常，两者一起回滚，重试后只出现一条台账记录。这个检查通过；多进程并发仍待真实 PG 验证。
- **核心零查询：**补充代表性 assertNumQueries(0) 通过。这不是证明所有未来路径无副作用。
- **AST“有牙”反例：**`test_scanner_finds_at_least_the_core` 只断言扫描文件列表包含 core.py 与 hard_constraints.py，并未喂入故意违规的代码验证扫描器。交接说明 §4 的对应描述应收窄。
- **义务白名单：**拒绝未知类型是合理保守策略，当前 allow 且无义务的路径有通过测试。真正尚缺的是可信执行方的能力与参数/计划绑定，不能把一个静态类型集合说成完整执行能力协商。
- **既有审计链边界：**交接材料没有继续将其夸大为防删除设施；无需为本轮重复要求重构 audit。

## 交付范围与声明仍需收紧

以下作为交付缺口单独记录，不混入上面的 13 项反例：

1. **M5 实际只有 4 个内置场景。** `experiments/scenarios.py:123–124` 返回 normal_bulk、continuous_batch、unapproved_recipient、new_account；方案 §15 第 465 行“10 类场景”不成立。高敏感对照、撤权、审批到期、画像不足、并发额度、事件乱序/缺失等没有形成完整实验场景集。
2. **回放没有交付/配额状态更新。** `replay.py:43–60` 累积输入事件，每步 deliveries 都传空列表，动作不更新额度或交付状态。它是行为输入序列上的判断回放，不是已经兑现方案 I5 全部要求的执行状态闭环模拟。
3. **D 臂没有业务上下文判定分支。** purpose/business_task_id 只有契约/存储，没有可信任务匹配、用途授权或任务有效期参与融合的实现。D-v1 当前主要是累计、异常与敏感性叠加，应按这一范围陈述。
4. **审计与回放快照链不完整。** create_risk_decision 把 assessment.request_id 写作 assessment_id，但没有持久化对应 assessment、具体特征/授权快照、原因和证据。policy_hash/registry_fingerprint 函数存在不等于实际决策已使用内容哈希绑定：当前调用主要在测试中，决定只存版本字符串。真实模型工件未钉版的披露正确，政策/输入追溯能力也需同样收窄。
5. **生命周期事件与领取凭证未完整实现。** invalidate/revoke 未发对应失效事件；claim 只返回布尔值，consume 不使用执行结果引用，也没有 claiming 结果未知后的恢复端口。这些与方案 §14.1 的完整契约仍有距离。

## 修复与复核顺序

1. 先修 F1–F5，保证判断、持久化、准备与领取之间的主体、来源、时效、请求及决定绑定一致。首次调用和幂等重放都走完整检查。
2. 修 F6–F8，完善配额幂等参数校验、未知结果核对与数量异常处理。
3. 修 F9–F13，统一双时间过滤、事件/环境选择、冷启动回退及输入质量传播。
4. 将相应反例转入正式测试集；保留 outbox 故障注入和零查询两个正向检查。
5. 在独立真实 PG 上验证首次创建桶、相同/不同幂等键竞争、单授权双领取、领取与撤销/到期/释放竞争、outbox 多消费者及故障恢复。采用有时限的同步与独立连接，不能仅删除 skip 标记后继续使用 SQLite。
6. 同步交接与方案的能力范围、场景数和测试口径；保留真实来源未接入、C 无训练模型等已准确披露的限制。

修复前不建议关闭上一轮 R1（授权生命周期）、R2（配额恢复）、R3（生产准入）；R4 的共同基础保护和 R6 的本地 outbox 原子追加已有实质改善，应保留这些正确改动。
