# 第7步计划生成、纯校验与执行方接入草案

2026-10-15。approval_status: **proposed**。owner：主线一；consumers：受控外发执行方、主线二、评测中心。本说明细化第2步 `design.md` 第8节及既有 RedactionPlan/Requirement/Operation Schema，没有批准或发布公共接口。

## 内部入口与信任边界

`backend/mainline1/planning.py` 提供 `PlanService.build(principal, profile_id, idempotency_key=...)`、`validate(principal, plan)` 和 `page(principal, plan_id, cursor=..., page_size=...)`。未注册 HTTP 路由、生产 app 或执行适配器。

组合方实现 `InputSource.read(principal, profile_id) -> PlanInputs`：每次鉴权及对象授权，读取固定 bundle/解析材料和当前资产、适用性、分类政策版本、规范化保护要求、脱敏政策。该端口必须只读，并提供一致的权威观察；不能把客户端上传的 bundle、approval 布尔值、政策或资产状态当作权威输入。没有生产实现。现有 `ReviewService.read_plan_basis` 对 bundle 和适用性采用一次仓储只读快照，调用既有 `plan` 对象权限门禁；资产 owner 与政策 owner 的组合仍待接入。

`PlanPolicy` 默认所有批准标记为 false、uncertain=review。其批准标记只能由未来可信 owner 从批准记录解析；测试里的 true 是明确虚构的合成许可，不是本项目真实批准。当前第6步 draft 画像的 usable_for_new_decision=false，因此真实 draft 条件下输出 invalid。`plan-examples-v1.json` 同时给出虚构许可 ready 和当前 draft invalid 样例。

公开字段仍遵守 `contracts/schema.json` 的 RedactionPlan、Operation、Requirement。计划绑定 meta 数据域/环境/评估身份、asset_id/asset_version_id/content_hash、scan/profile/scope、parser_version/config_hash、分类政策、脱敏政策版本、operation_contract_version、规范化要求及 requirements_hash。所有版本必须不可变；同版本改变政策内容违反输入端口契约，需要拒绝或生成新版本。

## 操作和覆盖

- 白名单：mask_span、mask_cell、drop_column；遮蔽值固定为字面 `[REDACTED]`，删除列 replacement=null。参数中没有表达式、代码、路径或可执行模板。
- 选择次序为满足要求的字符、整格、删除列；用户的 allowed_operations 是集合，不用于指定执行顺序。删除列须 allow_drop_column=true。重复的同类型同目标操作合并依据和要求引用。
- 字符范围是一基行列定位下的零基 Unicode 码点 `[start,end)`，指向原始单元格；不沿用展示字符串或 UTF-16 索引。检查原文边界、NFKC 映射边界和通道。公式通道不接受字符操作，可按明确政策整格替换为字面值。
- 发现判断未确定、字符映射失配时，uncertain=review 留下未解决项；uncertain=mask_cell 只在能够准确定位原格且要求允许时整格处理。找不到原格始终 unresolved，不能猜坐标。
- 删除列涉及整列结构，包括表头和隐藏内容。当前保守实现要求范围含表头、行范围覆盖完整工作表、隐藏内容包含、每行目标列已解析、没有合并或未覆盖的非单元格内容。普通排除表头的扫描不能生成删除列。CSV 完整范围的删除列路径已测；复杂 XLSX 结构删除没有执行证据。
- 同列删除与任何遮蔽并存、同格整格与字符并存、字符区间重叠，均 PLAN_CONFLICT。相邻字符区间允许。不会自动通过去掉操作来降低某项保护要求。
- “删除原 A 列＋处理原 B 列”允许，所有目标都以原输入解释。这里只规定最终结果等价性；不规定执行方先删列、倒序替换或重建工作表等内部算法。
- 校验器从当前权威发现和保护要求独立枚举义务，再验证操作覆盖、依据引用、未知操作、参数、位置及冲突，不信任传入计划的 unresolved 或 count。
- 覆盖不完整、未知类别、组合发现未支持时明确 unresolved。当前实现保守地禁止不完整画像产生 ready，即使 require_complete_coverage=false；该值不会授权把未扫描数据解释为安全。allow_unresolved 只允许 partial，不允许 ready 绕过未知项。

## 内容匹配与无写入校验

生成与校验均在受控进程内部，将解析单元格、元数据及配置与扫描快照所固定的内部摘要比较，再验证目标位置。公开操作的 match_ref 只含 plan_id/operation_id，没有单元格原文、原文摘要或低熵值裸 SHA256。它是本计划内的定位比较句柄，不是独立授权令牌或可访问文件路径。当前通过完整 `validate` 一并解析校验，不提供生产远程 match_ref API。

validation_ref 是同一内部计划的校验命名句柄，不代表已落库的证据记录；`validate` 每次返回新观察结果，包含 valid/error_codes/plan_hash/observed_asset_state_version/observed_applicability_version/checked_at。不存在永久有效的校验收据。授权失败采用 OBJECT_NOT_FOUND；权威源异常返回 AUTHORITY_UNAVAILABLE，不含异常原文。

校验没有 ORM 写调用、业务状态更新、文件写入、额度预占、共享或交付。Memory/Django 仓储新增的 read 路径不会创建缺失账本；Django 路径只 SELECT 一次固定 aggregate。隔离 PostgreSQL 捕获 SQL 验证成功、失效及缺失账本路径。它没有消除跨资产/政策 owner 的检查与使用之间的时间窗口；生产执行方必须重新读取权威状态并实现相应并发保护。

## 状态、摘要、幂等和分页

ready：当前资产/画像/政策及批准条件符合、全部操作与范围有效、所有指定义务被覆盖，unresolved/validation_errors 均为空。partial：没有硬校验错误，存在未解决义务且要求允许部分计划。invalid：版本、适用性、审批前置、参数、冲突等硬错误，或存在不允许保留的未解决义务。validate 对 partial/invalid 都返回 valid=false。

人工补录或复核后，旧计划本体保持不可变。后续校验重新读到 superseded/reevaluation_required 或状态版本变化时失败；资产内容摘要未变不能豁免此检查。先前 invalid 也不会在批准发生后自动变 ready，需要新计划。

plan_hash 使用既有内部整数/字符串 canonical JSON 的 SHA256：键排序、UTF-8、无空白、保留规范化数组顺序；投影覆盖计划全部字段，排除 plan_hash 和 meta.trace_id。操作按稳定 UUID 排序。此受限对象不包含浮点字段；不声称已验证跨语言浮点规范。`plan_hash` 只证明内容一致性，不是签名、许可或授权。

build 的幂等键作用域含 actor/domain/environment/evaluation，绑定固定版本、规范化要求、政策及观察状态。相同键相同规范化输入返回同一 ID/hash 的副本；同键输入变化 IDEMPOTENCY_CONFLICT。新键产生新计划身份。内存实例重启会丢失重放登记，因此没有跨进程或持久化幂等保证；旧返回内容不能代替新的 validate。

page 固定 plan_id/full plan_hash/operation_count/operations_hash；翻页重新鉴权，后续复核不会混入新画像操作。HMAC 游标绑定主体作用域、计划摘要、page_size、offset 和15分钟到期时间；它是完整性保护，不是保密加密。密钥由服务端注入，生产密钥不写文档或日志。单页不构成完整计划，消费者收齐后重算整个计划摘要。内存记录缺失返回 OBJECT_NOT_FOUND，不悄悄重新生成计划。

内部限制：每服务实例最多100个计划、每请求最多100项要求、最多1000个要求×发现位置目标及1000个操作；超限返回 RESOURCE_LIMIT 或输入错误。当前为小规模内部验证，未测生产吞吐/长期留存；完整生产计划仓储、密钥生命周期和远程服务属于后续经批准接入工作。

## 执行方消费与具体待决项

1. 对固定 plan_id 收齐分页，检查相同 header/count/operations_hash 和完整 plan_hash；保留所有原始目标坐标。
2. 执行前再次通过权威资产/画像/要求/政策查询并调用纯校验。状态不可查询、已替代或要求变化时停止使用；不能只等异步通知。
3. 外发授权、额度、接收方、检查后变化保护和实际操作由执行方负责。ready 与 valid=true 都不授权外发。
4. 不接受客户端 approval 标志，不将测试样例的虚构许可用于生产。

Q7-contract-policy（未批准）：建议本次保持内部 Proposed；正式接入前由政策 owner 与执行方共同批准既有 `original-snapshot-v1-proposed` 的坐标/组合/失败语义，提供保护要求来源、版本和不确定项处理政策，并指定权威状态/私有匹配端口、权限、检查后变化规则。替代方案是共同修订并版本化新契约，再适配和验证；不能单方改变执行算法或当前公共语义。本次只完成可审阅实现和样例，未触发公共发布。

沿用前序 D02/D03 owner/生产接入、D04 真实模型/数据/费用、D05 组合策略以及 Q6 事件信封和保留规则，已有授权仍有效，未批准项不影响本步独立验证。

回滚：仅撤回 planning.py、计划测试/样例/第7步文档；撤回 review.py 的 read_plan_basis/read 协议及内存实现、review_repository.py 的 read 方法、隔离 runner 第7步证据文件白名单和 README 增量。恢复本步前 HANDOFF 归档；不 reset/clean、不修改历史迁移或任何业务库。
