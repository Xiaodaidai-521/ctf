# 模块三实施进度

## 约束与现状核查（2026-10-29）
- 材料包按 context → module3-plan → master-plan → nav-index → module2-plan-ref → prompt 顺序全文阅读。
- 工作目录 `/home/hatch/workspace/ctf-module3`，分支 `feat/module3-knowledge-base`，HEAD `dc997fe`。开工时 PROGRESS.md / DELIVERY.md 为已删除状态；本次重建模块三记录，不恢复旧模块交付声明。不 commit / push，不触碰主检出或其他 worktree。
- 迁移归属：新 `learning_knowledge` 应用拥有材料修订、任务映射、授权、证据及审阅记录；复用 learning_map 的任务/目录/尝试，legal_kb 的分块存储及 rag_ingestion 的解析基础，不建第二向量库。公共 settings/urls 仅增加本应用注册/路由行。

## M3-01 入口与数据盘点（完成：静态核查 + 本地基线）
已核查差异：
1. teaching_agent.context 已从 TaskAttempt/TeachingRun 解析主体和提示层级，旧任务绑定聊天有专用入口拒绝机制。不能把无任务旧聊天当作具备课程授权。
2. teaching_agent.permissions.student_material_snapshot 仅剔除敏感字段名，仍信任 JSON 中的标题/URL；缺材料级来源、审核、课程实时校验。将以受控材料引用替换未登记投影。
3. TaskPackage 有 materials/hints/student_solution_ref/validator；目录没有独立课程成员表。新增课程授权只映射既有 CatalogVersion（首期课程范围）和既有用户，不自建用户/任务体系；尝试归属与显式课程准入同时检查。
4. 模块二 HintCard / StudentAnalysis 已存在，提示经模块六 request/show 记录，解析经通过核验后静态交付。新增材料与这些卡片关联，不复制第二份分层正文；撤回同时约束交付入口。
5. 模块七 create_feedback 的原生去重保留每次重复票且不按关闭状态筛选。模块三入口先按同尝试/证据修订/原因查找未关闭工单，再调用真实模块七服务；不更改模块七总体去重语义。
6. 完整旧检索/缓存/下载盘点已完成，见 `docs/module3/entrypoints.md`（描述的是开工状态，不是修复验收结论）。

测试：
- 实际运行 `DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test teaching_agent learning_map legal_kb rag_ingestion --noinput`：106 发现 / 97 通过 / 9 跳过，196.361s，exit 0。日志 `artifacts/module3/m3-01-baseline.log`。
- 完整读取入口图、题解混入点和分类映射见 `docs/module3/entrypoints.md`。额外确认：无任务 legal_reviewer 仍可扫含题解的 challenge 索引；文章status及资源highlight存在旧放行路径；将做最小收口。rag token+事务块替换已有，不重写成较弱实现。

## M3-02 权限统一（完成：当前代码本地相关回归通过）
新增材料权限关系、显式课程成员及用途Scope；服务端白名单交集；旧材料读取缺来源时保守拒绝。首期课程准入采用既有目录版本映射，不改变模块一发布/领取逻辑。

续跑实物对账（2026-10-29）：
- `learning_knowledge` 模型、0001迁移、policy、services、review、序列化/API路由和30条原创候选卡片已落盘；其中审阅/API/素材属于后续包的未验收实现，不能标为包完成。
- 旧入口实现已修改 ai_assistant、agent_runtime、agents、articles、resources、learning_paths；历史正文无来源时遮蔽、旧包/回复缓存停用、highlight不再授权。这些改动尚待专门测试，上一进程中断没有测试完成记录。
- 权限单测实际运行：9发现/9通过，`artifacts/module3/m3-02-policy.log`。
- 首次相关回归：52发现/49通过/2跳过/1失败，`artifacts/module3/m3-02-regression.log`。失败是模块二无AI用例仍期望未登记的任意文件引用；已将fixture改成显式课程授权与发布材料引用，保留原核心链路断言。旧rerun日志只有33个点，complete日志有未完成失败标记，均不算完整验证。
- 本次在当前代码上完整执行 `DATABASE_BACKEND=sqlite OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test learning_knowledge teaching_agent legal_kb --noinput --verbosity 2`：**59发现/57通过/2跳过/0失败，33.954s，EXIT_CODE=0**。日志 `artifacts/module3/m3-02-current-regression.log`；包含新增7条旧历史、知识包、详情/下载与缓存负例，修订fixture通过，两个跳过是PostgreSQL ANN测试。
- 模块二m3提示/解析已接require_card并用权威快照投影；api_tutoring已增加ACL/grant哈希与fallback门禁，专门撤回/生成中变更测试留在M3-05。教师/学生页面、候选素材导入命令、并发与T3全集尚未完成。
- 公共settings仅+1注册行，urls仅+2本应用路由；HEAD仍dc997fe。DELIVERY.md仍未生成。
- 材料包全量基线 638 发现 / 11 跳过 / 5 FAIL / 1 ERROR 为交接数据，尚未在本轮全量重跑，不冒称本轮验证。

## M3-03 审阅与版本（完成：代码及本地自动化；人工签收未做）
- 增加修订作者字段及0002迁移，防止非原owner的新修订作者自审；发布复核审阅者当前权限，校验每块hash；新版本发布使旧版本superseded，保留原块和证据审计关系但不重放旧正文。
- `.../python backend/manage.py test learning_knowledge.tests.test_review --noinput --verbosity 2`（sqlite）：9发现/9通过，0.416s，EXIT_CODE=0，`artifacts/module3/m3-03-review.log`。覆盖独立审阅、职责撤回、幂等冲突、旧版本、候选token与失败回滚、来源缺失、管理预览和替换后旧证据拒绝。
- 候选导入命令及30条原创台账完成：显式actor/catalog、四任务精确版本、现有知识映射、整批draft/internal、无自动grant/代签/发布；许可与教师内容审核均待确认。仅在测试临时库导入。
- 当前代码完整执行 `.../python backend/manage.py test learning_knowledge.tests.test_review learning_knowledge.tests.test_candidates --noinput --verbosity 2`（sqlite）：**46发现/46通过，7.145s，EXIT_CODE=0**，`artifacts/module3/m3-03-complete.log`。包含36条候选导入测试。SQLite顺序token测试不等于PostgreSQL并发验收。
- 教师审阅页 `/teaching-knowledge` 完成，严格JSON登记/修订、分块检查、双人动作与理由、版本冲突。页面仅纯文本展示，不凭前端角色授权。
- 前端最初build因缺vite未完成；本worktree执行 `npm --prefix frontend ci --ignore-scripts` 后重新build：**exit 0，42.64s**，保留既有大chunk警告。`node --test frontend/src/learningKnowledge/requestGeneration.test.js` **14/14通过**。日志frontend-install/build/tests.log；未做浏览器人工演示。

## M3-04 学生证据入口（完成：代码、API及前端构建；浏览器人工未测）
- `/learning-knowledge/:attemptId` 提供基础阅读、词项搜索、来源/许可/适用范围/定位、重新鉴权详情及短投影下载、缺证反馈。失焦/切用户/任务清空内容，取消旧请求，不持久化正文、不渲染材料HTML。
- 修复严格序列化器的异常格式（原unknown-fields路径导致500），保留拒绝语义；词项结果保持排名，缓存候选仍与当前授权及知识点相交；反馈不允许挪用同用户另一尝试证据。
- 首跑 `m3-04-api.log`：21测试中参数注入用例6个子例ERROR；修复后同命令 `test learning_knowledge.tests.test_review learning_knowledge.tests.test_evidence --noinput --verbosity 2`（sqlite）：**21发现/21通过，1.112s，EXIT_CODE=0**，`artifacts/module3/m3-04-api-rerun.log`。涵盖短投影/下载/跨学生、注入、DB故障、缺证/过期/冲突/无定位、引用不蕴含结论及真实模块七去重/关闭后新票。
- 基础阅读不记帮助；hint/analysis仍只走模块二和六受控入口。静态/纯词项检索不调用外部模型。

## M3-05 缓存与导入并发（完成：本地顺序/故障回归；PostgreSQL并发未测）
- 模块二追加实时来源/过期/账户状态检查、生成结果提交前鉴权、fallback重新鉴权；模块三任务不接受未经审阅的模型推论，使用已审静态卡片，无提示复测拒绝AI和卡片辅导。旧响应缓存不作为模块三授权，重复请求重新构造静态投影。
- 原始模块二六联调首跑25项/24通过/1 ERROR（新隐私测试误用事件字段payload，实际为metadata）；已修测试字段。日志 `artifacts/module3/m3-05-teaching.log`。
- 同hash导入（包括completed快速返回）只收紧visibility，重导入不更换owner；禁止metadata覆盖可信visibility；旧worker或省略token不能替换当前索引。保留原锁/原子替换，解析错误只存类型、不存正文，普通检索历史日志遮蔽全部内容；普通admin资源/法规管理入口也不能读已登记秘密。
- 联合首跑85项/75通过/9跳过/1FAIL：旧rag测试依赖异常正文。改成验证RuntimeError类型且正文不存储，保留旧worker状态/完整索引断言；对应PostgreSQL测试同样更新但未运行其并发路径。
- 完整重跑 `.../python backend/manage.py test learning_knowledge.tests.test_teaching learning_knowledge.tests.test_integrity teaching_agent rag_ingestion legal_kb --noinput --verbosity 2`（sqlite）：**85发现/76通过/9跳过，36.857s，EXIT_CODE=0**，`artifacts/module3/m3-05-complete-rerun.log`。9跳过为6项真实PG并发、2项ANN和可选python-docx路径。
- 真实本地模块二/六HTTP接点覆盖request/show、通过后analysis、撤回后拒绝、模型全停用仍可确定性提交；429/断连/超时/quota为mock供应商故障，不宣称真实供应商联调。

## M3-06 联合安全回归（进行中）

### 首轮全量与基线对账
- 已读取 `artifacts/module3/full-suite-first.log` 的完整失败清单与堆栈：**728发现 / 695通过 / 20 FAIL / 2 ERROR / 11跳过，379.903s，EXIT_CODE=1**。728 = 基线638 + 当时新增90条模块三测试，不是全量通过。
- `context.md` §测试基线给出的 dc997fe 结果为 **638发现 / 621通过 / 5 FAIL / 1 ERROR / 11跳过**；本轮没有切换或修改其他worktree来重跑基底。首轮同名、同症状的既存集合如下，未改这些实现或测试，也未补环境变量隐藏loader错误：
  - `challenges.tests.ChallengeProxyAccessTests.test_access_url_does_not_include_reusable_token`：URL仍包含access_token。
  - `...test_proxy_accepts_authenticated_owner_without_cookie`：401 != 200。
  - `...test_proxy_rejects_authenticated_non_owner`：401 != 403。
  - `...test_proxy_rejects_unsafe_session_request_without_csrf`：401 != 403。
  - `mainline1.tests.test_semantic.SemanticTests.test_real_transport_constructor_pins_options_without_provider_registry`：进程中已导入ai_providers。
  - `unittest.loader._FailedTest.mainline1.test_settings`：缺MAINLINE1_TEST_PORT，ImportError包装KeyError。

新增15 FAIL / 1 ERROR逐簇处理（下表为代码原因与修改依据，是否通过以之后实跑结果为准）：

| 首轮新增簇 | 数量 | 实现依据与旧预期失效原因 | 测试修订及保留的功能 |
| --- | ---: | --- | --- |
| runtime历史列表 | 1 FAIL | `backend/agent_runtime/serializers.py:23` 历史结果缺材料证明，正文/中间产物遮蔽；“本人旧记录”不等于有当前材料权限 | `AgentRuntimeApiTests.test_run_list_api_only_returns_authenticated_user_runs` 保留200/本人一条/跨用户隔离，新增redacted及双方正文均不回放 |
| runtime检索与配额 | 2 FAIL | `backend/agent_runtime/retrieval.py:73` 经可信Scope进入 `_semantic_knowledge_items` 受控证据投影；原无Scope和绕过授权的OneSemantic mock不再成立 | `LearningRetrievalSemanticTests` 用真实concept、TaskAttempt、CourseGrant和发布修订；保留正向正文/标题/引用编号、12条上限和大量工具结果下的证据保留，不一概改空 |
| 共享历史上下文 | 1 FAIL | `backend/agents/context/teaching_context.py:71,278` 无来源旧消息不能仅截断后送模型 | `SharedTeachingContextTests.test_bounds_history_resources_weak_points_rag_and_sensitive_fields` 验证空history/summary，保留弱点/资源/长度/敏感字段约束 |
| 画像缓存 | 1 FAIL | `backend/ai_assistant/cache_services.py:24` 停用无来源旧缓存读取；实时DB查询1次替代旧0次命中契约 | `ProfileCacheTests.test_hit_miss_invalidation_and_student_isolation` 注入旧毒缓存，验证不回放、实时1次查询、跨用户key隔离和修改后新值 |
| ai_assistant检索/旧知识包 | 4 FAIL | `backend/ai_assistant/service.py:1472,1483,1556` 旧pack停读、可信Scope与用户必须匹配。不能mock掉新授权边界后要求保留旧解题context | `KnowledgeContextSemanticFusionTests` 补真实授权fixture；毒化旧pack helper而不mock新搜索，断言旧pack不读取/不进items或context，授权概念标题和解释正文仍进入；`LegalReviewerAgentTests.test_tutoring_vector_context_returns_approved_learning_article` 验证受控证据URL、无Scope拒绝、来源变pending立即拒绝、禁止低层向量调用 |
| resources放行及排序 | 6 FAIL + 1 ERROR | `backend/resources/views.py:60,90,153,249` highlight仅排序、不授权reserved；`backend/agents/specialists/resource_agent.py:209,274,393,464` 实时回源，拒绝伪ID/challenge和reserved。旧排序fixture使用basic/advanced伪ID，空结果后索引报错 | `backend/resources/tests.py:139,212,258,282,311,332,534` 原方法名保留以便对账；reserved负例覆盖关键词/向量候选/上下文/缓存，以及单复数highlight；真实approved Article排序、普通资源list/detail/download和AI类型/entry仍有正向断言。无需放宽或修改资源实现 |

**实现遗漏与预期变化分开记录**：上述15 FAIL/1 ERROR的旧前提（无Scope召回、旧正文重放、highlight授权、伪ID可信）均不再允许；不能据此恢复放行。其中辅导资料兼容方法还存在真实实现缺口：`MultiAgentChatService._build_tutoring_vector_context` 未接受可信Scope，仍直接调用低层检索并依赖匿名过滤返回空，无法提供合法材料的受控正向召回。已增加服务端user/Scope参数，改为当前词项证据投影，返回 `mode=lexical`、短摘要和证据URL；正向召回/缺Scope拒绝/来源撤回/禁止低层向量调用均已回归。其余簇未发现需恢复或修改实现的功能回归。旧名称/`semantic_count`仅兼容字段，不宣称首期实际调用语义模型。

许可门禁补测：候选 `LicenseRef-Project-Internal-Pending` 明确禁止发布；新增 `test_pending_candidate_license_cannot_be_published`。候选导入幂等测试中的发布fixture改用合成已确认测试许可，不等于批准真实候选许可。

### 针对性复跑及最终检查
- `test agent_runtime agents.context.test_shared_context ai_assistant learning_knowledge --noinput --verbosity 2`：**156发现 / 155通过 / 1 ERROR，86.815s，EXIT_CODE=1**，`m3-06-targeted-first.log`。原失败簇已通过，唯一新增ERROR来自许可测试：旧内存revision全字段save把parse_candidate已写入的completed覆盖回pending；改为 `save(update_fields=['license_id'])`，并明确断言许可拒绝消息、保留approved状态、不产生发布审计记录，未绕过解析门禁。
- resources单独复跑：**23发现 / 23通过，11.911s，EXIT_CODE=0**，`m3-06-resources.log`。
- 联合完整复跑 `test agent_runtime agents.context.test_shared_context ai_assistant learning_knowledge resources --noinput --verbosity 2`：**179发现 / 179通过，40.015s，EXIT_CODE=0**，`m3-06-targeted-rerun.log`。包含许可门禁修复，0跳过。
- 根据T3证据核对又补2条测试：三类秘密已有证据ID的学生/教师/管理员/匿名详情下载矩阵；教师实际预热与两个学生课程同词查询、真实缓存命中及混入跨课程候选ID。`test learning_knowledge.tests.test_evidence learning_knowledge.tests.test_integrity --noinput --verbosity 2`：**20发现 / 20通过，1.555s，EXIT_CODE=0**，`m3-06-matrix.log`。当前模块三共93条测试；新增测试不以mock掉授权服务代替安全断言。
- 最终Node请求代次测试 **14/14通过**；前端最终构建 **exit 0，1m38s**，保留大chunk警告。日志 `m3-06-frontend-tests.log`、`m3-06-frontend-build.log`；不是浏览器人工验收。
- 最终 `manage.py check`、`makemigrations --check --dry-run` 均exit 0，No changes detected；日志 `m3-06-system-check.log`、`m3-06-migration-check.log`。测试库实际执行新迁移；未对生产库迁移。
- 最终全量正在运行，日志 `artifacts/module3/full-suite-final.log`，结果未预填。人工签收、PostgreSQL并发未做。

## 后续顺序
完成M3-06针对性回归 → 全量结果集合对账 → T3证据映射与DELIVERY。

## 开放边界
仅交付教师待审的真实原创教学卡片与完整来源/许可登记；不代签教师双人复核。不导入生产数据。不部署 RAGFlow，不调用外部模型/抓取器证明权限。模块四/五/八跨 worktree 未接通；只使用本 worktree 的真实模块二/六/七接口与明确标注的契约测试。
