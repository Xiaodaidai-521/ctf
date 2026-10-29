# 模块二首期交付说明（工作包 2-1 至 2-4）

交付日期：2026-10-29  
分支：`feat/module2-teaching-agent`  
范围：任务型 AI 教学智能体首期；未 commit、未 push。

## 1. 已完成工作包

| 工作包 | 状态 | 交付摘要 |
|---|---|---|
| 2-1 上下文与权限 | 完成 | 可信任务/尝试/运行上下文、材料与工具矩阵、学生知识包题解隔离、旧入口适配、LearningBehaviorEvent 幂等事件 ID |
| 2-2 无 AI 核心链路 | 完成 | 复用模块一领取/进度与模块六提交/核验/复测，静态材料快照，模块四/五缺失依赖的契约状态 |
| 2-3 四级提示与状态 | 完成 | 四级审核卡、请求/展示分离、七态运行、版本化暂停/恢复、教师工单、独立鉴权静态解析 |
| 2-4 API 与故障处理 | 完成 | 10 秒总预算、取消与迟到隔离、故障分类、熔断/探测、预置卡降级、调用事实、权限缓存、工具建议复核 |

详细逐包记录和证据见 [`PROGRESS.md`](PROGRESS.md)。

## 2. 修改文件清单

### 2.1 新增 `teaching_agent` 应用

- `backend/teaching_agent/__init__.py`
- `backend/teaching_agent/apps.py`
- `backend/teaching_agent/models.py`：运行、提示卡、提示交付、恢复回执、教师工单、学生解析、辅导请求、模型调用、熔断、练习动作、响应缓存。
- `backend/teaching_agent/context.py`：从 `TaskAttempt`/`TeachingRun` 解析可信上下文和所有权。
- `backend/teaching_agent/permissions.py`：学生材料净化、服务端材料/工具矩阵和敏感字段隔离。
- `backend/teaching_agent/events.py`：≤64 字符事件 ID 和模块二事件统一写入适配。
- `backend/teaching_agent/core_flow.py`：静态任务快照及模块四/五契约侧练习动作适配。
- `backend/teaching_agent/tutoring_state.py`：提示、状态、暂停/恢复、教师帮助和解析鉴权。
- `backend/teaching_agent/api_tutoring.py`：有界 API 辅导、故障/熔断、降级、调用事实、迟到隔离和缓存。
- `backend/teaching_agent/serializers.py`
- `backend/teaching_agent/views.py`
- `backend/teaching_agent/urls.py`
- `backend/teaching_agent/tests/test_context_permissions.py`
- `backend/teaching_agent/tests/test_no_ai_flow.py`
- `backend/teaching_agent/tests/test_hints_state.py`
- `backend/teaching_agent/tests/test_api_failures.py`

### 2.2 既有入口适配

- `backend/agent_runtime/serializers.py`：支持任务尝试/教学运行定位字段。
- `backend/agent_runtime/views.py`：任务绑定请求改用服务端可信上下文。
- `backend/agent_runtime/tool_registry.py`：由动态 `getattr` 改为显式白名单，并执行任务权限复核。
- `backend/ai_assistant/tutor_request_orchestrator.py`：解析任务绑定；任务辅导不再进入旧的无预算链路。
- `backend/ai_assistant/views.py`：题目上下文补服务器 ID；直接题解 API 对学生任务关闭；旧任务聊天/SSE 转向模块二入口。
- `backend/ai_assistant/service.py`：学生知识包不再读取或写入 `ChallengeSolution.content`。
- `backend/learning_analytics/models.py`：`LearningBehaviorEvent` 增加兼容的唯一事件 ID 和模块二事件类型。
- `backend/learning_analytics/events.py`：支持严格幂等、同键异内容冲突和可靠失败语义；旧调用保持 best-effort 兼容。
- `backend/ctf_backend/settings.py`：注册应用及 10 秒预算、缓存、熔断配置。
- `backend/ctf_backend/urls.py`：注册 `/api/teaching/`。
- `PROGRESS.md`：开工核对、逐包结果及全量测试对账。

## 3. 数据迁移

1. `backend/learning_analytics/migrations/0011_learningbehaviorevent_event_id_and_more.py`
   - `LearningBehaviorEvent.event_id`：`CharField(max_length=64, unique=True, null=True, blank=True)`。
   - 扩展模块二事件类型。
2. `backend/teaching_agent/migrations/0001_initial.py`
   - 初始教学运行、提示卡、工单、学生解析、辅导请求、模型调用及熔断表。
3. `backend/teaching_agent/migrations/0002_practiceaction.py`
   - 幂等练习动作账本。
4. `backend/teaching_agent/migrations/0003_hintdelivery_resumereceipt.py`
   - 提示交付绑定和持久化恢复回执。
5. `backend/teaching_agent/migrations/0004_tutorrequest_material_hash_tutorresponsecache.py`
   - 请求材料哈希及权限感知响应缓存。

迁移一致性：`manage.py makemigrations --check --dry-run` 返回 `No changes detected`。

## 4. API 说明

所有接口均需认证。学生端资源通过服务端用户与 `TaskAttempt`/`TeachingRun` 所有权关联，不接受客户端自报授权。

| 方法与路径 | 说明 |
|---|---|
| `POST /api/teaching/runs/` | 以 `attempt_id` 创建或返回活动教学运行，并返回净化任务上下文/快照 |
| `GET /api/teaching/runs/{run_id}/` | 读取自有运行和当前权限上下文 |
| `POST /api/teaching/runs/{run_id}/actions/` | 幂等登记练习动作；模块四/五仅返回明确契约状态 |
| `POST /api/teaching/runs/{run_id}/tutor/` | 任务绑定辅导；总等待硬上限 10 秒，响应先校验后展示 |
| `POST /api/teaching/runs/{run_id}/hints/request/` | 请求审核提示，不返回提示正文，不计实际帮助展示 |
| `POST /api/teaching/runs/{run_id}/hints/{request_id}/display/` | 重新鉴权后展示提示并登记实际帮助 |
| `POST /api/teaching/runs/{run_id}/pause/` | 按预期 `state_version` 暂停 |
| `POST /api/teaching/runs/{run_id}/resume/` | 按请求 ID 和预期版本幂等恢复；重复请求返回原结果 |
| `POST /api/teaching/runs/{run_id}/teacher-tickets/` | 创建教师帮助工单 |
| `GET /api/teaching/teacher-tickets/{ticket_id}/` | 学生读取自有工单，教师读取待处理工单 |
| `POST /api/teaching/teacher-tickets/{ticket_id}/help/` | 教师登记并展示实际帮助 |
| `GET /api/teaching/runs/{run_id}/analysis/` | 仅任务程序核验通过后读取审核静态学生解析；`private, no-store` |

任务绑定请求若进入旧聊天、SSE 或旧辅导入口，返回 409 `task_tutoring_endpoint_required`；`POST /api/ai/solve/` 不向学生任务返回完整题解。

## 5. 权限、事件与故障口径

- 模型上下文仅含任务目标、尝试状态、受控证据引用、运行版本、学生材料引用及允许工具；不含学生身份资料、原始提交、教师答案、评分键、隐藏验证器或完整学生解析。
- `LearningBehaviorEvent` 是模块二唯一行为事件写入口。模块二事件 ID 不超过 64 字符；同 ID 同内容返回原记录，同 ID 不同内容拒绝。
- 提示请求和实际展示分开；请求失败或未展示不计实际帮助。教师实际帮助和解析查看继续写入模块六 `AssistanceRecord`，模块二不复制成绩判断。
- 调用记录保留 provider、model、template、token、latency、状态、错误类别、重试、取消和费用口径；供应商未返回的 token/费用保持 `NULL`/`unknown`。
- 断连、供应商错误、超时、429、额度耗尽分别分类。超时只记录尽力取消；没有供应商确认时不声称已成功取消。
- 缓存键含学生、尝试、运行、学科/任务、提示层级、上下文版本、权限版本、材料哈希和模板版本。每次命中重新鉴权；材料撤回、卡片变化、权限版本变化均使旧内容不可读。

## 6. 实际测试命令与结果

测试解释器：`~/workspace/ctf-venv/bin/python`。SQLite 测试使用：

```bash
DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH=/tmp/ctf-module2.sqlite3 \
  ~/workspace/ctf-venv/bin/python backend/manage.py test <labels>
```

### 6.1 分包及回归测试

| 命令标签 | 结果 |
|---|---|
| `teaching_agent.tests.test_context_permissions` | 6/6 通过（最初 5 项通过，加入直接题解负向用例后纳入全模块 15 项） |
| `teaching_agent.tests.test_no_ai_flow` | 1/1 通过 |
| `teaching_agent.tests.test_hints_state` | 3/3 通过 |
| `teaching_agent.tests.test_api_failures` | 5/5 通过 |
| `teaching_agent.tests` | 15/15 通过 |
| `teaching_agent.tests agent_runtime.tests ai_assistant.test_main_chain ai_assistant.test_performance` | 56/56 通过 |
| `manage.py check` | 0 问题 |
| `manage.py makemigrations --check --dry-run` | 无遗漏迁移 |

### 6.2 无 AI 证据

`backend/teaching_agent/tests/test_no_ai_flow.py` 在以下条件下完成领取→材料→练习→模块六提交/程序核验→模块一进度→复盘卡→新场景复测：

- 关闭学习地图 AI、语义检索、路由、专员和教学上下文开关。
- 在模型服务边界设置“调用即失败”。
- 断言模型边界调用次数为 0。
- 断言 `ModelCallRecord` 数量为 0。

结果：1/1 通过，核心链路没有先尝试外部模型再降级。

### 6.3 全量 SQLite 测试

完整命令在 `backend/` 目录运行：

```bash
DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH=/tmp/ctf-module2.sqlite3 \
  ~/workspace/ctf-venv/bin/python manage.py test --verbosity 1
```

完整输出：`/tmp/ctf-module2-full-sqlite-20261029.log`。

结果：

- 发现并运行：638
- 严格通过：621
- 跳过：11
- FAIL：5
- ERROR：1
- 未 FAIL/ERROR：632/638
- 进程结果：失败（非零退出）

#### 失败清单

1. ERROR `mainline1.test_settings` — `KeyError: MAINLINE1_TEST_PORT`。
2. FAIL `challenges.tests.ChallengeProxyAccessTests.test_access_url_does_not_include_reusable_token` — URL 仍含 `access_token=`。
3. FAIL `challenges.tests.ChallengeProxyAccessTests.test_proxy_accepts_authenticated_owner_without_cookie` — 期望 200，实际 401。
4. FAIL `challenges.tests.ChallengeProxyAccessTests.test_proxy_rejects_authenticated_non_owner` — 期望 403，实际 401。
5. FAIL `challenges.tests.ChallengeProxyAccessTests.test_proxy_rejects_unsafe_session_request_without_csrf` — 期望 403，实际 401。
6. FAIL `mainline1.tests.test_semantic.SemanticTests.test_real_transport_constructor_pins_options_without_provider_registry` — `ai_providers` 已在 Django 进程的 `sys.modules`。

第 6 项单独运行仍失败；未修改不属于本模块范围的 `mainline1`。

#### 与给定基线逐项对账

给定基线：512 项、501 未失败；4 个 challenges proxy FAIL、6 个 mainline1 loader ERROR、1 个 learning_map `jsonschema` 导入 ERROR。

- 4 个 challenges proxy FAIL：完整复现，名称和类别一致。
- mainline1 loader：本次测试运行器仅汇总 1 个 `mainline1.test_settings` ERROR，首个缺失环境变量为 `MAINLINE1_TEST_PORT`；没有得到 6 个独立 ERROR，不能宣称其余 5 项已修复。
- learning_map `jsonschema`：本环境未复现该导入 ERROR；不能据此宣称代码已修复。
- 基线外失败：新增记录 1 个 mainline1 semantic FAIL（上列第 6 项）。
- 测试总数比给定基线多 126；其中模块二新增 15 项，其余差异来自当前分支/测试发现范围，不能用给定 512 项直接推导回归通过率。

## 7. 验收证据位置

| 验收关注点 | 证据 |
|---|---|
| 跨学生尝试、运行、SSE 拒绝 | `backend/teaching_agent/tests/test_context_permissions.py` |
| 学生 API/知识包/直接题解不泄露教师答案 | `backend/teaching_agent/tests/test_context_permissions.py` |
| 模型越权工具建议被平台拒绝 | `backend/teaching_agent/tests/test_api_failures.py` |
| 无 AI 核心链路、外部调用为零 | `backend/teaching_agent/tests/test_no_ai_flow.py` |
| 四级提示请求/展示分离及材料撤回 | `backend/teaching_agent/tests/test_hints_state.py` |
| 暂停、重启语义恢复、重复继续、过期版本 | `backend/teaching_agent/tests/test_hints_state.py` |
| 工单所有权和教师实际帮助 | `backend/teaching_agent/tests/test_hints_state.py` |
| 静态学生解析独立鉴权 | `backend/teaching_agent/tests/test_hints_state.py` |
| 10 秒预算、取消、迟到隔离 | `backend/teaching_agent/tests/test_api_failures.py` |
| 断连、429、额度、熔断和恢复探测 | `backend/teaching_agent/tests/test_api_failures.py` |
| 权限缓存及材料撤回失效 | `backend/teaching_agent/tests/test_api_failures.py` |
| 完整逐包记录 | `PROGRESS.md` |
| 全量原始输出 | `/tmp/ctf-module2-full-sqlite-20261029.log`（本机临时证据，不纳入 Git） |

## 8. 未运行项目

- 未调用任何真实模型供应商，未产生真实 token/费用。
- 未执行真实供应商 429 `Retry-After`、真实额度耗尽、真实取消确认或真实恢复探测；使用合成异步供应商和故障异常做契约测试。
- 未与模块三知识服务联调；首期只传服务端身份、任务范围、材料用途和权限版本契约。
- 未与模块四沙箱/网络实训联调；返回 `unavailable`，不伪造执行结果。
- 未与模块五数据工具联调；首期数据导出动作返回 `not_applicable`，不伪造导出能力。
- 未与模块八评测/对账平台联调；调用、降级、提示、暂停恢复事实已保留在当前数据库契约中。
- 未在 PostgreSQL 或生产多进程部署运行迁移/恢复演练；SQLite 测试验证数据库持久化和新客户端恢复，不等同于生产部署演练。
- 未运行浏览器端页面验收或真实 SSE 前端交互；任务绑定旧 SSE 已通过 API 负向测试关闭绕过。

## 9. 剩余依赖与配置审核

1. **模块三**：知识卡权限、缺失/冲突/过期状态的服务端实现与联调。
2. **模块四**：沙箱/网络实训动作登记、幂等执行和证据回传。
3. **模块五**：受控数据工具动作及首期之后的数据导出策略。
4. **模块八**：统一调用成本、故障、事件对账与验收报告接入。
5. **真实供应商**：provider/model/token/cost 字段映射、429 重试提示、取消确认、额度恢复和小流量探测。
6. **运营审核**：熔断阈值、探测间隔、缓存 TTL 和重试策略当前使用 `unapproved-default`/环境变量默认值，需平台及测试负责人冻结配置版本后才能作为正式策略。
7. **内容治理**：三模式审核提示卡和学生解析内容需由课程教师按正式版本发布；当前自动化证据使用合成卡片。
8. **全量基线差异**：需由主线维护者确认 638 项当前发现范围、mainline1 专用环境设置及新增 semantic FAIL；模块二没有修改这些失败所属实现。**复核结论（2026-10-29，主 agent 亲自核查）**：同一环境同一方法枚举，干净 e118f5b 发现 623 个测试、本分支 638 个，差值恰为 teaching_agent 新增的 15 个，旧测试零减少；旧 512 基线系当时 mainline1 大面积加载失败与 jsonschema 缺失导致的少算。该 semantic FAIL 在干净 e118f5b 上以相同断言复现——平台 manage.py test 加载总路由后 ai_assistant 调用链已将 ai_providers 引入 sys.modules，与该用例为隔离测试环境设计的断言冲突，属既存现象而非模块二回归；其处理归 mainline1 侧，不在本分支范围内。

## 10. 约束确认

- 未引入 LangGraph。
- 未引入新平台组件或第三方依赖。
- 未新增第二套任务、成绩、事件或用户体系。
- 模块一/六复用真实契约；模块三/四/五/八仅做契约侧适配。
- 实施期间未 commit、未 push；2026-10-29 应用户决定提交到本地分支 feat/module2-teaching-agent，未推送。
