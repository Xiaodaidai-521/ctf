# 第8步 backend_only 入口说明

`Operations` 是内部服务组合器，不是已发布 HTTP API。资产 owner 提供 `resolve/create_version/open_version`，ACL 通过 `allowed` 注入；未提供可信实现时入口返回受控错误。`create_scan` 固定版本、解析范围、上下文、规则配置、语义开关和幂等作用域；`execute_one` 显式运行受管同步 worker，任务状态来自既有 CAS 状态机。

`compare_scans` 只接收有权限的画像。完全相同私有输入才允许稳定位置配对；变更版本、范围、解析配置或内容摘要时全部报告 `unmatched`。相同类型发现移动到新行/列没有稳定实体 lineage，因此不伪造 added/disappeared 配对。类别变化保留 before/after finding ID。

`regrade` 只接受政策版本改变且规则/类别/组合证据投影不变的配置，产生新画像和替代关系。发现或组合证据变化必须完整重扫。人工复核继承要求 binding、engine、范围和适用性均一致，其他情况保持 pending。

清理只处理 `temporary_parse`/`detection_cache` 资源。`preview` 计算候选、阻塞项和摘要；生产执行要求批准 `CleanupPolicy`、未过期预览摘要、固定原因码和重新检查。活动任务、活动引用、ACL 失败、未知保留时间及范围越界均保护。原资产删除仅向 owner 发起带审计引用的失效请求。

由于本轮 backend_only 选择没有批准生产权限、保留规则或公共路由，文档和样例不构成部署说明或删除授权。
