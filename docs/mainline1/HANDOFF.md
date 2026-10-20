# 主线一最终交接：第10步

2026-10-17 复核；**step / status: 10 / partial**。第10步完成最终审查、backend-only 接入说明和回滚说明。本次复核确认第3—9步的本地组件、合成验证和历史隔离数据库证据边界；当前隔离 PostgreSQL 运行器在 Windows `CREATE_NO_WINDOW` 子进程路径上以 `ISOLATED_INITDB_FAILED` 失败，因此不能把隔离数据库验证称为本次复核通过。真实语义效果、独立评测、生产下游、公共契约发布和真实外发阻断仍未验证或未获授权。

## mission

已解决：

- 保留并核对第3—9步实现和证据，未覆盖其他任务线修改；忽略的数据库、日志、媒体、虚拟环境和 `__pycache__` 未清理。
- 汇总 backend-only 的配置/启动、合成样本、任务、复核、重扫、计划验证和清理入口。
- 形成四条下游支线的对象、版本、事件、错误、ACL、适用性替代和回滚边界。
- 明确真实模型、规则路径、内存契约替身、隔离 PostgreSQL 和生产环境之间的证据边界。

未解决：独立标注集和 B/C 真实模型实验；生产资产 owner/ACL、HTTP 路由、跨进程计划仓储、正式事件中心；执行方原子使用；组合政策；正式保留规则；业务库迁移、资产删除和真实外发阻断。

## artifacts

- [`step-10.md`](step-10.md)：成功定义逐项状态、最终审查、验证、限制和回滚。
- [`integration-v1.md`](integration-v1.md)：主线二、执行支线、审计支线、评估支线接入说明。
- [`step-09.md`](step-09.md)、[`step-09-results.json`](step-09-results.json)、[`step-09-verification.json`](step-09-verification.json)：第9步评测和五级验证证据。
- [`backend/mainline1/README.md`](../../backend/mainline1/README.md)：内部组件和命令说明。
- [`backend/mainline1/operations.py`](../../backend/mainline1/operations.py)、`comparison.py`、`cleanup.py`、`planning.py`、`review.py`：服务组合、比较、清理、计划和复核入口。
- [`contracts/catalog.json`](contracts/catalog.json)、[`contracts/schema.json`](contracts/schema.json)、[`contracts/examples.json`](contracts/examples.json)：Proposed 对象/事件目录、schema 和样例。
- [`history/handoff-step-08.md`](history/handoff-step-08.md)：第8步归档；本文件保留第9步交接内容的结果和限制。

## findings

| 能力 | 能力状态 | 证据状态 | 验证状态 | 置信度 |
|---|---|---|---|---|
| CSV/XLSX 受限解析、位置映射、规则识别、版本快照 | Implemented | Verified | Passed（合成/隔离范围） | High |
| 语义适配、融合和降级边界 | Implemented | Verified | Passed（适配器/故障注入）；真实模型 Blocked | Medium |
| 复核、人工补录、后继画像和适用性状态 | Implemented | Verified | Passed（当前内存；隔离 PostgreSQL 为历史证据，本次运行器失败）；生产 owner/ACL Untested | High |
| 重扫、差异、取消、受限重试、分页和清理 | Implemented | Verified | Passed（当前本地；第8步 55 项隔离 PostgreSQL 为历史证据，本次复核 Failed） | High |
| 脱敏计划生成和纯业务校验 | Implemented | Verified | Passed；执行方接入 Untested | High |
| 规则 A 候选集描述性指标 | Partial | Verified | Passed；不代表独立效果或生产表现 | High |
| B/C 上下文收益、模型成本和真实拒答 | Partial | Unknown | Blocked（调用 0、metrics null） | Low |
| 跨模块公共契约、真实事件、生产 ACL 和外发阻断 | Proposed/Unknown | Unknown | Untested / Blocked | Low |

## verification

- 第9步评测入口 `python -B -m mainline1.evaluate_step09`：Passed；2 个合成资产、20 个解析单元格、6 个严格规则实体匹配；B/C 仅做目标等价和输入预检。
- 第9步本地回归 `python -B -m unittest discover -s mainline1/tests -q`：157/157 Passed；第8步后业务实现未变，作为引用证据保留。
- 第9步编译 `python -B -m compileall -q mainline1`：Passed（引用）。
- 第8步历史隔离 PostgreSQL 证据仍记录 55 项 Passed；本次复核重新运行同一入口时 `initdb` 子进程返回 `ISOLATED_INITDB_FAILED`，当前证据文件已保留失败状态。手工 `initdb` 可完成，失败范围限定为当前 Windows 子进程启动路径，不能升级为业务逻辑回归或当前数据库通过。
- 第10步静态检查：契约样例脚本、主线 JSON 和接入文档可解析；未重新执行无必要的全套实验。
- 真实模型、独立标注集、公共 HTTP、生产 owner/ACL、正式事件中心、执行方和真实外发：Blocked / Untested。

第9步结果摘要 SHA-256 为 `sha256:50e38a83fd81ccc3286383d5aec264e759e2e51cb0d7796b57e27a4afe25f989`；该一致性只证明固定合成运行输出可重复，不扩展为真实模型可复现性。

## approved_decisions

- 交付模式为 `backend_only`；来源：用户选择及第8步交接。
- 真实模型调用保持关闭，交付部分结果并记录缺口；来源：用户明确回复。没有读取凭据、网络调用或真实原文外发。
- 允许既有依赖、合成输入、内存契约替身、内部文档和全新隔离数据库验证；不包含公共契约发布、生产部署、真实外发、业务库迁移、资产 owner 删除或正式 retention 批准。

## judgment_changes

- 从“第9步后需补最终接入说明”更新为“已提供 `integration-v1.md`，但契约仍 Proposed，不能直接接入生产”。
- 从“固定合成集合可作效果数据”保持修正为 `candidate_not_independent`；A 指标仅描述性。
- 从“内部链路可复核”细化为：规则、复核、计划、重扫和清理在已列测试范围内 Passed；真实模型、事件、ACL、执行方和外发保持 Blocked/Untested。
- 从“隔离 PostgreSQL 可在本次交接引用”更新为“历史记录仍可审计，但本次运行器因 `ISOLATED_INITDB_FAILED` 未完成验证；手工 `initdb` 成功仅定位环境差异，不替代隔离测试”。

## open_questions

- Q9-independent-set：独立人工标注集、争议处理、模板/实体组切分和冻结批准。
- Q9-semantic-budget：provider/model/endpoint、凭据注入、本地 token 计数、模型修订、数据范围和总 token/费用上限。
- Q9-downstream-contract：公共对象、事件 envelope、权威适用性查询、执行原子边界、生产 ACL 和 owner。
- Q9-combination-policy：正式关系政策、保护等级、真值和批准来源。
- Q8-retention / D02 / D03 / D04 / D05 / Q6 / Q7：正式保留、真实语义、跨线契约、事件和下游授权。

## changes and rollback

第10步新增 `step-10.md`、`integration-v1.md` 并更新本文件；本次复核另更新 `step-08-postgres-verification.json` 为当前运行器失败记录，没有修改业务源码、迁移、配置、业务数据库或其他任务线文件。回滚仅删除本步两个新增文档并恢复本文件到第9步交接，或移除本次复核记录并保留历史证据；不使用 `git reset`/`git clean`，不删除业务数据。未来生产启用须先停止新任务和事件消费，保留被引用产物和审计，再按 owner 的迁移/失效流程处理；已承载数据的迁移不可直接 reverse/drop。不可逆的真实外发、资产删除和业务库迁移本轮均未发生。

## next_step_constraints

本主线阶段性交付在此停止。任何后续正式接入必须先取得相应 owner 的公共契约、ACL、事件、模型/数据和数据库授权，并对新增风险做定向验证。不得把 `partial`、合成规则指标、B/C 预检、内存替身、`ready` 或 `plan_hash` 解释为模型效果、生产表现、外发许可或部署许可。
