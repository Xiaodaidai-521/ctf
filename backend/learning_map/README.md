# 模块一：双主线能力地图与个性化学习路径

状态：**代码实现完成，隔离测试通过；目录与课程材料仍是候选，未冻结、未发布，也未完成人工审核。**

本目录（Django app `learning_map`）实现操作方案第一阶段的核心可验证部分：

- 约 20 项双主线能力目录候选、知识点、先修关系、旧标签映射候选
- WSTG v4.2 场景转译草案与数据依据卡草案
- 8 道双主线诊断题候选（各主线 4 道）
- 4 个最小任务包候选（数据/网络各含一个复测题）
- 确定性诊断、状态机、推荐、教师调整、路径变更记录
- 首期交付登记（3.1）与冻结/发布门禁
- 复用现有 `LearningEvent` 的统一事件字典
- 模块六核验事实回传接口与本地测试替身
- CASE v1.1 目录导出与 xAPI 1.0.3 证据映射（仅交换格式，不引入外部服务）

## 1. 快速运行

后端（隔离 SQLite 库，不影响正式库）：

```bash
cd backend
DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  SQLITE_DATABASE_PATH="$PWD/.tmp-learning-map.sqlite3" python manage.py migrate
DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  SQLITE_DATABASE_PATH="$PWD/.tmp-learning-map.sqlite3" python manage.py seed_learning_map
DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  SQLITE_DATABASE_PATH="$PWD/.tmp-learning-map.sqlite3" python manage.py runserver 127.0.0.1:8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

页面：

- `/capability-map` 学生能力地图、基础诊断、确定性推荐、领取任务
- `/capability-map/changelog` 本人路径变更记录
- `/teacher/capability-map` 教师：候选目录、门禁缺失项、学生证据、教师调整、交付登记、CASE 导出

## 2. 测试与已验证结果

```bash
cd backend
DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key python manage.py test learning_map
```

已验证（2026-10-25，本地隔离 SQLite）：

- `learning_map` 36 个测试全部通过，覆盖：新学生待诊断、同输入推荐一致、受助/未展示/未知、环境故障、事实幂等与冲突、版本保留、发布门禁、里程碑 I 任务不推荐、空题池、教师指定、诊断确定性、越权访问、交付签收校验、CASE schema 校验、xAPI 隐私字段、事件写入失败回滚与重试。
- `python manage.py check` 无问题。
- 候选种子装载结果：20 项能力、10 个知识点、4 个任务、8 道诊断题、4 条旧标签映射。
- 候选目录 `publish_readiness` 返回 `ready=false`，共 45 项缺失（交付项未签收、依据卡/WSTG 未复核、部分能力无任务、诊断未冻结），发布与冻结被阻止，符合预期。
- CASE v1.1 导出通过 1EdTech/OpenCASE 官方 JSON Schema 校验。
- 前端 `npm run build` 通过。
- 学生接口不返回内部能力 ID、任务键、证据引用、原因码、规则版本、缺口码、输入摘要；教师接口保留完整审核字段（有自动化测试断言）。
- 本地浏览器走通：学生登录、能力地图、双主线诊断、领取任务；教师候选目录、门禁缺失项、学生证据、教师指定任务。候选预览仅在本地用 `LEARNING_MAP_PREVIEW_CANDIDATE=true` 打开，默认关闭。
- `seed_learning_map` 可重复执行：不重复建表记录，不覆盖已冻结任务/已签收交付/已复核状态。

未验证/未完成：

- 模块六真实联调（当前只有事实接口、读接口和本地测试替身）
- 网络任务隔离环境验收（`environment_available=false`，不进入推荐）
- 真实模型调用（本模块不调用）
- 教师人工审核、签字、正式发布
- 任务包引用的材料/提示/学生解析文件尚未实际编制，因此任务均为 `draft`，不能签收或发布
- 法规与标准现行性、行业目录选型未核验

## 3. 共享接口（模块六/七/八）

### 3.1 稳定标识与版本

所有记录同时带以下版本：

| 字段 | 位置 | 说明 |
|---|---|---|
| `capability_id` | `Capability.stable_id` | 如 `DS-001`、`NS-004`；同一目录版本内唯一 |
| `knowledge_point_id` | `KnowledgePoint.stable_id` | 如 `KP-DS-03` |
| `catalog_version` | `CatalogVersion.version` | 如 `v1-candidate` |
| `task_key` + `version` | `TaskPackage` | 任务自身版本，不与目录版本混用 |
| `attempt_id` | `TaskAttempt.attempt_id` | UUID；模块六用它关联提交与核验 |
| `fact_id` | `VerificationFact.fact_id` | 幂等事件 ID；重复回传返回原事实 |
| `rule_version` | 目录/状态/推荐 | 相同输入和版本产生相同结果 |

ID 含义不可改写。拆分、合并或口径变化必须新建目录版本与能力 ID，并用 `Capability.supersedes` / `LegacyLabelMapping` 记录映射；旧事实保留原目录版本。

### 3.2 模块六 → 模块一：核验事实

`POST /api/learning-map/verification-facts/`

请求字段（只允许摘要与受控证据引用，不发送答案正文、学生真实身份或凭证）：

```json
{
  "fact_id": "module6-event-uuid",
  "student": 3,
  "catalog_version": "v1-candidate",
  "capability_id": "DS-005",
  "knowledge_point_id": "KP-DS-03",
  "task_key": "TASK-DS-CUSTOMER-TABLE-001",
  "task_version": "1.0.0-candidate",
  "attempt_id": "uuid",
  "outcome": "passed|failed|pending_review|verification_failed|environment_affected|unknown",
  "independence": "independent|assisted|unknown",
  "assistance_level": 0,
  "assistance_source": "none|ai|card|teacher|unknown",
  "assistance_shown": false,
  "retest_of_attempt_id": null,
  "first_attempt": true,
  "evidence_ref": "server-evidence-ref",
  "verifier_version": "verifier-v1",
  "occurred_at": "2026-10-25T10:00:00+08:00",
  "payload": {}
}
```

校验规则：

- `independence=assisted` 必须有实际展示的帮助层级 1—4 和来源；请求但未展示不算帮助。
- `independence=independent` 且 `assistance_shown=true` 被拒绝。
- `outcome=environment_affected` 不能标记为独立。
- 相同 `fact_id` 且内容一致：幂等返回原事实，不重复产生路径变更。
- 相同 `fact_id` 但内容不同：`409 fact_id_conflict`，必须使用新 ID。

状态映射：

| 核验事实 | 路径状态 |
|---|---|
| `passed` + `independent` | `independent` 已有独立证据 |
| `passed` + `assisted` | `assisted_pass` 受助通过；设置复测到期日 |
| `passed` + `unknown` | `unknown` 未知；不冒充独立 |
| `failed` | `needs_practice` 需要练习 |
| `pending_review` | `pending_review` 待教师评阅 |
| `verification_failed` | `pending_verification` 待核验 |
| `environment_affected` | `environment_affected` 受环境影响 |
| 复测事实 | 按新事实重新判定；独立通过才转为 `independent` |

已完成的独立状态冻结：之后非复测事实不追溯降级。复测失败会回到 `needs_practice`。

### 3.3 模块一 → 模块七/八：状态与证据读取

- `GET /api/learning-map/me/map/`：学生本人能力地图（含四维、先修、证据摘要、版本）
- `GET /api/learning-map/teacher/students/<id>/map/`：教师按权限读取
- `GET /api/learning-map/me/recommendations/`：确定性推荐，含理由、规则版本、输入摘要
- `GET /api/learning-map/me/changelog/`：路径变更记录（前后态、触发事实、规则版本）
- `GET /api/learning-map/status/`：模块状态；明确 `module6_connected=false`、`milestone_i_open=false`

`handoff.py` 同时提供 `VerificationFactSource` 读侧协议、`DjangoVerificationFactSource` 本地实现和 `MemoryVerificationFactSource` 测试替身。

### 3.4 事件字典（复用 `learning_analytics.LearningEvent`）

新增事件类型：`diagnosis_submit`、`task_claim`、`task_start`、`task_submit`、`verification_result`、`hint_request`、`hint_show`、`teacher_help`、`analysis_view`、`retest_assign`、`recommendation_issued`、`path_update`、`ai_degraded`。

`metadata` 公共字段：`task_id`、`task_key`、`task_version`、`attempt_id`、`capability_ids`、`knowledge_point_ids`、`catalog_version`、`task_purpose`、`evidence_ref`、`verifier_version`、`assistance_level`、`assistance_source`、`assistance_shown`、`source`。

事件按 `event_id` 去重。提示请求与实际展示必须分开记录（由模块二/六实现，模块一只定义字段与消费方式）。

## 4. 推荐规则（`rules-v1-candidate`）

固定顺序：

1. 教师指定任务
2. 无证据时基础诊断
3. 到期复测
4. 当前目标缺失的先修
5. 未通过知识点练习
6. 受助后的巩固
7. 新能力任务

过滤：未冻结、材料撤回、环境不可用、要求里程碑 I、先修未满足、已尝试任务。同优先级按课程顺序、稳定任务 ID、任务版本排序。题池为空输出 `gaps`，不临时生成题目。相同目录、状态、事实、任务快照和规则版本 → 相同 `inputs_hash` 与输出。

先修只接受 `independent`；`assisted_pass` 不满足需要独立证据的后续任务。

## 5. 审核门禁与交付登记

`GET /api/learning-map/delivery-register/`，`PATCH /api/learning-map/delivery-register/<delivery_no>/`。

`status=signed_off` 必须同时具备：真实 `author`、`reviewer`、`attachment_path`、`signed_off_at`。任何字段缺失都拒绝，且不得代填审核人。

冻结/发布要求：

- 5 个必需交付项全部签收
- 每个开放能力至少一个已冻结任务，含学生材料、四级提示、学生版解析引用、验证器/量表、验收要求、复测题池
- 数据能力有已复核依据卡；网络能力有已复核 WSTG 转译
- 每个有开放能力的主线有已冻结诊断题
- WSTG 转译保留 `4.2` 版本与场景编号

候选目录当前 45 项缺失，发布被阻止。

## 6. GitHub 复用评估与取舍

采用：

- **1EdTech CASE v1.1 CFPackage**（规范；schema 取自 [1EdTech/OpenCASE](https://github.com/1EdTech/OpenCASE)，Apache-2.0）。已 vendored 到 `fixtures/case-v1p1-cfpackage.schema.json`，导出接口与测试使用。仅作为目录交换格式，不替换本地数据库。
- **xAPI 1.0.3 语句结构**（[adlnet/xAPI-Spec](https://github.com/adlnet/xAPI-Spec)，Apache-2.0）。把核验事实映射为 statement；`actor` 只用内部账号，不含真实身份；未部署 LRS，也未把 xAPI 作为第二套事件库。

评估后未直接采用：

- [opensalt/opensalt](https://github.com/opensalt/opensalt)（MIT，PHP）：能力框架对齐工具，适合作为 CASE 编辑与对齐的参考；不引入其 PHP 服务。
- [infosign/compeito](https://github.com/infosign/compeito)（Apache-2.0，Python，CASE v1.1 server）：项目很小（3 stars），不作为依赖；只参考规范实现。
- [CAHLR/pyBKT](https://github.com/CAHLR/pyBKT)（MIT）：知识追踪，按计划第四阶段有足够数据后再评估；首期保持可解释规则。
- [pykt-team/pykt-toolkit](https://github.com/pykt-team/pykt-toolkit)、[ZhijieXiong/pyedmine](https://github.com/ZhijieXiong/pyedmine)：研究型深度知识追踪/路径推荐，依赖重、不可解释，不作为首期运行时依赖。
- xAPI Learning Record Store 类项目：需要独立服务与部署，首期只做格式映射，不接外部存储。

## 7. 数据模型与迁移归属

- `learning_map/migrations/0001_initial.py`：模块一全部新表。
- `learning_analytics/migrations/0007_alter_learningevent_event_type.py`：只扩展现有 `LearningEvent` 的事件类型枚举，未新增重复事件表。

表：`CatalogVersion`、`KnowledgePoint`、`Capability`、`LegacyLabelMapping`、`WSTGMapping`、`DataBasisCard`、`TaskPackage`、`DiagnosticQuestion`、`DiagnosticSession`、`TaskAttempt`、`VerificationFact`、`CapabilityState`、`RecommendationRun`、`PathChangeLog`、`TeacherAdjustment`、`DeliveryRegisterItem`。

## 8. 明确未完成/待人工确认

- 课程负责人、领域教师、平台负责人尚未审核；`WSTGMapping.translator/reviewer`、`DataBasisCard.owner/verified_date` 保持空，`status` 保持候选/草案。
- 任务包引用的 `fixtures/`、`hints/`、`solutions/` 附件尚未编制；不能把引用当作材料已存在。
- 模块六尚未实现真实提交与核验，`POST attempts/<id>/submit/` 只保存提交快照并明确返回 `verification_connected=false`。
- 网络任务隔离、跨学生访问、外连白名单等验收未执行，任务不开放。
- 里程碑 I 的执行能力未开放；数据任务只做识别、复核和风险决策回放。
- 法规/标准现行性、行业目录选型未核验，依据卡不得作为真实合规结论。
