# 模块七：分类型反馈与系统改进（首期）

状态：**首期代码实现完成，隔离测试通过；真实模块六/模块八联调、候选审批发布与里程碑 I 执行反馈尚未接入。**

本目录（Django app `feedback_center`）实现操作方案第一阶段的核心可验证部分：

- 识别、决策、教学三类反馈采集
- 每类必需证据槽、缺证/未映射状态与候选资格门禁
- 已提交 → 待去重 → 待事实复核/待补证 → 已确认/驳回 → 人工处理中 → 已处理
- 新证据到达后重开；人工更正追加复核结论，原结论与原始判定保留
- 网络重试幂等、同尝试同类别同争议去重、同尝试跨类别关联
- 教师按冲突、影响、新颖性、等待时间处理待办
- 可复现的随机抽查批次（范围、总体摘要、随机种子、入选原因）
- 受控附件上传/下载与访问审计
- 统一 `LearningEvent` 事件关联、失败待重试与事件核对页
- 第三阶段问题组/候选/审批/发布/观察/回退的接口契约（**未启用**）

首期**不会**触发实际导出、生产配额或生产策略修改；执行反馈入口保持关闭，等待独立里程碑 I。反馈“已处理”不等于“新规则已生效”，也不等于“教学效果已验证”。

## 1. 代码落点

| 路径 | 内容 |
|---|---|
| `backend/feedback_center/models.py` | 工单、证据、附件、复核、动作、转交、关联、抽查、访问日志、事件 outbox |
| `backend/feedback_center/constants.py` | 三类问题类型、必需证据槽、状态机、路由、优先级、事件类型 |
| `backend/feedback_center/services/submission.py` | 提交、链接解析、自动只读证据、去重、跨类别关联、学生补证 |
| `backend/feedback_center/services/workflow.py` | 教师认领/分配/登记/补证/确认/驳回/更正/转交/处理/效果 |
| `backend/feedback_center/services/evidence.py` | 证据槽校验、缺证计算、去重键、候选门禁 |
| `backend/feedback_center/services/events.py` | 确定性事件 ID、outbox 同步、重试、内容不一致检测 |
| `backend/feedback_center/services/sampling.py` | 确定性随机抽查批次 |
| `backend/feedback_center/services/reconciliation.py` | 事件核对队列与重试 |
| `backend/feedback_center/services/phase3.py` | 第三阶段接口契约（只读，未启用） |
| `backend/feedback_center/views.py` / `urls.py` | 学生、教师、核对、抽查、第三阶段契约接口 |
| `frontend/src/views/Feedback/` | 学生反馈中心与详情 |
| `frontend/src/teacher/FeedbackQueue.vue` | 教师待办 + 随机抽查 |
| `frontend/src/teacher/FeedbackDetail.vue` | 教师详情与人工处理 |
| `frontend/src/teacher/FeedbackReconciliation.vue` | 事件核对 |
| `frontend/src/assets/feedback.css` | 页面样式 |

## 2. 运行与测试

后端依赖与模块一相同（Django 6 + DRF + SQLite 开发回退）。

```bash
cd backend
DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  SQLITE_DATABASE_PATH="$PWD/.tmp-feedback.sqlite3" \
  python manage.py migrate --settings=feedback_center.test_settings

DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  python manage.py test feedback_center --settings=feedback_center.test_settings
```

模块七 + 模块一联合回归：

```bash
cd backend
DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key \
  python manage.py test learning_map feedback_center --settings=feedback_center.test_settings
```

前端：

```bash
cd frontend
npm run build
```

说明：模块六 `skill_review` 已具备模型、迁移与 HTTP 入口；默认 settings 下 `manage.py check` 通过。模块七测试同时覆盖默认 settings 与 `feedback_center.test_settings`（后者隔离模块六扩展表）。模块六真实业务联调仍需跨模块验收；模块七可选读取 `skill_review` 扩展表，表不可用时降级为 `learning_map.VerificationFact` + `LearningEvent`，并在状态接口返回 `module6_extension_connected=false`。

## 3. 首期接口

挂载前缀：`/api/feedback/`。

### 3.1 学生/通用

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `status/` | 模块状态、执行反馈关闭、候选发布关闭、生产效果全 false |
| GET | `options/` | 类别、问题类型、必需证据槽、状态、去向、效果状态、附件限制 |
| POST | `` | 创建反馈；需要 `client_request_id`；网络重试幂等 |
| GET | `me/` | 本人（提交人或所属学生）反馈列表与状态计数 |
| GET | `<feedback_id>/` | 详情；学生仅本人，教师按职责 |
| POST | `<feedback_id>/evidence/` | 追加证据；可能进入待补证或重开 |
| POST | `<feedback_id>/attachments/` | 上传受控附件（multipart） |
| GET | `<feedback_id>/attachments/<attachment_id>/download/` | 鉴权下载；学生不可下载教师专用附件 |

创建请求示例（字段均为合成示例）：

```json
{
  "client_request_id": "retry-safe-uuid",
  "category": "decision",
  "issue_type": "normal_request_blocked",
  "attempt_id": "00000000-0000-0000-0000-000000000000",
  "dispute": "110 条正常请求被拦截，授权事实齐全。",
  "expected_result": "确认为教学回放误拦并记录回放案例。",
  "reason": "身份、范围、目的和有效期均满足。",
  "original_decision_ref": "replay-decision-001",
  "original_decision_version": "policy-v1",
  "original_decision_snapshot": {"action": "deny", "record_count": 110},
  "evidence": [
    {"slot": "request_scope", "ref": "attempt-snapshot:request_scope", "version": "v1", "summary": "110 条"},
    {"slot": "identity_authorization", "ref": "authorization-snapshot-001", "version": "v1", "summary": "授权有效"}
  ]
}
```

响应会包含 `missing_evidence`、`candidate_eligible`、`production_effects`、`rule_activation`、`event_sync`。保存失败返回 `503 save_failed_retry`，客户端必须使用同一 `client_request_id` 重试；相同标识不同内容返回 `409 idempotency_conflict`。

### 3.2 教师

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `teacher/queue/` | 待办列表；默认排除重复记录；按冲突/影响/新颖性/等待排序 |
| GET | `teacher/<feedback_id>/` | 教师详情（含证据、复核、转交、动作、事件核对） |
| POST | `teacher/<feedback_id>/actions/` | 统一动作入口；必须带 `expected_version` |
| GET/POST | `teacher/sampling-batches/` | 抽查批次列表/创建 |
| GET | `teacher/sampling-batches/<batch_id>/` | 批次明细与入选原因 |
| GET | `teacher/reconciliation/` | 事件核对队列 |
| POST | `teacher/reconciliation/retry/` | 重试待同步事件；可带 `ticket_id` |
| GET | `teacher/phase3/contracts/` | 第三阶段接口契约（`enabled=false`） |
| POST | `teacher/phase3/candidates/` | 固定返回 `409 phase3_not_enabled` |

教师动作（`action` 字段）：

`claim`、`assign`、`triage`、`request_evidence`、`confirm`、`reject`、`revise_review`、`start_handling`、`refer`、`ack_referral`、`handle`、`reopen`、`note`、`set_effect`、`confirm_duplicate`、`split_duplicate`。

关键规则：

- 确认前必须 `evidence_complete` 且 `mapping_complete`；缺证返回 `409 evidence_incomplete`，缺任务/尝试/能力映射返回 `409 mapping_incomplete`。
- 评分争议 `scoring_dispute` 必须转模块六；目录/推荐问题必须转模块一；技术故障必须转平台维护。接收方确认前不能 `handle`。
- `handle` 只表示人工动作完成；`effect_status` 默认 `not_assessed`。标记 `verified` 必须引用真实 `VerificationFact` 且结论为通过；受助复测会注明“不能证明无提示保持”。
- 人工更正使用 `revise_review`，新增复核结论；旧结论 `is_current=false`，原文、复核人、时间和原始判定保留。
- 重复记录不能补充证据或单独确认；先 `split_duplicate` 或回到主记录。

## 4. 三类反馈的路由与必需证据

| 类别 | 典型问题 | 必需证据槽（另有 `original_decision_ref`） | 默认去向/责任 |
|---|---|---|---|
| 识别 `recognition` | 误报、漏报、分类修正 | 合成样本定位、原始检出、识别器版本、匹配粒度、人工标注、依据卡版本；分类修正另需适用事实 | 识别案例 / 识别负责人 + 领域教师 |
| 决策 `decision` | 正常请求误拦、越权放行、遗漏授权事实 | 请求范围/数量、身份与授权快照、业务目的、识别复核结果、教学策略版本、回放输入输出、预期理由 | 决策回放案例 / 决策负责人 |
| 教学 `teaching` | 提示无效、错误归因、受助误记、复测未保持、评分争议、目录/推荐、材料 | 原尝试、提交与核验、提示实际展示/教师介入、量表版本、材料版本、复盘及新场景复测（未复测明确标注）；评分争议另需评分依据，目录/推荐另需规则引用，材料问题另需材料引用 | 模块六/模块一/课程材料/教师，按问题类型 |

`正常请求被拦` 永远是决策反馈，不会自动变成识别错误。点赞、投诉次数、重复投诉数量都不构成正确性证据；同尝试同类别同争议的重复提交只保留一个主记录，重复记录保留原文和主记录引用。

## 5. 状态机

| 状态 | 含义 | 允许的下一步 |
|---|---|---|
| `submitted` | 服务端已落库 | `deduplicating` |
| `deduplicating` | 去重中 | `duplicate` / `pending_fact_review` / `pending_evidence` |
| `duplicate` | 重复记录，关联主记录 | 教师拆分后可进入复核 |
| `pending_fact_review` | 待事实复核 | `pending_evidence` / `confirmed` / `rejected` |
| `pending_evidence` | 待补证 | 新证据后 `pending_fact_review`；可驳回 |
| `confirmed` | 已确认事实 | `handling` / `rejected`（追加更正）/ `reopened` |
| `rejected` | 已驳回 | 新证据 `reopened` |
| `handling` | 人工处理中 | `handled` / `reopened` |
| `handled` | 人工处理完成 | 新证据 `reopened`；效果单独登记 |
| `reopened` | 新证据待复核 | 认领后 `pending_fact_review` |

所有状态变更都写入追加动作记录；人工更正写入新的 `FeedbackReview`，不覆盖旧结论。

## 6. 事件、核对与保存失败

- 复用 `learning_analytics.LearningEvent`，新增事件类型：`feedback_submitted`、`feedback_deduplicated`、`feedback_evidence_added`、`feedback_reviewed`、`feedback_handling_started`、`feedback_handled`、`feedback_reopened`、`feedback_effect_updated`、`feedback_status_changed`。
- 事件 ID 确定性生成：提交 `fb-submit-<feedback_id>`；动作 `fb-action-<action_id>`。重复重试不会产生第二条事件。
- 事件写入失败时工单仍保存，`FeedbackEventLink.status=pending`，接口返回 `event_sync.status=pending_retry`；教师可在事件核对页重试。
- 事件元数据只包含反馈 ID、类别、问题类型、状态、工单版本、任务/尝试/能力/知识点引用和动作 ID；不包含争议正文、答案、教师评分密钥或学生真实身份。
- 事件已存在但 `feedback_id`/`action_id` 不匹配时标为 `mismatch`，不自动覆盖。

## 7. 权限与受控证据

- 学生只能提交本人反馈、查看本人反馈、补充本人证据、下载学生可见附件。
- 教师/管理员可查看待办与详情、处理工单、抽查、核对事件；管理员可分配责任人。
- 附件使用非公开 `FileField`，只通过鉴权下载接口返回 `application/octet-stream` 和 `nosniff`；学生看不到 `staff` 可见附件。
- 详情访问与附件下载写入 `FeedbackAccessLog`；越权尝试也会记录 `allowed=false`。
- 不保存完整答案、教师答案、凭证或真实个人信息；证据只保存引用、版本和必要摘要。

## 8. 抽查与优先级

- 待办排序：证据冲突 → 影响 → 新颖性 → 等待时间；重复投诉数量不参与。
- 抽查批次保存：范围、总体数量/摘要/ID 快照、目标样本数、随机种子、方法、是否排除既往样本、入选原因、抽样时工单版本。
- 相同总体、范围和种子应产生相同随机样本；高风险样本单独标记，不能当作总体错误率的随机估计。
- 既往样本默认排除；剩余不足目标数量时全部查看并标记 `census`。

## 9. 首期明确未完成/未接通

- **模块六 HTTP 层**：`skill_review` 已具备模型、迁移和 HTTP 入口；模块七读取 `learning_map.VerificationFact` 和统一 `LearningEvent`，并在扩展表可用时只读读取 `skill_review` 的帮助记录、当前核验结果和复测安排。真实跨模块业务联调（教师处理、评分争议接收、复测回传）仍需联合验收。
- **模块八评测报告**：第三阶段契约已定义 `run_id/report_id/report_version/report_digest`，但未实现报告导入、逐例差异或审批联动。
- **模块一目录/推荐发布**：目录/推荐问题可转模块一，但模块七不修改目录、推荐规则或任务版本。
- **候选管理/审批/发布/回退**：未启用；`POST teacher/phase3/candidates/` 固定返回 `409 phase3_not_enabled`。
- **里程碑 I 执行反馈**：执行反馈入口关闭；`involves_actual_execution=true` 返回 `409 milestone_i_not_open`，不落库。
- **真实生产 PostgreSQL**：本轮在 SQLite 隔离测试与默认 settings 测试通过；生产 PG 仍需重跑迁移、并发和权限验收。
- **浏览器端人工验收**：已完成本地浏览器冒烟：学生登录并提交反馈、教师待办/详情/认领/确认/开始处理/标记已处理、事件核对显示 5 条事件全部关联；未做生产环境多账号并发验收。
- **真实附件存储/留存策略**：当前使用 Django 默认媒体存储，并在根路由显式拒绝 `/media/feedback_evidence/` 直接访问；生产需配置私有对象存储、留存期限、访问审计与删除任务。

## 10. 测试结果

2026-10-25，本地隔离 SQLite：

- `feedback_center`：21 个测试全部通过（默认 settings 与 `feedback_center.test_settings` 均通过）。
- `learning_map` + `feedback_center` 联合：59 个测试全部通过（默认 settings）。
- `manage.py check`：默认 settings 无问题。
- `makemigrations --check --dry-run`：无待生成迁移。
- 前端 `npm run build`：通过。
- 本地浏览器冒烟：学生提交反馈成功；教师待办显示 1 条待事实复核；详情页认领、确认、开始处理、标记已处理均成功；事件核对显示 5 条事件全部关联、0 待重试、0 不一致。

覆盖场景：三类路由、缺证待补、确认门禁、网络重试幂等、同尝试重复/跨类别、正常请求误拦不转识别、评分争议转模块六且不改成绩、人工更正留痕、驳回后新证据重开、随机抽查可复现/排除既往/不足全查/高风险单列、越权访问、附件可见性、事件同步失败重试、保存失败可重试、执行反馈关闭、全模型停用核心流程、优先级排序、第三阶段契约禁用。

## 11. 第三阶段交接

见 `docs/feedback/module7-phase3-handoff.md`。核心边界：

- 模块七持有问题组、候选审核、审批、发布、观察与回退状态；
- 模块八持有评测集、运行与报告；两边按 `candidate_id` / `run_id` / `report_id` 互跳，不复制报告；
- 审批绑定确切配置摘要与完整报告；配置/范围/报告变化后旧审批失效；
- 发布只影响后续教学任务，旧尝试与成绩不追溯改写；
- “反馈已处理”不能替代“候选已审批”或“配置已生效”。
