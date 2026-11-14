# 模块七第三阶段交接清单

状态：**第三阶段服务与接口已实现，写入和发布默认关闭。** 当前代码已提供问题组、候选管理、审批、发布、观察与回退；分别由 `FEEDBACK_PHASE3_ENABLED` 和 `FEEDBACK_PHASE3_RELEASE_ENABLED` 控制。默认关闭不代表接口缺失，也不代表真实教学联调或正式开放已经验收。下文保留交接契约和人工验收要求；实际路由与服务见 `backend/feedback_center/urls.py`、`services/issue_groups.py`、`services/candidates.py`。

## 1. 不可违反的边界

1. “反馈已处理”不等于“新规则已生效”，也不等于“教学效果已验证”。
2. 候选只能引用已确认、证据完整、映射完整且非重复的反馈。缺证/未映射记录不能进入候选验收或能力提升统计。
3. 同尝试去重只处理重复提交；跨尝试问题组必须由反馈负责人人工确认成员，保存纳入/排除理由、版本和审核人。
4. 模块八持有评测集、运行与报告；模块七持有候选审核、发布、观察与回退状态。两边引用同一报告，不复制评测或成绩系统。
5. 审批绑定确切配置摘要、报告版本和适用范围；配置、数据或范围变化后旧审批立即失效。
6. 发布只影响后续教学任务；已开始尝试保持领取时版本，旧判定与成绩不追溯改写。
7. 回退保留前后版本、审批、评测、操作者和结果；失败或未知状态不得报成功，保留待对账。
8. 全模型停用（生成、向量化、模型重排）时，规则汇总、人工复核、问题组和候选登记仍可工作。

## 2. 跨尝试问题组

实际接口：`POST /api/feedback/teacher/phase3/issue-groups/`（已实现；默认写入门禁关闭，需在隔离评测或已批准的第三阶段环境配置开关）。

请求/响应字段：

```json
{
  "group_id": "uuid",
  "category": "recognition|decision|teaching",
  "issue_type": "stable issue type",
  "task_key": "TASK-...",
  "task_version": "1.0.0",
  "catalog_version": "v1",
  "knowledge_point_ids": ["KP-..."],
  "time_window": {"from": "2026-10-01T00:00:00+08:00", "to": "2026-10-31T23:59:59+08:00"},
  "member_feedback_ids": ["feedback uuid"],
  "excluded_feedback_ids": ["feedback uuid"],
  "exclusion_reasons": {"feedback uuid": "缺证/不同版本/非独立"},
  "counts": {
    "raw_feedback": 0,
    "deduplicated_instances": 0,
    "distinct_students": 0,
    "missing_evidence": 0
  },
  "reviewed_by": 1,
  "reviewed_at": "ISO 8601",
  "version": 1,
  "supersedes_group_id": null,
  "split_merge_history": []
}
```

实现要求：

- 只允许已确认、证据完整、映射完整且非重复的反馈进入成员候选；
- 同尝试同类别同争议只计一个实例；重复投诉不增加独立证据；
- 不同任务/版本默认分列；要汇总必须先由课程负责人审核可比性与映射；
- 拆组、并组新增版本并保留历史；
- 同时展示原始反馈数、去重实例数、不同学生数、缺证数，不能混用；
- 单条高影响已确认问题也可建组提出候选，不以投诉量设门槛。

## 3. 候选与配置版本

建议状态机：

`draft → pending_eval → evaluating → needs_revision → pending_approval → approved_pending_release → observing → stable / rolled_back / withdrawn`

候选字段：

- `candidate_id`
- `issue_group_ids`
- `baseline_config_version`
- `candidate_config_version`
- `single_changed_factor`
- `target_task_versions`
- `excluded_scope`
- `expected_risk`
- `owner_id`
- `rollback_version`
- `config_digest`
- `evaluation_report_ref`
- `approval`
- `activation`
- `observation`
- `rollback`

实现要求：

- 一次优先只改一个因素；组合改动必须在报告说明；
- 配置摘要、数据集版本、目录/事件版本、验证器版本必须冻结；
- 评测运行不得写正式配置；
- 证据不足退回草稿；失败、缺依赖或中断如实登记，不能跳过后标通过；
- 候选作者不能独自完成终验和审批。

## 4. 模块八评测报告引用

```json
{
  "run_id": "m8-run-001",
  "report_id": "m8-report-001",
  "report_version": "1",
  "report_digest": "sha256",
  "dataset_version": "acceptance-v1",
  "baseline_config_digest": "sha256",
  "candidate_config_digest": "sha256",
  "recommendation": "pass|fail|insufficient_evidence",
  "completed": true,
  "missing_cases": 0
}
```

- 模块七不导入报告正文，只保存引用与摘要；
- 报告不完整、摘要不匹配、关键案例失败或退化未解释时，不能进入待审批；
- 教师从模块八“评估中心”与模块七“候选管理”按候选 ID 互相跳转，打开同一报告；
- 重复导入不得产生第二份业务结论。

## 5. 人工审批

- 审批人必须有明确授权，不能是候选作者本人；
- 审批记录包含：审批人、时间、确切配置摘要、报告 ID/版本、适用范围、观察窗口、回退条件；
- 审批只改变状态，不触发执行或发布；
- 当前生效版本与审批所用基准不一致时，旧审批失效，重新评测审批。

## 6. 生效、观察与回退

- 发布人核对当前基准与审批绑定后显式生效，记录生效时间、适用后续任务和配置摘要；
- 观察方案在审批前固定任务版本、时间窗、样本要求、停止条件；
- 关注新失败、正常误拦、越权放行、缺证和教师异议；样本不足保留“观察中/证据不足”；
- 关键授权反例失败或实际配置不匹配时暂停扩用并人工回退；
- 回退记录前后版本、操作者、原因、结果；失败/未知状态待对账，不能显示成功；
- 学生旧成绩和已开始尝试不变。

## 7. 首个候选建议

限定为“教学模拟导出阈值 T=100 → T=120”（虚构待审核示例，不是已部署参数）：

- 只改变 T，不改分类分级、标注真值、累计规则或授权条件；
- 验收数据包含正常、越权、缺事实和边界案例（99/100/101/119/120/121 条）；
- 教师依据事先审核的任务事实独立标注预期，不按候选输出倒填真值；
- 全部关键授权反例通过、目标误拦修正、其他案例无未解释退化；
- 模块八开发/回归/终验集合隔离；终验案例用于调参后退出终验并补新版本；
- 首期全程不触发实际导出、生产配额或生产策略修改。

## 8. 当前已实现但默认未启用的接口

- `GET /api/feedback/teacher/phase3/contracts/`：返回完整字段、状态机、边界和后续任务清单；
- `POST /api/feedback/teacher/phase3/candidates/`：已实现；写入开关关闭时返回 `409 phase3_write_disabled`，开启后仍须通过权限与业务校验；
- 问题组、候选及状态事件表已由迁移 `0002_feedbackcandidate_feedbackcandidateevent_and_more` 提供。审批、生效、观察与回退均有服务和路由；发布开关关闭时返回 `409 phase3_release_disabled`。真实评测、独立审批和部署验收仍须另外完成。

## 9. 原任务清单与当前验收状态

M7-P3-1 至 M7-P3-6 已有实现，代码位置见下节；清单保留用于逐项验收，不能据此认定功能缺失。M7-P3-7 至 M7-P3-9 仍需按真实业务和部署条件确认。

- M7-P3-1 跨尝试问题组与人工成员确认；
- M7-P3-2 候选与配置版本状态机；
- M7-P3-3 模块八报告引用与逐例差异互跳；
- M7-P3-4 人工审批与权限分离；
- M7-P3-5 生效、观察与样本不足处理；
- M7-P3-6 回退、失败与待对账状态；
- M7-P3-7 首个阈值候选闭环与独立终验；
- M7-P3-8 全模型停用下的问题组/候选登记验收；
- M7-P3-9 生产 PostgreSQL 并发、权限与审计验收。


---

## 实施更新（第三阶段已实现，默认关闭）

原先列为后续任务的 M7-P3-1 至 M7-P3-6 已实现，代码位置：

- `feedback_center/services/issue_groups.py`：跨尝试问题组、成员人工确认、计数快照、拆组/并组历史。
- `feedback_center/services/candidates.py`：候选状态机、报告引用绑定、审批、生效、观察、稳定、回退。
- `feedback_center/services/dispute_link.py`：评分争议转交模块六并镜像状态；模块七不改成绩。
- `frontend/src/teacher/FeedbackCandidates.vue`：教师端问题组与候选管理页。

开关（默认 false）：

- `FEEDBACK_PHASE3_ENABLED`：候选写入、评测登记、审批。
- `FEEDBACK_PHASE3_RELEASE_ENABLED`：生效、观察、稳定、回退。

模块八现已提供持久化 `EvaluationRun`、`EvaluationCaseResult`、`EvaluationReport` 和报告读取/校验服务；隔离运行仅在其测试配置和权限门槛满足时允许。真实发布仍需显式开启第三阶段开关，并将确切候选、配置版本与完整报告核对；本交接文档不代替服务端校验回归或实际教学验收。详见 `backend/evaluation_center/README.md`。
