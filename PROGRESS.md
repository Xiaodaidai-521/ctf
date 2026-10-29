# 模块四实施进度

## 约束与开工核查（2026-10-29）

- 工作位置：`/home/hatch/workspace/ctf-module4`；分支 `feat/module4-case-lab`，HEAD `dc997fe`。不 commit、不 push，不操作主检出/其他 worktree。开工状态已有 `PROGRESS.md`、`DELIVERY.md` 删除；依本任务要求重新编写，不恢复旧交付结论。
- 已依次完整阅读材料包 context、module4-plan、master-plan、nav-index、module1-plan-ref、module6-plan-ref、prompt。
- **材料差异**：`module6-plan-ref.md` 实际标题/正文是模块七反馈方案，不是模块六。核验侧以本 worktree `skill_review` 源码、README、测试和 `learning_map` 契约核对，不臆造接口。
- 当前无 `backend/data_lab` / 模块四页面；settings 已注册 learning_map、skill_review、teaching_agent、export_risk，未注册 mainline1；总路由无 data-lab。
- mainline1 存在 parsing/classification/rules/review/repository/worker，仍为内部组件；教学持久化适配与 ACL 待完成核对，不把内存 smoke 示例当部署实现。
- export_risk `assess_risk` 显式接收请求/画像/授权/特征/模型与策略版本/评估时间；无 DB/配额操作。`ExportRequestSnapshot` 和 AuthorizationSnapshot 默认 production，适配时必须双重显式 test；SourceMode.SYNTHETIC 服务端固定。
- B-v1 draft 条件为 `req_count_long > 50`；每次 10 条与请求次数分开。基础保护义务在所有策略分支生效。执行 service 的 prepare_execution/claim/consume 及 RiskDecision/ExecutionAuthorizationRecord/QuotaReservation/DeliveryRecord 不属于教学调用链。
- 公共文件归属：仅增本应用 settings 注册、后端总路由、前端模块四路由；既有应用原则不改。所有新增迁移归 data_lab。
- 前端 Vue 3/Vite，无既有 test script；使用独立本模块测试与构建验证，不改公共依赖清单。既有 Python venv 只用于运行，禁止修改依赖。
- 基线材料记载：638 发现，621 通过，11 跳过，5 FAIL / 1 ERROR（4 challenges proxy、1 mainline1 semantic、1 mainline1 loader）。待本 worktree 重跑并保存真实日志。

## 实施顺序与记录

1. D4-1：合成客户表/嵌套业务日志、依据事实、答案、四层帮助、独立版本与摘要、待签收清单。
2. D4-2：教学 owner/ACL、受管进程、扫描/复核教学副本持久化与状态冲突。
3. D4-3：冻结四轮回放、先判断后揭示、只读边界。
4. D4-4：API 与五步页面、教师对象权限。
5. D4-5：提交、事件事务、模块六→一真实本地交接、帮助/复测。
6. D4-6：固定回归、五类无 AI 故障、副作用哨兵、完整基线对账。

各包完成后追加实现、命令、实际结果、证据。未完成项不标通过。

### D4-1 完成（候选材料，人工待签收）

- 两个六行真实 CSV、事实卡、三个结论字段、四级帮助、独立答案/验证器/回放版本、服务器白名单与 SHA-256 固定在 `backend/data_lab/`；教师附件和签收表在 `docs/data-lab/teacher-signoff.md`。
- 测试：`cd backend && PYTHONDONTWRITEBYTECODE=1 /home/hatch/workspace/ctf-venv/bin/python -m unittest data_lab.tests.test_materials -v`：6/6 通过，日志 `docs/data-lab/evidence/d4-1.log`。
- 后续依据卡读取将复用真实 DataBasisCard；不会复制教师答案到 TaskPackage 学生材料或前端包。

### 接入核查补充 / D4-2 决策

- 与材料说明不同，mainline1 已有 `DjangoReviewRepository`，但它绑定未注册的 mainline1 模型及 PostgreSQL，不能直接用于本模块。复用 `encode_state/decode_state` 与原 ReviewService，新增 data_lab 自有 JSON 账本，按每次教学扫描隔离、DB revision CAS、事务落盘；不注册 mainline1、不复制内存仓储。
- `scan_rules` 的内置检测器白名单仅 email/ip/luhn，缺两个合成形态；需对 mainline1 作最小静态扩展：只新增两个固定合成模式、可选列范围扫描（默认行为不变），保留 draft/test 限制。受限 worker 调原 parser + RuleConfiguration/BusinessContext/scan_rules；补录使用同一完整 ParseResult 的位置，扫描覆盖与补录分列。
- 模块六已有真实 `create_submission → create_result → dispatch_result → ingest_verification_fact` 链，但 server_verifier 尚未接证据；需仅为本模块注册服务端验证入口，不能用学生自报字段通过 structured_rules。模块六原有长 fact/event ID 与重试 UUID/时间不稳定问题，计划在模块四专用 handoff 适配内用有界稳定 ID 和冻结 payload，不改其他任务口径。
- 既有教师接口普遍仅检查角色，无课程对象 ACL；模块四新增 CasePackage owner/授权教师关系，所有教师入口按对象复查。

### D4-2 完成

- data_lab 自有 CasePackage/LabAttempt/Scan/ReviewLedger/ProfileIndex，复用原 TaskAttempt、DataBasisCard、ReviewService 和 codec；asset UUID 每次教学扫描单独生成，重扫不继承复核。对象读取每次校验学生归属；教师另走对象 ACL。
- mainline1 两项最小适配已做：固定 `demo_person_ref_v1/demo_contact_v1` 白名单与检测实现；可选 `scan_columns`（默认 None 行为不变），完整解析但未扫描格明确 skipped/partial，支持对同一原文补录，原覆盖不增加。
- worker 为 `python -I -B` 独立进程，CPU 3秒/地址空间512MiB/文件输出0/FD32/core0，父进程墙钟6秒；输入仅服务器登记资源，读取资产与扫描均在受限进程。CSV 64KiB/32行/8列/256格/每格2048码点。
- 教学账本4MiB上限、数据库 revision CAS + atomic；复核/事件同事务，失败回滚，无内存回退。创建迁移 `data_lab/0001_initial.py`。
- 测试：`manage.py test data_lab.tests.test_scanning --noinput`（sqlite）：8/8 通过；涵盖受限真实 worker、四动作、逻辑位置、幂等/过期冲突、重扫、跨学生、事件失败与解析故障。证据 `docs/data-lab/evidence/d4-2.log`。

### D4-3 完成

- 四轮冻结 `B-v1` draft、同评估时刻/窗口与同输入版本；A1 mask+义务，A2 deny/recipient_forbidden，A3 defer，A4 50→51 为 mask→require_approval。每次10条与请求次数独立记录。
- 为严格保证可重放，使用服务端教师冻结参考画像（明确不是学生检测覆盖）；另绑定真实 student_profile_ref。结果不会把学生未覆盖的原扫描改写为完整。
- 所有可信环境、来源、授权、策略、时间由服务端组装并检查整个输入集。回放先隐藏程序结果；学生判断落盘后才揭示，揭示后不可覆盖原判断。
- 测试：`manage.py test data_lab.tests.test_replay --noinput`：3/3 通过。prepare/claim/consume/网络调用哨兵均0，RiskDecision/ExecutionAuthorizationRecord/DeliveryRecord/QuotaReservation均0。证据 `docs/data-lab/evidence/d4-3.log`；D4-6将扩展到完整提交流程。
- 开工全量基线跑到600秒被工具超时停止，未取得完整结果；`baseline.log` 为中断记录，不能当完整基线通过。最终全量将加长时限重跑。

### D4-4 进行中（2026-10-29 续跑检查点）

- 已核查原 `views.py`、`urls.py`、`DataLab.vue`、`api.js`，没有重建这些文件。补齐 `help.py`（模块六 AssistanceRecord、请求/展示分离、层级、教师对象权限、解析门禁）与 `submissions.py`（当前扫描/画像/四轮归属核对、冻结证据、同事务事件、幂等保存）。
- 当前 `deliver` 明确只返回已保存待交接状态；模块六核验适配尚未接通，不能视为 D4-5 完成。解析在模块六结果存在前拒绝读取。
- 修复暂停导致既有尝试无法继续；教师详情移除答案，仅返回状态和尝试，状态修改写事件；回放 DTO 增加公共 scan/profile UUID 与时间供前端绑定。
- 新增8个 API 测试；`PYTHONDONTWRITEBYTECODE=1 DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test data_lab --noinput -v 2` 已完成：25/25 通过（65.217秒），日志 `docs/data-lab/evidence/d4-4-backend.log`。前端收尾仍在进行，尚未把整包标为完成。

### D4-4 完成（API/页面本地验证，交接在 D4-5）

- 学生 `/data-lab` 与独立教师 `/data-lab/teacher` 路由、五步页、教师状态/尝试/帮助入口已完成；受控答案另走教师对象授权 API，不进入前端包。学生四轮引用按当前 scan/profile 和每变体最新已揭示结果选择，切换尝试清除旧响应状态。
- 后端 `data_lab` 25/25通过；追加教师附件权限后重跑 `data_lab.tests.test_api` 8/8通过（21.283秒），证据 `d4-4-api-final.log`。
- 前端 `node --test frontend/src/views/DataLab/*.test.js` 25/25通过；`npm --prefix frontend run build` 成功（3685 modules，42.75秒），有全站大chunk警告。源码与dist禁用答案键扫描无命中。证据 `d4-4-frontend-node.log`、`d4-4-frontend-build.log`、`d4-4-frontend-audit.log`。
- 未做真实浏览器交互验证；保存证据不代表核验成功，六→一交接仍待下一包。教师人工签收未做、课程不据此开放。

### D4-5 进行中

- 正在注册仅 data_lab 任务使用的模块六服务端证据上下文和交接适配；普通客户端不能提供该上下文，避免其他提交接口复用他人证据。真实结果、人工队列、独立性均保存在模块六，不新增成绩表。

### D4-5 完成（真实本地交接）

- 证据提交事务先冻结当前版本/摘要/依据/复核/四轮引用，后进入模块六 `create_submission → create_result → dispatch_result`；仅 data_lab 注册服务器证据上下文，通用客户端不能伪造该上下文。核验结果和人工必评任务由六持久化；执行未开展、保护未评估。
- 六→一用有界稳定 fact/event ID、冻结 payload、UUID 规范化、包括 first_attempt/payload 的严格幂等对比；失败 notice 保留，重试不重复事实/路径/分数；模块七/八通知明确 not_connected。
- 六的事件入口仅对 data_lab 超64字符 ID 缩短；其他应用规则不变。提交失败保留四的证据，恢复后不重跑扫描/回放。帮助记录直接复用六 AssistanceRecord，旧解析暴露保留 unknown。
- 本地真实链：`manage.py test data_lab.tests.test_submissions --noinput -v 2`，6/6通过（9.485秒）；证据 `d4-5-submissions-retry.log`。上轮 `d4-5-submissions.log` 停于迁移，是中断日志而非通过证据。
- 交接专项：`manage.py test data_lab.tests.test_handoff --noinput -v 2`，16/16通过（1.588秒），日志 `d4-5-handoff.log`。涵盖接收/重试、内容冲突、事务回滚、修订、教师受助和断开的下游。
- 检测核验客户样本原始 TP=8 / FP=1 / FN=2（10个正例、9个候选，精确位置+类别匹配），复核后另列，不能把补录算成原始召回。真实延迟复测和人工评分仍非本地自动测试可代替。

### D4-6 固定回归与全量对账完成；开放验收仍阻断

- 新增五类无模型完整流程：断网、超时、429、额度耗尽、全部模型禁用；每类均真实完成客户表→六核验→一事实→复盘→分配日志复测→再次核验。故障为替身注入，模型/检索入口实际调用0；复测到期时刻为模拟，不声称观察三天后的学习效果。
- 全流程 prepare_execution/claim/consume、父进程 HTTP/socket 哨兵0；RiskDecision、ExecutionAuthorizationRecord、QuotaReservation、DeliveryRecord均0。worker是受限独立进程，不把父进程mock夸成跨进程网络沙箱。
- 补充扫描失联恢复（30秒、旧键不重跑、新键新扫描、旧worker不覆盖终态）、失效CAS、损坏证据不计知识错误/通过、撤回后禁止读取；仅创建草案的登记命令，不伪造签收、不自动发布。§12矩阵在 `docs/data-lab/acceptance.md`，开放仍阻断。
- 初次9项验收：`manage.py test data_lab.tests.test_acceptance --noinput -v 2`，9/9通过（15.586秒），日志 `d4-6-acceptance.log`。随后加入登记测试后，相关套件首次被120秒工具时限停止（`d4-final-related.log`）；延长时限重跑141项，140通过、1 ERROR（240.667秒，`d4-final-related-retry.log`）。首次全量695项，677通过、11跳过、5 FAIL、2 ERROR（483.999秒，`d4-full-sqlite.log`）。这两次完整运行的新增ERROR均是草案登记冲突，不作为最终通过证据。
- 已修复：TaskPackage唯一键为全局(task_key, version)，不是目录内唯一。登记按全局键查找并显式拒绝跨目录、非兼容草案、不同能力绑定及已签收案例；登记测试改用独立空库夹具，保留跨目录冲突与不覆盖签收的断言。重跑10项验收成功（14.859秒，`d4-6-acceptance-final.log`）。修复后 `manage.py test data_lab skill_review learning_map teaching_agent --noinput -v 2`：141/141通过（234.924秒），其中data_lab 57/57；证据 `d4-final-related-fixed.log`。修复后全量完成：695发现、678通过、11跳过、5 FAIL、1 ERROR，465.972秒，进程exit 1；日志 `d4-full-sqlite-final.log`。与用户提供的dc997fe基线相比仅新增57项通过，5 FAIL/1 ERROR的测试ID集合完全相同，没有新增失败。机器对账见 `d4-reconciliation.json`，不能把全量描述为全绿。
- `manage.py check`：0问题。`makemigrations --check --dry-run`：No changes detected，但无法打开常驻SQLite库，迁移历史一致性检查发出warning；不能宣称业务库迁移状态已验证。日志 `d4-check.log`、`d4-migrations-check.log`。

### 交付收尾

- 已写根目录 `DELIVERY.md`，区分代码/本地测试/下游接通/人工签收/开放状态；保留失败和中断日志，不删除不利结果。
- 最终核查：仍为 `feat/module4-case-lab` / HEAD `dc997fe`，无commit/push；`git diff --check`通过；依赖清单/lock无变更；材料SHA匹配；前端模块与dist的 `teacher_answer` / `grading_secret` 扫描无命中，证据 `d4-worktree-audit.log`。
- D4-5本地真实交接、D4-6固定回归及全量对账已完成；课程开放验收没有通过。以下阻断项继续保留，不用自动测试替代人工签收。

## 接入和开放边界

- 教师双人审校、目录冻结及课程发布为人工门禁，候选材料保持 draft/待签收。
- 模块三材料权限服务与模块八评估中心在其他 worktree，本轮不得访问；使用现有依据卡记录及本地契约，跨 worktree 联调未接通。
- 里程碑 I 不实施。执行未开展、实际保护未评估，不计通过率。任何回放均只建议、不授权。
- Presidio 隔离验证本轮未做，未安装到公共 venv，也未升级 cryptography；当前使用固定合成规则，不能描述成“验证失败后降级”。
- 模块四自身教师 API 对象 ACL 已测试；既有模块六通用教师队列/查看等入口仍为角色级授权，本轮未改这些公共视图，CasePackage 对象授权联动未完成，属于开放阻断项。
- 真实浏览器、部署同类数据库多进程并发、普通抽查流程专门验证、真实教师评分及三日学习效果观察均未做；不能用本地测试代签。
