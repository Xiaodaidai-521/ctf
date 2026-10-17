# 第10步：最终审查、接入说明与交付

2026-10-16；**step / status: partial**。第10步完成了工作区边界复核、最终状态整理和 backend-only 接入说明。主线一内部组件和合成验证可复核；真实语义效果、生产下游、公共契约发布和外发阻断仍未验证或未获授权，因此不能将整条主线标为 complete。

## mission

已解决：

- 对照第1—9步交接和 `acceptance.md` 逐项整理成功定义；保留第3—9步实现和证据，未覆盖其他任务线修改。
- 交付启动、合成样本、任务查询/取消/受限重试、复核、重扫/比较、计划纯校验和模块内清理的 backend-only 使用说明。
- 给主线二、执行支线、审计支线和评估支线提供对象、版本、事件、错误、ACL、适用性替代和回滚边界。
- 明确规则路径、内存契约替身、隔离 PostgreSQL 和真实模型/生产下游之间的证据边界。

未解决：真实模型与独立标注集、生产资产 owner/ACL、公共 HTTP/事件契约、执行方原子使用、真实外发阻断、组合政策和正式保留规则。

## success definition 对照

| 成功定义 | 状态 | 证据与边界 |
|---|---|---|
| 1. 解析并扫描授权输入的固定资产版本 | **部分完成** | `parsing.py`、`operations.py`、`step-03`/`step-08` 证据；合成资产和 owner 替身已验证，生产 owner 未接入 |
| 2. 保留准确源位置及文本映射 | **完成（内部范围）** | `parsing.py`/`rules.py` 测试覆盖 CSV/XLSX、Unicode 和不可靠映射；JS/执行方互操作未验证 |
| 3. 综合字段名、格式、行列上下文和业务描述 | **部分完成** | 规则与语义适配器/融合边界已实现；真实语义调用为0，组合政策为 N/A |
| 4. 输出分类、依据、版本、不确定性及覆盖 | **完成（内部范围）** | `classification.py`、`rules.py`、`fusion.py` 和第4—5步证据；生产契约仍 Proposed |
| 5. 通过版本化政策映射内部保护等级 | **完成（内部范围）** | `rule-baseline-v1`、规则与复核重算测试；不等同法定分级或外发许可 |
| 6. 支持人工复核、误报纠正和漏检补录 | **完成（内部范围）** | `review.py`、`review_repository.py`、第6步及隔离 PostgreSQL 证据；生产 ACL/事件中心未接入 |
| 7. 根据要求生成可验证脱敏计划 | **完成（纯业务校验）** | `planning.py`、`plan-design-v1.md`、第7步/第9步契约替身；不执行脱敏、不生成交付副本 |
| 8. 支持版本变化、重扫和旧结果失效识别 | **完成（内部范围）** | `comparison.py`、`operations.py`、第8步 16 项定向测试和55项隔离证据；生产调度未验证 |
| 9. 提供稳定契约供其他任务线使用 | **部分完成** | `contracts/catalog.json`/`schema.json`、`integration-v1.md` 和内存替身；契约尚未批准或发布 |
| 10. 用固定功能样本和独立评测数据验证能力及失败边界 | **部分完成** | 固定合成候选集、A 规则和五级检查通过；数据集不是独立标注集，B/C 真实效果 Blocked |

## artifacts

- [`integration-v1.md`](integration-v1.md)：四条下游支线的接入、对象/事件/错误、ACL、版本、限制和回滚说明。
- [`HANDOFF.md`](HANDOFF.md)：最终交接，保留第9步证据和第10步状态。
- [`backend/mainline1/README.md`](../../backend/mainline1/README.md)：内部组件、命令、限制和前序验证入口。
- [`backend/mainline1/operations.py`](../../backend/mainline1/operations.py)、`comparison.py`、`cleanup.py`、`planning.py`、`review.py`：backend-only 服务组合、比较、清理、计划和复核能力。
- [`docs/mainline1/contracts/`](contracts/)：Proposed 对象/事件 schema、目录和无敏感样例。
- [`step-09.md`](step-09.md)、[`step-09-results.json`](step-09-results.json)、[`step-09-verification.json`](step-09-verification.json)：第9步评测及边界证据。

## changes

本步只新增 `integration-v1.md`、`step-10.md` 并更新 `HANDOFF.md`；没有修改业务实现、迁移、配置、数据库或任务线外文件。工作区原有 `backend/mainline1`、`docs/mainline1` 和任务提示文件均保留；`.gitignore` 覆盖的数据库、日志、媒体、虚拟环境和 `__pycache__` 未清理。没有发现本轮独立调试残留。

批准依据：交付模式 `backend_only` 来自用户选择；保持真实调用关闭来自用户明确回复；内部实现、合成验证、隔离数据库和文档在既有阶段授权内。未批准事项未写成公共接入：生产部署、公共契约发布、真实模型/原文外发、生产数据库迁移、业务/资产删除、正式 retention、事件 owner 和组合政策。

## verification

| 检查 | 范围 | 状态 | 证据 |
|---|---|---|---|
| 工作区边界与忽略文件复核 | `git status --short --ignored`、`.gitignore`、`mainline1` 文件树 | **Passed** | 本步执行记录；其他未跟踪任务内容未被覆盖，忽略的运行时目录未删除 |
| 新增/既有 JSON 可解析 | `contracts/*.json`、第9步配置/结果/验证文件、`operations-examples-v1.json`、`plan-examples-v1.json` | **Passed** | 本步静态检查命令及文件本身 |
| 契约样例校验 | `python -B docs/mainline1/contracts/validate_examples.py` | **Passed** | 本步执行结果；不连接数据库或模型 |
| Python 编译 | `python -B -m compileall -q mainline1`（`backend/`） | **Passed（引用）** | 第9步 `step-09-verification.json`；本步无 Python 实现变更 |
| 全量本地回归 | `python -B -m unittest discover -s mainline1/tests -q`（`backend/`） | **Passed（引用）** | 第9步及第8步：157/157 |
| 隔离 PostgreSQL | `python -B -m mainline1.tests.run_operations_postgres`（`backend/`） | **Passed（引用）** | 第8步：55项，临时集群已清理 |
| 真实模型/生产下游/外发 | 未执行 | **Blocked / Untested** | 用户保持真实调用关闭；无 owner、ACL、HTTP、事件或业务库授权 |

本步没有因为文档变更而无依据重跑全套业务实验；引用的代码/测试自第9步后未改变。新接入文档不构成契约批准。

## real-model and substitute boundary

规则路径使用真实本地解析器和规则引擎，但输入是合成数据。复核后继画像和计划验证在第9步使用明确标注的内存契约替身；它们证明对象关系和纯函数边界，不能证明生产 HTTP、持久化、事件投递或外发执行。B/C 目标输入预检通过，真实语义调用为0，未测量模型准确率、拒答率、延迟、token 或费用。隔离 PostgreSQL 只证明临时数据库事务和迁移行为，不证明业务库或生产 ACL。

## open questions and limits

- 独立人工标注集、争议处理、分组切分和冻结批准仍缺失。
- 真实 provider/model/endpoint、凭据注入、本地 token 计数、模型修订和总预算未批准。
- 主线二、执行支线、审计支线的公共对象 owner、事件 envelope、权威适用性查询和生产 ACL 未共同批准。
- 组合关系政策、正式保护等级和真值缺失；组合覆盖为 N/A。
- 未验证生产强制 CPU/RSS、跨进程计划仓储、HTTP 路由、真实资产存储、执行方原子边界、正式保留期限和删除后的跨服务引用处理。

## rollback

回滚本步时删除 `integration-v1.md`、`step-10.md` 并恢复 `HANDOFF.md` 到第9步版本；保留前序源码、契约草案和历史交接，不能使用 `git reset`/`git clean`，也不删除业务数据。若未来已获准注册服务或执行迁移，应先停止新任务和事件消费、保留被引用产物及审计，再按 owner 的迁移回滚/失效流程处理；已承载数据的表不能直接 reverse/drop。不可逆的真实外发、owner 删除或业务库迁移本轮均未发生。

## next_step_constraints

本主线阶段性交付在此停止。后续若要正式接入，必须先取得对应 owner 的公共契约、ACL、事件、模型/数据和数据库授权，并针对新增风险定向验证；不得把本步 `partial` 或文档中的 Proposed 文字解释为部署许可、外发许可或业务库执行许可。
