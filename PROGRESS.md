# 模块二首期实施进展

## 开工核对（2026-10-28）

### 已读口径

按要求依次阅读：

1. `~/workspace/module2-brief/context.md`
2. `~/workspace/module2-brief/module2-plan.md`
3. `~/workspace/module2-brief/master-plan.md`（模块二定位及第一阶段无 AI 运行方式）

### §2 真实入口与代码现状

- 总路由：`backend/ctf_backend/urls.py` 同时暴露 `/api/ai/`、`/api/ai/learning/`、`/api/agent-runtime/`、`/api/learning-map/`、`/api/skill-review/`。
- 聊天/辅导入口：
  - `AIConversationViewSet.chat`：`POST /api/ai/conversations/{id}/chat/`
  - `multi_agent_chat`：`POST /api/ai/multi-agent/chat/`
  - `multi_agent_chat_stream`：`POST /api/ai/multi-agent/chat/stream/`（SSE）
  - `solve_challenge`：`POST /api/ai/solve/`
  - `TutoringSessionView`：`POST /api/ai/learning/tutoring/`
  - `LearningRunCreateView`：`POST /api/agent-runtime/learning-runs/`
  - `GenerateContentView`、`AssessKnowledgeView`、`LearningRecommendView` 是生成/评估/推荐入口，不属于学生任务辅导核心链路，但仍需避免把客户端字段当授权。
- `TutorRequestOrchestrator.prepare` 已是多数聊天/辅导入口的会合点，但当前只组装用户画像、路由、知识与客户端提供的 `student_level`/`knowledge_point` 等字段；没有可信任务/尝试/目录版本/提示层级/运行状态，也未校验客户端提供的任务授权。`solve_challenge` 与 `agent_runtime` 仍可绕过这一会合点。
- `AgentRunStateStore` 仅支持 pending/running/completed/failed 及 JSON 中间结果；没有模块二辅导状态、状态版本、暂停/继续、幂等恢复或运行与任务尝试绑定。
- `LearningToolRegistry` 只登记三个只读工具；`run()` 通过 `getattr`，虽然当前类中没有执行器，但缺少显式白名单与任务权限矩阵校验。
- `service.py` 的知识缓存键仅含查询/题目/范围，回答缓存键仅含问题/题目/智能体/模式等；均未含主体、任务尝试、解锁状态和权限版本，命中后也没有统一任务再鉴权。
- `build_challenge_knowledge_pack_payload` 会读取启用的 `ChallengeSolution.content` 并写入知识包 `context_text`，这是学生辅导泄露教师/标准解题路径的真实缺口；普通提示词“不要泄露”不足以隔离。
- 流式入口实际先等待每个智能体返回完整内容再发 SSE，未按 token 先流出，便于首期采用“缓冲—校验—展示”；但目前仍没有统一任务权限和迟到响应隔离。
- 教学步骤在 `service.py` 使用 `asyncio.wait_for`，`TUTORING_STEP_TIMEOUT` 默认 180 秒且最低 60 秒；没有页面级 10 秒总预算、统一取消/迟到隔离或四类故障记录。
- 模块一已有真实 `TaskPackage` / `TaskAttempt`、领取与提交入口；尝试保存任务版本、目录和能力快照。
- 模块六已有确定性提交、程序核验、人工待评、帮助请求/实际展示分离、解析暴露、规则复测及幂等提交契约，核心链路本身不依赖模型。模块二应调用这些公开服务/接口，不复制任务、成绩或复测体系。
- 事件现状与方案有差异：模块一/六写 `learning_analytics.LearningEvent`，而本任务明确要求模块二一律走 `LearningBehaviorEvent` 的 `record_learning_event`；现有写入口吞掉异常、模型无独立 `event_id`、事件类型列表也未含模块二事件。模块二将增强该入口以提供 ≤64 字符事件 ID 去重/冲突拒绝和显式失败语义，不另建事件表。
- 模块四/五/八仍不存在；只实现模块二侧的动作契约适配和明确的 unavailable/not_applicable 状态，不伪造跨模块联调。

### 实施计划

1. **2-1 上下文与权限**：新增模块二应用及迁移；以 `TaskAttempt` 为唯一可信任务入口，建立运行绑定、权限版本与材料/工具矩阵；增强 LearningBehaviorEvent 写入口；所有既有学生聊天/辅导/流式入口在携带任务尝试时统一调用服务端上下文解析；从学生知识包移除标准题解，工具注册改为显式白名单。
2. **2-2 无 AI 核心链路**：模块二只做模块一任务/尝试与模块六提交/核验/复测的契约侧编排和静态任务快照；提供模块四/五动作适配状态，不补造实现；测试在模型全停用时领取→材料→提交→核验→进度→复测且外部调用为零。
3. **2-3 四级提示与状态**：实现审核提示卡、解锁规则、请求/展示分离事件、七态辅导运行、带状态版本与幂等键的暂停/恢复、教师工单/实际帮助、独立鉴权解析静态响应。
4. **2-4 API 与故障**：10 秒总预算、取消和运行/上下文版本隔离；断连/超时/429/额度耗尽分类、持久化熔断及预置卡片降级；调用事实与未知费用；缓存主体/权限版本和命中再鉴权/撤回失效；模型工具建议重新鉴权。
5. 每个工作包完成后跑对应测试并追加本文件；最后运行全量 sqlite 测试并写 `DELIVERY.md`。真实供应商、模块三/四/五/八依赖仅做契约测试，未运行项如实登记。

## 工作包进展

### 2-1 上下文与权限

状态：完成（2026-10-29）。

- 新增 `teaching_agent` 应用、可信 `TaskAttempt`/`TeachingRun` 上下文解析、服务端材料与工具权限矩阵；客户端自报的任务版本、提示层级、运行状态和权限版本不参与授权。
- 新增运行创建/读取 API，并对尝试、运行、挑战绑定做所有权校验；旧聊天、辅导、SSE 与 agent-runtime 的任务绑定均经可信解析器，`solve` 直出完整题解入口对学生任务关闭。
- 学生模型上下文只含任务目标、尝试状态、受控证据引用、运行版本与学生材料引用；不含身份资料、教师答案、评分键、隐藏验证器或原始提交。
- `LearningBehaviorEvent` 增加可空且唯一的 64 字符 `event_id`，原写入口支持严格幂等：同 ID 同内容返回原事件，同 ID 不同内容拒绝，旧调用仍保持兼容的 best-effort 语义。
- 从学生知识包生成路径移除 `ChallengeSolution.content`，知识包不再标记或缓存标准题解；工具执行改为显式白名单并对任务上下文再次鉴权。
- 迁移：`learning_analytics/0011_learningbehaviorevent_event_id_and_more.py`、`teaching_agent/0001_initial.py`。
- 证据：`backend/teaching_agent/tests/test_context_permissions.py` 覆盖服务端上下文、材料隔离、跨学生尝试/运行/SSE 拒绝、事件去重冲突、知识包题解隔离及越权工具拒绝。
- 测试：
  - `manage.py test teaching_agent.tests.test_context_permissions --verbosity 2`：5/5 通过。
  - `manage.py test teaching_agent.tests.test_context_permissions agent_runtime.tests ai_assistant.test_main_chain ai_assistant.test_performance`：46/46 通过。

### 2-2 无 AI 核心链路

状态：完成（2026-10-29）。

- 复用模块一领取/任务尝试和能力进度契约、模块六提交/确定性核验/复盘卡/复测契约，没有复制任务、成绩或复测系统。
- 教学运行返回静态任务快照、已净化材料、验收口径和模块六提交地址；隐藏验证器及学生解析引用不进入普通任务快照。
- 新增幂等练习动作登记；只读观察可登记，模块四沙箱明确返回 `unavailable`，模块五数据导出明确返回 `not_applicable`，仅存摘要哈希而不伪造执行证据。
- 迁移：`teaching_agent/0002_practiceaction.py`。
- 证据：`backend/teaching_agent/tests/test_no_ai_flow.py` 覆盖领取→材料→练习登记→模块六提交/程序核验→模块一进度→复盘卡→新场景复测完整链路。
- 无 AI 证明：测试关闭路由、专员、语义检索等 AI 开关并在模型服务边界设置“调用即失败”；完整链路通过，`ModelCallRecord=0`，模型边界调用次数为 0。
- 测试：`manage.py test teaching_agent.tests.test_no_ai_flow`：1/1 通过。

### 2-3 四级提示与状态

状态：完成（2026-10-29）。

- `HintCard` 固化 1—4 级审核卡与版本化解锁规则；默认逐级解锁，可增加失败次数和尝试状态条件。提示请求不返回内容，实际展示才写 `shown`、推进提示层级并产生独立展示事件。
- 复用模块六 `AssistanceRecord` 作为帮助事实，不另建成绩/帮助体系；模块二 `HintDelivery` 仅绑定运行、卡片版本、权限版本和请求幂等关系。
- 七种辅导状态已冻结到 `TeachingRun`；新增带预期 `state_version` 的暂停/继续，继续结果以数据库 `ResumeReceipt` 持久化。同请求同内容在新客户端/进程语义下返回原结果，过期版本和同键异内容返回 409。
- 新增教师工单、跨学生所有权检查、教师角色实际帮助及模块六实际帮助记录；工单等待不改变任务成绩。
- 新增独立鉴权学生解析 API：仅自有运行、任务程序核验通过后读取 `StudentAnalysis` 静态内容；普通运行上下文、提示、知识包和模型上下文不包含解析正文。
- 材料撤回、卡片停用或权限版本变化时，已请求但未展示的提示会在展示时重新鉴权并拒绝。
- 迁移：`teaching_agent/0003_hintdelivery_resumereceipt.py`。
- 证据：`backend/teaching_agent/tests/test_hints_state.py` 覆盖四级逐级解锁、请求/展示分离、撤回后拒绝、重启语义恢复、重复恢复、过期版本、跨学生工单、实际教师帮助、解析锁定与通过后静态访问。
- 测试：`manage.py test teaching_agent.tests.test_hints_state --verbosity 2`：3/3 通过。

### 2-4 API 辅导与故障处理

状态：完成（2026-10-29）。

- 新增任务绑定辅导 API `POST /api/teaching/runs/{run_id}/tutor/`，页面级总等待预算硬上限 10 秒；既有 180 秒教学步骤仅保留给非任务旧链路。携带任务尝试的旧聊天/SSE 返回 409 并要求进入新入口，避免绕过预算、权限缓存和展示校验。
- API 调用在输出前缓冲并校验提示层级、结构和工具建议；模型声称“已授权”无效，任何未在任务工具矩阵中的建议都会使整次响应拒绝并切换审核卡片，不执行工具。
- 超时使用异步 `wait_for` 取消等待并记录 cancellation=`requested`；请求一旦降级或运行/上下文/权限版本变化，迟到结果只标记 `late_response_discarded`，不能写回当前页面。
- 故障分类覆盖断连/供应商错误、timeout、429、quota exhaustion；实现持久化 closed/open/half-open 熔断、到期恢复探测和配额耗尽需管理确认的无限期打开状态。未审核阈值以 `config_version=unapproved-default` 标明，并在交付依赖中保留配置审核。
- 降级使用一级审核预置卡片并记录真实展示；无卡片时只返回可继续练习/确定性提交的固定状态说明，不虚构证据或调用事实。
- `ModelCallRecord` 保存可取得的 provider/model/template/token/latency/status/error/retry/cancellation/cost basis；供应商未返回的 token 和费用保持 `NULL`/`unknown`，不写零。
- 持久化响应缓存键包含学生、尝试、运行、学科/任务主体、提示层级、上下文版本、权限版本、材料哈希和模板版本；命中后重新鉴权，材料撤回、卡片变更或权限版本更新均不能读取旧内容。
- 迁移：`teaching_agent/0004_tutorrequest_material_hash_tutorresponsecache.py`。
- 证据：`backend/teaching_agent/tests/test_api_failures.py` 覆盖成功调用事实、权限缓存、撤回失效、超时取消、迟到隔离、断连、429、配额、熔断与恢复探测、审核卡降级、越权工具建议拒绝及旧流式绕过关闭。
- 测试：
  - `manage.py test teaching_agent.tests.test_api_failures --verbosity 2`：5/5 通过。
  - `manage.py test teaching_agent.tests`：15/15 通过。
  - `manage.py test teaching_agent.tests agent_runtime.tests ai_assistant.test_main_chain ai_assistant.test_performance`：56/56 通过。
  - `manage.py makemigrations --check --dry-run`：无遗漏迁移；`manage.py check`：0 问题。

## 全量 SQLite 回归（2026-10-29）

- 命令：在 `backend/` 执行 `DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH=/tmp/ctf-module2.sqlite3 ~/workspace/ctf-venv/bin/python manage.py test --verbosity 1`，完整输出保存到 `/tmp/ctf-module2-full-sqlite-20261029.log`。
- 结果：发现并运行 638 项，严格通过 621、跳过 11、FAIL 5、ERROR 1；按“未 FAIL/ERROR”口径为 632/638。全量进程非零退出。
- 与给定基线（512 项、501 未失败；4 challenges proxy FAIL、6 mainline1 loader ERROR、1 learning_map jsonschema ERROR）对账：
  - 4 个 `challenges.tests.ChallengeProxyAccessTests` FAIL 完整复现，名称与基线类别一致。
  - `mainline1` loader 实际只汇总为 1 个 `mainline1.test_settings` ERROR，首个缺失配置为 `MAINLINE1_TEST_PORT`；没有出现基线描述的 6 个独立 loader ERROR，不能据此宣称其余已修复。
  - 本环境没有出现 `learning_map` 的 `jsonschema` 导入 ERROR，不能据此宣称代码已修复；仅说明本次环境/依赖下未复现。
  - 基线清单之外新增 1 个 FAIL：`mainline1.tests.test_semantic.SemanticTests.test_real_transport_constructor_pins_options_without_provider_registry`，断言运行时 `sys.modules` 不含 `ai_providers`，但 Django 应用加载后该模块已存在。单独运行该测试仍失败，记录为当前环境/主线回归差异；未修改不属于模块二范围的 `mainline1`。
- 实际失败清单：
  1. ERROR `mainline1.test_settings` — `KeyError: MAINLINE1_TEST_PORT`。
  2. FAIL `test_access_url_does_not_include_reusable_token` — URL 仍含 `access_token=`。
  3. FAIL `test_proxy_accepts_authenticated_owner_without_cookie` — 期望 200，实际 401。
  4. FAIL `test_proxy_rejects_authenticated_non_owner` — 期望 403，实际 401。
  5. FAIL `test_proxy_rejects_unsafe_session_request_without_csrf` — 期望 403，实际 401。
  6. FAIL `test_real_transport_constructor_pins_options_without_provider_registry` — `ai_providers` 已在 `sys.modules`。

## 收尾交付（2026-10-29）

- 已完成根目录 `DELIVERY.md`，汇总修改文件、迁移、API、实际测试命令与结果、全量失败对账、证据位置、未运行项及模块三/四/五/八和真实供应商剩余依赖。
- 未新增收尾功能；未 commit、未 push。
