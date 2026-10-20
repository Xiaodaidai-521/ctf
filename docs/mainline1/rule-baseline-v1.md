# 规则基线 rule-baseline-v1

状态：内部开发基线已实现并验证；公共契约仍Proposed。不是生产分类政策或法定分级。

## 版本与可见信息

配置：[rule-baseline-v1.json](../../backend/mainline1/config/rule-baseline-v1.json)。字典`format-dictionary-v1`，规则集`format-rules-v1`，政策`synthetic-policy-v1`，引擎`format-rule-engine-v1`，复核策略`format-review-v1`。

规则只看选区中实际解析出的单元格文本和位置，不使用表头、相邻字段或业务描述来增加/否定命中。后续A/B/C实验中的规则路径必须保持这一可见信息集合；模型另行读取的上下文不能改变本基线。数字/公式通道也只按解析后的存储文本检测，不执行公式，不依据显示格式补零。

| 类别 / 内置实现 | 必要校验 | 开发政策等级 | 局限 |
|---|---|---|---|
| email_address / email_ascii_v1 | ASCII邮箱候选；local长度/连续点/首尾点、域名标签长度及首尾、域名点分结构 | L2 | 不验证邮箱存在、个人身份、国际化/引号邮箱语法；可能误报，遗漏不支持形式 |
| ip_address / ipv4_v1 | 标准库IPv4解析，八位组合法及字符边界 | L1 | 不支持IPv6，不证明主机所有权、网络角色或与个人关联 |
| payment_card_candidate / luhn_candidate_v1 | 13—19位连续ASCII数字、Luhn校验、拒绝全同数字与粘连字母编号 | L3 | 不验证发行机构/账户真实性；符合校验的订单号仍可能误报；不支持空格/横线分隔形式 |

L1<L2<L3的**列表顺序**是这份开发配置的排序，命中类别按配置映射取最高候选保护等级；不是正式全平台等级含义。无发现时等级null，不自动归一般数据。配置state=draft，只允许test/development，production请求明确拒绝。已有正式分类政策后由owner提供映射；本文件不是启用它的授权。

配置校验拒绝重复类别/规则/等级ID、悬空规则/类别关系、规则归属不一致、未定义等级、未知实现、非法状态/冲突策略及政策摘要不匹配。只允许三个内置实现，不加载任意正则或可执行代码。类别同时携带定义、别名、合成正反例、规则引用、关联关系、等级及复核条件。规则完整内容与配置摘要进入运行快照；版本字符串相同但内容不同也不会复用旧缓存。正式配置版本登记与生产激活不在本步。

## 调用与结果

入口：[classification.py](../../backend/mainline1/classification.py)的`load_baseline()`、`BusinessContext.create()`，以及[rules.py](../../backend/mainline1/rules.py)的`scan_rules()`。

调用方必须是已鉴权的内部服务：提供第3步`ParseResult`、可信meta/domain/environment/evaluation、principal、固定AssetKey、scan_id、实际私有parsed_ref，以及owner预留的applicability_ref。所有这些参数不是HTTP用户字段；每次调用（包括缓存命中）之前必须由资产owner完成对象鉴权。跨域上下文、错误资产版本/范围、配置摘要或伪完整解析输出会拒绝。

BusinessContext保存场景、用途、表/字段说明（坐标绑定）、来源、版本、确认状态及摘要。默认全部unconfirmed，包括admin_config来源；已确认状态必须由可信owner显式传ConfirmationReceipt。该内部对象不提供认证能力或公共确认入口，不能把客户端提交的同名字段当凭据。model_inferred不能变confirmed。用户指令样式文本始终是数据，不执行、不外发、不降低保护等级。

返回不可变`RuleResult.payload`；`data()`返回独立副本。内容包括：

- `findings`：兼容现有Proposed Finding字段，rule来源、原文位置、规则及私有解析证据引用；不带命中原文，不伪造分数/概率。格式候选默认pending_review；同格重叠不同类别为conflict；逆映射无法证明时保留整格位置和insufficient，不能生成字符操作。
- `profile`：兼容现有Proposed SensitivityProfile字段，类别计数是去重后发现数（不同位置的重复值不合并）；人数null；规则版本/政策/扫描引用明确。只有显式semantic_required=false且规则完整时quality可为complete，它只表示这份规则扫描要求完成；复核仍pending，未授予外发许可。
- `cell_outcomes`：内部诊断，独立表示no_match、not_detected、detection_failed、insufficient_evidence、conflict。空值是成功检查后的no_match，不是一般数据，也不强制待复核。
- `snapshot`：**内部快照，不冒充公共ScanRunSnapshot**。保存上下文和配置完整版本内容、解析配置/范围/输入摘要、引擎、principal/meta、model=null、fusion=not_run、全量采样与预算等。公共快照序列化需后续适配，不改变既有公共model结构。
- `manifests`：私有覆盖目标/实际/跳过/失败清单，`resolve_private()`解析包内清单和规则配置引用。parsed_ref由资产/解析owner解析；不是新建的HTTP地址。applicability_ref只预留，尚无发布/权威服务，profile明确APPLICABILITY_NOT_PUBLISHED。

本步不把规则服务接入原解析worker，不将`ParseRun.succeeded`改成扫描完成，不修改数据库或已发布接口。后续融合器可消费rule findings、原始位置、规则依据和快照；不能伪造semantic/fusion来源或把pending_review当已确认事实。

## 覆盖、预算和缓存

四层coverage分别报告。规则逐实际格检测，失败格保留原因且不算processed；禁用规则有明确跳过/不完整状态。解析排除列表保留在包内；只完成单元格解析不表示整本XLSX所有内容均覆盖。semantic/combination始终not_run，分母和比例null。取消抛TASK_CANCELLED，不返回完整画像；达到发现数预算标规则partial并保留已得到候选，不缓存失败/部分规则结果。

默认不启用缓存。可显式注入单进程`RuleCache(ttl_seconds=..., max_entries=..., max_bytes=...)`：TTL最多1小时，条数最多100，总UTF-8载荷最多64MiB（默认4MiB）；访问清除过期项，clear显式释放，不写磁盘或公共缓存。回收是惰性的，进程闲置时对象可留内存至下一次访问/clear/进程退出，不能当作生产硬删除时限。无线程/分布式幂等保证。

缓存键为受控SHA256，不直接用原文；涵盖domain/environment/evaluation/principal、scan_id及meta、资产版本/实际格摘要、解析配置/覆盖、上下文内容/版本、完整规则/政策/字典、要求和预算。当前只复用相同运行和完整输入；主动重扫的scan_id不同会miss。快照和摘要仅供内部比较，禁止写通用日志或公开输出，以免上下文原文或低熵摘要泄露。

## 验证及限制

从backend执行`python -B -m unittest discover -s mainline1/tests -v`。本步24项规则测试，加第3步41项回归，共65项Passed。新规则测试使用真实解析器与规则；只有故障路径注入异常，不用Mock制造正例。测试检查BusinessContext/ClassificationPolicy/Finding/SensitivityProfile通过未改动的草案Schema。

当前只验证固定合成功能样本，不是独立效果集；不报告准确率、召回率或生产性能门槛。真实语义未运行。真实资产owner、生产权限、正式分类/等级政策、画像持久化/权威适用性和公共发布仍待接入。CPU硬截止仍依赖受管worker；本纯服务只有输入/发现数上限和协作式取消。

回滚：本步仅新增classification.py、rules.py、config/rule-baseline-v1.json、tests/test_rules.py及本步文档/交接增量；保留第1—3步文件与用户原提示词。无需数据库回滚，不使用git reset/clean。
