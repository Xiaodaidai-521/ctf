# 模块三首期交付记录

日期：2026-10-29。范围：有来源、有权限边界的安全知识库。

> 当前为收尾记录：分包与针对性回归已完成，最终全量正在运行，下面未预填最终数字。人工签收、PostgreSQL真实并发及其他未运行项目不在已验证结论内。

## 1. 工作区与逐包状态

- 唯一工作区：`/home/hatch/workspace/ctf-module3`；分支 `feat/module3-knowledge-base`；基底及保留的HEAD：`dc997fe`。
- 未commit、push、stash，未操作主检出或其他worktree。此文件是新建的模块三记录，不恢复HEAD中的旧模块二交付声明。
- 权限只收紧：缺可信用户/任务/课程/来源/审阅/有效版本时拒绝；教师管理权不升级为他人的学生尝试读取权。

| 工作包 | 状态与产物 | 实际本地验证 |
| --- | --- | --- |
| M3-01 入口盘点 | 完成；旧检索、详情、下载、历史、包及缓存入口台账 | 106发现 / 97通过 / 9跳过；`m3-01-baseline.log` |
| M3-02 统一权限 | 完成；可信Scope、课程授权、分类与用途、白名单交集、旧入口收口 | 59发现 / 57通过 / 2跳过；`m3-02-current-regression.log` |
| M3-03 来源与审阅 | 代码/本地自动化完成；不可变修订、分块检查、独立审阅、发布/撤回、30条draft候选与教师页；人工签收未做 | 当时46/46；`m3-03-complete.log`。新增待确认许可禁止发布用例已在M3-06复跑通过 |
| M3-04 学生证据 | 代码/API/构建完成；短卡、详情/短投影下载、缺证状态、真实模块七反馈；浏览器人工未做 | 21/21；`m3-04-api-rerun.log`；最终Node 14/14及前端build exit 0 |
| M3-05 缓存与导入 | 本地顺序/故障回归完成；即时重新鉴权、旧包隔离、同hash只收紧、令牌校验与原子替换；PG并发未做 | 85发现 / 76通过 / 9跳过；`m3-05-complete-rerun.log` |
| M3-06 联合回归 | 失败簇对账与针对性修复完成；最终全量待结果 | 联合179/179；追加矩阵20/20；详见第5节 |

这里的“完成”指对应代码和已列出的本地验证，不是生产部署、教师批准候选内容或T3全部人工签收。

## 2. 修改文件清单

相对路径均在本worktree内，完整逐簇代码与测试依据见 [PROGRESS.md](PROGRESS.md)。

### 新增

- `backend/learning_knowledge/`：`models.py`、`policy.py`、`services.py`、`review.py`、`serializers.py`、`views.py`、`urls.py`、`teacher_urls.py`、`apps.py`、初始化文件。
- 迁移：`backend/learning_knowledge/migrations/0001_initial.py`、`0002_materialrevision_author.py`。
- 候选：`backend/learning_knowledge/candidate_materials.py`、`management/commands/import_candidate_materials.py`。
- 测试：`backend/learning_knowledge/tests/{helpers,test_policy,test_legacy,test_review,test_candidates,test_evidence,test_teaching,test_integrity}.py`。当前新增93条后端测试。
- 前端：`frontend/src/learningKnowledge/{TeachingKnowledge.vue,LearningKnowledge.vue,EvidenceCard.vue,api.js,usePrivatePage.js,requestGeneration.js,requestGeneration.test.js,materialForm.js,learningKnowledge.css}`。
- 文档：`docs/module3/{entrypoints.md,candidate-register.md,contracts.md}`；重建本模块的`PROGRESS.md`和`DELIVERY.md`。

### 修改既有入口及测试

- `backend/agent_runtime/{gateway,retrieval,serializers,tool_registry,views,tests}.py`：可信检索、旧历史遮蔽、任务专用入口。
- `backend/agents/context/{student_profile_adapter,teaching_context,test_shared_context}.py`；`backend/agents/specialists/{cached_resource_agent,knowledge_agent,knowledge_diagnosis_agent,resource_agent}.py`：无来源旧缓存/历史停读，资源候选实时回源。
- `backend/ai_assistant/{cache_services,service,tutor_request_orchestrator,views,tests,test_performance}.py`：旧包/回复隔离、可信Scope词项投影、保留已授权正向召回测试。
- `backend/articles/{serializers,views}.py`、`backend/resources/{views,tests}.py`、`backend/learning_paths/views.py`：普通入口剔除已登记受控材料，资源highlight不授权。
- `backend/legal_kb/{serializers,views}.py`、`backend/legal_kb/services/{knowledge_retrieval_service,retrieval_service,visibility}.py`：低层过滤交集、法规父全文侧路关闭、旧检索日志输出遮蔽。
- `backend/rag_ingestion/{services,tests,test_postgres_concurrency}.py`、`adapters/repository_legalkb.py`：同hash权限不放宽、保留所有者、旧/缺token拒绝、错误只存类型。
- `backend/teaching_agent/{api_tutoring,context,core_flow,permissions,tutoring_state,views}.py`、`tests/test_no_ai_flow.py`：提示/解析实时来源门禁、生成提交前复核、静态降级、无提示复测拒绝辅导。
- 公共文件仅加自己应用的行：`backend/ctf_backend/settings.py` +1注册；`backend/ctf_backend/urls.py` +2路由；`frontend/src/router/index.js` +2独立页面路由。未改其他路由/全局guard/布局。
- 未修改`challenges`、`mainline1`既存失败簇，未修改前端依赖清单或锁文件。

## 3. 迁移、配置与候选材料

- 新应用拥有材料、修订、块、任务绑定、CourseGrant、Evidence、ReviewAction及EvidenceIssue；复用既有CatalogVersion/TaskAttempt、HintCard/StudentAnalysis、模块六帮助记录、模块七工单及LegalKnowledgeEmbedding，不建第二向量库或用户/课程体系。
- `0001_initial`创建本应用表；`0002_materialrevision_author`增加可空作者FK。作者缺失不能批准发布，不能把旧null作者视为已完成独立审阅。
- 测试临时库实际执行迁移；`makemigrations --check --dry-run`确认无模型迁移漂移。**未对生产/共享库执行迁移或导入**。
- 后续部署步骤由部署负责人确认后执行，未在本轮代执行：
  ```sh
  /home/hatch/workspace/ctf-venv/bin/python backend/manage.py migrate
  /home/hatch/workspace/ctf-venv/bin/python backend/manage.py import_candidate_materials --actor <已有用户主键> --catalog <已有目录版本>
  ```
- 导入命令要求现有actor、目录、四个精确候选任务版本及知识映射；不创建用户/任务、不自动grant、不代审、不发布。同一slot重复导入不覆盖已有修订/审批。
- 30条原创候选目前是`draft/internal`，仅在合成测试库导入。`LicenseRef-Project-Internal-Pending`被发布门禁拒绝；许可确认后需新修订和独立审阅。素材不是法规原文、正式答案或真实秘密；不得将合成测试发布fixture视为教师已批准。
- 首期检索为静态/纯词项；不安装RAGFlow，不调用embedding/rerank/generate来完成证据搜索，不为候选额外写向量。兼容字段`semantic_count`表示当前证据数，不是实际执行向量搜索的证明。

## 4. 接口与真实接通边界

详细字段、作用域、错误和缓存语义见 [docs/module3/contracts.md](docs/module3/contracts.md)。

- 学生：`POST /api/learning-knowledge/search/`；`GET /api/learning-knowledge/evidence/{uuid}/`及`download/`；`POST /api/learning-knowledge/evidence-issues/`。
- 教师：`GET/POST /api/teaching-knowledge/materials/`；材料`chunks/`、`revisions/`、`submit/approve/publish/withdraw/`；admin独立`grants/`。
- 页面：`/teaching-knowledge`、`/learning-knowledge/:attemptId`。cookie/CSRF客户端、纯文本呈现、失焦/换用户/换任务清除内存并使旧请求失效，无正文localStorage。
- 学生下载仍是最多360字符短投影JSON，不是原文件。未知字段不能增加角色/源/用途/提示级别权限；无权与不存在一致拒绝。
- **本地真实服务**：模块二提示请求/展示、模块六request/show与确定性提交、通过后analysis、模块七create_feedback。HTTP证据来自Django APIClient进程内调用及合成数据库，不是部署环境网络或人工浏览器。
- **未接通**：模块四/五/八跨worktree联调；模块四材料消费、模块八执行授权仅有明确契约。evidence_id、source_ref、引用存在、sufficient状态均不是工具授权或合规证明。
- 模块三任务的未审模型推论不展示：当前保守回退已审静态卡，无卡则不给正文；有效引用ID也不认证推论。无提示复测不交付AI/提示卡。
- 旧历史输出遮蔽，不表示数据库历史原文已清除。保留证据/审阅/帮助曝光事实；已合法显示或主动下载到本机的内容不能远程抹除。“即时撤回”是后续读取、缓存命中与响应提交时重新鉴权。

## 5. 实际命令、结果与基线对账

所有后端命令均使用：

```sh
DATABASE_BACKEND=sqlite OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
/home/hatch/workspace/ctf-venv/bin/python backend/manage.py test <下表标签> --noinput --verbosity 2
```

所有日志位于`artifacts/module3/`。日志目录被gitignore，文件实际保留在本地但不会随普通git提交自动交付；交接日志需另行显式处理，未上传任何外部服务。

| 检查 | 真实结果 | 日志 |
| --- | --- | --- |
| 基底dc997fe交接基线 | 638发现 / 621通过 / 5 FAIL / 1 ERROR / 11跳过；来自任务context.md，未另建worktree重跑基底 | 任务简报§测试基线 |
| 模块三首轮全量 | 728发现 / 695通过 / 20 FAIL / 2 ERROR / 11跳过，379.903s，exit 1 | `full-suite-first.log` |
| `agent_runtime agents.context.test_shared_context ai_assistant learning_knowledge`首次对账复跑 | 156发现 / 155通过 / 1 ERROR，86.815s，exit 1；许可测试误用全字段save覆盖解析状态，已修为仅保存license_id并强化精确拒绝断言 | `m3-06-targeted-first.log` |
| `resources` | 23/23，11.911s，exit 0 | `m3-06-resources.log` |
| `agent_runtime agents.context.test_shared_context ai_assistant learning_knowledge resources` | 179/179，40.015s，exit 0 | `m3-06-targeted-rerun.log` |
| `learning_knowledge.tests.test_evidence learning_knowledge.tests.test_integrity`（再补秘密证据HTTP及真实跨角色/课程缓存矩阵） | 20/20，1.555s，exit 0 | `m3-06-matrix.log` |
| 最终全量 | 正在执行；结果未预填 | `full-suite-final.log` |
| `node --test frontend/src/learningKnowledge/requestGeneration.test.js` | 14通过、0失败，exit 0 | `m3-06-frontend-tests.log` |
| `npm --prefix frontend run build` | exit 0，1m38s；保留大chunk警告 | `m3-06-frontend-build.log` |
| `manage.py check` | 无系统错误，exit 0 | `m3-06-system-check.log` |
| `manage.py makemigrations --check --dry-run` | No changes detected，exit 0 | `m3-06-migration-check.log` |

最终全量实际从本worktree的`backend/`目录执行无标签的`manage.py test --noinput --verbosity 2`，使用同一sqlite/venv/线程环境，没有补`MAINLINE1_TEST_PORT`掩盖基线错误。当前发现数应由日志确定，不能以638+93的算式代替执行结果。

### 失败簇结论

完整22项首轮失败/错误逐簇、代码位置和修订依据在 [PROGRESS.md §M3-06](PROGRESS.md#m3-06-联合安全回归进行中)。

- 既存5 FAIL/1 ERROR：4个`ChallengeProxyAccessTests`（URL含access_token、owner无cookie、non-owner、unsafe无CSRF），1个`mainline1`语义测试的进程模块导入假设，1个缺`MAINLINE1_TEST_PORT`的loader错误。未顺手修复，也未过滤测试。
- 首轮新增15 FAIL/1 ERROR分为：runtime历史1、runtime召回2、共享历史1、画像缓存1、ai_assistant检索/旧包4、resources 6 FAIL/1 ERROR。旧要求无Scope召回、本人历史原文重放、0SQL旧画像缓存、highlight临时授权和伪ID可信均违反新边界，测试改为拒绝负例与可信正向fixture并存，没有删除或重命名原失败测试。
- 同时修复真实实现遗漏：`MultiAgentChatService._build_tutoring_vector_context`原未接受可信Scope，仍走低层检索并依赖匿名拒绝，不能为合法材料提供新受控投影。现显式传user/Scope，经实时证据服务返回词项短摘要及证据URL；无Scope拒绝、合法召回、来源变pending撤回和不调用低层向量均有通过记录。
- resources排序没有实现回归：旧basic/advanced非数值ID及challenge条目被正确拒绝后，测试索引空数组报错；改为真实approved Article，同时保留伪ID/challenge拒绝和不同水平排序断言。reserved仍不可见。

## 6. T3-01至T3-16证据矩阵

**本表“通过”只表示列出的本地自动化断言已有通过日志，不等于全部场景或人工验收通过。** 首期关闭旧融合直通，并不等于已验证真实语义融合。路径简称：

- `P/L/R/C/E/T/I`依次为`backend/learning_knowledge/tests/test_policy.py`、`test_legacy.py`、`test_review.py`、`test_candidates.py`、`test_evidence.py`、`test_teaching.py`、`test_integrity.py`。
- `N`为`backend/teaching_agent/tests/test_no_ai_flow.py`；`F`为`frontend/src/learningKnowledge/requestGeneration.test.js`。
- 表内方法名省略`test_`前缀，数字为方法起始行；T/N的链路结果还由M3-05通过日志支撑。

| 编号 | 对应代码测试与结果 | 不能据此声称的验收 |
| --- | --- | --- |
| T3-01 角色/预览 | 本地通过：P:18 `t3_01_role_matrix_and_student_preview`、P:27秘密维护职责、R:40独立审阅、R:118管理预览不授权学生；E:163秘密证据HTTP角色矩阵 | 未人工操作教师“学生预览”；管理入口与他人尝试读取始终分开 |
| T3-02 秘密及未解锁解析 | 本地通过：P:34搜索；E:32短详情/下载/跨学生、E:163 `t3_02_known_secret_evidence_ids_never_authorize_http_reads`；L:22旧聊天、L:74/82资源详情下载。三类秘密已有证据ID也不能通过学生/教师/admin/匿名HTTP读取标题或正文 | 不是所有聊天流式/导出入口的穷举；没有浏览器人工 |
| T3-03 参数注入 | 本地通过：P:42 `t3_03_whitelist_intersection_cannot_be_overridden`、E:55未知字段与过滤仅收窄；底层Mock必须未被调用 | 不冒称真实向量服务参数矩阵联调 |
| T3-04 污染旧包 | 本地通过：L:33真实库中污染题解/旧包不进items/context；L:49仅合法短lesson；既有ai_assistant融合测试保留授权正文及毒旧包排除 | 首期兼容门面改静态/词项，未运行真实语义+关键词融合、ANN或RAGFlow |
| T3-05 缺源/权限/ACL故障 | 本地通过：P:51/58缺grant/源及DB错误；E:65 API503不回显；T:117来源/期限/账户实时检查；辅导资料兼容测试验证源变pending拒绝 | 数据库故障为注入，不是真实存储失联演练 |
| T3-06 跨角色/课程缓存 | 本地通过：L:58旧缓存停读；E:72候选再鉴权；I:78同学生跨课程；I:96 `t3_06_teacher_warm_cache_and_two_student_courses_are_isolated`实际教师预热、两个学生不同课程同词、真实缓存命中与污染候选交集 | 不等于分布式缓存/多进程压力或竞态测试 |
| T3-07 生成中撤权 | 本地通过：T:56 pending结果提交前撤回不保存、不写回复缓存；T:70 provider失败副作用撤grant后不fallback旧提示；E:72旧证据拒绝；T:40已shown事实保留；F旧请求代次作废 | 手动pending/模拟provider，不是真实并发生成撤权；未串部署环境生成→撤权→会话重开全链 |
| T3-08 同hash/旧worker | 本地通过：I:35/45只收紧、不换owner；I:56旧/缺token拒绝；R:82/91候选旧worker与失败保留旧版；C重复导入、回滚、身份冲突 | SQLite顺序/故障注入不证明PostgreSQL互斥；6项PG导入并发跳过 |
| T3-09 非文档来源 | 本地通过：P:63/69未审/未知/任务停用；L:64 article status与登记秘密；I:89同源冲突取最严；L:82资源秘密；C草案对有课程权限学生也拒绝 | 非所有source×用途×课程的穷举；不能只凭article/resource名称放行 |
| T3-10 材料提示注入 | 本地通过：E:84恶意材料按静态文本处理、内网URL不投影、不调用requests.get/post；F:100表单字面保留快照 | 未做真实模型攻击评测、浏览器XSS演示或模块八工具执行联调 |
| T3-11 缺证状态 | 本地通过：E:95 `t3_11_insufficient_stale_conflict_and_missing_locator`；无命中/过期/冲突/无定位不伪造引用页码 | conflict_group及locator是合成状态，未人工验证补查闭环 |
| T3-12 阅读/提示计量 | 本地通过：P:75普通搜索不给高层hint；E:115阅读不产生帮助；T:40真实模块二/六request→show、使用当前快照、撤回保留shown | 不等于逐层全部解锁组合或学生真实看见页面的确认 |
| T3-13 引用不认证推论 | 本地通过：E:122真实evidence_id仍needs_review/supported=false；T:81模拟推论退已审静态卡，旧response毒化不重放 | 保守拒绝不是语义蕴含判定；真实供应商答案未评测 |
| T3-14 故障/无模型流程 | 本地通过：T:94断连/超时/429/quota模拟静态降级；T:106无提示复测；T:147停模型后提交解锁解析再撤回；N:88真实领取—练习记录—提交—核验—保存—新场景复测API链 | 四类供应商故障均mock，未逐个故障跑全链；练习为readonly_observation，sandbox_execute断言模块四不可用，不是真实靶场 |
| T3-15 隐私日志/输入/响应 | 本地通过：T:132捕获内部model_context及指定事件字段；I:69异常只存类型、旧检索日志输出遮蔽；L:22历史响应；E:32短投影；C命令成功/故障输出不含素材正文 | 未抓实际供应商请求、所有日志处理器、浏览器网络或全库事件；历史数据库原文未清除 |
| T3-16 纠错/换版 | **部分，本地已列断言通过**：E:130真实模块七工单去重/版本引用、E:152跨尝试拒绝；R:101换版保留旧块/ReviewAction、旧证据拒绝、新搜索用修订2；C:355重复导入不覆盖已审版 | 关闭工单直接ORM；反馈/换版未串闭环；换版测试同一尝试，未验证旧尝试与新任务成对绑定；模块六成绩更正仅契约，未联调或声称成绩更正验收通过 |

## 7. 明确未运行与剩余依赖

1. **人工签收未做**：30条内容/来源/许可确认、两位教师逐卡签署、真实管理与学生页面验收。任何候选不因测试通过而自动发布。
2. **PostgreSQL真实并发未做**：6项rag导入并发、1项export_quota行锁测试；2项pgvector ANN也未执行。SQLite锁/顺序结果不能替代。
3. 首轮全量另2项跳过：固定本地Docker镜像的Juice Shop集成1项；可选python-docx路径1项（XML回退另有测试）。最终跳过集合仍需按最终日志确认。
4. 浏览器人工操作、XSS/网络抓包、真实切用户/后台/刷新/离页演示未做；Node仅测试请求代次及表单工具逻辑，构建只证明编译成功。
5. 真实供应商429/503/断连/配额/计费未做；模拟故障不冒充真实服务结果。没有外部模型费用或网络SLA验收结论。
6. 模块四/五/八跨worktree、真实靶场、执行/交付授权未接通；模块六成绩更正完整闭环未运行。生产部署、生产数据导入及共享数据库迁移未执行。
7. 5 FAIL/1 ERROR既存基线不得写成全绿；最终结果待全量完成后据实更新。本地T3覆盖不替代上述条件，尚不能签署全面上线验收。
