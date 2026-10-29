# §12 首期验收对照（2026-10-29）

本表区分自动验证与开放签收；**没有代签或自动开放**。最终固定验收10/10、教学相关141/141（含data_lab 57/57）；全量695发现、678通过、11跳过、5 FAIL、1 ERROR，与用户提供基线的失败/错误ID集合相同，无新增失败。完整对账以根目录 `DELIVERY.md` 和 `evidence/d4-reconciliation.json` 为准；全量不是全绿。

| §12 项 | 实施/证据 | 结论 |
|---|---|---|
| 1 版本与双审、复测题 | 两案合成CSV文件及版本/hash；独立合成日志场景；register_data_lab只建draft，拒绝跨目录同版本及已签收覆盖，签收表全待办 | 候选材料完成；真实双人审校未做，不通过开放门禁 |
| 2 合成边界 | test_materials登记白名单/固定SHA/6行；run_worker仅接受服务器固定资源 | 本地通过，不支持任意上传或生产样本 |
| 3 学生与教师授权 | test_api/test_scanning/test_submissions跨学生；data_lab教师详情/附件/操作均角色+对象检查 | 模块四入口通过；模块六通用教师入口对象ACL联动尚缺，整体开放阻断 |
| 4 位置 | test_materials/test_scanning中文、emoji、换行、空值、全角；前端codepoints Node测试 | 本地通过；未做真实浏览器交互 |
| 5 检测口径 | original/人工补录/复核后分列；精确逻辑行列+码点span+类别匹配；客户原TP8/FP1/FN2 | 本地通过，仅6行固定合成集，不支持生产性能结论 |
| 6 四动作/冲突 | test_scanning四动作、旧profile、幂等异内容、重扫；test_acceptance失效CAS、丢失最终事务恢复 | 本地顺序竞争/CAS通过；部署同类DB真实并发未验证 |
| 7 四轮 | test_replay A1 mask、A2 deny、A3 defer、A4 mask→require_approval，固定时刻/B-v1/draft/50与51 | 本地通过，参考画像不是学生检测覆盖 |
| 8 只读哨兵 | test_replay与test_acceptance覆盖完整领取→识别→复核→回放→提交→核验→记录→复测 | prepare/claim/consume、父进程网络、四类执行记录全0；里程碑I无实现 |
| 9 可信字段 | test_replay拒绝source/env/auth/hash/policy/path/url；test_submissions禁止通用六接口伪造证据上下文 | 本地通过；无可提交给执行端的授权结构 |
| 10 故障 | 解析失败保留；提交/六事件失败回滚并保留待重试；证据损坏不产生六成绩/一事实 | 本地通过，未把故障算作知识错误或通过 |
| 11 程序/人工 | 真实六VerificationResult与ManualReviewTask；program passed但overall pending_manual；执行/保护不计分 | 本地通过；教师真实评分未做 |
| 12 幂等与对账 | test_submissions真实重试；test_handoff严格全字段、稳定事件ID、修订不回退、失败notice恢复 | 本地通过；没有部署异步对账服务，需人工/API重试 |
| 13 帮助 | request/display分开、card来源、教师层级、missing/旧解析unknown；普通AI提示入口不存在 | 卡片/教师本地通过；AI帮助展示未接入，不声称AI来源联调完成 |
| 14 五类无AI | disconnected/timeout/429/quota_exhausted/all_models_disabled五个独立测试，各完成两案真实链 | 本地通过；为故障替身，模型调用均0，未制造真实外部429；复测时钟模拟，非三日学习效果 |
| 15 答案/解析/缓存 | 教师附件独立鉴权；解析解锁与撤回；no-store；学生源码和dist禁用键扫描；恢复不重跑worker | 模块四本地通过；模块三知识包/权限服务不在本worktree，未联调 |
| 16 六/一/八与教师队列 | 六真实收到证据、一真实VerificationFact；同版本notice；人工必评记录；八明确not_connected | 六→一本地通过；八接点、普通抽查及六通用教师ACL联动未完成 |

## 只读/无模型测试的具体边界

`test_acceptance.py` 对 prepare_execution、claim、consume、requests Session.request、socket.connect、MultiAgentChatService的chat/tutoring、EmbeddingService的embed_text/embed_many、LegalRetrievalService.retrieve（封住检索/排序入口）、mainline1.run_semantic 注入相应故障并断言未被调用。每种情形都真实保存两案扫描/复核/回放、模块六结果、模块一事实、复盘和RetestAssignment。执行数据库检查包括 RiskDecision、ExecutionAuthorizationRecord、QuotaReservation、DeliveryRecord。

系统没有独立rerank方法；测试阻断整个检索/排序入口，不宣称验证了不存在的rerank SDK。worker在单独受限进程中运行固定规则，父进程mock不跨进程传播；代码路径不含模型/导出服务，但这不是网络隔离容器证明。

## 开放决定

**不开放。** 本地自动测试通过不代替课程签收、跨模块权限联动、跨worktree联调、部署同类数据库并发验证或人工评分。Presidio隔离验证本轮未做，未安装到公共venv；使用本地固定合成规则，不把“未做”描述成“验证失败后降级”。
