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

- 第1–5期为39个具体DTO／19个Protocol；第6期新增ReportProof、ReportRecord、SecurityEventV2、AuditCheckpoint、QuotaRecoveryEvent、CanarySeed及ReportRepository／CanaryCheckPort后，`CONTRACT_TYPES`登记45个DTO，`PORT_TYPES`登记21个Protocol。源码字段声明是精确结构；`tests/fixtures.py`覆盖每个DTO。
- DTO 为 frozen、slots、kw-only dataclass；集合为有界 tuple，JSON 为深复制的 FrozenJSON。不可变约束是编程边界，不抵御拥有同进程任意 Python 执行权的主体。
- `schema_version` 必须显式且精确匹配各类 `SCHEMA`。所有字段（包括可为 null 的字段）都须出现；多字段、缺字段、错误类型、未知枚举／schema 均拒绝。bool 不当 int、字符串不当数字；未知版本不靠缺省值补齐。
- `from_wire()` 只解码闭合类型图；无 eval、get_type_hints 字符串求值、用户 Python 路径、Any 或 SDK kwargs。`from_json()` 另拒绝重复键、NaN／Infinity、错误 Unicode／过深 JSON 及超长输入。
- 时间为时区感知 UTC；线格式固定 `YYYY-MM-DDTHH:MM:SS.ffffffZ`。校验不读取当前时间；到期／撤销／授权再检查是后续用例职责。
- 默认 repr 全部隐藏值。原文 DTO／FrozenJSON 必须显式 `include_payload=True` 才能序列化；该开关只是受信任内部操作，不是脱敏或对外许可。禁止 `dataclasses.asdict()` 后把原文全量写日志。
- SERVER_ONLY：ProtectionContext、ObjectContext、ProtectedResult、MaskReport、RevealGrant、ReportRecord 不能由 `from_wire/from_json` 获得。内部直接构造仍只校验形状，不建立真实角色、审批、来源、报告或交付的可信性；以后由服务端鉴权／仓储核验其引用。
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
| execution：ProtectedResult、ExecutionBinding、QuotaReceipt、MaskReport、ReportProof（第6期新增）、RevealGrant、DeliveryReceipt | 完整扫描、同一执行绑定、额度状态、可信复检报告、限时单次原文授权、独立交付证据 |
| ports：AIRequest、AIResponse、EmbeddingResult、StoredObject、ReportRecord | 中立有界 AI 载荷／引用／用量、有限向量、候选密文对象及受控报告记录；不含任意 base_url、raw SDK response 或认证秘密 |

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
| CryptoPort | seal/open、blind_index、内部 authenticate／verify_authentication；均绑定 ObjectContext 与 KeyReference | M4 调 M3；open 不映成公共解密 API |
| PolicyCatalogPort / PolicyRepository | snapshot/approve/retire；read/put(expected_version) | M4 / M6 |
| KeyResolverPort | resolve(key_ref, purpose, service_identity) → SecretMaterial 或安全错误 | 唯一 M5 |
| AuditPort / AuditSink | record(event,durability)；append/verify/read_authenticated/checkpoint | M4 / M6；Sink 不回调入口 |
| OfficialAIPort | chat/stream/embed(request,context,binding) | M7；最终 prepare 后保护、认证后发送；本期无网络实现 |
| TableCodec / SourcePlanAdapter | parse/serialize 显式 Limits；to_action_plan(source,snapshot,binding,resolved_actions) | M8，不自行审批策略 |
| Detect | (BoundedPayload,Limits) → Findings 或错误 | B 将未来 M1 函数注入薄兼容入口 |
| RiskPort | decide(request,binding)、issue/recheck/consume(execution) | M6；请求／授权使用**既有**风险DTO，decide返回原域持久化decision_id引用，不泄漏ORM、不复制同义模型 |
| QuotaPort | reserve、require_active、commit(delivered)、release(no_delivery_evidence)、reconcile(delivered或null,evidence_ref) | M6 包装唯一旧 QuotaService |
| PrivateStore / BackupPort | write_candidate/verify/publish/read；create/restore | M6；引用而非用户任意路径；离线恢复密钥不进常驻应用 |
| UnitOfWork | 上下文进入／commit／退出 | M6 短事务；不包住模型网络或大文件处理 |
| ReportRepository | put/read准备记录；delivery读取回执；lock_delivery(binding,record_hash)；record_delivery(receipt) | M6受控仓储；锁和回执写入要求外层UoW，状态查询不授予当前下载权限 |
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

AuditReceipt.DURABLE 只证明已持久化，不填 ledger 字段；LEDGER_CONFIRMED 才要求链版本／条目引用／序号／哈希。第1期M0仅识别旧 `v1` 与未来 `ds.audit.v2` 的结构，当时未实现新链认证或checkpoint；第6期认证链与外部checkpoint增量见§12.8，旧链完整审批归档桥接仍待完成（内部捕获见§12.8.1）。旧链须先验证后按批准归档，保留算法和迁移关系，绝不原地改 payload。Sink／Gateway 防递归与旧直接 writer 退出见 operations C12/C13。

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

## 12. 第6期：额度与交付前复核（实施中，未开放交付）

### 12.1 原域所有权与回执

`DjangoQuotaPort`包装原`QuotaService`五个状态操作；原服务保持QuotaBucket／QuotaReservation唯一写入者。`QuotaExecution`只存完整ExecutionBinding＋window／limit／ttl的摘要及操作回执，不维护第二套额度余额。新增原服务`observe`在bucket→reservation锁下返回不可变快照，不改变额度状态。

- 同幂等键必须绑定同一完整执行；另换幂等键不能收编旧reservation。没有M6完整绑定出处的legacy hold也不能收编。
- commit、release及确切reconcile重放要求同操作、同数量和同证据引用，返回已保存回执，不再次调用原状态writer。commit后换成reconcile不视为同操作重放；后续Flow必须按记录选择操作，不能凭客户端成功声明补结算。
- unknown保留全额占用；过期不是释放依据。unknown后的确切reconcile可以结算0至预占量；无确切证据时继续unknown，不释放、不发布第二次。
- `active_until(binding)`是M6之间的只读期限接线，不新增M0端口或更改QuotaReceipt版本。它经同一完整绑定校验和原`require_active`，返回实际hold期限与binding期限的较早者，或ProtectionError。不能仅从QuotaReceipt.binding推测hold期限；跨域回调把错误映为拒绝，不回退旧默认入口。RiskPort已消费该注入回调，正式B／ExportFlow接线尚未完成。
- 端口仅接受test／evaluation装配；不构成生产额度authority。合法evidence_ref只是引用格式，不证明实际交付；证明的可信来源仍须由Flow／持久化回执建立。

测试侧新增`data_security.tests.quota_memory.MemoryQuotaPort`，以显式共享内存记录和时钟实现完整五操作及`active_until`，不导入ORM／原QuotaService。`quota_contract.QuotaContract`的同一组案例分别由纯内存与真实PostgreSQL适配继承：绑定／配置冲突、hold与binding独立期限、错误无占用、unknown全额保留、实际结算量和精确历史回执重放。重建内存端口只表示同进程共享记录，不代表持久恢复。它仅用于单线程行为与提交段测试，没有事务回滚、锁等待或DB故障能力；这些继续由原PG专用测试证明，不拿内存实现替代UoW或四端口完整同契约门禁。

### 12.2 授权与短事务

`DjangoRiskPort`按可信owner请求构造单次请求范围实例，显式固定原`ExportRequestSnapshot`、M0 TableScope、domain、完整PolicyBinding及隔离环境。研判／当前授权供应器和额度`active_until`由装配注入；客户端不能用下载请求替换这些输入。`decide`复用原域`create_risk_decision`，以完整请求／scope／domain／policy摘要作为幂等身份，只向M4返回原域decision_id字符串引用，不新增同义决策DTO或返回可写ORM实例。研判必须匹配请求及风险策略版本。返回引用前，经原域`check_execution_eligibility`锁决策后重新取时，检查当前授权、来源、环境、allowlists、审批、决策状态和期限。该准入不查hold、不reserve、不prepare／claim，失败不保留缓存引用；只代表此时可以进入预占阶段，不是执行授权。

`issue`在原风险事务内prepare并claim一次，随后复核并返回原`ExecutionAuthorization`DTO；已claiming的同执行再次issue拒绝，避免把重复领取当重试成功。交付幂等重放由后续ExportFlow记录处理，不以重新issue代替。`recheck`每次调用可信authorize供应器、核对完整执行绑定和当前授权，不再次claim或结算。恢复时用相同可信请求重建实例并`decide`取回同一原域引用，再recheck；缓存引用不是状态authority，也不复活失效决策。失败claim／后续异常回滚本次授权与原outbox，不释放已有hold；原服务仍独占风险表写入。

风险`prepare_execution`的外部hold路径必须显式传reservation／authorization／execution身份及`require_active`，不能同时传旧quota参数；该路径不reserve／release。旧调用路径暂留兼容，不作为新Flow的预占入口。`claim`注入相同检查；`recheck_execution`在claiming状态重新核对当前授权、审批、来源、环境、scope和四个执行身份，锁等待后重新取时，只能收紧期限，不consume／结算／释放。

`consume(execution)`要求已有外层UoW，复用当前授权／完整绑定／实际hold复核后，调用原风险域consume完成claiming→consumed，不重新claim、不写额度。后续Flow失败可随外层事务回滚消费；autocommit调用拒绝。它不是可以脱离交付事务调用的成功通知。

测试侧`risk_memory.MemoryRiskPort`独立保存决策、执行授权、幂等身份和事件计数，不调用Django或原域writer；复用的仅是原冻结DTO与无副作用的授权范围／时间判断。`risk_contract.RiskContract`由它与原DjangoRiskPort原样继承19项：准入不查hold、完整绑定、当前许可／审批、原决策期限、单次领取、授权期限只收紧、重建后重新准入、unknown保留、consume作用域与终态、准确错误及资源计数。内存搭配已验证的MemoryQuotaPort，PG搭配原DjangoQuotaPort，各自额度仍由自己的端口唯一修改。内存work仅是显式作用域标记，不模拟UoW原子回滚、DB故障、锁竞争或持久恢复；这些仍由原PG专项覆盖，不能把相同案例通过当作正式owner／B已装配。

提交段外层短事务的锁序为report→decision→authorization→M6 quota binding→原bucket→reservation→private object→audit ledger。reserve单独完成后再取风险锁；不能先持quota binding锁再倒序申请decision锁。`DjangoUnitOfWork.commit()`仅标记提交意图；正常退出且已标记才提交，未标记或后续异常回滚。返回ProtectionError本身不抛异常，调用者必须检查并不提交UoW。额度效果与回执同库原子；文件、模型和网络发送不加入该事务。

### 12.3 私有候选与二进制封装

`DjangoPrivateStore`仅接收CipherEnvelope，在owner受控0700私有根下以0600文件保存规范封套字节，不持久化明文。ciphertext_hash是**完整封套文件字节**的SHA-256，覆盖key引用／版本、salt、nonce、tag等，不只是裸ciphertext。文件身份绑定项目、环境、对象UUID／版本、字段和封套摘要；authorization_ref更新不改变对象身份，当前权限仍由上层复核，不由存储端口授予。

write_candidate先完成密文写入／fsync，再登记PrivateObject。verify核对持久身份与文件摘要，并经注入CryptoPort完整认证、验证有界载荷后改为verified；文件I/O和认证不在端口自建DB事务内。publish仅把verified改为published，不移动到公开MEDIA路径、不读大文件，可加入交付短UoW。数据库状态为准，客户端StoredObject.state不能提权。read只向内部用例返回已published对象的封套，实际下载必须再经CryptoPort完整open成功后发送，不能直接把这个内部端口暴露为HTTP。

数据库回滚不回滚文件；失败可留下不可下载的密文孤儿或部分密文，不能覆盖后假称成功。完整同内容文件可重用；部分孤儿拒绝复用，恢复／受管清理尚待接线。发布回滚保留verified及文件，不产生公开路径。该局部端口不等于资源、反馈和独立执行器上传／分享／清理已封口。

20 MiB按原始文件字节计量，Limits版本与业务上限不变。旧JSON内嵌base64会让足额二进制在加密前超限，新增明确格式`aes-256-gcm-hkdf-sha256.binary.v1`：单条AEAD明文为4字节大端头长度＋BoundedPayload规范JSON头（binary为空）＋原始文件字节；头与长度总计≤4 KiB。整个帧只加密／认证一次，不是分块密码协议。二进制帧最大20 MiB＋4 KiB，tag另16字节，32 MiB外层wire上限不变。格式版本同时进入HKDF info及AAD，换版本不能重解释原密文。旧`aes-256-gcm-hkdf-sha256.v1`的20 MiB密文前载荷限制和读取保持不变；新增读取器按显式格式处理，无明文／猜格式回退。原语及内部bytes容器允许帧开销，不允许BoundedPayload借此增加业务文件上限；open在完整tag认证后仍核对嵌入及装配Limits。

测试侧新增`private_store_memory.MemoryPrivateStore`，以独立元数据和规范密文bytes实现四个PrivateStore操作，实际调用原CryptoPort验真；不是只返回verified的Mock。`private_store_contract.PrivateStoreContract`的12项案例由内存与Django／PG夹具原样继承，统一检查完整身份、候选／验真／发布状态、重复操作、错钥／跨对象、salt／nonce／tag篡改、密文截断／缺失、孤儿及对象数量／字节占用。测试owner通过独立故障钩子改变bytes或登记状态，不将这些钩子暴露为生产端口。内存仅单线程，不证明fsync、文件权限、真实重启持久性或UoW回滚；原PG专项与20 MiB资源验证仍独立保留。该端口不签发许可、不核授权到期；当前授权与完整下载认证仍归上层owner。

### 12.4 报告完整性认证（内部组件，未接正式owner出口）

新增M0 `ReportProof`（`ds.report-proof.v1`）：report_hash、完整ExecutionBinding摘要、ObjectContext摘要、audit-auth密钥引用和32字节认证码。它可以反序列化，但反序列化成功不代表可信；原MaskReport仍为SERVER_ONLY，现有schema／字段不改变。

M4 `ReportAuthenticator`仅是受信任执行器与交付用例之间的认证组件，不是客户端报告签名API。issue只能由可信执行器在实际转换、复检及候选验真后调用；verify须用owner记录重新取得的执行绑定、计划、对象上下文及三个实际内容摘要，不能把客户端提供的报告内容同时当作“期望值”。两侧均校验源／目标计划、资产／策略／算法、完整scope、输入／输出／密文摘要、成功且完整复检及当前期限；HMAC额外认证完整执行身份（包含授权／决策／预占／数量／幂等键等）与对象上下文。算法版本统一为排序去重的`算法枚举/版本`，例如`replace/v1`。

认证经CryptoPort的audit-auth用途，使用独立`reports/mask-auth.v1` scope与`ds.mask-report-auth.v1`正文域；普通审计或其它元数据MAC不能复用。内容hash及ReportProof各摘要即使全部重算，仍须有合法MAC；密钥错误／缺失失败关闭。当前组件仅test／evaluation及synthetic来源。issue只用active密钥；verify经CryptoPort.verify_authentication，可显式注入同版本的受限read-only材料，只返回bool／错误，不暴露新MAC。校验仍保留原proof中签发时active的规范字节，但resolver接收当前read-only引用，不把旧材料标成active加载；签发、退役材料、用途／scope错误仍拒绝。旧报告的计划／授权期限不延长。尚无自动选历史key或真实轮换／恢复批准，不据此开放下载。

该认证组件本身不重新执行M1、不验证owner审批数据库、不代替RiskPort当前授权或QuotaPort活性。实际生成、报告仓储及内部提交段见下节；完整ExportFlow及正式owner接线仍缺，仅有一份MAC正确的报告不能放行。

### 12.5 实际表格报告候选（尚未交付）

`TableReportExecutor.prepare(payload, plan, execution, context)`消费owner加载的原始文件、计划与执行／对象绑定，没有客户端report或hash参数。它调用现有M1与注入的TableCodec，核对实际输入摘要和源快照，按已批准scope投影，应用既有actions后序列化，再解析实际输出字节复检。不会自行增加动作、批准计划或扩大范围；缺表头、间断／越界范围沿冻结格式限制拒绝。

TableCodec新增只读`delivery_metadata`，返回冻结serializer保留的非网格值（XLSX工作表标题，CSV为空）；原parse／serialize语义不改。标题经现有三类检测，实际输出须与解析后再次规范序列化的字节相同，避免把被parse丢弃的OOXML通道算作已检。此保证依赖受信任冻结codec，不是任意OOXML认证器。当前要求输出三类候选为零；尚未注入HMAC／PSEUDONYM动作key材料，也不宣称保留可识别格式的GENERALIZE已全面支持。

通过复检的实际输出经CryptoPort加密、PrivateStore写候选并完整验真，才生成MaskReport及ReportProof。输入／输出摘要对应各自实际文件字节，密文摘要对应完整规范封套字节。源coverage用CELL：total为原输入全部cells，eligible／processed为scope内cells（含随后drop的cells），excluded为scope外cells；排除引用是相对于已绑定原输入的scope补集摘要。复检coverage用FIELD：实际输出cells＋保留工作表标题，excluded为0。

返回的`ReportCandidate`是M4内部对象，只有verified私有引用、报告和proof；不publish、不预占／结算／释放。最终认证失败或处理中到期可留下不可下载的verified密文。提交段另按scope数据行计算逻辑记录数并复核当前策略／风险／额度；内部execute现已编排prepare和提交段，正式owner来源审批与B接线仍缺，不能将候选当交付回执。

### 12.6 不可变受控报告仓储

M0 `ReportRecord`（ds.report-record.v1）保留完整ExecutionBinding、ActionPlan、ObjectContext、StoredObject、MaskReport及ReportProof，不含原文件／表格快照。SERVER_ONLY且默认禁止序列化；显式内部序列化开关不代表对外许可。`ReportRepository`由M6 `DjangoReportRepository`实现，仅test／evaluation装配。

`ExportReport`／0004迁移以execution_id和idempotency_key分别唯一约束，保存完整绑定摘要、规范文档及摘要，并以PROTECT外键关联私有对象。put只允许完全相同的记录重放，不覆盖报告、计划、对象或认证码；read要求owner提供完整预期binding，键不存在为null，数据库错误为DELIVERY_UNKNOWN，不能混淆。记录过期仍可读取作恢复，但必须再认证和当前授权复核，不能自动续期。仓储不读取文件、不签名、不发布／结算，也不声称不可变规则抵御DB管理员。

JSONField返回wire列表，仓储直接按ds-json-v1排序／UTF-8规则编码，不将wire列表误当M0内部tuple。只在DB边界显式重建SERVER_ONLY的MaskReport／ObjectContext／ReportRecord，公共from_wire禁止保持；其它嵌套DTO走原校验。文档摘要用于一致性检查，攻击者重算它仍不能伪造MAC。加载结果不是“已认证记录”，M4仍须对照owner计划／执行／对象验证proof；当前没有正式owner／Flow接线。

写入可参加短UoW；成功返回在外层事务中仅代表暂存，外层提交前包括延迟FK约束都未最终确认。失败／回滚不删除密文、不释放额度。0005迁移新增独立nullable delivery_receipt，不修改已认证的准备文档。delivery读取内部逻辑回执；无报告是错误，存在报告但无回执才为null。lock_delivery在调用方外层事务内锁报告并比对完整文档摘要；record_delivery只允许SUCCEEDED＋ds.audit.v2入链回执，同内容重放、不同内容拒绝覆盖。二者autocommit调用拒绝。回执存储仅检查形状和绑定，不证明调用方真的入链，不抵御DB管理员，不替代后续账本核验。

0006迁移增加`intent_hash`及preparing／prepared／aborted状态，准备前document和private_object可为空。`begin(plan,binding,context)`要求调用方外层短UoW，绑定完整执行／计划／对象；只有新建者返回true，相同意图重放返回false，不能重复领取准备权。已准备的旧记录不改正文、不重新准备。`put`对preparing行加锁后填入一次真实报告；不同意图或aborted拒绝。`read`在尚无报告时可返回null，这本身不是未交付证明。

`abort(binding)`同样须外层UoW并锁报告行：已交付返回原回执，缺行／坏回执／绑定不符返回错误；无交付回执则置aborted，迟到put与lock_delivery均拒绝。现有准备文档和私有文件保留，不删除证据。仓储不调用额度服务；返回null仅在该UoW内表示已阻止后续报告提交，是否释放／对账及原子提交仍由Flow负责，不能把方法返回当已落库证明。准备隔离原31项已在04／10／export-recovery-postgres-01逐项聚合通过；中断及两项真实失败保留，不冒充一次干净候选suite。

### 12.7 ExportFlow提交段（未装配为完整ExportPort）

`ExportFlow.commit(plan,binding,ObjectContext)`从仓储加载准备证据并对照owner提供的计划和对象上下文，认证报告、完整验真私有文件后才进短UoW。锁报告后重新检查期限，调用必注入的owner授权供应器取得ProtectionContext，消费当前PolicyCatalog并逐动作比对批准的算法及参数；当前不接受教学例外或与当前规则不一致的额外动作。再经RiskPort复核并消费授权，重新取时检查计划／策略期限，依次发布DB状态、结算逻辑记录数、获取新链审计回执、保存逻辑交付回执，最后提交。文件验真在锁外；所有错误返回都不commit、不自动release。记录数是各sheet范围内数据行之和，不计表头，不是cells数或网络接收量。

同绑定已有回执只返回内部历史状态，不再次消费／发布／扣费，不新发下载授权；并发提交在报告锁后读到赢家回执也走此路径。新交付只接受LEDGER_CONFIRMED且ds.audit.v2；旧v1或仅outbox的DURABLE回执拒绝。UoW退出异常返回DELIVERY_UNKNOWN，不假定提交或回滚成功，不自行释放。提交段构造SecurityEventV2，report证据值为实际已验证MaskReport完整规范正文（含report_hash）的SHA-256，ciphertext证据值为验真私有对象的密文文件摘要。编排单测仍使用显式替身；真实v2适配器另行验证，正式B仍未注入此提交段。

### 12.7.1 内部释放与确切零交付对账（未装配为恢复入口）

`release(binding)`与`reconcile(binding)`不接收客户端的交付数或证据字符串。两者要求显式注入`authorize_recovery(binding, operation)`，由owner检查当前恢复操作者对完整binding和具体操作的权限；供应器现在必须返回当前恢复操作者的ProtectionContext或ProtectionError，不再接受true等无身份许可；未装配默认拒绝。上下文须绑定同环境／域／execution_id／asset_version、scope含reservation_id、outlet=AUDIT及purpose=SECURITY_AUDIT；actor与当前恢复authorization_ref由可信owner提供，不从原导出申请人推定。该权限不同于旧导出授权，旧授权过期不能自动获得恢复权限，也不阻止有当前恢复权限者终止过期执行。

短UoW内先`reports.abort`取得报告行锁，再复核当前恢复权限；有已交付回执只返历史状态，不重复结算／发布。缺行或读取错误不是零交付证明。只有同事务已禁止未来put／发布且没有既有交付回执，才以完整binding生成固定`flow/no-delivery/`证据引用，调用原QuotaPort：release仅释放reserved，unknown仍被原域拒绝；reconcile按确切零结算，从unknown移出保留量，不把unknown直接当失败释放。确认的零表示逻辑交付被原子阻断，不是推测客户端网络结果。

终止状态、额度、额度回执及关键恢复审计同库提交，失败不提交，UoW退出异常返回DELIVERY_UNKNOWN并保留状态供显式重试；不删除文件或旧回执，不调用risk／publish／reserve。新增QuotaRecoveryEvent以独立schema记录本次操作、当前actor／恢复授权及原额度域完整不可变QuotaReceipt，经唯一Gateway／Sink进入ds.audit.v2链；没有v2配置或入链失败时，额度和abort一起回滚。

同操作重试返回原额度回执，但每次新的当前操作者观察仍记录审计：事件时间是本次观察时间，嵌套quota.observed_at保持原效果时间，不能把多条观察事件解释为多次结算。既有交付回执仍只查历史状态，不伪造零交付恢复事件。恢复身份／审计新增纯组90项及恢复／受影响执行路径22项真实PG全部通过；可信恢复操作者的业务供应器与B入口仍未接线，不宣称正式恢复闭环已验收。

新增M6 `DjangoRecoveryAuthorization`从`RecoveryPermission`读取显式恢复许可：可信调用方供应已认证的ProtectionContext和授权引用，许可绑定actor与整个ExecutionBinding摘要，release／reconcile分别授权，默认均关闭。必须在外层UoW内、报告锁之后取得权限行锁，之后才核当前期限／撤销；不缓存许可，不根据角色、旧导出授权或调用方布尔值补权。该适配只读许可，不负责认证或签发；尚未接入业务owner／B，不据此开放恢复或下载。security_policies.0007只新增许可元数据，不改原风险／额度writer或M0 DTO。

### 12.7.2 内部execute编排（正式owner／B仍关闭）

`execute(plan,binding,ProtectionContext)`须显式注入可信owner的风险request、ObjectContext、load_input和executor，缺任一即拒绝；不从客户端补齐这些依赖。已有报告／回执只作历史状态重放，不重新加载原文或再次发布；只有begin真正新建的准备者能够继续，相同执行的竞争者不能终止赢家。

当前owner、精确批准策略及风险准入通过后，短UoW中begin取得准备权、锁后重新核期限、单次reserve并提交，再在该事务之外issue／claim、加载原文、调用既有TableReportExecutor、保存不可变ReportRecord并进入commit。owner先取得真实decision_id以冻结完整ExecutionBinding，execute再次准入时必须返回同一decision_id，不偷偷替换绑定；这不允许提前reserve／claim。提交段仍重新复核当前权限／策略／期限，不把准备时的准入当长期授权。

已确认回滚的预占失败直接返回，不清理已回滚的新行；准备后的已知错误只在显式恢复权限存在时走锁内release。UNKNOWN只允许本准备者另开短UoW：abort隔离未来发布，确认没有历史回执后以固定`flow/unknown/`证据调用reconcile(binding,None,...)登记unknown并保留全额额度，并用本次execute已验证的owner身份记录unknown恢复事件；这只保留额度，不授予释放权限。unknown登记与入链同事务，审计失败则两者回滚，原保留额度不回补，调用方仍得到UNKNOWN。若已实际交付或登记本身不可确认，仍返回原UNKNOWN，不覆盖成功、不自动按零结算。只有后续显式授权reconcile才可依据锁内零交付证明结算。未知事务结果与已正常回滚分开处理，不用finally释放。

新增12项编排单测连同受影响提交／恢复／边界共36项通过；真实PG execute8项和受影响commit5项共13项通过，额外执行故障／完整binding冲突6项也通过。默认装配／生产交付仍关闭；恢复审计增量另行验证，不将内部组件当正式ExportPort启用。

### 12.8 新链与版本化证据

QuotaRecoveryEvent使用独立ds.quota-recovery-event.v1 schema，扩展受控事件元数据而不修改旧SecurityEvent／SecurityEventV2的字段或识别类别；操作仅release／reconcile／unknown，完整嵌套QuotaReceipt绑定执行／预占／scope／策略／金额与证据引用。事件校验操作与回执状态一致、reconcile确切为零、对象／版本／关联及counts匹配。Gateway只额外接受该精确DTO，dict／任意子类仍拒绝。Sink统一写现有ds.audit.v2认证链，按显式schema解码验证，非对象／缺字段／未知schema在verify、checkpoint和追加时均失败关闭；恢复事件与普通v2混链、检查点及重算无密钥摘要后的伪造拒绝已在PG验证；不另开ledger writer，不新增表或迁移。当前44 DTO／20 ports。

SecurityEventV2使用独立ds.security-event.v2 schema，保留原事件白名单，并新增有序、唯一、最多3项的evidence_hashes（archive／ciphertext／report）。成功DELIVERY必须同时具有report和ciphertext；只接摘要，不接自由detail或原文。旧SecurityEvent schema不扩展，这两类原事件的字段与精确类型限制保持，新恢复事件使用上述独立schema。DTO形状不证明owner真的执行过转换。

DjangoAuditSink显式注入CryptoPort、AUDIT key及test／evaluation ObjectContext后可处理v2；无配置拒绝v2，绝不降级旧链。旧事件仍写旧v1表，新事件写独立AuthenticatedAuditEntry（audit 0007）。事件行→v2链锁顺序，sequence在锁内取尾加1；durable、升级入链和重放按event_id唯一，冲突拒绝。外层UoW未提交时回执仍是事务内结果。

HMAC绑定ds.audit.v2、稳定链身份、sequence、previous_hash、完整事件摘要、event_id、服务器接收时间、入链时间和签发key引用；事件摘要覆盖对象版本、策略绑定、调用方事件时间及证据摘要。用途域固定audit/ledger.v2，不复用报告MAC域。链身份包含project／environment／object UUID／version，不绑定可更新的操作者授权引用。entry_hash覆盖上述内容及MAC。验证逐条重建事件、核时间／顺序／连续序号／摘要和MAC；数据库不能指定加载新key，须在显式当前／retained_keys目录中查得同版本材料。只读key仅验证旧签发字节，不可新签。

AuditCheckpoint（ds.audit-checkpoint.v1）绑定chain_identity、准确尾部AuditReceipt（含长度／末条引用／摘要）、checkpointed_at和ACTIVE签发key，通过独立audit/checkpoint.v1域认证。checkpoint只能在无外层事务时创建，对已提交链持锁验证后写库外owner预建0700目录中的0600不可覆盖内容寻址文件，文件及目录fsync后才返回引用；不把同库自签值当锚点。失败文件保留且不返回成功引用。

verify所需的checkpoint_ref必须从可信的库外管理记录显式注入，不能从待验证数据库选取。只配置目录不等于已选择锚点；没选引用的验证返回checkpoint_ref=null，没有尾部保护。已选择的文件缺失／篡改／权限不符或数据库短于其前缀时失败，不静默退回无锚模式。更晚链尾可返回同一检查点引用，但只证明该检查点的前缀，之后的完整尾部截断仍有窗口。当前提供创建／验证端口，不含定期调用、自动选最新引用或恢复开通流程。

`AuditSink.read_authenticated(event_id)`为可信引用加载提供内部证据读取：只在显式配置的新链内查找，逐条解码并核验整条当前链及已选择检查点，完成尾部验证后才返回已经验证的不可变SecurityEventV2／QuotaRecoveryEvent。不会先取裸SecurityAuditRecord再当作可信证据，也不会在找到目标后跳过后缀；单次遍历复用已验证DTO，不二次查询／解析目标事件。缺目标、仅durable、旧链事件、其他链、坏正文／认证／检查点及缺历史key都拒绝；未装配新链返回UNSUPPORTED_FORMAT，不退回v1。只读key可验证，不签发／追加／改写事件、不新建检查点。此方法不授予业务下载或恢复权限、不证明目标不存在或网络已交付；没有显式库外锚点时，后缀窗口限制仍成立，owner还须比对当前业务对象／版本与实际引用。新增读取方法不增加DTO／Protocol数量或识别类别。若调用方已有外层事务，读取可看到该事务自身尚未提交的新事件；返回DTO只证明当时可见证据的认证，不替调用方提交，也不是持久提交确认。用于unknown对账时不得把同一未完成事务内的读取当成提交证明。

B的`ds.bootstrap.v2`新增可选`audit_chain`显式配置；缺省与原`ds.bootstrap.v1`保持旧链能力，不自动升级事件。配置只接受chain_version=ds.audit.v2、project_ref／object_uuid／object_version／authorization_ref、retained_keys、checkpoint_root和checkpoint_ref。B从受控配置构造EVALUATION ObjectContext，固定audit/ledger.v2用途，不开放ObjectContext wire解码或动态实现路径。当前签发仍用原独立audit_key；历史引用只接受READ_ONLY且须在FileKeyResolver中有同一引用、用途与service/security身份，缺材料或跨用途复用字节拒绝。只创建一个Sink／Gateway，目录与显式检查点由原M6验证；配置了checkpoint_ref必须在装配时完整验证，不从DB补最新、不丢锚降级。新7项及受影响旧B6项共13项PG全部通过；新增实际Django启动和受影响ORM／字段3项共4项也全部通过，20项依赖护栏及610文件扫描通过；ExportFlow owner／恢复业务入口仍未装配。

测试侧新增`audit_memory.MemoryAuditSink`，独立记录事件、旧链、新链和检查点bytes，通过实际CryptoPort签发／验真；不调用正式Sink或ORM，不替代原MemoryAudit的旧测试。`audit_contract.AuditSinkContract`由内存与原DjangoAuditSink的PG夹具原样继承原15项及新增可信读取7项，统一核durable升级、event_id冲突、三事件版本、回执、时间顺序、当前／保留只读key、篡改、检查点内容寻址／幂等、已锚定截尾与后缀窗口，且经唯一AuditGateway实际消费。内存只模拟单线程状态效果与失败不发布，不证明DB事务回滚、锁等待、真实重启、文件权限、fsync或库外锚保存；实例共享字典不等于灾难恢复。原PG专项仍独立保留。Sink不签发业务授权，密钥READ_ONLY约束和事件时间校验不等于业务许可到期检查。

持有应用密钥并控制检查点及其可信引用的主体不在此完整性保证内。旧链已有显式隔离审批／捕获／桥接和原归档对账；离线业务恢复及旧源治理仍未完成。

### 12.8.1 旧链快照加密归档（显式隔离入口，无历史原文下载）

M6 `DjangoLegacyAuditArchive.create`只接受test／evaluation服务上下文和明确的旧链长度／尾摘要。单个READ ONLY REPEATABLE READ快照内先以Limits限制两表行数与单行JSON大小，再调用原`AuditLedgerService.verify_chain(entries=...)`验证同一快照，随后按主键序流式送入成熟age。原无参验证器、canonical及hash算法保留；加密期间不锁住旧链writer，之后追加不进入该快照，也不假称已冻结全历史。

归档包含版本化header、旧AuditLedgerEntry完整字段，以及有旧ledger引用或v1事件schema的SecurityAuditRecord行。旧时间和原始事件行仍未认证，header明确两个False保证标志；复制不升级其真实性，不原地修改／删除payload或event。只用BACKUP_PUBLIC，输出写服务所有的0700目录、0600密文和元数据；不产生磁盘明文中间文件。异常保留隔离残留，不自动删除或重传。

create返回`StoredObject`和待入链`SecurityEventV2`：BACKUP事件绑定真实行数、旧尾摘要和归档密文摘要，不包含历史正文。本地初始登记为`bridge_state=pending`，create本身不调用第二个ledger writer，也不表示已桥接。

B的`assemble_legacy_archives`显式装配当前权限owner、M4 `LegacyArchiveFlow`及上述M6，复用原唯一Gateway和同一Sink的read_authenticated；要求已配置ds.audit.v2，只接受ACTIVE BACKUP_PUBLIC，不开放HTTP或默认启动。`LegacyArchiveOwner.run`的user必须来自可信认证，不由请求正文声明；每次重取数据库active用户及`audit.archive_auditledgerentry`权限，不以缓存角色／is_staff代替能力，不自动赋权。audit.0008仅增加该权限选项，不改旧payload。此权限仅批准隔离捕获、原归档对账或已桥接归档的内容检查，不授予历史原文下载、源删除或生产治理。

capture先由唯一Gateway确认AUTHORIZATION v2事件，绑定当前操作者、精确旧count／tail、策略、算法及公钥版本，再调用原M6快照捕获；批准成功不等于归档成功。M4把返回的BACKUP事件交同一Gateway，只有v2回执后M6才以临时文件／rename及文件／目录fsync保存`bridge_state=confirmed`和回执。入口及M6维护拒绝外层事务；数据库入链与本地登记不是跨资源原子，桥接或回执保存失败保留原archive_ref／密文，不能当未发生。

reconcile重新复核当前权限，仅加载原受控目录中的有界登记和精确密文，核引用／事件绑定、权限／大小／SHA-256，再读取已认证批准事件比对原count／tail等，最后以原event_id重放BACKUP并保存回执；不重新capture、重传、删源或自动清理。sidecar的confirmed和本地回执不是新链认证来源。load不持离线私钥、不解密、不验证age标签，依赖服务所有的受控目录，文件摘要核对不能替代离线真实性验证。缺失／损坏登记、密文或批准均拒绝，不推断零效果。离线业务恢复、旧源迁移／隔离／删除及归档密钥轮换闭环仍待，不能据此宣称6-F05完成。

新增M6 `verify_content(stored, event, identity, context)`只做离线归档内容核验，不调用load／sidecar或查询数据库。调用方须提供可信StoredObject及已认证的原BACKUP证据；方法本身不认证传入事件，也不从归档自证批准。服务上下文只限定隔离用途，不替代当前业务授权。BACKUP_PRIVATE经原KeyResolver解析、以memfd交给age；同一已打开密文先核权限／大小／SHA，再有界解密。header绑定归档／批准／环境／旧尾摘要和两表计数；ledger行经原v1验证器逐条核验，security行仅核结构／顺序／归档内引用，旧时间与裸事件仍不具认证保证。

Limits.max_actions分别限制两表计数，max_json_bytes限制header，max_bytes限制单行，不把整份归档套入业务单对象上限。只有预期行全部验证、无额外尾部且age正常退出才返回原StoredObject；不返回原文、不落盘明文、不生成审计回执或恢复数据库。不能把此方法自身的内容验证成功当桥接认证、恢复／下载许可、旧源迁移或密钥轮换完成。

现可经`assemble_legacy_archives(..., identity=明确BACKUP_PRIVATE引用)`显式启用owner.run(operation='verify', archive_ref=...)；默认未提供identity时该操作拒绝，不自动加载私钥。owner重新核对当前active用户与原archive_auditledgerentry权限，且拒绝外层事务。M4先加载受控登记，再通过同一Sink的read_authenticated取得原BACKUP事件，逐字段等于登记候选事件后才调用M6内容检查；本地confirmed／回执不能替代认证桥接。缺失／坏认证证据不解密，失败不自行重桥接、再捕获或清理，成功也不写新事件／回执。此组合需要可用的新链数据库，只有最后M6内容检查不访问SQL；不是空环境恢复入口或无数据库的整条业务链。沿用原显式test／evaluation装配，不开放HTTP、生产或历史原文下载。

### 12.9 显式私有密文备份包（局部能力，默认关闭）

`PostgresAgeBackup`缺省仍为数据库单独备份v1。可信构造显式提供`private_root`、`code_version`和非空`required_keys`后才使用v2，仅test／evaluation；B仅对ds.bootstrap.v2接受这三个完整显式选项并解码KeyReference；旧schema、新schema的原六字段配置均不自动启用v2。缺项／未知字段拒绝，不加载离线私钥或自动寻找历史key。private_root为服务所有的预建私有规范目录，不扫描任意媒体目录或自动纳入孤儿。固定读取M6 PrivateObject的对象引用、密文摘要和大小；数据库检查投影、文件目录、文件读取及pg_dump共享同一exported REPEATABLE READ快照，引用文件缺失／变动则不注册成功。

v2由两个age文件组成：`<id>.age`保存版本化manifest和数据库导出，`<id>.files.age`保存流式标准USTAR中的不可变私有密文。主manifest以大小／SHA-256绑定文件包，并包含目录计数／摘要、代码版本和显式key引用；`StoredObject.version=v2`，其`ciphertext_hash/size_bytes`仅表示主age文件，不是两包总量。文件包只接收`private/<对象ID>/<密文摘要>`普通成员，不使用extractall；完整age认证、文件摘要与目录复核通过后才发送SQL，随后比对恢复库中的文件投影。不是自研分块密码格式，业务20 MiB上限不应用于备份总量。

离线恢复必须配置同一代码版本／引用清单、空数据库和空私有目录，并能以离线身份解析所有声明key；在线仍只解析BACKUP_PUBLIC。声明可解析不证明key清单完整或数据key内容正确，当前未逐对象解密核验全部历史引用。恢复错误可能留下已落盘密文，后续非空目录拒绝覆盖；不假装文件与数据库跨资源回滚。成功回执仍只是DURABLE、chain_version=null，不是链／检查点验证或下载开通许可。

当前仅覆盖M6 PrivateObject单根，不代表资源／反馈／独立执行器旧文件、任务／分享、旧链归档和库外检查点已纳入备份包。新增完整主Django schema隔离演练恢复178表，对12个有序投影及实际交付报告／额度／恢复许可验真，候选状态保留、未登记孤儿不进入包；使用库外明确保留的原检查点及离线READ_ONLY文件key验证新旧链。错data／audit内容与坏检查点是在恢复后的独立验真中拒绝，不是BackupPort在SQL前验证全部业务key；测试没有实现自动开通门。完整业务恢复、全部引用key核对、跨部署对账及开通门仍待实施。

资源原件／封面与反馈附件若由可信装配共用同一个M6私有根，恢复不能只核PrivateObject目录：还须恢复Resource.private_files、FeedbackAttachment.private_file、主体／工单和PROTECTION认证链，并由各自原owner按当前权限及metadata重新取得内部引用；再独立完整open核原文摘要。仍为verified的对象不因恢复或自报状态取得下载权。框架／数据／审计key、policy及明确选定的库外锚须由恢复owner独立保留，不从恢复库选latest；重装当前B需要原ACTIVE引用，不冒称READ_ONLY密钥轮换已实现。这里不包含旧媒体迁移、独立执行器、分享／任务恢复或自动开通服务。

### 12.9.1 显式备份保留（隔离D8，不代表完整恢复开通）

`BackupRetentionRecord`（ds.backup-retention-record.v1）是SERVER_ONLY不可变登记，绑定v2 StoredObject、UTC创建时刻、daily／weekly及文件包摘要／大小；当前M0为46 DTO／21 Protocol。BackupPort的create新增可选cadence，缺省仍不纳管；显式daily／weekly只适用于既有隔离v2双包。创建时由服务时钟记录快照开始时刻，保留信息写入加密manifest及服务私有成功登记，不用文件mtime推断历史备份年龄或类别。旧v1／无保留登记的v2与未登记孤儿保持原样，不自动纳管。

M4 `BackupRetention`按UTC自然日和ISO周（含周所属年份）各留一个最新成功样本，分别保留最近7个日槽和4个周槽；两类独立创建，不把同一份日备份重复计作周备份。相同槽的旧样本及超出份数的旧槽进入预览；未积累足够槽时保留已有样本，停产数周也不会因简单TTL清空最后恢复点。该策略不证明周期任务持续运行或RPO达标。

M6库存只读取服务私有登记，数量受显式Limits.max_actions约束（包括历史退役登记），每个JSON读取有界；对待保留和待退役双包都逐一复核大小／摘要。损坏的新包不能挤掉旧包；缺文件、坏登记或未完成退役使预览失败，不返回可清理集合。这是受控本地登记与密文字节核对，不是在线持私钥进行age恢复认证，也不能证明全部业务key／文件覆盖。

preview无删除副作用；apply仅接受显式确认的完整预览，执行前重新读取库存并要求相同记录集合和顺序。M6退役由该owner调用，先持久化retiring意图，再删除该登记的两个精确age路径，最后保留retired登记和DURABLE本地回执；不删登记／证据、不按glob删除。部分I/O失败返回UNKNOWN并停止批次，retiring阻断后续自动清理，须人工核对残留与已完成记录，不将多文件操作当原子事务。该回执chain_version=null，不冒充ds.audit.v2事件或全部批次成功。

B `assemble_backup_retention`仅显式装配已配置的隔离v2 BackupPort与M4 owner，没有默认清理、调度、HTTP或生产启用。调用方在维护窗口串行执行创建／保留／离线恢复；当前不提供多清理进程或并行恢复的协调承诺，也不开放不经M4预览批准的仓储直调。只处理本轮受管备份副本，不清理业务私有文件、密钥或库外检查点；完整业务恢复开通、周期执行与RPO／RTO仍待。

### 12.10 合成蜜标工具与出口注入点（尚未正式装配）

`CanarySeed`（ds.canary-seed.v1）只保存32位hex种子标识、knowledge／database／challenge目标类型、对象引用／版本、test／evaluation环境和域；不接受任意邮箱、地址、卡号或生产环境。M4 `CanaryTools.tools`显式提供`canary.plant`／`canary.check`两个可调用项，接收受控目录和当前授权回调；字典中出现工具名不等于已注册到运行中的智能体。没有新识别类别、后台线程或定时扫描。

每个种子生成三项确定性假值：example.invalid邮箱、三个TEST-NET网段之一、000000非真实发卡前缀的Luhn测试卡号；埋点包用受限JSON明确标记synthetic与目标元数据。plant只接受目录内种子和匹配对象版本的AUDIT／SECURITY_AUDIT上下文，当前授权回调须返回准确ProtectionContext，不能用角色或True冒充批准。注入的目标owner负责合成目标校验及埋点／登记原子持久化，须返回同一CanarySeed；当前仅测试owner回调，尚未提供业务写入适配或许可签发。

M0 `CanaryCheckPort.check`返回回执tuple或ProtectionError，供出口注入，不让M7／M9导入M4实现。check检查受限TEXT／JSON的原样已登记值（包括JSON键和嵌套字符串，不拼接片段、不做大小写或格式归一化），另接受仅用于EXPORT的实际输出TableSnapshot，检查original_text及column.label而非normalized_text。保留工作表标题另以解码metadata检查；压缩／加密／表格二进制仍拒绝，不宣称已扫描。目录数量受显式Limits.max_findings限制，输入按工具Limits检查。每个命中种子生成一个SecurityEventV2，复用唯一AuditPort／Gateway／Sink并要求ds.audit.v2入链回执；仅包含命中类别数、目标引用／版本、种子标识、出口、trace和策略绑定，不记录蜜标原样值或正文摘要。空tuple表示无命中，错误不能当无命中；库外锚点窗口仍沿原链语义。有限TEST-NET地址可能被多个种子共享，全部匹配目标各自记录为候选来源，不把地址当唯一泄露源证明。

三个实际代码出口现在支持显式注入（缺省None保持原封口，不等于启用蜜标）：OfficialAI在保密处理及ProtectionPort之后、key解析／OAuth／WebSocket认证与发送之前检查最终业务payload，命中拒绝发送；SafeLogFormatter在原metadata-only清洗及格式化后只检查最终安全文本，命中／失败分别输出固定LOG_CANARY_BLOCKED／LOG_CANARY_CHECK_FAILED，不渲染已丢弃原文、不递归日志；install_safe_logging可显式传递同一checker、LOG上下文及Limits。TableReportExecutor在真实serialize→parse之后检查输出表格与保留标题、在原M1复检／canonical roundtrip之前告警，命中不加密或写候选；原复检与roundtrip没有移除。

启用表格check时，prepare须由可信owner另传canary_context，绑定EXPORT、环境／域、execution.subject_ref／authorization_id、ObjectContext.object_uuid／版本及execution_id追踪；不能从ObjectContext自行签发授权。CanaryTools仍以注入的当前权限owner复核。模型与表格错误不当干净结果，日志错误只产生固定失败文本。告警表示检查点发现拟输出的原样值，不表示网络已泄露或客户端已收全。

运行时新增M9 `CanaryToolRegistry`和`AgentGateway.available_security_tools`／`run_security_tool`显式入口。工具参数为封闭对象：plant仅seed_id，check仅artifact_ref；不接受模型自报身份、授权、上下文、正文或任意文件路径。每次调用由可信owner的resolve_context按操作／引用／当前用户取得ProtectionContext，check再由load_output加载与该上下文绑定的实际解码出口内容；不从工具参数补造权限。工具结果仅固定状态、种子ID或告警数，异常正文不进入结果，不把错误当clean，不自动重试。M9仅依赖M0及注入，不引入M4／M6实现；该运行时增量未新增DTO，备份保留增量后的M0为46 DTO／21 Protocol。

网关缺省security_tools=None，工具列表为空、调用固定CANARY_TOOLS_DISABLED。该显式入口不加入LearningToolRegistry的自动只读检索列表、不在普通学习任务中触发埋点，不新增模型调用或后台扫描。业务知识库／数据库／题目owner落地、当前权限与产物供应器、B启用、模型tool-call协议接线、重启后的可信目录恢复及退役管理仍未完成。显式合成夹具可驱动运行时及实际出口代码，但不是正式业务装配或生产批准；该增量不能将蜜标门禁记为通过。

### 12.11 显式上传解析边界（默认业务路由尚未启用）

M9 `PrivateUploadBoundary(get_response, limits=...)`为同步消费上传的请求显式安装唯一`BoundedUploadHandler`，必须先于POST／FILES解析。Limits在处理器入口校验一次，不从环境或客户端声明加载；每个part按实际收到的字节计量，写入BytesIO前拒绝超过max_bytes的chunk，不依赖Content-Length或Django默认小文件阈值，不降级TemporaryUploadedFile。已完成part仍在请求内驻留，故同时持有的buffer数使用原Limits.max_inflight_objects（基线2）；不是新增“请求总量20 MiB”，两个各自合格的对象可同时处理，也不是已实现跨请求并发限流。

解析完整后返回原InMemoryUploadedFile供原业务格式校验及后续加密用例同步消费。超限／过多文件抛明确拒绝，不用StopUpload吞错后返回部分成功；未完成multipart拒绝，解析或view异常与正常返回都关闭本请求的全部buffer。返回view后不能继续拿该上传对象做流式响应或当持久私有引用。该边界不存文件、不认证用户、不发布／下载、不替代CryptoPort／PrivateStore，原资源及封面validator未改。

当前仅隔离测试显式安装此请求边界，resources的新增owner由B辅助函数装配（见下一节），但默认settings／HTTP路由、feedback与独立执行器均未启用。Django ASGIHandler在中间件之前仍有SpooledTemporaryFile请求体路径，单个multipart handler不能覆盖该路径；网关／ASGI缓冲及跨请求资源预算仍待。BytesIO不证明交换保护或绝对内存清零；原D7窄项环境受限登记与完整文件级扫描要求不变。

### 12.12 新资源原件与封面的私有候选（未开放下载）

M4 `PrivateFilePreparation`仅以注入的CryptoPort／PrivateStore执行seal→write_candidate→verify，返回verified StoredObject或原ProtectionError，不publish、不认证主体、不操作ORM。资源域`ResourcePrivateUploads`消费原serializer已校验的文件和可信request.user；当前数据库重取active的teacher／admin，不以缓存角色代替当前权限。只接受内存上传对象，读取最多max_bytes＋1后由原BoundedPayload校验实际上限。原件与封面共用新object_uuid，field_ref分别为resources/file与resources/cover_image。上传authorization_ref仅标识本次主体上下文，不是公开发布、原文读取或生产批准。

两份候选全部验真后才创建pending Resource：file与cover_image为空，file_size来自实际原件长度；`private_files`（resources.0004）保存版本化内部context／StoredObject引用，不保存原文，也不在公开serializer中输出。封面准备或资源入库失败保留已写密文，不创建成功资源、不删除或发布候选；不能据此宣称数据库和文件原子提交。旧审核状态改approved仍不发布，新资源通过原下载入口返回404。

文件处理完成后，资源与每个实际文件的SecurityEventV2在同库短transaction.atomic提交；原件和可选封面各一条PROTECTION事件，不将两个密文hash混称单文件hash。每条事件绑定资源ID／field、原对象UUID、当前主体、明确策略和data key版本、该文件实际字节数和ciphertext_hash；共同report摘要绑定入库资源的metadata及全部私有引用，不是MaskReport。事件不包含标题、描述、原文件名或文件原文。任一回执缺失、v1、仅outbox或审计拒绝都回滚资源及已入链事件；真实入链后DB失败同样整体回滚，已写密文保留。真实提交后确认丢失返回DELIVERY_UNKNOWN，保留资源及全部事件、不自动重试／删除／发布。可信引用及显式内部原件读取见§12.15；完整生命周期、上传unknown对账、清理与当前授权下载仍待。

B `assemble_resource_uploads(config_path=..., private_root=..., project_ref=..., source_reads=False)`显式装配原FileKeyResolver／CryptoPort及0700私有根，固定evaluation；不是start_application启用项，没有新增配置文件开关。内部source_reads参数见§12.15.1，默认不授予原件读取能力。ResourceUploadSerializer只有服务器context显式含private_uploads才走新owner；值None拒绝，键不存在保留旧unbound基线。测试子类注入不代表默认ResourceUploadView或ASGI已启用。既有文件未迁移，必须先具备完整一致性恢复点；旧基线仍不被宣称满足新私有文件门禁。

资源容量增量仅测显式组合：20 MiB合成原件通过真实multipart／原serializer与格式校验／当前owner／PrivateFilePreparation／CryptoPort／PrivateStore，完整open在事务外验真后以短事务提交PROTECTION新链；仅留下verified候选及pending资源，不发布、不授下载。20 MiB＋1在prepare前拒绝并关闭活动buffer。单次耗时／Python分配峰值／测试runner生命周期RSS高水位见acceptance；不是生产并发预算、进程树RSS或默认HTTP路由吞吐，不据此放宽原Limits或更改业务校验。

资源进程崩溃增量在测试拥有的worker中对三个20 MiB上传窗口执行SIGKILL：密文及目录fsync后、登记前只留未登记密文；验真后、资源创建前只留verified私有记录；资源与PROTECTION提交后、返回view前保留两者。重装原B后都不能因自报published而读取，密文本身可完整认证；最后一种以已知资源ID重复reconcile只观察原保护事件，不新增资源、候选或事件，也不发布。没有证明失去业务ID时的操作引用恢复、部分文件写入时清理、产品崩溃清理或完整交付；不能将测试父进程最终删除其自有夹具当产品清理。

### 12.13 未开通上传的实际入口关闭

正式配置启动现在将B的private_upload_middleware置于最前，对原资源上传路径及反馈工单UUID附件上传路径（带／不带尾斜线）在读取请求体前返回空503、Cache-Control: no-store，不进入CSRF、认证或业务FileField。反馈路径由B注入完整匹配模式，不拦截工单详情、证据补充或附件下载路由。根ASGI application经B包装，同一路径在调用Django handler及receive之前拒绝，避免原SpooledTemporaryFile先接收私有原文；路径前缀按Django的root_path／FORCE_SCRIPT_NAME语义剥离。此M9边界只处理HTTP拒绝，不存储、不解析、不认证或发布；其他路径与非HTTP scope原样交回原application。

这是一道未开通入口的拒绝门，不是ASGI上传实现，也没有添加新的请求总量限额。资源及反馈私有候选owner仍仅显式装配，不向默认HTTP开放。无DATA_SECURITY_CONFIG时保留原WSGI／ASGI入口行为；旧unbound路径不被称作私有上传合格实现。上游反向代理／服务器在ASGI receive之前的缓冲、完整文件生命周期与独立执行器仍待改造，不据本次拒绝探针宣称6-F03／F04完成。

### 12.14 新反馈附件的私有候选（未开放下载）

反馈域`FeedbackPrivateUploads`消费原AttachmentUploadSerializer校验后的文件与visibility；原扩展名白名单和10 MiB业务限制不变，不因D7的20 MiB上界放宽业务规则。owner重新读取active用户及当前工单：所属student或submitter可上传，teacher／admin／superuser沿用原权限；非教师身份不能写仅教师可见附件。缓存角色、旧工单归属及客户端传来的服务／引用不授予权限。

仅接受InMemoryUploadedFile，经同一M4准备链写verified密文；attachment_id与object_uuid一致，context绑定工单及上传主体。FeedbackAttachment.file为空，实际长度和原内容摘要由owner计算，`private_file`（feedback_center.0003）只存版本化内部引用，不进入公开payload。准备失败不创建附件；DB失败保留密文，不删除、不publish，不承诺文件与数据库跨资源原子。原下载先执行工单／visibility检查，私有或空文件附件返回503且不调用FileField.open、不记成功下载；改变visibility不会发布候选。

反馈owner在加密／文件工作结束后，以短transaction.atomic将附件元数据与SecurityEventV2经原唯一AuditGateway一起入库／入新链。事件为PROTECTION／SUCCEEDED，不是DELIVERY：ciphertext摘要来自StoredObject，report摘要绑定附件／工单／上传主体、文件名、类型、实际长度、原摘要、visibility与内部引用；report在这里是上传元数据摘要，不冒充MaskReport。事件只保留引用、计数、版本与摘要，不含原文／文件名正文。B注入同一Gateway、明确policy binding、clock及data key引用；旧v1／仅outbox回执拒绝，审计失败回滚附件和新事件，密文仍保留。实际提交后的确认丢失返回DELIVERY_UNKNOWN，不删除已提交附件／事件、不发布候选，不自动重试。既有FeedbackAccessLog仍是业务访问记录，不能替代新链回执或证明HTTP已收全。

B `assemble_feedback_uploads`固定evaluation并要求0700私有根，未接start_application或默认HTTP启用。只有服务器显式组合的view属性private_uploads才走新owner；属性为None拒绝，未提供保留旧unbound基线。B同时将原Sink的read_authenticated显式注入owner，不新建审计入口。

`FeedbackPrivateUploads.authenticated_reference`只接受服务器调用，重新读取当前active用户、附件及工单归属，沿原teacher／admin／superuser、student／submitter和visibility规则检查访问；未经许可不调用审计读取。随后从已认证新链取得原PROTECTION成功事件，逐一绑定当前持久metadata摘要、上传主体／工单／附件、对象版本、算法、实际长度及密文摘要，拒绝改名／换类型／改长度／原摘要／可见性／上传主体／迁移工单／交换内部引用和旧FileField回落。原Context与服务器构造的原上传身份相符后，返回`(ObjectContext, StoredObject)`，其中上下文基于当前访问者重新构造，不从wire解码SERVER_ONLY上下文，不把原上传authorization_ref转交给当前访问者。

返回值是内部不可变引用二元组，不是文件内容、公开URL、下载许可或持久提交证明；不读文件、不解密、不publish、不签发审计，不改变verified状态。历史metadata被修改后必须有相应可信业务更新流程才能继续读取，不能自动重签旧上传；删除上传者后的空引用也不回退。此处是读取当时的业务权限检查，未来交付仍须按其生命周期重新授权及完整验真。资源可信引用消费、当前授权下载、清理、上传unknown对账及完整恢复仍待，旧附件未迁移，不移除正式入口拒绝门。资源owner的上传新链语义见§12.12。

### 12.15 资源可信引用与已提交上传观察

`ResourcePrivateUploads.authenticated_references`由B注入原Sink的认证读取。当前active上传者或is_staff复核者才可加载；仅有teacher／admin角色不是其他上传者资源的读取许可。原件与封面分别绑定原PROTECTION事件、完整资源metadata和密文摘要，任一失败不返回部分引用。返回各文件的`(field, ObjectContext, StoredObject)`，上下文绑定当前访问者；不读文件、不解密、不publish。资源status等已绑定字段不能被直接改写后继续当作原上传证据使用，后续审核／编辑须有可信更新流程。

两域`reconcile`仅为已知业务ID的内部正向观察：调用前要求autocommit且无外层atomic，在自身只读事务中调用上述当前授权／认证引用读取，事务正常退出后才返回。实际上传提交后确认丢失可据此重新观察；未提交的调用方事务不可自行确认。它不是DeliveryReceipt，不表明网络交付、负向零效果证明或文件完整open；缺行、权限拒绝、坏链不能据此自动重传、释放额度或清理候选。尚缺HTTP稳定操作引用及完整准备／清理对账接线，不把这一窄入口当两域unknown全生命周期完成。

### 12.15.1 资源原件的显式内部认证读取（未接正式交付）

B的`source_reads=True`才将原M6 `open_verified_source`注入资源owner；参数必须为bool，且显式装配须具备v2认证链，默认False和旧无新链组合均不会获得该能力。`read_original(user=..., resource_id=...)`要求autocommit且无外层事务，先复用上述当前用户／资源权限及全部原件／封面认证引用；任一引用认证失败不打开文件。只将排首位的原件交给M6，不读取封面原文，不把其他上传者的admin／teacher角色当许可，也不要求原上传者继续保有上传新文件的角色。

M6在短读事务中重取完整对象身份，只有数据库与StoredObject状态均为verified才可作为该内部来源；candidate、published、未知行或换绑拒绝。文件读取和完整Crypto.open在该事务结束后执行，复用原文件权限／大小／SHA和一次AES-GCM认证及有界载荷解码，成功才返回BoundedPayload。缺／错DATA key、坏文件、截断或完整认证失败不返回原文；读错误不写状态、不删除或修复文件。它不改变M0 PrivateStore协议：原read仍只接受数据库published且只返回密文封套，verify／publish原语义不变。

这不是下载、原文审批、RevealPort或完整ExportFlow.load_input：资源上传保留的media_type仍为BINARY，尚无Resource到导出asset_version的权威映射、冻结请求及源计划重取组合。返回内容只供已授权内部处理，不新签PROTECTION／DELIVERY，不改变pending／verified或下载计数，不publish、不授予分享。正式HTTP拒绝门、M8语义及源计划默认批准状态均不变。

### 12.15.2 私有原件至交付的合成集成边界

`resources.test_phase6_source_delivery`仅在测试中把真实上传、认证读取、原M8、目标审批、报告、Risk／Quota／Flow和v2审计串联。TXT仍由原白名单上传并返回BINARY；仅测试loader声明CSV解释，测试构造包含原件身份的资产映射、源批准、冻结请求指纹及风险授权。没有新增业务owner、格式支持、权限、正式供应器或完整交付B。目标批准仍独立来自当前Django审批owner，不能替代当前原件访问权或认证PROTECTION。

真实成功只产生一次逻辑交付／结算；重新装配并回读DTO后可返回同一历史回执，不重复打开原件、reserve或publish，也不授予下载。原件权限拒绝、缺认证上传证据或坏密文均不进入转换；原件打开后撤销目标许可仍在最终提交拒绝。该测试未装恢复授权，已知失败保留reserved及原准备状态，不自动release、不伪称unknown。合成集成通过不改变上一节的正式来源缺口或HTTP拒绝门。

### 12.15.3 已交付产物读取（内部实现，未向B／HTTP开放下载）

`ExportFlow.open_delivery(binding, attempt_ref=...)`在当前目标许可、报告MAC、认证DELIVERY、锁外完整open及输出摘要通过后，以短UoW复核原consumed授权和committed额度，记录独立AUTHORIZATION放行尝试；不重新计额、发布或读取原件，不表示客户端收全。B1已修复额度／审计等待后较短风险期限失效仍可能返回产物的问题：保留原风险行锁，在提交放行尝试前再次复核当前授权及原期限。纯测试有实际失败复现及12项通过证据；真实PG读取9项为8项ok、1项最终审计锁SQL定位断言失败，最后的期限拒绝／状态不变断言未执行。该组合整体退出1，失败未解决，不以内部实现冒充最终锁等待验收或正式下载装配；详情见acceptance。

`QuotaPort.read_committed`的Django／Memory实现以原QuotaService.observe为业务状态来源，精确核完整binding与window／limit／ttl，只有已结算状态及原terminal receipt相符才返回历史回执；过期历史可读但不是当前下载许可，不更新、续期、预占、结算或对账。commit证据按原生成规则核对，reconcile仅保留持久化引用，未增加独立鉴证来源。B1已完整验证26项PG共享案例（原14＋新增12）。

`RiskPort.recheck_delivered`已接原风险owner及独立Memory实现。原owner沿decision→authorization行锁核原准入key、原签发key与完整执行binding摘要、consumed状态、当前授权／审批及决策／授权原期限；不读active hold、不重新decide／assess／claim／consume、不更新或收紧期限。只读是业务状态只读，不是取消短UoW行锁。DS签发新增完整binding摘要，旧调用未提供该摘要时仍沿原算法；历史缺摘要的DS签发不能自动升级为可下载，不补写或续期。原claiming＋active hold的执行检查不被替代。

### 12.16 恢复许可管理与仅恢复装配

`audit.RecoveryPermissionOwner`重新读取当前active Django用户；签发要求`security_policies.add_recoverypermission`，撤销要求`security_policies.change_recoverypermission`，沿Django现有权限语义（含superuser），不以业务role=admin／teacher或is_staff代替权限，不自动给任何账号分配权限。只有显式test／evaluation装配可用；内部请求要求类型化ExecutionBinding，不接受客户端wire冒充来源权威。许可绑定完整binding摘要、当前active受领用户、独立release／reconcile标志及明确期限；许可不审批ActionPlan、不延长旧导出授权，也不授予下载。

M6 `DjangoRecoveryPermissionWriter`将许可签发／撤销和AUTHORIZATION新链事件放在同一短事务，事件由原唯一Gateway写入，摘要绑定全部许可字段。v1／不足durability的回执不能提交；失败回滚许可和事件，实际提交后的确认丢失返回UNKNOWN并保留opaque许可引用。重复撤销可保留首次revoked_at并增加本次操作者的审计观察，不重新启用许可。外层事务仍由调用方负责，不以内部收据宣称外层已经提交。

B `assemble_recovery_permissions`只装配这一owner；`assemble_export_recovery`则使用同一Gateway和owner，仅提供原ExportFlow的release／reconcile绑定方法，不装配或暴露execute／commit／publish能力。原报告仓储和QuotaService仍分别是准备隔离及额度唯一writer，窗口／上限／TTL由可信装配显式给定且须与原预占一致。Flow取得报告锁后才调用owner重新读取当前用户，再由原DjangoRecoveryAuthorization锁定明确许可；装配后停用用户也不能利用缓存身份恢复。缺／撤销／过期／错binding许可保留unknown容量，不做自动释放。它不是正式交付owner或完整恢复开通服务。

B1新增`security_policies.0009_export_binding`：ExportReport在begin／直接put创建时保留完整binding，`load_binding(execution_ref)`从服务端记录解码一次并核execution／idempotency／摘要／环境；旧prepared仅可沿原document.binding取回，不重写历史记录。旧preparing缺意图、缺执行或DB错误保持DELIVERY_UNKNOWN；坏绑定拒绝，不推导为零交付。执行binding不包含完整冻结请求或完整源计划，不能代替正式供应器。

M9新增`POST /api/data-security/exports/recovery/{release|reconcile}/`，只接受execution_ref和permission_ref。B仅在v2／evaluation配置显式给定`export_recovery={window_key,limit,ttl_seconds}`且存在认证v2链时注入；缺选项为503，v1不接受该配置。当前HTTP认证用户及服务端重取binding交原Flow，不能自报数量、成功、证据或完整binding。零效果由锁内报告终止约束和原额度状态共同决定，缺行／缺回执不单独证明零；审计及额度同UoW，确认丢失保持UNKNOWN。响应不含文件、binding或新下载许可，已知交付只称logically_delivered，始终明确network_delivery_confirmed=false。本轮9项HTTP均在子进程退出检查失败，未取得父测试的响应／效果断言结果；根因未确认、未修复，当前不能按已验入口启用。实际失败记录见acceptance，不据此宣称普通启动、完整恢复或下载开放已验证。

### 12.17 精确目标计划审批（显式隔离入口）

`audit.ExportPlanOwner`仅接受内部类型化ActionPlan／完整ExecutionBinding／ObjectContext，不接受wire字典作为权威输入。当前active请求者必须与binding.subject_ref一致；批准者另需Django `security_policies.add_exportplanapproval`权限，撤销者需`change_exportplanapproval`，沿既有superuser语义，不以业务role或is_staff代替权限，不自动赋权。复用M0 Approval要求两人分离，批准不改变plan.content或plan_hash；未解决项、过期、非合成来源或环境／域不匹配拒绝。source的provenance／approval_basis非空只是准入条件，不是对源记录真实性的认证。

M6 `DjangoExportPlanApprovals`只保存Approval文档、plan／完整binding／context摘要与期限／撤销时间，不保存原文或完整actions。许可写入和AUTHORIZATION v2经原Gateway同库短事务提交；旧链／不足durability回执与审计错误不能留下许可。管理入口拒绝外层未提交事务，提交确认丢失返回UNKNOWN与稳定审批引用，不自动再批准。`reconcile`以原draft／完整binding／context及该引用重新观察：当前active管理者仍需add_exportplanapproval权限，锁定未撤销的精确许可，读取原AUTHORIZATION的认证事件并比对全部审批metadata，再检查当前期限，自身读事务正常退出后才恢复原Approval到draft。返回的是原approved ActionPlan，不签发新批准或回执、不写事件、不增加额度；缺行／换绑／坏文档／坏链／已撤销或过期均不能作为无效果证明。消费时仍须另行复核当前请求者，管理观察不授予下载。

消费时重取当前active请求者与精确许可，锁定许可行后才检查期限；撤销、换plan／binding／context或伪造Approval均拒绝。由原ExportFlow调用时，预占前先复核，提交段报告锁后再次复核，许可行锁跟随Flow外层事务持有，不增加reserve或第二个风险／额度writer。许可表是当前审批权威，消费不额外把许可文档通过审计链重新认证；AUTHORIZATION事件不是下载或交付回执。

B `assemble_export_plan_approvals`仅在明确配置新链的evaluation环境装配管理／当前审批owner，不装配execute／HTTP，不授予源访问、风险批准、额度或下载。真实Flow消费测试仍用合成request／source／input供应器，不代表正式资产／源计划owner或完整交付B已实现。

### 12.18 旧执行器的显式私有候选准备

`execute_authorized_export`仅在可信调用方显式传入`prepare_private`、`private_project_ref`和M0 `Limits`时消费原M4／M6准备链；只允许evaluation、autocommit且无外层事务，限额不能超过旧执行器的配置上限。owner只依赖M0，不自行装配密钥／存储或访问M6表。D1仍为同进程可安装库＋端口：原执行工程注册原M6 app，不将第二套Django工程装入主后端，也不是新增独立部署批准。

原签名、输入／计划／请求指纹及claim保留。私有模式幂等operation与旧执行分离，并额外绑定project_ref及完整Limits；同一授权不能靠换模式或key重复消费。短claim事务先记录版本化私有意图，服务端attempt UUID作为稳定ObjectContext身份，随后在锁外转换、加密、写候选及完整验真。第二个短事务复核active attempt、fence、授权及lease，再保存原StoredObject和转换摘要，状态仅到prepared／verified。该metadata没有成为可信MaskReport或认证PROTECTION，不创建ProtectedArtifact、execution.completed、配额结算、发布或分享；旧receipt中的输出与完成时间仍空，before_publish义务仍未满足。

准备确认丢失或普通异常保留稳定意图及密文，进入repair_required／unknown，不自动删除或重传；真实owner事务已经提交后丢确认，不将prepared改成失败。过期命令遇到带私有意图的running attempt，同样只记unknown／repair_required与preparation_unknown，完成时间保持空；重复巡检不再处理，旧无私有意图的stale／failed语义不变。这些本地状态及outbox不是新链回执或零效果证明。

本增量未装配正式B，也没有把原HTTP view改为调用此模式；原legacy HTTP、临时上传、存储／分享／下载仍待完整改造，不能称执行器HTTP已关闭或全部密文。CSV合成用例的私有准备通过，不替代全格式／上传临时区扫描、完整交付、恢复或开通验收。

### 12.19 尚未实现的交付保证

ExportFlow内部execute已实现预占／准备及已知失败／unknown分流，真实PG执行及故障组19项分两组通过；B1又补上述内部读取复核、保留binding及仅引用恢复HTTP，均不等于完整正式交付B。可信资产／完整冻结请求／完整源计划供应器和6-F02正式owner矩阵未完成；资源／反馈／独立执行器私有文件完整接线、检查点定期维护／恢复接线、旧源治理／离线业务恢复及完整备份恢复仍待其他块。

B1登记P6-B1-SOURCE-CONTRACT待授权：原P5批准仍有效，但明确只准测试golden，不能把测试source approval／CSV解释／请求／常量ALLOW接进正式B。首个正式evaluation来源、登记／源批准／当前使用许可及风险输入权威尚待明确；mainline1源环境与B evaluation在冻结M8要求相等时不兼容，真实PLAN_APPROVAL_REQUIRED不绕过。未自行创建新来源契约或修改格式／环境／批准位；详见实施报告及E6的b1-source-contract-review-01.md，不索要生产开通或重开第五期验收。

MaskReport自报hash、SERVER_ONLY、文件ready、入outbox或HTTP开始都不是客户端收全或可信成功证据；output_hash与ciphertext_hash保持不同语义。旧审计链没有获得新链保证。本节只记录已实现的基础边界，不把尚未接线的目标写成已有能力。

### 12.20 B1四点批准后的现行边界（2026-11-08；未完成）

§12.19中P6-B1-SOURCE-CONTRACT待授权是批准前历史；四点批准现已有效解除受限登记／源批准／当前使用许可、资源原件逐对象CSV／COLUMN_V1及mainline1拒绝的范围。TXT全局格式、上传白名单、M8、原P5及生产状态不改变，源／目标／风险许可仍分离。

原owner及共享Quota契约的unknown release拒绝码仍是AUTHORIZATION_DENIED，M9按现有映射返回403；不能为新HTTP用例的409期待擅改M4／Quota原码。默认恢复未配置仍503，经正常5xx审计新增SecurityAuditRecord不代表业务恢复发生，也不增加AuthenticatedAuditEntry。原两项HTTP业务断言仍FAIL，未修改或删除，不据此宣告HTTP开放；完整恢复效果与逻辑／网络口径仍按原契约。

新P6-B1-RISK-AUTHORITY在此为09:24批准前截点：当时仅登记正式COLUMN_V1风险权威落点缺口，未新增owner／完整供应器／交付B，详见R及E6的`b1-risk-authority-blocker-01.md`。当前授权与实现以§12.21为准；不以源批准／目标批准／报告MAC代替风险，不造等级映射、填缺项零值或自动批准。

### 12.21 B1最小风险供应器与完整来源重取（2026-11-08；实施中）

用户09:24批准「授权按需最小新建（缺哪个补哪个），B1 续工」。按实际缺口只新增ColumnRiskOwner的持久化条件风险许可／审批；没有同时新增画像、历史特征或模型生产器。新增权限为独立add／change／use_columnriskpermission，风险许可明确绑定完整原Risk请求、源文档摘要、资产、scope、domain及精确policy binding。`risk_inputs={}`生成实际资产的MISSING／unknown画像，不是完整、低风险或零；原policy-m0产生REQUIRE_APPROVAL，只有实际第二人批准及当前use权限可满足原审批状态。B／C／D需要的历史仍缺失，即使客户端声称完整或报零也保持DEFER。原不可变decision.action、原Risk DTO和精确`ds-risk/`幂等key不改，mainline1正向／生产不开放。

ResourceExportSources以明确权限登记现有资源原件、资产版本、逐对象CSV解释、完整SourceDocument／scope／actions、完整冻结请求及风险输入，登记／真实源批准／当前使用授权各有独立状态和认证v2证据；原上传者或staff ACL不因管理权限而消失。源批准与目标Approval严格分离，上传白名单和全局TXT类型不改。COLUMN_V1的source_state仍not-declared，源批准依据来自真实owner及审计；不把SourcePlanBinding元数据或恢复用ExecutionBinding冒充完整来源。

DjangoResourceExports在进入ExportFlow前重取原件引用和版本、全部冻结请求、完整源计划、认证风险grant／approval及当前目标批准。grant认证保存原实际ExportRiskAssessment；后续load恢复原DTO并匹配原decision，不在私有helper中重研判。完整同绑定重放只使用既有执行和回执，不重开原件、不新增decision／claim／reservation／发布或结算；已交付产物读取另核当前权限、报告MAC、认证DELIVERY、完整文件及consumed／committed状态，不授予网络收全保证。

v2 B只在evaluation、真实认证新链及显式export_delivery配置下装配；无配置保持关闭，不引入执行／下载／审批签发HTTP，公共契约与生产批准状态未升级。引用恢复HTTP仅接收execution_ref／permission_ref，未知release仍AUTHORIZATION_DENIED→403；缺省503保留既有5xx SecurityAuditRecord。已有DeliveryReceipt的恢复HTTP状态是logically_delivered，零结算QuotaReceipt是committed，均不称网络收全。独立两项裁定及8项修正smoke已通过；60项组合实际58 ok／2 FAIL，按实际字段／状态仅修新测试。后续18项完整17 ok／1 FAIL：三处真实等待均通过，唯一新增故障注入误拦类方法而非B已保存的write_permission回调。只修实际回调命中点后，审批原许可对账与新普通启动双进程准备竞争2项完整通过；竞争者真实begin=False且所有业务阶段计数0，赢家只一次交付／结算。该截点未改产品授权或审计契约，原18／60失败保留，不拼接完整成功。普通全app dry-run后已确认无drift，但不等于私有迁移／回退通过，不称B1或整期完成。

后续四项静态遗漏已由主线程普通启动真实 PG 复现（3 FAIL＋4 FAIL），再作三文件最小修复：Flow 在最后额度／审计等待后重取当前源／目标／精确版本 policy；逻辑提交在写 DeliveryReceipt 前还复用现有 recheck_delivered 观察 consumed 授权，不重研判、再次消费或结算。此处不新增锁类型、source_deadline 字段或替代政策；policy 仓储读取仍不声称有行锁。原件读取、完整证据认证、文件与密码工作继续在持锁 Flow UoW 外。

新条件批准在取得原 decision／permission 锁后重新获取审批者当前 CHANGE 权限及 active 状态，再签发批准；已签发的历史有效审批不因原审批者后来失权自动失效。目标批准 A 已实际提交后，源指针保存失败或提交确认丢失均保留 A.approval_ref 作为返回 trace_id，供原 reconcile_target 重取同一批准；不自动再签、不以源指针缺失当零效果。

七个原样反例 `b1-authority-repairs-postgres-01` 完整 7 ok、218.646s、exit 0，含实际最后账本等待、当前较短源许可过期／真实 policy.retire／consumed 授权过期的拒绝与状态回滚，以及失权审批拒绝和原批准 A 两次对账后唯一结算。此前 373 组的 180 ok 仍为中断部分结果，旧失败不覆盖；当前完整 457（正式 84＋原域 373）选组在途，尚不称 B1 或候选验证通过。详见 acceptance 及 `b1-formal-authority-review-01.md`。

### 12.22 B2 HTTP 私有文件与稳定操作引用（2026-11-08；写入待真库验证）

本节是 B2 的现行实现说明，§12.11–12.18 中“仅辅助装配／HTTP 尚未接线”等描述保留为较早截点；不改写 B1 历史成绩，不表示 B2、G06 或第 6 期已验收。只允许明确的 evaluation 装配，不增加生产、旧源治理、恢复开通或蜜标业务权限。

**身份与准备。** 新 `FileUploadOperation`（`ds.file-upload-operation.v1`，SERVER_ONLY）使 M0 当前为 47 DTO／21 Protocol。它保留 operation_ref、actor_ref、scope_ref、request_hash、服务器 object_uuid、1–2 个 field_refs、state 与 result_ref。HTTP 上传和分享创建要求规范 UUID 形式的 `X-File-Operation-ID`；该 UUID 只标识调用方的重试，不选择密码对象 UUID。操作引用按当前主体及原域作用域隔离，反馈还绑定工单；更换内容、元数据或字段集合不能复用原意图。内部二进制 SHA-256 绑定实际输入，不对敏感 `BoundedPayload` 调用公开序列化／`content_hash`，原敏感序列化禁令保留。

M6 `PrivateFileOperation`（`security_policies.0010`）在密文 I/O 前提交意图，在 `write_candidate` 前保留精确 context、输入摘要和预期密文路径／摘要／大小；真实文件准备、完整认证在行锁事务外。资源／反馈的业务行、v2 PROTECTION 及 operation 的结果指针只在最后短事务一起提交。原件与可选封面共用对象身份、字段不同；只有全部字段准备并验证才提交业务对象。FileField 为空，上传仍是 pending 资源／verified 候选，不是公开发布或逻辑导出。

状态只沿 `preparing → prepared → committed`、`preparing/prepared → aborted → cleaned` 或 `committed → retired → cleaned` 推进。每个操作在私有根持有非阻塞 `flock`，覆盖准备、正向对账和负向清理；忙碌、缺意图或读库失败保持 UNKNOWN。只适用于共享同一受控本地根及文件锁语义的进程，不宣称分布式协调。没有“等待若干秒就接管”的租约；进程退出由 OS 释放锁，锁文件保留，禁止 unlink 后重建成第二个锁身份。

**正向与负向对账。** 凭操作 UUID 可重取业务 result_id，不必猜丢失的资源／附件 ID；同一已提交请求重放不重新加密、建业务行或写上传事件。准备对账只认预先保留的精确文件，允许恢复 fsync 后登记确认丢失的窗口；长度、摘要、上下文及完整 tag 均须相符。缺行、缺文件、半份原件／封面或未完成对账不等于零效果。DELETE 先按当前主体／原域权限经唯一 Gateway 记录 AUTHORIZATION 并在短事务提交 abort/retire tombstone，再在锁外删除保留的精确候选文件；清理确认丢失沿原 tombstone 重试，保留意图、引用与事件，不按目录 glob 猜孤儿、不删除已 published 的导出产物。M6 的 `retired` 是内部不可读状态，不扩展公开 `StoredObject` 的 candidate／verified／published 集合。

**原件读取与引用分享。** 资源原件／封面只允许当前 active 上传者或 is_staff 复核者，approved 状态或普通 teacher/admin 角色本身不授予他人原文权限。反馈沿当前工单 student／submitter、teacher/admin/superuser 及 visibility 规则；旧缓存身份、迁移工单或篡改上传 metadata 不放行。两域在完整解密后、关键审计等待后重新认证引用与当前权限，才交给 M9 返回完整内存响应，带 no-store／nosniff／attachment；不是先发部分明文再验 tag。下载记录 AUTHORIZATION 放行，不记录新的 DELIVERY、不宣称客户端收全。v2 资源上传摘要不绑定可变 review status，v1 旧证据仍按原规则核对；这不把审核状态变成原文读取授权。

`PrivateFileShare` 与操作表同次迁移建立。当前实现为固定 5 分钟的引用链接，不是 bearer grant：任何读者仍须通过上述原域 ACL，持有链接不扩权。创建按主体／operation UUID 幂等；创建和撤销经认证 v2 审计。撤销须当前有原件访问权的原签发者；记录保留，不物理删分享。读取在解密／审计等待后再次核对过期、撤销和当前原件引用，退役原件也阻断旧链接。URL／过期时间不是网络交付回执或恢复许可。

**HTTP 与装配。** `ds.bootstrap.v2.private_files` 只接受 private_root／project_ref，需已有认证 v2 链；根须为明确的服务私有绝对路径，不得与 MEDIA_ROOT／STATIC_ROOT 重叠。与 export_delivery 同时配置时，两者项目和根须一致。仅普通 `start_application` 安装 HTTP 能力，直接调用辅助 assemble 不开路由；正式缺能力仍 body 前关闭，不回落 FileField。原未绑定基线保留，但不称其满足私有文件门禁。上传使用专属内存 ASGI handler 加原有界 multipart handler；基线单对象 20 MiB、最多 2 个驻留文件，反馈原 10 MiB 业务限额不变。仅引用路由 ASGI 请求体总预算为 64 KiB，即使 capability 关闭或 export operation 非法也不用默认磁盘 spool；并不证明代理缓冲、交换保护或跨请求并发预算。

`POST /api/data-security/exports/resources/{execute|download}/` 只接收 source_ref／permission_ref，复用 B1 的正式来源、风险、目标批准及 ExportFlow；不能传客户端 binding、approved 或成功声明。execute 只称 logically_delivered，download 读取既有认证产物，不重开原件／预占／结算；始终不证明网络收讫。完整路由清单与关闭办法见 operations 的 B2 小节。

**独立执行器。** `ds.executor-preparation.v1` 通过可信配置显式组合文件 key、CryptoPort、同一 M6 私有准备／操作登记及原受签名约束的执行服务。服务原 caller、授权、计划／输入摘要、幂等、fence 和 lease 检查保留。新增 GET preparation 仅观察、空 body POST 正向对账，只认原 caller 和保留意图；其 M6 操作留在 prepared，不冒充 committed 的业务交付。HTTP 能到 prepared 或 repair_required／unknown，但未新增可信 MaskReport、PROTECTION 新链、ProtectedArtifact、成功事件、配额结算、负向清理或分享权限；正式模式旧分享／交付和 PrivateStorage 关闭。该限制是明确的未开放能力，不是“独立执行器完整交付已完成”。

**备份与扫描。** B2 只将私有备份 live-files 投影排除内部 retired 行；DB dump 仍保存退役证据，不能把已授权删除的文件当缺件或据此删除其他文件。B3 恢复开通／轮换不在本增量。离线原文扫描只查登记的合成原样及 UTF-16／JSON 转义／base64 表示，ZIP/gzip 有界内存展开，不执行或提取成员；图片、PDF、嵌套或不支持内容为 unscanned，不当零。源码限定扫描不替代运行清单、500 条语料或 G06，未扫项与已知样例命中都须保留。

### 12.23 B3 隔离恢复、旧源治理与保留密钥（2026-11-08；实现待独立验证）

本节描述新增代码，不将 PG／age／指标的待分发用例写成通过，不覆盖上文历史截点。仅 test/evaluation；没有生产部署、自动销毁密钥或执行器交付扩权。M4 仍只编排端口，M6 只依原 owner／M0，历史报告认证从 B 注入；依赖矩阵未放宽。

- **完整快照**：`PostgresAgeBackup(full_inventory=True)` 显式选择全量模式，原 v1/v2 默认不变。原导出 PG snapshot 同时绑定完整非系统表摘要、实际 snapshot_at、服务／库／私有根身份、既有 registered live 密文和 opaque partial 密文。后者只原样保留，不登记、验为候选或发布。完整 age 认证先于 SQL 恢复；失败目标保持隔离，不抹掉 partial 或原证据。任意旧 FileField 和独立旧审计归档目录不自动收入 private 包。
- **恢复与开通分离**：`RecoveryFlow` 只沿 closed→restoring→restored→verified→opened；每次恢复／核验／开通是显式维护调用。主站 `assemble_recovery` 在待恢复表存在前只构造原 BackupPort／journal，恢复后才装配原 owner。核验／开通都比较恢复回执中的全表／文件清单，开通须原 run_ref、完整 owner 核验、opening_allowed 和实际 RPO≤86400s、RTO≤14400s。RTO 含 close 停服声明至实际读取密钥／恢复／核验／人工确认的全部阶段，不仅是 pg_restore 用时；close 前的目标环境准备不计入，不能声称生产故障开始时间。合成时钟测试不构成指标。
- **只读核验**：PG autocommit 入口拒绝错目标或外层事务，在 REPEATABLE READ, READ ONLY 中复用资源／反馈原 metadata、报告原签名／逻辑回执、实际密文、字段及索引／最小化约束、原认证链与明确选中的库外 checkpoint。project_ref 保留原配置，不拿部署 domain 替换 AAD。保留 preparing／unknown／expired reserved／过期分享，不释放、结算、重授访问或生成锚；报告真实未锚后缀。cleaned 原件只有精确原 operation／result／context／stored 匹配且保留退役身份时可无字节；线上 committed／ACL 门仍拒绝。
- **恢复证明**：`VerifiedRecoveryPoint` 固定受控文件路径和 SHA-256、原部署／代码／环境／域、精确源哈希。journal 回执是 DURABLE、chain_version=None，不是 v2 LEDGER_CONFIRMED。private staging 和旧审计源各用独立 source_ref／hash；一个无关恢复点、布尔值或旧候选证明不能授权本源变更。含未治理旧 FileField／非空旧字段时可完成关闭态演练，但不允许开通。
- **旧私有源**：新增 `PrivateFileOperation.legacy_sources`（0011）保留不可变源→候选关系及后续阶段。资源／反馈原 owner 的 stage 先保留原文件／FileField，只准备密文。真实完整恢复覆盖该关系后才 migrate 或 quarantine；delete 必须另行当前授权、认证事件和精确路径／哈希／无其他 owner 引用核验。当前原上传者与原 ACL 必须同时成立，staff 不覆盖原上传者身份。确认丢失沿原 tombstone 重入，不把“未见回执”当“没有效果”。
- **旧审计源**：保留原 v1 payload／event／时间，不新认证历史时间；实际 age 归档、认证桥接、覆盖桥接的外部锚和源专属恢复证明之后才隔离，隔离之后才显式删除。删除只对两张原表做固定 SQL，保留法务 FK，不能 ORM SET_NULL／级联擦除其他域。隔离／删除元数据不是空 genesis；恢复必须另供原归档及离线 identity 并验内容，不现场造归档或锚。
- **轮换及退役**：显式 `retained_data_keys` 只接受 DATA READ_ONLY，仍用原 resolver 精确相等匹配；旧 envelope 中签过的 ACTIVE 引用不改写，只在读取材料选择时使用明确保留引用。新写只走当前 ACTIVE key。字段重加密复用 FieldRotation；私有根实际重加密限未切换的 B3 staging replacement，保留旧意图／密文并要求新的恢复证明。已签上传、报告和历史回执不就地换 key_ref。认证链保留旧 audit key 验证，新写用新版本；备份切换 recipient 不替换旧包，匹配的旧 identity 离线保留。
- **引用清单边界**：恢复记录分别列实际打开的 data／index／audit／report key 和已验归档 identity；`PostgresAgeBackup.key_inventory` 列本地 full 包所需 key／recipient，非 full 或 orphan 包记 unresolved。在线 sidecar＋密文哈希不是 age 内容认证，也不能推导 recipient 与私钥 identity 的映射。其他归档、其他 checkpoint、保留旧包和未知文件须纳入独立受控清单。所有本地结果明确 `retirement_allowed=False`；不得凭本地零引用销毁密钥。
- **周期与入口**：BackupCycle 只在显式调用时检查完整 daily（24h）和 weekly（7d）；原 D8 七日槽＋四周槽保留语义不变，非 full 包不满足 full 周期，清理仍另行授权。全站 WSGI／ASGI 恢复门在 body／业务 owner 前关闭，含 health／未知路由及 websocket。未绑定恢复门保留原应用对象；无 journal 的从未恢复部署维持旧基线，不是已恢复批准。
- **独立执行器**：v2 配置在 v1 精确字段外增加 retained_data_keys 与 recovery_target_identity；原新写 key／caller／fence 规则不变。独立离线工厂只核验原 prepared/unknown 意图及字节，不加载主站 owner、不发布／交付／负向清理。旧 artifact／candidate_storage_ref 未收入包则不开通；旧 outbox 明确不宣称 v2 认证链。

### 12.24 B4 三业务蜜标、官方工具协议与目录保留（2026-11-09；PG 待分发）

本节更新 §12.10 的实现截点，不改其历史成绩，也不将代码写入／pure 检查记为蜜标门禁通过。复用原 CanarySeed、CanaryTools、CanaryCheckPort、CanaryToolRegistry 和三个出口；没有新增 M0 DTO、识别类别、智能体后台巡检或平行目录机制。

- **真实业务落点**：LegalDocument、ResourceCache、Challenge 各自的 `canary_payload` 保存现有 CryptoService 生成的 CipherEnvelope；目录 CanaryRegistration 只存 seed 元数据、真实业务主键、actor、packet hash、状态和认证事件引用，不存合成原样值。只允许当前创建者的空 draft/other 知识文档、本人空 resourceList 的数据库缓存行、staff 有明确题目权限的 inactive 空题目。题目若已保护 flag，必须用既有 FieldStorage 读取实际 flag，不能把数据库空占位认作空目标。正文、题面、缓存列表均不替换；不发布、建索引或加入普通学习检索。专用字段 editable=False，不进入现有知识库／题目 serializer。
- **引用与当前权限**：B 配置的 target_ref 是 `knowledge/<pk>`、`database/<pk>`、`challenge/<pk>`；pk 为正整数。plant/check/retire 分别要求 `security_policies.add/view/change_canaryregistration`，以及实际目标 model 的 change/view/change 权限，再检查当前 active actor 和上述本人／空目标范围。缓存用户、role 字符串、布尔批准不能代替当前权限。plant 参数仅 seed_id，check 参数仅 `artifact_ref=canary/<seed_id>`；产物从实际业务字段解密并核对目录／认证事件，不接受正文、路径或模型自报授权。
- **持久化与退役**：新 plant 在目标短行锁后重取当前权限，仅更新专用字段；业务密文、目录和唯一 v2 审计同事务提交。seal 在锁外；相同 seed 重入验证已存密文／事件，不重新 seal、换值或重写。提交确认丢失保留 DELIVERY_UNKNOWN，不自动重试。显式 owner.retire 只认证并更新目录状态和退役事件，保留原密文、seed 和历史事件；拒绝复活或普通产物 check，但原 checker 继续检测 retired seed 的历史漏出。目录／事件证据只含 ciphertext/report 摘要和 metadata。
- **官方模型协议**：原 OfficialAI 增加显式 `{messages, tools}` 非流式模式，仅 volcano/deepseek/moonshot/qwen 使用官方 compatible endpoint；wenxin/spark/stream 明确 UNSUPPORTED_SCOPE，不降级。function 名 `canary_plant/check` 适配回原点号 registry。闭合 definition／调用参数、完整批次和调用 ID、tool-result 关联先在协议边界校验；完整响应在丢弃 metadata／解码 arguments 前有界，解码后再保护。发送仍依 confidentiality→ProtectionPort→原 canary→key/transport；厂商正文不能成为授权。
- **显式智能体入口**：`assemble_canary_runtime(config_path=...)` 返回现有 AgentGateway；`run_security_task(user=..., message=..., max_rounds=4)` 由模型按需选择工具、串行执行，1–8 回合，无自动重试或固定 plant/check 序列。只桥接模型协程，Django owner 保持同步栈；不新增后台线程巡检，不写 AgentRun／正文日志，返回原 registry 安全 metadata，不返回模型 prose。普通学习任务和只读工具列表不变。
- **B 与出口**：v2 可选 `canary` 配置仅 seeds/project_ref/provider_ref；须启用认证 v2 审计及 full_inventory 备份。无配置且无目录时保持关闭；已有目录不能通过删掉整段配置或遗漏 planted/retired seed 静默关闭。原 OfficialAI 和安全日志接入同一个工具实例；正式资源导出为真实 source/target owner 构造同机制 checker，factory 返回绑定当前 execution 的 ProtectionContext，并沿原恢复 admission 拒绝关闭态内部调用。表格原 M1 复检／M8 roundtrip 不改。
- **恢复接缝**：只在 B 的原 verify_owners 回调中，在 B3 原 owner 核验成功后追加目录核验；不修改 B3 journal/verifier/flow。目录核验自行建立 PG REPEATABLE READ, READ ONLY，使用既有选定 checkpoint 认证事件、实际业务密文及原 AAD／保留读钥；遗漏 seed、坏密文／hash／event、孤立业务密文都拒绝。结果列 planted/retired 和实际 data_key_refs；B 将引用并入原恢复 key 清单。两个核验是顺序只读快照，不是跨 owner 原子快照。全部结果 traffic_opened=False、key_retirement_allowed=False；不生成锚、补种、修复、开流量或销毁密钥。实际全包恢复、三出口正式 B 回归和完整候选仍须独立证据。

## 13. 第七期文本与原文审批契约（2026-11-10；开发状态）

本节更新早期“RevealPort 未实现／不开通”等实施截点，不覆盖历史测试结果，也不构成候选、真实厂商或生产批准。M0 当前为 49 DTO／23 Protocol，`ds.m0.v1` 保留；PolicyCatalog、KeyResolver、AuditGateway 仍是唯一权威。资料定位与统计未再增加 DTO／Protocol、模型或审计写入口。

### 13.1 RAG 显式装配与文本保护

既有 parser／chunker／embedder／repository Protocol 不换协议；pipeline 不再隐藏创建默认实现，由 B 提供。正文与 metadata 在 parse／clean 后、chunk／embed 前保护；查询 embedding、召回、cache、引用／答案及 HTTP／SSE 的已接薄适配复用 ProtectionPort。业务清洗不是第二套识别器，识别仍仅邮箱／IPv4／银行卡候选。默认未绑定兼容路径和显式保护组合分别登记，不能把 pipeline 可运行当已保护。

M7 原厂商权威复用：方舟 vision 的文本请求显式 dimensions=1024，官方 multimodal 路径返回 data.embedding；不截断／改列、不以本地确定性向量冒充真实语义。图片／OCR 按用户改令延期并拒绝图片外发。旧索引／缓存受控读取不等于已获准历史重建；P7-HISTORY-GOV 只清点限制保持。

### 13.2 RevealFlow、申请与单次消费

M0 保留严格服务器侧 RevealGrant，新增 RevealRequestRecord／RevealRequestRepository 供 M4 管理；仓储从已核服务器列重建 DTO，不解除客户端创建 grant 的禁令。M4 `RevealFlow` 管理 request／decide／revoke／list_requests／reveal_request，读取仍消费原 RevealRepository／RevealSourcePort 与 CryptoPort。M6 负责真实 owner、密文来源、请求持久化与 PG 原子状态，M9 只映射闭合 HTTP 输入；B 显式配置 reveal_requests.enabled 后注入，不由 M9 导入实现或秘密。

- 请求／批准绑定对象 UUID、全局版本、字段引用、目的、申请者与独立批准者；当前对象权限在相应边界重新取得，管理员与 CourseDataGrant 不构成原文批准。
- 新批准由服务器生成，最长 900 秒、只消费一次；同一 PG UOW 内 consume 先于 decrypt，故障不能留下已消费却伪报成功的状态。对象全局版本不替换字段 envelope 原 revision／AAD。
- 批准事件经唯一 sink.read_authenticated 取得，核 event_id、时间与完整批准元数据；raw row、普通 hash、自报成功或非要求的收据都不能替代。读取成功须同 event_id、ds.audit.v2、LEDGER_CONFIRMED。
- 理由先经原 ProtectionService 保护，B／M4 只为该理由调用投影 content/body scope，不扩充披露范围；保护后的理由才保存和返回。
- 只开放 email／evidence／report 对应的既有三组 owner 字段；法律对象沿原 reviewer／实际 task owner。会话、手工事实、密码／密钥不支持，不建立通用解密接口。

### 13.3 只读资料定位与统计

资料定位在已有 M6／M9／B 内新增 Callable：`(ProtectionContext, int, tuple[tuple[RevealField, str], ...], int | None) -> FrozenJSON | ProtectionError`。M9 一次验证闭合 source_id／field／field_ref／可选 course_id；M6 复用当前 actor 和 owner 权限，只 SELECT 身份／版本／保护状态，返回 object_ref／object_version／fields。定位不解密、签发、创建申请／grant／新事件，无权与不存在同拒绝；提交时原版本／权限复核保留，不为此加锁或创建第二套授权。

统计沿 phase4 管理装配显式注入 `(offset) -> FrozenJSON | ProtectionError`，不新增 M4 服务或采集系统。M6 只读 ExportReport 元数据，经原 DjangoReportRepository 重建并由 B 注入的 ReportAuthenticator 按报告创建时刻验证历史 MAC；不 crypto.open、不签发、不回写报告、不读取业务原件。M9 只允许 active admin、闭合单值 offset，页长固定 20，额外一条只用于判断下一页。

Coverage 继续满足 total=eligible+excluded、eligible=processed+failed+unknown+unscanned；原处理 CELL 与复扫 FIELD 分别呈现，不跨单位或任何版本聚合。已知 eligible=0 时 0/0、ratio=null、NO_ELIGIBLE_UNITS；缺分母时 numerator／denominator／ratio／zero_reason 均 null 并单列原因。unknown_records 计报告份数；字段保护、文本 RAG 与出口基线缺完整 Coverage 时仍为未知。历史 MAC 不是交付、当前授权或验收状态。

### 13.4 兼容退出与治理尚未核销

C01–C16 已有逐项只读清点，见 E7 `P7-C-INVENTORY-01.md`；现有职责、默认／局部／真正入口及差异分列。尚无完整的个人认领、批准兼容白名单、移除日期和旧测试等价／批准差异核销，不能把“发现调用方”写成最终退出清单已完成，也不由七期重写前六期责任能力。

七期到期删除、派生副本清理及恢复点之后删除／撤销重放未实现／未验证。原 D8 七日／四周槽、六期恢复门和旧源维护保留，访问 TTL 不等于存储保留期；P7-RETENTION-SCOPE 与 P7-HISTORY-GOV 的待确认／待批范围见 E7 `LIFECYCLE-SCOPE-01.md`。本次没有扩大原恢复契约、跳过清单核验、处置历史数据或开放恢复后新权限。
