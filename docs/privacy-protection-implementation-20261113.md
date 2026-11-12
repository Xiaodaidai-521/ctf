# 隐私与数据保护展示实施说明

日期：2026-11-13。

## 改动边界

本次接入用户可见的保护状态、说明页、自己的记忆管理和已授权的资源导出入口。复用 `ProtectedModel`、`FieldStorage`、资源与反馈附件的私有存储 owner、`UserMemoryStore.forget`、现有导出生成与下载链路。没有新增加密算法、数据库字段或迁移，没有修改现有部署配置、创建业务授权或迁移历史数据。

工作区原有知识库、检索、Windows 密钥权限等修改保持原样。本次在已有改动的 AI 视图和资源页面中追加保护状态接入，没有重置原文件。

保护标签表示查询时已核验的服务器存储状态。它不表示端到端加密，不替代对象访问权限，也不表示草稿、本机副本或外部模型服务具有相同的存储保护。

## 各模块接入

| 模块 | 实现与复用 | 边界 |
| --- | --- | --- |
| 公共说明页 | 新增 `/privacy`，展示保护对象、技术展开说明和公开能力状态 | 能力已配置仍需逐条核验；不公开管理策略、密钥和对象上下文 |
| 用户邮箱 | 现有用户序列化器追加邮箱存在标记、展示文本和字段保护状态；资料页展示标签 | 已隐藏邮箱不回填编辑框；空白、原值或脱敏值不作为新邮箱提交，避免覆盖原邮箱 |
| AI 对话 | 复用现有消息与会话接口；按整段历史聚合，发送后另行读取自己的保存状态 | 未保存输入不继承标签；空会话、混合历史和核验失败不显示完整加密成功；换账号时丢弃迟到结果 |
| AI 记忆 | 新增 `/profile/memories` 与自己的记忆列表、详情、删除接口；复用记忆存储服务删除 | 查询和删除均限定当前账号；不公开内部记忆键；删除需页面确认，已有会话分别保留 |
| 入学访谈 | 原回答接口与画像报告追加保护状态，报告另给已回答问题数量 | 成功提交后才更新本地答案与提示；问题数量不依赖前端读取被隐藏的原始访谈快照 |
| 考试答案 | 原答案序列化与提交响应追加状态，答题记录按全部答案聚合 | 不改变评分、考试流程和教师正确答案存储策略 |
| 法律分析 | 复用法律序列化器与工作台，分别展示原文、报告正文和人工备注状态 | 原报告导出仅修改状态、写审计，没有生成文件；现明确返回 `409 EXPORT_NOT_AVAILABLE` 并禁用按钮，不伪造导出完成 |
| 资源与反馈附件 | 在现有详情、预览与上传响应中追加主文件、封面或附件状态 | 先由原 owner 校验访问范围和元数据，再通过原只读下载回调认证存储内容；历史公开文件不声称已加密 |
| 受控资源导出 | 新增 `/profile/exports` 与当前账号有效授权的分页查询；复用原生成、下载接口 | 不自动登记来源、批准风险或授予导出权限；未配置时展示尚未开放，缺少授权时不可生成或下载 |

备份、题目正确答案、Flag 与 Canary 没有新增普通用户入口。备份管理界面、备份 age 状态接口和新的法律文件生成器均不在本次新增范围。

## 状态核验规则

- 字段返回 `encrypted / legacy / unknown / empty`，其中 `encrypted` 要求字段属于现有加密模型、对象已经保存、字段无待保存修改、原始列已清空，并且现有适配器能够认证解密。单凭 `sealed-v1` 或全局功能开关不足以显示成功。
- 整段会话与考试记录使用完整集合聚合；同时有加密与历史明文时为 `partial`，存在未知状态时保留待确认，空集合不显示成功。
- 私有文件必须通过已有 owner 的只读认证结果；封面和正文分别核验。状态查询不发布文件、不添加下载记录。
- 导出状态复用从既有下载校验中抽出的 `inspect_delivery`：校验当前授权、策略、报告证明、逻辑交付审计、密文认证和正文哈希。该方法不执行交付、配额操作或审计写入；真正下载仍执行原来的风险、配额、锁和审计复核。
- 导出页面只有同时满足真实生成状态、脱敏完成、服务器文件加密和允许下载时才展示两个完成提示。下载开始提示不声称网络交付已经完成。
- 新增自己的状态和列表接口使用 `Cache-Control: no-store`。分页参数不能指定其他账号，也不会把来源文档、密文或内部存储上下文交给前端。

现有加密实现包含 test/evaluation 的环境限制。本次没有解除限制，测试通过不表示真实部署已经启用或历史数据已经覆盖。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| 前端生产构建 `npm.cmd run build` | 通过；保留项目现有大 chunk 提示 |
| 后端隐私状态、导出读校验、导出流程、导出执行与法律模块 | 75 项全部通过；Django system check 无问题 |
| 前端隐私展示、邮箱提交、导出完成判定、AI 会话迟到响应、导航与路由专项测试 | 30 项全部通过 |
| 前端广泛回归 | 82 项中 75 项通过、7 项失败；下述失败在只读 Git 基线对照中同样出现 |
| 浏览器实际运行 | 8 项全部通过，页面脚本异常为 0；同时人工检查记忆页截图 |
| `git diff --check` | 通过 |

后端测试使用 `data_security.privacy_test_settings` 创建独立 SQLite 测试库，真实字段加密使用随机内存密钥。浏览器通过 Edge/Playwright 访问本地 Vite 与 Django，使用临时 SQLite、合成用户、合成记忆及随机内存密钥，没有连接现有业务数据库。浏览器验证了公共说明页、真实会话登录、加密与历史记忆的区别、确认删除并刷新、邮箱留空实际 PUT 不含邮箱且保留原保护状态、完整混合会话、受控导出未启用提示和手机宽度布局。浏览器没有在真实部署中执行文件导出；导出流程与状态的正反例由上述后端测试覆盖。

广泛前端检查的 7 个既有失败为：考试旧路由正则与保留 hash 的实现不一致、管理端 Challenges 与 Resources 两个样式契约、资源预览契约扫描到既有管理端直接 API 调用、个人资料中学习路径 ID 映射、分页提交记录读取、旧题目跳转路径。对照仅将被检查的既有前端源文件只读替换为 `git show HEAD:<path>` 内容；保留工作区原有 Resources 修改，不改变文件或导入的运行时模块。在覆盖这 7 项检查的 52 项基线测试中，同样为 45 项通过、7 项失败。本次没有扩展修复这些问题。

运行证据位于 `artifacts/privacy-backend-tests.log`、`privacy-targeted-frontend-tests.log`、`privacy-frontend-tests.log`、`privacy-frontend-baseline.log`、`privacy-build.log` 与 `privacy-browser-smoke.json`。页面截图为 `privacy-page-smoke.png`、`privacy-memory-smoke.png` 和 `privacy-export-smoke.png`。临时运行脚本、数据库和浏览器依赖位于系统临时目录，未加入项目依赖或修改项目启动配置。

## 重跑专项测试

后端需要项目已有依赖与可用的 `magic` 库，并在测试进程中提供随机 `SECRET_KEY`、`DEBUG=true`、`DATABASE_BACKEND=sqlite`；不要复用生产配置。

```powershell
python manage.py test data_security.tests.test_privacy_status data_security.tests.test_phase6_delivery_read data_security.tests.test_phase6_export_flow data_security.tests.test_phase6_export_execute legal.tests --settings=data_security.privacy_test_settings --noinput
```

前端在 `frontend` 目录运行：

```powershell
node --test src/shared/privacy/privacy.test.js src/learning/agent/session.test.js src/learning/agent/request.test.js src/shared/navigation/navigation.test.js src/router/integration.test.js
npm.cmd run build
```
