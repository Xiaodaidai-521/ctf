# 知识库检索原因分析与逐点修复（2026-11-12）

修复前，资料入库完整，但21个实际查询按来源筛选仅5/21命中目标，不筛选仅3/21命中。问题发生在候选选取、排序和调用接入，不能以“返回内容非空”证明调取效果正常。

修复后，同一批21个查询各运行筛选/不筛选两种模式，共42次，全部在前5条命中目标。管理员和教师可通过资料目录及助手调取新OWASP文档；学生仍不获得内部文档权限。以下结果仅针对这批诊断样本及本次SQLite运行环境，不是全库准确率或远程模型质量结论。

## 原因及修正

| 原因 | 实际修正 | 验证 |
| --- | --- | --- |
| 按入库顺序先截断1000片段，再进行排序 | 分批读取全部授权候选，省略向量载荷后统一排名；先校验片段正文哈希，返回前再次检查权限 | 4205个候选全部参与；新增测试覆盖1001个早期片段后面的文档和法规 |
| 字符向量不是语义相似度，固定关键词分数也区分不了关键条款 | SQLite/便携路径改用BM25词频、稀有词权重、查询覆盖、真实来源标题和法条首段；输出标为lexical | 敏感个人信息定义条款进入前5；原有法规自然语言问句恢复通过 |
| 重复片段挤占结果、缺少跨语言术语匹配 | 多来源查询限制同一来源连续占用；按文档ID查询可返回完整top_k；增加明确的SQL/XSS/CSRF/SSRF等术语等价组 | OWASP文档13/13命中；中文跨站脚本查询召回英文原资料 |
| 无答案仍按字符向量返回伪相关内容 | 没有词法证据则不返回；低覆盖且无明确主题词的片段被过滤；问句按提问词及已知术语边界分词 | 两个无答案探针在两种来源筛选下共4次均返回空；补充“个人信息+无关词”负例 |
| 助手未接入document且未传递调用者 | 传递服务端认证用户；仅教师/管理员可在现有实时可见性约束下召回文档；调用者的显式来源限制继续生效 | 助手的管理员SQL查询返回新文档；学生/匿名、staff-only对教师、失败和已登记课程文档均不越过限制 |
| 目录实现存在但路由缺失，资源页入口缺失 | 挂载已有只读列表/详情路由；补回角色对应入口；读取并校验来源URL | 教师列表与文档208详情由404恢复200；前端95/95通过 |
| 分片实现丢失重叠参数、长法条边界、标题元数据 | 恢复800/100教学、1200/160法规窗口，句末优先、尾片段合并、稳定条号/子片段键；标题解析忽略代码围栏，保留C#标题 | 分片重建原文、句末率、长法条身份、标题和错误配置回归通过 |

本地字符向量仍保留在原有索引中作为历史存储；新检索不把它的碰撞分数作为内容相关性依据，也不标成远程语义模型结果。PostgreSQL已有远程ANN分支没有作为本次效果评测对象。

## 同批查询比较

| 查询类型/筛选 | 修复前前5条命中 | 修复后前5条命中 |
| --- | --- | --- |
| OWASP，不筛选 | 3/13 | 13/13 |
| OWASP，document | 3/13 | 13/13 |
| 法规，不筛选 | 0/8 | 8/8 |
| 法规，legal_clause | 2/8 | 8/8 |

命中判定仍使用修复前预先指定的文档/法条，没有修改样本目标或放宽“前5条命中”的标准。原始记录保留在 [修复前逐查询结果](../artifacts/knowledge-retrieval-evaluation.json)，修复后结果在 [复测逐查询结果](../artifacts/knowledge-retrieval-after.json)。

扫描全部候选增加首次调用成本：本次首次查询约2秒，之后文档或混合查询中位延迟约0.2—0.3秒，单独法规查询约0.04秒。词项缓存仅缓存词频特征；每次检索仍重新查询并检查授权，不缓存用户可见的候选或结果。数据规模继续增长时，需要进一步优化持久化词法索引和候选选择，不能恢复按入库顺序截断。

## 测试和边界

最终后端验证集覆盖新召回回归、入库、法规服务/API、目录、分片、模块接入、学习上下文、流式问答和内容保护；完整用例、通过/跳过数见 [验证统计](../artifacts/knowledge-retrieval-fix-verification.json)。前端定向95项全部通过，生产构建通过。

新增的12项召回回归包括：超过1000片段、无答案、常见词掩盖无关查询、结果多样性、双语术语、权限/失败状态、来源过滤不扩权、登记课程文档隔离、正文哈希、排名中途撤回、助手调用者传递和真实目录API。

调整两处已过期测试协议：长法条测试明确使用当前本地配置，替换已禁用的local供应器名称；受保护供应器测试按既有vision接口断言文本对象和1024维，而不是旧字符串数组。流式测试桩接受新增的调用者参数。没有通过删除失败断言或改动目标资料使测试通过。

本轮有3项跳过：2项需要PostgreSQL ANN，1项需要未安装的可选langchain分片依赖。旧 `tests_indexing`、`tests_platform_chunking` 仍依赖已移除的EmbeddingUnavailableError、远程客户端和向量存储接口，未计入本次通过集；需要另行按现有受保护端口迁移。这与已修复的当前SQLite检索、目录和分片路径是不同的验证范围。

实际资料评测使用只读原库的一致性临时副本。253份原资料、393条法规正文、4106个新增索引片段的存量完整性校验仍通过，原数据库和模型配置未改动。新分片规则用于后续入库/显式重建，本次没有批量改写现有索引、课程授权或发布状态。

## 复现

在backend目录、同一项目环境运行：

```powershell
python scripts/evaluate_merged_knowledge.py --output ../artifacts/knowledge-retrieval-after.json
```

回归测试使用隔离测试数据库：

```powershell
$env:SECRET_KEY='knowledge-retrieval-test-only-framework-key-20261112'
$env:DATABASE_BACKEND='sqlite'
$env:PYTHONUTF8='1'
python manage.py test legal_kb.test_retrieval_regressions legal_kb.test_corpus_import legal_kb.tests legal_kb.tests_browse legal_kb.tests_chunking_round2 rag_ingestion.tests rag_ingestion.tests_chunking ctf_backend.test_module_integration agent_runtime.tests.LearningRetrievalSemanticTests ai_assistant.test_main_chain ai_assistant.test_phase3_content ai_assistant.tests.KnowledgeContextSemanticFusionTests --noinput --verbosity 2
```

在frontend目录运行：

```powershell
node --test src/learningKnowledge/libraryController.test.js src/learningKnowledge/libraryPage.test.js src/learningKnowledge/conceptSource.test.js src/learningKnowledge/requestGeneration.test.js src/shared/knowledge/teachingTransfer.test.js src/utils/tutorResources.test.mjs
npm run build
```

完整日志保存为 `artifacts/knowledge-retrieval-fix-backend.log`、`knowledge-retrieval-fix-frontend.log`、`knowledge-retrieval-fix-build.log` 和 `knowledge-retrieval-after.log`，沿用现有日志忽略规则。
