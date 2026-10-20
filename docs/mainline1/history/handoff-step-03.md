# 主线一交接

更新时间：2026-10-13。实际交接目录：`docs/mainline1/`，继续复用。仓库：`project-code`，分支 `feature/Sensitive-data-recognition`，基线 `f4ac82caf32a4112c047cdb8848cab135acbb3c6`。

本轮只审查并补齐第2、3步，**已停止，未进入第4步**。没有改动既有业务代码、生产配置、公共接口或业务数据库；没有新增依赖或真实模型调用。当前所有新增代码和文档仍未跟踪、未提交。

| step / status | mission 与证据 |
|---|---|
| 01 / complete | [源码核查](step-01.md)保持原样；原始交接保存在[历史副本](history/handoff-step-01.md)，不作为当前状态 |
| 02 / complete | [设计记录](step-02.md)、[设计说明](design.md)、[Schema](contracts/schema.json)、[字段目录](contracts/catalog.json)、[样例](contracts/examples.json)、[验收清单](acceptance.md)；14个公共对象仍 **Proposed**，不是Approved |
| 03 / partial | [实现记录](step-03.md)：内部解析、定位、PostgreSQL持久化、单次worker骨架已完成；真实资产owner/生产鉴权与部署接入仍缺前置 |

## artifacts / findings / verification

- [内部组件及运行说明](../../backend/mainline1/README.md)：真实CSV/XLSX解析、固定版本读取端口、范围规范化、Unicode码点及可逆NFKC映射。映射不可靠时拒绝字符级操作；公共v1仍只允许identity。
- [持久化仓储](../../backend/mainline1/repository.py)、[迁移](../../backend/mainline1/migrations/0001_initial.py)、[worker](../../backend/mainline1/worker.py)：复用现有Django事务/行锁/令牌机制，独立ParseRun/ParseAttempt/ParsedArtifact；取消/成功与产物原子提交。没有新建跨模块资产管理系统或Web后台线程。
- [内部验证证据](step-03-verification.json)：**Passed**，41项解析/状态机测试、18个Python文件AST；29个设计场景/396对象校验（草案检查单独记录，不算业务测试）。
- [PostgreSQL验证证据](step-03-postgres-verification.json)：**Passed**，13项真实数据库测试，含多连接竞态、独立Python进程读取、过期恢复、受限重试、旧尝试拒绝、产物写入失败回滚；Django检查、迁移一致性及空隔离库正反迁移通过。最终测试集群已停止并清理。
- [收尾核查](review-verification.json)：原三个提示词、第1步/历史交接、公共Schema/样例摘要保持不变；已测试源码摘要一致，阶段记录必需字段、JSON和链接目标检查通过，tracked/index diff为空。
- 私有资产owner使用合成BytesIO替身；PostgreSQL和解析器是实际实现。部署鉴权/TOCTOU/生产CPU、RSS和硬截止 **Untested/Blocked**；规则、语义、联合风险未执行。解析任务成功只表示`parsed_asset`，检测三层保持`not_run`，不等于扫描完成、复核完成或外发授权。

上述内部能力：Implemented / Verified / High / Passed（能力/证据/置信度/测试四轴独立）。生产集成：Partial / Verified / High / Blocked；不存在真实语义效果证据。

## approved_decisions

- 来源：用户本轮“审查第二步第三步任务，将确实未完成的部分补上”及随后“continue”。授权只覆盖第2/3步内部实现、适配、合成验证和交接，不自动推进第4步。
- 根据完整提示词B4，编写迁移、全新合成隔离库验证与既有业务库执行分别判断。本轮前两者属于已授权的内部补齐；**未执行或批准业务库迁移**。
- 公共契约、生产部署/注册、真实模型/原文外发、依赖新增、生产删除/保留策略均不因本轮验证获批。

## changes / judgment_changes

动机：原任务控制只有纯状态机和内存替身，缺持久化与真实并发证据；HANDOFF停在第1步，step-03未落盘。现已补上仓储/迁移/原子产物/受管执行单元、NFKC逆映射及完整交接，并修正把内部迁移和隔离测试全部待批准的判断。依据为本轮指令、规范B4和新增验证证据。

范围：仅`backend/mainline1/`、`docs/mainline1/`。复用已有Django、psycopg2、openpyxl与本机PostgreSQL；不安装Celery/Redis等依赖。不使用RAG自动embedding链路，也不拿SQLite/内存测试代替PostgreSQL保证。重要中间失败及修正见step-02/03的verification与judgment_changes。

回滚：仅按本任务文件清单撤回增量，保留用户原提示词、第1步历史和其他任务修改；不用git reset/clean。不能直接恢复旧HANDOFF丢弃当前记录。业务库未改变；空测试库逆迁移通过不意味着含真实数据的表可直接删除。以后生产启用前须另审查停任务/引用/保留和迁移方案。

## open_questions / next_step_constraints

| 待决事项 | 具体选项与取舍 | 阻塞范围 |
|---|---|---|
| D02：真实资产由谁提供？ | 推荐提供既有私有资产服务的正式契约/适配位置；若选择扩展resources，则需额外明确其公开审核语义、域ACL与不可变版本改造。主线一不另建跨模块资产系统 | 真实私有读取/权限验证；公共ParsedAsset/TaskReference发布需相关owner确认 |
| D03：是否启用生产持久化？ | 推荐先维持隔离验证；生产启用需明确环境、迁移窗口、私有数据库角色、worker进程限制和保留策略 | 仅生产注册/迁移/部署；内部代码和隔离测试无需再批准 |
| D01/D04/D05：交付/模型/保留策略 | [设计§12](design.md)给出选项；推荐backend_only、模型关闭。minimal_ui增加页面验收；真实模型必须有model/数据路径/金额预算；保留期不沿用开发候选值自动执行 | 后续第5/8步对应能力，不影响本轮独立底座验证 |

下一步只能在用户另行指令后开展。第4步仍需分类字典/等级政策和已授权输入契约；可消费本轮已验证内部解析产物，不能直接把内部DTO当公共响应。不得绕过未知owner/权限、修改其他主线决策、执行公式、生成公开文件或把解析成功写成扫描成功。

本机清理附记：首轮已停止的临时目录`mainline1-synthetic-pg-633pg7hs`递归清理被自动审批拒绝，原因仅为`blocked by policy`；已保留且未绕过删除。后续验证脚本的临时集群已停止并清理。残留是新建的合成测试目录，不含业务原文或凭据。
