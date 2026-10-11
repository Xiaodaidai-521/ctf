# 主线二 F1–F13 修复复核

日期：2026-10-11。对象：`E:\xianmu\ctf` 工作区的未提交修复，基线提交 `b978b8d7efaf6b1263d2a16c3aa87974b9ad6e5f`。

## 结论

**原 22 条保护测试确实全部通过，但不足以关闭全部 13 项发现。** 补充同类边界后，仍有 **2 项 P1、3 项 P2**。以下均有顺序执行的确定性反例，不依赖 PostgreSQL 并发环境，也不是要求补做已延期的五项交付功能。

原 F4/F5/F6 的来源、评估绑定、配额绑定修复，以及 F8/F9/F10/F11/F12 的原发现，可以按本次核验范围关闭。F1/F2/F3/F7/F13 的原始反例已消失，但仍有下面的边界未覆盖，应标为部分修复。此结论不等于其他模块或全部输入组合已经通过穷尽验证。

本轮未修改业务源码、作者测试、原审查脚本或历史结果；只新增本报告、补充脚本和两份结果文件。独立反例使用 SQLite `:memory:`，没有使用真实业务数据库、PGDATA 或 dump。

## 独立验证结果

| 验证 | 实际结果 |
|---|---|
| 原审查脚本（文件未修改） | 22 通过，0 失败，0 错误 |
| 两 app 测试 | Ran 90：89 通过，1 跳过 |
| 六 app 回归 | Ran 205：196 通过，9 跳过 |
| 新增边界保护测试 | Ran 12：11 失败，1 正向控制通过，0 错误 |
| `check` | 零问题 |
| `makemigrations --check --dry-run` | No changes detected |
| 真实 PG 并发 | 本轮未运行，仍未验证 |

六 app 日志包含既有 fallback、SQLite table locked 告警，但运行结果成功。首次直接运行迁移检查出现默认库无法打开的历史一致性检查警告；随后显式将数据库覆盖为内存 SQLite，重新执行 check 和迁移漂移检查，均通过且无该警告。这个结果只证明模型/迁移文件无漂移，不证明真实数据库迁移历史完整。

修复说明 `E:\xianmu\ctf\docs\mainline2-remediation.md` 已正确写明 89/196 的实际通过数；聊天中的“90通过 / 205通过”不应重复用于验收统计。

## R1 [P1] 当前权限范围收紧后，首次准备和重放仍可签发（原 F1）

位置：`E:\xianmu\ctf\backend\export_risk\decisions\service.py:105–128`，尤其 110–112 行的“不重新检查 envelope”说明。

**复现：**先用正常授权生成 allow 决定；请求本身完全不变，新授权仍为同主体、未过期、AUTHORIZED，但分别清空 `allowed_scope`、`allowed_operations`、`allowed_recipients`。三个首次 prepare 都返回 executable。已经 prepare 成功后，再撤去允许的接收者，同键重放也返回 executable。

对同一份收紧后的授权重新调用纯核心，结果都是 deny，说明不是测试误解 AUTHORIZED 的语义：它还必须受允许名单约束。请求指纹证明请求没有变化，**不能证明当前权限没有变化**。

**修正：**首次和重放共用完整的当前权限校验，至少复用硬约束对主体/范围/操作/接收者的判定，并保留时效、来源和一致性检查。不要只检查总体结果从 AUTHORIZED 变为 FORBIDDEN 的撤销形式。

证据：`test_first_prepare_rejects_narrowed_scope`、`test_first_prepare_rejects_narrowed_operations`、`test_first_prepare_rejects_narrowed_recipients`、`test_replay_rejects_narrowed_recipient`，4 条失败。

## R2 [P1] 执行许可仍可超过前置授权/预占的有效期，重放遗漏预占状态（原 F3）

位置：

- `E:\xianmu\ctf\backend\export_risk\decisions\service.py:263–267`：执行许可仅复制决定期限。
- 同文件 `:301–305`：claim 对预占只检查 state，不检查 `expires_at`。
- 同文件 `:144–161`：幂等复核不检查关联预占。
- 同文件 `:181`：返回契约的期限也取决定期限，而不是执行授权记录期限。
- `E:\xianmu\ctf\backend\export_quota\services.py:85–90`：reserve 的同键重放不检查预占期限。

**四条独立复现：**

1. 上游授权只剩 30 秒，决定默认有效 600 秒。正常 prepare 后推进到上游授权到期后 1 秒，claim 返回 True。签发时已经知道这个期限，却把执行许可延长到了决定期限。
2. 正常 quota prepare，默认预占 300 秒、决定 600 秒。推进到预占到期后 1 秒，数据库 state 尚为 reserved，claim 仍返回 True。这不需要调度器竞态或数据库并发。
3. prepare 后通过正常服务 release 预占，同键 prepare 重放仍返回 executable。此时独立 claim 会拒绝，所以这里**不声称已发生实际二次交付**，但可执行结果契约仍不正确。
4. 单独 reserve 后推进到 expires_at 之后，以相同绑定重放，仍作为有效预占成功返回。

**修正：**执行许可的有效上界应受已知前置授权、决定和预占等期限共同约束，返回契约也必须使用实际执行许可期限；claim、prepare 重放、reserve 重放均需按各自职责验证当前状态与期限。到期不等于可以把未知交付结果的额度直接释放，仍须保持保守核对/占用。数据库锁顺序及撤销/释放竞争需要另做真实 PG 验证，不能仅增加几个顺序检查后宣称并发闭环。

证据：`test_claim_does_not_outlive_known_authorization_grant`、`test_claim_rejects_expired_reservation`、`test_prepare_replay_rejects_released_reservation`、`test_reserve_replay_rejects_expired_reservation`，4 条失败。正向控制 `test_control_valid_claim_still_works` 通过，证明有效许可可领取且顺序重复领取被拒。

## R3 [P2] 全部时间不带时区时，纯层仍判授权有效（原 F2）

位置：`E:\xianmu\ctf\backend\export_risk\judgment\validity.py:18–28,41–54`。

当前只捕获 naive 与 aware 比较时的 TypeError。若 `evaluation_time`、`observed_at`、`valid_until` 全部不带时区，Python 比较可以成功，函数返回有效，纯核心 allow。ISO 解析成功不代表已经确定了绝对时间；这不符合方案的带时区契约，也与生产 prepare 对 naive 到期值的拒绝行为不一致。

**修正：**解析阶段显式要求参与比较的时间有有效 UTC offset；缺失时返回 validity unknown/defer，而不是等比较报错。保留注入时间和无时钟读取的实现方式。放行 datetime 的纯值解析本身合理，无需撤销这一设计。

证据：`test_core_rejects_all_naive_authorization_times`，实际 allow，预期 defer。

## R4 [P2] unknown 结清成功后，相同确认回执重试仍抛错（原 F7）

位置：`E:\xianmu\ctf\backend\export_quota\services.py:170–182`。

**复现：**reserve 60 → reconcile(None) → reconcile(40) 成功结清 → 同一确认值 reconcile(40) 重试，抛 `QuotaStateError: cannot reconcile from state committed`。

修复只让“重复未知结果”幂等，没有让“确认结清结果”幂等。工作进程在数据库提交后、确认消息之前故障或丢响应时，合法重投会一直报错。当前不会因此重复扣款，但恢复流程无法把已成功的处理识别为成功。上一轮 F7 修正建议已明确要求相同结果重试幂等。

**修正：**锁内识别 committed 且确认结果一致的重放，返回已完成结果、不再次记账；不同确认值显式冲突。未来接入回执标识时再增加不可变回执绑定，不必为本次修复扩建整套执行闭环。

证据：`test_confirmed_reconcile_retry_is_idempotent`。

## R5 [P2] 整份特征快照缺失时仍返回 input_quality=OK（原 F13）

位置：`E:\xianmu\ctf\backend\export_risk\judgment\core.py:109–120`，尤其 118 行。

对存在的快照透传 quality 已修正，但 `feature_snapshot=None` 的分支仍用 OK。该参数在接口中明确为 Optional，因此不是故意传入错误类型。使用依赖累计特征的 B-v1 且整份快照缺失时，融合取空字典、跳过全部累计阈值，最终返回 allow 和 input_quality=OK。

**修正：**根据政策的实际输入依赖标记 MISSING/不可用及相应原因，不能将未取得特征等同于观察到了零异常。是否强制 defer 仍应由明确的降级政策决定；不要求所有不依赖行为特征的基线政策一律拒绝 None。

证据：`test_absent_feature_snapshot_is_not_quality_ok`。

## 不计作新增缺陷的边界

- 四类场景、非执行闭环的回放、D 臂业务分支、完整快照证据链、完整生命周期事件/领取凭证，仍按已披露的后续里程碑处理。
- datetime 纯解析/比较不破坏纯函数设计；AST 扫描仍是工程护栏而非形式化证明。
- 真实 PG 并发继续记未验证。本轮的 11 个失败均不需要 PG；因此不能用唯一环境 Blocked 来解释或覆盖它们。
- 未接入真实来源/生产 owner 是原型限制，本报告没有据此推断匿名网络利用或真实业务数据已经泄露。

## 复现与交付

新增脚本：`E:\xianmu\ctf\docs\review-support\mainline2_remediation_probes.py`。

它复用原脚本的内存库配置、模型建表和结果输出函数，但不修改原脚本文件；本次执行的测试类单独定义。断言表达预期保护行为，退出码 1 代表反例仍成立。

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'E:\xianmu\.review-venv\Scripts\python.exe' 'E:\xianmu\ctf\docs\review-support\mainline2_handoff_probes.py'
& 'E:\xianmu\.review-venv\Scripts\python.exe' 'E:\xianmu\ctf\docs\review-support\mainline2_remediation_probes.py'
```

本轮原脚本结果：`E:\xianmu\ctf\docs\review-support\mainline2-remediation-original-results.json`。

补充边界结果：`E:\xianmu\ctf\docs\review-support\mainline2-remediation-boundary-results.json`。

建议先修 R1/R2，再补 R3–R5；同时保留原 22 条用例与新增边界用例。当前可接受“原反例均已修复、原型继续推进”，不可接受“13 项安全契约全部关闭”。
