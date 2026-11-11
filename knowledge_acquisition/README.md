# 独立知识库采集

用户要求本工作与业务开发隔离，只有用户明确宣布合并时才合并。

- 分支：`codex/knowledge-base-collection`
- 独立目录：`D:\aaa10\16015478源码\project-code-kb-collection`
- 业务项目继续使用原目录与 `main`；原目录的未提交修改不带入本分支。
- 本工具只下载公开文档并生成离线候选数据，不连接 Django、数据库、向量库或业务接口。

## 目录

```text
knowledge_acquisition/            # 采集工具、配置、测试和本说明
datasets/knowledge_base/
  raw/                           # 原始 Markdown、许可、版本清单和 ZIP 缓存；Git 忽略
  staged/                        # 清洗候选数据；仅提交采集分支
    markdown/                    # 可逐篇查看的正文
    documents.jsonl              # 正文及来源、版本、摘要、许可等元数据
    licenses/                    # 上游原始许可文本
    sources.lock.json            # 固定提交、ZIP 和许可摘要、采集时间
    quality_report.json          # 数量、拒收项、重复项和待审核事项
  .working/                      # 临时结果和上一次候选包；Git 忽略
```

`staged` 是待审核资料，所有条目保持 `review_status=pending`、`published=false`。
不生成 embeddings，不创建课程材料，不替用户审核或发布。

## 运行

仅需要 Python 3.11+，使用标准库，不安装主项目依赖。在本 worktree 根目录执行：

```powershell
python knowledge_acquisition/pipeline.py run
python knowledge_acquisition/pipeline.py verify
python -m unittest discover -s knowledge_acquisition/tests -v
```

也可以分步运行：

```powershell
python knowledge_acquisition/pipeline.py collect  # 需要联网；已有 ZIP 缓存会复用
python knowledge_acquisition/pipeline.py clean    # 使用原始快照，离线清洗
```

所有默认路径均由脚本位置确定，在其他目录运行也不会写进主项目。
`--data-dir` 可指定其他离线数据目录。重新清洗时将旧候选包保存在被忽略的 `.working/` 下。
修改固定提交或元数据后需重新 `collect`，再 `clean`；脚本不会静默跟随 master 更新。

## 第一批来源与清洗范围

1. OWASP WSTG **v4.2**：固定 `dd33419e10edb22b78d89325a6c2aad9f184e3a2`，采集 `document/` 下非 README 的 Markdown，避免目录导航页混入。
2. OWASP Cheat Sheet Series：固定 `9c87d0a0e9411de028b9d7eb853872082d6d3382`，采集 `cheatsheets/` Markdown。

两份来源的文档使用 **CC BY-SA 4.0**。保留上游许可和署名；资料改编须标注修改并遵循相同许可，第三方代码和示例按原文说明核对。许可针对采集资料；不改变业务代码的许可。

清洗采用保守规则：UTF-8/BOM 和换行规范化，移除开头 front matter，合并正文多余空行，把可识别的相对 Markdown 链接改为固定版本的 GitHub 链接，按正文摘要去重并过滤过短/二进制内容及已废弃、移除、跳转的占位页。扩展后的链接长度不计入正文最低长度。
保留代码块、缩进代码、HTML 安全示例、表格和正文，不自动删除可能是教学载荷的 HTML，也不自动翻译或改写技术结论。
没有下载图片，图片链接回指上游固定版本；本包是文本候选知识库，暂不提供离线图片。

`snapshot_date` 是固定仓库提交日期，不能当作每篇文章的发布日期。
未知的 `source_date` 和人工 `verified_at` 留空，后续登记课程材料前由审核人补充。
JSONL 是独立交换格式，尚未绑定课程任务，不能直接当成现有 API 的登记请求。
数据目录的 `.gitattributes` 固定正文和清单为 LF、保留许可原始字节，避免 Windows 换行转换破坏摘要校验。

## 下一批数据

中国法规建议从国家法律法规数据库、全国人大、国家网信办和中国政府网的官方原文补充，单独保存正文、条款、生效日期及版本。
当前实现只支持上述 GitHub Markdown 来源，尚未适配法规网站。法规需另外配置和实现正文解析，避免把文章发布日期误作法规生效日期。

## 合并边界

本阶段只在采集分支提交 `knowledge_acquisition/` 和 `datasets/knowledge_base/`。
用户宣布合并后，先按最新主分支核对候选包和课程元数据，再执行合并；数据入库、课程登记和发布应在对应授权范围内分别执行。
当前没有自动合并、自动入库、自动推送或定时任务。
