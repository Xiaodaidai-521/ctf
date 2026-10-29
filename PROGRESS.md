# 模块八第一阶段实施进展

## 2026-10-29 开工核对（实施前）

已按顺序阅读 `/home/hatch/workspace/module8-brief/` 的 context.md、module8-plan.md、master-plan.md（模块八/阶段/里程碑 I）、nav-index.md（§3–4）、module7-plan-ref.md（候选/评测/报告）。工作目录仅为 ctf-module8，分支 feat/module8-evaluation-center；不访问其他 worktree，不 commit/push。开工已有 DELIVERY.md/PROGRESS.md 删除及未追踪的三个伪造报告复现测试；按任务要求重建交付文档并保留、反转攻击测试。

### 真实入口与数据源核对

- M1：`learning_map/models.py` 的 TaskPackage（256）、TaskAttempt（386）、VerificationFact（417）均存在。任务/目录版本分开，fact.attempt_id 是 UUID，而 M6 的 attempt_id 是数字外键。`services/handoff.py` 有事实幂等/冲突校验；`events.py` 写入失败会上抛。模块八只读，不调用会写推荐/画像的服务，不从事件计通过。
- M6：SubmissionSnapshot → 当前 VerificationResult 才是成绩和独立性的权威；原提交与更正结果要分别展示。`RetestAssignment` 持有原尝试、新尝试、完成提交；抽查是 TeacherSamplingBatch/Item，开放题是人工评阅队列，争议/更正有独立记录。`DownstreamNotice(target=module8)` 目前明确 not_connected。模块八将通过关系读取并在本应用保存幂等接收/重算回执，不另裁成绩。
- 差异/防误读：M6 first_effective 是“每尝试”而非“学生—任务首次”；统计需自行固定首次资格。更正后 submission.independence、assignment.outcome 与 M1 路径状态可能仍旧，不能用它们代替当前 result。teacher_help 事件也用于评阅/抽查，不等同真实帮助；采用 AssistanceRecord/冻结快照。M1 教师帮助 level=0 与 assisted 校验 1–4 不一致时可能事实交接失败，应显示对账差异，不伪造成功。
- `learning_analytics`：LearningEvent 与 LearningBehaviorEvent 是两套现有记录。旧 record_learning_event 默认 best-effort 返回 None；M2 使用 strict=True。教师报表可以查询全平台学生，不存在班级归属模型；旧 teacher 入口排除 staff，但其他模块允许 teacher/admin/superuser。本应用沿用学生本人、教师/管理员平台教学范围，待办修改另校验负责人/原提案作者。LearningAdjustmentProposal 只有状态与摘要，没有验证效果的可信含义。
- M2：TeachingRun、TutorRequest、ModelCallRecord、HintDelivery、TeacherTicket、PracticeAction 均真实落库；成本/token 可空。运行/请求公开 UUID 与数字 FK 不混用；帮助以 M6 记录为准，避免跨两套事件重复计数。开始运行与开始事件不是同一个事务，事件可能缺失；读侧显示缺口。`ai_assistant/performance.py` 是请求内摘要，部分存 AIMessage.metadata，不是完整运行账本，M8 不读消息正文也不重复造账。
- 风险回放：`export_risk/experiments/replay.py:38`、`comparison.py:15` 为无写入的合成虚拟时间策略回放，可复用；真实策略目录是 A/B/C/D 等 Policy，不直接接受模块七示例的任意配置 JSON。评测必须明确支持的配置/适配范围，未支持的模型/提示/知识库改动不借冻结结果给通过建议。
- M7：`feedback_center/services/candidates.py:149` 的 attach_report 只验证调用方 JSON，candidate_config_digest 可空，complete/approve/activate 没有查询评测运行。将增加模块八权威报告解析与确切候选/基准/任务范围绑定，关键放行点复验，保留模块七状态机。原 test_phase3 的假报告 fixture 需改成实际模块八测试运行。
- 前端：LearningEffectAnalysis.vue 会无条件补演示学生，按用户名覆盖真实响应，失败也回退演示；旧快照种子还有 sample_description.source 标记。本次页面改接最小化 M8 事实查询，正式模式不消费旧合成快照；显式演示独立、无写入、不影响正式查询。
- M3/M4/M5 证据契约保持“未接通”；既有只读风险回放不冒充模块四接通。里程碑 I 执行“未开展”、实际保护“未评估”。

### 实施计划与公共文件归属

1. **M8-1** 新建 evaluation_center：只读尝试/事实/结果/版本投影、首次口径与统一指标结构、事件对账；配真实 M1/M6 服务构造测试。
2. **M8-2** 教学查询/本人明细/运行摘要权限与字段白名单；正式/演示/离线分离；改现有教师页为明确模式的基础证据页。
3. **M8-3** 在本应用扩展 proposal 周边待办，revision 原子认领/转交/处理日志；导入求助/必评/抽查/争议；关联真实新场景复测；消费更正并按学生、任务/目录版本、原窗口保存重算回执，保留原结果。
4. **M8-4** 冻结数据集与批次/逐例持久化、隔离测试配置/服务令牌适配器、确定性规则回放、三组报告/缺失/预算/完整性；模块七真实报告校验与攻击回归。
5. **M8-5** 固定场景 1–10 自动验收，缺依赖作契约测试并登记；全量测试与迁移检查，生成 DELIVERY.md。

每包完成先跑相关测试、追加本文件，再开始下一包。新增依赖暂定为零，不安装 promptfoo/外部平台。公共文件仅 `ctf_backend/settings.py` 增应用注册、`ctf_backend/urls.py` 增 include；共享事件/事实模型不改。前端修改限定本页面及新增本应用 API 文件。feedback_center 的最小安全接缝及相关测试会单列交付。

### 测试基线

交接基线：638 发现、621 通过、11 skip、5 FAIL、1 ERROR（4 proxy、1 mainline1 semantic、1 loader，均既存）。开工执行 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test backend --noinput`，日志 `/tmp/module8-baseline.log`，含现有额外 3 个报告复现测试。该次基线复跑到达 600 秒后台时限被终止，未产生完整计数，不记为通过；交接基线作为比较依据。最终全量回归将使用更长后台时限。

### M8-1 完成

事实投影已实现（`projections.py`）：任务/目录/事件版本、当前与历史 M6 结果、M1 事实、帮助/事件对账、更正链与真实复测关系；首次资格在时间过滤前按学生—任务—任务版本—目录版本固定。缺完整记录不判独立，可信更正可以把原未知改为受助；不依赖陈旧 assignment.outcome。23 个投影测试全部通过（`/tmp/module8-projections.log`），加本应用基础测试 11 个，共 34 个通过。源应用 learning_map/skill_review 回归另在后台执行。下一步 M8-2。

#### M8-1 基础建设记录

已创建 evaluation_center 应用、统一指标封装与 NonFormalAccount 来源标记（迁移 0001）；settings 仅增加一行注册。事实投影及真实 M6 服务测试正在实现。基础测试命令 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test evaluation_center.tests.test_provenance evaluation_center.tests.test_metrics --noinput`：初跑 7/7 通过；加入权限与缺失语义测试后，附加 test_permissions 再跑 11/11 通过，证据 `/tmp/module8-foundation.log`。迁移已生成，未对实际数据库 migrate；原默认 SQLite 路径不存在时 makemigrations 仅报历史检查警告，后续检查显式使用内存库。

### M8-2 完成

已核对中断后文件与日志。新增只读 `students/learning/attempts/runtime` API、严格查询字段校验与角色/本人归属校验；按学生/任务/知识点/目录版本筛选，隐藏答案、邮箱、响应正文与供应商请求凭证。正式查询排除 NonFormalAccount 的 demo/offline 账号；演示仅显式合成响应，无数据库写入。教师 LearningEffectAnalysis.vue 改为版本化事实与指标表，正式无数据保留空，旧演示用户名覆盖逻辑已移除；请求序号防止旧响应覆盖新筛选。运行摘要使用模块二真实调用记录，未知成本/token 保持 null，费用按币种与价格版本分开。

测试：`DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test evaluation_center --noinput`，**44 发现、44 通过、0 失败/错误**，7.711 秒（测试主体时间），证据 `/tmp/module8-m8-2.log`。覆盖学生读他人明细拒绝、匿名拒绝、教师/管理员权限、字段最小化、演示隔离、未知费用、严格筛选。前端依赖未安装，尚未构建/浏览器联调，不声称前端运行验收完成。上轮源模块后台回归被会话中断，未有完整结果，不计通过。下一步 M8-3。

### M8-3 完成

新增 TeacherTodo/TodoAction/ProjectionReceipt（迁移 0002），保留原提案/原核验结果；五类队列分离，同步包含 needs_correction 抽查项及批次依据/规模/负责人/窗口。revision 条件更新与日志同事务，冲突 HTTP 409；负责人权限、转交原因和处理摘要强制校验。验证仅接受同学生/原尝试关联的新场景、干预后、当前独立通过复测；更正使复测失效则重开待验证，读侧亦即时复验。幂等本地回执按原日窗口与版本重算，不改源 notice/成绩。教师页新增正式模式协作操作区；源成绩处理仍留在 M6。

测试：初次14例因测试 fixture 未解包 schedule_retest 元组和错误 correction source 有5 ERROR，修正后14通过；补充回执保存失败回滚、源 notice 不变、HTTP创建/同步和非正式来源排除后，`DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH=:memory: /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test evaluation_center --noinput`：**60发现、60通过**，测试主体10.536秒，证据 `/tmp/module8-m8-3.log`。已覆盖审计失败回滚、过期revision、非负责人、无证据验证、旧/无关复测、迟到更正按当前版本重算。未运行前端构建，未对实际库 migrate；迁移在测试库执行通过。原协作会话已退出（消息套接字失效，活跃列表无该会话），后续由当前会话继续 M8-4/M8-5，避免等待不存在的接手者。

### M8-4 进行中

评测内核与模块七最小安全接缝分文件并行实现。M7 在登记、完成评测、审批、发布有效性检查处解析 M8 持久记录，而不是信任请求 JSON；绑定当前数据库候选，发布范围不得扩出已测任务。既有三个攻击断言反转为拒绝；旧状态机合法 fixture 将改用实际隔离运行。新增真实摘要/版本/范围/相同配置不同候选/审批发布复验及 HTTP 测试，尚未执行，不计为通过。前端使用现有 package-lock 执行 `npm ci --prefix frontend --ignore-scripts --no-audit --no-fund` 成功（241 包，无新增依赖）；`npm run build --prefix frontend` 已通过（2分7秒，`/tmp/module8-frontend-build.log`），仅大于500kB的chunk警告；无浏览器/真实后端联调结论。M1/M2/M6 回归运行中。M7初次集成32例中31通过、1 ERROR（`/tmp/module8-m7-trust.log`）：内核fixture的 insufficient 与M7现有 insufficient_evidence 枚举不一致，正在修复；原三攻击、真实合法报告及新增边界测试已经通过，但本包尚不记完成。

内核最终测试已核对原始日志：**44发现、44通过**，20.058秒（测试主体），证据 `/tmp/claude-0/-home-hatch-workspace-ctf-module8/f4ae79c9-a207-4447-9e56-96395927c7d1/tasks/bp71drbbo.output`。覆盖真实持久运行、25例固定合成回归、100→200退化、配置/清单/逐例/报告篡改、预算与中断、无网络复现、系统权限和令牌、正式账号拒绝及配置秘密不出API。推荐枚举已统一。

### M8-4 完成

模块七枚举对齐后，`DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test feedback_center.tests.test_phase3 feedback_center.tests.test_forged_report_repro --noinput`：**32发现、32通过**，228.939秒，证据 `/tmp/module8-m7-trust-final.log`；原三攻击全部拒绝，合法报告仍可登记并完成原生命周期。内核44项通过，迁移0003一致性与Django check通过；新增评测管理/报告路由，适配器仅在专用测试URLConf，正式环境写服务关闭。独立管理账号、冻结25例、逐例持久化、预算/中断缺失、三组指标、完整report_digest/稳定replay_digest均已落地；不支持配置/来源不编造成功。未启用第三阶段发布开关。

另完成 M1/M2/M6 源回归：`DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH=:memory: /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test teaching_agent learning_map skill_review --noinput`，**84发现、84通过**，959.238秒，证据 `/tmp/module8-source-regression.log`。说明：基础settings把相对字符串 :memory: 拼成工作区文件名；仅makemigrations历史检查曾产生一个空文件，已检查并删除，测试仍使用Django内存测试库。后续检查使用专用test_settings或绝对临时路径。下一步 M8-5。

### M8-5 进行中

新增 `acceptance.py` 版本化场景1–10与真实测试选择器（去除包含关系导致的重复运行），以及 `test_evaluation_acceptance` 管理命令；外部依赖单列，不把纯契约当真实隔离/供应商/模块五验收。新增8项固定集成测试：断连、超时、429、额度、全模型关闭分别走真实领取/只读练习/规则提交/人工必评/教师处理/新场景复测；另验证源保存回滚与重试幂等、M8保存失败503待重试、网络浏览器自报不得变为服务端证据。初跑 **8/8通过**，2.865秒，日志 `/tmp/module8-m8-5-focused.log`。补修源抽查实时状态与导入快照分开展示，M8写失败不报成功；全evaluation_center第一次整包运行 **115发现、111通过、4失败**（37.637秒，`/tmp/module8-m8-5.log`）：其中3个适配器测试失败：完整发现提前在普通配置导入条件注册的 test_urls，后续override_settings不会自动重载模块。已在隔离测试setUp中重载专用URLConf并清resolver缓存（不放宽正式路由或鉴权），第4处为固定选择器指向错误的M6测试类，已改为 Module6UnavailableVerifierTests。修正后整包重跑中。最终前端构建已通过，3分22秒，`/tmp/module8-frontend-build-final.log`，仅大chunk警告。M6提交HTTP数据库异常仍是通用失败，跨服务恢复/物理隔离/真实供应商/课程签收列为未验收。

### M8-5 完成（本地适用范围）

修正后 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test evaluation_center --noinput`：**115发现、115通过**，44.597秒，证据 `/tmp/module8-m8-5-final.log`。固定场景选择器全部解析到真实测试，无重叠重复选择；源队列实时状态、保存失败待重试及隔离URL完整发现回归通过。最终前端构建通过；`git diff --check`、Python compileall、Django check 通过，迁移无漂移。开始全量普通配置 SQLite 回归，使用长后台时限；全量结果与基底对账完成前不声称整体交付。

最终全量已启动：`DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test backend --noinput`，普通配置（非隔离评测test_settings），日志 `/tmp/module8-full.log`，后台上限7200秒。

### 最终全量对账完成

全量退出码1（保留既存失败，不伪报全绿）：**764发现、747通过、11跳过、5 FAIL、1 ERROR**，测试主体2169.157秒。与基底dc997fe的638/621/11/5/1相比，新增126项全部通过（115项M8 + 11项M7安全回归），基底通过数未下降，失败/错误集合未增加。

已逐项核对：4个 ChallengeProxyAccessTests（URL仍含token、owner无cookie401、non-owner401而非403、unsafe无CSRF401而非403）；mainline1.test_settings缺MAINLINE1_TEST_PORT；SemanticTests.test_real_transport_constructor_pins_options_without_provider_registry发现ai_providers已由平台路由导入。与context.md既存清单一致，未改这些模块以掩盖失败。证据 `/tmp/module8-full.log`，SHA256 `0e020f87d86732a59a069e4de4481e52f2144d2a9437cfdc3629358bac259c9c`。

代码与本地适用范围验收完成，DELIVERY.md记录变更、迁移、API、命令、结果及未联调依赖。真实供应商/模块三四五/靶场物理隔离/里程碑I/浏览器联调均不宣称完成。无commit/push、无其它worktree读改、无新增运行依赖。

## 2026-10-29 保留项补做（第二轮）

### 一·验收快捷命令已实测

重读 DELIVERY.md 第7节及本进度后，实际执行 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test_evaluation_acceptance --verbosity 2`：**139发现、139通过，44.803秒，退出码0**。完整标准输出/错误（含迁移及逐测试名）在 `/tmp/module8-round2/acceptance-command.log`，SHA256 `b3d6e146d13810f4445d70569fc550391f8b2784068f6e1a3cda21469ee24c2b`。这是原固定选择器的补跑，不是139个新增样本。

### 二·真实批次前置探测

初探 `/v1/models` 返回401；随后排查确认本机配置采用嵌套结构，顶层api-keys是供应商分组而非客户端密钥数组，初探误把分组名用作凭据。此处纠正原先“两项密钥认证失败”的错误判断。首次应用持久运行 `7d87fb1f-52db-493d-b9ab-52ddfeda6ee3` 也因旧数组解析器得到 credentials_unavailable，**provider_calls=0**，不能算真实API批次；其6例均无模型证据，报告 insufficient_evidence，经M7登记进入needs_revision，日志 `/tmp/module8-round2/live-batch-key0.log` 保留，不计真实闭环成功。

修正读取 `access.api-keys`（仅内存，不打印或写出），同时兼容旧数组结构并禁止误用上游供应商密钥；补两项配置结构回归。正确凭据实测 `/v1/models` 成功，明确列出 deepseek-v4-flash 与 deepseek-v4.1（共13个模型），`server.port`确为8317。正在使用同一应用持久流程重新运行真实批次；原合成集合及语义不变。

### 四·真实数据库迁移已实测（提前作为第二项持久批次的前置）

新建独立目录 `/tmp/m8-scratch-round2.CiF1Ua`，使用 `evaluation_center.scratch_settings` 和绝对磁盘数据库路径 `/tmp/m8-scratch-round2.CiF1Ua/evaluation.sqlite3`。实际执行 `manage.py migrate evaluation_center --noinput --settings=evaluation_center.scratch_settings`，0001、0002、0003及依赖均应用成功；随后在同一新库执行完整 `migrate --noinput` 补齐独立账号及M7闭环所需表，退出码均0。日志分别为 `/tmp/module8-round2/migrate-evaluation.log`、`/tmp/module8-round2/migrate-scratch-all.log`；不是Django临时测试库，也未连接业务数据库。PostgreSQL检查：本机未发现pg_isready，127.0.0.1:5432不可连接，常用本地socket路径不存在；没有安装或启动PostgreSQL，本轮仅SQLite真实迁移。

### 二·真实请求及故障报告已持久化（模型有效输出仍待取得）

正确客户端凭据后的首批 `082a079b-9c96-4b94-bdca-7285b5deda19` 实际发出1次chat请求，HTTP403；停止剩余用例，保存1例记录和缺5例报告，M7拒绝不完整报告。随后通过同一M8/M7流程重新执行（仅临时观察错误体中的白名单词，不保存原文、不替换HTTP响应）：批次 `6cdc353f-d8b0-4d46-abd2-ab07d9b90546` 冻结 deepseek-v4-flash、export-classifier/v1 对 v2、6例×两臂×2观测；**72次真实HTTP尝试全部503**，每个观测最多3次、退避2/4秒，未直接放弃。6条逐例记录完整，但双方有效判定分母0、缺失6，通过率null，token/费用均null；不是0%或0费用。报告 `b4ca91da-d78c-4999-9299-22a57c2ae75b`、摘要 `b954a7996eda8a28d078abbd46bc8d31d3b6907d2e70ffcb8ba10f885633ddea` 为 insufficient_evidence，真实M7挂接/完成评测后进入needs_revision，未审批、未发布。诊断shell捕获CommandError后退出0仅表示诊断脚本结束，**不代表评测通过**。证据 `/tmp/module8-round2/live-batch.log`、`/tmp/module8-round2/live-diagnostic.log` 及独立scratch库。

另用已登记模型 deepseek-v4.1 对比相同v1/v2提示，保持原6例、最小输入、同一持久流程：批次 `25b6dfe9-af20-4ace-acc3-d2db633164b2` 发出1次请求也得到403，保存1例、缺5例，M7拒绝挂接；日志 `/tmp/module8-round2/live-alternate-model.log`，退出码1。三次真实批次合计74次HTTP尝试，**有效模型输出0条**，没有可报告的模型通过率或token数量。403的根因未被证实，不能因代码的停止标签断言是客户端密钥错误；该客户端密钥已经成功查询模型目录。未修改网关配置或生产策略。

第二项结论：真实请求、故障持久报告与M7故障报告闭环已实测；**成功取得真实模型输出并完成有效两配置比较仍开放**，原因是上述403/503，合理重试及换已登记模型后仍不可用。模型列表可见不等于模型调用成功。新进程在未开启live调用的scratch配置下回读4份报告，均通过M8完整性校验；M7两份完整的不足证据报告为needs_revision，两份缺例报告未挂接，全部未发布，证据 `/tmp/module8-round2/persistent-readback.log`。对本轮日志及scratch库扫描实际 `access.api-keys` 字节，无密钥值命中（仅输出泄漏数量0，不输出密钥）。

### 三·固定因素扩展及回归已实测

固定选择器版本提升到 `m8-phase1-acceptance/2`，新增 `FACTOR_SETS` 登记 `m8-live-export-classification/1` 的 prompt_version/model_id 两类单因素、2模型/2提示/6例/每臂2观测，默认测试用mock传输，真实调用单独显式启用。原 `m8-synthetic-regression/1` 的25例及语义保持不变，内容摘要固定断言为 `4de3c74803971973b2028c4d1600175120e6f640aafd389bf2f1a942790ff5b1`。

新增live记录/报告/M7信任与因素注册测试25项（20 live + 5清单，其中清单原有3项），**25/25通过，1.286秒**，日志 `/tmp/module8-round2/live-contract-tests.log`；网关含新旧YAML结构、密钥不外泄、重试、拒绝重定向/代理、未知用量等 **27/27通过，0.400秒**，日志 `/tmp/module8-round2/gateway-schema-tests.log`。这些是mock合同回归，不计为真实API样本。

最终重跑 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test evaluation_center feedback_center --noinput --verbosity 2`：**217发现、217通过，93.473秒，退出码0**（M8 164 + M7 53），日志 `/tmp/module8-round2/m8-m7-regression-final.log`。M8相比第一轮新增49项测试，不把原139项快捷补跑或重复模型观测算新增样本。迁移一致性检查无变化；git diff --check通过。
