# 主线一设计与契约说明 v1

状态：**Proposed**。日期：2026-10-11。基线 revision：`f4ac82caf32a4112c047cdb8848cab135acbb3c6`。
第2步形成设计、Schema、合成样例与草案检查；未发布接口。2026-10-13 按用户审查补齐指令完成收尾，第3步内部实现另见 step-03.md。冻结的是可审阅草案，不是已批准公共契约。产品基线沿用完整提示词 B/C/D/F/J。

## 1. 产物与解释顺序

[契约 Schema](contracts/schema.json) 定义14个核心对象及辅助结构；[字段目录](contracts/catalog.json) 提供 owner/consumers/fields/invariants/errors/compatibility/approval_status；[样例](contracts/examples.json) 与 [校验器](contracts/validate_examples.py) 仅验证草案。跨字段和跨对象约束由本文与样例校验共同描述，JSON Schema 不替代数据库一致性或权限验证。若三者冲突，停止接入、修订草案并增加版本，不静默选一个解释。

共同字段通过每个核心对象的 `meta` 给出。字段均显式必填，可未知的字段使用 null；不将缺失、空数组、零、未知混同。UUID 用小写标准字符串，新领域对象使用 UUID；现有 CTFUser ID 保持正整数。数组分页与内部受控清单分开：Schema 中完整数组是逻辑对象，网络分页不改变该对象的 hash/引用语义。

## 2. 模块所有权和数据流

| 模块/对象所有者 | 责任及适配点 | 明确边界 |
|---|---|---|
| 既有资产所有者（待共同指定，主线一仅适配） | 私有上传、只读固定版本流、原始字节摘要、删除墓碑；主线一只消费 AssetVersionRef | 不借 resources 审核后公开语义，不将上传交给会自动 embedding 的 RAG；不由扫描清理删除资产 |
| mainline1 解析器 | 标准库 csv、已声明 openpyxl；原文/规范化/展示分开，结构和位置映射 | 不改 RAG ParsedDocument，不执行公式/宏/链接 |
| mainline1 配置与检测 | 可信上下文、版本化字典/规则/政策、语义适配/校验/融合、分层覆盖 | 内部等级来自政策，不生成法律/外发决定 |
| mainline1 扫描任务 | ScanRunSnapshot、ScanRun/Attempt、受管 worker、取消/预算/幂等 | 复用 ORM 和 RAG token 模式，不复用教学任务表或 Web 裸后台线程 |
| mainline1 画像/复核 | 不可变发现与画像，追加复核、当前链、适用性权威查询 | 不覆盖人工结论，不撤销主线二/执行模块数据库对象 |
| mainline1 计划 | 保护要求到白名单计划、无业务写入验证 | 不创建输出副本、共享、配额、执行授权 |
| 审计/事件支线 | 消费最小事件，独立投递适配 | AuditEvent/哈希链非可靠消息总线；不写单元格/上下文/prompt 原文 |
| 主线二/执行支线 | 消费画像/适用状态/计划；决定后果并再次查询权威状态 | plan ready/hash 均不授予外发权限；实际执行由其负责 |
| 评估支线 | 固定数据/模型/配置/版本及独立标注；只读隔离结果 | evaluation_run_id 由可信服务决定，与生产缓存/权限隔离 |

数据流：鉴权 → 资产所有者确认 ready 固定版本 → 规范化范围/上下文/政策 → 事务创建逻辑运行和快照 → 返回 TaskReference → worker 认领 Attempt → 预算下解析/规则/语义/融合 → 事务发布不可变画像及适用状态 → 查询/追加复核 → 后继画像＋同事务 outbox → 下游重评估 → 生成固定计划 → 只读计划验证。任一外部/权限/覆盖失败走显式错误或 partial，不回退为空文本成功。

## 3. 身份、私有数据与所有权

API 复用 Session/Token 认证和 CSRF，但显式 IsAuthenticated；匿名只读默认不适用。权限矩阵草案：owner/operator 可创建并读取本域授权资产扫描；reviewer 可复核授权画像；policy_admin 可确认上下文和发布配置；service_executor 只读获授权计划/适用状态；auditor 只读最小历史；普通角色名本身不自动赋予所有资产权限。原文读取需要独立 `read_sensitive_source`，默认仅脱敏样本和依据码。

现有 CTFUser 只有角色、未见域成员模型，故域成员/资产 ACL 需要独立适配/持久化设计，不能把任意 role=teacher 映射为全域授权。development/test 可由服务端配置单一测试域与合成 owner，禁止继承为生产默认。客户端 domain_id/environment/evaluation_run_id/actor_id 不在创建输入 DTO 中；服务端从鉴权上下文和记录填入响应 meta。未知/跨域对象统一 404，避免泄露存在性。

私有存储句柄必须是不可解析不透明 ID，仅服务端 AssetReader.resolve 使用；禁止普通 API 暴露物理路径、预签 URL 或存储直链。原始文本、映射、模型输入/输出仅受控引用；ParsedAsset/BusinessContext 完整结构是内部/有权限接口，不默认返回完整原文。审计仅 trace/id/版本/原因/计数/耗时，不写任意 filename/异常字符串。读取资产时重新检查权威 ready/版本/hash/ACL，不能仅校验一致性 hash。

## 4. 表格与位置语义（跨线 Proposed）

- 行列均一基，包含表头。CSV row 是逻辑记录序号，引号内换行不增加记录号；XLSX row/column 是原始表坐标。CSV sheet_id=`csv:0`；XLSX sheet_id=`xlsx:0` 等原始 sheet 顺序标识，仅在同一资产版本稳定；显示名称单独存 structure_ref，禁止据名称跨版本匹配。
- DataScope 使用已排序、不重叠闭区间。显式范围，不用空数组表示全部；先读取结构清单后展开全选，合并邻接区间、去重 sheet，固定 include_header 和版本后计算 scope_hash。范围跨合并区域但不含锚点时返回 SCOPE_INVALID，不偷偷读取范围外原文。
- 字符 span 使用零基 Unicode 码点 `[start,end)`，不是字节、UTF-16 code unit 或 grapheme。JS 用 `Array.from(text)` 对码点切片；向 DOM UTF-16 offset 转换时累计每个码点的 `.length`，不能直接用 Python offset 调用 string.slice。组合字符保留多个码点，不擅自 NFC/NFKC。
- 首版 normalization=`identity-v1`。CSV 原文指解码后逻辑单元格值（CSV 结构引号/转义已去除，格内换行保留）；XLSX 原文指单元格存储值的约定文本通道，保存原始类型、数值/日期原始表示与格式信息到 structure_ref，禁止依据显示格式补造丢失前导零。数值/日期转文本序列化规则必须由解析版本固定（十进制原始标量；布尔 true/false；错误值保持错误类型并计覆盖缺口），不得依赖区域设置或浮点格式化。
- 重复/空表头保留原字符串，列索引是身份；无表头显式 null。CSV 空字段为空字符串；XLSX 缺失格与空字符串区分记录类型，不自动视为零。空文件报 PARSE_FAILED/EMPTY_ASSET；不规则 CSV 列数显式 PARSE_FAILED，不填补后宣称完整。
- CSV 明确 encoding/delimiter/quotechar/doublequote；允许 CRLF/LF/CR 记录分隔，用 newline-preserving reader；不确定编码/方言要求显式配置，不采用 latin-1 万能回退。BOM 只由 utf-8-sig 处理；不静默剪裁空白。
- XLSX 默认纳入隐藏行/列/sheet；排除必须在 scope/coverage 指明。合并区域只检测锚点一次，其他格指向锚点且不重复计算发现。公式仅扫描公式文本（channel=formula），不计算、不下载外链、不依赖缓存值；未扫描缓存值作为限制。拒绝宏格式/宏条目、加密或损坏 ZIP、重复危险条目、外部关系的主动解析；可记录外链存在但不请求目标。批注、超链接目标、文本框、图像等首版明确排除，不能称整个工作簿均扫描。
- 预检 ZIP 条目数/声明大小，流式累计实际解压量；读取行/列/格长度/时间限制，不信任 workbook dimension。超预算记录已处理和失败/跳过范围；无可靠分母 ratio=null。不得忽略越限或无效单元格并输出 complete。
- 后续 normalization 变更必须保存逐边界或区段逆映射；无法准确映射时可留发现，不能生成 span 替换。整格处理也必须由保护政策允许并满足原文匹配条件。

## 5. 配置快照、分类和模型

BusinessContext 按来源保留 version；user_input/model_inferred 仅辅助证据，不能原地改为 confirmed。人工确认创建新版本，来源仍可追溯，confirmed_by/confirmed_at 必填；model_inferred 直接 confirmed 被拒绝。冲突文本不得降低强证据政策等级。

ClassificationPolicy 配置加载检查类别/规则/等级重复、悬空引用、循环或矛盾映射；levels 是内部有序集合，不声称法定等级。每个版本 immutable，draft→active→retired 由授权发布控制；active 后变更内容必须新版本。未命中不是 unknown 数据类别，也不是必须待复核：已完整检测未发现记录为空发现+coverage；未扫描/失败/证据不足分别表达。score_meaning 与概率分开，校准版本未知则概率 null。组合发现必须引用至少两个位置/来源且输出关系建议，不作可重识别/合法性结论。

ScanRunSnapshot 保存所有影响结果输入、模板、版本、完整受控配置、原始资产、规范化范围、主体授权作用域、模型参数、预算、seed。跨对象引用必须同域/环境/评估身份；元数据之外的身份不能由客户端覆盖。模型修订无法固定时记录 reproducibility_limits。

摘要草案：原文件为字节 SHA256；结构对象使用 `canonical-json-v1`：UTF-8、键按 Unicode 码点排序、无空白、数组保持领域规定顺序、字符串不做 Unicode 归一化、禁止 NaN/Infinity、JSON 数字按十进制整数或 Decimal 最短非指数表示（-0→0）。不得依赖任意语言默认 JSON 浮点输出；跨语言需要黄金字节样例。scope/plan/request 指纹各使用明确投影（scope 排序选区+include_header+asset_version+coordinate_version；plan 包括 ID/所有版本/要求/完整操作/状态/校验引用，排除 plan_hash 与 meta.trace_id；request 排除 idempotency_key/trace/timestamps，加入 principal/domain/environment/evaluation）。相同幂等键请求按首次已解析版本快照比对，不因当前默认配置变更改变旧请求的解释；显式变化必须冲突或新运行。

默认语义关闭，不读取/验证凭据。拟议后续真实烟测只发固定合成文本；具体 provider/model/修订/端点数据驻留和调用预算待用户批准。复用 BaseProvider/ChatResponse 的传输边界，单独适配主线一参数与结构校验；DeepSeek 现有实现忽略 kwargs，不能假称温度/输出上限已生效，也不直接修改全局教学默认。不得使用 get_manager 自动跨厂商 fallback 向未批准端点转发。

语义输入只能含批准的目标格、表头、相邻字段、业务描述；只作为数据，不提供工具/网络/执行代码权限。输出 schema/类别白名单/数量长度/原文片段/码点位置/证据引用逐项验证；失败可保留规则结果并标记 semantic partial/failed。无语义时不拿 local-hash-v1 或规则模板填充结果。分类业务真实实现和效果均尚未测试。

缓存键为作用域+principal授权分区+environment+evaluation_run_id+资产hash+scope_hash+context/policy/rules/model/revision/prompt/fusion/parser/sampling/seed/budget/scan_policy 的规范化指纹，禁止以原文直接为键。读取仍校验当前 ACL/资产状态。无可靠模型修订时缓存记录限制并设有效期；取消/失败/部分结果不作为完整缓存命中。首版默认禁用跨运行模型缓存，后续开启须有保留政策。

## 6. 异步扫描、尝试与状态

`run_scan` **只返回 TaskReference**；HTTP 拟议新接口 `POST /api/mainline1/scans/` 返回 202，重复请求也返回同 TaskReference（可已终态）；查询返回 ScanResult。不与已有 RAG 同步 201 接口混用。输入仅 asset_version_id、scope/config/version refs、idempotency_key；主体和环境来自服务端。固定同步纯函数解析器可内部使用，但不改变 public run_scan 返回。

逻辑运行 ScanRun 与 Attempt 分离：Run 保持相同 scan_id/snapshot/request 指纹；每次尝试新的 attempt_id、单调 attempt_no、随机 lease_token、lease_expires_at、heartbeat。Run queued→running→succeeded/failed/cancelled；failed 可经 retry→queued（不更改旧 Attempt）；succeeded/cancelled 不重开；主动重扫用新键/新 run。Attempt queued→running→succeeded/failed/cancelled/expired；取消 running 时先 cancel_requested_at，worker 停止并完成清理后终态 cancelled；不能只改 UI 就声称已取消。

同 domain/env/evaluation/principal/operation/idempotency_key 唯一；相同规范化请求重放同 Run，不同 fingerprint 返回 IDEMPOTENCY_CONFLICT。retry 自己具有幂等键并绑定 expected_attempt_no；只允许失败且未发布画像、未超过 max_attempts/累计预算、快照仍可验证的 Run；预算累计不因重试清零。旧 worker 只能以当前 attempt/token/status/lease 进行条件更新；超时 worker 无权覆盖新尝试。cancel 和 publish 在同一 Run 行锁下串行化：取消先提交则不得发布完整画像；发布先提交则取消返回 TASK_TERMINAL，不销毁已发布结果。

受管 worker 草案：Django management command 常驻/--once，由进程管理器托管；短事务 `select_for_update(skip_locked=True)` 认领；租约到期先标记旧尝试 expired，再在预算内排队新尝试。外部模型/解析在事务外，最终 token 校验后提交；失败保留最小错误码/阶段。不是 Web 请求起线程，不引入 Celery/Redis 新依赖。SQLite 只可做纯函数/串行样例，不能冒充 PostgreSQL 并发验收。队列故障恢复与生产进程管理目前 Untested。

ScanResult.task_status=succeeded 表示扫描流程正常结束，quality 可以 partial（如语义不可用）；complete 仅按快照扫描政策所要求各层 target 全覆盖、无缺口/错误/未解决范围判定。空目标数量=0 时 ratio=null、状态按明确空范围策略，不伪造100%；禁止 complete profile 覆盖 required 层 not_run。未运行/失败不能被空发现列表掩盖。部分结果可形成只读 partial profile，但取消不发布 complete；重试已发布 partial profile 必须新 run，避免覆盖历史。

## 7. 复核、画像链和适用性

submit_review/add_manual_finding 都绑定 base_profile_id、expected_state_version、幂等键和原因。事务内锁同 domain+asset_version+scope 的 ProfileHead，再核查当前 head/适用状态。同键同 fingerprint 返回同 ReviewRecord；同键不同内容 409；并发版本落后返回 REVIEW_VERSION_CONFLICT，只有获授权者才获 latest_profile_id。所有确认/修正/误报/补录都追加记录，并生成唯一后继画像（即使类别不变也固化复核状态）；旧发现/画像/计划不改写。新画像继承仍适用发现引用，修正创建新发现；误报在新画像移除活动发现但保留原始证据与记录。等级重新按政策算，首版不提供人工等级例外。

复核 pending 与 completed 独立于 accepted/rejected 及 conclusion；被拒请求 conclusion/successor 为 null，不能转 false_positive。漏检补录 source_type=manual，detector_id/version=null，created_by/review_id 必填。融合 source_finding_ids 保留来源，不伪造成单模型判断。

每个画像有独立可变 ProfileApplicability：current→superseded / reevaluation_required / unverifiable_deleted。禁止终态恢复旧画像为 current；重新评估后产生新画像。superseded 必有新画像，policy 更新而证据不足为 reevaluation_required，资产被删除无法验证为 unverifiable_deleted；state_version 单调，历史内容仍 immutable。旧画像是否可审计单独 historical_audit_available；不等于可用于新决定。

ProfileHead 同资产版本+scope 的 canonical current 唯一；并发重扫发布须 CAS head 版本，落后运行可保留历史 partial/complete 结果但不得抢写 current，记录 PROFILE_HEAD_CONFLICT。不同 scope 可并存；重叠 scope 的人工补录可能影响其他画像，须事务或受管任务标记重叠范围 reevaluation_required，未能确定交集时保守标记；不能仅维护完全相同 scope 的链。

同事务追加 OutboxEvent（ProfileChangedEvent），包含 event_id/old/new/asset/scope/reason/aggregate_version；发布至少一次、消费者按 event_id 去重、按 aggregate_version 拒绝旧状态回退。失败重试不删除已提交业务结果；留 dead-letter 待处理。无已批准外部信封，适配器默认未连接，不能把本地 outbox 叫真实投递。建议延迟目标30秒、告警60秒（待共同批准，非实测 SLA）。下游处理延迟不构成使用旧结果的理由。

`get_profile_applicability(profile_id)` 为权威查询，返回当前状态/version；执行前要同时校验资产/授权/政策及状态，查询失败、超时或非 current 时建议 defer/fail-closed，须执行方共同确认。校验结果不提供跨模块事务锁或防止检查后变化的执行授权；执行层须在其最终准入事务中按共同契约处理变化/再检查，主线一不保证零 TOCTOU 窗口，也不直接撤销下游决定。

## 8. 计划共同语义与纯验证

RedactionPlan 绑定 asset/hash、scan/profile/scope、解析/政策、规范化要求及摘要、完整操作清单和 operation_contract_version。首版只允许 mask_span、mask_cell、drop_column；固定 replacement=[REDACTED] 作为字面字符串写值，不执行公式、不接受代码/路径/表达式。一致替换/类型保留等若保护要求必需而首版不支持，返回未解决/invalid，不暗中降级。

所有 target 指向同一原始快照。语义定义为原始列 ID 被删除则最终不存在；保留格的字符替换以原文区间同时解释，整格覆盖以原格解释。禁止同列 drop_column 与其中 mask 并存；禁止同格 mask_cell 与 mask_span 并存；重叠 span 返回 PLAN_CONFLICT，相同重复操作规范化去重。允许“删除 A 列＋原 B 列字符处理”，执行方不得将 B 的坐标误当删列后坐标。这里只定义输入输出等价性，不规定执行方先删列、倒序替换或重建表的内部算法。

match_ref 指向主线一/资产 owner 内部存储的受控内容比较材料，执行方经认证请求校验；禁止对外公开手机号等低熵值裸 SHA256。内容比较、位置有效性和公式通道验证失败返回 LOCATION_MISMATCH；结构操作不得涉及未授权范围。所有 finding/requirement 引用必须存在且在当前 profile/请求范围。

ready 必须版本、范围、位置、参数、互斥、保护要求覆盖、当前画像/状态全部通过且 unresolved/errors 为空。partial 表示可描述部分措施但未满足全要求；invalid 表示当前不能用。所有状态均没有外发授权。生成计划的幂等键绑定固定完整输入，不能因翻页时画像变化产生混合操作。校验结果为 `{valid, error_codes, plan_hash, observed_asset_state_version, observed_applicability_version, checked_at}`，不写业务对象/状态，不创建输出、不预占额度；仅批准的最小访问审计可独立追加。

复核生成新画像后，旧计划本体仍保留其原 status/hash，但再次 validate 必须拒绝 PROFILE_SUPERSEDED；不原地将 immutable 计划改为 invalid。新状态是本次校验结果，而不是伪造历史计划内容。计划生成方与执行方对坐标、覆盖、时序、防检查后变化及版本类型必须共同确认后方可接入。

## 9. 服务、分页与稳定错误

所有接口路径为新 namespace 草案，未发布。请求 DTO 只接受下列业务输入，拒绝额外字段；Idempotency-Key 可来自头部但规范化后存服务端。

| 服务 | 输入（除可信 actor 外） | 返回与 HTTP |
|---|---|---|
| run_scan | asset_version_id, scope, context/policy/config refs, idempotency_key | TaskReference /202 |
| get_scan | scan_id | ScanResult /200 |
| cancel_scan | scan_id, expected_attempt_no, idempotency_key | TaskReference /202；已发布终态409 |
| retry_scan | scan_id, expected_attempt_no, idempotency_key | TaskReference /202 |
| get_profile | profile_id | SensitivityProfile /200 |
| get_profile_applicability | profile_id | ProfileApplicability /200（不缓存权威准入读取） |
| list_findings | profile_id, cursor?, page_size? | 固定 profile 的 results,next_cursor,total_count,profile_id /200 |
| submit_review | base_profile_id, expected_state_version, action, finding_ids, category?, reason, idempotency_key | ReviewRecord /201；重放200 |
| add_manual_finding | base_profile_id, expected_state_version, locations, category_id, reason, idempotency_key | ReviewRecord /201；新 Finding 为 manual |
| compare_scans | before/after_scan_id, matching_version | ScanComparison /200 |
| build_redaction_plan | profile_id, expected_state_version, scope_hash, requirements, idempotency_key | RedactionPlan /201；重放200 |
| validate_redaction_plan | plan_id, expected_plan_hash | 纯 ValidationResult /200，valid=false 含业务错误；鉴权/无对象按HTTP错误 |
| get_redaction_plan | plan_id, cursor?, page_size? | 不可变计划分页视图 /200；供执行支线 E8 消费 |

分页固定 profile_id/plan_id/parsed_id，按稳定 UUID 排序；游标是带签名的不透明 scope+object+last_id+filter_hash+page_size+expiry，page_size 默认50最大200，游标过期返回 CURSOR_EXPIRED，不能悄悄切换当前画像。分页 plan_header 含完整 plan_hash、总数和操作清单摘要，各页带相同引用；执行方先收齐核验，不对单页当完整计划。解析/mappings 私有分页与普通 findings 权限分开。

| 错误码 | HTTP | 语义 |
|---|---|---|
| AUTHENTICATION_REQUIRED / PERMISSION_DENIED | 401/403 | 未认证/操作权限不足；不存在或跨域对象统一 OBJECT_NOT_FOUND 404 |
| OBJECT_NOT_FOUND / ASSET_DELETED | 404/410 | 410仅向有权读取删除标记者返回 |
| ASSET_VERSION_MISMATCH / ENVIRONMENT_MISMATCH / DOMAIN_MISMATCH | 409/403/404 | 版本或可信作用域不匹配，无敏感详情 |
| UNSUPPORTED_FORMAT / PARSE_FAILED / EMPTY_ASSET / SCOPE_INVALID | 415/422/422/422 | 格式/解析/空输入/坐标范围错误 |
| RESOURCE_LIMIT / BUDGET_EXHAUSTED | 413/429 | 资源或累计调用预算；不自动无限重试 |
| PROFILE_NOT_READY / COVERAGE_INSUFFICIENT | 409/422 | 未发布画像/保护要求覆盖不足 |
| DETECTOR_UNAVAILABLE / MODEL_OUTPUT_INVALID / LOCATION_MISMATCH | 503/422/409 | 后端不可用、输出无效、原文失配 |
| CONTEXT_INVALID / POLICY_INVALID | 422 | 配置/确认/引用校验失败 |
| PLAN_CONFLICT / PLAN_HASH_MISMATCH | 409 | 操作冲突/完整计划不匹配 |
| IDEMPOTENCY_CONFLICT / REVIEW_VERSION_CONFLICT / PROFILE_HEAD_CONFLICT | 409 | 重放内容不同/并发版本冲突 |
| PROFILE_SUPERSEDED / PROFILE_REEVALUATION_REQUIRED / PROFILE_UNVERIFIABLE | 409 | 不可用于新的决定，旧内容仍可按权限审计 |
| TASK_CANCELLED / TASK_TERMINAL / STALE_ATTEMPT | 409 | 取消、终态操作或旧尝试写回 |
| APPLICABILITY_UNAVAILABLE / CURSOR_EXPIRED | 503/409 | 权威状态不可查/游标失效 |

错误 envelope 不携带原文、数据库错误和路径；最新版本引用先鉴权。所有失败是否 retryable 由服务端错误分类和预算共同决定，客户端不可提升。

## 10. 数据保留、预算与 delivery_mode

设计基线选用 **backend_only（Proposed）**：提供相同服务、样例和管理命令；minimal_ui 是用户可选的扩展交付，不自动展开导航改版。UI 若批准仅复用 LegalWorkspace/布局/Axios，添加上传范围、任务、结果覆盖、复核和版本比较；现有 response.data 已解包，保留旧同步 API。第8步才执行 UI 接入。

合成开发预算建议：20 MiB 文件、每sheet 100000行、256列、单格32768码点、ZIP 2000条目/100 MiB解压、总300秒、同域并发1、最多2次尝试；模型默认 calls/input/output=0。以上是待批准开发限制，不是性能承诺或生产默认。生产缺少预算时拒绝启动，不能无限制读取。

| 数据 | 所有者 | 建议开发保留/清理条件（Proposed） |
|---|---|---|
| 原资产及资产墓碑 | 资产所有者 | 不由主线一删除；资产 owner 定保留策略；仅请求删除并处理引用失效 |
| 临时解析/映射 | 主线一 | 活动运行保护；终态后24小时可清理，复核/计划需要重建时重新校验资产和配置；有依赖则延迟 |
| 模型缓存 | 主线一 | 默认关闭；批准开启后建议24小时，域/评估隔离，无原文键 |
| 配置快照/发现/画像/计划/复核证据 | 对应对象所有者（主线一） | 建议合成开发30天；删除经预览、引用/保留例外检查；仅最小墓碑，不默认无限保留原文 |
| 独立评测数据/标注 | 评估支线 | 冻结版本保留至该轮验收结束；具体天数待定，不并入生产清理 |
| 审计/投递记录 | 审计/事件所有者 | 主线一不得直接删除；最低审计字段由其政策决定 |

清理默认 dry-run，输出 ID/计数不含原文；实际删除必须有已批准规则和作用域，保护活动任务、复核、计划引用和保留例外。失去重放证据时设置 unverifiable_deleted，不保留无必要原文来假装不可变。当前本步不清理任何数据。

## 11. 最小文件/迁移草案与回滚

后续拟新增独立 `backend/mainline1/`：contracts/ DTO、parsers/csv_parser.py与xlsx_parser.py、scope.py、snapshots.py、permissions.py、models.py、services/{scan,review,applicability,plan}.py、detectors/{rules,semantic,fusion}.py、adapters/{asset,provider,audit,event}.py、config/*.json、management/commands/{run_scan_worker,cleanup_mainline1}.py；按第3—8步逐项落地，不一次建立空壳整树。现有代码只必要注册 settings.INSTALLED_APPS/root URLs 和明确适配函数；不改 resources/RAG/教学模型主键和公开语义。

下表为总体迁移草案。第3步已编写 ParseRun/ParseAttempt/ParsedArtifact 的独立迁移，并仅在新建隔离 PostgreSQL 验证正反迁移；其余未实施。业务库未迁移：

| 拟议表 | 关键字段/约束与动机 |
|---|---|
| 既有资产 owner 的版本引用适配（不新建跨模块资产系统） | owner/domain、private_ref、byte_hash、版本状态从权威 owner 获取；不可覆盖 bytes；不能直接挂 resources 文件当私有资产 |
| DomainGrant/AssetGrant（或已批准权限适配） | domain、user整数外键、capability、asset scope；域查询索引；不用教师角色隐含全权限 |
| ContextVersion/PolicyVersion/ScanSnapshot | 不可变 JSON 与受控引用/hash/version；unique(owner,id,version)，无原文日志 |
| ScanRun | UUID、trusted scope、principal、idempotency_key/fingerprint、snapshot FK、current_attempt、cancel_requested_at、status；唯一幂等作用域约束 |
| ScanAttempt | FK run、attempt_no、lease_token/expiry、budget counters、stage、processed/total、status；unique(run,attempt_no)；终态不可重写 |
| ParsedArtifact/Finding/Profile | immutable parsed/version/coverage、发现来源、画像 policy/scan/scope/前驱；人工引用允许 detector null；FK保护历史 |
| ProfileHead/Applicability/ApplicabilityHistory | unique(domain,asset_version,scope_hash) 当前指针与state_version；状态历史追加；CAS/行锁解决复核与重扫竞争 |
| ReviewRecord | base/expected/fingerprint/action/reason/actor/result；unique(scope,actor,operation,idempotency_key)；追加，不静默覆盖 |
| RedactionPlan | 版本引用、要求/操作私有清单、hash、生成时校验状态；不可变 |
| OutboxEvent/DeliveryAttempt | 事件与业务事务同提交；event_id唯一、aggregate_version、next_retry_at、ack；无敏感正文 |

后续公开集成迁移拟依赖 swappable AUTH_USER_MODEL 和已确认资产服务；第3步内部任务表只保存受信任主体/资产引用，不擅自建立用户或资产外键。不在现有应用历史 migration 上修改。编写迁移、隔离 PostgreSQL 数据库验证、业务库迁移执行分别列授权，不互相推导。无 Redis/Celery/新模型 SDK；jsonschema 4.26.0 是当前检查环境已安装工具，未加入 runtime requirements；生产 DTO 校验方案不由此新增依赖。

兼容性：新增 namespace，不更改旧 RAG hash 去重/任务 status 枚举；不把 AgentRun 已有201转202；不改 BaseProvider 原签名和教学默认；不改 Axios 响应解包；新 asset UUID 通过适配明确映射执行模板 asset_version_id，其未声明类型不能猜已兼容。执行模板 E2—E8 仅待核对模板，非批准契约。事件中心暂无正式信封，本地 schema 先 Proposed，正式接入需共同映射。

回滚（后续实现计划）：逐模块关闭入口/worker、拒绝新任务、完成或取消活动尝试、停投递；保留审计及已引用历史。代码回退与数据回退分开；新增表已存在引用时不得盲目 reverse/drop，先评估保留/导出和兼容读；外部资产不在主线一回滚范围。本步回滚：恢复 history/handoff-step-01.md 到 HANDOFF，仅撤回 step02 新产物（若已有后续编辑则按差异恢复），保留 step01 和用户提示词；不用 git reset/clean。

## 12. 决策与后续前置

[D01] 交付模式：建议 backend_only（较小范围，服务/样例/管理命令齐全）；minimal_ui 增加第8步真实页面/权限/端到端验收成本。未答复则作为设计推荐，不视为用户批准或业务实现指令。

[D02] 跨线契约/资产所有权：建议按本草案的独立资产 owner、原始快照坐标、权威适用性查询和 original-snapshot 操作语义，由资产、主线二、执行、审计相关 owner 共同确认；替代是提供既有正式契约后映射。确认前可设计/开发内部纯解析与测试替身，不发布跨线 API、不把草案强加执行方。

[D03] 生产持久化接入待决：用户本轮要求补齐第2/3步，结合规范B4，已授权内部仓储/迁移文件编写及新建合成隔离库验证；不再把它们误记为全部Blocked。业务库迁移、生产app注册/worker部署仍未批准。推荐正式环境确认后仅启用三个解析领域表；替代继续仅隔离运行。不得索取或记录业务库凭据。

[D04] 真实语义：默认继续关闭；需要用户给出/选择 provider+model、数据路径与预算后另行批准合成烟测。建议首轮最多20次调用、每次目标输入≤2000 token/输出≤1000、总输入≤40000/输出≤20000，最大费用必须由用户明确币种金额（未知时不调用）。可替代批准本地离线模型，仍需资源和模型标识。真实个人/敏感原文出域不包含在合成授权中。

[D05] 数据/资源策略：第10节开发预算/24h与30d仅候选；生产期限、资产/审计 owner、保留例外与通知时限均待共同确认。未经批准的实际删除/生产配置不执行。

第3步：用户明确启动后，内部 csv/openpyxl 解析、范围、位置及合成样本可在不新增依赖/不公开接口下推进；真实资产服务受D02约束；DB并发隔离验证已完成，生产接入仍受D03约束。第4步需解析契约与字典/等级政策版本。第5步真实语义需D04，降级/替身可独立。第6步需复核及适用状态/事件契约。第7步需执行方操作语义共同确认。第8步需D01与保留/权限策略。第9步需冻结独立标注集、真实后端/预算及下游契约；无效果阈值只报告实际结果。第10步仅对已实现/已验证内容交付，不自动部署。

## 13. 第2/3步审查补充（2026-10-13）

- 全部14个公共契约保持 Proposed，schema/examples 的公共字段与坐标语义未变。所有权说明改为消费既有资产 owner，撤回“另建 asset_registry”的建议。
- 生产全链路的 ScanRunSnapshot/TaskReference 与本步 ParseRun/Attempt 是不同层级：后者的成功只表示私有 ParsedArtifact 已保存；不得转换成扫描 succeeded/质量 complete，更不能代表复核或外发授权。
- 本步采用现有 Django 事务/行锁/ownership-token 模式，独立解析领域表；没有可直接复用的通用队列。认领由 revision CAS 和短父行锁保证唯一，不承诺 skip_locked 公平调度。过期尝试失败后需显式受限重试，避免未经选择自动重复错误输入。
- 内部 AssetRef→公共 AssetVersionRef 必须由 owner 补齐可信 meta、规范ID、删除状态；Scope→DataScope 需要公共版本/指纹桥接；ParseResult→ParsedAsset 需要私有引用、覆盖单元和逐格映射适配。当前没有公共序列化器，禁止直接 asdict 后作为契约响应。
- 内部 coverage.parse 分母只含选区内实际有效格，表头/隐藏/合并别名在 excluded_locations 逐项记录；rule/semantic/combination 为 not_run。公共 CoverageLayer 适配须保留这些事实与单位，不能只补一个complete标志。
- 默认 identity-v1 与公共v1一致；内部 opt-in nfkc-mapped-v1 保存原文和 Unicode 版本，完整组合序列逆映射，跨序列映射无法证明时字符操作失败关闭。公共v1不接收此扩展；采用它的公共消费者需另立契约版本，不能静默更改本草案。
- 第3步内置资源值仅约束内部合成验证。读取/解析各为协作式300秒，非生产总300秒硬预算；缺少进程级隔离不能宣称CPU/RSS或硬截止达标。生产资源策略和保留时限仍D05。
- 回滚当前补齐只撤回本任务文件增量；不得再直接恢复第1步HANDOFF而丢弃有效第2/3步记录。历史副本只用于追溯。
