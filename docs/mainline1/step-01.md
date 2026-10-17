# 第 1 步：源码核查与复用边界

日期：2026-10-11（Asia/Shanghai）。本步 complete 仅指源码核查完成；不表示主线一功能完成。

结论：可复用认证/事务/审计/前端基础及真实模型传输代码；上传私有存储、任务与模型输出需要适配。精确表格定位、资产版本和识别—复核—计划闭环需新建。真实语义接入未获本任务批准，运行状态未知。所有复用建议均为后续设计输入，不是实现授权。

本文件内路径相对实际 repository_root；代码证据以文件和符号为准，行号为本 revision 定位辅助。evidence_refs 的 E 编号解析到 findings.evidence_index 的 EvidenceRef 对象；Verified 仅表示直接源码/元数据证据，业务测试均未运行。

## 结构化阶段结果与共同交接

```json
{
  "step": "01",
  "status": "complete",
  "stage": "Stage 1 / 源码核查",
  "stage_result": {
    "schema": "mainline1.stage1.v1 / E7",
    "data": {
      "repository_state": {
        "repository_root": "D:\\aaa10\\16015478源码\\project-code",
        "session_cwd": "D:\\aaa10\\16015478源码",
        "revision": "f4ac82caf32a4112c047cdb8848cab135acbb3c6",
        "branch": "feature/Sensitive-data-recognition",
        "commit_time": "2026-10-10T23:00:29+08:00",
        "review_date": "2026-10-11",
        "timezone": "Asia/Shanghai",
        "initial_tracked_changes": [],
        "initial_staged_changes": [],
        "initial_untracked": [
          "docs/主线一-上下文敏感数据识别-任务提示词.md",
          "docs/主线一-分阶段实施验证提示词.md",
          "docs/受控外发与执行-分阶段实现提示词-数据库增强版.md"
        ],
        "rules": [
          "未发现 D:/、D:/aaa10/、会话 cwd 与 project-code 内适用 AGENTS.md；external-labs/juice-shop/AGENTS.md 不适用本仓库",
          "遵守用户仅第1步授权及两份主线一提示词；.editorconfig 要求 UTF-8/LF",
          "未找到正式主线一交接/批准契约；docs 旧 agent-rag 文档仅为线索，不视为本轮批准",
          "忽略的 .env、业务数据库、媒体、日志和备份不读取；不能用 git clean 状态证明这些文件无已有内容"
        ],
        "entrypoints": [
          "backend/manage.py → ctf_backend.settings / ctf_backend.urls",
          "backend/ctf_backend/wsgi.py / asgi.py",
          "frontend/src/main.js → App.vue → router/index.js；frontend/package.json dev/build"
        ],
        "stack": {
          "declared": "Django 6.0.3 / DRF 3.16.1 / PostgreSQL+pgvector；Vue 3.5 / Vite 7.3 / Pinia / Arco / Axios；openpyxl 3.1.5 已在 requirements",
          "observed_interpreter": "Python 3.12.8; Django 6.0.5; DRF 3.17.1; openpyxl 3.1.5; langchain-openai 0.3.16; markitdown 不存在"
        },
        "handoff_location": "docs/mainline1/；本轮新建，无前序 step 依赖"
      },
      "capabilities": [
        {
          "id": "C01",
          "name": "认证与角色基础",
          "capability_status": "Implemented",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E08"
          ],
          "limitations": "只评价现有认证/角色代码；主线一对象权限尚需适配"
        },
        {
          "id": "C02",
          "name": "上传和私有资产存储",
          "capability_status": "Partial",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E03",
            "E04"
          ],
          "limitations": "有上传/受控下载，但不可直接满足敏感资产域隔离和不可变版本"
        },
        {
          "id": "C03",
          "name": "CSV/XLSX 精确定位解析",
          "capability_status": "Missing",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E05",
            "E12"
          ],
          "limitations": "限定已检索 backend Python 与当前 RAG 链路；有文本转换不等于目标定位解析"
        },
        {
          "id": "C04",
          "name": "扫描任务底座",
          "capability_status": "Partial",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E06",
            "E12"
          ],
          "limitations": "可借用持久状态/事务/令牌模式，尚无完整扫描调度、取消与尝试契约"
        },
        {
          "id": "C05",
          "name": "真实模型传输适配",
          "capability_status": "Implemented",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E07"
          ],
          "limitations": "只确认真实 API 调用代码，不确认运行可用或敏感分类能力"
        },
        {
          "id": "C06",
          "name": "已批准且可用的主线一语义后端",
          "capability_status": "Unknown",
          "evidence_status": "Verified",
          "verification_status": "Blocked",
          "confidence": "Medium",
          "evidence_refs": [
            "E07"
          ],
          "limitations": "未提供主线一模型、数据出域与预算批准；真实验证 Blocked"
        },
        {
          "id": "C07",
          "name": "最小审计与下游通知",
          "capability_status": "Partial",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E09",
            "E12"
          ],
          "limitations": "已有数据库审计/账本，需最小化载荷；可靠事件发布尚缺"
        },
        {
          "id": "C08",
          "name": "分类/画像/复核/计划/版本适用性闭环",
          "capability_status": "Missing",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E10",
            "E05",
            "E06"
          ],
          "limitations": "限本次 backend/frontend 源码检索范围；法律业务的类似名称不等价"
        },
        {
          "id": "C09",
          "name": "前端操作基础",
          "capability_status": "Partial",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E11"
          ],
          "limitations": "现有框架可直接复用，扫描业务页面需适配或新建；delivery_mode 未定"
        },
        {
          "id": "C10",
          "name": "当前解释器依赖一致性",
          "capability_status": "Partial",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E02",
            "E13"
          ],
          "limitations": "仅当前 Python，未核查其他环境；未安装/升级任何包"
        }
      ],
      "dependency_map": {
        "incoming": [
          "POST /api/rag-ingestion/ → DocumentIngestionView → IngestionService；management/commands/ingest_documents.py 也直接调用同 facade",
          "资源上传页/资源审核页 → api.resource → resources views/serializers → Resource + validators；下载还写 download_count 与 learning event",
          "KnowledgeBase.vue → api.legalKb.ingestDocument → legal_kb.views → LegalKbIngestionService（另一法规入库链）",
          "agent_runtime.views → AgentGateway → AgentRunStateStore + retrieval + AI service；AI service/legal 合规服务均消费 ai_providers",
          "learning_analytics.tasks 与 refresh_learning_analytics 管理命令 → run_analytics_job",
          "legal/challenges/legal_kb 服务 → AuditLedgerService；audit.views → verify_chain"
        ],
        "outgoing": [
          "RAG pipeline → registry/parser → clean_text → chunker → LegalKbEmbedder/EmbeddingService（可远程）→ LegalKbChunkRepository → LegalKnowledgeEmbedding + ContentType + DocumentSource",
          "ai_providers → 环境配置 → LangChain/OpenAI 兼容外部模型；provider 调用受数据出域和成本授权约束",
          "ORM → PostgreSQL（亦有 SQLite 配置分支）；审计/资源/分析任务有业务写入，不在本步执行",
          "UI → /api + Session/CSRF；资源媒体 → Django/Nginx storage 配置"
        ],
        "implicit_contracts": [
          "DocumentSource 全局 source_hash 唯一；同 hash completed 直接返回旧 visibility/owner，不能当作 scope 隔离缓存；重入是原地替换而非不可变新版本",
          "RAG document_id 为模型整数主键；ingestion_token 为 UUID；对象引用不能擅自统一主键或迁移",
          "RAG status completed 不等于扫描质量 complete；现有任务均无 cancelled 业务状态；同步 HTTP 201 不是异步任务协议",
          "plain 先匹配 CSV；ParsedDocument.text 无坐标；清洗不可逆，不可把 Markdown/规范化 offset 当原文 offset",
          "provider.is_available 仅配置检查；DeepSeek kwargs 不控制温度/输出上限；模型 fallback、规则 fallback 和 local-hash 分别记录",
          "可见性角色不等于资产所有权；IsAdminUser 与 role=admin 判断不同；默认匿名只读不可继承到敏感对象",
          "AuditEvent 与哈希链并非消息总线；payload/prompt/异常字符串/用户文件名需最小化，不能原样写审计",
          "Axios 默认已解包 data；列表分页一般 results；LegalWorkspace 仅展示组件；RAG GET 截断 200 条并非通用扫描分页",
          "任意新媒体路径若落在公开 /media/ 下可能直出；部署私有性须未来单独验证"
        ]
      },
      "reuse_decisions": [
        {
          "target": "认证、Django ORM 事务、Axios/基础布局",
          "decision": "可直接复用基础组件",
          "boundary": "对象权限/业务服务仍须新建或适配；不意味着端到端直接可用",
          "evidence_refs": [
            "E02",
            "E08",
            "E11"
          ]
        },
        {
          "target": "上传校验与受控下载",
          "decision": "需要适配",
          "boundary": "保留 resources 教学语义，主线一使用独立私有资产引用；评估复用 ZIP 限制函数，不能直接放宽资源白名单",
          "evidence_refs": [
            "E03",
            "E04"
          ]
        },
        {
          "target": "RAG parser/pipeline",
          "decision": "不作为精确表格解析器复用；新建表格解析及位置映射",
          "boundary": "优先标准库 csv 与已声明 openpyxl；本步不设计正式坐标契约、不实现、不新增依赖",
          "evidence_refs": [
            "E05",
            "E13"
          ]
        },
        {
          "target": "任务持久化与 ownership token",
          "decision": "需要适配机制；新建主线一 scan/attempt 领域",
          "boundary": "不复制/改写教学任务，不把同步 RAG 入口变成未管理后台线程；调度方案留第2步",
          "evidence_refs": [
            "E06"
          ]
        },
        {
          "target": "BaseProvider/ChatResponse",
          "decision": "需要适配",
          "boundary": "固定后端、参数、预算、输出 schema/类别/定位校验；不沿用教学工具执行器和自动多厂商切换",
          "evidence_refs": [
            "E07"
          ]
        },
        {
          "target": "AuditEvent/AuditLedgerService",
          "decision": "需要适配",
          "boundary": "仅最小元数据；事件信封、可靠发布与去重属于待共同确定契约；不用 AIAuditLog 记录敏感正文",
          "evidence_refs": [
            "E09"
          ]
        },
        {
          "target": "分类政策、可信上下文、发现画像、人工复核、适用状态、计划纯校验",
          "decision": "新建",
          "boundary": "法律关键词风险/事实脱敏不可替代本主线领域；不做主线二风险决策或实际外发",
          "evidence_refs": [
            "E10"
          ]
        },
        {
          "target": "真实后端/部署资产服务/正式跨线契约",
          "decision": "未知",
          "boundary": "配置文件或另一任务提示词不等于批准；只阻塞实际接入，源码核查不受阻",
          "evidence_refs": [
            "E01",
            "E07"
          ]
        }
      ],
      "open_questions": [
        {
          "id": "Q01",
          "status": "Unknown",
          "blocking_scope": "后续资产/范围/画像/事件/执行契约接入",
          "resolution_needed": "正式 owner 和已批准契约位置 Unknown。第2步先提交 Proposed 契约，明确资产所有者、定位基数/Unicode 单位、版本/范围/hash、画像替代、权威适用状态、事件延迟/去重以及计划组合语义；不得自行批准跨线不兼容变化。"
        },
        {
          "id": "Q02",
          "status": "Unknown",
          "blocking_scope": "真实语义调用及 A/B/C 效果验收",
          "resolution_needed": "semantic_backend、允许数据、调用预算 Unknown。推荐先保持网络调用禁用；第2步形成固定 provider/model、合成样本烟测、超时/成本上限的可审阅方案，再请求具体批准。真实敏感原文外发仍禁止。"
        },
        {
          "id": "Q03",
          "status": "Unknown",
          "blocking_scope": "后续持久化实现与迁移",
          "resolution_needed": "approved_schema_changes Unknown，现有任务表不满足目标。推荐先设计独立领域表及与资产 owner 的引用；迁移文件编写、隔离测试库验证、业务库执行分别确认范围；本步均不做。"
        },
        {
          "id": "Q04",
          "status": "Unknown",
          "blocking_scope": "运行/部署与安全验收",
          "resolution_needed": "资源存储部署、任务执行方式、崩溃恢复机制、依赖基线 Unknown；当前解释器版本漂移。推荐第2步列不新增队列依赖的受管执行方案与引入队列的成本对照，未经批准不安装/升级；已有 openpyxl 可优先评估。"
        },
        {
          "id": "Q05",
          "status": "Unknown",
          "blocking_scope": "验收配置与交付范围",
          "resolution_needed": "delivery_mode、效果阈值、资源/并发预算、数据保留时限 Unknown。以完整提示词 B/C/J 为产品与验收内容基线；不编造阈值。第2步提出 backend_only/minimal_ui 的具体范围及配置供决定。"
        }
      ]
    }
  },
  "mission": {
    "solved": [
      "版本/规则/修改边界确认",
      "主要复用边界、直接调用方、出向依赖与隐式约定有源码证据",
      "CSV/XLSX 定位、任务持久化和真实模型代码专项核查",
      "未知、依赖授权与跨任务线契约问题已记录"
    ],
    "not_solved": [
      "后续阶段的设计、实现和验收（不在本步）",
      "真实后端可用性、部署私有性、数据库并发行为和模型效果"
    ]
  },
  "inputs": {
    "repository_root": {
      "value": "D:\\aaa10\\16015478源码\\project-code",
      "source": "目录与 Git 核查"
    },
    "product_spec": {
      "value": "完整提示词 B/C 及成功定义为基线",
      "source": "用户无额外产品文本；B3"
    },
    "contract_spec": "Unknown：未见正式主线一契约；不将受控外发任务提示词当批准",
    "approved_contracts": "Unknown",
    "approved_change_scope": "仅第1步源码核查与 docs/mainline1 文档",
    "approved_dependencies": "无本会话新增依赖批准；已声明依赖保留",
    "approved_schema_changes": "Unknown；本轮禁止数据库变更",
    "semantic_backend": "Unknown；provider 代码不构成批准",
    "data_policy": "不读取无关凭据/业务原文；不发真实模型请求；不改业务数据库",
    "acceptance_targets": "本步主要复用判断有代码证据，未知和影响明确；完整效果门槛 Unknown",
    "resource_budget": "Unknown；本步仅本地只读检查",
    "delivery_mode": "Unknown",
    "handoff_in": "无已有主线一 HANDOFF 或前序阶段记录"
  },
  "artifacts": [
    {
      "path": "docs/mainline1/step-01.md",
      "purpose": "完整本步结果与证据/命令"
    },
    {
      "path": "docs/mainline1/HANDOFF.md",
      "purpose": "最小恢复入口与结构化阶段摘要"
    }
  ],
  "findings": {
    "capabilities_ref": "stage_result.data.capabilities",
    "evidence_index": {
      "E01": {
        "source": "git / repository inventory",
        "location": "project-code; HEAD f4ac82caf32a4112c047cdb8848cab135acbb3c6",
        "observation": "实际仓库位于会话 cwd 的 project-code 子目录；分支 feature/Sensitive-data-recognition；初始 tracked/index diff 为空，三个提示词未跟踪。",
        "supports": "本次源码基线与修改边界",
        "does_not_support": "运行服务、忽略目录和生产部署状态"
      },
      "E02": {
        "source": "backend/requirements.txt; frontend/package.json; backend/ctf_backend/urls.py",
        "location": "requirements:1; package.json:1; urls.py:33",
        "observation": "Django/DRF、PostgreSQL/pgvector、Vue/Pinia/Arco/Vite；根路由包含 resources、rag-ingestion、agent-runtime、audit、legal、legal-kb、analytics。",
        "supports": "现有技术栈声明和 HTTP 接入点",
        "does_not_support": "依赖全部安装、接口运行可用"
      },
      "E03": {
        "source": "backend/resources/models.py; backend/resources/views.py; backend/resources/validators.py; frontend/nginx.conf",
        "location": "Resource.file:29; resource_download_view:247; validate_resource_file:76; nginx:34",
        "observation": "资源 FileField 在 resources/；下载需登录、已审核，reserved 使用 highlight_resource 参数；Django/Nginx 阻断 /media/resources/，其他 /media/ 静态公开；资源白名单无 CSV/XLSX，ZIP 有条目与实际解压累计限制。",
        "supports": "已有上传校验、受控下载模式可参考；不能原样作为敏感资产存储",
        "does_not_support": "租户/资产级授权、不可变文件版本、部署实际私有性"
      },
      "E04": {
        "source": "backend/rag_ingestion/views.py; models.py; services.py; adapters/repository_legalkb.py",
        "location": "DocumentIngestionView:19; DocumentSource:7; ingest_bytes:23; replace:20",
        "observation": "上传限 staff、大小/后缀校验，读 bytes 后同步 parse→embed→store；DocumentSource 仅元数据无原文件字段，source_hash 全局唯一；已完成同 hash 直接返回，重入更新原记录；向量库替换旧索引。",
        "supports": "RAG 入库不等于私有资产版本存储；全局去重不能直接用作域内扫描幂等",
        "does_not_support": "原始文件重放、scope/context/policy 隔离、不可变扫描历史"
      },
      "E05": {
        "source": "backend/rag_ingestion/adapters/parser_plain.py; parser_markitdown.py; interfaces.py; cleaning.py; registry.py",
        "location": "PlainTextParser:12; MarkItDownParser:15; ParsedDocument:19; clean_text:10; DEFAULT_PARSER_PATHS:18",
        "observation": "CSV 被 plain 优先识别，只解码成 text；编码回退含 latin-1。XLSX 仅可选 MarkItDown 转 Markdown；输出 text/metadata。清洗改变换行、空白且无逆映射。backend Python 搜索 csv.reader/DictReader/load_workbook/read_excel 未命中。",
        "supports": "所查链路缺少 CSV 逻辑记录、XLSX 工作表/坐标/合并锚点、Unicode 区间映射及覆盖契约",
        "does_not_support": "真实 XLSX 可解析性、公式/隐藏内容/外链/压缩包安全策略"
      },
      "E06": {
        "source": "backend/rag_ingestion/services.py; adapters/repository_legalkb.py; backend/learning_analytics/scheduler.py; models.py; backend/agent_runtime/models.py; gateway.py",
        "location": "ingest_bytes:23, _finish:100; replace:40; run_analytics_job:28; LearningAuditJob:331; AgentRun:5; run_learning_task:37",
        "observation": "RAG 事务行锁与 ingestion_token 保护当前尝试；分析作业有数据库状态、计数、幂等键和 attempt_count；AgentRun 保存步骤与结果；入口同步执行，gateway 的线程池用于同步等待协程。",
        "supports": "持久化与旧尝试防护确实存在，可适配原理",
        "does_not_support": "通用持久队列、崩溃恢复/租约、取消、预算、重试请求冲突、scan/attempt 分离完整能力"
      },
      "E07": {
        "source": "backend/ai_providers/base.py; deepseek.py; __init__.py; backend/legal/services/compliance_agent.py; backend/legal_kb/services/embedding_service.py",
        "location": "BaseProvider:73; DeepSeekProvider:10; MultiProviderManager:197; ComplianceAgent:12; EmbeddingService:15",
        "observation": "真实网络传输代码调用 ChatOpenAI.ainvoke；is_available 仅检查 enabled/key。DeepSeek 固定 temperature/max_tokens 且 chat kwargs 未传入客户端；manager 从环境初始化。ComplianceAgent 存在 rules-v1 fallback；embedding 无配置/失败使用 local-hash-v1。",
        "supports": "真实 provider 适配代码存在，语义后端运行状态未知；本地 hash/规则降级不是敏感识别语义",
        "does_not_support": "当前凭据有效性、已批准后端、成本/准确率/上下文收益；嵌入成功不等于分类定位完成"
      },
      "E08": {
        "source": "backend/ctf_backend/settings.py; backend/users/permissions.py; backend/agent_runtime/views.py; backend/legal_kb/services/visibility.py",
        "location": "REST_FRAMEWORK:259; is_staff_or_role:4; AgentRunListView:28; apply_embedding_visibility:64",
        "observation": "Session/Token 认证，默认 IsAuthenticatedOrReadOnly；已有角色检查与 user 过滤查询；RAG 可见性按当前 DocumentSource 过滤而非缓存快照，非 document 行不受此过滤。",
        "supports": "可复用认证和对象过滤模式；匿名只读默认不可直接用于敏感结果",
        "does_not_support": "组织/数据域/资产/复核/原文读取权限与跨作用域隔离"
      },
      "E09": {
        "source": "backend/audit/models.py; services.py; backend/rag_ingestion/services.py; backend/legal/services/compliance_orchestrator.py",
        "location": "AuditEvent.log:83; AIAuditLog:164; AuditLedgerService:80; IngestionService._audit:112; orchestrator:180",
        "observation": "有事件记录与事务哈希链；RAG 审计 best-effort 吞异常；AIAuditLog 含 user_message/ai_response，ComplianceAgent input_payload 含 prompt。检索未见通用 outbox 实现。",
        "supports": "最小事件记录/哈希链可适配；不得沿用正文审计；审计写入不能当作可靠通知",
        "does_not_support": "事件可靠投递、去重信封、下游消费/权威适用状态查询、账本运行并发正确性"
      },
      "E10": {
        "source": "backend/legal/services/risk_evaluator.py; fact_redactor.py; backend/legal/models.py",
        "location": "RiskEvaluator:25; redact_manual_notes:14; LegalFactSnapshot:482",
        "observation": "现有法律风险评估是关键词/风险分值；fact_redactor 截断并替换 token/flag 无位置映射；事实快照绑定法律任务。目标对象及服务检索未见主线一画像、扫描、计划实现。",
        "supports": "现有法律规则/快照属于另一业务域，不能冒充敏感类别政策/发现/复核/脱敏计划",
        "does_not_support": "主线一分类、语义融合、版本化政策、画像替代、计划验证和效果评测已完成"
      },
      "E11": {
        "source": "frontend/src/api/index.js; admin/views/legal/LegalWorkspace.vue; KnowledgeBase.vue; admin/views/Resources.vue; router/index.js",
        "location": "api:3,77,306; LegalWorkspace:96; KnowledgeBase:1,129; Resources:203; router:159",
        "observation": "Axios 带 cookie/CSRF，成功响应解包 response.data（blob 例外）；LegalWorkspace props/slots/events 提供表格操作框架；资源/知识库页面调用真实现有 API，未见扫描页面。",
        "supports": "复用 API 客户端、布局和基础表格；主线一流程需适配/新建",
        "does_not_support": "扫描进度、覆盖、复核、版本比较 UI 或真实联通已存在"
      },
      "E12": {
        "source": "backend/rag_ingestion/tests.py; test_postgres_concurrency.py; backend/resources/tests.py; backend/legal_kb/tests.py; backend/audit/tests.py; backend/learning_analytics/test_pipeline.py",
        "location": "RegistryTests:27; IngestionOwnershipTests:272; PostgresIngestionConcurrencyTests:29; Resource validation tests:314; DocumentVisibilityTests:520; AuditLedgerServiceTests:14; LearningPipelineTests:13",
        "observation": "已有测试覆盖入库幂等/失败、旧尝试、资源下载/ZIP、RAG 可见性、哈希链、学习任务。MarkItDownParserTests:160 使用 FakeMarkItDown，仅证明临时文件关闭与清理；Pg 并发用替身 parser/embedder。",
        "supports": "已有测试设计范围及后续可选定向回归入口",
        "does_not_support": "本轮测试通过、CSV/XLSX 精确定位或真实模型效果"
      },
      "E13": {
        "source": "本次只读 Python AST / importlib.metadata 检查",
        "location": "step-01.md verification.V02/V03",
        "observation": "180 个目标模块 Python 文件 AST 解析通过；当前 Python 3.12.8，Django 6.0.5、DRF 3.17.1 与声明 6.0.3/3.16.1 不同；openpyxl 3.1.5，langchain-openai 0.3.16，MarkItDown 未安装。",
        "supports": "语法检查和当前解释器发行包元数据",
        "does_not_support": "导入成功、应用启动、其他虚拟环境/容器配置或业务行为"
      }
    }
  },
  "changes": [
    {
      "target": "docs/mainline1/step-01.md 与 HANDOFF.md",
      "motivation": "固化第1步核查结果、证据与授权边界",
      "scope": "仅新建本任务两份文档；不改业务代码/接口/配置/数据库",
      "dependencies": [
        "两份主线一任务提示词",
        "当前源码与会话授权"
      ],
      "priority": "P1",
      "authorization": "用户本轮明确允许核查与交接文档",
      "important_alternatives": "未发现正式交接目录，故使用规定目录；不侵入旧 agent-rag 文档或其他任务线提示词",
      "unverified_assumptions": "运行环境、部署私有性与后续契约均未验证",
      "rollback": "仅在确认两份文档仍为本轮版本且无后续追加后，删除这两份新文件；若已有后续记录，仅撤回本步新增内容。不得 git reset/clean 或删除其他文件。"
    }
  ],
  "verification": [
    {
      "id": "V01",
      "name": "版本、规则、调用链与已有测试源码核查",
      "level": 1,
      "status": "Passed",
      "scope": "本步静态核查，不代表行为测试",
      "commands": [
        "git rev-parse HEAD; git branch --show-current; git log -1 --format=fuller",
        "git -c core.quotepath=false status --short; git diff --stat; git diff --cached --stat",
        "rg --files --hidden -g AGENTS.md -g \"!.git\" -g \"!node_modules\"",
        "rg -n \"csv|xlsx|openpyxl|read_excel|DictReader|csv.reader|load_workbook\" backend -g \"*.py\"",
        "rg -n \"AssetVersion|ScanRun|sensitivity|redaction_plan|脱敏计划|敏感数据识别\" backend frontend/src -g \"*.py\" -g \"*.js\" -g \"*.vue\"",
        "定向 Get-Content 与 rg 读取 E02—E12 的调用方/出向依赖/测试；未读取 .env/数据/媒体/日志"
      ],
      "actual_result": "定位真实仓库；无 tracked/index 修改；未见适用 AGENTS 或正式交接目录；目标能力结论见 capabilities",
      "evidence_refs": [
        "E01",
        "E02",
        "E03",
        "E04",
        "E05",
        "E06",
        "E07",
        "E08",
        "E09",
        "E10",
        "E11",
        "E12"
      ],
      "gap": "部署与行为未验证"
    },
    {
      "id": "V02",
      "name": "定向 Python AST 语法检查",
      "level": 1,
      "status": "Passed",
      "scope": "9 个相关目录，共180个 .py 文件；不 import 应用、不生成 pyc",
      "command": "见下方可复现命令",
      "actual_result": "AST_PARSE_PASS files=180；exit 0",
      "evidence_refs": [
        "E13"
      ],
      "gap": "不是导入、数据库、模型或业务测试"
    },
    {
      "id": "V03",
      "name": "当前解释器及依赖元数据",
      "level": 1,
      "status": "Passed",
      "scope": "python --version；importlib.metadata.version 查询指定包，不导入业务模块",
      "actual_result": "Python 3.12.8；Django 6.0.5；djangorestframework 3.17.1；openpyxl 3.1.5；langchain-openai 0.3.16；markitdown=NOT_INSTALLED_IN_CURRENT_PYTHON",
      "evidence_refs": [
        "E13"
      ],
      "gap": "当前环境与 requirements 不一致；Passed 仅表示完成检查"
    },
    {
      "id": "V04",
      "name": "已有业务/权限/持久化/并发测试",
      "level": 2,
      "status": "Untested",
      "scope": "E12 所列 Django TestCase / PostgreSQL TransactionTestCase",
      "actual_result": "仅阅读测试源码，未运行；未创建/迁移测试库；未新增业务测试",
      "evidence_refs": [
        "E12"
      ],
      "gap": "不能据此声明现有测试通过或 PostgreSQL 锁正确"
    },
    {
      "id": "V05",
      "name": "Mock、规则与真实语义分别验证",
      "level": 2,
      "status": "Untested",
      "scope": "Mock：FakeMarkItDown/FakeProvider 只检查测试源码；规则：RiskEvaluator/fact_redactor 只检查源码",
      "actual_result": "本轮无 Mock/规则执行结果；真实语义验证单列 V06",
      "evidence_refs": [
        "E07",
        "E10",
        "E12"
      ],
      "gap": "没有主线一效果或定位行为证据"
    },
    {
      "id": "V06",
      "name": "真实语义后端与核心对照实验",
      "level": 2,
      "status": "Blocked",
      "scope": "主线一模型烟测与 A/B/C",
      "actual_result": "未执行网络/付费模型调用；未验证凭据；后端、数据和预算无本任务批准",
      "evidence_refs": [
        "E07"
      ],
      "gap": "仅阻塞后续真实路径，不阻塞本步 complete"
    },
    {
      "id": "V07",
      "name": "浏览器、真实存储/接口、迁移及端到端验收",
      "level": 3,
      "status": "Untested",
      "scope": "前端、部署、数据库与下游",
      "actual_result": "未启动服务、构建页面、迁移数据库或触发下载/审计写入",
      "evidence_refs": [
        "E03",
        "E08",
        "E11"
      ],
      "gap": "复用结论限源码，不能宣称生产安全"
    },
    {
      "id": "V08",
      "name": "交接结构与最终变更边界",
      "level": 1,
      "status": "Passed",
      "scope": "两份新文档、三个初始提示词、Git tracked/index",
      "commands": [
        "Python json.loads 提取两份 Markdown 首个 JSON 块并断言共同字段和 E7 字段；UTF-8/LF 检查",
        "hashlib.sha256 比对三个初始提示词与本轮写文档前摘要",
        "git diff --exit-code; git diff --cached --exit-code; git diff --check; git -c core.quotepath=false status --short"
      ],
      "actual_result": "两份文档字段齐全；三个初始提示词摘要不变；tracked/index diff 为空；git diff --check exit 0（不覆盖未跟踪文件）；新增仅 docs/mainline1 下两份文档。",
      "evidence_refs": [
        "E01"
      ],
      "gap": "未跟踪文档另用 JSON/编码检查；忽略的业务数据未读取，不能据此证明其状态"
    }
  ],
  "approved_decisions": [
    {
      "decision": "仅执行第1步，允许只读源码/已有检查与本任务文档",
      "source": "当前用户消息"
    },
    {
      "decision": "使用完整提示词基线及共同交接约定；结束停止等待第2步",
      "source": "当前与上一条用户消息"
    }
  ],
  "judgment_changes": [
    {
      "previous": "初次在会话 cwd 查询 Git 失败，仓库根位置待确认",
      "current": "真实 Git 仓库是 project-code；并非无 Git 信息",
      "new_evidence_refs": [
        "E01"
      ],
      "affected_decisions": [
        "版本记录与全部核查路径"
      ]
    },
    {
      "previous": "CSV/XLSX 扩展名、task/provider 模块仅为能力线索（Unknown）",
      "current": "精确表格定位 Missing；任务底座 Partial；真实传输代码 Implemented，主线一运行后端 Unknown",
      "new_evidence_refs": [
        "E04",
        "E05",
        "E06",
        "E07",
        "E12",
        "E13"
      ],
      "affected_decisions": [
        "不直接复用 RAG 解析和任务入口",
        "模型代码与可用性/效果分开记录"
      ]
    }
  ],
  "open_questions": [
    {
      "id": "Q01",
      "status": "Unknown",
      "blocking_scope": "后续资产/范围/画像/事件/执行契约接入",
      "resolution_needed": "正式 owner 和已批准契约位置 Unknown。第2步先提交 Proposed 契约，明确资产所有者、定位基数/Unicode 单位、版本/范围/hash、画像替代、权威适用状态、事件延迟/去重以及计划组合语义；不得自行批准跨线不兼容变化。"
    },
    {
      "id": "Q02",
      "status": "Unknown",
      "blocking_scope": "真实语义调用及 A/B/C 效果验收",
      "resolution_needed": "semantic_backend、允许数据、调用预算 Unknown。推荐先保持网络调用禁用；第2步形成固定 provider/model、合成样本烟测、超时/成本上限的可审阅方案，再请求具体批准。真实敏感原文外发仍禁止。"
    },
    {
      "id": "Q03",
      "status": "Unknown",
      "blocking_scope": "后续持久化实现与迁移",
      "resolution_needed": "approved_schema_changes Unknown，现有任务表不满足目标。推荐先设计独立领域表及与资产 owner 的引用；迁移文件编写、隔离测试库验证、业务库执行分别确认范围；本步均不做。"
    },
    {
      "id": "Q04",
      "status": "Unknown",
      "blocking_scope": "运行/部署与安全验收",
      "resolution_needed": "资源存储部署、任务执行方式、崩溃恢复机制、依赖基线 Unknown；当前解释器版本漂移。推荐第2步列不新增队列依赖的受管执行方案与引入队列的成本对照，未经批准不安装/升级；已有 openpyxl 可优先评估。"
    },
    {
      "id": "Q05",
      "status": "Unknown",
      "blocking_scope": "验收配置与交付范围",
      "resolution_needed": "delivery_mode、效果阈值、资源/并发预算、数据保留时限 Unknown。以完整提示词 B/C/J 为产品与验收内容基线；不编造阈值。第2步提出 backend_only/minimal_ui 的具体范围及配置供决定。"
    }
  ],
  "next_step_constraints": [
    "仅等待用户第2步指令，不自动实施设计或实现。",
    "第2步使用本记录与产品基线，先形成 Proposed 方案/契约/验收再提出具体实质决策；不能把本步复用建议当批准。",
    "不覆盖初始三个未跟踪提示词；后续开始时重查 Git 和交接，保留并行任务线新修改。",
    "不擅自更改跨模块语义、新增依赖、执行迁移、调用真实模型或外发真实原文；权限缺失只阻塞相关工作。",
    "设计优先考虑现有 csv 标准库/openpyxl、认证、事务、受管任务与最小审计；不得将 Mock/local-hash/教学 fallback 作为语义结果。"
  ]
}
```

## 可复现检查命令和执行限制

工作目录：`D:/aaa10/16015478源码/project-code`。V02/V03 的实际结果见上方记录。本轮未运行 manage.py test/check/migrate，未启动应用或 provider，未读取环境凭据。以下 Python 代码通过 PowerShell 单引号 here-string 管道交给 `python -B -` 执行；版本另用 `python --version` 查询。AST 不执行模块。

```python
import ast, pathlib, importlib.metadata as m
paths = [pathlib.Path('backend')/x for x in ('rag_ingestion','resources','ai_providers','agent_runtime','audit','legal','legal_kb','learning_analytics','users')]
files = sorted(p for root in paths for p in root.rglob('*.py'))
for p in files:
    ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))
print('AST_PARSE_PASS files=' + str(len(files)))
for name in ('Django','djangorestframework','openpyxl','markitdown','langchain-openai'):
    try: print(name + '=' + m.version(name))
    except m.PackageNotFoundError: print(name + '=NOT_INSTALLED_IN_CURRENT_PYTHON')
```

命令纠正记录：初次在会话父目录执行 Git 失败，已在实际仓库重新执行取得 E01；一次 Bash 花括号路径的 rg 命令被 PowerShell 拒绝，已用明确路径/目录重做；一次追加文档命令因嵌套 here-string 语法拒绝，改用不嵌套形式后写入。失败命令未造成文件写入，不构成业务测试结果。

## 后续优先风险（非本步实现任务）

| 优先级 | 触发条件与后果 | 证据与约束 |
|---|---|---|
| P0 | 把敏感文件直接放入通用 media 或学习资源/RAG 链，可能扩大读取范围、外发到 embedding 后端或保留原文 | E03/E04/E07/E09；先明确私有存储、作用域、数据策略和审计白名单 |
| P0 | 用清洗/Markdown 偏移直接替换原单元格，可能修改错误位置 | E05；独立解析映射，失配不能生成字符级操作 |
| P0 | 把全局 hash 去重、原地重入、completed 当域内不可变扫描完成，可能复用错误上下文或覆盖历史 | E04/E06；需 snapshot/scope/request/attempt 契约 |
| P1 | 将 local-hash、法律规则或教学 fallback 当真实语义，无法证明上下文识别收益 | E07/E10/E12；真实后端和 A/B/C 另行验证 |
| P1 | 把审计账本当可靠事件通知，下游可能继续使用旧画像/计划 | E09；需共同通知契约及权威状态查询，不能直接修改下游数据库 |

本步回滚仅撤回新建的两份核查文档；不回滚已有用户提示词、不触碰业务库和忽略目录。
