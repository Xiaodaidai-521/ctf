# 知识库资料合并与入库记录

用户于2026-11-12明确授权：合并采集资料、删除采集程序、提交当前项目状态。

## 已完成

- 原有未提交的模块恢复和前端改动已保存为检查点提交 `020786a`。
- 独立采集分支已合并到 `main`，清洗后的资料位于 `backend/data/knowledge_corpus/`。
- `knowledge_acquisition/` 中的采集程序、配置、专用依赖和测试已从当前项目移除；不再自动采集。
- 导入现有知识库：246篇OWASP文档、7份中文法规资料，共253份、4106个索引片段。
- 复用并更新5份既有法规记录，新增2份配套法规；7份法规共393条，分条正文与采集原文逐条一致。
- 现有SQLite数据库在更新结构前完成一致性备份；75项待执行迁移已应用，当前没有待执行迁移。
- 重复运行导入跳过全部253份，索引记录ID和数量不变。
- 管理员实际检索“SQL injection”和“个人信息”均返回结果。

入库使用明确的128维本地确定性索引，未调用远程向量服务或改变模型配置。
OWASP资料采用internal可见性，已有文档的可见性不被放宽；没有伪造课程授权、审核或发布记录。
法律、条款和通用文档继续使用现有知识库数据表及共享索引，不创建第二套检索库。

## 数据位置与复现

- 中文法规阅读目录：`backend/data/knowledge_corpus/chinese_laws/阅读目录.md`
- OWASP正文：`backend/data/knowledge_corpus/owasp/markdown/`
- 来源、许可和审计：各资料目录及`backend/data/knowledge_corpus/audit/`
- 离线导入：`python manage.py import_knowledge_corpus --actor <已有管理员ID> --local-index`
- 仅验证文件：`python manage.py import_knowledge_corpus --validate-only`
- 实际入库映射：`artifacts/knowledge-import.json`
- 完整性、重复执行和检索检查：`artifacts/knowledge-integration-verification.json`

导入命令是本地资料到现有知识库的适配入口，不包含网页爬取或官方资料下载。
现有数据库包含用户和业务记录，按仓库约定不提交Git；保留资料包和幂等导入入口，便于其他环境复现。

## 验证结果及已知问题

- Django系统检查通过；导入、权限、回滚、幂等、RAG及模块接入等38项后端测试通过。
- 法规知识库服务的8项测试单独复核通过，覆盖入库、重新建索引、失败记录及检索等既有行为。
- 追加后端回归18项中9项通过、4项失败、5项报错。失败与报错集中在既有`rag_ingestion.tests_write_permissions`：测试引用已不存在的`UploadIngestionService`名称，教师/非staff管理员上传预期与当前`IsAdminUser`权限不一致，以及使用当前不支持的`local`供应器名称。这些上传视图、旧命令及测试没有因本次资料合并而修改。
- 前端生产构建通过。
- 定向前端测试52项中48项通过、4项失败。资料合并与入库未改变检查点之后的前端源码，这4项失败属于当前已有界面状态：
  - 教师、管理员资料入口渲染断言各1项（`learningKnowledge/libraryPage.test.js`）。
  - 学习路径/模块路由和个人画像深链源码契约各1项（`shared/navigation/phase2Destinations.test.js`）。

上述前端和旧上传权限测试问题已如实保留，未通过修改期望、放宽权限或回滚用户界面改动掩盖。
英文翻译、课程筛选与人工内容审核仍使用现有教学流程；部分数据出境配套办法没有采集到，详见原完整性报告。
