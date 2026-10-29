# 模块五首期进展

## 2026-10-29 开工核查（实施前）

已按顺序阅读 `module5-brief/context.md`、`master-plan.md`、`nav-index.md`、`module6-plan-ref.md`。工作区为 `/home/hatch/workspace/ctf-module5`，分支 `feat/module5-practical-training`；初始状态仅 DELIVERY.md / PROGRESS.md 删除，按本次要求重新建立。禁止 commit/push，不访问主检出与模块八 worktree。

### 实际代码与方案差异

- `challenges.Challenge` 有 practice 模式、TaskPackage 已有 challenge FK；复用这些对象，不另建任务目录。
- `challenges.juice_shop.JuiceShopRuntime` 固定 Juice Shop v20.2.0 镜像摘要，按用户独立容器/bridge/端口，1 CPU / 768 MiB / 256 PID，有启停/到期清理和审计；不是成果同步器。
- Juice Shop 是直连端口，绕过通用 challenge proxy；现有 bridge 允许出站、直连无平台身份校验。不能把配置存在当作网络隔离实证。模块五默认关闭真实靶场放行，保留教师部署前验收依赖。不修改既有自由练习入口/4 个 proxy 基线失败。
- 模块一已有 TaskPackage/TaskAttempt/VerificationFact 与统一事件。TaskPackage 关联能力、知识点通过能力目录解析；发布/冻结、先修与材料约束复用现有口径。
- 模块六实际是 SubmissionSnapshot → VerificationResult → dispatch_result → 模块一 ingest_verification_fact；没有 VerificationRun。`server_verifier/external/isolated_challenge` 在通用提交核验器中仍固定返回 `server_evidence_not_connected`。
- 因此新增应用通过模块六公开持久化模型及 assistance_snapshot、compute_overall、dispatch_result、retest 等服务做一个来源受限适配器，不修改模块六通用学生提交行为、不让学生 JSON 选择通过状态、不另建成绩表。
- 模块六首次有效提交规则不能由模块五覆盖；一次已提交尝试结果冻结，重新练习须新尝试。hint request/show 已分开，复用之。普通教师帮助 level=0 与模块一受助事实 1–4 级契约有既有差异；本期只使用四级卡片，不冒充已解决。
- 模块六复测必须 `schedule_retest` / `claim_retest` 才关联原尝试；现有选题不验证场景语义，模块五显式限定已审核的不同资源场景修复任务。方案的实际延迟测量不以即时测试冒充。
- 模块一与六重试有既有 UUID/时间戳等边界；模块五先按完整来源键和内容摘要去重，重复请求返回已存结果、不重复 dispatch；交接失败保留模块六 notice 待重试，不伪称成功。
- 模块二 data_export 的 module5/not_applicable 是既有占位；不改该动作或成绩状态，模块五以共享 task/attempt 对接。

### 实施计划与边界

1. **5-1 任务映射与流程**：新增 `practical_training` 应用；映射既有 Juice Shop `confidentialDocumentChallenge` 至已有目录下 TaskPackage；草案材料/四级卡片/目标/先修/验收/版本与课程审核入口。分配绑定 TaskAttempt、容器来源、目标端口、时段、AUP、资源/网络策略快照；只在冻结、审核、环境放行满足时领取。学生/教师读取边界。
2. **5-2 服务端证据**：只向服务端登记的该用户 Juice Shop 实例读取固定挑战 API，不接受客户端 URL/solved/验证器。记录服务端观察、来源与内容摘要、版本、故障状态；模块六适配器可靠写结果/事件并回传模块一。提示请求与交付分开。去重/冲突拒绝测试。
3. **5-3 修复复核**：已通过挑战产生模块六新场景复测分配；学生解释成因、提出结构化访问控制方案。提交主张不等于完成；独立 POST 复核在服务端重新执行固定合成访问测试，包括合法访问与拒绝越权。验证的是方案在合成场景中的行为，不宣称改写了 Juice Shop。结果经模块六复测契约关联原任务；复盘复用模块六。
4. **5-4 生命周期/教师控制**：平台资源、寿命、目标策略校验、重置/到期回收状态、教师暂停/隔离、异常审计。外部实例停用/网络隔离需真实运行证据，本环境无法完成则列出缺口，状态不伪装物理回收。
5. 每包跑定向测试并追加本文件；最后完整回归、迁移检查、无 AI 全链路测试，写 DELIVERY.md。

公共文件预计仅新增 `ctf_backend/settings.py` 中应用注册行、`ctf_backend/urls.py` 中 include 路由。配置默认值放本应用，不新增依赖、组件或 LangGraph。

### 测试基线与证据

- 用户提供基线：638 发现，621 通过，11 skip，5 FAIL，1 ERROR（4 challenges proxy、mainline1 semantic FAIL、缺 MAINLINE1_TEST_PORT loader ERROR）。
- 初次从 worktree 根调用 `python backend/manage.py test` 发现 0 个测试，**不是有效基线**，日志 `evidence/module5/baseline.log`。
- 已纠正到本 worktree 的 backend 目录运行全量基线，日志 `evidence/module5/baseline-backend.log`，后台运行中。后续所有测试从 backend 运行，使用 `/home/hatch/workspace/ctf-venv/bin/python`、`DATABASE_BACKEND=sqlite`。

## 5-1 完成（2026-10-29）

- 新应用 practical_training：ChallengeMapping 仅引用模块一 TaskPackage；领取要求已由模块一产生的本人尝试，不新建任务体系。新增草案 seed 命令，静态知识与四级提示为原创候选资料；默认不冻结、不放行。
- 分配记录任务快照、能力、先修、验收/材料引用、目标、端口、AUP、时段与资源/网络策略。复用模块六提示 request/show，提供本人/教师 API 读取边界。
- 公共改动已落地且仅两行：settings 添加 practical_training；urls 添加 `/api/practical-training/` include。
- 已生成本应用 `0001_initial` 迁移（包含后续工作包的证据/修复关系）；makemigrations 提示默认 SQLite 文件目录不存在，但测试数据库正常创建，后续会用独立临时 SQLite 验证迁移。
- 命令：backend 下 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python manage.py test practical_training.tests.MappingTests --noinput`；**9 发现 / 9 通过 / 0 失败**，证据 `evidence/module5/wp5-1.log`。包括跨学生读取/修改/尝试绑定、AUP、服务端目标、默认关闭环境、提示请求与交付、事务回滚和 seed 幂等。
- 本地全量基线命令在 600 秒后台上限被终止，未得到完整结果，不算运行通过；保留 `baseline-backend.log`。最终全量将提高时限并检查慢测试来源。
- 尚差：5-2 服务端核验/交接、5-3 修复复核、5-4 生命周期。真实 Juice Shop/网络隔离、课程签收未完成。

## 5-2 完成（2026-10-29）

- 新增固定 `/api/Challenges` 服务端观察器：仅登记的个人实例/专用端口/IP，禁重定向与环境代理，限制超时和响应大小；启动先记录未解出基线，拒绝既有完成状态归因。
- 证据绑定 assignment、TaskAttempt、任务/目录版本、学生、容器、challenge key、验证器版本、观察摘要/故障。幂等键上检查完整请求来源与证据内容；同键异内容拒绝，重试返回存储结果不重执行。
- 可信适配器写模块六 SubmissionSnapshot / VerificationResult，复用独立性快照、compute_overall、dispatch_result / retest；由模块六回传模块一 VerificationFact。保留学生通用提交的 server_evidence_not_connected 行为，不能提交 passed/solved 绕过。自报仅审计，不生成通过。
- 一次已核验尝试冻结；失败/故障后的新练习须由模块一新领尝试和新环境，避免违反模块六首次有效提交不覆盖规则。
- 命令：`DATABASE_BACKEND=sqlite .../python manage.py test practical_training.tests --noinput`；**18 发现 / 18 通过**，其中本包新增 9；证据 `evidence/module5/wp5-2.log`。服务端状态以测试替身验证契约，不表示真实 Juice Shop 联调。源码版 HTTP 适配器及无 AI 完整链路测试将在最终验收再覆盖。
- 尚差：5-3、5-4；真实环境、课程签收仍未运行/未完成。

## 5-3 代码完成，扩大回归待完整结果（续跑登记）

- `repairs.py` 已实现：原挑战有可信通过证据后，经模块六 schedule_retest / claim_retest 创建不同资料场景的尝试；解释与声明式修复方案先冻结，主张未复核时不完成。
- 单独的修复 verify 入口真实执行服务端固定合成授权测试（匿名、同租户、跨租户、所有者、未知资源，含正常访问对照），不执行学生代码；结果写模块六并关联原尝试。测试方案通过不等于在线修补 Juice Shop。
- 原 `wp5-3-rerun.log` 记录本应用 25 项（含 RepairTests 7 项）逐项通过，但扩大回归中断于模块六测试；**没有完整运行结论，不计整组通过**。
- 已再次从 backend 干净运行 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python -u manage.py test practical_training.tests skill_review.tests learning_map.tests --noinput --verbosity 2`；使用 7200 秒后台时限，日志 `evidence/module5/wp5-3-complete.log`。完成后在此登记总数。
- **完整重跑已结束：94 发现 / 94 通过 / 0 失败 / 0 跳过，耗时 529.858 秒**，`wp5-3-complete.log:213–215`。其中模块五 25、模块一/六既存 69。5-3 代码及本地契约回归完成；真实 Juice Shop 修复联调不在此结论内。
- 后续：5-4 进行中；不改变模块一/六既有代码。

## 5-4 完成，本地开放条件复验（2026-10-29）

- 教师入口：映射审核及内容哈希、任务 pause/resume；分配 pause/resume/isolate；逐实例隔离验收登记（教师身份、全部检查项、证据引用、有效期、实际资源上限与来源绑定）。学生仅可 reset 本人授权；跨学生与教师控制拒绝有审计。
- 默认真实靶场关闭。设置、任务审核、实例验收三道门均满足才可启动。实例 ID/端口/镜像/启动时间等变化使验收失效；未完成干净基线前不交付访问链接。
- `expire_practical_training [--dry-run]` 回收到期平台授权；读取时可补做过期流转。隔离/reset/到期均保留证据、撤销验收，标记 `pending_operator`，**不把平台状态当作容器销毁**。既有运行时出现 stopped/destroyed + destroyed_at + 空 access_url 后才能登记 `confirmed_by_runtime`；待清理仍占用平台资源额度。
- CPU/内存/PID、时长/个人并行数校验；默认外连拒绝及其他学生/宿主控制面/内网/生产拒绝策略不可放宽。配置放本应用，支持环境变量，不增加公共 settings 项。
- 真实 Docker、网络 ACL、直连身份网关仍未运行/未证明，教师验收引用只是运维登记，不能冒充自动隔离实测。

### 联调中发现的共享契约差异与处理

- 首次 5-4 测试 **44 发现 / 43 通过 / 1 FAIL**，`wp5-4.log`：无 AI 全链路发现共享模块六提示/事实/复测/复盘的拼接事件 ID 超过 64 字符；SQLite 未限制，不能据此宣称跨数据库可用。
- 不改共享模块：本应用适配器直接使用模块六既有 AssistanceRecord / SubmissionSnapshot / VerificationResult / RetestAssignment / ReviewCard / DownstreamNotice **公开持久化契约**，为模块五产生有界 ID，事实经模块一 ingest_verification_fact。继续复用模块六 assistance_snapshot、compute_overall、show_hint、schedule_retest、claim_retest；**最终不再调用原 dispatch_result / apply_result_to_assignment**。没有新成绩表、提示表或事件表。
- 新增模块五 `review/` 将六项复盘写入模块六 ReviewCard，保留完成冻结；模块六原生复盘接口未改。修复任务的 unknown 帮助状态不会被计为独立复测通过。
- `retry_practical_delivery` 复用模块六 DownstreamNotice 重试原始固定 payload，UUID 转为契约类型，稳定时间和事实 ID，不重执行练习；测试覆盖发送失败恢复、无重复事实。
- 修复后的定向测试 **46 发现 / 46 通过 / 0 失败**，`evidence/module5/wp5-4-final.log:164–166`。包含平台生命周期 14 项、HTTP 解析/故障 3 项、完整无 AI/交接恢复等验收 4 项，加原有 25 项。
- 无 AI 完整测试走真实回环 HTTP 的**合成 Juice API fixture**、真实本地访问策略验证器及模块一/六数据库；禁所有模型相关开关，阻止除 fixture 地址外的一切 socket 连接，模型边界调用数 0，模型调用记录 0，仅两次本地靶场观察请求。全部该链路事件 ID ≤64。这是契约联调，不是 Juice Shop 镜像实测。
- 曾启动全量：backend 下 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python -u manage.py test --noinput --verbosity 2`，7200 秒时限，日志 `evidence/module5/full-suite.log`。发现下述生命周期边界后主动停止，未完成，不计通过；最终代码另行完整重跑。

### 最终收尾核查

- 独立临时 SQLite 全迁移完成，模块五 0001/0002 均 OK；`makemigrations --check --dry-run` 为 No changes detected，`check` 为 0 issues，整条命令退出码 0。证据 `evidence/module5/migrations.log:80–81,107–108`。
- 补测暂停映射的材料重新审核：审核只更新内容签收，不自动恢复；恢复仍需显式教师操作。已将审核时的内容校验与暂停放行校验分开；领取和学习操作仍拒绝 paused，补测已通过。
- 补测到期但尚未执行回收调度/读取补偿的资源占用：不能仅依据 expires_at 将仍在运行的实例排除额度。先用 `lifecycle-edge-before.log` 复现（2 项中 1 通过 / 1 FAIL：未命中额度校验），然后修正为所有非终态分配及 pending_operator 都保留额度，直到既有回收/回执对账释放。
- 最终新增测试共 48。`manage.py test practical_training --noinput --verbosity 2` → `wp5-final-48.log:166–168` **48 / 48 通过，24.489 秒，退出码 0**；包含两个最终生命周期边界及完整无 AI 闭环。
- 全量同命令不带 label → `full-suite-final.log` 已完整结束，后台时限 7200 秒内完成；**686 发现/运行、669 通过、11 skip、5 FAIL、1 ERROR**，测试耗时 **1977.955 秒**，退出码 **1**。不是全绿，但不能与中断运行混淆。

## 最终交付结论（2026-10-29）

- 对照给定 dc997fe 基线（638 / 621 / 11 / 5 / 1），新增 **48 发现、48 通过**；失败、错误、跳过数量不变。全量中 48 个模块五测试逐项为 ok，无新增失败或错误。
- 保留的四个 `challenges.tests.ChallengeProxyAccessTests` 失败：`test_access_url_does_not_include_reusable_token`（URL 含 token）、`test_proxy_accepts_authenticated_owner_without_cookie`（401 ≠ 200）、`test_proxy_rejects_authenticated_non_owner`（401 ≠ 403）、`test_proxy_rejects_unsafe_session_request_without_csrf`（401 ≠ 403）。证据 `full-suite-final.log:897–938`。
- 其余给定基线问题：`mainline1.tests.test_semantic.SemanticTests.test_real_transport_constructor_pins_options_without_provider_registry`（ai_providers 已在 sys.modules，FAIL，行 941–952）；`mainline1.test_settings`（缺 MAINLINE1_TEST_PORT，loader ERROR，行 880–893）。未越界修复这些既有问题。
- 最终代码 25 份 Python 源文件 SHA-256 与全量启动时清单完全一致；清单 `evidence/module5/final-code-sha256.json`。迁移检查成功，公共变更仍只有 settings 注册和 urls include 各一行，`git diff --check` 通过。
- `DELIVERY.md` 已登记完整结果、实际命令、接口/迁移、证据位置和剩余依赖；`backend/practical_training/README.md` 为使用与配置说明。测试日志被 gitignore 排除，须单独保留。
- 5-1～5-4 代码及本地契约验收完成；真实 Juice Shop、真实身份/网络隔离、资源强制与物理清理、正式课程签收和 PostgreSQL 并发验收仍未运行/未证明，不允许冒充生产放行。未 commit、未 push，未修改其他 worktree。

## 保留项补做（第二轮，2026-10-29）

### 开工及宿主能力核查

- 已重读 DELIVERY 第 6 节七项保留内容及本文件。继续只在模块五 worktree 工作，不修四个 proxy 基线失败，不 commit/push。
- 官方 v20.2.0 的 node24_linux_x64 发行包已下载，SHA-256 `dbb457f74e908e28c41d7787e36d30d121d5b9f6178524720567b4aeb41f2968` 与官方 release 元数据一致；本机 Node v24.22.1，无需替换 Node。证据 `r2-release-metadata.json`、`r2-download.log`。
- systemd-run 实际失败：没有 system bus；当前 cgroup 没有委派 cpu/memory/pids 控制器。iptables 缺 CAP_NET_ADMIN。独立 user/net/mount/PID namespace 可创建，但独立宿主 UID 映射、新 proc 挂载受限。保留所有 probe 日志，不将“有命令”当作控制成功。
- 本地实测基础设施与生产放行分离：不伪造教师签收或 EnvironmentApproval，不开启生产 PRACTICAL_TRAINING_ENABLED；真实读取/证据回传和 HTTP 身份门将使用独立验收数据库与明确标记的测试身份。

### 第 4 项：课程送审材料已备好，待人工

- 新增 `docs/module5-r2-course-signoff.md`：映射/WSTG/四级提示/解释口径逐条清单、种子评审表、冻结/发布/变更重审操作路径；审核人/日期/结论全部留空，无完整题解。
- 证据：`r2-course-source-snapshot.json`、`r2-course-references.json`、`r2-course-generation-manifest.json`。11 项静态材料检查通过；仅编制送审包，没有执行教师签收或写业务审核记录。
- 明确待审缺口：原题/修复题目前共用提示，解释仅保存、不进入自动评分；种子不创建 WSTG 转译记录，实际能力目录与资料语义仍须教师核对。

### 第 1 项：真实 Juice Shop / 服务端读取 / 归属已实测通过（本地范围）

- 官方 v20.2.0 Node 24 发行包真实运行，每个测试学生独立进程与数据副本，未使用 Docker。实际 API 暴露 `Confidential Document` 的 key 为 `directoryListingChallenge`；首轮 fixture 的 `confidentialDocumentChallenge` 不存在，旧 key 读取明确失败关闭，证据 `r2-key-compatibility.log`。已修正默认值、映射校验和 fixture，新增迁移 `0003_correct_juice_challenge_key` 及两项回归；旧别名映射改正后暂停并清空旧审核，必须重新人工审核/恢复，不改历史证据。
- 两实例先由未修改算法的固定 `/api/Challenges` 读取器记录 `solved=false`。学生 B 随后通过实际 HTTP 学生入口浏览并获取应用文档，Juice 自身记录挑战完成；没有直接修改 Juice 数据库或伪造 solved。B 的 reader 变为 true，A 仍为 false，负向对照成立。
- 真实观察进入既有模块六结果/模块一事实契约：A 得 failed，B 得 passed，各自绑定 assignment、attempt、student、task/version、发行包摘要、实例进程和端口。证据共 2、结果共 2、事实共 2；28 次实际请求/响应（认证头脱敏）保存在 `r2-http-*.json`，另有 `r2-reader-observations.json`、`r2-real-handoff.json`、`r2-live-summary.json`。
- 生产准入仍关闭：独立验收 DB 中课程/任务为草案；EnvironmentApproval=0、已审核映射=0，真实 start API 返回 400。此次是**运维验收路径下真实 reader + 来源证据回传 + HTTP 身份门联调**，不是生产 claim/start/verify 全链路放行，也不是 Docker 镜像实测。`r2-post-cleanup-db.json` 回读 ModelCallRecord=0。

### 第 2 项：本机实例/网络隔离与身份门已实测通过，生产边界仍开放

- 每实例独立 user/mount/PID/net namespace、独立 chroot/应用数据；网络仅 loopback。实际运行时 namespace ID 两两不同；应用进程 CapEff=0、NoNewPrivs=1，chroot 内不可见宿主 `/home/hatch`，不挂载宿主 proc。未获得独立宿主 UID，不能宣称该项通过。
- 两实例实际端口：内部 18211/18212、学生网关 18411/18412、只读观察网关 18111/18112。学生入口每次向真实平台 assignment HTTP API 校验归属/状态；未记录基线前地址隐藏、本人基线后可见、他人 404、匿名拒绝，网关也拒绝他人/匿名。授权头不会转发给 Juice。
- 实测自身 loopback 可达；对方实例 loopback、真实运行中的宿主控制面 canary 均连接拒绝；内网/文档保留地址/互联网/IPv6 探测被拒绝或无路由。宿主侧 canary 实际 GET 200，与隔离内不可达构成正负对照。证据 `r2-student-*-isolation.json`、`r2-student-*-live-controls.json` 和 HTTP 原始记录。
- 仍开放：可信宿主 root、宿主内部只读 observer 端口不属于学生进程隔离边界；不能外推为共享宿主所有用户、多宿主网关/VPN、生产部署 ACL 或原有 Juice 直连入口已治理。此临时验收网关不替换 challenges proxy。

### 第 3 项：真实到期回收与部分资源强制已通过，完整 cgroup 限额仍开放

- 两个真实 Node 进程均回读到 RLIMIT_AS 2147483648 字节、RLIMIT_NOFILE 256、CPU affinity 仅 CPU 0、Node heap 参数 256 MiB；独立分配探针触发 MemoryError，日志标记 `HOST_RLIMIT_AS_ENFORCED`。这是 **2 GiB 虚拟地址空间上限**，不是 768 MiB RSS/整组内存限制，也不是 cgroup CPU 带宽控制。
- PID 上限未强制到 256：实际 Max processes=27153；systemd bus、cgroup 控制器和 iptables 能力不足的失败日志已留存。首次新 proc 挂载失败、随后 768 MiB AS 导致 V8 启动 OOM，均保存于 `r2-attempt1-*` / `r2-attempt2-*`，未计通过。
- 真实授权到期时间为 `2026-10-29T05:45:55.132677+00:00`。临时宿主控制器按真实时钟停掉捕获的实例进程组，学生/观察端口随后均 errno=111；驱动确认所有捕获子进程消失。旧地址不可达；测试 Token 删除后真实平台请求拒绝。只有物理回读成功后才登记 destroyed 回执并 reconcile，两条分配最终 expired + confirmed_by_runtime。
- 证据 `r2-runtime-cleanup.json`、`r2-live-acceptance.log`（两项真实验收 PASS 标记）、`r2-post-cleanup-db.json`。临时平台 HTTP 服务也已停止。生产常驻调度、cgroup CPU/RSS/PID 聚合强制与生产运行时故障恢复仍须部署验收。

### 第 4 项补记：真实 key 勘误已同步至未签收送审包

- `docs/module5-r2-course-signoff.md` 更新为 v1.1，保留原未签收副本 `r2-course-signoff-initial.md`；`r2-course-key-correction.json` 保存实际 key、代码/送审包当前摘要与未人工签收标记。原 generation/source snapshot 仅描述初始文档子任务，不能当作第二轮最终代码未变更的证明。

### 第 5 项：真实基线与未来观察计划已落盘；真实时间/学习者保持仍开放

- 真实 B 通过证据 `69bd0d26-cd86-4309-a948-2ada8d00b1a8`，观察时间 `2026-10-29T05:45:42.991558+00:00`。独立验收 DB 和 `r2-delayed-retest-plan.json` 保留 assignment/attempt/result/fact 关联；模块六 RetestAssignment 已创建，因候选任务未签收仍为 pending_item。
- day3=`2026-11-01T05:45:42.991558+00:00`，day7=`2026-11-05T05:45:42.991558+00:00`。`delayed_observation.py` 两次实际执行均返回 awaiting_real_time、retention_proven=false，日志 `r2-day3-eligibility.log`、`r2-day7-eligibility.log`。另生成待人工导入的 tentative 日历 `r2-delayed-retest-calendar.ics`，没有安装自动调度或向外部日历发送事件。
- 本次为操作者驱动的合成学生账号，不是人类学习保持证据。后续须真实时间经过、教师签收全新任务/环境、全新未解实例、相同学习者及关联新尝试/新服务端证据；真实学习者还须自己的真实初测基线，不能继承此合成账号成绩。不得复用旧 solved 状态或修改时钟。

### 第二轮受影响回归已完整结束

- backend 下 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python -u manage.py test practical_training skill_review.tests learning_map.tests --noinput --verbosity 2`：**119 / 119 通过，187.525 秒，退出码 0**（模块五 50，既存模块一/六 69），证据 `r2-regression.log:240–242`。
- 全新独立 SQLite DB 全迁移含 0003 成功，`makemigrations --check --dry-run` 成功，证据 `r2-live-corrected-migrations.log`。第二轮未再跑全量；首轮 686 项完整结果保留为历史结果，不能据此宣称当前全量全绿。
- 第 7 项仍按范围保留：没有修复其他应用的四个 proxy FAIL，也没有改共享模块原生行为。

### 第 6 项：真实 PostgreSQL 迁移/套件/双进程并发已实测通过

- 没有系统 PG/可用安装候选；在私有目录真实构建 PostgreSQL 16.13，官方摘要核对一致。既有 legal_kb 全迁移需要 vector 扩展，首次缺扩展失败已留档；随后私有构建 pgvector 0.8.1，未跳过/fake 迁移、未修改共享应用或 venv。专用集群只监听 `127.0.0.1:55465`，临时 trust 认证仅作本地验收，不是生产配置。
- 最终全库迁移含模块五 0001–0003 成功，`makemigrations practical_training --check --dry-run` 无变更；真实 PostgreSQL 上 **50/50 模块五测试通过，14.893 秒**，测试库随后删除。证据 `r2-pg-migrate-final.log`、`r2-pg-tests-final.log:169–172`。
- 5 组各 2 个独立 OS/Django/PG 会话竞争：挑战同 key 201/200；重复修复主张 201/200；同 key 异内容 200/400；修复证据同 key 201/200；已提交挑战换新 key 400/400。每组均有父锁和释放后的 worker 间真实行锁等待；服务端另记录 947.417ms、506.623ms 的实际等待，不是 mock 锁。`r2-pg-*-locks.json`、worker SQL 日志和 `r2-pg-server.log` 保存原始证据。
- 原生 psql 只读快照确认 evidence/submission/result/fact/notice 各 2，claim/retest 各 1，重复 evidence key / first_effective attempt 分组均 0。HTTP fixture 仅收到两次状态读取（基线+核验）。PG 专项使用合成已审核 fixture/APIClient 身份，这是数据库契约测试，不是新增真实 Juice 或生产身份验收，也不代表人工签收。
- `r2-pg-report.md` 有完整版本、构建/运行命令、失败记录与边界；新增三个专用 `backend/scripts/r2_pg_*` 文件。最终 `pg_ctl status=3`（no server running），55465/58165 无监听；`r2-pg-shutdown-verified.log`、`r2-pg-final-status.log` 已核对。没有留下服务/自动调度，私有工具与数据保留供追查。
- 入口目录复核发现首次 PG label 套件从 worktree 根调用绝对 manage.py 路径。为满足本会话 backend cwd 约束，另以明确 backend cwd 重跑同一套件：**50/50 通过，9.246 秒，退出码 0**，`r2-pg-tests-backend.log:1,170–173` 保存 pwd/结果/测试库删除。未重跑独立并发或修改应用；再次停服，`r2-pg-shutdown-backend.log` / `r2-pg-status-backend.log` 确认关闭且无监听。该次作为最终 PG 套件结果。

### 第二轮交付收尾

- `DELIVERY.md` 已追加 §7“保留项补做（第二轮）”，七项分别列出已实测通过、已备好待人工、仍开放及原因；§1–6 保留首轮历史口径。新增 `scripts/module5_r2/README.md`，记录精确成功命令、证据保护、重跑前置条件、停止方法、真实延迟观察步骤；本应用 README 同步兼容性修正与剩余边界。
- `r2-final-local-checks.log`：分支/基底未变、未暂存、公共注册各一行、所有变更在模块五约定范围、`git diff --check` 通过；31 个 Python 文件和 PG shell 语法检查通过；九个 PG 测试版核心文件摘要未变，七个课程勘误附件摘要一致；28 份 HTTP 认证元数据均脱敏。八个 Juice/平台/canary 宿主端口连接拒绝、旧 supervisor 不存在。
- 课程签收仍为空，真实延迟观察仍未发生；本机 cgroup CPU/RSS/PID 与生产边界未被写成通过。仅成功验收 DB 的测试 Token 撤销结论有回读证明，失败运行 DB 作为历史测试证据保留，不可拿来重开旧授权。
- 未 commit、未 push、未 stash；不读取或修改主检出/模块八应用文件。最终运行残留核查与受控摘要分别登记为 `r2-final-runtime-checks.json`、`r2-evidence-sha256.json`，与第二轮附件一并保留；日志/SQLite 不依赖 git 自动收录。
