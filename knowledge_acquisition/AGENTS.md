# 知识库采集工作约定

- 用户明确要求：采集程序、知识库数据和业务代码隔离；只有用户明确宣布合并时才能合并。
- 本分支为 `codex/knowledge-base-collection`，使用独立 Git worktree。
- 改动限于 `knowledge_acquisition/` 和 `datasets/knowledge_base/`。不要修改 backend、frontend、主项目依赖或数据库。
- 不调用项目入库、向量化、课程登记、发布接口，不启动业务服务。
- 原始数据和下载缓存放在 `datasets/knowledge_base/raw/`，不提交 Git。
- 清洗后的候选数据放在 `datasets/knowledge_base/staged/`，允许提交当前采集分支；不得将候选数据标记为已人工审核或已发布。
- 保留来源、固定版本、采集时间、原始/清洗内容摘要、授权和变更说明。未知的原文发布日期和人工核验日期留空。
- 后续合并前先展示数据统计、来源许可和待处理事项，再按用户明确的合并指令执行。
