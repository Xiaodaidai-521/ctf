# 合并资源后的知识库检索测试（2026-11-12）

本文件保留修复前结果。后续原因分析、逐点修正与复测见 [修复报告](knowledge-retrieval-fix-20261112.md)。

结论：资料入库完整，核心回归通过，但当前内容调取表现不能算通过验收。实际查询暴露了候选截断、相关性排序和目录接口缺失；学习助手也尚未接入新导入的OWASP文档。

## 测试范围与数据

在当前 `5c8f2b0` 项目状态上测试。实际数据源为项目正常使用的外部SQLite数据库 `D:/aaa10/16015478源码/database/db.sqlite3`，不是项目内另一份历史数据库。原数据库以只读方式打开，使用SQLite一致性备份生成临时副本，API审计和检索日志仅写入副本，结束后删除副本。

新资料包括246篇OWASP文档、7份法规、393条法条、4106个片段。加上已有文章、题目和资源，共4205个索引片段。所有索引正文哈希、OWASP来源哈希、法规逐条正文均校验通过；246篇OWASP的internal可见性保留。

根目录环境配置指定dashscope/text-embedding-v4，但当前SQLite检索实现使用128维确定性本地向量和关键词融合。没有远程模型调用。HTTP检索通过Django测试客户端调用真实视图，回答使用本地模板；本次结果不能用于评价远程语义模型或LLM回答质量。没有进行并发压测，延迟只表示本次本地串行调用。

## 实际召回结果

选取13个OWASP查询和8个法规查询，各跑一次不筛选来源、一次按来源筛选，共42次查询。目标OWASP文档或明确的法条出现在前5个片段才记为命中。该指标只判断来源/条款命中，不代表片段完整回答了问题；样本用于诊断，不能外推为全库准确率。

| 查询类型 | 来源筛选 | 前5条命中 | MRR@5 | 中位延迟 | P95延迟 |
| --- | --- | --- | --- | --- | --- |
| OWASP | 无 | 3/13（23.1%） | 0.135 | 156ms | 162ms |
| OWASP | document | 3/13（23.1%） | 0.231 | 158ms | 188ms |
| 法规 | 无 | 0/8（0%） | 0 | 153ms | 159ms |
| 法规 | legal_clause | 2/8（25%） | 0.125 | 70ms | 75ms |

按来源筛选后合计5/21命中（23.8%）；不筛选来源合计3/21命中（14.3%）。这比此前只检查“返回非空结果”更严格，不能把旧记录中两条查询有结果解释为检索质量已经通过。

## 确认的问题

1. **本地检索的1000片段上限排除了大量资料。** `backend/legal_kb/services/retrieval_service.py:120` 直接取 `queryset[:1000]`，表默认按source_type、object_id、chunk_index排序。管理员不筛选时只取到26个文章片段、41个题目片段和933个OWASP片段，法规和已有32个资源片段完全未进入候选集。单独筛选document也只覆盖114/246篇文档。合并前备份只有368个片段，尚未触及此上限；这里仅比较备份库存，没有重跑合并前排序。
2. **指定准确文档标题仍会漏检。** `SQL Injection Prevention Cheat Sheet`、`Zero Trust Architecture Cheat Sheet`在通常检索中都没有命中目标。加object_id筛选后，同一检索服务分别正确返回文档208、245的5个片段，证明资料已经入库，遗漏发生在候选阶段。
3. **法规排序偏离明确条款。** 查询“敏感个人信息”时，个人信息保护法第二十八条没有进入前50；指定其object_id=912后能返回该条。查询“数据分类分级保护制度”也没有在前5条命中数据安全法第二十一条。本地向量与词法融合应改进相关性判断，不能以固定分数0.45作为高相关证明。
4. **无关查询可返回伪相关内容。** `zxqv987654_no_matching_corpus`在OWASP和法规各返回5个片段；中文无关探针“火星量子香蕉税法”返回空。这说明当前本地向量阈值不能稳定识别无答案问题。
5. **学习助手没有召回新OWASP文档。** `SafeKnowledgeRetrievalService`默认只允许knowledge_concept、article、resource、legal_clause，排除document。本次管理员和学生两种身份查询“SQL injection”，只召回旧文章/资源，没有新OWASP。internal文档不能直接开放给学生，应通过现有教学审核、课程授权或明确的教师文档接入流程处理。
6. **资料浏览列表和详情接口缺失。** 前端实际调用 `/api/legal-kb/library/` 与 `/api/legal-kb/library/document/208/`，教师请求均返回404；现有法规documents接口返回200。前端模拟接口测试通过并不表示真实目录接口可用。

权限实测通过：管理员和教师能读取internal OWASP，学生和匿名用户不能读取；法规检索API管理员/教师返回200，学生/匿名返回403；教师的include_raw请求不会暴露原始结果。这里是所测路径的结果，不代表全部平台权限已审计。

上述候选逻辑、助手来源列表、目录路由和分片代码在检查点 `020786a` 到当前提交之间没有改动。资料规模增长让原有候选上限成为实际遗漏因素；不能把全部扩展测试失败都归因于此次导入。

## 回归测试

- 核心后端46项全部通过：corpus_import、原法规服务、RAG入库、模块接入、学习上下文保留。覆盖文件完整性、来源元数据、幂等、失败回滚、权限和检索行为。
- 扩展后端运行114项，报告71次失败、54次错误、3项跳过。失败/错误包含子用例，影响33个不同测试用例，不能把71与54相加当作失败用例数。集中于目录API不存在（404）、旧测试引用不存在的EmbeddingUnavailableError、旧分片overlap参数和local供应器名称，以及分片长度/边界契约。
- 前端定向95项：93项通过，2项失败，均为教师/管理员资料入口名称渲染断言。
- PostgreSQL ANN路径与一个可选分片依赖路径被跳过；没有将跳过项视为通过。核心46项与扩展后端重叠，不累加为独立用例总数。

## 证据与复现

- [逐查询结果和指标](../artifacts/knowledge-retrieval-evaluation.json)
- [回归统计及失败用例](../artifacts/knowledge-retrieval-regression.json)
- [实际数据评测脚本](../backend/scripts/evaluate_merged_knowledge.py)
- 本地完整日志：`artifacts/knowledge-retrieval-backend.log`、`artifacts/knowledge-retrieval-core.log`、`artifacts/knowledge-retrieval-frontend.log`、`artifacts/knowledge-retrieval-evaluation.log`。日志受现有.gitignore规则排除。

在backend目录运行实际数据评测：

```powershell
python scripts/evaluate_merged_knowledge.py --baseline ../../database/db.sqlite3.before-knowledge-merge-20261112-012356
```

评测脚本退出0表示完成诊断和报告生成，不表示检索质量通过验收。另一个环境可用 `--database <SQLite路径>` 指定实际数据库，省略 `--baseline` 不作备份库存比较。

在backend目录运行回归，使用本次专用的非生产框架密钥：

```powershell
$env:SECRET_KEY='knowledge-retrieval-test-only-framework-key-20261112'
$env:DATABASE_BACKEND='sqlite'
$env:PYTHONUTF8='1'
python manage.py test legal_kb.test_corpus_import legal_kb.tests.LegalKbServiceTests rag_ingestion.tests ctf_backend.test_module_integration agent_runtime.tests.LearningRetrievalSemanticTests --noinput --verbosity 2
python manage.py test legal_kb.test_corpus_import legal_kb.tests legal_kb.tests_browse legal_kb.tests_chunking_round2 legal_kb.tests_platform_chunking rag_ingestion.tests rag_ingestion.tests_chunking ctf_backend.test_module_integration agent_runtime.tests.LearningRetrievalSemanticTests --noinput --verbosity 2
```

在frontend目录运行：

```powershell
node --test src/learningKnowledge/libraryController.test.js src/learningKnowledge/libraryPage.test.js src/learningKnowledge/conceptSource.test.js src/learningKnowledge/requestGeneration.test.js src/shared/knowledge/teachingTransfer.test.js src/utils/tutorResources.test.mjs
```

本次仅新增评测脚本、报告和证据；没有修改业务检索、课程授权、模型配置或正式数据库。建议优先修复候选截断和目录接口，再改进相关性/无答案判断，最后验证经授权的新资料能进入助手上下文。
