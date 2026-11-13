# 当前代码逻辑与联调检查

续查已经完成：原 16 类问题仍存在，新增 7 类，共 23 类。最新结果和分工见 [续查报告](./logic-audit-followup-20261113.md)。本文件保留上一轮检查与全量测试记录。

检查日期：2026-11-13（Asia/Shanghai）。以当前工作区为准，包含开始检查时已存在的未提交修改。本次没有修改业务代码、迁移真实数据、调用付费模型或启动/停止真实靶场；新增的是检查报告和隔离复现证据。

确认 **16 类问题**。其中多数可以直接修复并自动验证，不需要用户先手工重现。宠物原图恢复需要原始资产或接受替代设计；综合考试的计时规则需要在最终验收时确认。以下“复现成功”表示观察到了缺陷，不表示已经修复。

P1 表示应优先处理的核心流程、权限或成绩问题；P2 表示功能不一致、资源缺失和性能问题。

## 已确认问题

| 编号 | 优先级 | 问题和实际影响 | 当前代码与验证证据 | 处理归属 |
| --- | --- | --- | --- | --- |
| 01 | P1 | **数据实验室无法将证据交给技能核验模块。** 提交传入 `data_lab_evidence`，接收函数不接受，抛出未捕获的 `TypeError`。证据可以先保存，但核验与后续能力事实不能完成；重试仍会碰到同一错误。 | [提交调用](D:/aaa10/16015478源码/project-code/backend/data_lab/submissions.py:85)、[接收签名](D:/aaa10/16015478源码/project-code/backend/skill_review/services/submissions.py:95)。现有联合测试中 10 项报同一错误。[已存在的核验函数](D:/aaa10/16015478源码/project-code/backend/data_lab/verification.py:47) 也没有被接入，不能仅删除参数了事。 | 我可以补齐可信证据交接、核验器选择和失败重试，再跑跨模块回归。 |
| 02 | P1 | **理论考试到期才保存答案，被后端拒收。** 用户选择答案后等待到期，前端才逐题发送；后端已禁止新答案，前端停止交卷。未保存选择仍只在内存，刷新会丢失。若另行调用交卷接口，可能以 0 分结算。 | [到期处理](D:/aaa10/16015478源码/project-code/frontend/src/views/ExamTaking.vue:469)、[后端拒收](D:/aaa10/16015478源码/project-code/backend/exams/views.py:376)。真实后端复现正确答案返回 `400 exam_time_expired`，随后交卷 200、0 分；实际 SFC 探针验证保存失败后不继续交卷。 | 我可以修复持续保存、提交时序和恢复逻辑，并验证截止边界。无需用户先手测定位。 |
| 03 | P1 | **综合考试的实战时间从理论开始时就被消耗。** 实战记录在待开始时已有 `start_time`，理论完成仅改状态。理论耗时被计入实战时限，极端情况下刚进入实战已超时。 | [同时创建记录](D:/aaa10/16015478源码/project-code/backend/exams/comprehensive.py:65)、[激活不重置开始时间](D:/aaa10/16015478源码/project-code/backend/exams/views.py:358)。隔离复现理论开始 181 分钟后激活实战，第一题立即被判超时。 | 我可以修复状态和计时一致性；用户最终确认两部分分别计时还是整场共用时限。当前两个试卷分别有 duration，页面表现为分段开始。 |
| 04 | P1 | **管理员重新生成实战题，会删除历史答案。** 删除旧试卷关联题时，已完成及进行中的答题明细被外键级联删除，记录上的成绩却保留。 | [删除旧试题](D:/aaa10/16015478源码/project-code/backend/exams/views.py:138)、[答案外键](D:/aaa10/16015478源码/project-code/backend/exams/models.py:226)。实测已完成考试答案 `1 → 0`，成绩仍为 10。 | 我可以冻结已使用试卷，或引入试卷版本/快照，并验证重组题不改变历史。已被删除的真实明细若存在，需要从备份评估恢复。 |
| 05 | P1 | **实战考试只显示标题，漏掉实际题面。** 后端 `challenge` 是数字 ID，正文在 `challenge_description`；前端读取 `challenge.description`，从而丢失题目说明及正文里的附件、环境信息。 | [前端读取](D:/aaa10/16015478源码/project-code/frontend/src/views/ExamTaking.vue:114)、[真实序列化字段](D:/aaa10/16015478源码/project-code/backend/exams/serializers.py:63)。用真实接口数据形状执行实际 SFC，正文渲染输入仅剩标题。 | 我可以统一接口契约并补真实数据形状的回归。教师最后确认题面完整且可理解。 |
| 06 | P1 | **文章撤回后仍可被学生知识检索召回。** 文章详情已经 404，但保留的索引仍返回原文，可能再次成为 AI 回答依据。当前过滤主要处理上传 document，没有统一复核 article 等平台来源状态。 | [检索可见性](D:/aaa10/16015478源码/project-code/backend/legal_kb/services/visibility.py:76)。真实 `SafeKnowledgeRetrievalService.retrieve()` 的 SQLite 词法路径复现撤回后仍返回正文。 | 我可以统一来源权限过滤、失效处理和检索回归；真实 pgvector/嵌入服务再做环境联调。 |
| 07 | P1 | **来源撤权后聊天详情仍返回相关回答和来源摘录。** 历史权限辅助函数会正确隐藏，但实际 API 没有使用它，直接解密输出。加密保存本身无法替代读取权限检查。 | [聊天详情](D:/aaa10/16015478源码/project-code/backend/ai_assistant/views.py:447)。使用真实运行时加密、来源签名和文章撤回，文章详情 404，聊天详情仍 200，含回答和 `metadata.source_excerpt`。 | 我可以把来源权限校验接入实际历史读取；历史再次送入模型的路径也应一并核验。 |
| 08 | P1 | **独立内容生成缓存跨账号命中，并忽略关键参数。** B 生成相同主题时返回 A 创建的记录；同账号要求 10 题也可能返回缓存的 1 题。图表类型和编程语言同样未进入缓存键。 | [缓存键](D:/aaa10/16015478源码/project-code/backend/content_generator/generators.py:25)、[缓存对象返回](D:/aaa10/16015478源码/project-code/backend/content_generator/generators.py:147)、[测验缓存](D:/aaa10/16015478源码/project-code/backend/content_generator/generators.py:173)。跨用户归属和题数错配均已动态复现。 | 我可以补齐账号隔离与所有影响输出的参数，并验证缓存命中结果的归属。 |
| 09 | P2 | **管理员无法在审核前查看资料原文。** 页面要求先核对原文，但普通下载仅接受 approved，管理员和上传者对 pending 文件都得到 404。审批前只能看到元数据和封面。 | [下载状态限制](D:/aaa10/16015478源码/project-code/backend/resources/views.py:279)、[审核页入口](D:/aaa10/16015478源码/project-code/frontend/src/admin/views/Resources.vue:17)。隔离 HTTP 实测管理员列表 200、管理员原文下载 404、上传者原文下载 404。 | 我可以补充有权限的审核原文访问，不向普通学生开放未审核内容。 |
| 10 | P2 | **清空多选答案后仍按旧答案计分。** 第一次点提交会先保存答案；取消确认后清空选择，第二次保存跳过空答案，后台旧值还在。UI 可显示未答，但最终仍按旧值结算。 | [清空本地选择](D:/aaa10/16015478源码/project-code/frontend/src/views/ExamTaking.vue:155)、[跳过空答案](D:/aaa10/16015478源码/project-code/frontend/src/views/ExamTaking.vue:276)、[后端写入](D:/aaa10/16015478源码/project-code/backend/exams/views.py:442)。实际 SFC 探针复现 UI 已答 0、后台替身仍保留旧答案。 | 我可以统一空答案/删除答案语义，并做真实后端联调回归。 |
| 11 | P2 | **普通实战组卷可能抽到没有 Flag 的自由练习。** 题池只按难度和启用状态筛选，后续判题却必须比较 Flag。综合考试已排除此类题，普通实战生成器没有。 | [题池筛选](D:/aaa10/16015478源码/project-code/backend/exams/views.py:118)。隔离 HTTP 复现 `submission_mode='practice', flag=''` 被成功选入考试。 | 我可以补齐题池过滤和可判题校验。 |
| 12 | P2 | **生成内容详情的类型和编号混淆。** 四张独立自增表共用 `/content/<id>/`；先查教程遮蔽同编号的测验、图表或练习。自己的内容也可能因为先命中他人的教程而返回 404。 | [按表依次寻找 ID](D:/aaa10/16015478源码/project-code/backend/content_generator/views.py:65)、[归属检查](D:/aaa10/16015478源码/project-code/backend/content_generator/views.py:88)。真实 API 复现读取 quiz 1 返回 tutorial 1，以及自有 quiz 详情 404。 | 我可以用类型和 ID 联合定位，或统一内容标识，并同步路由与调用方。 |
| 13 | P2 | **重新生成仍复用缓存，没有产生新内容。** 接口返回 201 和原 ID、原内容，模型调用为 0；前端显示完成。 | [重新生成入口](D:/aaa10/16015478源码/project-code/backend/content_generator/views.py:253)、[缓存命中返回](D:/aaa10/16015478源码/project-code/backend/content_generator/generators.py:142)。已动态复现。 | 我可以增加明确的重新生成语义，正确失效或绕过本次缓存。此项与 08 共用缓存实现，但还有独立的用户操作语义。 |
| 14 | P2 | **模型失败被保存成生成成功。** 上游返回 fallback 和 `MODEL_CALL_FAILED` 时，生成器仍保存测验、返回 201；宣称 5 题但实际题目数组为空，还可能污染缓存。 | [读取生成结果](D:/aaa10/16015478源码/project-code/backend/content_generator/generators.py:183)、[真实上游失败契约](D:/aaa10/16015478源码/project-code/backend/ai_assistant/service.py:2897)。用该失败契约模拟供应商失败，真实生成 API 复现空测验持久化。 | 我可以检查上游状态和输出结构，使失败可重试且不保存为成功内容。 |
| 15 | P2 | **资源列表为显示加密状态而读取并解密所有文件。** 匿名列表也会执行，分页大小默认 20，单文件上限默认 50 MiB，满页大文件时每次可能处理约 1 GiB 内容，另有封面；这不是同时驻留内存大小。 | [列表序列化](D:/aaa10/16015478源码/project-code/backend/resources/serializers.py:46)、[状态探测](D:/aaa10/16015478源码/project-code/backend/data_security/runtime/storage.py:137)、[整文件读解密](D:/aaa10/16015478源码/project-code/backend/data_security/runtime/storage.py:98)。仅 3 个 1 MiB 文件，匿名 GET 列表已产生 3 次完整读取和 3 MiB 解密。 | 我可以把列表状态投影与完整性验证成本分开，保留下载时的安全核验，并做读取量回归。 |
| 16 | P2 | **五套宠物图片缺失。** dundun、xiaoju、yeye、gugu、xiaoqing 只有 manifest，没有 spritesheet.webp/png。页面退化到机器人兜底，换宠物或重试无法恢复原图。 | [图片引用](D:/aaa10/16015478源码/project-code/frontend/public/pets/dundun/pet.json:5)。文件检查和 Git 跟踪检查均缺图；前端 2 项测试失败涉及图片与资产证据文件缺失。 | 我可以恢复引用、完善缺失提示和验证。恢复原设计需要原图备份；无备份时需要用户接受替代形象。 |

内容生成问题 08、12、13、14 的影响范围为已注册的独立生成内容 API 和 `/content/:id` 页面。本轮没有找到主学习页面主动调用四个首次生成 API，不能据此推断全部 AI 导学功能失效。

## 需要联调的链路及分工

| 链路 | 我可以完成 | 用户/环境负责人需要参与 | 建议验收条件 |
| --- | --- | --- | --- |
| 考试：答题 → 保存 → 截止 → 交卷 → 实战 → 历史 | 修复 02–05、10–11；自动验证计时、刷新、清空答案、历史稳定性和接口字段 | 确认分段计时规则、题目内容与通过标准；在实际浏览器/手机完成一次验收 | 截止前已确认保存的答案不丢；实战开始时间正确；历史成绩与明细一致；题面完整 |
| 数据实验室 → 技能核验 → 能力事实/成长展示 | 修复 01，连接可信证据核验器、幂等和失败重试，做隔离集成测试 | 教师确认材料、人工量表、能力结论及复测要求 | 一次有效提交形成正确核验事实；重试不重复计数；故障可恢复且不伪造成绩 |
| 资料审核 → 索引/缓存 → AI 检索 → 聊天历史 | 修复 06–09，验证双账号访问、撤回材料、缓存失效、审核下载权限 | 教师确认哪些内容应公开、哪些只供教学；评阅引用准确性 | 来源撤回后新检索和历史展示均遵守当前权限；管理员可先审阅原文 |
| 生成内容 → 类型路由 → 详情 → 重新生成 → 失败提示 | 修复 08、12–14，统一前后端契约并模拟失败/重试 | 评阅生成内容的正确性、难度和教学适用性 | 账号与参数正确，详情类型一致，重新生成语义真实，模型失败不冒充成功 |
| 模块五真实靶场 → 服务端证据 → 六 → 一 → 修复/复测 | 可继续做部署检查、接口和自动化验收；已有 4 项隔离主链测试通过 | 可运行的 Linux/Docker 环境、真实 Juice Shop/FRP 路由；两名学生角色进行实际隔离与体验验收 | 环境互不串用；资源限制有效；停止、超时、异常回收正确；核验不可由客户端伪造 |
| 反馈 → 候选 → 评测 → 审批 → 生效/回退 | 前后端、状态机、报告绑定与事件对账可自动联调 | 使用真实教学候选、独立审批角色，确认发布/观察/回退规则 | 审批与确切报告/配置一致；仅后续尝试生效；失败可对账；旧成绩不被改写 |
| PostgreSQL/pgvector、模型服务、Nginx/Gunicorn 流式对话 | 可检查配置、语义检索、超时、断线、重试、Cookie/CSRF、深链接和并发 | 有效供应商权限/额度、部署域名与证书、目标服务器；教师评阅回答与引用 | 实际语义召回有质量，失败有正确提示，流式中断后消息和状态一致 |
| 历史数据保护与备份恢复 | 可以盘点、写迁移/恢复检查，先在副本中验证 | 指定目标数据副本、备份介质和上线窗口；确认保留期限 | 密钥与数据库/文件配套，重建可解密；历史数据状态经过盘点；本轮未迁移真实数据 |

用户不需要替我排查代码异常。真正需要人工实测的是：真实设备和网络的操作体验、多人靶场隔离及回收、教学内容与能力评价是否合理、真实模型质量。环境配置就绪后，技术联调仍可由我执行。

## 实际运行结果

| 检查 | 本轮结果 | 证据 |
| --- | --- | --- |
| 前端现有全量 node tests | 938 项：936 通过、2 失败。失败涉及宠物图片与资产证据缺失 | [日志](D:/aaa10/16015478源码/project-code/frontend/artifacts/audit-frontend-tests-20261113.log) |
| 前端生产构建 | 通过，有大 chunk 警告；不等同于业务流程通过 | [日志](D:/aaa10/16015478源码/project-code/frontend/artifacts/audit-frontend-build-20261113.log) |
| 加密、私有文件、法律导出、资源后端回归 | 81/81 通过，独立 SQLite | [日志](D:/aaa10/16015478源码/project-code/.state/current-audit-20261113/backend-regression.log) |
| 考试、用户、学习路径专项回归 | 26/26 通过，独立 PostgreSQL | [日志](D:/aaa10/16015478源码/project-code/artifacts/full-audit-20261113/audit-learning-review.log) |
| 反馈与数据实验室联合回归 | 111 项：101 通过、10 项错误，均为问题 01 的参数/接线错误 | [日志](D:/aaa10/16015478源码/project-code/.state/current-audit-20261113/feedback-data-lab-regression.log) |
| 模块五交接专项 | 4/4 通过，合成 PostgreSQL 和本地 HTTP fixture；未使用真实 Docker 靶场 | [日志](D:/aaa10/16015478源码/project-code/artifacts/full-audit-20261113/logic-review-m5-handoff.log) |
| 模型迁移一致性 | `makemigrations --check --dry-run`：No changes detected | 在隔离 settings 下执行，不变更真实库 |
| 当前本地入口 | 后端 `127.0.0.1:8000/proxy/health/` 和前端 `127.0.0.1:5176/` 均 200 | 只读 HTTP 检查，未登录或变更业务 |
| Docker 完整部署 | 当前 Linux Engine 管道不存在；Compose 校验因缺 `TLS_CERT_DIR` 失败 | 本轮重新执行 `docker version` 与 `docker compose config --quiet`，不能声称部署已验收 |

后端上述四组现有测试合计 222 项：212 通过，10 项错误。前端与后端测试数量分列，新增缺陷复现不混入“通过的产品回归”统计。

专项证据：

- [考试 4 个缺陷复现](D:/aaa10/16015478源码/project-code/artifacts/full-audit-20261113/logic-review-learning-repros.log)，[可重跑脚本](D:/aaa10/16015478源码/project-code/artifacts/logic_review_learning_repro.py)。
- [前端实际 SFC 考试探针](D:/aaa10/16015478源码/project-code/frontend/artifacts/audit-exam-probes-20261113.mjs)：部分 HTTP 边界使用模拟响应，已另用真实后端复现到期拒收。
- [资源审核及列表读取量复现](D:/aaa10/16015478源码/project-code/.state/current-audit-20261113/root-repro.log)，[脚本](D:/aaa10/16015478源码/project-code/.state/current-audit-20261113/root_repro.py)。
- [生成内容复现](D:/aaa10/16015478源码/project-code/.state/current-audit-20261113/ai_content_repro.json)，[脚本](D:/aaa10/16015478源码/project-code/.state/current-audit-20261113/ai_content_repro.py)。
- [聊天撤权复现](D:/aaa10/16015478源码/project-code/.state/current-audit-20261113/ai_history_repro.json)，[脚本](D:/aaa10/16015478源码/project-code/.state/current-audit-20261113/ai_history_repro.py)。
- [知识检索撤权复现](D:/aaa10/16015478源码/project-code/.state/current-audit-20261113/ai_retrieval_revocation_repro.json)，[脚本](D:/aaa10/16015478源码/project-code/.state/current-audit-20261113/ai_retrieval_revocation_repro.py)。

## 覆盖范围与处理顺序

优先处理：01 的提交断链、06–08 的权限/账号隔离、02–05 的考试成绩与核心可用性。随后处理审核访问、答案清空、题池和生成内容契约，最后优化列表读取成本并补齐宠物资产。

深入检查了考试、资源审核下载、数据实验室交接、AI 历史、知识检索和独立内容生成；运行了反馈、私有存储、法律导出、用户/学习路径及模块五部分回归。实训授权生命周期、学习地图、学生画像、agent_runtime、teaching_agent、rag_ingestion、legal 等还做了入口和部分流程抽查。**本报告不是全项目逐接口穷尽证明，没有列出的问题不代表已经确认无缺陷。**

未执行真实模型调用、生产负载、真实 Linux Docker/FRP 靶场、正式教师课程签收，也未确认历史数据已经全部完成加密迁移。模块五在隔离链路中有独立的可信证据适配器，已通过专项检查，不能因为模块四的接线错误而把模块五同样列为断链。

环境附注：首次内容复现的临时 SQLite 因线程连接占用未自动清理；后续清理命令被自动审批以 `blocked by policy` 拒绝，未给出更具体原因。已停止删除并保留仅含合成数据的临时证据，所需交付结果已放入工作区，不影响本次检查完成。
