# Agent RAG 改造审查说明（Change Review）

> 用途：供另一位（无本次对话上下文的）审查者/模型独立审查本次改造。
> 配套文件：
> - 本说明 `docs/agent-rag-change-review.md`
> - 逐行代码变更 `agent-rag-changes.patch`（37 个文件，约 2.5k 行；由改造前纯净克隆 `diff -ruN` 生成，已排除 `media/`、`__pycache__` 等运行期产物）
> - 需求/现状分析与设计方案 `docs/agent-rag-analysis-and-plan.md`

---

## 0. 给审查者的话（怎么看这份改动）

- 项目：CTF 教学平台，Django 6 后端在 `backend/`。本次只动后端。
- 一句话目标：平台原本有两套互不连通的检索——`legal_kb` 的**语义向量 RAG**（质量较好）和面向学员智能体用的**纯关键词匹配**。本次把智能体接到统一的语义 RAG 上，补齐漏索引的数据，升级检索融合，并新增一条文档入库管线。
- **git 噪声提醒**：仓库被复制进工作目录后所有文件权限位从 644 变 755，`git status` 会把几乎所有文件标成 `M`（diff 里仅 `old mode/new mode`，无内容改动）。**真正的内容改动以 `agent-rag-changes.patch` 为准。**
- 设计红线：统一复用 `legal_kb` 这一套向量库与 Embedding 入口，**不新建并行体系**；所有新能力都开关化；关键词与本地向量回退全程保留。

## 1. 改造范围（5 块）

| 编号 | 名称 | 性质 |
|------|------|------|
| 改造2 | 索引 KnowledgeConcept（知识概念向量化） | 补数据 |
| 改造3.2 | RRF 混合检索（替代 `max(向量,词法)`） | 升级检索 |
| 改造1 | 打通 KnowledgeAgent 语义检索 | 补能力（收益最大） |
| 改造4 | agent_runtime 叠加语义检索 | 补能力 |
| 工作流⑤ | 文档输入处理管线（新 app `rag_ingestion`） | 新功能 |

> 说明：改造3.1（HNSW 索引）核查后发现仓库 `legal_kb/migrations/0004_embedding_vector_hnsw.py` **已存在**，故本次未重复实现（设计文档首版曾误判为缺失，已更正）。

## 2. 设计原则（审查时可据此判断是否达标）

1. **单一向量库 / 单一 Embedding 入口**：一律写入 `legal_kb.LegalKnowledgeEmbedding`，用 `legal_kb.services.embedding_service.EmbeddingService`。
2. **依赖倒置 + 懒加载**：`rag_ingestion` 的管线核心只依赖本地 `interfaces.py` 的 Protocol；所有第三方解析库（markitdown/pdfplumber/python-docx/langchain 切块）只在 `adapters/` 内**懒加载**，缺库只降级该格式，不拖垮整体。
3. **只加不改签名**：既有检索函数签名未变；智能体改为调用新服务；回归面最小。
4. **全程可回退**：远程 Embedding 不可用→本地向量；语义检索失败/关闭→关键词；langchain 切块不可用→内置切块。
5. **开关化**：所有新路径都有 settings 开关（见第 5 节）。

## 3. 变更清单

**新增文件**

- `backend/legal_kb/services/knowledge_retrieval_service.py` — 泄题安全的语义召回门面（改造1/4 共用）
- `backend/legal_kb/migrations/0005_alter_legalknowledgeembedding_source_type.py` — 新增 `document` source_type
- `backend/rag_ingestion/`（新 app，自包含）：`interfaces.py / pipeline.py / registry.py / cleaning.py / chunking.py / models.py / services.py / serializers.py / views.py / urls.py / admin.py / apps.py / tests.py / adapters/* / management/commands/ingest_documents.py / migrations/0001_initial.py`
- `docs/agent-rag-analysis-and-plan.md`、`docs/agent-rag-change-review.md`

**修改文件**

- `backend/legal_kb/services/platform_indexing_service.py` — 新增 `index_knowledge_concepts()` 并入 `index_all()`
- `backend/legal_kb/services/retrieval_service.py` — RRF 混合检索（重写 `retrieve` + 新增 `_retrieve_with_pgvector/_retrieve_portable/_fuse/_rank_map/_lexical_candidate_pool/_dedupe_by_id`）
- `backend/legal_kb/models.py` — `LegalKnowledgeEmbedding.SOURCE_TYPE_CHOICES` 增加 `document`
- `backend/ai_assistant/service.py` — `build_knowledge_context` 语义+关键词融合，新增 `_semantic_knowledge_items/_merge_knowledge_items`；`_format_knowledge_context_text` 增加概念/法规标签；补 `from django.conf import settings`
- `backend/agent_runtime/retrieval.py` — `LearningRetrievalService` 叠加 `_semantic_documents`
- `backend/ctf_backend/settings.py` — 新增配置项（第 5 节）
- `backend/ctf_backend/urls.py` — 挂载 `/api/rag-ingestion/`
- `backend/requirements.txt` — 新增 `langchain-text-splitters`（MIT）、`pdfplumber`（MIT）、`markitdown`（MIT）
- 各 app 的 `tests.py` — 新增针对性单测

<!-- REVIEW_PLACEHOLDER -->

## 4. 分块说明（含审查关注点）

### 改造2：索引 KnowledgeConcept
- 改法：`platform_indexing_service.index_knowledge_concepts()` 遍历 `learning_paths.KnowledgeConcept`，拼接「名称+类型+难度+描述+MITRE/CWE」为检索文本，复用既有 `_index_queryset`（已处理分块、本地向量、pgvector 写入、审计、按 source_type 删旧幂等），`source_type='knowledge_concept'`，并入 `index_all()`。
- 审查关注点：`knowledge_concept` 本就在 `SOURCE_TYPE_CHOICES` 中（无需迁移）；`metadata` 带 `concept_type/difficulty/importance/cwe_id/slug/url`，确认不含敏感内容；`index_all()` 现返回 5 个结果（原 4 个），相关断言已更新。

### 改造3.2：RRF 混合检索
- 改法：`retrieval_service.retrieve` 不再用 `score=max(向量,词法)` 排序，改为 **Reciprocal Rank Fusion**：对向量、词法各自排名，`fused = Σ 1/(k+rank)`（仅对该模态分数>0 的项计入；`k=LEGAL_KB_RRF_K`，默认 60）。
  - PostgreSQL：ANN 取候选池（`max(top_k*4,40)`），再并入一小批词法候选（`_lexical_candidate_pool`，对长 token 做 `icontains`），融合后排序。
  - SQLite/离线：遍历前 1000 行，向量余弦+词法双算后融合。
  - 返回项**保留 `score`（相似度，用于阈值过滤，语义不变）**并新增 `rrf_score`（融合排序值）。
- 审查关注点：
  1. 阈值 `LEGAL_KB_SCORE_THRESHOLD` 仍只在 portable 路径按 `score` 过滤（与改造前一致），pgvector 路径不过滤——确认符合预期。
  2. pgvector 路径里，词法候选若不在 ANN 池、且其 JSON `embedding` 维度与 1024 查询向量不一致，`cosine_similarity` 返回 0（维度不等保护），只贡献词法排名——确认此行为可接受。
  3. 新增 `rrf_score` 字段是否影响下游（已验证 `rag_answer_service`/序列化器/API 不受影响）。

### 改造1：打通 KnowledgeAgent 语义检索
- 新增 `SafeKnowledgeRetrievalService`（`legal_kb/services/knowledge_retrieval_service.py`）：对 `LegalRetrievalService` 的薄封装，**默认安全源 = `knowledge_concept/article/resource/legal_clause`，刻意不含 `challenge`**（challenge 文本可能含题解，防泄题），输出规范化 item（含 `title/summary/text/score/url/metadata`）。
- `ai_assistant.service.build_knowledge_context`：先取原关键词结果，再取语义结果，`_merge_knowledge_items` **语义优先**去重合并、按 `limit` 截断；`KNOWLEDGE_RAG_SEMANTIC_ENABLED=false` 可关闭回到纯关键词。失败只降级（不抛），保证 KnowledgeAgent 的既有 fallback 契约不变。
- 审查关注点：
  1. 泄题隔离是否严谨——确认 `challenge` 不在默认安全源；上传文档 `document` 也不在（见工作流⑤）。
  2. 原来「无 challenge 上下文时关键词路径返回空」——现在由语义补足，确认这是期望的增强。
  3. `settings` 之前未在 `service.py` 导入，本次新增 `from django.conf import settings`，确认无副作用。

### 改造4：agent_runtime 叠加语义检索
- 改法：`agent_runtime/retrieval.py` 的 `LearningRetrievalService.retrieve` 在原「工具读结构化数据」之后调用 `_semantic_documents`（复用 `SafeKnowledgeRetrievalService`），把语义结果转为与工具文档同构的 doc（统一在最后重编 `S1/S2...` 引用号），再进 `knowledge_context`。`AGENT_RUNTIME_SEMANTIC_RETRIEVAL`/`AGENT_RUNTIME_SEMANTIC_TOP_K` 控制。
- 审查关注点：引用号 `source_ref` 规范保持不变，`verifier` 的引用校验无需改（已验证）；工具文档仍排在语义文档之前（`S1` 稳定）。

### 工作流⑤：文档输入处理管线（新 app `rag_ingestion`）
- 分层：`interfaces`(Protocol) ← `pipeline`(编排) ← `registry`(按扩展名/MIME 选 parser) + `cleaning` + `chunking` + `adapters/`(parser_plain/docx/pdf/markitdown + embedder_legalkb + repository_legalkb)。
- 数据流：登记去重(sha256) → 加载 → 解析为文本 → 清洗 → 结构感知切块（装了 `langchain-text-splitters` 用 Markdown 标题切块，否则回退 `legal_kb.ChunkingService`）→ 批量向量化 → 写统一表 `source_type='document'` → 审计留痕 → 可检索。
- 模型 `DocumentSource`：记录文件/hash/状态/可见范围；状态机 pending→running→completed/failed；按 hash 幂等。
- 安全：上传 API `POST /api/rag-ingestion/documents/` 为 `IsAdminUser`，限大小(`RAG_INGESTION_MAX_UPLOAD_MB`)、限扩展名白名单；`document` **不在**学员安全源白名单，默认不对学员检索暴露；文件名不可信、按字节处理。
- 审查关注点：
  1. 上传接口鉴权是否足够（当前 staff/admin）；是否需要加病毒扫描/更严格的 MIME 校验。
  2. `repository_legalkb` 写库时 `embedding_model` 恒为 `'local-hash-v1'`（真实模型名入 `metadata.vector_model`）——这是**沿用既有 `platform_indexing_service` 的行为**，非本次引入；若要修建议统一改。
  3. `adapters/parser_pdf.py` 优先 `pdfplumber`(MIT)，仅在已安装时回退 `PyMuPDF`(AGPL)；默认依赖不含 PyMuPDF。确认许可策略 OK。

## 5. 新增配置项（`ctf_backend/settings.py`，均可用环境变量覆盖）

| 配置 | 默认 | 作用 |
|------|------|------|
| `LEGAL_KB_RRF_K` | 60 | RRF 融合常数 |
| `KNOWLEDGE_RAG_SEMANTIC_ENABLED` | true | KnowledgeAgent 语义召回开关 |
| `AGENT_RUNTIME_SEMANTIC_RETRIEVAL` | true | agent_runtime 语义召回开关 |
| `AGENT_RUNTIME_SEMANTIC_TOP_K` | 4 | agent_runtime 语义召回条数 |
| `RAG_INGESTION_CHUNK_SIZE` | 1000 | 文档切块大小 |
| `RAG_INGESTION_CHUNK_OVERLAP` | 120 | 切块重叠 |
| `RAG_INGESTION_USE_LANGCHAIN_SPLITTER` | true | 是否用 langchain 切块（缺库自动回退） |
| `RAG_INGESTION_MAX_UPLOAD_MB` | 20 | 上传大小上限 |
| `RAG_INGESTION_ALLOWED_EXTENSIONS` | md/txt/html/csv/json/log/docx/pdf/pptx/xlsx | 上传扩展名白名单 |

## 6. 数据 / 迁移影响

- `legal_kb/0005_alter_legalknowledgeembedding_source_type.py`：仅给 `source_type` 增加 `document` 选项（CharField choices，无 DDL 风险）。
- `rag_ingestion/0001_initial.py`：新建 `DocumentSource` 表。
- 需重建向量以纳入知识概念：`python manage.py prepare_legal_kb --platform-only`（`index_all` 已含概念）。
- 已验证 `makemigrations --check --dry-run` 无待生成迁移。

## 7. 验证结果

- 环境：VM 自带 Python 3.10，但项目要 Django 6（需 ≥3.12），用 `uv` 装 Python 3.12 建 venv。
- 运行方式（SQLite 开发库）：
  `DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key python manage.py test <app>`
- 结果：
  - 改动涉及的 5 个 app（`legal_kb/ai_assistant/agents/agent_runtime/rag_ingestion`）共 **101 用例全绿**。
  - 全量 **208 用例**：仅 `challenges.tests.ChallengeProxyAccessTests` 的 **4 个失败**；已在**未改动的纯净克隆**复跑确认同样失败，属环境/预存问题（挑战容器代理 token/CSRF），**与本次改造无关**。
  - `manage.py check` 无问题；`makemigrations --check` 无遗漏。

## 8. 建议审查重点（已知点 / 可讨论）

1. **泄题隔离**是否足够：确认 `challenge` 与 `document` 不进学员可见的语义召回；上传可见范围 `visibility` 的后续用法（当前仅存 metadata，检索侧默认按 source_type 白名单隔离）。
2. **RRF 的 `score` 与阈值语义**：是否接受「排序用 RRF、过滤/展示仍用相似度」的折中。
3. **本地回退非语义**：无远程 Embedding Key 时 128 维字符哈希≈词法，检索质量受限（设计文档列为后续项，未在本次范围）。
4. **`embedding_model` 落库恒为 `local-hash-v1`**：既有行为，`check_legal_kb` 统计可能偏差；是否本次一并修。
5. **依赖版本**：`langchain-text-splitters` 固定 `>=0.3.0,<0.4` 以兼容现有 `langchain-core 0.3.x`/`langchain-openai 0.3.16`；审查是否接受。
6. **上传接口**：是否需要超出 `IsAdminUser` 的更细粒度权限、速率限制或内容扫描。

## 9. 关键代码位置（审查入口）

| 作用 | 文件 |
|------|------|
| 安全语义召回门面 | `backend/legal_kb/services/knowledge_retrieval_service.py` |
| RRF 混合检索 | `backend/legal_kb/services/retrieval_service.py` |
| 概念索引 | `backend/legal_kb/services/platform_indexing_service.py` |
| KnowledgeAgent 融合 | `backend/ai_assistant/service.py`（`build_knowledge_context`） |
| agent_runtime 语义 | `backend/agent_runtime/retrieval.py` |
| 文档管线编排 | `backend/rag_ingestion/pipeline.py` + `interfaces.py` + `registry.py` |
| 入库仓储 | `backend/rag_ingestion/adapters/repository_legalkb.py` |
| 上传 API | `backend/rag_ingestion/views.py`（`IsAdminUser`） |

---

## 10. 审查反馈修复记录（第二轮）

针对首轮审查提出的 5 个问题，已全部修复并补回归测试。补丁 `agent-rag-changes.patch` 已包含这些修复。

### [P1] staff 文档被非 staff 教师越权读取 —— 已修
- 根因：可见范围只写进 `metadata`，但原有读取入口（`/api/legal-kb/embeddings/` 用 `.objects.all()`、RAG `retrieve()`）未做可见范围过滤，`IsLegalKbReader` 又放行教师。
- 修法：新增**统一可见范围层** `backend/legal_kb/services/visibility.py`（`allowed_document_visibilities(user)` + `apply_embedding_visibility(qs, user)`，fail-closed）。在**共享查询层**统一调用：
  - `LegalKnowledgeEmbeddingViewSet.get_queryset()`（原始切块 API）
  - `LegalRetrievalService.retrieve()`（RAG 检索，所有调用方共用）
  - 规则：staff/admin 看全部；teacher 看 internal+learner，**排除 staff-only 文档**；其他/匿名/内部调用仅 learner。非 document 行不受影响。
- 回归测试：`legal_kb.tests.DocumentVisibilityTests`（embeddings API + retrieve 两条入口，teacher 看不到、admin 看得到）。

### [P2] 命中知识包时语义召回未进入提示词 —— 已修
- 根因：`build_knowledge_context` 在 `context_text` 非空（命中 pack）时只给旧文本加前缀，语义只进了 `items`，没进最终 `context_text`。
- 修法：新增 `_format_semantic_supplement()`，命中 pack 时在保留原 pack 上下文基础上**追加「补充语义检索证据」块**（按标题对已有上下文去重、最多 5 条、摘要截断控长）。
- 回归测试：`ai_assistant.tests.KnowledgeContextSemanticFusionTests.test_semantic_evidence_appended_when_pack_context_present`（断言 pack 上下文保留 + 语义内容出现在 `context_text`）。

### [P2] runtime 语义结果被 12 条上限截断 —— 已修
- 根因：语义文档被追加在工具文档之后，`_build_context` 只取 `docs[:12]`，工具文档占满 12 条时语义被挤掉；且 `retrieved_docs`（编号/验证证据）与实际进 prompt 的集合不一致。
- 修法：改为**先选择后编号**——新增 `_select_context_docs()`，为语义结果保留配额（`min(语义数, AGENT_RUNTIME_SEMANTIC_TOP_K, limit)`），工具文档填其余额度并回填；选择结果即 `retrieved_docs`，再统一编号 `S1..Sn`，`_build_context` 不再二次截断。编号、验证证据、提示词三者一致。新增 `AGENT_RUNTIME_CONTEXT_LIMIT`（默认 12）。
- 回归测试：`agent_runtime.tests.LearningRetrievalSemanticTests.test_semantic_docs_survive_context_cap_with_many_tool_docs`（17 工具文档 + 1 语义：语义仍在、总数≤12、每条编号都出现在 context）。

### [P2] 文档索引重建非原子 —— 已修
- 根因：`repository.replace()` 先删旧切块再逐条写新切块，无事务；中途失败留下半成品且删掉了旧索引。
- 修法：把「删旧 + 写全部新」包进 `transaction.atomic()`（解析/向量化在调用前完成，事务短）。失败回滚，旧索引保持完整。
- 回归测试：`rag_ingestion.tests.RepositoryAtomicityTests.test_failed_rebuild_rolls_back_and_keeps_old_index`（第 2 条写入注入失败→旧索引仍在、无半成品）。

### [P2] MarkItDown 适配器 Windows 临时文件占用 —— 已修
- 根因：`NamedTemporaryFile` 句柄未关闭就按路径 `convert()`，Windows 上触发 `PermissionError`。
- 修法：改为 `delete=False` 先写入并 `close()`，再按路径转换，`finally` 中 `os.unlink` 清理，跨平台安全。
- 回归测试：`rag_ingestion.tests.MarkItDownParserTests.test_tempfile_closed_before_convert_and_cleaned_up`（注入 fake markitdown，按路径重新打开读取成功 + 临时文件已清理）。

### 本轮验证
- 相关 5 个 app 单测：**107 全绿**（新增 6 个回归用例）。
- `manage.py check`、`makemigrations --check` 均通过（无新模型变更，无遗漏迁移）。
- 关于审查者「因缺 pgvector 未能跑用例」：**更正**——Python 包 `pgvector` 是**始终必需**的（它在 `requirements.txt` 里，且 `legal_kb/models.py` 顶部无条件 `from pgvector.django import VectorField`）。只有 PostgreSQL 服务器端的 `vector` **扩展**才是 Postgres 专属。用 SQLite 跑测试时仍需先 `pip install pgvector`（随 `requirements.txt` 一起装即可）；命令务必带 `DATABASE_BACKEND=sqlite DEBUG=true SECRET_KEY=dev-test-key`，否则默认连 PostgreSQL(host=postgres) 会在初始化阶段退出。pgvector 的 ANN/HNSW 仅在 PostgreSQL 路径启用，已做 vendor 判空与回退。

### 新增配置项（本轮）
- `AGENT_RUNTIME_CONTEXT_LIMIT`（默认 12）：agent_runtime 进入上下文的文档总数上限（语义配额在此之内保留）。

---

## 11. 审查反馈修复记录（第三轮）

第二轮审查确认 3 项（Runtime 配额、索引原子替换、Windows 临时文件）可关闭；提出 1 个 P1、1 个 P2 遗漏。两项均已修复并补回归测试。

### [P1] 权限按「切块快照」判定，收紧/重建失败后仍可能泄露 —— 已修
- 根因：统一可见范围层只读 `切块 metadata.visibility`（入库时的快照）。两种可复现路径会使快照过期：(a) 文档以 internal 入库后在后台改为 staff；(b) 以 `visibility='staff', reingest=True` 重建但解析失败（旧索引按原子修复被正确保留，但旧切块快照仍是 internal）。此时 `DocumentSource.visibility=staff` 而切块快照=internal → 教师仍可读。
- 修法：`apply_embedding_visibility` 改为**以关联的 `DocumentSource` 当前 `visibility` 为准**，不再信任切块快照：document 切块仅当其 `DocumentSource.visibility` 在用户允许级别内才保留；**关联对象缺失或超权则拒绝（fail-closed）**。实现用 `object_id__in=DocumentSource.objects.filter(visibility__in=allowed).values('id')` 子查询，避免物化。
- 回归测试（`legal_kb.tests.DocumentVisibilityTests`）：新增
  - `test_tightening_visibility_after_ingest_blocks_teacher`：internal 入库→教师可读→改为 staff→教师经 retrieve 与 embeddings API 均不可读；
  - `test_stale_internal_snapshot_does_not_grant_access_to_staff_doc`：切块快照=internal 但 DocumentSource=staff，教师不可读、管理员可读。

### [P2] 仅凭标题出现在知识包里就丢弃语义证据 —— 已修
- 根因：`_format_semantic_supplement` 用 `if title and title in existing: continue` 去重。知识包通常会提到当前题目的概念**名称**，于是「提到名称」被误判为「已包含该知识」，把概念的解释正文整条丢弃。
- 修法：去重改为**基于实际正文**（`summary`/`text` 是否已包含在上文），不再用标题判断；标题相同但正文未出现时照常补充。
- 回归测试：`ai_assistant.tests.KnowledgeContextSemanticFusionTests.test_semantic_body_included_even_when_pack_mentions_title`（上文只含概念名「SQL注入」、不含正文；断言概念解释「参数化查询」仍进入 `context_text`）。

### 另修（自审 + 审查附带发现）
- **可移植回退丢失向量臂**：`retrieve` 在 PostgreSQL 上用 1024 维远程查询向量，但 JSON `embedding` 恒为 128 维本地向量；pgvector 不可用而走可移植回退时，`cosine_similarity(1024,128)` 恒为 0，退化成纯词法。修法：`_retrieve_portable` 内改用**本地查询向量**与 128 维 JSON 向量匹配。
- **并发首次上传竞态**：`services.ingest_bytes` 改用 `update_or_create`（命中唯一约束会重试 get），避免两个相同内容的并发上传因 `source_hash` 唯一约束 500。
- **PDF 解析健壮性**：`parser_pdf` 对 `pdfplumber.open` 失败/空结果捕获并回退 PyMuPDF（原先只在 import 失败时回退）。
- **DOCX 表格丢字**：`parser_docx` 当 python-docx 仅读到空正文（如纯表格）时回退 zipfile XML 扫描（覆盖所有 `<w:t>`）。
- **语义/关键词合并配额**：`_merge_knowledge_items` 为语义与关键词各留配额，避免命中知识包时任一方被挤空（配套 `test_merge_reserves_slots_for_both_sources`）。

### 本轮验证（含真实 PostgreSQL + pgvector）
- **SQLite**：5 个相关 app **113 用例全绿（2 个 pgvector 专用用例按 vendor 跳过）**；`manage.py check`、`makemigrations --check` 通过。
- **真实 PostgreSQL 16.2 + pgvector 0.6.2**（用户空间 `pgserver`，无需 root）：同样 5 个 app **113 用例全绿**，其中 2 个 pgvector 专用用例实际执行。这验证了此前未覆盖的集成路径：
  - 迁移 `0002`（`CREATE EXTENSION vector`）、`0004`（`hnsw ... vector_cosine_ops` 索引）在真实 PG 建库成功；
  - `VectorField(1024)` 列、`_retrieve_with_pgvector` 的 `CosineDistance` ANN 分支（`PgvectorAnnRetrievalTests` 断言最近邻命中）；
  - 文档可见范围过滤（`DocumentSource` 子查询 + `object_id__in`）在真实 PG 上同样生效（教师被挡在最近邻 staff 文档之外）。
- 说明：补丁与测试计数已同步（SQLite 113 ran / PG 113 ran）。补丁 `agent-rag-changes.patch` 已重新生成，仅后端代码、38 文件、无 media/自引用。
