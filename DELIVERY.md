# 模块八第一阶段交付记录

日期：2026-10-29。工作目录：`/home/hatch/workspace/ctf-module8`；分支：`feat/module8-evaluation-center`；基底：`dc997fe`。

**M8-1 至 M8-5 的代码、本地适用范围自动测试与前端构建已完成。全量保留6项既存失败/错误，无新增回归。真实设施联调未完成，不等于两条试点已满足全部开放条件。**

改动留在worktree待审查；未commit、未push，未读取或修改主检出与模块五worktree。没有新增Python/Node运行依赖，没有引入平台组件、LangGraph或promptfoo。

## 1. 交付范围

| 工作包 | 已实现并本地验证 | 边界 |
|---|---|---|
| M8-1 | M1/M6只读版本化投影、当前/历史结果、首次资格、帮助与事件对账、真实复测、更正链 | 不从浏览器事件生成成绩，不写推荐/画像，不跨版本拼接提升 |
| M8-2 | 学生本人/教师管理员查询、最小字段、筛选、显式演示隔离、M2运行/费用摘要、教师证据页 | 未知token/费用保持null；正式空数据不自动补演示；浏览器联调未执行 |
| M8-3 | 提案周边待办、五类队列、revision认领冲突、转交审计、处理摘要、当前独立新场景复测验证、更正重算回执 | 成绩和源队列处理仍归M6；本地回执不伪装为上游推送已接通 |
| M8-4 | 冻结清单、独立账号、逐例持久化、预算/中断、三组报告、digest、测试专用令牌适配器、M7真实报告校验 | 25例合成规则回归不是全球教学/生产准确率；模型/提示/知识库变化未做真实API评测 |
| M8-5 | 版本化场景1–10测试选择器、故障到教师处理/复测的真实本地API流程、缺依赖拒绝成功、缺陷修复与全量对账 | 网络实例/物理隔离等仅有消费侧契约，不冒充真实验收 |

统一指标包含分子、分母、缺失量、窗口、版本与来源；没有合并总分。M3/M4/M5显示未接通，执行未开展，实际保护未评估。平台内独立不代表已排除平台外帮助。

## 2. 修改文件清单

### 新应用 `backend/evaluation_center/`

- 基础：`__init__.py`、`apps.py`、`models.py`、`permissions.py`、`provenance.py`、`metrics.py`。
- 事实与查询：`projections.py`、`runtime.py`、`serializers.py`、`views.py`、`urls.py`。
- 教师协作：`operations.py`、`operations_views.py`。
- 评测内核：`evaluations.py`、`evaluation_fixtures.py`、`evaluation_views.py`、`test_settings.py`、`test_urls.py`。
- 固定验收：`acceptance.py`、`management/__init__.py`、`management/commands/__init__.py`、`management/commands/test_evaluation_acceptance.py`。
- 文档：`README.md`。
- 迁移：`migrations/__init__.py`及下节三个迁移。
- 测试：`tests/__init__.py`、`factories.py`、`test_metrics.py`、`test_permissions.py`、`test_provenance.py`、`test_projections.py`、`test_api.py`、`test_operations.py`、`test_evaluations.py`、`test_acceptance.py`、`test_acceptance_manifest.py`。

### 既有应用与前端

- `backend/ctf_backend/settings.py`：仅新增 `'evaluation_center'` 注册行。
- `backend/ctf_backend/urls.py`：仅新增 `/api/evaluation/` include行。
- `backend/feedback_center/services/candidates.py`：最小报告信任接缝，详见第5节。
- `backend/feedback_center/tests/test_phase3.py`：原假报告fixture替换为真实隔离评测服务生成的报告。
- `backend/feedback_center/tests/test_forged_report_repro.py`：保留原复现文件，反转三个攻击断言并扩展为11项安全回归。
- `frontend/src/api/evaluation.js`：新增本应用客户端。
- `frontend/src/teacher/LearningEffectAnalysis.vue`：替换自动混入演示的逻辑，接真实证据查询与显式模式。
- `frontend/src/teacher/TeacherOperations.vue`：新增协作操作区、实时源状态、复测证据与审计。
- 根目录 `PROGRESS.md`、`DELIVERY.md`：重建阶段进度与交付记录。

未修改M1/M2/M6的成绩、事件、画像或提案状态模型/服务；未修改生产导出策略。

## 3. 数据迁移与配置

三个迁移均已在Django测试库执行；**未对实际业务数据库运行migrate**。

1. `0001_initial.py`：NonFormalAccount，显式标记demo/offline来源。
2. `0002_projectionreceipt_teachertodo_todoaction.py`：TeacherTodo、TodoAction、ProjectionReceipt。
3. `0003_evaluationrun_evaluationreport_evaluationcaseresult.py`：EvaluationRun、EvaluationCaseResult、EvaluationReport及`manage_evaluation`权限。

部署审查通过后可按现有部署流程运行 `python backend/manage.py migrate`；此命令本次未执行到实际数据库。

- 正式/演示/离线账号应由部署负责人显式登记，不能靠用户名猜测。页面内置演示是无数据库写入的合成响应。
- `evaluation_center.test_settings`仅供隔离测试：内存数据库、本地缓存、测试用密码哈希；不得当生产配置。
- 评测写服务要求 `EVALUATION_ISOLATED_TESTS=True` 且 `ROOT_URLCONF='evaluation_center.test_urls'`；操作者还须为有效、具有评测权限、标记offline的独立账号。正式配置下管理员也不能执行评测。
- 测试适配器需显式配置 `EVALUATION_SERVICE_TOKEN`、`EVALUATION_SERVICE_ACCOUNT_ID`，没有默认有效凭证；认证头为 `Authorization: Evaluation <token>`。请求只提交冻结run_id，不接受自带角色、任意URL或案例输入。
- M7第三阶段创建/发布开关保持原默认值，本次没有启用生产发布。

## 4. API与数据语义

公共前缀：`/api/evaluation/`。

| 路径 | 方法 | 权限/用途 |
|---|---|---|
| `students/` | GET | 教师/管理员，最小学生列表，显式formal/demo |
| `learning/` | GET | 学生仅本人；教师/管理员平台范围；按学生/任务/知识点/目录版本/时间筛选 |
| `attempts/<uuid>/` | GET | 本人或教师/管理员；展开安全的事实/版本/帮助/事件对账 |
| `runtime/` | GET | 教师/管理员；M2持久调用账本摘要，不返回响应正文/供应商凭证 |
| `todos/` | GET、POST | 教师/管理员；五类队列，创建可绑定本人提案的协作待办 |
| `todos/sync/` | POST | 幂等导入求助、开放题必评、抽查（含需更正）、争议 |
| `todos/<uuid>/` | POST | revision + claim/transfer/handle/verify；非负责人拒绝，过期revision返回409 |
| `receipts/` | GET、POST | 读取/显式消费M6通知并保存本地幂等重算回执 |
| `runs/` | GET、POST | 独立评测权限；列出/创建冻结运行，写入还需隔离环境和账号 |
| `runs/<uuid>/` | GET | 冻结摘要与完整性，不返回任意配置正文 |
| `runs/<uuid>/execute/`、`interrupt/` | POST | 隔离评测执行/中断封存 |
| `reports/<uuid>/` | GET | 独立评测权限，校验后返回reference与JSON报告，可保存响应作为报告文件 |

`/api/evaluation/adapter/` **只存在于专用测试URLConf**，不注册到正式应用路由；请求鉴权也复验环境与服务端账号。

普通教师不自动具有系统评测权限；管理员/超级管理员，或持有`evaluation_center.manage_evaluation`的教师才可读评测报告。

协作注意事项：
- 原提案不因M8待办操作而改变状态。源队列实时状态与导入快照分别展示。
- 处理完成不等于改善；须同学生/原尝试关联的新场景、干预后实际提交、当前平台内独立通过复测。`verified`不是因果效果证明。
- 更正使证据失效时重开待验证；即便通知尚未消费，读侧也不展示陈旧成功。
- 回执按学生、任务/目录版本和原提交日窗口重算，保留原结果引用；不改写源notice。当前为显式消费，没有新建后台调度平台。
- M8数据库写失败返回503 / `save_pending_retry`，更新和审计同事务，不先报成功。

## 5. 模块七安全闭环（单列）

登记、完成评测、审批、发布有效性检查均解析M8真实持久记录，验证：run/report真实存在、完整报告digest、冻结配置/清单/逐例结果、候选UUID、基准与候选配置内容摘要、版本及任务范围。复制候选自身digest不能伪造运行；发布范围不能扩大到未测任务。

原三个攻击均被拒绝；额外覆盖真实报告缺/伪造摘要、相同配置不同候选、配置正文变更但未更新digest、基准/候选版本和scope变更、审批/发布复验及HTTP挂接。合法完整报告仍可走原M7生命周期；真实完整fail/insufficient_evidence走需修订，不搬迁M7状态机。

固定集合 `m8-synthetic-regression/1` 仅支持合成 TASK-X@1.0.0 的 `export_record_limit` 单因素：100→120正例可通过，100→200产生真实规则退化与fail。其它scope、模型、提示、知识库、组合配置不能借固定模型输出获准。

`report_digest`覆盖全部报告（含运行ID、时间及耗时）；`replay_digest`用于比较同版本逻辑证据。不要求不同运行的完整报告digest相同。

## 6. 实际验证与证据

Python命令均使用 `/home/hatch/workspace/ctf-venv/bin/python`，工作目录为本worktree。下列秒数是测试主体耗时，不是包含建库的总墙钟时间。

| 检查 | 结果 | 证据 |
|---|---|---|
| M8-1/2整包 | 44/44通过 | `/tmp/module8-m8-2.log` |
| M8-3整包 | 60/60通过，10.536秒 | `/tmp/module8-m8-3.log` |
| M8-4内核 | 44/44通过，20.058秒 | `/tmp/claude-0/-home-hatch-workspace-ctf-module8/f4ae79c9-a207-4447-9e56-96395927c7d1/tasks/bp71drbbo.output` |
| M7状态机及安全闭环 | 32/32通过，228.939秒 | `/tmp/module8-m7-trust-final.log` |
| M1/M2/M6源回归 | 84/84通过，959.238秒 | `/tmp/module8-source-regression.log` |
| M8-5新增固定集成 | 8/8通过，2.865秒 | `/tmp/module8-m8-5-focused.log` |
| 最终M8整包 | **115/115通过，44.597秒** | `/tmp/module8-m8-5-final.log` |
| 最终全量普通配置SQLite | **764发现、747通过、11跳过、5 FAIL、1 ERROR**，2169.157秒，退出码1 | `/tmp/module8-full.log` |
| 前端最终构建 | 成功，3分22秒；大于500kB的chunk警告 | `/tmp/module8-frontend-build-final.log` |
| 迁移一致性、Django check、Python compileall、git diff --check | 通过 | 实际命令如下 |

主要实际命令：

```sh
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test evaluation_center --noinput
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test feedback_center.tests.test_phase3 feedback_center.tests.test_forged_report_repro --noinput
DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH=:memory: /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test teaching_agent learning_map skill_review --noinput
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test backend --noinput
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py makemigrations evaluation_center --check --dry-run --settings=evaluation_center.test_settings
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py check
/home/hatch/workspace/ctf-venv/bin/python -m compileall -q backend/evaluation_center backend/feedback_center/services/candidates.py backend/feedback_center/tests/test_forged_report_repro.py
git diff --check
npm ci --prefix frontend --ignore-scripts --no-audit --no-fund
npm run build --prefix frontend
```

`npm ci`安装的是现有锁定依赖（241包），没有修改依赖清单/锁文件。基础settings会将相对字符串`:memory:`拼成文件路径；一次迁移历史检查生成的空文件已检查并删除，测试仍用Django内存测试库。后续迁移检查使用专用test_settings。

中间失败均保留记录：M8-3测试fixture的返回值解包/来源枚举错误；M7的insufficient枚举对接错误；M8整包的条件URLConf缓存与错误测试选择器。均修正后复跑，不把中途失败或中断记为通过。最初基线复跑600秒被终止，最终全量使用7200秒时限并完整结束。

### 全量基线对账

| 项目 | 基底dc997fe | 最终 | 差值 |
|---|---:|---:|---:|
| 发现 | 638 | 764 | +126 |
| 通过 | 621 | 747 | +126 |
| 跳过 | 11 | 11 | 0 |
| FAIL | 5 | 5 | 0 |
| ERROR | 1 | 1 | 0 |

新增126项 = 115项M8测试 + 11项M7安全回归；基底通过数未下降。以下集合与context.md已知失败一致，未修改它们来掩盖失败：

1. `challenges.tests.ChallengeProxyAccessTests.test_access_url_does_not_include_reusable_token`：URL仍包含可复用token。
2. `...test_proxy_accepts_authenticated_owner_without_cookie`：401而非200。
3. `...test_proxy_rejects_authenticated_non_owner`：401而非403。
4. `...test_proxy_rejects_unsafe_session_request_without_csrf`：401而非403。
5. `mainline1.tests.test_semantic.SemanticTests.test_real_transport_constructor_pins_options_without_provider_registry`：平台路由已导入ai_providers，与隔离断言冲突。
6. `mainline1.test_settings`加载错误：缺少MAINLINE1_TEST_PORT。

完整日志SHA256：`0e020f87d86732a59a069e4de4481e52f2144d2a9437cfdc3629358bac259c9c`。日志为本机/tmp证据，不是已上传或永久归档的工件。

## 7. 固定验收与未运行项目

`acceptance.py`的 `m8-phase1-acceptance/1` 将场景1–10映射至真实自动测试，并逐项声明依赖。选择器解析与去重已测试；所选测试路径已被最终全量覆盖。另提供 `manage.py test_evaluation_acceptance` 快捷命令，**该快捷命令本身未额外运行一次**，避免将重复运行伪算为新样本。

- 场景1–5：本地版本/授权/来源/帮助/保存与更正路径已测试；真实课程签收、M3全部检索路径及跨服务恢复仍需联调。
- 场景6–7：注入断连、超时、429、额度耗尽及全模型停用时，实际调用M1/M2/M6 API走通数据规则、人工必评、教师处理和新场景复测。超时测试用50ms缩短预算并断言小于10秒；不是对真实供应商十秒SLA的实测。
- 场景8：只有未接通与拒绝浏览器自报成功的契约；宿主/内网/生产地址、白名单、学生实例隔离、资源回收、暂停和凭证回收均未做真实靶场验收。
- 场景9：冻结无网络规则回放、预算/中断与报告信任已测试；真实新模型/提示/知识库API比较未开展。
- 场景10：数据线现为M1/M2/M6合成本地闭环；模块四实验台未接通。网络线缺模块五服务端挑战/修复证据，不能宣称两条真实试点均已走通。
- M6源提交HTTP数据库错误仍返回通用失败；本应用没有擅改其错误契约。M8自身待办写失败已明确返回保存待重试。
- 未做浏览器/真实后端联调，未对实际数据库migrate；没有生产部署、真实API调用或外部报告发布。
- 里程碑I未开展；无实际脱敏/交付/配额/回执/结算/保护通过率，不据此开放执行课程。

方案理解、代码完成、本地检查通过与真实联调通过以上分别登记，不互相替代。

## 8. 保留项补做（第二轮，2026-10-29）

本节为第二轮增量，前述第一轮“未运行”记录保留其当时含义。**第一、三、四项已实测；第二项的真实HTTP请求、持久故障报告及M7故障报告挂接已实测，但成功模型输出/有效两配置比较仍开放。** 不将网关报错、mock测试或模型目录可见算作模型评测通过。

### 8.1 逐项结论

| 保留项 | 已实测 | 仍开放及原因 |
|---|---|---|
| 验收快捷命令 | 真正执行 `test_evaluation_acceptance --verbosity 2`，原`m8-phase1-acceptance/1`选择器139/139通过，44.803秒，退出0；完整输出含迁移与逐例名称 | 这是补跑，不增加139个样本；扩展后`/2`选择器的底层测试在最终两应用回归中覆盖，未另行声称执行过`/2`快捷命令 |
| 真实模型批次/M7 | 实际向127.0.0.1:8317发送74次chat HTTP请求，按M8现有模型保存运行、逐例、报告；72次503批次的完整不足证据报告成功经M7挂接并进入needs_revision；两份403缺例报告被拒绝挂接 | 没有取得任何有效模型输出：flash先403、随后72次503，v4.1也403。真实成功/失败分类通过率无法测量；需恢复网关模型chat调用后重跑。不是模型质量差或0%通过率的结论 |
| 固定因素扩展 | 新集合`m8-live-export-classification/1`及prompt_version/model_id因素；6例、2模型、2提示、每臂2次观测；登记/隔离/持久化/信任/重试/密钥/最小输入测试通过 | 模型间有效比较、知识库对比未实测；注册支持不等于已取得真实模型结果 |
| 真实数据库迁移 | 新建磁盘SQLite scratch库，真实执行M8三项迁移及依赖，随后完整migrate补齐账号/M7所需表；新进程能读回运行与报告 | PostgreSQL未做：无pg_isready、127.0.0.1:5432不可用、常用socket不存在；未安装或启动新数据库。未迁移业务库 |

### 8.2 实现与配置增量

- 新增 `live_fixtures.py`、`live_evaluations.py`、`gateway.py`、`scratch_settings.py`、`management/commands/run_live_evaluation.py` 和对应测试；扩展现有evaluations分发、API登记集合字段、acceptance注册与README。继续复用 EvaluationRun / EvaluationCaseResult / EvaluationReport，不新增数据模型/迁移，不迁移M7状态机。
- 普通模式仍默认无网络合成回放；真实模式要求既有隔离URLConf/offline管理账号门禁及独立live开关。接口不能传自带用例、角色、任意URL或密钥。所有生产发布开关保持关闭。
- 原 `m8-synthetic-regression/1` 25例不变，固定内容摘要断言为 `4de3c74803971973b2028c4d1600175120e6f640aafd389bf2f1a942790ff5b1`；固定验收选择器更新为`m8-phase1-acceptance/2`，显式区分无网络规则集合、mock传输合同测试与手动授权真实批次。
- 网关地址固定为 `http://127.0.0.1:8317/v1/chat/completions`，不走环境代理、不跟随重定向。凭据从指定config.yaml内存读取；本机实际采用 `access.api-keys`，顶层`api-keys`是供应商分组。兼容旧数组结构，绝不选择上游供应商密钥作为客户端密钥。
- 两臂共用合成输入，每次仅发送该例必要字段和对应提示，不发送预期答案、整表、学生身份、其他用例或无关上下文。报告保存规范化action、白名单错误及usage，不保存模型原始正文/推理或原始错误体。配置快照无凭据。
- 429/502/503/504及连接/超时最多3次尝试，等待2/4秒后重试；401/403不盲重试。每socket操作最多30秒，批次有总预算，但不宣称对慢流作硬墙钟取消。每次最多256个输出token，价格未知，没有伪造费用上限或免费假设。
- 未安装新依赖、未改依赖清单；使用现有LangChain环境已包含的PyYAML 6.0.3。公共settings/urls仍仅第一轮的本应用注册/include各一行。没有改主检出或模块五worktree。

### 8.3 真实批次、冻结配置与事实结果

原集合输入仍为合成数据；`mode=live_gateway, simulated=false, input_source=synthetic`只表示请求使用真实传输，不表示真实学生材料、真实生产操作或成功模型推理。

| 运行ID | 请求模型/提示 | 真实chat尝试 | 模型有效输出 | 报告与M7结果 |
|---|---|---:|---:|---|
| `7d87fb1f-52db-493d-b9ab-52ddfeda6ee3` | flash，v1→v2 | 0 | 0 | 首次解析器不支持嵌套配置，credentials_unavailable；6例均无证据，完整insufficient_evidence报告登记为needs_revision；**不计真实批次** |
| `082a079b-9c96-4b94-bdca-7285b5deda19` | deepseek-v4-flash，v1→v2 | 1（403） | 0 | 1条逐例记录，缺5例，不完整报告被M7拒绝 |
| `6cdc353f-d8b0-4d46-abd2-ab07d9b90546` | deepseek-v4-flash，v1→v2 | 72（全部503） | 0 | 6例×两臂×2观测均按3次上限等待重试；完整故障报告挂接并进入needs_revision |
| `25b6dfe9-af20-4ace-acc3-d2db633164b2` | deepseek-v4.1，v1→v2 | 1（403） | 0 | 1条逐例记录，缺5例，被M7拒绝挂接 |

两个配置的提示版本全名为 `export-classifier/v1`、`export-classifier/v2`；参数固定 `temperature=0, max_tokens=256`。同一批次的模型ID相同，唯一因素为prompt_version。模型目录GET实测列出了两者，但错误响应没有证明上游完成了推理，表中是**请求模型ID**，不是伪造的供应商执行确认。

完整故障报告：
- report_id：`b4ca91da-d78c-4999-9299-22a57c2ae75b`
- report_digest：`b954a7996eda8a28d078abbd46bc8d31d3b6907d2e70ffcb8ba10f885633ddea`
- baseline_config_digest：`d806ff73ae2bd6efd21df30afa272c98cd1ef77ab294772c093045c5e1a5129a`
- candidate_config_digest：`3740a2b521c56c50a082620d622eb66d536464a8272d0cb53e9873c52a4c144a`
- 两臂各6例；有效判定分子0、分母0、缺失6，**value=null、受环境影响**。prompt/completion/total token均未提供，全部为null；费用null。72次请求是重试次数，不是72个新案例或模型成功响应。
- M7调用 `attach_report` → `complete_evaluation`，事件含report_attached / evaluation_started / evaluation_not_passed；状态needs_revision。没有调用approve/activate或修改教学配置。

中间问题没有抹去：最初误把供应商分组名用于模型目录探测得到401；修正读取结构后目录调用成功。首次零调用持久报告与随后403/503报告全部保留。诊断脚本只观测原始HTTPError中的白名单关键词后重抛，没有替换响应、注入模型答案或把mock结果写入真实批次；其shell退出0只是捕获异常后结束，不是评测通过。403根因尚未证实，不能据此断言客户端凭据错误或模型质量问题。

### 8.4 Scratch迁移与实际命令

独立库：`/tmp/m8-scratch-round2.CiF1Ua/evaluation.sqlite3`，非Django内存测试库，非业务库。0001/0002/0003在真实磁盘库应用成功；`showmigrations evaluation_center`三项均[X]。关闭live开关的新进程回读4份报告，均通过M8校验；两份完整不足证据报告已挂接，两份缺例报告未挂接，全部未发布。

本轮主要实际命令（均从ctf-module8运行）：

```sh
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test_evaluation_acceptance --verbosity 2
EVALUATION_SCRATCH_DATABASE=/tmp/m8-scratch-round2.CiF1Ua/evaluation.sqlite3 DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py migrate evaluation_center --noinput --settings=evaluation_center.scratch_settings
EVALUATION_SCRATCH_DATABASE=/tmp/m8-scratch-round2.CiF1Ua/evaluation.sqlite3 DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py migrate --noinput --settings=evaluation_center.scratch_settings
EVALUATION_SCRATCH_DATABASE=/tmp/m8-scratch-round2.CiF1Ua/evaluation.sqlite3 EVALUATION_LIVE_GATEWAY=1 DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py run_live_evaluation --settings=evaluation_center.scratch_settings
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test evaluation_center feedback_center --noinput --verbosity 2
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py makemigrations evaluation_center --check --dry-run --settings=evaluation_center.test_settings
```

第二次flash诊断批次与v4.1替代模型批次经同一scratch配置下的`manage.py shell`调用M7候选服务、M8 create_run/execute_run、M7 attach_report/complete_evaluation；未伪称它们由快捷命令成功退出。完整命令与执行过程见本会话，本地输出证据如下。

### 8.5 最终测试与证据

- 最终两应用套件：**217发现、217通过，93.473秒，退出0**，其中M8 **164/164**、M7 **53/53**；M8相比第一轮新增49项回归。早一轮215项通过后补齐2项嵌套密钥结构测试，再执行最终217项。
- live记录/清单聚焦25/25通过；网关聚焦27/27通过。测试使用mock供应商，不算真实API样本。
- 迁移无漂移，Python编译与diff空白检查通过。第二轮没有前端改动、没有重跑浏览器/前端构建，也未重跑整仓全量；第一轮764项基线对账不能冒充第二轮全仓结论。

| 证据 | 路径 |
|---|---|
| 快捷命令完整输出 | `/tmp/module8-round2/acceptance-command.log` |
| M8定向迁移 / scratch全迁移 | `/tmp/module8-round2/migrate-evaluation.log` / `migrate-scratch-all.log` |
| 首次零调用、403、503、替代模型输出 | `/tmp/module8-round2/live-batch-key0.log`、`live-batch.log`、`live-diagnostic.log`、`live-alternate-model.log` |
| 新进程持久回读 | `/tmp/module8-round2/persistent-readback.log` |
| 最终M8+M7测试 | `/tmp/module8-round2/m8-m7-regression-final.log` |

关键SHA256：快捷日志 `b3d6e146d13810f4445d70569fc550391f8b2784068f6e1a3cda21469ee24c2b`；最终回归 `ab8990f2d55112107042e5efdf66768dfc95efb85da2e12474b33bfd64ed7e63`；M8迁移 `67a5767e13702b8ee0e6c20c15734037aba12afb186f4d8f7fe596a58a82995e`；503诊断批次 `c400af79e71bc38929509a613da0e60bec9ac1dec7a50ea939c6885149eeb484`。

所有日志及scratch库用实际客户端密钥字节作本机检查，无密钥值命中；检查只输出泄漏数量0。密钥未打印、未写入文件/数据库/日志、未传入模型文本。工件在本机/tmp，未上传、未承诺永久保留。

本轮未触及模块四实验台、里程碑I、模块三检索路径、课程人工签收、模块五靶场证据；不依赖并行模块五会话。无commit、无push、无部署或对外报告发布。
