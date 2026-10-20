# 第8步：重扫、操作入口与受控清理

2026-10-15；**step / status: partial**。本步按已选择的 `backend_only` 实现内部服务入口、重扫/差异比较、政策重分级和预览优先清理。正式 delivery_mode、权限、资产 owner 和保留规则仍未批准，因此生产接入、公共路由和真实数据删除保持阻塞。

## 交付内容

- `backend/mainline1/operations.py`：`create_version`、`create_scan`、`get_scan`、`cancel_scan`、`retry_scan`、`recover_expired`、`execute_one`、`get_profile`、`list_findings`、`submit_review`、`compare_scans`、`regrade`、私有解析结果读取及清理委托。入口要求可信 `ReviewPrincipal`、资产 owner 端口和对象 ACL；同步 worker 由调用方显式驱动，不创建无人管理线程。
- `backend/mainline1/comparison.py`：同一私有输入仅按完整 finding 投影比较；文件/解析/范围变化产生 `unmatched` 和限制，行列移动不按坐标强配；类别变化单列 `category_changes`。不完整检测不会把消失解释为安全。
- `backend/mainline1/cleanup.py`：主线一临时解析/检测缓存的 scope、活动任务、引用、保留期限和 ACL 检查；默认 dry-run，执行需批准策略、预览摘要和稳定原因码。执行只清除本模块 payload，并将关联适用性标为 `unverifiable_deleted`；资产 owner 删除通过 `invalidate` 正式端口请求且单独审计。
- `backend/mainline1/tests/test_operations.py`：16 项合成端到端工作流测试，覆盖新版本、主动重扫、取消/失败/重试、移动/类别变化、人工结论精确继承、政策重分级、清理预览/活动保护、owner 请求和运行中取消。
- `backend/mainline1/tests/postgres_operations_cases.py`、`run_operations_postgres.py`：隔离 PostgreSQL 工作流检查。`docs/mainline1/step-08-postgres-verification.json` 为独立证据。
- `docs/mainline1/operations-examples-v1.json`：不含敏感原文的 backend_only 调用、状态和清理边界样例。
- `backend/mainline1/operations_smoke.py`：真实规则/解析路径的可运行合成 smoke 示例；仅内存仓储，无业务数据、模型或数据库。

重扫使用新的幂等键和新的 run；同资产同范围重扫只有在解析/上下文/检测器绑定完全一致时继承人工结论，否则保留待复核限制。政策只改变已具备证据的等级映射时建立新画像；规则、类别、组合或证据要求变化返回 `RESCAN_REQUIRED`。旧画像、发现和计划不原地改写。

清理的公开结果只包含资源 ID、数量、原因码和审计引用，不含原文。原始资产、跨模块证据和共享对象不由此服务删除。

## 验证与边界

本地 `python -B -m unittest discover -s mainline1/tests -v`：157 项 Passed（16 本步＋141 前序）。定向工作流 `python -B -m unittest mainline1.tests.test_operations -v`：16 项 Passed；`python -B -m mainline1.operations_smoke` 成功。相关 Python AST/编译检查和工作区边界检查 Passed。真实规则/解析路径使用合成资产；ACL、资产 owner、保留批准是替身；真实语义调用为 0。

隔离数据库命令：`python -B -m mainline1.tests.run_operations_postgres`。最新代码重跑 55 项 Passed，包含新增权限、actor 绑定、分页/私有 ACL 和清理重连测试；system check、迁移漂移、正反向迁移 Passed，`temporary_cluster_removed=true`；未连接既有业务库。生产 PostgreSQL、HTTP 路由、真实资产存储、跨进程计划/任务服务及实际外发均 Untested/Blocked，不能由本步结果推导。

## 交接约束

已批准：backend_only 的本步内部实现、既有依赖、合成测试和全新隔离库验证；来源为用户本步指令、backend_only 选择及完整提示词 B3/B4。未批准：公共契约发布、生产 app/worker、真实模型/数据外发、保留期限和资产删除。

回滚只撤回第8步新增模块、测试、证据和文档，以及 `ReviewState` 对工作流/资源/清理审计字段的兼容增量；保留第3—7步历史和业务数据，不反向迁移、不 reset/clean。

待决：Q8-delivery-permissions（生产权限/owner/公共入口）、Q8-retention（正式保留与删除策略）、继承 D02/D03/D04/D05/Q6/Q7。下一步只能消费已验证工作流；不得把合成 `succeeded`、`ready`、清理预览或 `plan_hash` 当作外发授权。停止等待第9步。
