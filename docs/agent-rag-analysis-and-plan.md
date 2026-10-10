# Agent RAG 现状分析与改造方案

> 范围：`backend/` 下与「智能体（agent）」相关的检索增强（RAG）链路。
> 目标：先给出现状分析和改造方案，暂不改动代码；待确认后再分步落地。
> 本文覆盖四块：① 打通知识 Agent 的语义检索；② 索引 KnowledgeConcept；③ 提升检索质量；④ 为 agent_runtime 增加语义检索。

---

## 0. 结论先行（TL;DR）

当前项目里其实存在**两套互不连通的检索体系**：

1. 一套**完整的语义向量 RAG**，位于 `legal_kb/`（Embedding + pgvector + 余弦回退 + 答案合成），质量较高；
2. 一套**纯关键词/词法匹配的检索**，被真正的多智能体导师（`agents/specialists/KnowledgeAgent`）和 `agent_runtime` 使用。

核心问题是：**面向学员的智能体没有用上已经建好的语义 RAG**，而是走了关键词匹配；同时向量库漏索引了 `KnowledgeConcept`（知识概念），检索侧也缺少混合检索、重排和 ANN 索引。四块改造彼此解耦，可以分阶段独立上线，风险可控。

---

## 1. 现状架构梳理

### 1.1 三条检索链路

| 链路 | 入口 | 检索方式 | 是否语义向量 | 数据源 |
|------|------|----------|--------------|--------|
| A. 合规审计 RAG | `legal_kb/services/rag_answer_service.py` → `retrieval_service.py` | pgvector ANN / 余弦 + 词法回退 | ✅ 是 | 法规、案例、题目、文章、资源 |
| B. 多智能体导师 | `agents/specialists/knowledge_agent.py` → `ai_assistant.service.build_knowledge_context` → `search_simple_knowledge` | 关键词 `icontains` + 打分 | ❌ 否 | Challenge、知识包（ChallengeKnowledgePack） |
| C. agent_runtime | `agent_runtime/gateway.py` → `retrieval.py`（`LearningRetrievalService`） | 平台工具读数据（档案/知识状态/学习路径） | ❌ 否 | 结构化平台数据，无检索排序 |

> 注意：`ai_assistant.service` 里有一个 `_build_tutoring_vector_context`，它**确实**调用了 `LegalRetrievalService`（过滤 `article`/`resource`），但只服务于导师对话的「资料推荐」子环节，**没有**给 `KnowledgeAgent` 的知识点召回使用。所以链路 A 的能力只被局部复用。

### 1.2 链路 A（legal_kb）内部构成

- `embedding_service.py`：
  - 远程 Provider（`dashscope` / `volcano` / `ark`，OpenAI 兼容 embeddings，1024 维）；
  - 本地回退 `_local_embed_text`：128 维「字符桶计数」哈希向量——**不具备语义能力**，仅用于离线/SQLite/无 Key 时保证可运行；
  - `cosine_similarity` 为纯点积（依赖调用方已归一化）。
- `models.LegalKnowledgeEmbedding`：统一向量表。同时存 `embedding`（JSON，便携回退）与 `embedding_vector`（pgvector 1024 维，生产 ANN 用）。
- `retrieval_service.LegalRetrievalService.retrieve`：
  - PostgreSQL 且查询向量为 1024 维 → 走 `pgvector.django.CosineDistance` 排序；
  - 否则回退：遍历前 1000 行，取 `max(向量余弦, 词法分)`，按 `LEGAL_KB_SCORE_THRESHOLD`（默认 0.35）过滤；
  - 每次写 `LegalRetrievalLog`（含延迟）。
- `rag_answer_service.RagAnswerService`：召回 → 构造 citations → 可选 LLM 合成（`LEGAL_KB_RAG_USE_LLM`）→ 结构化「审计结论/法规依据/多智能体意见/建议/证据缺口」。
- `platform_indexing_service.py`：把 Challenge、ChallengeKnowledgePack、Article、Resource 写入向量表。
- `chunking_service.py`：法规按「第X条」切块，平台内容按定长（1200 字）切块。

### 1.3 链路 B（KnowledgeAgent）内部构成

`KnowledgeAgent.analyze()` → `MultiAgentChatService.build_knowledge_context()` → `search_simple_knowledge()`：

- 先查知识包（`_get_pack_based_knowledge`），否则对 `Challenge` 做 `icontains` 关键词查询 + `_practice_match_score` 打分；
- **完全不触碰向量表**，也不读取 `KnowledgeConcept`；
- 对中文语义近义、跨表（法规/文章/概念）召回能力弱。

---

## 2. 核心问题与差距

### 问题 1：知识 Agent 未接语义检索（最关键）
`KnowledgeAgent` 走关键词匹配，拿不到 `legal_kb` 已建好的 1024 维语义召回，导致：语义近义词召不回、跨源（概念/文章/法规）证据拿不到、召回质量明显低于「合规审计」链路。**这是四块里优先级最高、收益最大的一块。**

### 问题 2：KnowledgeConcept 未被向量化
- `LegalKnowledgeEmbedding.SOURCE_TYPE_CHOICES` 已经声明了 `knowledge_concept`，但 `platform_indexing_service` 只索引 Challenge/包/文章/资源，**从未写入概念**；
- `learning_paths.models.KnowledgeConcept` 自带一个废弃的 `embedding` JSONField（注释里原计划 384 维 VectorField），实际未使用；
- 结果：知识点「定义/前置/易错点」这类最该被检索的内容反而不在向量库里。概念还带 `ConceptRelation`（前置/相似/部分）和 `ConceptResource`，有做「图增强召回」的结构基础。

### 问题 3：检索质量偏弱
- **无 ANN 索引**：`0002_enable_pgvector` 只 `CREATE EXTENSION`，`embedding_vector` 上**没有 HNSW/IVFFlat 索引**，数据量上来后是全表精确扫描；
- **融合方式粗糙**：回退路径用 `max(向量, 词法)`，不是标准的分数融合，向量与词法无法互补排序；
- **无重排、无查询改写**：缺 RRF（倒数排名融合）、缺 cross-encoder/规则重排、缺 query rewrite / 多查询 / HyDE；
- **本地回退无语义**：128 维字符桶哈希在离线环境≈关键词，检索体验割裂；
- **小瑕疵**：`platform_indexing_service` 写库时 `embedding_model` 恒为 `'local-hash-v1'`（真实模型名只落在 `metadata.vector_model`），`check_legal_kb` 的统计/告警可能产生误导。

### 问题 4：agent_runtime 无语义检索
`LearningRetrievalService` 只按工具读结构化数据拼上下文，没有对知识库做任何语义召回，`run_learning_task` 的 `knowledge_context` 缺少真正的「检索」。

---

## 3. 改造方案

设计原则：**不新建第二套向量库**，统一复用 `legal_kb` 这套（Embedding/模型/表/pgvector/日志）；对智能体只做「接入 + 增强」，保证关键词路径作为回退始终可用（符合 `ResourceAgent.PROMPT_POLICY` 里「不得替换现有 RAG」的约束）。

### 改造 1：打通知识 Agent 的语义检索

目标：`KnowledgeAgent` 优先走语义召回，关键词匹配降级为回退，二者结果融合。

改法（建议新增一个薄封装，而非改散各处）：

1. 在 `legal_kb/services/` 新增 `knowledge_rag_service.py`（或在 `ai_assistant.service` 内加方法 `semantic_knowledge_context`），对外暴露一个面向学员安全的召回：
   - 调 `LegalRetrievalService.retrieve(query, top_k, filters={'source_type': [...]})`；
   - **安全过滤**：排除会泄题的内容。沿用 `_build_tutoring_vector_context` 的既有策略——challenge 正文可能含解法，默认只放 `knowledge_concept` / `article` / `resource` / `legal_clause`，challenge 仅用于影响 query、不进 prompt；
   - 输出结构与现有 `build_knowledge_context` 的 `items` 对齐（`title/text/score/source_type/metadata/source_id`），这样 `KnowledgeAgent` 现有解析逻辑几乎不用改。
2. 在 `MultiAgentChatService.build_knowledge_context` 内，把现有 `search_simple_knowledge` 的结果与语义召回结果做融合（见改造 3 的 RRF），语义优先；无 Key/离线时自动回退到关键词路径。
3. `KnowledgeAgent.analyze` 不动或仅微调（它已消费 `items`）。

涉及文件：`ai_assistant/service.py`（`build_knowledge_context`）、新增 `legal_kb/services/knowledge_rag_service.py`、（可选）`agents/specialists/knowledge_agent.py`。

风险 / 规避：
- **泄题风险**——务必保留 challenge 正文的隔离策略，概念/文章/资源才进 prompt；
- **性能**——语义召回带 DB/远程开销，复用现有知识缓存键（`_build_knowledge_cache_key`）即可；
- **回退**——远程 embedding 不可用时 `embed_many` 已自动回退本地向量，再叠加关键词兜底，不会「召回为空就崩」。

验证：对一组中文语义改写 query（如「怎么防 SQL 注入」vs「参数化查询」）对比改造前后召回命中；单测覆盖「无 Key 回退」「泄题过滤」。

### 改造 2：索引 KnowledgeConcept

目标：把知识概念纳入统一向量表，`source_type='knowledge_concept'`。

改法：

1. 在 `platform_indexing_service.py` 新增 `index_knowledge_concepts()`：
   - `queryset = KnowledgeConcept.objects.all()`；
   - `text_getter`：拼接 `name + description +（concept_type 中文）+ mitre_attack_id / cwe_id`；
   - `title_getter`：`name`；
   - `metadata_getter`：带上 `concept_type / difficulty_level / importance / slug`，便于前端跳转与过滤；
   - 复用现有 `_index_queryset`（它已处理 chunk、本地向量、pgvector 写入、审计留痕）。
2. 把 `index_knowledge_concepts()` 挂进 `index_all()`，并在重建命令 / `fetch_official_laws` 等编排处补一行。
3. （可选，增强）利用 `ConceptRelation` 做「图增强」：召回某概念后，带回其 `REQUIRES` 前置概念作为补充证据——放到改造 3 的重排阶段做。
4. `learning_paths.models.KnowledgeConcept.embedding` 这个废弃 JSON 字段：建议文档标注「以 `LegalKnowledgeEmbedding` 为准，择机清理」，本次不动表结构以免迁移风险。

涉及文件：`legal_kb/services/platform_indexing_service.py`、重建/种子命令、（文档）`learning_paths/models.py`。

风险 / 规避：概念文本短，chunk 基本 1 块；注意 `unique_legal_embedding_chunk` 约束（`content_type+object_id+chunk_index+embedding_model`）——重复索引前先按 `source_type` 删旧（`_index_queryset` 已有删除逻辑）。

验证：`python manage.py check_legal_kb` 应能看到 `knowledge_concept` 计数>0；抽查概念 query 能召回概念块。

### 改造 3：提升检索质量

目标：召回更准、排序更稳、规模可扩展。按投入产出排序：

1. **加 ANN 索引（低成本高收益）**：新增迁移，在 PostgreSQL 上为 `embedding_vector` 建 HNSW 索引：
   `CREATE INDEX ... USING hnsw (embedding_vector vector_cosine_ops);`（仅在 `vendor=='postgresql'` 时执行，SQLite 跳过）。消除全表扫描。
2. **混合检索 + RRF 融合**：把「向量召回 Top-N」与「词法/关键词召回 Top-N」各自排名，用倒数排名融合
   `score = Σ 1/(k + rank_i)`（k 取 60），替代现在的 `max(向量, 词法)`。向量召空时词法补位，反之亦然。
3. **轻量重排**：对融合后的候选做规则重排——标题命中、`source_type` 优先级（概念/法规 > 文章 > 资源）、`importance/difficulty` 加权；若后续接 LLM，可选 cross-encoder/LLM 重排（受 `LEGAL_KB_RAG_USE_LLM` 之类开关控制，默认关）。
4. **查询改写（可选，默认关）**：在 `RagAnswerService` 前置一步，用现有 provider 把口语化 query 归一化/扩展为 1~3 条检索式（多查询），再并集召回。开关化，避免给无 LLM 环境增加依赖。
5. **本地回退语义化（可选）**：把 128 维字符桶哈希换成「字符/词 n-gram TF 向量 + 维度调大」或引入轻量本地 embedding；成本较高，列为后续可选项。
6. **修 `embedding_model` 落库值**：写库时如实记录真实模型名（远程时写 provider 模型名，回退时写 `local-hash-v1`），让 `check_legal_kb` 统计准确。

涉及文件：新增 `legal_kb/migrations/000X_hnsw_index.py`、`legal_kb/services/retrieval_service.py`（融合/重排）、`legal_kb/services/platform_indexing_service.py`（模型名）、（可选）`rag_answer_service.py`（查询改写）。

风险 / 规避：
- HNSW 建索引对大表耗时——放单独迁移、低峰执行；SQLite 必须跳过；
- 融合/重排改排序逻辑——保留阈值与 Top-K 配置项，灰度对比 `LegalRetrievalLog` 的延迟与命中变化；
- 查询改写增加一次 LLM 调用——默认关闭，仅在明确开启时生效。

验证：构造中文检索评测集（query→期望命中），对比改造前后 Recall@k / MRR；检查 `LegalRetrievalLog.latency_ms` 分布。

### 改造 4：agent_runtime 增加语义检索

目标：`LearningRetrievalService` 在现有「工具读结构化数据」之外，叠加对知识库的语义召回，丰富 `knowledge_context`。

改法：

1. `agent_runtime/retrieval.py` 的 `retrieve()` 增加一路：调用改造 1 的统一语义召回服务（同样套用泄题安全过滤），把召回的知识块转为与现有 `retrieved_docs` 同构的文档（带 `source_ref` `S1/S2...`，`_build_context` 已按此拼接）；
2. 工具结果 + 语义召回合并后统一编号、统一进 `knowledge_context`，`gateway.py` 的引用校验（`verifier`）无需改；
3. 开关化（`settings` 加 `AGENT_RUNTIME_SEMANTIC_RETRIEVAL`，默认开/关由你定），便于灰度。

涉及文件：`agent_runtime/retrieval.py`、（可选）`agent_runtime/gateway.py`、`ctf_backend/settings.py`。

风险 / 规避：注入到 `knowledge_context` 的来源必须可被 `verifier` 的引用校验接受（保持 `source_ref` 规范）；无 Key 环境走本地回退，保证不空。

---

## 4. 建议实施顺序

1. **改造 2（索引 KnowledgeConcept）** — 独立、低风险，先把数据喂进向量库；
2. **改造 3.1 + 3.2（HNSW 索引 + RRF 融合）** — 打好检索质量底座；
3. **改造 1（打通 KnowledgeAgent）** — 收益最大，依赖 2/3 的数据与融合；
4. **改造 4（agent_runtime）** — 复用改造 1 的服务，顺带接入；
5. **改造 3.3~3.6（重排/查询改写/回退语义化/模型名修正）** — 增量优化，开关灰度。

> 另有一条可**并行**的新增工作流 ⑤「文档输入处理管线」（见第 8 节）：它只负责把文档喂进统一向量库，不改检索签名，可与改造 2/3 并行推进，入库后四条链路自动可检索。

每步都可独立上线、独立回滚；关键词与本地向量回退全程保留，不破坏现有行为。

## 5. 验证与测试清单

- 单元测试：泄题过滤、无 Key 回退、RRF 融合排序、概念索引计数；
- 管理命令：`check_legal_kb` 验证各 `source_type` 向量数；
- 评测集：中文语义改写 query 的 Recall@k / MRR 对比；
- 性能：`LegalRetrievalLog.latency_ms` 改造前后分布；
- 回归：导师对话、合规审计、agent_runtime 三条链路端到端冒烟。

## 6. 关键代码位置索引

| 作用 | 文件 |
|------|------|
| 语义召回 | `backend/legal_kb/services/retrieval_service.py` |
| 答案合成 | `backend/legal_kb/services/rag_answer_service.py` |
| Embedding | `backend/legal_kb/services/embedding_service.py` |
| 平台内容索引 | `backend/legal_kb/services/platform_indexing_service.py` |
| 向量表模型 | `backend/legal_kb/models.py`（`LegalKnowledgeEmbedding`） |
| pgvector 迁移 | `backend/legal_kb/migrations/0002_enable_pgvector.py` |
| 知识 Agent | `backend/agents/specialists/knowledge_agent.py` |
| 关键词检索/上下文 | `backend/ai_assistant/service.py`（`search_simple_knowledge` / `build_knowledge_context` / `_build_tutoring_vector_context`） |
| agent_runtime 检索 | `backend/agent_runtime/retrieval.py`、`gateway.py` |
| 知识概念模型 | `backend/learning_paths/models.py`（`KnowledgeConcept` / `ConceptRelation` / `ConceptResource`） |
| 配置项 | `backend/ctf_backend/settings.py`（`EMBEDDING_*` / `LEGAL_KB_*`） |

---

> 下一步：确认优先级后，我可以从「改造 2」或「文档输入管线」开始落地，每块附带单测与验证命令。

---

## 7. 模块化与低耦合设计原则

本次所有改造（含新增管线）统一遵循以下原则，保证不增加耦合、便于阅读与替换：

- **单一向量库、单一 Embedding 入口**：一律复用 `legal_kb` 的 `LegalKnowledgeEmbedding` + `EmbeddingService`，**不新建并行检索体系**，避免数据与配置分裂。
- **依赖倒置（核心只依赖抽象）**：管线/服务核心只依赖 `Protocol`/`ABC` 接口，具体第三方库封装在独立 `adapters/` 里，**懒加载**（沿用项目已有的 `from openai import OpenAI`、`from pgvector.django import ...` 懒导入风格）；某个库缺失只降级对应格式，不拖垮整条链路。
- **对现有代码「只加不改」**：通过「新增 `source_type` + 新增薄服务」接入，不改动既有检索函数签名；智能体侧改为调用新服务，回归面最小。
- **清晰单向分层**：`loader → parser → cleaner → chunker → embedder → repository`，各层职责单一、单向依赖，不出现反向引用或环依赖。
- **可读性**：一个 stage 一个小文件；优先纯函数；完整类型注解与简短 docstring；所有可调参数集中到 `settings`（如默认 parser、分块大小、上传上限、开关）。
- **可测试**：每个 adapter 可独立单测；管线用「假 adapter」即可端到端跑通，不依赖网络或真实文件。

## 8. 新增：RAG 文档输入处理流程（Ingestion Pipeline）

目标：支持上传文档（PDF / Word / PPT / Markdown / TXT / HTML 等），自动「解析 → 清洗 → 切块 → 向量化 → 入统一向量库」，形成**一套新的 RAG 数据**（`source_type='document'`），四条检索链路自动可用。

### 8.1 建议模块布局（新 Django app，自包含、低耦合）

```
backend/rag_ingestion/
  __init__.py
  interfaces.py            # Protocol: DocumentParser / TextChunker / Embedder / ChunkRepository
  pipeline.py              # 编排器：只依赖 interfaces，不 import 任何第三方解析库
  registry.py              # 按扩展名/MIME 选择 parser（可被 settings 覆盖）
  cleaning.py              # 文本归一、去页眉页脚/噪声
  chunking.py              # 结构感知切块（复用/扩展 legal_kb.ChunkingService）
  models.py                # DocumentSource（登记上传文档）；入库作业复用 KbIngestionJob
  services.py              # IngestionService（门面，供 API / 命令 / 智能体调用）
  adapters/
    parser_markitdown.py   # 默认轻量解析（MIT）
    parser_docling.py      # 复杂版式/表格（MIT，可选依赖）
    parser_pymupdf.py      # PDF 文本兜底
    parser_docx.py         # python-docx
    parser_plain.py        # md / txt / html
    embedder_legalkb.py    # 封装现有 EmbeddingService（适配 Embedder 接口）
    repository_legalkb.py  # 封装 LegalKnowledgeEmbedding 读写（适配 ChunkRepository）
  management/commands/ingest_documents.py
  views.py                 # 上传 + 触发入库（必须鉴权）
  tests/
```

> 关键点：`pipeline.py` 与 `interfaces.py` 不出现任何 `markitdown/docling/fitz/pgvector` 字样——第三方只存在于 `adapters/`，通过 `registry` 在边界处装配。这样换解析器 = 换一个 adapter，不动核心。

### 8.2 处理流程（数据流）

1. **登记/上传**：`DocumentSource` 记录文件、MIME、`source_hash`、状态、可见范围；按 `sha256` **去重幂等**（沿用 `legal_kb.hashing` + `LegalDocument.source_hash` 既有模式）。
2. **加载**：读取字节（不信任原始文件名，存储隔离）。
3. **格式路由**：`registry` 按扩展名/MIME 选 parser。
4. **解析**：统一产出「Markdown + 结构信息（标题层级、页码、表格）」。
5. **清洗归一**：去页眉页脚/重复噪声、规整空白、保留标题结构。
6. **结构感知切块**：优先按标题/章节切，超长再按定长窗口回退；标题路径、页码写入 `metadata`。
7. **批量向量化**：走 `EmbeddingService`（远程不可用自动回退本地向量）。
8. **入库**：写 `LegalKnowledgeEmbedding`，`source_type='document'`，`metadata` 带 `document_id/page/heading_path/visibility`。
9. **审计留痕**：`AuditEvent` + `AuditLedgerService`（与现有索引流程一致）。
10. **可检索**：无需额外改动，四条链路查询统一表即命中。

### 8.3 幂等 / 失败 / 安全

- **幂等**：以 `source_hash` 判重；重复入库前按 `source_type+object_id` 删旧块（`_index_queryset` 已有该模式）。
- **分阶段状态**：解析/切块/向量化/入库各阶段状态落 `KbIngestionJob`，失败可续跑；单格式解析失败降级到兜底 parser（如 PDF: docling → pymupdf）。
- **安全（务必）**：上传接口**强制鉴权** + 限格式 + 限大小 + 内容类型校验；文档可见范围用 `metadata.visibility` 控制，**沿用泄题隔离策略**（含答案/题解的文档不对学员检索暴露）；文件存储与执行环境隔离。

### 8.4 需要的最小改动

- `LegalKnowledgeEmbedding.SOURCE_TYPE_CHOICES` 增加 `('document', 'Uploaded document')`（加迁移）。
- `settings` 增加：默认 parser、是否启用 docling/MinerU、分块大小、上传大小/格式白名单、管线开关。
- 其余均为**新增文件**，不改既有检索与智能体代码签名。

## 9. 可复用的成熟开源项目与代码

定位：**优先选相对成熟、API 稳定、许可友好（MIT / Apache）的库，作为依赖直接安装、在 adapter 里调用其代码**；大型平台只读源码借鉴、不整体嵌入。所有第三方只出现在 `adapters/`，核心零第三方依赖（第 7 节）。

### 9.1 直接复用的成熟库（装依赖即用）

| 库（pip 包） | 用途 | 许可 | 成熟度 | 管线位置 |
|------|------|------|--------|----------|
| `markitdown`（Microsoft） | 多格式→Markdown，依赖小 | MIT | 微软维护、活跃 | `parser_markitdown`（默认轻量解析） |
| `docling`（IBM） | PDF 版式/表格→结构化 MD/JSON，自带 HybridChunker | MIT | RAG 领域主流 | `parser_docling`（富解析）+ 切块参考 |
| `pdfplumber`（基于 `pdfminer.six`） | PDF 文本/表格精取 | MIT | 老牌稳定 | PDF 首选解析（MIT，见红线） |
| `pymupdf` / fitz | PDF 高速文本/图像 | **AGPL-3.0 / 商用双授权** | 老牌高性能 | 可选，许可敏感，建议隔离或用 pdfplumber 代替 |
| `python-docx` | Word 解析 | MIT | 事实标准 | `parser_docx` |
| `python-pptx` | PPT 解析 | MIT | 事实标准 | `parser_pptx`（可加） |
| `openpyxl` | Excel 解析 | MIT | 事实标准 | 表格类解析（可加） |
| `beautifulsoup4` + `lxml` | HTML 正文提取/清洗 | MIT | 老牌 | `parser_plain`（html） |
| `langchain-text-splitters` | `RecursiveCharacterTextSplitter` / `MarkdownHeaderTextSplitter` | MIT | 切块事实标准 | `chunking.py` 直接复用切块算法 |
| `unstructured` | 统一 `partition()` 多格式 | Apache-2.0（部分付费） | 企业级 | 可选「全能 parser」adapter |
| `rank-bm25` | BM25 词法召回 | Apache-2.0 | 轻量稳定 | 改造 3 混合检索的词法侧（或用 PG 全文检索） |
| `FlagEmbedding`（BGE-reranker） | 中文重排效果好 | MIT | BAAI 维护 | 改造 3.3 重排（可选，依赖较重） |
| `sentence-transformers`（CrossEncoder） | 通用重排 | Apache-2.0 | 主流 | 改造 3.3 重排（可选，依赖 torch） |

> 关键点：`langchain-text-splitters` 是**独立小包**（不拉入 LangChain 全家桶），可只装它来复用成熟切块代码——既「成熟可复用」又不引入框架级耦合。

### 9.2 各格式推荐选型（首选 → 兜底）与调用示例

| 格式 | 首选 | 兜底 |
|------|------|------|
| PDF（文本型） | `pdfplumber`（MIT） | `pymupdf`（隔离）/ `docling` |
| PDF（复杂版式/表格/扫描） | `docling`（MIT） | MinerU（独立服务隔离） |
| Word `.docx` | `python-docx` | `markitdown` |
| PPT `.pptx` | `python-pptx` | `markitdown` |
| Excel `.xlsx`/`.csv` | `openpyxl` / 标准库 `csv` | `markitdown` |
| Markdown / TXT | 内置 `parser_plain` | — |
| HTML | `beautifulsoup4`+`lxml` | `markitdown` |
| 兜底（未知/混合） | `markitdown` | `unstructured` |

```python
# adapters/parser_markitdown.py —— 第三方只在 adapter 内，懒加载
def parse(path: str) -> str:
    from markitdown import MarkItDown           # 懒导入：缺库只降级本格式
    return MarkItDown().convert(path).text_content

# chunking.py —— 复用成熟切块代码，但只装 langchain-text-splitters 子包
def split_markdown(md: str, size=1000, overlap=120):
    from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
    headed = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")]
    ).split_text(md)
    rec = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
    return rec.split_documents(headed)           # 标题路径保留在 metadata
```

### 9.3 仅作架构借鉴的平台（读源码，不整体嵌入）

| 平台 | 许可 | 借鉴点 | 为何不直接嵌入 |
|------|------|--------|----------------|
| [RAGFlow](https://github.com/infiniflow/ragflow) | Apache-2.0 | DeepDoc 深度解析、模板化切块、混合检索实现 | 组件重、与自身服务/存储强绑定 |
| [Dify](https://github.com/langgenius/dify) | 开源 + 商用条款 | 模块化文档管线的架构划分 | 平台级，含商用限制 |
| [LlamaIndex](https://github.com/run-llama/llama_index) / [LangChain](https://github.com/langchain-ai/langchain) | MIT | `IngestionPipeline` / `NodeParser` 可插拔接口设计 | 全家桶依赖大；只需切块就装 `langchain-text-splitters` 子包 |

### 9.4 许可红线（务必遵守）

直接链接进后端的代码**只用 MIT / Apache-2.0**。`pymupdf`、MinerU 为 **AGPL-3.0**，若需其解析能力，必须以**独立进程 / 服务**隔离调用（输入文件、输出 JSON），或改用 `pdfplumber`（MIT）；`unstructured`、Dify 含付费/商用附加条款。**采用前以各仓库当前 LICENSE 复核。**

---

> 下一步：确认优先级后，我可以从「文档输入管线」或「改造 2」开始落地，每块按第 7 节原则（接口 + adapter + 单测）实现，并附验证命令。


