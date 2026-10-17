# 第9步：跨模块契约与独立效果验证

2026-10-16；**step / status: partial**。本步完成了可复现的规则路径评测、解析→规则→画像→复核后继画像→纯计划校验的契约替身，以及静态、行为、契约、边界和安全检查。核心 B/C 上下文效果实验未完成：真实语义后端、固定模型修订、预算和独立标注集均未获批准或提供，因此不能宣称上下文收益或生产效果。

## mission

已解决：

- 登记了与第5步固定功能样本分开的合成评测候选集，固定资产版本、模板族、业务实体组、内容摘要、定位标签、匹配口径、解析/规则配置、输入长度和无随机采样设置。
- 新增可复现入口 `backend/mainline1/evaluate_step09.py`。A 使用真实解析器和规则引擎；B/C 构造相同目标集合并执行 `abc_preflight`，不发起模型调用。
- 输出字段、实体位置、政策等级、解析/规则覆盖、误报/漏报/未知/失败、复核替身和计划验证结果；组合关系因无批准政策记为 N/A。
- 用内存契约替身联通解析结果、规则画像、复核后继画像和计划纯校验；不执行真实外发、共享、业务库写入或模型请求。

未解决：

- 合成标签是本步手工编写、尚未独立复核的候选集；A 指标只能作为管线描述，不能作为独立效果结论。
- B/C 的真实语义调用为 0；上下文整体效果、模型成本、真实拒答/失败率和生产规模均未测量。
- 真实下游事件适配、生产对象 owner/ACL、公共路由和外发阻断仍为 Untested/Blocked。

## artifacts

- [评测入口](../../backend/mainline1/evaluate_step09.py)：从冻结候选集加载输入，运行 A、B/C 预检、失败样本和契约替身，写出聚合结果。
- [合成候选集](step-09-eval-set-v1.json)：两种模板族、两个业务实体组、6 个手工定位标签及独立解析失败样本；状态为 `candidate_not_independent`。
- [冻结配置](step-09-eval-config-v1.json)：解析、规则、A/B/C、匹配、采样、预算和已知限制。
- [结果](step-09-results.json)：确定性 JSON 结果；包含摘要哈希、实体/字段指标、覆盖、策略映射、失败和安全计数。
- [验证证据](step-09-verification.json)：五级验证及引用的前序证据。
- [输入状态](step-09-input-state.json)：本步开始前受保护文件摘要，用于边界复核。

## findings

| 结论 | 能力状态 | 证据状态 | 验证状态 | 置信度 |
|---|---|---|---|---|
| A 规则路径能在两种合成模板上给出 6 个严格实体位置匹配 | Implemented | Verified | Passed | High |
| A 的 `1.0` precision/recall/F1 是候选集上的描述性规则结果 | Partial | Verified | Passed | High |
| B/C 目标集合、目标文本和上下文输入组织可预检 | Implemented | Verified | Passed | Passed / High |
| B/C 上下文语义效果和收益 | Partial | Unknown | Blocked | Low |
| 解析→规则→画像→复核后继画像→纯计划校验契约替身 | Implemented | Verified | Passed | High |
| 真实下游事件、生产 ACL、模型和外发阻断 | Unknown | Unknown | Untested / Blocked | Low |
| 组合发现质量 | Missing for this scope | Unknown | N/A | High |

A 汇总结果：实体严格一对一匹配 `TP=6, FP=0, FN=0`；字段指标按 `(sheet,column,category)` 单独计算同样为 `TP=6, FP=0, FN=0`。这些数值只适用于本步候选集合和规则基线，不是模型效果门槛、提升比例或生产预测。解析和规则覆盖为每个资产 `10/10`；组合分母为 0，写 `N/A`。复核替身确认 1 项，规则发现仍是待复核；拒答为 0 是因没有运行真实语义请求，不是“模型无拒答”。

## changes

动机是集中验证第3—8步已实现链路的契约边界，并为未来获批的独立实验保留固定输入和口径。范围仅包括评测入口、合成候选集、冻结配置、结果、验证记录和本交接文档；没有修改解析、规则、语义、复核、计划、任务或数据库业务实现。复用既有 `parse_table`、`scan_rules`、`abc_preflight`、`ReviewService` 和 `PlanService`。

重要替代方案是接入真实模型或用 Mock 生成 B/C 指标；前者缺少授权、凭据注入、token 计数和费用账本，后者不符合“不能用 Mock 证明语义效果”的约束，因此均未采用。未验证假设包括真实模型修订固定、实际 token 计数、价格、下游事件 envelope 和生产 ACL。结果脚本只写 `docs/mainline1/step-09-results.json`，不写业务状态。

回滚：删除本步新增的 `evaluate_step09.py`、`step-09-*` 评测产物和第9步交接文档，恢复第8步交接；不回滚或删除第3—8步实现、数据库、任务或业务数据，不执行 `reset/clean`。

## verification

- **Level 1 静态：Passed。** `python -B -m compileall -q mainline1`；5 个第9步 JSON 文件可解析；结果文件两次运行 SHA-256 相同。
- **Level 2 行为：Passed。** `python -B -m mainline1.evaluate_step09`；两资产、20 个解析单元格、A 规则路径和一个 `PARSE_FAILED` 样本完成。真实解析/规则使用合成数据。
- **Level 3 契约：Passed。** 评测入口内存替身完成复核 successor 和计划 `validate`；`test_operations` 16、`test_review` 20、`test_planning` 32 项通过。该替身不证明生产公共接口或下游投递。
- **Level 3 前序持久化证据：Passed（引用，不重跑）。** 第8步实现未变化；157 项本地回归和隔离 PostgreSQL 55 项证据继续有效，范围见 `step-08-verification.json` 与 `step-08-postgres-verification.json`。
- **Level 4 边界：Passed。** 解析失败不转成实体负例；B/C 使用完整解析目标集合而非只选正例；移动、取消、旧任务、人工结论继承、清理和计划失效边界引用第8步定向证据；组合为 N/A。
- **Level 5 安全：Passed（合成范围）。** 网络调用 0、凭据读取 0、真实数据 0、结果中无原始敏感值；不执行模型生成代码、外发或业务删除。
- **B/C 真实语义：Blocked。** `model_calls=0`、`metrics=null`；仅 `target_equivalence=Passed` 和输入限制预检有证据。
- **真实下游/生产环境：Untested / Blocked。** 没有 HTTP、生产 owner、真实事件适配器、生产 ACL 或业务数据库执行。

## approved_decisions

- 交付模式继续使用 `backend_only`；来源为前序用户选择和第8步有效授权。
- 用户明确选择“保持真实调用关闭，交付部分结果并记录缺口”；因此本步不调用真实语义后端、不读取凭据、不发送原文。
- 允许使用既有依赖、纯合成候选输入、内存契约替身和已存在的隔离数据库证据；不含公共契约发布、生产部署、真实外发、正式 retention 或 owner 删除授权。

## judgment_changes

- 原结论：第9步尚无评测入口和候选集。新证据：已生成可复现 A/B/C 预检和契约替身结果。影响：内部链路可复核，但核心上下文实验仍未完成。
- 原草案曾把本步集合标为独立冻结标注集。新证据：集合由本步手工构造且未独立复核。新结论：改为 `candidate_not_independent`，A 指标降为描述性结果；不再作为独立效果证据。
- 原结果包含随机 ID/时间。新证据：固定扫描输入和过滤运行时字段后，两次结果 SHA-256 相同。新结论：评测结果文件可重现，但真实模型可复现性仍未知。

## open_questions

- Q9-independent-set：需要独立人工标注、争议处理记录、模板/实体组隔离和冻结批准，才能运行独立效果评测。
- Q9-semantic-budget：需要批准 provider、model、HTTPS endpoint、凭据注入方式、本地 token 计数器、模型修订、输入资产范围及总 token/费用上限；不应把本步候选集自动视为外发授权。
- Q9-downstream-contract：需要主线二、执行支线和事件 owner 共同确认公共契约、事件 envelope、适用性权威查询和生产 ACL。
- Q9-combination-policy：需要正式关系类别、保护等级、真值和批准来源；当前组合指标为 N/A。

## next_step_constraints

下一步只能消费本记录中明确为 Passed 的内部证据。不得把 A 的合成规则结果、B/C 预检、复核替身、`ready` 或 `plan_hash` 当作模型效果、生产表现或外发许可。真实模型、独立标注集、生产下游和实际外发仍需单独授权与验证。本步结束后停止等待第10步。
