# 主线一交接：第8步

2026-10-15；**step / status: 08 / partial**。已按用户选择的 `backend_only` 完成本步内部日常工作流、重扫比较、入口样例和预览优先清理，并完成合成回归与隔离 PostgreSQL 验证。生产权限、公共路由、正式保留规则和真实外发仍未获批准或接入；本步完成后停止等待第9步。

## mission

已解决资产版本/主动重扫/差异查询、任务创建查询取消受限重试、画像与复核入口、政策重分级、私有结果读取以及本模块临时资源清理的首版 backend-only 闭环。文件变化创建新版本和新运行；输入、解析映射、范围或政策证据变化时保守返回 unmatched、待复核或 `RESCAN_REQUIRED`。不按移动后的坐标认定同一发现。

## artifacts

- [第8步记录](step-08.md)：本步结果、边界、回滚和未验证项。
- [操作服务](../../backend/mainline1/operations.py)：入口组合器，显式驱动 worker，不创建无人管理线程。
- [差异比较](../../backend/mainline1/comparison.py)：固定完整 finding 投影比较，报告新增、消失、类别变化和无法可靠匹配。
- [受控清理](../../backend/mainline1/cleanup.py)：预览、作用域、活动任务/引用保护、保留条件、审计及 owner 委托。
- [backend-only 样例](operations-examples-v1.json)：参数、状态和非授权边界，不含敏感原文。
- [操作测试](../../backend/mainline1/tests/test_operations.py)：16 项定向工作流测试。
- [隔离数据库证据](step-08-postgres-verification.json)：最新代码 55 项通过，临时集群已删除。
- [本地证据](step-08-verification.json)：157 项本地回归及静态检查。

## findings

内部能力：Implemented / Verified / High / Passed。规则、解析、任务和复核路径使用合成资产，真实模型调用 0 次；ACL、资产 owner、保留批准为注入测试替身。隔离 PostgreSQL system check、迁移漂移、正向和反向迁移均 Passed。

正式公共接入：Partial / Verified（边界） / High / Blocked。`Operations` 不是已发布 HTTP API，未注册生产 app/worker 或跨进程服务。真实资产存储、生产 owner 权限和公共契约未验证。

真实执行/外发：Unknown / Unknown / Low / Untested。扫描成功、`ready`、清理预览、profile/scan ID 或 `plan_hash` 均不构成外发授权。

## changes

新增 `operations.py`、`comparison.py`、`cleanup.py`、定向测试、PostgreSQL runner/案例、样例和第8步证据文档；对 `planning.py`、`review.py`、隔离 runner 和 README 的兼容增量已在 `step-08-input-state.json` 中记录。创建版本先做权限检查并绑定可信 actor；扫描读写和私有结果访问逐次检查对象权限。未新增第三方依赖、生产迁移、HTTP 路由、共享或业务数据删除。

## verification

- `python -B -m unittest mainline1.tests.test_operations -v`：16 / 16 Passed。
- `python -B -m unittest discover -s mainline1/tests -v`：157 / 157 Passed。
- `python -B -m mainline1.operations_smoke`：Passed；仅内存合成资产并输出状态/数量元数据。
- `python -B -m mainline1.tests.run_operations_postgres`：55 / 55 Passed；system check、makemigrations 漂移检查、forward/reverse migration Passed；`temporary_cluster_removed=true`。
- `python -B -m compileall -q backend/mainline1`、样例 JSON 解析和受保护输入哈希复核：Passed；工作区无尾随空白。`git diff --check` 对未跟踪文件不提供覆盖，故以同等范围的文本扫描记录。
- 业务库执行、真实 HTTP、生产 owner、真实保留删除和实际外发：Untested / Blocked。

## approved_decisions

已批准内容：backend_only 交付模式；本步内部服务实现、无敏感合成样例、既有依赖、隔离临时数据测试和全新隔离 PostgreSQL 验证。来源：用户选择 backend_only、第8步提示词、前序继续有效的内部实现授权。

未批准事项不得混入：公共契约发布、生产部署、真实模型/数据外发、正式 retention/deletion policy、资产 owner 删除、业务库迁移或删除。

## judgment_changes

此前记录的 50/52 项数据库验证发生在新增权限、分页和清理重连测试之前；最新重跑证据将结论更新为 55 项 Passed。此前 `step-08.md` 的本地数字 153/12 已更新为 157/16。该变化只影响证据计数，不放宽生产边界。

## rollback

仅撤回本步新增模块、测试、样例、证据和文档，以及列明的兼容增量；保留第3—7步历史和业务数据。不执行 `reset/clean`，不反向迁移生产库，不调用 owner 删除既有资产。回滚前停止任何受管调用方并保留被引用私有产物。

## open_questions

- Q8-delivery-permissions：生产 service identity、资产 owner/ACL 权威端口、公共或内部路由契约。
- Q8-retention：正式临时数据保留期、删除授权、跨模块引用策略和审计要求。
- 继承 D02/D03/D04/D05/Q6/Q7：前序政策、语义、适用性和执行契约待决。

## next_step_constraints

下一步只能消费本交接列示且已验证的内部工作流。不得把合成结果、清理预览、`ready` 或 `plan_hash` 当作外发许可；不得在未批准 owner/retention/公共契约前接入生产或删除业务数据。
