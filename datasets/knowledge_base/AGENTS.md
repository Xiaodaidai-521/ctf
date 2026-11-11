# 候选知识库约定

- 用户要求采集工作和业务代码隔离，只有用户明确宣布合并时才允许合并。
- 遵守 `knowledge_acquisition/AGENTS.md` 中的采集工作约定。
- 原始数据仅存放在 Git 忽略的 `raw/` 中；候选包在 `staged/` 中。
- 不导入数据库、不生成向量、不自动登记课程或发布。
- 通过 `python knowledge_acquisition/pipeline.py clean` 生成候选包，不手工修改已计算摘要的正文。
- 每次修改候选包后执行 `python knowledge_acquisition/pipeline.py verify`。
