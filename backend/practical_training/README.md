# 模块五首期：网络安全实训与修复验证

## 边界

本应用映射既有 `challenges.Challenge` 到模块一 `TaskPackage`，不建立任务或成绩体系。首期支持既有固定镜像 Juice Shop 的 `directoryListingChallenge`。本地 HTTP fixture **不是**真实 Juice Shop 联调；教师验收登记**不是**自动网络隔离证明。

修复任务是**不同资源场景的声明式访问控制方案**：学生解释原理、提交方案，独立调用服务端验证器重执行 20 项合成访问测试。包含允许正常访问、拒绝跨租户/越权、未知类型默认拒绝；deny-all 不能通过。不执行任意学生代码，不修改 Juice Shop 镜像。解释保存但不自动评分；结果只表示本任务声明的程序项通过，不表示解释题评分、生产修复或延迟保持证明。

无 AI 核心链路独立于模型、向量化、重排。没有新依赖、平台组件或 LangGraph。

## 安装与开放准备

```sh
# 在本 worktree 的 backend 目录，使用现有虚拟环境
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python manage.py migrate
python manage.py import_juice_shop
python manage.py seed_practical_training --catalog <已有目录版本> --capability <已有网络能力ID>
```

seed 只创建候选 TaskPackage 和 ChallengeMapping；重复执行不覆盖历史；不创建能力目录、不伪造教师审核、不冻结/发布、不创建环境。候选材料为本项目原创；WSTG v4.2 WSTG-ATHZ-02 是参考编号，不等于完成课程人工转译审核。

课程负责人通过既有模块一流程审核、冻结、开放原任务与修复任务，补齐知识点/目标/先修。原任务不允许绑定 repair 维度，防止挑战解出即获得修复能力；修复任务可含原知识点共同能力及单独修复能力。首期原任务的 retest_task_keys 仅包含绑定的新场景修复任务。模块五教师调用 review API 记录材料内容哈希。材料变化需新版本/重新审核，已领取尝试的旧快照不可覆盖。

应用内配置支持环境变量，无需增加公共 settings 行；同名 Django setting 优先于环境变量：

| 配置 | 默认 | 含义 |
|---|---|---|
| `PRACTICAL_TRAINING_ENABLED` | false | 只有环境变量为 true（不区分大小写）才开启；不能代替实例验收 |
| `PRACTICAL_TRAINING_VERIFIER_IP` | 127.0.0.1 | 服务端访问 Juice 专用端口的固定 IP，拒绝 DNS/学生 URL |
| `PRACTICAL_TRAINING_POLICY_JSON` | `{}` | 默认策略覆盖 JSON；Django setting 名为 `PRACTICAL_TRAINING_POLICY` |

默认策略：1 CPU（1000 milliCPU）、768 MiB、256 PID、3600 秒、每人 1 份占用；可调范围见 `policy.py`。资源上限与时长必须为正整数，时长不超过 7200 秒，并行不超过 2；CPU/内存/PID 不超过既有运行时上限。下调资源后若现有实例不能满足，领取会被拒绝，不会假装已经调整 Docker 限额。

默认禁止任意出站、其他学生、宿主控制面、校园/企业内网与生产地址。首期配置不允许放宽这些拒绝策略；本应用没有替运维安装 firewall/网络 ACL。

运维必须先提供逐实例隔离证据：身份/跨学生拒绝、宿主控制面拒绝、内网/生产拒绝、互联网出站拒绝、资源限制、到期凭证拒绝。教师将实际证据引用、实测资源上限和有效期登记到环境 approve API。登记绑定容器 ID、启动时间、身份、镜像、目标端口、访问地址、runtime metadata 与验证器 IP；变更使原登记失效。未满足放行条件只可教师本地演示，不能用示例 `true` 字段冒充真实证据。

## HTTP API

前缀 `/api/practical-training/`，全部要求既有 DRF 登录认证，JSON body；学生只读/操作本人，教师可读和控制。未公开服务端证据回调，客户端不能指定 URL、验证器、passed/solved 或任意代码。

### 学生流程

1. `GET mappings/`：AUP、模块一任务入口。
2. `POST /api/learning-map/tasks/<task_id>/claim/`，`{"version":"目录版本"}`，取得本人 attempt_id。先修由模块一检查。
3. `POST mappings/<id>/claim/`，`{"attempt_id":"UUID","accepted_aup":"m5-aup-v1"}`。服务端选择本人已登记、未使用的实例。返回任务/目标/端口/时段/策略快照；未建立干净基线前不交付访问链接。
4. `POST assignments/<id>/start/`，空对象：服务端先观察固定 `/api/Challenges` 未解出状态，才显示个人环境入口。若已解出，须新环境，不能归因给新尝试。
5. `GET assignments/<id>/`：静态知识、验收、状态、证据引用。
6. `POST assignments/<id>/hints/`，`{"level":1}`：只请求；`POST assignments/<id>/hints/<record_id>/display/` 才交付卡片并计入帮助。实际交付即算受助，不依赖客户端 ACK。
7. `POST assignments/<id>/self-report/`：辅助自报，不产生通过结果。
8. `POST assignments/<id>/verify/`，`{"key":"唯一非空键，最多64字符"}`：固定服务端观察器验证。返回服务端证据、模块六 result/submission 引用、模块一 fact IDs。相同键返回已保存结果，不重新观察；同键不同来源/内容拒绝。
9. 通过后自动用模块六规则安排**即时修复新场景**（due_days=0，不是三天后的保持测量）。`GET assignments/<id>/repair/` 查看任务；`POST` 同地址提交 `key`、`explanation`、`policy`。此时 completed=false。
10. `POST assignments/<id>/repair/<claim_id>/verify/`，`{"key":"新的核验键"}`：独立重新执行声明式方案。只有已保存的独立复核通过才完成；失败/未复核不完成。repair GET 返回实际状态。
11. `PUT assignments/<id>/review/`：六个字符串字段 `original_task_summary`、`error_evidence`、`judgment_at_time`、`correct_basis`、`next_verification`、`student_reflection`，每项 1–2000 字符；保存到模块六 ReviewCard，完成后不覆盖。

结构化方案仅接受：`{"default":"deny|allow","rules":{"public":"public|tenant|owner|deny","internal":"...","private":"..."}}`。任务材料说明新场景语义，不执行学生命令。

`GET assignments/`、`GET assignments/<id>/evidence/<evidence_id>/` 均检查归属。返回受控引用/最小状态，不提供公共证据文件链接。访问别人的分配、提示、证据、修复和 reset 都被拒绝并审计。

### 教师与生命周期

- `POST mappings/<id>/review/`：`{"review_ref":"人工签收引用"}`，不替代模块一冻结流程。暂停时可重新审核材料，但审核不会自动恢复；仍须教师显式 resume。
- `POST mappings/<id>/control/`：`{"action":"pause|resume","reason":"原因"}`，暂停同时阻止已有分配的后续学习操作。
- `POST environments/<ChallengeContainer数据库ID>/approve/`：`evidence_ref`、`expires_at`、`limits`（cpu_millis/memory_mib/pids）及 `checks`。检查字段见 `policy.REQUIRED_CHECKS`；必须来自实际验收。已分配环境不允许替换验收登记。
- `POST assignments/<id>/control/`：`{"action":"pause|resume|isolate|reset","reason":"原因"}`。pause/resume/isolate 仅教师；学生可 reset 自己的分配。隔离不可直接恢复，须清理后准备新环境。

`reset/expired` 终结旧平台授权；未提交尝试标 abandoned，已核验尝试/证据不改。已终结、隔离或到期的旧授权不能重用。失败/故障结果不覆盖首次有效提交，重新练习必须由模块一领取新尝试。

```sh
python manage.py expire_practical_training --dry-run
python manage.py expire_practical_training
python manage.py retry_practical_delivery
```

运维需每分钟调度到期命令，并运行既有 `cleanup_containers`。本模块不新增队列/平台服务。读取时会补记到期，关键写操作始终校验时限；不依赖调度及时性才能拒绝到期授权。

平台隔离/重置/到期写 `physical_cleanup=pending_operator`，不声称断开了既有直连端口。待清理实例及到期但尚未完成状态对账的非终态分配继续占用个人资源额度；只有既有运行时的 stopped/destroyed、destroyed_at、空 access_url 回执齐备，才对账为 confirmed_by_runtime。真实停机/网络隔离仍需独立运行证据。

## 模块一/六契约适配

使用既有 TaskPackage/TaskAttempt 和模块六 AssistanceRecord、SubmissionSnapshot、VerificationResult、RetestAssignment、ReviewCard、DownstreamNotice；模块五只存映射、授权和原始来源证据。

通用模块六 `server_verifier` 目前返回未接通，不能由学生提交覆盖。模块五在已取得可信服务端观察后使用持久化契约创建结果；复用 assistance_snapshot、compute_overall、show_hint、schedule_retest、claim_retest。

原模块六 dispatch、提示请求、复测完成及复盘的部分事件 ID 超过 64 字符，且 UUID 重试/unknown 复测有边界差异。为不修改共享模块，本应用分别产生短 ID 的事实、提示请求、复测结果与复盘事件；事实调用模块一 ingest_verification_fact，失败存模块六 DownstreamNotice；稳定 payload/时间戳/UUID 类型可重试，不重跑验证器。unknown 帮助不计为独立复测。原模块的路由、行为和迁移均未改。

## 测试与剩余依赖

```sh
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python manage.py test practical_training --noinput
```

`test_acceptance.py` 的完整链路使用回环 HTTP fixture 与真实本地策略验证器；socket 白名单断言不允许其他连接，模型工厂禁止调用，模型记录为零。测试含服务端假状态/故障、跨学生、自报、未复核修复、同键冲突、回传失败恢复、事件持久化回滚、资源/时限、教师控制和清理对账。

首轮仅完成契约测试；第二轮真实验收补充如下，不能将两轮的证据口径混为一谈：

- 官方 v20.2.0 **Node 24 发行包**实际运行（不是 Docker）。真实 `Confidential Document` key 为 `directoryListingChallenge`。服务端先读两实例未解基线，再由一个合成学生通过真实 HTTP 解题；正确实例通过，另一个仍失败。现有 reader 算法未改，来源证据实际进入模块六/模块一。
- `0003_correct_juice_challenge_key` 修正首轮旧 fixture 别名。已有旧别名映射将暂停、清空旧审核并要求人工重审/显式恢复；旧证据不重写。新安装也必须迁移到 0003。
- 本机独立 user/mount/PID/net namespace + chroot、回环学生 HTTP 身份门、默认无外连路由、真实到期停进程/端口不可达/测试凭证撤销均有实测。范围仅为一次性本地验收工具；没有替换生产运行时/通用 proxy。
- 实际资源强制为 Node 2 GiB RLIMIT_AS、256 FD、单核 affinity；**未实现/证明 768 MiB RSS、CPU 带宽与 256 PID cgroup 限额**。可信宿主 root、内部 observer 端口、共享宿主其他用户及多宿主生产边界不在该证明内。生产暂停/隔离、调度故障恢复仍需部署验收。
- 真实 PostgreSQL 16.13 + pgvector 0.8.1 全迁移、50 个模块五测试、五组双独立进程行锁/幂等验收通过。其挑战来源为 HTTP fixture，不冒充第二次真实 Juice 解题。工具为私有测试安装，未新增应用依赖。
- 真实 Juice 验收 DB 没有教师审核/EnvironmentApproval，生产开关保持 false；运维驱动用专用草案任务测试 reader/证据交接，**不是生产 claim/start/verify 准入全链路通过**。课程送审包已备好但无人签收；day3/day7 真实时间与学习者保持观察仍待完成。

可复核命令、控制细节、清理与未来观察步骤见 `scripts/module5_r2/README.md`（worktree 根下）。旧 challenges proxy 失败与自由练习直连路径不在本补丁修复范围。本应用服务端观察器不经过旧 proxy。

完整结果、执行命令、基线差异见 worktree 根 `PROGRESS.md`、`DELIVERY.md`。本地 `evidence/module5/*.log` 被仓库忽略规则排除，交接时需另行保留，不能只靠 git diff 找日志。真实 HTTP 附件含解题相关材料，不公开给学生或发送模型。
