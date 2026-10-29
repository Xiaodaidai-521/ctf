# M3-01 正文入口盘点（dc997fe 静态核查）

本表描述开工状态，修复和运行结论见 PROGRESS.md / DELIVERY.md。未查询生产数据库，不声称旧包实际含某条答案。

|入口 / 调用者 → 输出|代码落点|开工权限与缺口|处置|
|---|---|---|---|
|conversations list/detail/chat → 消息/模型history|ai_assistant/views.py AIConversationViewSet|本人认证，但历史 content/metadata 无实时材料授权|不明历史正文隔离，审计ID保留|
|multi-agent chat/stream/tutoring → 回答/knowledge_items/SSE|ai_assistant/views.py；tutor_request_orchestrator.py|模块二已有 task-bound 拒绝，未绑定请求仍能走旧材料链|保留拒绝，新入口需明确 Scope|
|legal_reviewer → challenge vectors → 模型|ai_assistant/service.py build_legal_review_context/run_legal_reviewer|无 user；可读全部 challenge 索引|关闭此未授权旧检索|
|关键词/包/语义融合 → context_text|service.py search_simple_knowledge/build_knowledge_context/_semantic_knowledge_items|包直读，语义缺 user，旧正文仍在 context|统一主体与任务；未知来源不给正文|
|ChallengeKnowledgePack/CategoryKnowledgePack → 上述链|service.py _ensure_* / _get_pack_based_knowledge|现有包直接复用，版本/分类未核验|不把旧包标为安全|
|knowledge/response cache → 上述链|service.py _build_knowledge_cache_key/_build_response_cache_key；cache_services.py|跨授权范围正文缓存，命中不复核|弃用无来源旧缓存；新缓存仅候选ID|
|ResourceAgent / CachedResourceAgent → 摘要/entry|agents/specialists/{resource_agent,cached_resource_agent}.py|部分检查approved，但仍用旧摘要/reserved|登记材料只从受限证据API交付|
|SafeKnowledgeRetrievalService → 语义结果|legal_kb/services/knowledge_retrieval_service.py|默认四类源；extra_filters覆盖白名单|服务器交集；任务ACL|
|LegalRetrievalService → RRF / retrieval log|legal_kb/services/retrieval_service.py|只对document实时visibility；日志存正文|全源授权前过滤；日志只留ID/hash|
|legal-kb documents/clauses/cases/templates/embeddings/jobs/retrieve|legal_kb/views.py / permissions.py|教师/管理员读、管理员写；raw仅管理|不放宽；登记材料进入独立课程管理入口|
|rag documents GET/POST → 元数据/共享chunks|rag_ingestion/views.py/services.py/adapters/repository_legalkb.py|is_staff；同hash；token+事务swap已有|保留运行状态、补候选审核；hash不继承ACL|
|runtime learning-runs → tool docs/retrieval/model；runs list/detail → 快照|agent_runtime/{views,gateway,retrieval,serializers,tool_registry}.py|本人，semantic传user；module.content进入tool；历史无材料复核|工具最小化；历史正文不明则隔离|
|articles list/detail/favorites → content；comments/replies|articles/views.py|匿名只读却可status=pending/rejected；收藏/评论绕queryset|固定发布状态与父授权；登记来源移出公共入口|
|resources list/detail/download → 描述/文件|resources/views.py|highlight可放行reserved；download须登录approved|highlight只定位不授权；文件仍受控|
|knowledge-concepts list/detail → description|learning_paths/views.py KnowledgeConceptViewSet|匿名全部可读|登记材料不走普通概念入口|
|任务/教学context → JSON引用|learning_map/views.py；teaching_agent/{context,permissions,core_flow}.py|敏感键剔除但未知标题/URL仍可放行|证据引用投影，不依赖字段名过滤|
|hint request/display/analysis → 静态正文|teaching_agent/tutoring_state.py / views.py|已有模块六request/show与解析通过门禁|新增m3引用实时审核/撤回门禁，不复制提示系统|
|Django admin → 原始表单|各应用admin.py|staff+模型权限|仍为独立管理边界；不注册新秘密模型到通用admin|
|资源静态URL|ctf_backend/urls.py；frontend/nginx.conf|media/resources已404|保留，新增材料快照无公开文件路径|

## 题解混入与分类映射
- platform_indexing_service._build_challenge_text 将 ChallengeSolution.content/hint_map 编入 challenge；knowledge-pack同样使用challenge类型但GFK为包而非题目，不能按裸object_id当同一种源。
- 当前 build_challenge_knowledge_pack_payload 已不读取标准题解，和材料包旧描述有差异；但它仍含题目提示，且既存包不会自动重建。`has_solution_walkthrough=False`不证明旧包安全。
- scripts/vectorize_question_guide_resources.py 与 reserve_and_vectorize_ai_resources.py 会将 md/txt 文件正文编为resource，不能仅按resource名字认为安全。
- 原创 lesson → 基础查证；hint(1–4) → 模块二request/show；student_analysis → 模块二解锁静态页；ChallengeSolution/题解资源默认 teacher_answer；validator/密钥 → grading_secret。未分类来源不自动公开。
- 学生预览始终是学生Scope，不因教师角色提升。DocumentSource.completed只表解析完成。课程范围首期使用既有CatalogVersion+显式CourseGrant，任务绑定使用既有TaskPackage版本。

## 页面
旧读取组件：MultiAgentChat.vue、AIAssistant.vue、ArticleDetail.vue、Resources.vue、ResourceDetailModal.vue、管理KnowledgeBase.vue。资源预览blob与下载同一路径；CSS隐藏不构成权限。旧AIAssistant调用的 `/conversations/{id}/messages/` 未找到后端action，不记为已接通API。

## 并发已有保证
rag_ingestion以source_hash去重，锁source领取UUID token；解析在事务外；replace锁source、核验token/status后原子替换；_finish再核验token。候选解析失败保留上一有效块，旧worker不覆盖新状态。本轮数据库并发运行证据另附，不把静态阅读当通过。
