# 模块六：技能验收、错题复盘与延迟复习

状态：**第一阶段代码完成，隔离测试与本地真实 HTTP 验证通过；上游任务 UI、模块七/八尚未接通，人工审核与正式开放未执行。**

实现位置：`backend/skill_review/`，前端页面 `frontend/src/views/SkillReview/MyResults.vue`、`frontend/src/teacher/SkillReviewAdmin.vue`。

## 1. 已实现

- 提交快照：同一提交标识幂等；同标识异内容返回冲突；每次修改生成新快照并保留原快照。
- 首次有效尝试冻结：`first_effective` 唯一约束，多次重做不替换首次结果。
- 帮助记录：提示请求与展示分离；教师帮助单列；查看解析记为暴露事件。
- 独立性判定：实际展示过 1—4 级提示或教师帮助 → 受助；仅请求未展示 → 不影响；记录缺失或答案暴露 → 未知。
- 程序核验：任务包 `validator.checks` 的确定性规则；未配置或服务端验证器未接通 → `error`，绝不判通过。
- 人工评阅：独立队列、认领、四项量表（各 0—2 分）、逐项证据与理由、必须写评阅说明。
- 结果状态：程序、人工、综合三维分别保存；人工必评未完成时综合为待评，不生成总分。
- 错因：五类，规则可建议，学生可补充，教师可确认或排除；只有教师确认的错因进入下游通知。
- 复盘卡：六个字段，完成时必须齐全；完成后自动按规则选题安排复测。
- 复测：排除原题、已提交题、已看解析题、环境不可用与需里程碑 I 的任务；无候选时标“待补题”。
- 复测状态：待补题 → 待到期 → 已到期 → 进行中 → 已测 / 未完成；日期推进是纯日期逻辑。
- 教师抽查：批次登记范围、随机种子、样本量、依据、期限；随机与高风险分开；认领、逐项记录、超期识别。
- 争议：提交、处理；处理争议**不直接改分**。
- 更正：新版本替代旧结果，保留 before/after、复核人、来源、理由；旧结果不被修改。
- 下游通知：模块一事实即时回传；模块七/八标记 `not_connected`，可见但不假装成功。
- 统计：分子、分母、缺失量、版本分别给出；无样本返回 `null` 而非 0。
- 模块八固定回归样例：`/api/skill-review/teacher/regression-cases/`。

## 2. 共享事件与接口

复用 `learning_analytics.LearningEvent`，新增事件类型：`review_card_complete`、`correction`。

关键事件与 `metadata`：`attempt_id`、`submission_id`、`result_id`、`task_key/version`、`capability_ids`、`catalog_version`、`evidence_ref`、`verifier_version`、`assistance_level/source/shown`。

学生接口（只含本人）：

| 方法 | 路径 |
|---|---|
| GET | `/api/skill-review/me/attempts/` |
| GET | `/api/skill-review/me/submissions/` |
| GET | `/api/skill-review/submissions/<id>/` |
| POST | `/api/skill-review/attempts/<id>/submit/` |
| POST | `/api/skill-review/attempts/<id>/hints/` |
| POST | `/api/skill-review/hints/<id>/show/` |
| PUT | `/api/skill-review/submissions/<id>/review-card/` |
| POST | `/api/skill-review/submissions/<id>/causes/` |
| POST | `/api/skill-review/tasks/<id>/analysis-view/` |
| GET | `/api/skill-review/me/retests/` |
| POST | `/api/skill-review/retests/<id>/claim/` |
| POST | `/api/skill-review/submissions/<id>/disputes/` |

教师接口（`role=teacher|admin`）：`teacher/queue/`、`teacher/manual-tasks/`、`teacher/manual-tasks/<id>/{claim,review}/`、`teacher/attempts/<id>/{help,timeline}/`、`teacher/submissions/<id>/corrections/`、`teacher/retests/`、`teacher/retests/<id>/adjust/`、`teacher/retests/process-due/`、`teacher/sampling/*`、`teacher/disputes/`、`teacher/stats/`、`teacher/regression-cases/`、`teacher/notices/<id>/retry/`。

模块六 → 模块一：使用 `learning_map.services.handoff.ingest_verification_fact` 的既有契约，`fact_id` 含结果版本与修订号；更正产生新事实。

## 3. 运行方式

```bash
cd backend
DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  SQLITE_DATABASE_PATH="$PWD/.tmp-m6.sqlite3" python manage.py migrate
DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  SQLITE_DATABASE_PATH="$PWD/.tmp-m6.sqlite3" python manage.py seed_learning_map
DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  SQLITE_DATABASE_PATH="$PWD/.tmp-m6.sqlite3" python manage.py seed_skill_review
DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  SQLITE_DATABASE_PATH="$PWD/.tmp-m6.sqlite3" python manage.py runserver 127.0.0.1:8000
```

```bash
cd frontend && npm install && npm run dev
```

页面：学生 `/my-results`，教师 `/teacher/skill-review`。

迁移：`skill_review/migrations/0001_initial.py`、`users/migrations/0005_ctfuser_is_course_owner.py`、`learning_analytics` 事件类型扩展。

## 4. 验证结果

- `python manage.py check`：0 issues
- `python manage.py test learning_map skill_review`：**67 项通过**
- **与模块七联合**：`test learning_map skill_review feedback_center` 共 **90 项通过**。其中新增跨模块读测试证明模块七的只读适配器能读到模块六真实数据：帮助记录（层级/来源/展示）、当前核验结果（程序/人工/综合/独立性）、复测安排（状态/到期/结果）与模块一核验事实；无记录时正确报告 `hint_record_status=unknown`、不推定独立。
- 真实 HTTP 走通（隔离库、合成数据）：学生读本人提交、越权访问被拒（403）、教师队列、普通教师读候选目录被拒（403）、课程负责人可读、统计与回归样例、人工认领与评阅、复测日期推进。
- 前端 `npm run build` 通过。

覆盖场景：程序通过但人工待评并存；请求未展示不算帮助；1—4 级帮助后重交仍受助；教师帮助记受助；缺记录为未知；解析暴露保留；提交幂等与冲突；更正保留原判；复测排除原题/已看解析；题池为空；抽查可复现；争议不改分；越权拒绝；模块七/八未接通。

## 5. 未完成与人工待确认

- 上游任务页面（模块二/四/五）未接通：学生目前没有“做任务并提交”的界面，提交接口已就绪。
- 网络任务的 `server_verifier` 未接通：`TASK-NS-*` 提交一律 `verification_failed`，不伪造通过。
- 模块七已能只读模块六扩展表（联合测试覆盖）；但**教师处理、评分争议接收、复测回传的跨模块写入仍走模块七自己的工单表**，双向真实联调未验收。
- 模块八仅有通知记录，`not_connected`；报告导入、逐例差异、审批联动未实现。
- 无人值守的到期推进：目前由教师手动触发或管理命令，未接定时任务。
- 量表、错因映射、复测间隔（3 天/7 天）均为候选默认值，待课程审核。
- 浏览器视觉验收本轮未执行（Playwright 会话被另一会话占用），页面通过构建与接口验证。
