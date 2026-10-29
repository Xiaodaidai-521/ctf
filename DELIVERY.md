# 模块五首期交付登记

日期：2026-10-29。工作区 `/home/hatch/workspace/ctf-module5`，分支 `feat/module5-practical-training`，基底 dc997fe。未 commit、未 push；未修改主检出或模块八 worktree。

**阅读口径：§1–6 保留首轮交付时的历史状态；第二轮实际补做结果和当前仍开放事项见 §7。首轮“未运行”及 48 项/686 项统计不是第二轮最终状态。**

## 1. 完成状态与边界

| 项目 | 状态 | 证据/边界 |
|---|---|---|
| 方案与代码核查 | 完成 | PROGRESS.md，按顺序读四份 brief 并核对实际契约 |
| 5-1 挑战映射与流程 | 代码、本地测试完成 | 既有 Juice Shop 挑战 → 模块一任务/尝试；静态材料、AUP、范围与时段、四级提示 |
| 5-2 服务端证据与回传 | 代码、契约测试完成 | 固定服务端挑战 API、未解出基线、来源/版本绑定、去重/冲突、模块六结果与模块一事实 |
| 5-3 修复独立复核 | 代码、本地执行测试完成 | 解释/声明式方案先冻结；独立运行 20 项合成访问测试；模块六新场景复测关联；未复核/不通过不完成 |
| 5-4 平台隔离与生命周期 | 代码、本地测试完成 | 本人/教师鉴权、审核快照、环境登记、暂停/隔离/重置/到期、资源/时限校验与审计 |
| 全模型停用演练 | 本地契约链路通过 | 禁外连 socket 白名单 + 模型边界断言，模型调用 0；真实本地策略执行 |
| 真实 Juice Shop 联调 | **未运行** | 本地 HTTP 服务为合成 fixture，不是真实镜像 |
| 实例/真实网络隔离 | **未证明，不放行** | 默认关闭；运维验收登记不等于隔离实测 |
| 课程教师签收、正式开放 | **未完成** | seed 只创建草案，不能自动发布或填造人工确认 |
| 全量回归 | **完整结束，未全绿；与给定基线相比无新增回归** | 686 发现 / 669 通过 / 11 skip / 5 FAIL / 1 ERROR，见 §5 |

“修复通过”仅指提交的访问控制方案在指定合成新场景中通过独立验证；**没有宣称在线修补 Juice Shop 或生产系统**。原理解释已保存但不自动评分；即时修复复测不冒充三天/七天的延迟保持测量。

## 2. 修改文件清单

代码变更仅涉及本应用及两个公共注册点；另更新交付文档并保留测试证据：

- `backend/ctf_backend/settings.py`：仅添加 `'practical_training'`。
- `backend/ctf_backend/urls.py`：仅添加 `/api/practical-training/` include。
- `backend/practical_training/__init__.py`
- `backend/practical_training/models.py`：映射、环境验收、平台分配、来源证据、修复主张；无新任务目录/成绩/事件系统。
- `backend/practical_training/migrations/0001_initial.py`、`0002_challengemapping_review_hash.py`、`migrations/__init__.py`。
- `backend/practical_training/curriculum.py`：原创候选知识、四级卡片、合成新场景说明。
- `backend/practical_training/policy.py`：默认拒绝外连/跨域策略、资源配置、实例来源绑定。
- `backend/practical_training/services.py`：映射/快照校验、分配、提示契约与鉴权。
- `backend/practical_training/verifiers.py`：固定 Juice API 观察器、合成方案重执行验证器。
- `backend/practical_training/evidence.py`：未解出基线、证据幂等、来源绑定与故障状态。
- `backend/practical_training/handoff.py`、`delivery.py`：模块六结果/通知契约、模块一事实回传、固定 payload 重试、复测关联。
- `backend/practical_training/repairs.py`、`review.py`：主张冻结/独立复核，写模块六复盘卡。
- `backend/practical_training/lifecycle.py`：教师审核/控制、到期与运行时清理回执对账。
- `backend/practical_training/views.py`、`urls.py`：既有 DRF 认证下的学生/教师 API 入口。
- `backend/practical_training/management/commands/{seed_practical_training,expire_practical_training,retry_practical_delivery}.py`。
- `backend/practical_training/tests.py`、`test_lifecycle.py`、`test_acceptance.py`：48 个新增自动测试。
- `backend/practical_training/README.md`：配置、迁移、接口、使用、边界与运维步骤。
- 根目录 `PROGRESS.md`、`DELIVERY.md`。
- `evidence/module5/final-code-sha256.json`：最终测试版本的源码哈希清单（未被忽略、未暂存）；同目录运行日志被忽略。

没有改模块一、二、六、七的代码、迁移或原生接口，没有修改既有 challenges proxy。未新增第三方依赖。

## 3. 必要迁移及配置

后端使用既有 venv，执行 `python manage.py migrate --noinput` 应用模块五的 0001/0002。部署需已有模块一/六和 ChallengeContainer 表。独立临时 SQLite 数据库的全迁移及 makemigrations/check 验证均已通过，实际结果见 §5。

配置在本应用读取，公共 settings 没有新增配置块：

- `PRACTICAL_TRAINING_ENABLED`：默认 false，只有完成真实验收才能开启。
- `PRACTICAL_TRAINING_VERIFIER_IP`：默认 127.0.0.1，固定 IP + 既有 JUICE_SHOP 专用端口范围，不接受学生 URL。
- `PRACTICAL_TRAINING_POLICY_JSON`：默认策略覆盖；同名 Django setting 的配置优先（策略 setting 名为 PRACTICAL_TRAINING_POLICY）。默认 1 CPU / 768 MiB / 256 PID / 3600 秒 / 每人 1 份占用；禁止放宽默认网络拒绝。
- `seed_practical_training --catalog <版本> --capability <ID>`：复用目录，创建草案，不签收、不冻结、不伪造环境。
- 每分钟调度 `expire_practical_training`，配合既有 `cleanup_containers`；不引入新调度组件。
- `retry_practical_delivery` 重试模块五 DownstreamNotice，不重执行挑战/修复。

## 4. 接口与契约

详细 JSON/顺序见 `backend/practical_training/README.md`。

- 学生：模块一 claim → 模块五 mappings/id/claim → assignments/id/start → 静态材料/hints request/display → verify → repair 主张 → repair/id/verify → review。
- 查询：本人 assignments、evidence、repair；跨学生一律拒绝，教师可审阅。
- 教师：mapping review、mapping control pause/resume、environment approve、assignment control pause/resume/isolate；学生只可 reset 本人。
- 证据：任务/尝试/目录/验证器版本、用户、容器、challenge key、时间、source/content hash；学生自报仅辅助，不产生通过。
- 修复：方案主张与服务器重执行分开保存；未核验不完成。结果写既有模块六 VerificationResult 和 RetestAssignment，再回传模块一。
- 状态：allocated → active；教师 paused/resume；isolated 不可直接恢复；reset/expired 关闭旧授权。审计保留原因及实际状态，不记录完整答案/凭证。
- `physical_cleanup=pending_operator` 明确表示仅平台授权回收；仍占资源额度。到期但未完成状态对账的非终态分配也保留额度。只有既有运行时 stopped/destroyed + destroyed_at + 空 access_url 回执齐全才标 confirmed_by_runtime。
- 暂停映射允许教师重新审核材料，但审核不会自动恢复；恢复需显式 resume，过期审核哈希仍阻止恢复。

### 实际代码差异的处理

模块六通用 server_verifier 尚未接通；部分提示/事实/复测/复盘事件 ID 超长、UUID 重试与 unknown 复测边界不满足本次约束。**未修改共享模块**：本应用使用模块六既有 AssistanceRecord、SubmissionSnapshot、VerificationResult、RetestAssignment、ReviewCard、DownstreamNotice 持久化契约，生成有界事件/事实 ID；复用 assistance_snapshot、compute_overall、show_hint、schedule_retest、claim_retest。最终事实由本应用适配模块一 ingest_verification_fact，不再使用原 dispatch_result/apply_result_to_assignment。失败通知保留固定 payload、时间和 UUID 类型重试；unknown 不计为独立复测通过。没有复制另一个成绩系统或事件库。

## 5. 实际命令、测试与基线对账

所有有效测试都在 `/home/hatch/workspace/ctf-module5/backend`，使用 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python`。

临时 SQLite 检查实际命令（输出合并至 `evidence/module5/migrations.log`）：

```sh
scratch=$(mktemp -d /tmp/module5-migrate-XXXXXX)
DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH="$scratch/db.sqlite3" /home/hatch/workspace/ctf-venv/bin/python -u manage.py migrate --noinput
DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH="$scratch/db.sqlite3" /home/hatch/workspace/ctf-venv/bin/python manage.py makemigrations --check --dry-run
DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH="$scratch/db.sqlite3" /home/hatch/workspace/ctf-venv/bin/python manage.py check
```

最终测试开始时的 25 份 Python 源文件 SHA-256 已保存于 `evidence/module5/final-code-sha256.json`；用于核对运行期间业务代码未变更。

| 运行 | 实际结果 | 证据 |
|---|---|---|
| `manage.py test practical_training.tests.MappingTests --noinput` | 9 / 9 通过 | `evidence/module5/wp5-1.log` |
| `manage.py test practical_training.tests --noinput`（5-2） | 18 / 18 通过 | `wp5-2.log` |
| `-u manage.py test practical_training.tests skill_review.tests learning_map.tests --noinput --verbosity 2`（完整重跑） | 94 / 94 通过，529.858 秒 | `wp5-3-complete.log` |
| 首轮 5-4 | 44 发现、43 通过、1 FAIL（事件 ID 超长） | `wp5-4.log`；已修复适配器并重跑 |
| `-u manage.py test practical_training --noinput --verbosity 2`（修复后） | 46 / 46 通过，11.515 秒 | `wp5-4-final.log` |
| 生命周期追加补测（额度修正前） | 2 项：暂停审核通过；到期未对账的额度检查 1 FAIL，已修正 | `lifecycle-edge-before.log` |
| `-u manage.py test practical_training --noinput --verbosity 2`（最终代码） | **48 / 48 通过，24.489 秒，退出码 0** | `wp5-final-48.log:166–168` |
| `-u manage.py test --noinput --verbosity 2`（最终代码） | **686 发现/运行、669 通过、11 skip、5 FAIL、1 ERROR；1977.955 秒，退出码 1** | `full-suite-final.log:955–958`，后台时限 7200 秒，完整结束 |
| 临时 SQLite：`migrate --noinput`、`makemigrations --check --dry-run`、`check` | 全部通过；0001/0002 应用成功，No changes detected，0 issues；退出码 0 | `migrations.log:80–81,107–108` |
| `git diff --check` | 通过 | 实际命令无错误输出 |

对照用户提供的 dc997fe 基线：**638 发现、621 通过、11 skip、5 FAIL、1 ERROR**。本次完整运行为 **686 / 669 / 11 / 5 / 1**；差异为 **+48 发现、+48 通过**，其余数量不变。全量日志中 48 个模块五测试逐项为 ok，25 份最终 Python 源文件哈希与启动时一致。**全量未全绿，但未新增失败/错误，保留的问题与给定基线吻合。**

保留的失败/错误逐项核对如下（均未修改其所属代码）：

| 类型 | 测试（类/模块） | 实际失败 | 全量日志行 |
|---|---|---|---|
| FAIL | `ChallengeProxyAccessTests.test_access_url_does_not_include_reusable_token` | URL 仍包含 access_token | 897–905 |
| FAIL | `ChallengeProxyAccessTests.test_proxy_accepts_authenticated_owner_without_cookie` | 401 ≠ 200 | 908–916 |
| FAIL | `ChallengeProxyAccessTests.test_proxy_rejects_authenticated_non_owner` | 401 ≠ 403 | 919–927 |
| FAIL | `ChallengeProxyAccessTests.test_proxy_rejects_unsafe_session_request_without_csrf` | 401 ≠ 403 | 930–938 |
| FAIL | `mainline1.tests.test_semantic.SemanticTests.test_real_transport_constructor_pins_options_without_provider_registry` | ai_providers 已存在于 sys.modules | 941–952 |
| ERROR | `mainline1.test_settings`（unittest loader） | KeyError: MAINLINE1_TEST_PORT | 880–893 |

前四项均位于 `challenges.tests`；未增加新的 proxy 相关失败。11 项 skip 保持保留，不算通过。

无效/中断运行均不计入通过：根目录 `python backend/manage.py test` 发现 0；首次全量在 600 秒上限被杀；两次 5-3 中断扩大回归。原日志保留，后续完整 `wp5-3-complete.log` 才是该包结果。`full-suite.log` 在发现暂停审核/到期额度边界后主动停止，不计通过；最终代码以 `full-suite-final.log` 为准。

日志是本地运行产物，`evidence/module5/*.log` 被仓库 ignore 规则排除，**仍在 worktree 磁盘中**；交接需另存，不应假定未来提交会带上日志。

## 6. 未运行项目与剩余依赖

1. **真实 Juice Shop 镜像/API 联调**：固定现有 v20.2.0 镜像，实际 challenge key/API 兼容性、真正解题后信号、环境重建/故障恢复须在部署靶场验证。本地仅 HTTP fixture 及契约测试。
2. **真实身份/实例/网络隔离**：既有 Juice Shop 直连端口没有平台身份门，bridge 可外连；需网关/VPN 身份控制和默认拒绝出站、宿主控制面/内网/生产/其他学生 ACL 实测。平台 paused/isolated 不能证明直连端口已断开。未验收不得对学生开放。
3. **真实资源和回收**：CPU/内存/PID 实际强制、到期停止/删除、旧地址与凭证不可用、清理调度运行证据仍待部署验收。配置校验和模拟运行时回执测试不替代实测。
4. **课程人工审核**：能力/知识点映射、WSTG 选材转译、四级提示、解释评价口径、新场景修复题需签收。种子数据是候选，未自动签收。
5. **真实延迟复测**：本次修复是即时新场景重执行，没有真实三天/七天保持观察。
6. **目标 PostgreSQL 并发验收**：本地 SQLite 验证事务回滚、重复/冲突、权限与状态；目标数据库多进程竞争须另测。
7. **既有挑战代理问题**：不修复 4 个预存 proxy FAIL。本模块固定服务端读取不依赖通用代理；旧自由练习入口和直连安全边界仍须单独治理。

没有真实靶场执行/隔离证据的部分未写成通过。未安装新依赖，未引入新平台组件，未触及模块四或受控执行里程碑 I。

## 7. 保留项补做（第二轮）

日期：2026-10-29。逐项补做 §6 的保留工作；实际过程追加在 `PROGRESS.md`，证据均放 `evidence/module5/`，第二轮文件使用 `r2` 前缀。原失败/中断日志保留，不以成功运行覆盖失败结论。

### 7.1 七项状态总表

| 保留项 | 已实测通过 | 已备好待人工 | 仍开放及原因 |
|---|---|---|---|
| 1. 真实 Juice Shop | 官方 v20.2.0 Node 24 发行包真实启动；两实例未解基线；B 经真实 HTTP 解题；原 reader 读 B=true/A=false；来源证据及模块六结果/模块一事实正确归属 | — | 未运行 Docker 镜像；生产准入刻意关闭，未冒充 claim/start/verify 全链路上线；生产重建/恢复仍须部署验收 |
| 2. 身份/实例/网络隔离 | 每学生独立进程/数据/chroot/user-mount-PID-net namespace/端口；真实平台 HTTP 地址归属门；匿名/他人拒绝；本机自身可达、对方/宿主 canary 不可达、无外连路由 | 可供运维复核的原始控制读数 | 不是多宿主网关/VPN；无独立宿主 UID；可信宿主 root/内部 observer 端口不在学生进程边界内；既有直连入口未改 |
| 3. 资源/回收 | Node 2 GiB RLIMIT_AS、256 FD、单核 affinity 回读；地址空间分配失败探针；真实时钟到期停进程、端口拒绝、测试 Token 撤销、物理回执对账 | — | system bus/cgroup 委派不足，**768 MiB RSS、CPU 带宽、256 PID 聚合限额未证明**；不是生产常驻清理/故障恢复验收 |
| 4. 课程人工审核 | 送审包静态完整性检查，不是人工签收 | `docs/module5-r2-course-signoff.md` v1.1，映射/WSTG/四级提示/解释口径/种子评审表；签名/日期/结论留空 | 课程负责人须审核语义、提示、新场景、资料和评分口径；不得代签或自动冻结开放 |
| 5. 三天/七天复测 | 真实解出基线、模块六 pending_item 分配、未来 UTC 计划已落盘；两次资格检查均 correctly awaiting_real_time | tentative ICS 文件待人工导入；只读检查脚本与执行步骤 | 真实时间未经过；本次合成学生不是人类学习保持。须真实学习者自己的初测和延迟新证据；未安装调度 |
| 6. PostgreSQL 并发 | 私有 PG 16.13 + pgvector 0.8.1，全迁移、50 项模块五测试、5 组真双进程行锁/幂等、原生 SQL 数量/唯一约束检查 | — | 不扩大为压力/高可用/崩溃恢复或所有跨入口交错；PG 专项挑战来源是 HTTP fixture，不是真实 Juice |
| 7. 四个既存 proxy FAIL | 按要求未修改其他应用 | — | 原问题仍开放且不属本模块修复；第二轮未重跑全量，不对这些用例新增结果作推断 |

**结论：已完成本机可执行的真实验收与待人工材料；不等于七项生产条件全部关闭，不得据此正式对学生开放。**

### 7.2 实际应用兼容性问题及代码修正

真实官方 `/api/Challenges` 中 `Confidential Document` 的 key 为 **`directoryListingChallenge`**（本次真实记录 id=19），不是首轮 fixture 使用的 `confidentialDocumentChallenge`。旧 key 的固定 reader 实测拒绝，不把缺失项当成功；见 `r2-key-compatibility.log` 和真实 HTTP 记录。

修改范围：

- `backend/practical_training/models.py` 默认值、`services.py` 固定映射校验、`test_acceptance.py` fixtures/旧别名拒绝测试、`test_lifecycle.py` 旧映射重审测试。
- 新增 `migrations/0003_correct_juice_challenge_key.py`；未编辑原 0001，也不重写历史 ServerEvidence。
- 迁移将旧别名映射改为正确 key，**paused=true，清空 reviewed_by/reviewed_at/review_hash，要求教师重新审核和显式 resume**。反向迁移不恢复旧审批。已有分配不伪造重新签收，paused 会继续阻止操作。
- 固定 HTTP reader 算法未变；模块五测试从 48 增至 50。
- 新增 `scripts/module5_r2/` 一次性本机验收工具、`backend/scripts/r2_pg_*` 三个专用 PG 工具、课程送审文档与证据。未新增生产应用组件或修改共享模块行为。

课程包随真实接口勘误更新为 v1.1。原未签收包保留为 `r2-course-signoff-initial.md`；`r2-course-key-correction.json` 记录当前代码/文档摘要及实际 key。原 `r2-course-generation-manifest.json` / source snapshot 仅代表初始文档子任务，首轮 `final-code-sha256.json` 仅代表首轮测试版本，不能用它们证明第二轮代码未变化。

### 7.3 真实请求、归属与准入边界

发行包 SHA-256：`dbb457f74e908e28c41d7787e36d30d121d5b9f6178524720567b4aeb41f2968`，官方元数据/下载摘要一致。本机 Node v24.22.1；无 Docker，未安装应用 npm/Python 依赖。

28 次真实请求/响应保存在 `r2-http-*.json`（Authorization 脱敏），`r2-reader-observations.json` 保存实际 reader 输出。两实例先为 false；随后仅学生 B 经真实应用请求完成挑战，未直接改 Juice 数据库。真实观察与 source hash 进入现有持久化契约：

| 对照 | attempt | evidence | 结果 |
|---|---|---|---|
| A：另一个未解实例 | `b7d18b64-d810-4ff8-8322-4e20dd81459a` | `55c0b475-611f-4fd7-9cd5-53f07b5a05fe` | failed，没有被 B 的解题错误归属 |
| B：实际解题实例 | `6043cc2e-0720-46da-b170-741635f17837` | `69bd0d26-cd86-4309-a948-2ada8d00b1a8` | passed，绑定 B/任务版本/实际进程与端口 |

`r2-real-handoff.json` 含 assignment、student、task/version、catalog、发行包摘要、进程/端口、baseline、结果/事实 ID。最终真实验收 DB 为 2 evidence、2 result、2 fact，ModelCallRecord=0。

**不伪造人工签收：**该独立 DB 中 EnvironmentApproval=0、已审核 mapping=0，任务是 draft、environment_available=false，生产开关为 false；实际 start API 返回 400。运维驱动建立测试记录、记录实际基线，调用已有可信 persist_evidence/handoff，并经真实 HTTP 访问平台归属门。这证明真实 reader/证据契约/身份门集成，**不证明生产领取—启动—核验准入流程已经放行**。PG 专项的合成已审核 fixture/APIClient 强制身份只作测试，不是人工签收或生产认证证据。

### 7.4 宿主控制与真实清理证据

- 实际 user/mount/PID/net namespace 两套 ID 不同，各自只启用 loopback；独立 chroot 不暴露宿主 home/proc，应用 CapEff=0、NoNewPrivs=1。宿主只读 `/usr` 绑定和最小设备只服务此次隔离运行。
- 内部 Node 端口 A/B=18211/18212；宿主学生网关=18411/18412，observer=18111/18112。学生网关每次咨询真实平台身份/状态，未知/匿名/他人拒绝；它只实现此次所需 GET，不是通用生产代理。
- 两个已启动实例实测自身端口可达、对方 loopback errno=111、宿主控制面 canary errno=111，而宿主侧 canary HTTP=200；内网/文档保留地址/互联网/IPv6 探测拒绝或无路由。这不是连接真实生产地址测试，也不代表已装生产防火墙规则。
- 两个 Node 均回读 RLIMIT_AS=2147483648、RLIMIT_NOFILE=256、CPU affinity=0；heap 参数 256 MiB，分配探针产生 MemoryError。Max processes 实际 27153，**不能写成 256 PID 限额成功**。
- systemd-run 无 system bus、cgroup 无 cpu/memory/pids 委派、iptables 缺 CAP_NET_ADMIN、独立宿主 UID 映射及新 proc 挂载失败均保留。初次 768 MiB 虚拟空间上限导致真实 V8 启动 OOM；最终 2 GiB AS 限额是明确不同控制，不可冒充 768 MiB RSS。
- 到期时刻 `2026-10-29T05:45:55.132677+00:00`，控制器按真实时钟停捕获的进程组并关闭监听。驱动确认所有捕获后代 PID 消失、学生/observer 端口连接拒绝，旧测试 Token 撤销后平台拒绝；随后才记录 destroyed 回执，两个 assignment 均 expired + confirmed_by_runtime。

证据：`r2-student-*-isolation.json`、`r2-student-*-live-controls.json`、`r2-runtime-cleanup.json`、`r2-post-cleanup-db.json`、`r2-live-acceptance.log`。先前失败位于 `r2-attempt1-*`、`r2-attempt2-*` 等日志；不计通过。本次 Juice 与临时平台服务已停止，原始文件保留。

### 7.5 人工送审与真实延迟观察

送审包：`docs/module5-r2-course-signoff.md`。覆盖能力/知识点映射、WSTG 选材与转译、四级提示、解释评审、新场景修复和发布/冻结/重审步骤；不包含完整题解，审核签名/日期/结论全部空白。已指出种子目前原题/修复题共享提示、解释仅存储不自动评分、seed 不生成 WSTG 转译记录等待审问题。修改 JSON 不会自动新增人工评分闸门。

真实 B passed 观察时间为 `2026-10-29T05:45:42.991558+00:00`。其基线 DB 保留于 `evidence/module5/r2-live-corrected-60T78i.sqlite3`；计划 `r2-delayed-retest-plan.json` 绑定原 attempt/evidence/result/fact，模块六 retest `8a06c519-b88c-447d-bf28-dcda38e2445b` 为 pending_item。

| 观察点 | 最早真实 UTC 时间 | 当前结果 |
|---|---|---|
| day3 | 2026-11-01T05:45:42.991558+00:00 | awaiting_real_time；retention_proven=false |
| day7 | 2026-11-05T05:45:42.991558+00:00 | awaiting_real_time；retention_proven=false |

两次检查有 `r2-day3-eligibility.log`、`r2-day7-eligibility.log`。`r2-delayed-retest-calendar.ics` 仅待人工导入，没有外部发布或自动调度。到期也必须另有教师签收的新任务/环境、全新未解实例、相同学习者的新关联尝试及服务端证据。当前账号是操作者驱动的合成学生，不能成为人的保持测量；**真实学习者需要自己的真实初测基线与对应等待期**，不能继承该合成账号的通过记录或复用已解状态。

### 7.6 PostgreSQL 实际验收

私有安装 PostgreSQL 16.13 + pgvector 0.8.1，未更改系统服务、共享库或 venv。PG 官方源码摘要核对一致；pgvector 下载摘要已留档但不声称签名验证。最初缺 vector 扩展导致真实全迁移失败，补齐私有扩展后成功，未 fake/跳过共享迁移。

专用集群 `127.0.0.1:55465`，数据库 `module5_r2`，read committed、fsync=on。临时 trust 仅适用于本机验收，不是生产认证配置。完整构建/命令/依赖位置及停服证据见 `r2-pg-report.md`。

5 组各两个独立进程真实竞争如下；每组都保存父锁和释放后的 worker 相互阻塞快照，PG 服务器另记录 947.417ms、506.623ms 等等待：

| 场景 | 实际响应 | 结果 |
|---|---|---|
| 挑战同 key | 201 / 200 | 同 evidence/result/submission，只核验一次 |
| 重复修复主张 | 201 / 200 | 同 claim/attempt/retest，唯一冻结主张 |
| 修复同 key 异内容 | 200 / 400 | 原内容重放成功，冲突拒绝 |
| 修复核验同 key | 201 / 200 | 同 evidence/result，复测完成一次 |
| 已提交挑战使用新 key | 400 / 400 | 不新增结果，不重读上游 |

原生 psql 只读快照确认 evidence/submission/result/fact/notice 各 2，claim/retest 各 1，重复 evidence key 和 first_effective attempt 均 0；真实唯一约束亦有查询记录。HTTP fixture 共两次请求（基线+核验），不宣称这是真实 Juice 或生产认证测试；修复仍为 20 项真实执行的合成策略案例。

核心证据：`r2-pg-tests-final.log`、`r2-pg-concurrency-results.json`、`r2-pg-*-locks.json`、`r2-pg-*-sql.log`、`r2-pg-server.log`、`r2-pg-sql-results.log`。并发范围限定于上述五组，不是泛化并发正确性或高可用证明。

### 7.7 第二轮命令与回归结果

真实 Juice/平台/驱动的精确命令、端口、目录、停止方法和只读延迟检查见 `scripts/module5_r2/README.md`；PG 构建/运行/SQL 命令见 `r2-pg-report.md`。重跑前须先保留现有证据，使用全新专用 DB，不能直接覆盖真实基线。

SQLite 受影响回归（cwd=`/home/hatch/workspace/ctf-module5/backend`）：

```sh
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python -u manage.py test practical_training skill_review.tests learning_map.tests --noinput --verbosity 2
```

| 实际运行 | 结果 | 证据 |
|---|---|---|
| 独立 SQLite 全迁移 + makemigrations --check --dry-run | 含 0003 成功；No changes detected；退出 0 | `r2-live-corrected-migrations.log:80–82,108` |
| SQLite 模块五 + 受影响模块一/六 | **119/119 通过，187.525 秒，退出 0**：50 模块五 + 69 既存 | `r2-regression.log:240–242` |
| PG 全迁移 + 本应用迁移检查 | 0001–0003 应用成功，无待生成迁移 | `r2-pg-migrate-final.log` |
| PG 模块五 label 套件（首次根目录 cwd） | 50/50 通过，14.893 秒；保留原结果但另补 backend 入口复验 | `r2-pg-tests-final.log:169–172` |
| PG 模块五套件（最终 backend cwd） | **50/50 通过，9.246 秒，退出 0**；测试库删除 | `r2-pg-tests-backend.log:1,170–173` |
| PG 五组双进程并发/原生 SQL | 全部断言通过，真实等待/无重复结果 | `r2-pg-concurrency-results.json`、`r2-pg-sql-results.log` |
| 真实 Juice reader/归属与实际到期回收 | 两个 PASS 标记，实际驱动退出 0 | `r2-live-acceptance.log`、`r2-live-summary.json` |
| day3/day7 只读资格检查 | 两项均尚未到期；**不是保持通过** | `r2-day3-eligibility.log`、`r2-day7-eligibility.log` |

**第二轮未重跑全量。**§5 的 686/669/11/5/1 仅是首轮完整结果；当前不能外推成 688 项已运行或全量全绿。四个 proxy FAIL 及其他既有基线问题没有修复，未改变模块一/二/六/七原生接口和行为。

### 7.8 依赖、证据交接与当前开放条件

第二轮新增的执行依赖仅为本地测试所需的官方预编译 Juice 包及私有 PG/pgvector 工具；没有新增应用 Python/npm 依赖、系统常驻组件、LangGraph 或生产调度。资源/身份验收脚本为临时设施，不能被误部署成正式运行时。

HTTP 附件含实际应用响应与解题相关材料；认证头已脱敏，测试 Token 已撤销，但附件仍应作为受控验收资料，不公开给学生、不送模型、不自动上传。SQLite 保存合成账号及真实证据关联。`.log` / SQLite 可能被 gitignore 排除，必须另行保留磁盘证据；不应假设未来提交自动包含这些文件。

目前必须继续保留的门槛：人工课程签收、真实学习者三天/七天观察、生产 CPU/RSS/PID 聚合限额、正式身份网关/多宿主边界及生产运行时清理/恢复验收。原平台开关维持默认关闭。**未 commit、未 push；不修改主检出或模块八 worktree。**

### 7.9 最终收尾核查

- PG 最后一次以 backend cwd 重跑 50/50 后再次停服；`r2-pg-shutdown-backend.log` / `r2-pg-status-backend.log` 为最新停服证据（server stopped、pg_ctl=3、55465/58165 无监听）。无需重跑之前已完成的真实并发；最终业务代码未变。
- `r2-final-local-checks.log` 保存分支/基底、变更范围、公共注册各一行、未暂存、`git diff --check`、31 份 Python/一个 shell 语法检查、核心测试代码与课程勘误摘要一致、HTTP 认证脱敏、Juice/平台端口拒绝等结果。语法/文件检查不是额外单元测试统计。
- 最后宿主端口/本人启动的残留进程核查记入 `r2-final-runtime-checks.json`；本地文件与证据摘要清单为 `r2-evidence-sha256.json`，用于受控交接核对，不是人工签名或生产认证证明。失败运行的历史 DB/日志仍保留；成功验收 DB 的 Token 撤销不泛指所有历史文件已被清空。
