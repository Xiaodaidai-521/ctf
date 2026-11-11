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
  staged_legal/                  # 中文法规候选包，与 OWASP 分开维护
    阅读目录.md                  # 中文名称、日期和内容简介；从这里开始查看
    markdown/                    # 三部法律及配套法规，按中文名称保存
    documents.jsonl              # 全文、版本、日期、来源、摘要及复用依据
    clauses.jsonl                # 分条正文，保留原条号、项号和出处
    licenses/                    # 官方法律文本的复用依据说明
    sources.lock.json            # 固定官方版本及原始附件/元数据摘要
    quality_report.json          # 完整性统计及待采集资料
  .working/                      # 临时结果和上一次候选包；Git 忽略
```

`staged` 是待审核资料，所有条目保持 `review_status=pending`、`published=false`。
不生成 embeddings，不创建课程材料，不替用户审核或发布。

## 运行

需要 Python 3.11+。OWASP 清洗与审计使用本工具自己的 `markdown-it-py` 依赖，法规 DOCX 提取使用标准库；不安装主项目依赖。可在 `knowledge_acquisition/.venv/` 的独立虚拟环境安装。在本 worktree 根目录执行：

```powershell
python -m pip install -r knowledge_acquisition/requirements.txt
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

## 中文法规采集

中文法规使用独立的 `legal_pipeline.py`，从国家法律法规数据库公开 API 获取元数据和官方 DOCX 附件，使用标准库提取原文段落，单独写入 `staged_legal/`。

```powershell
python -X utf8 knowledge_acquisition/legal_pipeline.py run
python -X utf8 knowledge_acquisition/legal_pipeline.py verify
```

也支持 `collect` 和 `clean` 分步执行。原始附件、官方元数据和清单存放在被 Git 忽略的 `raw/chinese_laws/` 中；`clean` 可离线重建数据包。
两个采集程序各自维护自己的数据包，运行 OWASP 清洗不会覆盖中文法规。

`legal_sources.json` 固定各份法规的官方版本 ID、发布日期、生效日期和预期条数。
采集时核对官方标题、日期和现行性状态；清洗时检查完整条号连续性和原始摘要，遇到版本变化或缺漏即停止，不把失效版本悄悄标为现行。
`version_checked_at` 记录元数据获取时间，后续重新采集仍需检查是否存在更新版本。

2026-11-12 这一批共 **7 份、393 条**：网络安全法（2025修正版）、数据安全法、个人信息保护法、网络数据安全管理条例、关键信息基础设施安全保护条例、未成年人网络保护条例，以及民法典第1032—1039条节选。
网络安全法的本版本生效日期按官方元数据记录为 **2026-01-01**，原文末条保留的 **2017-06-01** 不覆盖修订版本日期。
民法典原始完整附件另存 raw，候选包只包含明确标注的隐私权和个人信息保护条款。

正式法律及行政法规正文的复用依据与 OWASP 资料分开记录，依据《著作权法》第五条第一项；不对政府网站整体、新闻解读或图片作同样声明。
正文保持中文原文，简介是单独整理的阅读提示，所有文档和条款仍为 `review_status=pending`、`published=false`，`verified_at` 留空。
官方临时签名下载链接不会写入候选包，仅保留固定法规页面、附件路径和内容摘要。

国家网信办的部分数据出境、标准合同和合规审计页面本次返回 HTTP 403，尚未采集；候选链接与待核验事项单独列在阅读目录及质量报告中，不用新闻摘要替代法规原文。

## 合并边界

本阶段只在采集分支提交 `knowledge_acquisition/` 和 `datasets/knowledge_base/`。
用户宣布合并后，先按最新主分支核对候选包和课程元数据，再执行合并；数据入库、课程登记和发布应在对应授权范围内分别执行。
当前没有自动合并、自动入库、自动推送或定时任务。

## 全量清洗审计

```powershell
python -X utf8 knowledge_acquisition/audit.py
```

报告保存在 `datasets/knowledge_base/audit/`。审计与清洗分开执行，直接对照原始仓库 ZIP 和官方 DOCX，而非仅对比本次生成的摘要。
检查正文与代码/HTML示例是否改变、所有法规条款与原始XML是否逐条相同、固定仓库引用的文件是否存在，以及日期元数据、乱码、残留相对链接和图片链接格式。
可通过 `--baseline-ref <采集分支提交>` 对比之前的数据包；本次修复审计使用 `e696884` 作为基准。

本次修正8个正文链接、117个图片链接，以及三部核心法律中的重复目录和章/节层级。按CommonMark结构识别代码块、缩进列表和行内代码，保留来源中的技术示例。
源资料明确标注的历史文档和XSS样例控制字符单独记录，不因匹配到“deprecated”或控制字符而自动删除有意义的教学内容。
报告只说明清洗和来源一致性结果；英文翻译、课程筛选、外部网页现行性和技术结论人工审校仍待完成。

Windows阅读器占用目录时，生成程序保留旧包备份后逐文件更新，完成后重新校验；不要求关闭整个知识库目录。
