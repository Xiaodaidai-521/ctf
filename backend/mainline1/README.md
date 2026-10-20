# 第3步内部组件

本目录提供可选 Django app；未修改生产 INSTALLED_APPS，不提供公共 HTTP 接口，不连接业务数据库或模型。
位置及任务语义是可独立验证的内部实现，不代表 `docs/mainline1/contracts/` 的公共 Proposed 契约已获批准。

从 `backend/` 执行定向检查：

```powershell
python -B -m unittest discover -s mainline1/tests -v
```

`parsing.parse_table(bytes, AssetRef, config=ParserConfig(), limits=Limits(), scope=None)`
返回不可变 `ParseResult`。先校验原始字节摘要/大小/状态，再做格式及资源检查。
`scope=None` 表示在受控内部解析结构后展开实际范围；输出 Scope 始终显式。
固定行列一基、字符零基 Unicode 码点半开区间；CSV 行号是逻辑记录，表头计数但默认不检测。
`Cell.source_span()` 输入规范化文本的码点区间，返回原文码点区间。默认 identity-v1。
内部可显式选择 nfkc-mapped-v1，组合序列和展开字符保持完整；无法证明逆映射（如跨组 Hangul 组合）
时 location_reliable=False 并拒绝字符操作，不允许切开连字的部分展开。原文始终保留，规范化后也检查格长上限。
运行快照保存解析器及 Unicode 数据版本；版本不一致的重试失败关闭。
公共 Proposed v1 契约仍只允许 identity；该内部扩展不自动成为公共契约。

XLSX 使用已有 openpyxl，前置检查 ZIP 声明/实际解压字节、条目、XML、坐标和合并区域。
保留原始数字标量文本及 number_format，不按显示格式补前导零；空字符串与缺失格不同。
公式只输出公式文本，缓存仅标记 `missing` / `present_unverified`，不执行、不推断缓存新鲜度。
隐藏内容由显式配置决定；合并非锚点给出别名排除，范围遗漏锚点拒绝。
批注、超链接目标、文本框、图片、公式缓存值明确不检测；未处理的复杂公式、错误值、宏、加密等显式拒绝。

`ParseResult.coverage_json` 中 parse 分母为配置/选区内的有效单元格，表头/隐藏/合并别名逐项列入
`excluded_locations`；`processed_locations` 可追溯实际格。零分母比例为 null。
rule/semantic/combination 始终 `not_run`，不把 parse 完成称为 scan 完成。
失败/取消抛出仅含稳定原因码的 InputError，不返回假成功或假完整覆盖。
失败时尚不提供部分解析产物，调用者必须记录失败而不能替换为空成功。

`read_private()` 消费资产所有者的 `PrivateSource.open_version()` 端口。
真实 owner 适配器必须逐次鉴权并提供稳定只读快照；本组件不接受路径/URL，也不另建资产系统。
本轮仅有合成 BytesIO 测试替身；真实文件权限、部署私有存储和 TOCTOU 保证未验证。
`ParseResult` 内含授权内部原文，禁止将 asdict/structure/coverage 批量写通用日志或公开接口。

`tasks.ParseTasks` 实现逻辑运行、独立尝试、幂等、CAS、取消、租约到期、受限重试、进度和旧尝试拒绝。
通过 `RunRepository` 的 create_unique/get/compare_and_swap 持久化端口工作；没有默认内存仓储或失败时降级。
`tests.RepositoryDouble` **仅测试替身**，不是持久化后端。
唯一键包含 domain/environment/evaluation/principal/idempotency_key；重试保留快照且不覆盖旧尝试。
任务成功的 result_kind 仅 `parsed_asset`，detection_status=`not_run`、scan_quality=`unavailable`。
`repository.DjangoRunRepository` 使用当前项目的 Django ORM/transaction/select_for_update 模式，
通过数据库唯一约束创建运行，父行锁保证 run/attempt 一致读取及 CAS 原子更新。
`models.py`/`migrations/0001_initial.py` 仅三个主线一解析领域表，未复用或修改 RAG/AgentRun 的领域语义。
`worker.execute_one()` 串行读取固定快照、解析并原子保存私有 ParsedArtifact 与成功状态。
发布必须走 repository.publish；不得直接以 ParseTasks.finish(private_ref) 伪造真实产物存在。
产物在私有数据库表中，无 MEDIA_URL/admin/HTTP 暴露；原资产仍由外部 owner 管理。
管理命令 run_parse_worker 每次恢复最多100个过期租约并处理一个排队任务，由外部进程管理器调度。
缺少 MAINLINE1_PRIVATE_SOURCE_FACTORY 时拒绝运行。配置值为受信任 settings 中的 factory dotted path，
factory 返回实现逐次鉴权的 PrivateSource；不得由客户端提供。过期尝试先失败，显式 retry 才排队新尝试。
扫描识别未启动；这个命令只产出 parsed_asset。没有创建 Web 后台线程或新队列依赖。
调用者须经授权后集成，不能把客户端自报 principal/domain 直接传入。

限制：截止时间是协作式检查，不会中断正在运行的 openpyxl/XML 单次调用；ZIP/网格上限限制输入规模，
不等于强制 RSS/CPU 隔离。生产需受管进程硬限制。解析读取整个受限文件，scope 不使 ZIP/CSV 成为随机访问源。
CSV 还受 Python csv 的进程默认 field_size_limit 约束，本模块不修改这一全局状态。
PostgreSQL 隔离测试已验证持久化、独立进程读取、真实多连接并发、取消/发布竞态和旧尝试 fencing。
重试次数和每次解析限制固定在快照中；没有模型费用。未验证生产调度/强制 CPU、RSS、总墙钟预算。
协作式读取/解析各用 max_seconds，租约为二者之和加30秒收尾；这不是设计中生产总300秒的硬保证。

验证命令（backend/）：

```powershell
python -B mainline1/tests/run_isolated_postgres.py
```

脚本只使用已安装 PostgreSQL 16，新建临时集群，绑定127.0.0.1临时端口并验证 data_directory，
以独立 test_settings 运行 system check、迁移漂移检查、真实事务测试、空库迁移及反向迁移，然后停止并清理。
不加载 .env/生产 settings；只有合成 CSV/XLSX、测试主体和本地数据库连接。不存在真实模型调用。
Windows 启动进程输出使用文件以避免继承管道挂起。证据输出 docs/mainline1/step-03-postgres-verification.json。

回滚：本轮没有业务库表或已注册入口；仅按变更清单撤回 mainline1 新文件和交接增量，保留原提示词/其他任务修改。
以后若正式启用，先停 worker 和新任务并保留被引用产物；不能直接 reverse/drop 含业务数据的表。


## 第4步内部规则基线

新增 classification.load_baseline()/BusinessContext.create() 与 rules.scan_rules()；版本和完整调用边界见
[rule-baseline-v1](../../docs/mainline1/rule-baseline-v1.md)。这是开发draft配置，production请求拒绝。
接收已授权ParseResult，输出兼容Proposed的rule findings及基础画像、内部快照/指纹和私有覆盖清单。
不修改解析worker的成功语义，不连接数据库/模型，不发布公共接口。semantic/combination始终not_run。
`python -B -m unittest discover -s mainline1/tests -v` 当前共65项（24规则＋41前序）通过。
规则输出中的applicability_ref只预留，不代表已发布权威适用性或外发授权。

## 第5步内部语义边界与融合

`semantic.SemanticBackend`及`LangChainSemanticAdapter`提供显式后端边界；默认无后端、无真实批准，保持Blocked。
`fusion.scan_context()`接收第3步ParseResult和第4步RuleResult，组织固定目标/上下文、校验输出、映射原文、
融合去重及冲突，返回私有Finding/Profile。默认组合关闭；test_only共现规则仅用于合成测试。
保持原规则证据，原始模型分数未校准；不可靠位置降为整格，不生成字符级操作或外发授权。

快照/请求可能包含原文，不得写通用日志或直接作为公共响应。所有授权receipt仅由可信owner注入。
缓存关闭、自动重试关闭；预算仅单批预留，不提供生产跨尝试/多worker总账。没有改解析worker或数据库。
详细输入/输出、覆盖口径、运输限制及具体烟测决策见[语义设计](../../docs/mainline1/semantic-design-v1.md)。

仓库根执行 `python -B docs/mainline1/verify_step05.py` 可重现合成预检和89项测试（本步24＋前序65）。
证据：[step-05](../../docs/mainline1/step-05.md)。测试后端与真实模型分开：实际模型调用0次，效果未评测。

## 第6步内部复核与适用性

`review.ReviewService`提供对象权限门禁、脱敏查询、追加复核、manual补录、政策重算、幂等/CAS和后继画像。
`review_repository.DjangoReviewRepository`及0002迁移提供私有PostgreSQL事务存储，单行aggregate上限16MiB；生产未注册。
权威适用性区分历史审计与新授权；draft政策的current也返回usable_for_new_decision=false。
`ReviewOutbox`默认not_connected；事件适配器替身测试不代表真实事件中心投递。
完整调用/限制/待决/回滚见[复核接入说明](../../docs/mainline1/review-design-v1.md)。

仓库根：`python -B docs/mainline1/verify_step06.py`（109项本地测试）；backend：
`python -B -m mainline1.tests.run_review_postgres`（36项真实隔离PostgreSQL测试及迁移检查）。
仅使用全新合成集群，证据单独保存step-06-postgres-verification.json，不覆盖前序记录。

## 第7步内部脱敏计划与纯校验

`planning.PlanService` 提供 build/validate/page，白名单操作绑定同一原输入快照。
`ReviewService.read_plan_basis` 和仓储 read 只读画像及适用性；不会创建缺失账本。
所有真实 draft 条件保持 invalid；合成测试的 ready 使用明确虚构的许可。
生产 InputSource、执行适配器及持久化计划仓储尚未接入。plan_hash 和 ready 均不代表外发授权。
契约、状态/摘要/分页、限制和待决项见[计划说明](../../docs/mainline1/plan-design-v1.md)。

仓库根：`python -B docs/mainline1/verify_step07.py`；backend：
`python -B -m mainline1.tests.run_planning_postgres`。
样例和证据保存在 docs/mainline1/plan-examples-v1.json、step-07-verification.json 及 step-07-postgres-verification.json。

## 第8步 backend_only 日常入口、重扫与清理

`operations.Operations` 是内部服务组合器，不是已发布 HTTP API。它要求可信的
`ReviewPrincipal`、资产 owner 端口和 ACL 适配器；`execute_one()` 由受管调用方显式
驱动，不创建无人管理线程。扫描绑定不可变资产版本、范围、解析配置、业务上下文、
规则配置和幂等键；主动重扫必须使用新运行。`comparison.compare_bundles()` 对输入、
解析映射或范围变化保守报告 `unmatched`，不会按移动后的坐标继承发现。

政策重分级只在证据投影未变化时复用固定发现，否则返回 `RESCAN_REQUIRED`。人工结论
只有在资产、范围、解析和检测器绑定精确一致时继承；其他情况进入待复核。

`cleanup.CleanupService` 默认预览，时间来自服务端 clock。执行需要批准策略、未过期
预览摘要和固定原因码；只处理本模块的临时解析/检测缓存，活动任务、活动引用、作用域、
ACL 或未知保留时间会阻塞。原始资产失效只能通过 owner 的正式 `invalidate` 端口请求，
并写入私有审计记录。清理并不授权删除既有业务数据。

定向检查：

```powershell
python -B -m unittest mainline1.tests.test_operations -v
python -B -m unittest discover -s mainline1/tests -v
python -B -m mainline1.tests.run_operations_postgres
```

第8步证据见 `docs/mainline1/step-08-verification.json` 和
`docs/mainline1/step-08-postgres-verification.json`。生产 owner、ACL、保留策略、HTTP
路由、跨进程服务和实际外发均未接入或验证；`plan_hash`、扫描成功和清理预览都不构成外发授权。

无敏感数据的调用契约样例见 `docs/mainline1/operations-examples-v1.json`。样例只展示
backend-only 服务组合器的参数、状态和失败边界；调用方仍须在每次执行前重新校验权威权限、
适用性和保留策略。

可从 `backend/` 运行一次真实规则/解析路径的合成 smoke 工作流：

```powershell
python -B -m mainline1.operations_smoke
```

该命令只使用内存仓储和内存中的 `.invalid` CSV，不加载业务配置、数据库或模型，
只打印合成任务状态和发现数量。它验证服务组合器调用形态，不代表持久化或生产接入。
