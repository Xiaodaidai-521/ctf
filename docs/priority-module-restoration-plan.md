# 优先模块恢复与真实性修复方案

日期：2026-11-11（Asia/Shanghai）  
设计基线：`main@0f7f451`  
状态：方案已形成，应用代码尚未修改，运行验收尚未执行。

本轮目标是恢复已合并模块的应用注册、API、页面和必要调用，修复个人评分及评测报告中的虚假结果，让模块可以进入后续调试。按当前安全装配定点恢复，既有分支只用于核对功能差异。本轮完成标准为“接入恢复、数据表达可信、最小操作可验证”。正式数据接入、真实模型效果和完整业务闭环另行验收。

## 1. 范围与完成状态

| 原优先分支 | 本轮交付 | 对应工作包 | 后续阶段 |
| --- | --- | --- | --- |
| `feat/frontend-overhaul` | 新版页面壳、路由、菜单、旧链接兼容；评分及个人学情真实性修复 | R2、R5 | 全站体验和完整教学闭环 |
| `feat/agent-memory-wiring-2` | 会话作用域、台账、长期记忆读写/召回/遗忘接回当前编排器 | R3 | 实际学生长期对话效果 |
| `feat/module2-teaching-agent` | 应用/API、任务上下文、事件兼容、可用状态和超时降级表达 | R0、R1、R3 | 真实模型提示质量与教师介入闭环 |
| `feat/module3-knowledge-base` | 学生/教师知识入口、资料读取、权限及答案隔离冒烟 | R1、R4 | 正式资料审核→发布→撤回全流程 |
| `feat/module4-case-lab` | 案例学生/教师入口、列表/详情读取及身份权限 | R1、R4 | 领取→识别→复核→提交及模块交接 |
| `feat/module5-practical-training` | 后端装配、映射/分配查询、最小前端入口 | R1、R4 | 领取→启动→核验→回收和真实容器 |
| `feat/module8-evaluation-center` | 评估API、统计组件、真实报告引用读取与校验接入 | R1、R4、R6 | 真实学习投影和正式模型评测 |
| `feature/modules-1-6-7-phase3` | 候选报告真实性核验与发布范围约束 | R6 | 诊断→任务→核验→能力更新→反馈 |
| `feat/rag-improvement` | 资料库入口、切块回退改进、迁移/索引状态一致性 | R0、R2、R7 | 正式语料召回效果及批量重建索引 |

暂缓原表中的重点链条：数据安全全流程、受控导出、导出风险及滚动行为基线、敏感识别业务化、上传并发与失败恢复、容器代理生命周期、真实数据及正式向量服务接入。只对本轮改动可能影响的既有安全边界做定向回归。

统一使用以下验收状态，避免混淆：

- **已接入**：应用可加载，正式根路由及页面可解析。
- **已最小验收**：隔离数据下的指定操作、权限及失败状态通过。
- **待联调**：外部模型、容器、真实业务资料或完整链条尚未验收。

## 2. 已核实的恢复前置问题

| 当前源码证据 | 设计判断 |
| --- | --- |
| `backend/ctf_backend/settings.py:49`、`urls.py:34`；合并提交与第一父提交的差异 | 六个应用注册及六个模块API前缀被移除，源码和迁移仍在 |
| `backend/legal_kb/migrations/0006_legaldocument_canary_payload.py:5`、`0006_legalknowledgeembedding_index_version.py:5` | 两条迁移均依赖同一条0005，需要统一迁移图；当前embedding模型还缺少已有迁移中的index_version |
| `backend/learning_analytics/models.py:105`、`migrations/0011_learningbehaviorevent_event_id_and_more.py:15` | LearningBehaviorEvent模型缺少迁移定义的event_id，事件类型也需核对 |
| `backend/teaching_agent/events.py:35`、`backend/learning_analytics/events.py:9` | 教学调用使用event_id/strict，共享函数已不接受这些参数 |
| `backend/agent_memory/ledger.py:44`、`long_term.py:105` | 记忆服务保留，但非测试业务调用已断开；只注册应用不能恢复记忆 |
| `frontend/src/teacher/FeedbackCandidates.vue:238`、`backend/feedback_center/services/candidates.py:149` | 前端生成虚构报告，后端登记接口信任传入JSON |
| `backend/evaluation_center/evaluations.py:499` | 可信报告解析仍在，可以恢复调用，无需重建校验引擎 |
| `backend/learning_analytics/views.py:572`、`:794` | 教师名单接口沿用管理员全平台学生查询，需要补授权对象范围 |
| `backend/users/permissions.py:8`、`models.py:88` | 已有CourseDataGrant课程授权可复用；授权名单不等同于完整班级成员管理 |
| `backend/evaluation_center/views.py:61`、`:86` | 评估学生名单和教师尝试读取也缺少课程授权范围，评分与评估学情必须同步修复 |
| `backend/agent_memory/models.py:27`、`ledger.py:158`、`backend/ctf_backend/security_bootstrap.py:981` | 首问、教学快照及响应缓存等普通字段尚未纳入现有字段保护所有者，需要核对恢复后新增副本出口 |
| `frontend/src/views/LearningAnalytics.vue:236`、`:295`、`:497` | 除雷达外，旧页个人热力图及趋势也含公式生成数据 |
| `backend/rag_ingestion/chunking.py:86` | 内置切块回退不传overlap，标题路径恢复也被覆盖 |

以上是静态源码及分支差异结论。具体启动、数据库迁移和运行行为仍需实施后的隔离验收确认。

## 3. 实施顺序与依赖

先完成 `R0 → R1 → R2`，建立可启动、可导航的基础。随后并行推进：

- R3：教学事件与记忆；依赖R0/R1及知识应用可加载。
- R4：模块最小入口；依赖R1/R2，实训新增入口控制在查询范围。
- R5：真实评分与学情；后端授权和前端页面一起交付。
- R6：可信报告；后端依赖R1，前端可与R2并行修改，早于任何候选写入/发布启用。
- R7：RAG切块；依赖R0，保留当前安全管道。

最后执行R8汇总验收。R1完成后可以开展恢复调试，R8通过后才把本轮标为完成。

### R0：统一迁移图、模型与事件基础

1. 为legal_kb新增合并迁移，保留既有蜜标和索引版本迁移，不修改已发布迁移历史。
2. 同步LegalKnowledgeEmbedding.index_version与既有迁移。索引版本和当前metadata.vector_space各自含义需明确，不能用补字段为未知历史向量补造语义来源。
3. 同步LearningBehaviorEvent.event_id及教学相关事件类型，保留无event_id的历史记录和旧调用。
4. 检查恢复应用的跨应用迁移依赖及意外字段删除。

验收：迁移图无冲突；模型状态检查无非预期变更；带pgvector的隔离空PostgreSQL库能够完整迁移。已有数据库的迁移历史只做核对，实际业务库升级和数据回填延后。

### R1：恢复六模块后端装配

| 应用名 | 正式API契约 |
| --- | --- |
| teaching_agent | `/api/teaching/` |
| learning_knowledge | `/api/learning-knowledge/`、`/api/teaching-knowledge/` |
| data_lab | `/api/data-lab/` |
| practical_training | `/api/practical-training/` |
| evaluation_center | `/api/evaluation/` |
| agent_memory | 通过聊天编排器和工具接入，无独立API |

补回settings和根urls中的装配。恢复教学总等待预算、熔断、探测、缓存配置，继续采用现有安全供应器入口。检查agent_memory信号及缓存包装重复注册问题。

验收：正常配置可启动并通过Django check；正式根路由可解析；未登录、越权角色以及学生访问其他学生对象的请求被拒绝；评测执行保留独立manage_evaluation权限。教师评分和评估学情的课程授权范围按R5验收。测试/服务令牌适配器仅在显式隔离配置使用。

### R2：恢复新版页面壳、路由和菜单

核心文件：`frontend/src/router/index.js`、`App.vue`、`teacher/TeacherLayout.vue`及`shared/navigation/`；保留当前新增数据安全管理入口和认证流程。

- 学生：guide、成长总览、任务绑定的learning-knowledge、案例专题入口、测评记录/结果深链。
- 教师：评分、学情、材料、知识、教学安排、学习路径管理、学生成长与学习证据、案例监督。
- 管理员：知识库tools/health/authorization/materials子页及案例监督。
- 完整knowledge/资料库保留教师和管理员权限；学生读取任务授权的学习材料。
- 接回现有canOpen/guardDestination；旧analytics、data-lab、测评URL做兼容，保留参数和片段。

验收：所有菜单目标可解析；按角色进入正确页面；深链刷新正常；换账号、退出及授权失败清理缓存和在途旧响应。导航出现后，缺外部能力的动作显示未配置/不可用及相应状态。

### R3：恢复教学事件、任务上下文和记忆

核心文件：`learning_analytics/events.py`、`teaching_agent/`、`agent_memory/`、`ai_assistant/tutor_request_orchestrator.py`、`ai_assistant/history.py`、`agents/context/teaching_context.py`。

1. 恢复event_id、strict及冲突异常契约。同ID同内容幂等，同ID异内容报冲突；旧调用继续允许无ID的尽力记录，新教学状态所需记录失败不得被吞掉后宣称成功。
2. 接回任务上下文和知识材料快照权限，再接会话作用域、台账、结构化长期记忆更新、召回及遗忘工具。
3. 接回历史来源绑定及create_message语义，适配当前ProtectedModel、内容保护和readable权限；缓存键包含用户、会话和任务作用域。
4. 提示请求与展示记录区分；显式表达超时、服务不可用和降级来源。
5. 逐一检查首问、上下文快照、响应缓存和回放等新增正文副本。保存经过当前保护层的投影；必须保留原文的字段接入现有FieldStorage及相应模型适配，读取仍受当前授权约束。已绑定保护模式下，未适配的出口不启用，保护失败拒绝写入/回放。历史字段回填和密钥轮换延后。

验收：本地测试适配器可完成一次教学请求及对应事件；重复请求不重复记账；隔离库中的记忆写入/读回、同会话召回、跨用户/任务隔离、遗忘及撤权行为通过。使用合成敏感样本核对已绑定保护模式下的新增数据库副本、缓存及回放，无非授权明文泄漏。测试适配器的结果只证明接线与状态行为，真实模型响应质量延后。

### R4：补齐知识、案例、实训和评估最小入口

复用现存learningKnowledge、DataLab、EvaluationStatistics页面和API；对学生答案、教师资料、案例对象和评测报告检查现有角色/对象授权。

- 知识：教师/管理员搜索、详情及资料列表；学生读取任务授权材料，不能进入完整资料库。缺资料明确空态。
- 案例：列表/详情和教师监督入口；合成案例继续注明教学用途。
- 实训：恢复映射和个人分配查询。当前未发现模块5专属前端API或页面，需补一个最小列表/详情入口；启动、核验、回收的完整交互留给容器联调阶段。
- 评估：接入学生/学情/报告查询及统计组件，零分母、缺记录和不可用依赖保留明确状态。

验收：通过正式前后端契约取得隔离测试记录；空库可正常显示空态；越权不可读；服务失败不会回退到假记录。未验收的完整写入流程列为待联调，不以入口可见宣称可用。

### R5：修复真实评分、个人学情和教师授权范围

核心文件：`teacher/assessment/`、`teacher/insights/`、`teacher/mockTeacherAnalytics.js`、`admin/views/LearningScores.vue`、`views/LearningAnalytics.vue`、`learning_analytics/views.py`、`evaluation_center/views.py`及`users/permissions.py`。

1. 教师评分接回TeacherAssessment及已有teacher API；管理员评分只调用admin API，移除运行时模拟名单和本地内存保存。
2. 用户名123、user_1、126不影响数据来源、选择逻辑或权限。
3. 课程范围明确传入服务端；教师名单以有效CourseDataGrant过滤，指定学生评分、计划、学情读写均校验相同范围。同步约束评估students/learning/attempt/runtime接口，在统计和分页前限制授权学生及课程任务，避免新版学情页经评估API取得全平台数据。核对任务与课程的服务端关联；无法确定范围时返回不可用/拒绝，不能凭客户端声明授予权限。未选择课程或无授权时返回空态/拒绝，不退回全平台名单。复用现有授权机制，不自动建立真实授权关系。
4. 评分保存后以服务端回读确认；超时明确结果未知，重新核对，避免重复提交和虚假成功。
5. 两次评分比较真实两次结果；一次只显示单次；零次显示暂无有效评分。缺维度不伪装成零分。热力图和趋势只使用真实行为记录。
6. 新版LearningActivity中独立标明且不参与个人统计的参考示意可保留；旧页冒充个人历史的公式数据清除。仍可访问的旧页也要修复。

验收：同名账号不进入演示路径；评分刷新/重新登录仍存在；零/一/两次评分和部分缺维度各有正确状态；教师不能越权读取或评分；撤权及换账号后旧数据清空。课程授权名单作为本轮可交付边界，完整真实班级成员管理另行对接。

### R6：恢复评测报告真实性核验

核心文件：`feedback_center/services/candidates.py`、`evaluation_center/evaluations.py`、`teacher/FeedbackCandidates.vue`及`teacher/feedback/candidateImport.js`。

1. 恢复现有resolve_report调用及_trusted_report封装，查数据库中的run/report，重验清单、逐例结果、报告摘要、候选UUID、配置/版本、改动因素和任务范围。
2. 登记时保存服务端规范引用；完成评测、审批、审批有效性/发布时重新核验。恢复发布范围属于已评测任务范围的约束。
3. 前端导入真实报告引用，取消时间戳run/report编号和固定pass/completed；候选配置也使用实际输入，去除固定100→120配置。
4. 历史不可验证引用保留供追溯，但不能继续审批/发布；提示重新评测。遇到模块不可用、报告缺失或损坏，拒绝放行。
5. 保持FEEDBACK_PHASE3_ENABLED和FEEDBACK_PHASE3_RELEASE_ENABLED默认关闭，仅在隔离验收启用。

负向验收：虚构ID、跨候选复用、配置/范围变更、逐例/清单/摘要被改或删除、失败结果改写pass、缺例/未完成、登记后篡改、发布范围扩大均不能通过后续关口。现有“伪造能放行”的复现改为拒绝回归；phase3成功夹具使用持久化报告factory。

报告完整性与效果真实性分别标记。数据库真实生成且可校验的offline合成回归报告可以用于其冻结范围；保留offline/simulated/input_source等来源标记，不能据此宣称真实学生效果或正式业务全链通过。

### R7：定点恢复RAG切块改进

核心文件：`rag_ingestion/chunking.py`、`legal_kb/services/chunking_service.py`及R0中的模型/迁移。通过当前security_bootstrap.assemble_rag装配，保留解析后、切块前的正文/metadata保护及既有向量空间隔离。

- 恢复中文句界、overlap、窗口参数校验、细尾处理和内置回退的Markdown标题路径。
- 以恢复分支的800/100作为教学切块候选默认；显式配置继续有效。最终默认与契约测试统一，不能只为通过测试修改期望。
- LangChain可选路径和内置路径都要验收，缺可选依赖不丢上下文。
- 索引版本仅用于可证明的索引状态；既有向量空间校验保留，未知历史向量不自动标为语义可信。此次不触发业务库批量重嵌入。

验收：正文覆盖完整；overlap=0有效；无死循环和非预期重复；标题正确；引用稳定；保护失败关闭出口；当前vector_space与资料权限回归通过。正式长文、表格及跨段问题的召回效果评测延后。

### R8：汇总验收与交付

本轮采用隔离数据库、本地测试适配器和显式测试配置，不连接业务数据库、真实模型或Docker。

| 验收组 | 主要检查 | 通过所证明的能力 |
| --- | --- | --- |
| 启动与迁移 | Django check、迁移图/模型状态、隔离空PostgreSQL迁移 | 模块能够共同加载 |
| 正式路由与角色 | 根URL、菜单、深链、学生/教师/admin/未登录、对象越权 | 接入和权限正确 |
| 教学与记忆 | 事件幂等/冲突、上下文、台账、召回、遗忘、撤权 | 必要内部调用恢复 |
| 评分与学情 | 隔离记录读写/回读、换账号、0/1/2评分、缺数据/错误 | 无假个人成绩和历史 |
| 可信报告 | 模块七到resolver的集成、篡改/跨候选/范围负向测试 | 报告来源和审批绑定有效 |
| RAG与安全 | 切块双路径、保护出口、向量空间、新增正文副本/缓存/回放、既有认证/私有媒体边界 | 恢复改进没有破坏当前安全装配 |
| 前端构建 | 现有build及改动相关行为测试 | 页面可构建，关键状态正确 |

优先复用teaching_agent、agent_memory、knowledge权限、evaluation_center、feedback phase3及rag_ingestion现有测试；只补缺少的跨模块与负向覆盖。前端针对navigation、assessment、insights、knowledge、DataLab和成长页运行相关测试。源码/样式契约失败与行为失败分别记录，不能把总失败数当成独立业务故障数。

验证正式接入时使用正式应用集合和根urls；evaluation_center.test_urls中的测试适配器验收单独记录，不能代替根路由验收。SQLite可用于适用的纯状态测试，迁移图、pgvector及数据库特定行为用隔离PostgreSQL验证。

交付记录包括：基线与候选SHA、变更文件、命令、实际通过/失败/跳过数、各模块接入状态、待联调项及回退边界。用户提供的858项/602通过/256失败作为历史观测引用，本次设计没有重新执行，不写成新的测试结果。

## 4. 变更与回退安排

实施可使用候选分支`codex/restore-priority-modules`；本设计阶段未创建分支。提交按R0/R1、R2、R3/R4、R5、R6、R7拆分；共享文件的编辑顺序由主实施者统一，避免并行覆盖。

应用恢复保留ctf_backend.SecurityConfig、安全启动绑定、Session/CSRF、私有媒体阻断、内容保护失败拒绝及正式模式禁用旧Token的语义。记忆及上下文恢复须经过现有授权与保护边界。

回退以功能提交为单位，阶段三发布开关继续关闭。已有数据库迁移不通过删除迁移、伪造迁移记录或自动逆向回退处理；新增迁移的部署方案与备份在业务库升级阶段单独确定。评分和历史报告原记录保留，不通过清库使验收通过。

## 5. 本轮完成后的用户可见结果

学生和教师能找到恢复的知识、案例、评估及教学入口；教师看到授权课程范围内的学生和可持久化评分；个人学情缺数据时如实展示；教学请求能够走通任务上下文、事件和记忆接线；反馈候选引用必须对应可验证的数据库报告。实训完整生命周期、正式语料/模型效果及真实业务闭环继续标记待联调。
