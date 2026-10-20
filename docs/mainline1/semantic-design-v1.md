# 第5步语义适配与融合边界（内部v1）

状态：内部实现；公共契约仍 **Proposed**。真实模型、数据外发与金额预算未获批准，本轮实际模型调用为0次。没有证明上下文改善识别效果。

## 输入、所有权与数据路径

`fusion.scan_context(ParseResult, RuleResult, SemanticConfig, *, backend=None, approval=None, target_keys=None, context_parsed=None, combinations=(), cancelled=...)` 是受管worker可调用的异步内部函数，不是HTTP接口。本步不改解析worker、数据库、公共Schema或资产owner；不创建线程、后台队列、RAG索引或embedding。输出仍为私有`RuleResult`容器，不能直接公开序列化。

调用方必须完成资产、域、主体、环境及范围授权。解析字节摘要、版本、范围、解析配置、实际格摘要必须与第4步规则快照相同。`context_parsed`只能由owner额外授权读取**同一固定版本**的快照提供；函数不自动扩范围。缺表头则记录`HEADER_UNAVAILABLE`，不猜测。此参数与`LiveApproval`/`CombinationSpec.approval_ref`都是可信内部配置，不是客户端可自报的授权证明。生产owner适配仍未完成。

数据流：已授权私有ParseResult → 固定模板请求 → 显式后端 → 严格输出校验 → 原文映射 → 规则/语义融合 → 基础画像扩展。每个目标单独请求；目标最多100格，每批调用默认最多6次、上限20次。规则仍只看原目标，未改其输入可见性。

B模式只给目标规范化全文和类别定义；C模式追加本列表头、同一行左右相邻字段和带来源/版本/确认状态的业务说明。表头/相邻字段最多256码点，裁剪有显式限制码；总输入超预算时先移除辅助上下文，绝不裁剪目标。目标本身超限则`MODEL_INPUT_LIMIT`，不返回空成功。业务描述即使来自用户，也不自动成为已确认事实。

## 模型边界与批准条件

`semantic.py`定义`SemanticBackend`、不可变请求/响应容器和`LangChainSemanticAdapter`，复用仓库既有`langchain_openai`运输依赖。没有安装新依赖。未复用`ai_providers`包自动注册入口，原因是其`__init__`会加载环境且管理器允许跨provider路由；现有DeepSeek调用路径也不能据kwargs证明本次预算参数生效。本适配器要求显式注入凭据、已批准HTTPS端点、provider/model及已验证本地token计数器，不读取.env、不自动选模型、不自动降级到其他provider。

固定`context-semantic-v1`模板、temperature=0、max_tokens、request_timeout、streaming=false、max_retries=0。没有绑定任何工具；响应带tool_calls或非stop结束原因时拒绝。报告的模型名若与配置不同则拒绝；provider未报告模型名时只能保留请求名，不能据此证明实际修订。当前适配器不支持固定revision，非空revision拒绝；画像记录`MODEL_REVISION_UNPINNED`，temperature=0不保证服务端输出确定。

真实调用前验证可信`LiveApproval`的source/provider/model/endpoint/domain/environment/asset_hashes以及调用、输入token、输出token和金额预算。金额使用整数微单位及显式币种、保守的每token上界价格；未获取报价或编造价格。输入token计数必须包含system及user消息。每次发送前预留费用与最大输出token，超时/失败不自动退还；无自动重试。`asyncio.wait_for`加客户端超时限制单次等待，但超时不能证明远端停止计费。

**当前预算仅在单次函数调用内累计，不是持久化总账。** B/C两批、进程重启、重复执行和多worker不能共用此内存计数冒充累计保证。首次真实烟测必须分配不可超出总额的独立B/C额度并禁止重放；生产/可恢复任务接入前需要owner提供持久化预留及尝试账本。真实端点、计数器、计费、取消服务端行为全部未验证。

## 严格输出与定位

模型只允许返回以下完整JSON，拒绝额外字段、重复键、Markdown包裹、NaN/Infinity、越界/布尔索引、未知类别、未知证据及过量/超长结果：

```json
{"target_id":"target:0","findings":[{"category_id":"email_address","start":0,"end":17,"quote":"a@example.invalid","evidence_ids":["target:0"],"raw_score":null}]}
```

所有字段必填；只有raw_score可空，非空为有限未校准数值（绝对值≤1e6），不推导概率。offset是规范化目标Unicode码点、零基半开区间；quote必须逐字等于切片，证据必须引用该目标且只能引用实际发送的target/header/neighbor/business-context ID。校验失败整格拒绝，不做正则捞JSON、模糊查找、补位置或默认类别。

每格默认最多20条、响应最多16000 UTF8字节。该长度限制是在运输层接收后实施，不保证HTTP缓冲区硬字节上限；生产网络层还需相应资源约束。模型分数只保留在原始语义finding中；融合finding分数与概率均null。

通过`Cell.source_span`保留第3步原文映射。可靠时才生成原文span；不可靠或切开规范化展开时降为整格、`judgment=insufficient`、`LOCATION_UNRELIABLE`。不会据模型位置直接生成脱敏计划。公共v1仍使用identity，内部NFKC扩展未发布。

## 融合、来源与组合

版本`conservative-fusion-v1`。同类别、同原文位置去重；规则与语义一致时生成新fusion finding并引用两个源ID，仍待复核。不同类别重叠则分别生成冲突finding，保留全部来源；语义未命中/无效/失败不能抹去规则证据或降低已发现类别对应政策等级。证据不足不会因两来源一致而提升成确定结果。上下文conflicted会形成复核冲突，不代替人工裁决。

`source_findings`保留不可变源finding及融合中间节点；画像只计最终有效候选，避免去重前后重复计数。私有证据引用可回溯规则配置及实际请求证据ID；完整请求/上下文仅在私有快照，不写通用日志。异常仅记录稳定错误码，不保存模型原始异常或未通过校验的响应全文。

组合引擎只实现显式配置的同sheet、同逻辑行、不同列的2—4类别共现；默认没有任何组合规则。`CombinationSpec`固定rule_id/version/relation_type/categories/protection_level/approval_ref/test_only。未知类别/等级、重复ID/类别拒绝；test_only仅test环境可用，业务配置需可信owner批准引用。每规则行笛卡尔候选上限100、累计1000，超过则整体`COMBINATION_RESOURCE_LIMIT`，调用者须记失败，不能替换空完整画像。

测试配置`test-cooccurrence@1`只证明引擎处理邮箱格式+IP格式不同字段共现；L3仅开发测试值，**没有批准成为业务政策**。组合输出category_id=null、kind=combination、source_type=fusion、source_finding_ids、relation_type及多个位置，始终待复核并标记`NOT_REIDENTIFICATION_OR_LEGAL_CONCLUSION`。不宣称个人可重新识别或外发违法。

## 覆盖、错误、快照与留存

- parse/rule覆盖沿用既有结果；semantic分母是所有解析目标格，显式选取之外计skipped，成功无候选仍计processed，响应校验/调用失败计failed，未批准/预算拒绝计not_run或skipped。
- combination分母是“配置规则×扫描行”的关系评估单元；完成评估但无共现计processed，并非召回率。没有配置则not_run，不能称组合信息已全部检查。
- 测试替身的层覆盖描述程序分支执行，并带`TEST_DOUBLE_NOT_REAL_SEMANTIC`；画像quality强制partial。真实语义未运行时同样partial；即使后续quality complete也不表示复核完成、画像权威发布或外发授权。person_count始终不推断。
- `BACKEND_UNAVAILABLE/BACKEND_NOT_APPROVED/APPROVAL_SCOPE_MISMATCH`阻止dispatch；`MODEL_TIMEOUT/MODEL_OUTPUT_INVALID/MODEL_UNKNOWN_CATEGORY/MODEL_EVIDENCE_INVALID/LOCATION_MISMATCH/MODEL_ID_MISMATCH`均降级保留规则。TASK_CANCELLED终止并拒绝发布，任务调用方承担旧尝试fencing，本步没有改解析任务成功语义。
- 请求指纹包括原规则快照指纹、模板/system摘要、完整实际发送目标和上下文、模型配置、执行模式、批准快照及组合配置。变化上下文或配置不会命中旧指纹。缓存关闭，无跨运行复用；输出可能非确定，不能仅依请求hash声称两次模型结果相同。
- 内部`snapshot.semantic`是本步模型配置权威位置；旧`snapshot.model`来自规则快照仍为空，整个内部snapshot不是公共ScanRunSnapshot。后续公共适配须遵守原Proposed契约，不直接透出内部字典。
- 本步只返回内存私有产物，不添加持久化或清理策略。生产落盘、加密、ACL、审计与保留期仍由owner确认。未实现复核、通知、画像替代或外发计划。

## 可审阅真实烟测方案与待决策项

固定[合成样本](step-05-smoke-fixture.json)与[预检结果](step-05-smoke.json)，版本semantic-smoke-synthetic-v1；CSV字节摘要`sha256:952d825f6c96d0092b13b448852f42b7d0a932654e49741ffef4da5e8042e63d`。只选3个固定目标：邮箱、含IP的自由文本、提示注入字符串；C可见合成模糊表头/邻格/未确认业务说明。A使用同3格已有规则候选，B/C逐字相同目标；类别仍只有第4步开发基线3类。此窄样本不能代表医疗/金融等业务上下文效果。

建议批准范围：仅上述合成文件内容及其上下文，A不调用模型，B3次+C3次，总计最多6次，无重试，每次最大输入16000字节、输出1000token、20秒。模型修订未知需记录，实际token上限及币种/金额需按所选模型报价和本地计数结果明确后才能运行。只记录必要脱敏结果/错误/用量，不能外发真实业务数据。

| 决策 | 可选项及取舍 | 尚需提供 |
|---|---|---|
| D04-model/data/budget | 维持关闭：无成本但效果Blocked；批准现有兼容HTTPS服务仅跑上述合成烟测：可验真实路径；指定本地后端：避免外发但需验证本地适配 | provider、model、endpoint、上述合成路径批准、可信凭据注入方式（不要写凭据）、本地token计数器、币种及总费用/token上限、价格依据 |
| D05-combination | 默认关闭：不引入未经确认业务含义；owner批准具体共现类别/关系/等级：可启用对应规则，但仍只是待复核关系候选 | 正式类别/等级政策、rule_id/version/relation_type、批准来源；不直接采用测试L3 |

提出这些决策的依据是用户本步前置输入与执行1/5，以及完整提示词的模型/数据路径/成本和政策授权约束。它们只阻塞对应真实路径，不要求重新批准内部实现。

## 验证、限制和回滚

[89项验证证据](step-05-verification.json)：24项本步测试替身/边界测试+65项前序回归，4个新增Python源文件AST。含实际async等待超时与预算不退款的本地替身测试；“live”分支标签仅用于测试授权门禁，不是实际模型。适配器构造使用ClientDouble；网络SDK调用兼容性未验。提示注入测试仅证明内容处于数据消息、无工具/政策变更通道及输出白名单，不证明真实模型不会被诱导误判。

预检证明A/B/C目标可固定、B/C上下文组织可执行，不测precision/recall/F1或上下文提升；指标均null。正式实验单位/切分/指标沿用第2步验收，独立测试集未使用、未反复调优。本步未新增效果门槛。

回滚只撤回semantic.py、fusion.py、semantic_smoke.py、tests/test_semantic.py及本步文档，按差异撤回README/acceptance/HANDOFF增量；第4步交接在history/handoff-step-04.md。保留前序实现和所有用户文件；无数据库/生产配置/依赖迁移，不执行reset/clean。历史交接不可直接覆盖当前记录丢失信息。
