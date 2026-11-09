# 数据安全契约（M0 冻结、纯核心与第3期适配）

设计依据：V2.0 §3.1–3.5、七期划分及 PHASE2-BRIEF；源文档及哈希见唯一实施报告 R。契约维护版本 `ds.m0.v1` 不变；这不是生产开通、策略批准或独立验收。原 M0 冻结说明保留在下文；第 2 期增量、算法及装配边界以末节为准。仓内文档固定为本文件、`operations.md`、`acceptance.md`，不另立设计体系。

## 1. 所有者与依赖矩阵（D14）

本期执行者承担后端契约维护职责；各原领域保留业务语义最终解释权。适配／部署角色负责外层实现；业务／数据所有者批准策略、必要原文和保留；独立验收角色负责放行。角色职责已登记，不冒充已指定生产审批人。

| 模块 | 位置／所有者职责 | 允许内部依赖（含自身） | 外部边界／禁止事项 |
|---|---|---|---|
| M0 | `backend/data_security/contracts/`；后端契约维护者 | M0 | 仅无副作用标准库；不得读取环境、数据库、Django、SDK 或业务包 |
| M1 | `core/redaction.py`，必要时 detectors/algorithms；契约维护者 | M0、M1、M3 | 纯识别／转换；不取策略、密钥、用户、时间或审计 |
| M2 | `core/policy.py`；契约维护者 | M0、M2 | 只解释显式批准快照；不查询 latest，不写库／日志 |
| M3 | `core/crypto.py`；契约维护者 | M0、M3 | 标准库及成熟 cryptography；显式密钥／盐／nonce；无隐式随机、环境、I/O |
| M4 | `application/`；用例维护者 | M0–M4 | 外部能力只通过 M0 Protocol；显式时钟／随机函数；不导入 M5–M9 实现 |
| M5 | `adapters/keys.py`；适配／部署角色 | M0、M5 | 唯一秘密读取；受信任引用清单及必要文件 I/O；无 ORM、SDK、任意目录搜索 |
| M6 | `adapters/persistence/`；按领域分文件 | M0、M6 | 本域 ORM／存储、age、被包装旧域服务；不得 HTTP、SDK、跨适配器写表或直接读秘密文件 |
| M7 | `adapters/llm/`；官方协议适配角色 | M0、M7 | 注入保护／审计／认证端口与批准的官方 SDK／HTTP 客户端；禁止裸 provider、独立规则、dotenv、ORM |
| M8 | `adapters/tabular/`；格式／旧域适配角色 | M0、M8 | 解析库及包装的旧公开边界；动作由 M4/M2 传入；不导入 M1 实现、不审批、不结算 |
| M9 | `adapters/django/`；HTTP／日志适配角色 | M0、M9 | Django、logging、必要 HTTP 客户端、注入的鉴权／用例端口；禁止自动全量 ORM→DTO、直接解密、秘密读取 |
| B | **唯一** `backend/ctf_backend/security_bootstrap.py`；部署装配角色 | M0–M9、B | 显式配置创建实现；其他模块不得反向导入 B；第 2 期只含测试注入和正式输入拒绝检查 |

运行时调用方向不等于源码导入方向。M7 可调用注入的 ProtectionPort，但不可 import ProtectionService；M6 可实现 QuotaPort，但不可导入 ExportFlow。唯一 PolicyCatalog／KeyResolver／AuditGateway 将分别落在 M4／M5／M4，当前数量均为 0，未以测试替身填补正式入口。M6 的 AuditSink 不回调 AuditPort；outbox relay 与 Sink 分离。各域继续拥有原表，不把 users/audit/export_risk/RAG 整体搬入 M0/M6。

`tools/data_security/dependencies.py` 检查上述静态导入方向、受保护模块的动态执行／导入、隐式 I/O／时钟、秘密配置旁路、反向装配及本期禁止的业务接线；违规测试包含全部 11×11 有向边、别名和相对导入。外层标准库／旧公开边界采用窄白名单，新增项必须复核并加测试。它不是 Python 沙箱，不能证明反射、运行时任意对象、每条 ORM 写入的所有权或 SDK 内部行为；后续必须结合调用点审查和端口故障测试，不能仅凭目录名宣称安全。

## 2. 公共数据、版本与失败规则

- 39 个具体 DTO 在 `CONTRACT_TYPES` 登记，19 个 Protocol 在 `PORT_TYPES` 登记。源码字段声明是精确结构；`tests/fixtures.py` 覆盖每个 DTO。
- DTO 为 frozen、slots、kw-only dataclass；集合为有界 tuple，JSON 为深复制的 FrozenJSON。不可变约束是编程边界，不抵御拥有同进程任意 Python 执行权的主体。
- `schema_version` 必须显式且精确匹配各类 `SCHEMA`。所有字段（包括可为 null 的字段）都须出现；多字段、缺字段、错误类型、未知枚举／schema 均拒绝。bool 不当 int、字符串不当数字；未知版本不靠缺省值补齐。
- `from_wire()` 只解码闭合类型图；无 eval、get_type_hints 字符串求值、用户 Python 路径、Any 或 SDK kwargs。`from_json()` 另拒绝重复键、NaN／Infinity、错误 Unicode／过深 JSON 及超长输入。
- 时间为时区感知 UTC；线格式固定 `YYYY-MM-DDTHH:MM:SS.ffffffZ`。校验不读取当前时间；到期／撤销／授权再检查是后续用例职责。
- 默认 repr 全部隐藏值。原文 DTO／FrozenJSON 必须显式 `include_payload=True` 才能序列化；该开关只是受信任内部操作，不是脱敏或对外许可。禁止 `dataclasses.asdict()` 后把原文全量写日志。
- SERVER_ONLY：ProtectionContext、ObjectContext、ProtectedResult、MaskReport、RevealGrant 不能由 `from_wire/from_json` 获得。内部直接构造仍只校验形状，不建立真实角色、审批、来源、报告或交付的可信性；以后由服务端鉴权／仓储核验其引用。
- 构造失败统一 `ContractViolation(ReasonCode)`，不拼入坏输入；端口返回成功 DTO 或 `ProtectionError(code,retryable,trace_id)`。HTTP／SDK／ORM 错误在外层转码，不回落原输入。
- 类别仅 `email_address`、`ip_address`、`payment_card_candidate`、`secret_credential`。不新增中国手机号、身份证、国内银行卡、姓名、地址识别；卡候选不推断地区、发卡行或真实账户。

### 2.1 DTO 分组

| 文件／类型 | 核心语义 |
|---|---|
| payloads：Limits | 有版本的显式资源限额；只可收紧当前版本 |
| ProtectionContext | 主体／授权／范围／环境／域／出口／目的／角色／对象版本／可信来源三元组／trace；来源三字段全有或全无 |
| BoundedPayload | text、tree、binary 恰一项；媒体类型一致；空文本、JSON null、空二进制互不混淆 |
| TableColumn、TableCell、TableSnapshot | 资产／输入摘要、稳定 sheet/column 身份、原始序号、逻辑记录、原／规范化文本与映射、Coverage、Limits |
| Location、Finding | 源坐标、类别／级别、规则版本、固定原因码；无原文 match 值 |
| Coverage、Metric | 单位和分子分母／版本；失败、排除、未知、未扫独立，零分母值为 null |
| policies：AlgorithmSpec | 封闭动作及参数形状；不含算法实现 |
| Approval、TeachingException、PolicyRule、PolicySnapshot、PolicyBinding | 申请／审批分离、可信来源最小例外、规则和摘要；保护／风险／契约绑定，不迁走风险业务规则 |
| plans：SourceDocument、SourcePlanBinding | 保留源文档及原域证据引用；格式族与真实源版本分开，源摘要不改写 |
| SheetScope、TableScope、ResolvedAction、Unresolved、ActionPlan | 有限作用域、已解析动作、来源／目标摘要和批准记录；未知／不可映射留 unresolved 或拒绝 |
| crypto：KeyReference、ObjectContext、CipherEnvelope | 非秘密引用元数据、可信对象上下文、封装格式；无主密钥、wrapped key 或明文回退 |
| events：ProtectionError、SecurityEvent、AuditReceipt | 有界白名单事件、固定失败、durable 与 ledger-confirmed 区分 |
| execution：ProtectedResult、ExecutionBinding、QuotaReceipt、MaskReport、RevealGrant、DeliveryReceipt | 完整扫描、同一执行绑定、额度状态、可信复检报告、限时单次原文授权、独立交付证据 |
| ports：AIRequest、AIResponse、EmbeddingResult、StoredObject | 中立有界 AI 载荷／引用／用量、有限向量、候选密文对象；不含任意 base_url、raw SDK response 或认证字段 |

`SecretMaterial` 不是 wire DTO：不可变 bytes、隐藏 repr、禁止 pickle／copy／deepcopy，仅匹配 KeyPurpose 时借用只读 memoryview。只供密码用例、认证适配、框架装配和指定备份／离线恢复使用。Python 不保证内存副本即时擦除；不宣称绝对清零。当前没有读取或解析秘密的实现。

### 2.2 摘要与规范化

M0 规范化标识为 **ds-json-v1**，不是 RFC 8785：UTF-8、键排序、紧凑分隔符、非 ASCII 不转义、不做 Unicode 正规化、拒绝非有限数和未知对象；tuple 映为 JSON 数组，UTC 固定微秒，bytes 为规范 Base64。FrozenJSON wire 使用 `{value: ...}` 的结构盒区分 JSON null 与可选字段缺载荷；不把盒当原 JSON 内容。JSON 整数限 ±(2^53−1)，树节点／深度另限界。

元数据 `content_hash` 为上述字节的裸小写 SHA-256。PolicySnapshot 的 content、ActionPlan 的 content、MaskReport 的 content 与相应 Approval 引用逐次复核；哈希不是 MAC／签名，知道内容便可重算，不能拿摘要替代权威仓储和授权。PolicySnapshot 的生命周期状态不是被批准内容的一部分，批准／退役仍由未来 PolicyCatalog 管理；无任何测试 Approval 被接到正式策略。

`output_hash` 指脱敏后、加密前交付字节；`ciphertext_hash` 指密文字节。输入／原字段哈希可能泄露低熵相等关系，只在受控内部绑定使用，不能发布到普通统计或公开证据。旧 mainline1／执行器／审计摘要均保持其独立算法和名字空间，见第 4、6 节。

### 2.3 Limits 与坐标（D16）

本期冻结 `limits-2026-11-04.v1` 作为**隔离契约测试基线**：对象 20 MiB，文本 65,536 code points，JSON 1 MiB／深度 16／节点 10,000／字段 2,048；sheet 16，源行 100,000，列 512，cell 100,000，findings/actions 各 10,000；zip 成员 1,000、展开 100 MiB、同时在途对象 2。wire 总输入上限 32 MiB。更大值必须升级契约并重测，不是批准生产内存预算；4 vCPU／8 GiB 目标环境的吞吐／并发仍待第 3、6、7 期。

- 行和列原始序号均一基；字符跨度为**原文 Unicode code point、零基、半开** `[start,end)`，不是 UTF-8 byte／UTF-16 offset。
- JSON path 与表格坐标分型；sheet/column ID 仅在同一 asset_version 内有效。重复 ID／原序号／cell、未知引用和越界 span 均拒绝。
- TableCell 同时保留 source_row、logical_record。NFKC 等变换只能在证明每个输出 code point 可映回原文时用于动作定位；重复映射跨度可表达展开，逆序或越界拒绝；unproven mapping 不允许字符级动作。
- TableScope 为每 sheet 的列 ID 和一基闭区间行范围，区间须规范排序且不重叠／不相邻；坐标版本 `source-codepoint-half-open.v1`。列删除是单独 COLUMN location，不能把字符替换降格成整列替换。
- `validate_snapshot()` 绑定资产、输入哈希、Limits、列和真实 cell。完整性不由 parse 成功推断；表格 codec、压缩安全、原策略／源批准和时效复核仍未实现。

## 3. 端口签名与责任

精确注解在 `contracts/ports.py`。所有成功类型显式；没有任意 kwargs／ORM 返回／裸 SDK。

| Protocol | 操作 | 将由谁实现 |
|---|---|---|
| ProtectionPort | protect(payload, context, policy_binding) | M4 |
| CryptoPort | seal/open、blind_index、内部 authenticate；均绑定 ObjectContext 与 KeyReference | M4 调 M3；open 不映成公共解密 API |
| PolicyCatalogPort / PolicyRepository | snapshot/approve/retire；read/put(expected_version) | M4 / M6 |
| KeyResolverPort | resolve(key_ref, purpose, service_identity) → SecretMaterial 或安全错误 | 唯一 M5 |
| AuditPort / AuditSink | record(event,durability)；append/verify/checkpoint | M4 / M6；Sink 不回调入口 |
| OfficialAIPort | chat/stream/embed(request,context,binding) | M7；最终 prepare 后保护、认证后发送；本期无网络实现 |
| TableCodec / SourcePlanAdapter | parse/serialize 显式 Limits；to_action_plan(source,snapshot,binding,resolved_actions) | M8，不自行审批策略 |
| Detect | (BoundedPayload,Limits) → Findings 或错误 | B 将未来 M1 函数注入薄兼容入口 |
| RiskPort | decide(request,binding)、issue/recheck(execution) | M6；泛型特化为**既有**风险 DTO，不复制另一套同义模型 |
| QuotaPort | reserve、require_active、commit(delivered)、release(no_delivery_evidence)、reconcile(delivered或null,evidence_ref) | M6 包装唯一旧 QuotaService |
| PrivateStore / BackupPort | write_candidate/verify/publish/read；create/restore | M6；引用而非用户任意路径；离线恢复密钥不进常驻应用 |
| UnitOfWork | 上下文进入／commit／退出 | M6 短事务；不包住模型网络或大文件处理 |
| RevealRepository | consume(grant,context,expected_version,at) | M6，原子 CAS 和再次鉴权 |
| ExportPort / RevealPort | execute(plan,binding,context)；reveal(grant,context) | M4，未实现／不开通 |

## 4. 两套源计划：保持差异，不伪造等价

### 4.1 对照

| 维度 | mainline1 | 独立 controlled-export |
|---|---|---|
| 格式族 | `SourceFormat.MAINLINE1 = mainline1` | `SourceFormat.COLUMN_V1 = controlled-export` |
| 实际源版本 | `meta.schema_version = mainline1.proposed.v1` | `plan["version"] = "1"`，必须是字符串 |
| 其他版本 | `$id=urn:mainline1:proposed:v1` 是 schema ID；`original-snapshot-v1-proposed` 是 operation contract；`internal-table-v2` 是 parser，不能混为顶层源版本 | 没有上述 mainline 版本字段，不补造 |
| 成熟度／批准 | Proposed、设计／测试能力；PlanPolicy 的 approved、contract_approved、requirements_approved 默认 false；ready/hash/valid 不等于批准 | 原 validator 通过不代表风险授权、production 来源或允许 share；默认 evaluation 不可分享 |
| 定位 | 源快照的一基行／列，零基半开 code-point span；CSV 是含表头的 csv.reader 逻辑记录；`csv:0`、`xlsx:<零基sheet序号>` | sheet／列名，mask_columns、drop_columns、sanitize_formulas；仅 fixed mask；输出列按 scope.columns 顺序 |
| 行数 | 不能把物理文件行、去表头数据索引与源逻辑行互换 | processed/output records 不含表头，不是 mainline 原始行坐标 |
| 正规化 | 公共 Proposed parser 只声明 identity-v1；内部 NFKC 能力不自动升级公共合同 | 转换时保留原输入和列身份；无法证明位置则拒绝 |
| 源摘要 | strict fingerprint：null/str/bool/int、JSON 类容器；拒绝 float／任意对象；UTF-8 sorted compact SHA-256，带 `sha256:` | digest_json：sorted compact、ensure_ascii=False、`default=str`；裸 hex SHA-256 |
| 哈希投影 | plan_digest 只排除顶层 plan_hash 与 meta.trace_id；status/errors/unresolved/created_at 仍绑定。scope_hash 是 `asdict(内部 Scope)`，不是整个公共 DataScope；parser_config_hash 绑定 parser/limits/Unicode 数据版本 | 原 whole-plan digest 包含额外字段，即使旧 validator 未一致拒绝它们；不能新建白名单摘要后声称与旧摘要相同 |
| 公式／交付 | 动作验证不等于真正执行／交付 | 公式保护不依赖是否显式出现 sanitize_formulas；成功、流耗尽、收据、额度结算是不同事实；无外部证据时流耗尽不能证明交付 |

M0 的 source_digest 仅验证名字空间和形状，不重算旧域摘要。**不能仅删除 `sha256:` 前缀就宣布两算法等价。** SourceDocument 保留有界原文（敏感、不可默认序列化），不在 M0 复制旧 validator。SourcePlanBinding 保留原记录／版本、来源证据、批准依据／版本、环境／数据域／evaluation、原状态、scope/parser/requirements/operation 绑定。它不是批准证据本身。mainline 状态保留 ready/partial/invalid；执行器无对应字段，以 not-declared 明示。

未来 M8 负责在同一 TableSnapshot 上复核源计划及批准范围，再映射到 ActionPlan；版本／来源／范围／动作／输入改变均需重新验证。字符／cell 操作不能扩成整列；源 production 不由 environment 名称推断。未知 schema、来源不明、批准缺失、不可表达动作、无法证明坐标和超限必须拒绝或 unresolved，不能借统一 DTO 放开真实出口。

### 4.2 四组原契约保留清单

1. **InputSource / PrivateSource（mainline1）**：保留 `planning.py:28–57` 的 PlanPolicy、PlanInputs、`InputSource.read(principal, profile_id) -> PlanInputs`；`parsing.py:145–162` 的 `PrivateSource.open_version(ref, *, principal, domain_id) -> BinaryIO` 仍由旧域维护。M8 仅在受控边界生成 M0 有界快照，不把 BinaryIO 泄入 M1/M2。公共 RedactionPlan 的 21 个必填字段继续由 `docs/mainline1/contracts/schema.json:2191–2333` 定义：meta、plan_id、plan_hash、asset、scan_id、profile_id、scope_hash、parser_version、parser_config_hash、policy_version、redaction_policy_version、requirements、requirements_hash、operation_contract_version、operations、operation_count、unresolved、validation_errors、status、checked_applicability_version、validation_ref。内部 Scope 和公共 DataScope 不互换。
2. **RunRepository（mainline1/tasks.py:51–73）**：保留 create_unique(candidate)、get(run_id)、compare_and_swap(expected_revision,replacement)，以及 revision、token、lease、cancel、progress、retry、parsed_ref、detection、quality 状态；PostgreSQL repository 原子发布不被 M0 同名仓储吞并。`review.read_plan_basis()` 当前 `usable_for_new_decision=False`，不能升级为新生产决策依据。
3. **export_risk DTO**：保留 ExportRequestSnapshot、AuthorizationSnapshot、SensitivityProfileRef、FeatureSnapshot、BehaviorBaseline（snapshots.py）、Obligation／ExportRiskAssessment（assessment.py）、NotExecutable／ExecutionAuthorization（execution.py）、原 SourceMode／action／disposition／quality 枚举。RiskPort 泛型由 M6 特化这些类型；FeatureSnapshot 的 float 不能塞进 mainline strict fingerprint。environment 默认 production 而 source_mode 可默认 SYNTHETIC，两者不是同一信任结论；UNKNOWN 授权不可执行，current_request_counted 防止重复计数，到期取 decision/grant/quota 最早截止。复用 decisions/serde.py 的 obligation_to_dict/obligations_to_json，不把独立执行器授权 dict 与风险 DTO 按 asdict 硬等同。
4. **RAG Protocol（rag_ingestion/interfaces.py:13–89）**：保留 DocumentParser.supports/parse、TextChunker.split(text,metadata)、Embedder.embed(chunks)、ChunkRepository.replace(document_id,source_type,embedded,base_metadata,ingestion_token=None)，以及 ParsedDocument、Chunk、EmbeddedChunk 和 SupersededIngestionError。保持 ingestion token fencing、原子替换、对象可见性；B 以后注入原接口，M7 只接管受保护的 embedding 外发。pipeline 使用 parser.name，但旧 Protocol 未声明该属性，此缺口登记而非谎称已完全覆盖。

## 5. 额度、幂等、交付与锁序

- 旧 reservation.state **仅 reserved / committed / released / unknown**；不存在 expired 状态。active_reserved、unknown_reserved、settled 是 bucket 计数，不是 reservation 状态。
- 旧锁序 bucket → reservation；风险外层 decision → authorization → quota bucket → reservation。outbox 另为 outbox row → ledger singleton → ledger tail。后续集成必须验证完整顺序，不为“统一”删除锁或并发断言。
- require_active 必须 reserved 且 `now < expires_at`；恰好到期无效，但到期本身不释放、不自动改状态。unknown 保留**全额**占用，不能按 0 交付 release。
- 重复 commit/release 是状态错误，不伪称幂等成功；已 committed 且交付数一致的 reconcile 才是幂等。确认 0 交付应 committed、settled_amount=0，不是 released。
- release 必须有调用方的无交付证据，旧服务本身不证明该事实；禁止无条件 finally release。交付未知保留 unknown、等待带同一 ExecutionBinding 的回执／对账，不无条件重发。
- ExecutionBinding 固定请求指纹／幂等键／请求、授权、决策、资产、执行、预占 ID，主体／域／环境、范围、数量／单位、截止和策略绑定；不能复用在不同请求上。数量是 RECORD，不把字节／源行混算。
- 当前 RiskService.prepare 可经注入 quota 预占，复核仍有直接 QuotaService 导入；没有证据显示独立执行器已经直接连接该 QuotaService。未来 ExportFlow 接管预占时序时必须移除第二次预占，不能假定原来已集成。
- 文件先私有候选密文、验真，再短事务记录就绪／结算／审计；文件系统与数据库无天然共同事务。尚无新实现，所有这些是保留的责任和后期验收义务。

## 6. 旧链保证与新格式边界

旧 `audit/services.py` 使用无密钥 SHA-256 完整性链，**不是加密、MAC、签名或外部锚定**。旧 canonical 为 `json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)`，未设 allow_nan=False；不能以 M0 的 canonical_bytes 重写旧链。

payload_hash 对上述 UTF-8 字节取 SHA-256。entry hash 投影为 previous_hash（空时 64 个 0）、payload_hash、event_category、object_type 或空串、`str(object_id or '')`、actor_id、chain_version；id 和 created_at 不在投影内。当前 verifier 不按 chain_version 分派不同算法；无库外尾锚／期望长度，自洽重写、截尾或空链不是独立防篡改证明。actor 外键 SET_NULL 可能使原 actor_id 哈希不再匹配。

AuditReceipt.DURABLE 只证明已持久化，不填 ledger 字段；LEDGER_CONFIRMED 才要求链版本／条目引用／序号／哈希。M0 仅识别旧 `v1` 与未来 `ds.audit.v2` 的结构，**未实现新链认证或 checkpoint**。未来旧链先验证后按批准归档，保留算法和迁移关系，绝不原地改 payload。Sink／Gateway 防递归与旧直接 writer 退出见 operations C12/C13。

第 1 期 CipherEnvelope 只固定 `aes-256-gcm-hkdf-sha256.v1`、数据用途引用、公开 salt 16 bytes、nonce 12 bytes、至少 16-byte tag 和密文限额；当期未实现密码算法。第 2 期原语见下节；历史 Fernet、真实 key resolver 和 wrapped key 仍未实现，不能用结构测试冒充密码学验收。

## 8. 第 2 期：算法、封装与薄兼容边界

### 8.1 唯一实现与失败语义

- M1=`core/redaction.py`，M2=`core/policy.py`，M3=`core/crypto.py`，M4=`application/protection.py`、`crypto_service.py`。纯层无 settings／环境／文件／网络／ORM／SDK；密钥、时间、随机材料由参数或 M0 端口显式提供。
- 39 DTO／19 Protocol、字段、wire 和 `ds.m0.v1` 均不改。`phase-boundary.json` 明示第 2 期许可文件；11×11 依赖矩阵不改，显式第 1 期扫描仍拒绝这些未来实现，M5–M7 和后期适配仍关闭。
- `ProtectionService` 只消费固定 PolicyBinding，扫描→解释→保护→复核同一绑定及教学例外→要求审计收据→返回。内存策略、假密钥、拒绝型审计只在 tests，M4 不 import 它们。错误返回不含原文的 ProtectionError，无默认策略／latest／明文 fallback。
- 服务构造拒绝 PRODUCTION；B 不接真实设施，拒绝任何非空正式 policy/keys/audit 输入，随机源只接受保存身份的 `secrets.token_bytes`。`bind_legacy_for_tests` 只接受 TEST；正式启动不自动调用它，生产上线必须等后期真实装配验收。此身份校验不抵御同进程任意代码执行，不冒充正式集成验收。

### 8.2 M3 参数和稳定身份

- AES-256-GCM：32-byte key、12-byte nonce、16-byte tag；每次封装 HKDF-SHA256 使用独立公开16-byte盐生成32-byte数据密钥，不保存 wrapped key。M3 从不自己取随机；M4 请求16和12字节，实际生产随机机制仍由 B 的后期集成负责。
- KDF info 域 `ds.data-key.v1`，AAD 域 `ds.aad.v1`；canonical UTF-8 JSON 绑定 project/environment/object_uuid/object_version/field/format/key_ref/key_version/purpose。对象授权收据和 key status 不作为密文身份，因此续期授权及 active→read-only 能读同一密文；可信授权仍由上游建立。写入须 ACTIVE；读取可 READ_ONLY，RETIRED 拒绝。
- 封装版本固定 `aes-256-gcm-hkdf-sha256.v1`；未知格式、错 key、salt/nonce/tag/AAD/密文篡改、跨对象／字段／环境／项目／版本失败关闭，认证成功前不解析或返回任何明文，不以空值假成功。
- HMAC-SHA256 按 `ds.stable-key.v1`、环境、数据域、scope、purpose、key_ref/version 隔离，固定域盐 `ds.stable-salt.v1`，不使用每行随机盐。blind_index 的 `typed-value.v1` 编码保留类型／内容、不包含执行 Limits；同值不同限额或不同对象行保持索引稳定，字段／域／环境／用途变化必须不同。
- 数据封装包含有界载荷完整类型帧，保留空文本／JSON null／空二进制区别；此封装不是历史格式迁移入口。authenticate 只接受有界元数据 bytes，不回调审计，避免递归；旧无密钥链算法不改。

### 8.3 M1/M2 范围、坐标及动作

- 自动 Detect 仅沿用三类既有 `existing-formats.v1`：邮箱／IPv4／银行卡候选。简报优先于旧“四类”文字；SECRET 只保留已有 DTO 与显式 L3 动作语义，旧凭据规则仅兼容复用。完整500条冻结数据保留，第四族自动检测指标不适用，不补新类别。明确不做：中国手机号、身份证、国内银行卡、姓名、地址识别。
- drop／replace／mask／hmac／pseudonym／IPv4 generalize 由批准参数决定；truncate 只能后置。MASK 至少替换一字符；L3 禁 mask/generalize/truncate 为主动作，SECRET 只可 drop/replace。Pseudonym 保留128–256位、8位步进；IPv4 只允许批准的 /24。含 HMAC／假名的文本容器若会被后置截短，v1 保守拒绝，不输出短码或半个假名。
- 文本跨度为原始 Unicode code point、0起点、半开区间。重叠按区间并集、类别 SECRET>CARD>EMAIL>IPv4，再按 drop>replace>hmac>pseudonym>generalize>mask，同类 mask 先取保留字符较少者；平局用算法规范编码，与动作编号或输入顺序无关。整 JSON 字段使用相同强度选择；根字符串 TEXT_SPAN drop 只删除对应跨度，越界拒绝。
- JSON 逐原始路径处理、删数组元素不重解释后续源下标；命中字段整体保护。敏感对象键、未知路径／类型、二进制未配 codec 均拒绝。表格仅接受有界快照；未证实映射只能整体 CELL replace/drop，拒绝片段 mask；表头命中拒绝。无完整覆盖／超行列节点深度字节限额拒绝；禁止删光某表全部列。表格动作预建坐标索引／分组，不逐单元格扫描全部动作，不提供真实编解码／交付。
- 策略精确验证版本／摘要／状态／批准／生效到期、类别／出口／角色／用途／字段授权范围。教学例外必须精确绑定 source_ref/version/hash、outlet、purpose、field 和批准期限；无来源证明不豁免。只允许已投影文本字段，JSON 嵌套和表格列没有可信映射时不继承文档级例外。

### 8.4 旧签名：默认基线兼容与显式测试绑定

2026-11-05 独立验收打回：默认应用没有调用 B，旧版本将“未绑定”当失败，造成普通 manage.py 累计476项中的3项回归。按打回要求恢复一期基线行为；不能用预绑定的测试通过或所谓批准差异替代默认兼容。

| 旧入口 | 默认未绑定 | 显式测试绑定 |
|---|---|---|
| mainline1.rules.candidates | 本次不改，未装配仍报受控错误 | M8 用 M0 Detect 签名调用注入函数；500夹具×3实现与基线等价；批准／缓存／报告仍归 mainline |
| OutputSanitizer | M9 基线兼容替换与一期一致，保留原大小写、匹配范围、替换次数／告警顺序及无65536新上限；业务提示词规则不变 | B 将同一份旧规则显式传给纯 `legacy_confidentiality`，已命中私钥移除完整块／余文、已命中凭据移除完整值 |
| fact_redactor | 恢复 `(value or '')[:limit]` → 原 token 替换 → flag 替换 → strip；包括零／负 limit 和边界截断行为 | 仍先完整保护，再业务 flag 替换、限长及 strip；Authorization/Cookie／带引号的已命中值按原二期测试要求移除该行余文 |

旧凭据／内网表达式只保存于 M9 兼容模块一处，原入口仍是短映射；B 显式传入同一组编译规则，M1不导入M9，M9不导入M1，不改依赖矩阵／M0端口或注册新检测类别。原三类 IPv4 候选的句点语义不变。

未绑定才回退基线；已绑定的异常／坏结果继续失败关闭，合法空结果不误判为未绑定。正式启动不自动绑定、无测试替身装入正式环境。默认基线兼容保留的是既有行为，不宣称已实现二期完整值保护，更不代表真实出口安全；显式绑定只供测试与后续第3期装配，当前不授权部署。

## 9. 第3期：正式适配的边界增量

本节更新当前实施状态，不改写§1–8历史：M0仍39 DTO／19 Protocol及 `ds.m0.v1`，M1–M3和已有三类识别不变。`phase-boundary.json`当前声明3；显式phase=1/2仍按历史阶段拒绝未来模块，不为旧阶段正例特判升级。用户于2026-11-05 15:36批准仅将当前授权阶段的整仓零违规正例改为phase=3；历史phase1/2规则断言和其他旧测试不变。旧失败记录保留，新结果必须以冻结候选全量复验为准。

| 唯一所有者 | 第3期实现与责任 |
|---|---|
| M5 FileKeyResolver | 仓库外只读清单和0600材料；环境／身份／用途／完整引用核验，每次解析重读，退役即拒绝；无框架跨用途回退 |
| M4 PolicyCatalog | 单一M0仓储端口、时钟和精确PolicyBinding；禁止未批／过期／hash不符／教学例外／稳定关联策略；生命周期管理关闭 |
| M6 FilePolicyRepository | 批准文件快照只读；不读latest、不回退第二仓储，ORM管理留后期 |
| M4 AuditGateway／M6 DjangoAuditSink | 前者要求明确收据强度，后者真实本地持久化及私有旧链writer；不能递归入队，durable不冒充ledger-confirmed |
| M7 OfficialAI | 固定官方协议prepare后经ProtectionPort；完成保护后才取认证材料及send；响应有界完整保护后交M0 DTO，无业务答案规则或裸SDK对象 |
| M9 | 内容白名单／截断前保护、日志白名单、Token停用、worker数据库连接所有权；不反导M4/B |
| B security_bootstrap | 唯一构造上述正式对象、OS随机源和业务回调；`DATA_SECURITY_CONFIG`显式装配，拒绝动态实现路径／测试替身 |
| M6 PostgresAgeBackup | 在线公钥create／独立离线私钥restore，一致性快照＋成熟age；验真和空库核对后才登记durable |

业务门面ai_providers只依赖M0和注入回调，不负责配置／环境发现；M7不导入业务prompt/flag保护。服务仍使用显式绑定的版本和范围，重试／厂商切换重新prepare和保护。M7 HTTP、WebSocket协议所必需认证是唯一追加例外，不能进入普通业务正文或返回DTO。已知凭据字段和旧匹配规则的保密不是新增Detect类别。

默认未设置正式配置时保留二期未绑定兼容；设置正式配置后失败关闭，不因缺钥／策略／审计故障回退默认模式。M9内部ProtectedText只避免同一叶子在多个同步预算阶段重复保护，进入M0前转普通str；M7最终整包保护不能被此标记绕过。异步业务中的同步内容保护由M9 worker执行，核心不导入Django/asyncio。

基础审计沿用旧v1无密钥哈希链；AUDIT独立引用已装配不等于新链认证已实现。本节是第3期时点：字段/历史Fernet/精确索引的后续实施见下节；交付Quota、私有文件、原文查看和完整RAG仍不由本期提前开放。所有正式适配只适用R记录的本机隔离批准，不构成生产运行许可。配置和回退详见operations，门禁复验见acceptance。

## 10. 第4期：所有者字段与策略存储

M0的39 DTO/19 ports、M1–M3算法、三类检测范围和冻结依赖矩阵不变。阶段声明推进到4；历史显式phase1/2/3仍拒绝未来实现。阶段4仅增加具体source级授权：owner使用M6字段薄适配，M9只调用注入的策略/preview能力，B独占实现选择及22-owner维护名单（含历史AIAuditLog最小化）。

- FilePolicyRepository与ORMPolicyRepository实现同一PolicyRepository；共享新版本CAS、同版本内容不可变、批准/撤销状态转换；文件锁+原子替换和PG事务锁分别实现持久化，不静默跨库fallback。PolicyCatalog仍唯一，管理调用需EVALUATION管理员、安全审计目的与policy/manage范围，并有durable审计意图；结果审计与策略存储不宣称跨存储原子事务。
- ProtectedModel属于原owner的抽象存储混入；owner在原app迁移security_uuid/revision/state/envelopes及旧列空值约束。加密名单固定15字段；read_protected只读指定字段，AAD使用受信任环境、owner/field、UUID与条目revision，保留单字段版本以允许非敏感字段更新。坏密文/未知状态/缺钥无明文回退，普通serializer无自动全对象解密。
- legacy-v0只在显式legacy_reads时可过渡读；普通save不能擅自迁移历史行。FieldBackfill.prepare核实当前源与真实备份恢复投影，再以metadata checkpoint驱动逐行CAS转换；现存业务判题/计分save不重放。成功、失败、未处理互斥且计数相加等于应迁移；finish必须零失败/零未处理、关闭旧读/旧索引、验真并清零旧值，之后PG拒绝legacy写入。原schema槽清空不等于物理DROP COLUMN。
- INDEX仅在显式field配置启用，邮箱规范化去外围空白/域小写/保留local大小写。盲索引候选在授权用户queryset内产生，再逐候选验证规范化原文，碰撞不扩大访问。重复归一化邮箱是冲突，不自动合并。索引双版本有截止并最终清空旧值；DATA只读旧引用与新写引用分离，M5清单权威状态不可由数据库envelope显示状态覆盖。LINK/PSEUDONYM继续关闭。
- AIAuditLog所有者声明固定`minimized_fields`，字段仅执行第3期已批准的最小化替换，不保存可恢复正文；通用保存/批量拒绝/源快照/CAS/回填核对共用此名单。邮箱仅在写入/查询入口规范化一次，内部索引消费规范值，不重复边界校验。
- Legal的编排边界显式读取获批的input_text，同一局部值供规则评估和一次性的四字段任务上下文使用；ComplianceAgent保留既有轻量输入契约，不依赖owner模型或解密方法，送模前仍经既有protect_text。该上下文仅在调用内存中存在，不新增数据库影子列，不提供缺方法/坏密文的原文fallback。
- B的现有保密投影在进入M0前把内部ProtectedText转换为普通str，根文本及JSON嵌套叶子同口径；内部标记不作为字段输出免保护凭据，仍执行API出口保护。M0闭合JSON严格类型不放宽。
- AuditEvent.detail业务脱敏可发最小SecurityEvent；DjangoAuditSink接收已经验证的metadata-only事件后直接持久化，不能再触发业务脱敏造成递归。普通事件/旧账本网络表示经保护入口，旧链存储payload和hash不重写；新链认证仍留第6期。
- M9服务器侧CourseDataGrant约束本人/获授权课程，管理员无原文豁免，缺request不升权。字段mode关闭的历史默认行为保持；不能拿默认兼容模式运行已迁密文。策略页面只服务固定合成预览，不保存正文，不开放reveal或完整导出。

D4/D5/D9及metadata批准的原文、适用范围和未选对象以R为准；所有者清单、离线维护步骤、密钥退出和失败回退见operations§8。当前测试结果与尚未可验项见E4，不以本节实现说明替代整期验收。

## 11. 第5期：受限表格与源计划适配

`adapters/tabular/codec.py`实现M0 TableCodec；`source_plans.py`独立实现SourcePlanAdapter。`legacy.py`仍只承载二期检测兼容。M0的39 DTO/19 ports和Limits版本不变；阶段声明推进到5，新增具体模块授权，不放宽M8→M1/ORM/策略/秘密/风险/配额禁令。D1通过仓库根pyproject的普通`ctf-data-security` wheel落实：一份data_security及被包装的mainline1代码，同进程端口，不从tasks注入sys.path，不自动注册第二个Django app。

### 11.1 快照、原坐标与格式

- Codec的owner构造参数是固定asset_version；parse验证实际MIME并计算原字节SHA-256，输出M0 TableSnapshot。sheet身份为`csv:0`/`xlsx:<零基序号>`，列身份`c<一基序号>`；CSV行是逻辑记录，含表头第1行。original_text与Unicode码点半开source_spans保留原文，不把UTF-8字节/UTF-16单元当位置。
- Codec只支持UTF-8 CSV及简单、可见、无合并/活动内容的XLSX文本网格。XLSX数值保留XML原始词形（如1.2300），布尔按源解析契约为true/false，不用Python浮点/布尔格式重写原文位置；不从显示格式猜前导零、公式缓存或格式化文本。输出全部写作惰性字符串，不声称保留Excel数值/日期格式。不能表达的日期/错误/公式等拒绝。重复表头可在快照保留稳定列身份，但旧按名称计划不能猜列；输出表头重复或公式转义后碰撞拒绝。
- XLSX工作表标题不塞进M0或旧v1；Codec在同实例保留与input_hash绑定的`sheet_names`映射，serialize验证相同输入身份。完整网格含首行且行号连续才可序列化，不能压紧省略的源行；XLSX声明、关系目标和实际sheet一一对应，缺失/别名/未引用工作表拒绝。未知/失败/未扫/排除覆盖不得冒充完整输出。列输出顺序来自显式scope投影，不重编号源坐标。
- CSV/XLSX表头和值统一经M8唯一`neutralize_formula`，危险首字符含`= + - @ TAB CR LF`及全角对应符号，前置单引号；已转义值不重复追加。XLSX同时强制字符串类型。

### 11.2 两套计划与批准绑定

入口固定为`to_action_plan(source, snapshot, binding, resolved_actions)`；M4/M2完成策略解析，M8只核对表示能力、原位置和批准范围。构造参数显式携带owner保留的SourcePlanBinding、源Approval、TableScope、资产/输入摘要及目标身份/时限。mainline另外必须提供**与快照同一治理信封的source元数据**`snapshot_source=FrozenJSON(governed['source'])`，独立保留parser/version、config及其摘要、实际header_row和完整sheet行数，不能由计划或已选择的单元格推导。缺少或漂移即拒绝；结构删列不能把部分行投影当完整工作表，无表头时第1行按普通数据授权。

| 来源 | 版本/摘要 | 转换边界 |
|---|---|---|
| mainline1 | `mainline1.proposed.v1`、`internal-table-v2`、`original-snapshot-v1-proposed`分别保留；源plan hash为严格排序紧凑UTF-8 JSON、带sha256:，仅去顶层plan_hash/meta.trace_id；scope_hash是内部Scope | mask_span精确映射原码点区间；不可靠映射交回用例，不扩大整格；mask_cell只该格且M0可表达DROP/REPLACE；drop_column须对应sheet完整行/表头授权，不能跨sheet按名称猜列 |
| controlled-export | 字符串`version:"1"`；历史digest_json为裸hex、排序紧凑JSON、default=str；适配入口闭合JSON子集内计算相同摘要，额外旧v1未知字段不静默丢弃 | 唯一标题映射到固定sheet/column，保持scope顺序；mask_columns fixed→逐数据格REPLACE，表头不被遮盖；drop_columns→固定COLUMN DROP；sanitize_formulas是序列化不变量 |

旧v1任意固定字符串（包括默认`***`）不能装成M0封闭Replacement枚举；SourcePlanAdapter明确拒绝，不改成另一哨兵。**保留执行门面**仍支持原固定字符串，由M4公开兼容操作委托M1唯一`fixed_replace`，M8接收注入callable；不是向ActionPlan或旧schema补字段。需要新的ActionPlan替换能力须另立版本。

源scope/parser/config/requirements/operation版本、trust/environment/domain/evaluation与approval依据均保留；源hash与目标ds-json-v1 plan_hash分开，不能仅去sha256:前缀宣称算法相同。源批准只证明保留源依据，转换结果`approval=None`，绝不自动签目标批准或交付报告。output_hash为保护后明文字节摘要，不是ciphertext_hash。未知版本、非ready、unresolved、漂移、越界、缺批准、动作冲突、零列和不可表示动作拒绝。

2026-11-06 12:12的批准仅允许隔离合成golden构造虚构approved绑定；生产B默认状态、draft/Proposed、planning.py的PLAN_APPROVAL_REQUIRED保持原样。源/目标摘要不代替owner新鲜度、撤销与执行原子边界鉴权。

### 11.3 ParsedArtifact私有表示

`parsed_artifacts.govern_parse_result`把旧ParseResult映射为M0 BoundedPayload(JSON)，唯一持久化树版本`ds.parsed-artifact.v1`。树含一个TableSnapshot及有界source元数据：原scope/config及摘要、结构、覆盖/排除/not_run、类型/通道/number_format/标题来源行；没有第二份raw ParseResult/source_text payload。未选择表头保持排除与空标签，不重读、不扩大批准范围；旧NFKC映射保留证明状态，但不升级公共identity-v1契约。

repository.publish先校验owner冻结输入，再治理，最后在原事务内完成任务并保存受限表示；超限/不支持时无成功状态或孤儿产物。完整JSON仍受1MiB/深度16/节点10000/字段2048等M0限额约束，不能借坐标数组绕过。私有原文快照不是公开导出或扫描完成凭据；不新增字段解密API、不迁移生产历史记录、不提供旧raw payload回退。已安装的正式业务/公开交付仍未接入该内部app。
