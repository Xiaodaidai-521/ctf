# 数据安全运行与责任登记（分期记录）

本文件是操作边界和登记，不是已上线声明。唯一执行报告：`/home/hatch/workspace/data-security-seven-phases/实施报告.md`（R）；证据为同目录 `evidence/phase-01/`（E1）、`phase-02/`（E2）、`phase-03/`（E3）、`phase-04/`（E4）。§1–6原台账保留第1期冻结内容／基线时的路径行号，第2期增量保留当期结论；第3期装配和批准见§7，**第4期已批隔离字段与维护流程见§8**。历史“待批准／未实现”不覆盖后续明确批准，也不当作生产结论。

### 第 2 期执行增量

- 基线为独立亲验通过的 `2970a4cb`。只在同一隔离 worktree/branch 实施 M1–M4、M8/M9旧入口薄映射、B测试注入／拒绝检查和本期文档工具；M0与原测试不改、基线修复保留。
- 执行 SID `a347e5fd-38d7-44cd-82b8-1ad4d5f7210a`；映射 `sessions/phase-02.json`、运行 `logs/phase-02.log`、看护 `logs/watchdog-phase-02.log`；真实JSONL路径见R。本期最初进程由运行时分配SID、命令无SID参数，所以仅首进程允许精确 pid/start_ticks/cwd/argv 匹配；恢复仍强制同SID。控制文件为 `phase-02.control.json`，完成／亲验与下一期隔离规则不变。
- C01/C02：只提取已有通用保密规则、保留业务提示词／flag／字段投影及旧版本映射；真实模型／法律出口仍未迁移，整条不结项。C04：纯候选和旧签名薄委托为本期交付，最终结项由本期独立验收确认，不把它扩成第5期完整表格适配。C05：只提供算法，不改独立执行器fixed/codec。C08/C13：只提供原语，旧Fernet和旧审计链仍不改，真实独立密钥／历史密文／新链工作未完成。
- 2026-11-05二期候选b47e3d92独立验收打回：预绑定476项通过掩盖默认manage.py下3项回归，原完成信号撤销。按要求将OutputSanitizer／fact_redactor的未绑定路径恢复一期行为，表达式单份保存在M9兼容模块，由B显式传入纯委托；已绑定异常不回退。正式B仍没有可用设施装配，不自动绑定。默认476项与显式绑定套件分开留证，不能互相替代；真实出口未升级。核心/B断接时保留这两处基线兼容、M0和已接受基线修复，mainline未绑定关闭不变；不恢复SECRET_KEY派生新用途、不迁移或倒退数据格式、不释放unknown交付额度。
- 第1期原三个业务基线阻断已按单独授权修复并独立验收；Docker B-RESOURCE-01沿原处置继续“环境受限未验”，不能当成功。E2命令与独立验收入口见 acceptance §6；先完成执行证据，再由不同验收角色亲跑同候选，第3期不得先行。

## 1. 隔离与运行规程

- 唯一实施目录 `/home/hatch/workspace/ctf-data-security`，分支 `feat/data-security`；起点 `be67a4e59d4a28ab07f3a55b295081c5831acaaa`。`/home/hatch/workspace/ctf-repo` 只读，初测 HEAD 同起点、分支 `fix/event-id-over-64`、工作区干净。最终按 E1 的实际测量比较，不套用会话附带的过时 git 摘要。
- `.venv`、`.state`、前端 node_modules/dist 均隔离；只在 `.gitignore` 增加 `.state/`。既有 settings、业务／测试源、锁文件不修改；不 stash、不 reset、不 amend 已验收历史。本地提交允许，push／PR 禁止。
- `tools/data_security/isolation.py` 统一记录命令、cwd、时间、退出码、HEAD 和输出哈希。已有标签不可覆盖，返修用新标签。失败不抹去；进程退出不代表门禁通过。
- Python 3.12.3、Node v24.22.1、npm 10.9.4、pnpm 10.29.3；前端锁定安装不换包管理器。只向隔离 Python 添加原测试实际需要的 jsonschema 4.25.1、python-docx 1.2.0，无新增 M0 运行时依赖。版本／许可在 E1 `resource-dependency-manifest.json`，完整已安装包在命令清单配套环境记录中。
- PostgreSQL 16.13＋pgvector 扩展 0.8.1 的二进制／库复制在 `.state/pg-install`，专用 data/socket 位于 `.state/pg-run`；配置 `.state/postgres.json` 记录端口、用途和身份。连接后用 `SHOW data_directory` 复核路径，禁止复用生产／共享数据库。
- 主后端 `ds_phase1_main / test_ds_phase1_main`，执行器 `ds_phase1_export / test_ds_phase1_export`，mainline `ds_phase1_mainline / test_mainline1`。前两者使用隔离 ds_phase1，mainline 使用 mainline1_test，匹配原子进程测试配置。未降低原密码哈希器、鉴权、中间件或 installed apps。
- 宿主 UID 为 root 时用 `unshare --user --map-user=65534 --map-group=65534 --` 运行未经修改的 PostgreSQL，不 patch root 检查、不放宽共享目录权限。已存在的自有集群停止后只验证归属并 pg_ctl start，绝不重新 initdb 或覆盖 data。未知状态／路径／端口冲突直接停止并保留证据。
- 子进程清空继承部署凭据，Django 测试 SECRET_KEY 只在进程环境临时生成且不记录。安装时仅保留既有代理／CA 传输配置，证书校验不关闭；不把这些值写入证据。测试拒绝 worktree 根／backend／cwd 的 `.env`。media/cache/email/export/test temp 定位隔离资源。
- 新测试网络护栏在原 settings 导入前安装，只允许 Python socket 连接专用 PostgreSQL 地址，其他网络／DNS 拒绝；标准库 import 隔离探针另禁一切网络、数据库、环境和媒体访问。**这不是内核防火墙，不能证明任意 C 扩展的全部网络活动被阻断。** 已有用例的模型调用使用原有 mock，不调用真实厂商；未授权 Docker 生命周期不执行。
- 测试结果适配器保留原断言、失败／跳过数量，异常只输出类型、文件／行号／函数，省略可能包含载荷的消息和捕获输出。普通业务 logger 置 NullHandler，assertLogs 可按原测试安装。不会把异常转成成功或新增 skip。专用数据库后续启动抑制错误 SQL 原文入日志；历史隔离日志仍纳入 G06 检查。

## 2. 同会话看护与真实完成条件

执行 SID 固定 `735d37b2-99a9-41f3-a843-fa9e0acca8af`。运行日志 `logs/phase-01.log`；真实会话记录 `/home/hatch/.claude/projects/-home-hatch-workspace-ctf-data-security/735d37b2-99a9-41f3-a843-fa9e0acca8af.jsonl`；映射 `sessions/phase-01.json`；看护日志 `logs/watchdog-phase-01.log`。这些路径在校验器中固定，不允许改成主区脚本或伪造会话记录。

`tools/data_security/watchdog.py --mapping /home/hatch/workspace/data-security-seven-phases/sessions/phase-01.json --interval 30` 必须独立于执行进程存活。映射中的恢复参数沿用初始启动授权，不修改权限、不扩大作用域。运行中的 Python 程序升级须先检查 PID／start_ticks／cwd／argv，停止与重启分成两次操作；确认新心跳后才继续实施。不得用模糊匹配连杀执行外壳，也不得杀其他会话。

检查规则：

1. 每 30 秒同时读运行日志和真实 JSONL，增量有界读取、保留 inode/offset/hash/pending。部分行或未读完的会话记录不能触发恢复。进程状态同时核实 PID、启动时钟、cwd、准确 SID 参数；PID 被复用或映射过时不能新开重复进程。
2. 进程不存在且有效标记不存在＝未完成，正常退出和 JSONL-only 异常同样恢复原 SID。flock 单例覆盖二次检查和 spawn；多个执行进程则阻断。900 秒无进展只报告需检查，不自动强杀。
3. 结构化用户取消／权限拒绝／待授权及真实工具拒绝为粘性阻断。OS EACCES 是任务错误，不等于用户拒绝；API request 快照不是新的控制事件。误分类修复须有记录检查和回归证据，不借此清除真正的拒绝。
4. `phase-01.control.json` 仅接受 operator_state/candidate_sha/reason。每个内容哈希只应用一次，旧 active 文件不能覆盖后来真实拒绝；待授权时保留 SID、使看护存活但不无限恢复或执行被拒动作。
5. 只有 R 中唯一第 1 期段落、唯一准确候选 SHA 块、唯一 active 状态中的严格整行完成标记有效。围栏、引用、缩进、HTML 注释、模板、别期、作废／重复候选不算。还要实际 HEAD=候选、分支正确、工作区干净。
6. 执行者只能在交付、自检、证据和回退全部齐备时写完成标记；看门狗从不代写。独立验收方另写亲验结论和**同一 SHA**。`--next-phase` 同时核对候选／工作区、完成、亲验、无拒绝、会话记录完整；完成而未验收不能开第 2 期。

真实报告格式为第 1 期标题下的候选标题及 active 状态，再记执行／验收事实；本文件不放可被误当真实完成的整行示例。所有标记模拟仅在 `.state/watchdog-fixture-*` 临时测试报告中发生。fixture 工作者两次启动的 SID 必须一致、只恢复一次、并发看护最多一个执行；真实 R 从未被测试写入。看护修复／换接证据在 E1 的 watchdog-handoff、watchdog-recovery-* 和各 fixture 结果。

## 3. C01–C16 迁移责任台账

下表路径相对 worktree；“所有者”是责任角色／原领域，不假称已取得具体人的批准。当前全表状态一致：**仅登记，迁移子任务未执行；部署均未实查**。已有代码可确认局部能力，不能确认线上使用。最终薄门面删除日期由对应期放行时绑定候选 SHA 和调用清零证据，不在第 1 期虚构日期。

| ID | 源路径／调用方与现状 | 目标与负责人 | 迁移子任务／责任期 | 退出条件 |
|---|---|---|---|---|
| C01 | `backend/ai_assistant/security.py:126–187,449–450`；service.py:2701–2801,3095–3337 调 sanitize_output。现有输出 regex 在 provider 返回后，不是模型输入保护 | M1 通用规则、M7 出口；ai_assistant 保留答案／提示词规则；核心＋模型适配角色 | 2：旧测试锁定／规则薄委托；3：最终模型输入、输出及所有调用路径收口 | 原保护顺序和旧签名测试通过；通用规则唯一；无裸输出或输入旁路 |
| C02 | `backend/legal/services/fact_redactor.py:7–42`；exercise_fact_builder.py:104–114、legal/views.py:385–398。notes 当前先截断再替换 | M1 凭据处理，legal 字段／flag 规则，M9 组合；legal＋核心角色 | 2：字段投影与通用替换分离、保留 REDACTION_VERSION 映射；3/4：用例／出口完整接入 | 法律事实测试、版本映射、截断前保护通过；删除重复凭据规则，不删业务规则 |
| C03 | `backend/agents/context/teaching_context.py:155–356`；tutor_request_orchestrator.py:35–95、specialists/executor.py:42–61、ai_assistant/views.py:323–337。TUTOR_CONTEXT_ENABLED 默认 true，按键过滤／正文截断不等于保护 | agents 组装，M0 中立上下文、M4 保护、M7 发送；agents＋适配角色 | 3：白名单投影、正文／历史先保护再限长、单聊／接力实际调用点迁移 | 不搬整个 TeachingContext 入核心；每个出口捕获桩证明无遗漏 |
| C04 | `backend/mainline1/rules.py:23–48,106–268`；operations.py:207–234。Draft／测试流程，无生产批准 | M1 候选，M8 映射，mainline 保留授权／快照；mainline＋核心角色 | 2：纯提取、B 注入 Detect 薄委托；5：完整计划／表格映射 | 原坐标／匹配回归等价；不移除基线批准门，不复制 mainline1 整包 |
| C05 | `tasks/controlled-export-execution/controlled_export/transformations.py:115–277`；views.py:65–85→services.py:178–249。列名作用域、fixed/drop、公式安全和 settings 耦合 | M1 算法、M8 codec/Limits、M0 摘要；执行器＋适配角色 | 2 提供唯一纯动作；5 编解码／显式限额／ActionPlan、原入口薄兼容 | 无第二份 fixed；保留公式保护、原摘要、列顺序和旧测试；不提前宣称真实交付 |
| C06 | `backend/mainline1/planning.py:318–459`、review.py:189–194；执行器 services.py:178–247。Proposed 坐标计划与字符串 v1 列计划不同 | 唯一 M8 SourcePlanAdapter；两原域＋契约维护者 | 5：源 schema／信任／批准／作用域复核、同源快照转换、记录两摘要和适配版本 | golden 等价／拒绝矩阵通过；span/cell 不放大成 column；未批来源不能生产化 |
| C07 | `backend/ai_providers/__init__.py:28–95,204–262`；settings.py:21–58、wenxin.py:19–38、spark.py:27–38,122–132、embedding_service.py:46–67、security.py:391–409、执行器 settings.py:91–112 | 唯一 M5／B，厂商认证留 M7；部署／适配角色 | 3：用途引用、单一清单、读取点改端口、去默认秘密与 dotenv 覆盖；凭据轮换另授权 | 所有读取旁路清零、引用用途和撤销测试通过；不把代码扫描当线上轮换完成 |
| C08 | `backend/ctfsafe/encryption.py:23–81`；未找到非测试业务 encrypt_field/decrypt_field 调用。缺 FERNET_KEY 会回退 SECRET_KEY，非仅 DEBUG；坏显式 key／InvalidToken 不降级明文 | M3/M4/M5；旧格式迁移归 M6；加密＋数据所有者 | 2 原语；3 独立引用与兼容边界；4 经授权核实／迁移必要历史字段 | 原文用途获批、备份恢复前置、显式旧格式只读、无 SECRET_KEY 跨用途；历史密文目前未知 |
| C09 | `backend/ai_assistant/service.py:2701–2801`、ai_providers/__init__.py:273–367；legal compliance_agent.py:65–95、RAG answer:72–134、embedding:85–107、mainline semantic:94–129 | M7 OfficialAIPort；各调用业务＋厂商适配角色 | 3：prepare→保护→认证→send；chat/stream/relay/retry/embed 全迁移 | 每种真实调用模式捕获最终载荷；裸 SDK 调用清零，官方区域和数据条款批准；存在 stream 方法不等于线上使用 |
| C10 | `backend/challenges/coze_injector.py:8–73`；challenges/views.py:366–470。COZE_SDK_ENABLED 默认 false，启用路径把 token 注入浏览器 | M7 服务端请求、M9 业务响应；challenges＋部署角色 | 3：保持浏览器注入关闭、必要用途改服务端、检查 HTML/JS；历史暴露另授权处理 | 返回物无凭据；单换读取来源不算修复；当前真实启用／历史暴露未知 |
| C11 | `backend/export_risk/decisions/service.py:128–158,181–299`；prepare 经 quota 可预占，replay/claim 复核直接 QuotaService；quota=None 可跳过，consume/revoke/invalidate 不结算 | M6 Risk/Quota、M4 ExportFlow；风险／额度原所有者 | 6：复核端口化、单一预占时序、完整锁序／到期／unknown／同绑定回执 | 真实 PostgreSQL 并发证明无双预占、无 finally release，状态不丢；现有基线失败须先处置 |
| C12 | `backend/export_risk/decisions/outbox.py:15–50`；container_audit、legal consent/ledger/compliance、legal_kb ingestion/platform_indexing、rag_ingestion services 等直接 helper 调用。部分 helper 吞失败 | M4 AuditGateway，M6 relay/Sink；audit＋各原域角色 | 3 最小事件入口／递归隔离；6 relay、所有直接 writer 薄委托／私有化 | 同 event_id 无双写／递归；事务入队 durable≠ledger-confirmed；失败关闭按出口实测 |
| C13 | `backend/audit/services.py:36–176`→audit/views.py:93–105；models.py:56–97,163–225、middleware.py:19–57 可接原文 | M3 摘要原语、M4 白名单、M6 链锁、M9 异常；audit＋核心角色 | 2 保留纯摘要语义；3 最小事件；6 新链认证／检查点与旧链归档 | 旧算法可复核、历史不原地重写、独立 checkpoint／截尾测试；旧链不称加密或防管理员篡改 |
| C14 | `backend/users/serializers.py:5–27`、views.py:59–255（178–204 email__icontains）；resources serializers.py:7–28 嵌套 UserSerializer，ResourceListView AllowAny；原密码哈希/write_only 保留 | M9 字段与鉴权，M4 保护／加密，M6 精确索引；users/resources＋数据角色 | 4：服务器上下文、角色矩阵、获批字段密文／索引／CAS 回填／清旧列 | 不以视觉遮挡代替保护；精确盲索引不冒充 substring 搜索；无明文影子列兜底 |
| C15 | `backend/rag_ingestion/views.py:33–57`→services.py:20–94→pipeline.py:31–101；cleaning.py 仅空白规整；retrieval_service 同时处理查询，另 ingestion_service 在 atomic 内 embedding | B 注入原 Protocol、M9/RAG 薄适配、M7 embedding；RAG＋数据角色 | 3 外发封口；7 正文/metadata 切块前保护、查询过门、历史 chunk/vector/cache 重建／删除 | 保留可见性与 ingestion token fencing；本地向量 fallback 非加密；旧历史和部署配置未核实 |
| C16 | `backend/resources/views.py:185–205,245–283`、feedback_center/views.py:66–119,650–719；原鉴权下载／media404 已有，FileField.open 仍读明文。执行器 storage.py:12–86 有 O_EXCL/0600/fsync/rename/hash，但内容明文 | M6 PrivateStore/Backup、M4 文件用例；资源／反馈／执行器＋部署角色 | 3 数据库迁移前备份恢复；6 私有新写／有界旧文件迁移／验真下载／孤儿清理／完整恢复 | 不删除既有私有权限；不能只加密路径；CDN、备份、历史文件实态未知，未发现应用 BackupPort≠运维无备份 |

## 4. D1–D16 决策登记

记录日期 2026-11-04，登记版本 phase1.v1。技术基线是本期授权范围内的实现约束；生产、数据、密钥或策略决策必须另有权威批准记录和适用环境。建议值不自动生效。

| ID | 本期状态／建议及未定处理 | 所有者 | 最晚门禁／后续证据 |
|---|---|---|---|
| D1 | **技术目标冻结**：优先同进程可安装普通库＋端口；不把第二个 Django 工程塞进主进程，不用 sys.path 导入 tasks。独立部署需求未获批，真实导出关闭 | 契约／执行器维护角色，独立部署由部署角色确认 | 1 定目标；6 前完成身份、传输、幂等／回执证据；若改独立则仅 M9 薄 HTTP、M6 保持本地持久化 |
| D2 | 待业务批准；来源／版本／字段／目的／出口最小例外，默认无例外；内部教学展示不是外发许可 | 教学／数据所有者＋独立复核 | 3 启用前；原题 flag/答案规则留业务 |
| D3 | 待引用保管／轮换批准；mask-link、mask-pseudonym、query-index、audit-auth 用途独立；180 天或比赛周期仅建议，暴露立即授权处置 | 密钥／部署角色＋数据所有者 | 3 启用前，4 索引前；双版本截止和退出须有记录；未定不开稳定关联 |
| D4 | 必要原文／保留待批准；非必要不存；必要原文最长 30d、导出 24h 均为建议非承诺 | 各对象数据所有者 | 4 字段／6 文件前；未定不迁移、不新增原文保留 |
| D5 | 邮箱规范化／取消模糊查询待业务确认；精确查询＋独立盲索引，无明文影子 fallback | users 业务／数据所有者 | 4 迁移前；不擅改既有生产查询 |
| D6 | 正式密钥设施、离线恢复保管、环境隔离、撤销缓存均待部署批准；只定义 key_ref，不读取材料 | 部署／密钥保管角色＋独立恢复复核 | 3 装配前、4 迁移前；缺必要版本停止相应用例 |
| D7 | 文件分类／tmpfs／交换及并发待批准；对象 20 MiB 为本期有界契约，不等于真实机器已验证 | 数据＋存储／部署角色 | 6 开工前；未知私有、超限拒绝、不入普通公开 MEDIA |
| D8 | age 备份管道、7 日＋4 周、RPO≤24h／RTO≤4h 待批准实测；本期未装 age／未声称可恢复生产 | 部署／备份保管＋独立恢复角色 | 3 迁移前数据库备份恢复；6 完整文件／配置／密钥引用恢复 |
| D9 | 历史审计／对话／缓存／索引／备份治理待对象级批准；旧链不原地改写，新写安全不外推历史安全 | 数据／audit/RAG 所有者 | 4、6、7 各自迁移前；未定保留“未治理”状态 |
| D10 | 原文审批权限待批准；最长 15 分钟、对象版本／字段／目的绑定、申请与审批分离、原子单次消费；无密码／密钥查看 | 数据所有者＋独立审批角色 | 7 开通前；管理员无自动豁免，未定无新 reveal HTTP |
| D11 | 启用厂商／区域／模型／数据条款／切换名单均未批准；只登记静态默认主机，真实调用 0 | 模型适配／部署＋数据所有者 | 3 各厂商启用前持续核对；仅官方 API、不可任意 base_url、不本地部署模型 |
| D12 | **本轮非必需、未实现、未启用**；第 1 期登记、第 7 期确认取舍。不为识别先外发未知原文；仍不增加排除的五类 | 业务／数据所有者＋契约维护者 | 基础验收后另议；没有语义识别实现任务 |
| D13 | TLS 终止、可信代理、跨机执行器／数据库证书链待真实部署实测；源码默认值不等于链路安全 | 部署角色 | 3 敏感业务前；不明链路不放行，真实联调另授权 |
| D14 | **职责冻结**：本期执行角色维护 M0／三份文档／C 清单，原领域语义由原所有者解释；生产审批／独立验收不由执行者代签 | 后端契约维护＋各原领域角色 | 1 定边界；7 核对薄门面调用清零／删除期限／单一实现 |
| D15 | 同库短 UoW 优先；实际部署是否同库和交付认定待确认。保留旧锁序，unknown 持有、零交付必须有证据 | 风险／配额／审计／交付所有者 | 6 开工前；文件私有候选验真后发布，不宣称分布式事务或网络 exactly-once |
| D16 | **隔离测试基线冻结**：Limits 见 contracts；可见 CPU=4，目标 4 vCPU/8 GiB 不当作已测性能。内存配额未验证、无并发吞吐承诺 | 契约／测试资源角色；生产限额由部署／验收角色 | 1 基线；3、6 压测；7 总验。超限拒绝，不能无界缓冲补缺口 |

## 5. 对象／字段／文件／出口登记

| 对象与原位置 | 原文／秘密风险及当前已有能力 | 后续所有者／出口／未决 |
|---|---|---|
| 用户：users models/serializers/views | 邮箱输出／icontains 依赖明文；密码已哈希，保留原机制，不二次“可解密加密” | users；API／查询；D4/D5 第 4 期 |
| AI 对话／agents 教学上下文 | 正文、历史、metadata、检索上下文可能外发；OutputSanitizer 仅局部输出保护；题目真实答案／系统提示词规则保留 | 各业务＋M7；chat/stream/relay/retry/model/log；D2/D4/D11 第 3/4 期 |
| legal 事实／报告／同意与审计 | 已有字段投影、凭据替换和 ledger helpers，非全出口闭环；任意 detail／异常文本可能含原文 | legal/audit＋M4/M6/M9；API/model/audit/log；D4/D9 |
| 资源／反馈附件与证据 | 已有鉴权下载／可见性及直接 media404 限制；FileField 内容非加密，真实存储／CDN 未核实 | resources/feedback；upload/private-store/download；D7/D9 第 6 期 |
| mainline 资产／解析／计划 | 内部 snapshot、scope、plan/hash 与批准门；根 URL 未公开，非已批准生产出口 | mainline/M8；暂仅内部测试；D1/D14 第 5 期 |
| 独立导出原件／产物／share | 私有文件权限及发布操作存在，但写入明文；evaluation 不分享，已有交付回执≠主 QuotaService 集成 | 执行器/M8/M6/M4；export/download/share；D1/D7/D15 第 5/6 期 |
| 风险／额度／outbox／ledger | 安装 app 不代表暴露公开入口；原 DTO/锁/unknown 保留，outbox 不等入链 | 原域唯一写者；audit/内部授权；D9/D15 第 6 期 |
| RAG document/chunk/vector/query/cache | 正文／metadata 与查询均涉及 embedding；清空白不是脱敏，本地向量不是加密；token fencing／可见性保留 | RAG/legal_kb/M7；embedding/retrieval/API/cache；D9 第 3/7 期 |
| 数据库、对象文件、临时区、备份、恢复材料 | 本期只使用合成专用库／临时文件；生产位置、挂载、保留、交换、备份完整性均未检查 | 部署／数据所有者；D4/D6/D7/D8；真实操作另授权 |

原文用途登记：业务处理必要内存（有界 DTO）、受控执行定位、获批必要存储、限时人工调查／查看、恢复演练。当前只使用合成测试内存／专用资源；生产必要性、字段集合、申请人／审批人、期限、删除／撤销重放均待 D4/D9/D10 按对象批准。禁止为日志、统计、截图、影子比对或模型检测额外保留／外发真实原文。

出口集合固定 model、embedding、log、audit、api、export、rag；新出口启用数为 0。原入口能力与是否已安全必须逐条区分，不能把本期“未接线”说成旧系统“全出口安全”。旧 mainline 和 export_risk/export_quota 未在主根 URL 开放公共业务入口，本期不新增路由。

### 5.1 用途引用登记（无秘密值）

| KeyPurpose／引用族 | 用途与允许消费者 | 本期状态 |
|---|---|---|
| enc-data | 独立数据根用途；M4 CryptoService，M3 只收内存材料 | 仅 KeyReference/CipherEnvelope 形状；无 resolver |
| mask-link / mask-pseudonym / query-index | 关联、假名、精确盲索引分别隔离；不跨环境复用 | 待 D3/D5，稳定相等关系不是匿名化 |
| audit-auth | 新链认证；经内部 CryptoPort 使用，无审计递归 | 第 6 期，旧链没有该保证 |
| provider/<厂商>/<版本> | 仅 M7 受信任认证；业务、浏览器、日志不得取得 | 待 D6/D11；无实际材料读取 |
| framework-signing | 独立 Django 启动签名用途，B 经 M5 加载 | 不派生数据密钥；本期只是隔离随机测试值 |
| export-authority / share-pepper | 授权签发／share 验证的独立用途 | 待对应域批准与迁移，不更改现有秘密 |
| backup-recipient / backup-identity | 在线备份仅公钥，离线恢复私钥独立保管；受控管道／FD，不进 argv 或明文临时文件 | 第 3/6 期，无真实备份／恢复材料操作 |

KeyReference 仅用途／版本／状态（active-write、decrypt-or-verify-only、retired）和受限引用；引用不是秘密也不是解密授权。真实部署清单、轮换日期、保管人、恢复副本未读取／未批准，不填虚构 key_ref 实例。

### 5.2 厂商／区域清单（静态，不是启用名单）

E1 `provider-static-endpoint-inventory.json` 仅从 AST 取 scheme/host，不输出查询串／认证字段。

| 现有厂商／路径 | 静态默认主机／协议 | 区域／条款／当前启用 |
|---|---|---|
| qwen.py／embedding_service.py | https dashscope.aliyuncs.com | 未批准；账号区域／留存条款未核实 |
| volcano／registry／embedding_service.py | https ark.cn-beijing.volces.com | 主机名含 cn-beijing；不据此证明实际账号／路由区域或数据承诺 |
| deepseek.py | https api.deepseek.com | 未核实／未批准 |
| moonshot.py | https api.moonshot.cn | 未核实／未批准 |
| wenxin.py | https aip.baidubce.com | 未核实／未批准 |
| spark.py／registry | wss spark-api.xf-yun.com | 未核实／未批准；仍需保护发送后的最终协议载荷 |
| coze_injector.py | 浏览器 SDK 注入分支，不能作为安全服务端出口 | 默认关闭；若有业务用途，须另选批准官方服务端端点 |

LEGAL_KB_RAG_USE_LLM 原默认 true、legal compliance LLM 原默认 false；MultiAgent 初始 use_real_api=False 可被 refresh 改变。静态开关不等实际部署，也不能用初始值宣称永不外发。重试／切换名单待批准；每次切换重新保护。真实 API 调用、本地模型部署本期均为 0；合成测试捕获／mock 与真实联调严格分开。

## 6. 回退、证据权限与待授权

第 1 期没有新装配、迁移或公开入口。回退是停止使用尚未接入的新包／工具、保持旧业务保护与证据；不回退旧密码哈希／DOMPurify／对象鉴权／提示词规则，不开放裸出口或明文兜底。代码断接演练用子进程 import 阻断新包，运行未改动业务的安全检查和只读路由核对；不移动／删除真实新文件，不 git reset。隔离 mainline 迁移 forward→zero 已单独演练；它不是生产数据回滚，更不是备份恢复。

发生接口变更须在本期改版本／测试后重验；格式／密钥版本／unknown 交付问题留原责任期，不靠回退恢复明文。真实数据未动，故不存在已完成的真实回填／清除／密钥轮换回退。待授权的基线业务修复不在 M0 范围内，保持 G02 和下一期阻断，保存原失败结果；看护进入明确 blocked 等待，不反复尝试越权修复。

E1 目录 0700，证据／会话控制／日志尽量 0600；生成结果仅含元数据、固定原因码、计数和摘要。不复制真实会话全文或合成秘密样本到 R/E1；报告不含机器秘密配置。已存源码的旧历史常量风险只记位置／用途，不复制其值。证据保留至本期独立验收及后续集成确认，清理时点由所有者决定；当前不自动删除证据、集群或历史日志，不承诺未经批准的生产保留期限。

## 7. 第3期：正式适配的隔离运行手册

### 7.1 批准、默认模式与正式模式

起点为二期独立亲验通过的 `65ef487f`。R《第3期前置决策落实记录（2026-11-05，用户批准·隔离验收口径）》落实六项决策：仅本机合成数据、无教学例外、稳定关联／假名／索引关闭、仓库外独立引用、隔离数据库age恢复、官方端点捕获和本机TLS。不是生产密钥设施、真实厂商或生产部署批准。

- 未提供 `DATA_SECURITY_CONFIG`：保留原默认回归语义和Session／旧Token的历史测试路径；仅B绑定默认teacher输入加载器，**不预绑定整个核心**。模型manager为空，旧直接provider、Coze浏览器注入、FRP sidecar配送、旧请求签名、未绑定字段加密均关闭。这个兼容模式不是批准的敏感业务部署模式。
- 正式隔离模式：`DATA_SECURITY_CONFIG` 必须指向显式绝对配置文件。settings通过B从M5读取独立框架密钥；`ctf_backend.apps.SecurityConfig.ready()`正式装配一次。默认认证和challenge显式认证均关闭长期Token，保留Session与CSRF。普通代码不得调用测试绑定作为启动替代。
- 不支持在同一进程从默认模式切换到正式模式；演练使用全新进程、全新合成数据和隔离缓存。没有治理生产历史对话／缓存／Token存量；源码关闭不等于真实吊销。

### 7.2 外部配置、用途与安装

配置schema `ds.bootstrap.v1`，字段闭合：`environment`（仅evaluation）、`key_manifest`、`policy_file`、`policy_binding`、`framework_key`、`data_key`、`audit_key`、`providers`、`backup`。不接受实现模块路径、测试端口或确定性随机源。

KeyReference仍为M0 `schema_version/key_ref/purpose/version/status`。清单schema `ds.key-manifest.v1`，字段 `environment/entries`；每个entry只有 `reference`（完整KeyReference）、`file`（同目录basename）、`identities`（服务身份列表）。应用identity为 `service/security`；离线恢复可用独立身份。**配置／清单仅引用，不含材料。**

1. 由获授权保管者在仓库外安装真实批准的文件；测试fixture只生成并销毁从未激活的合成材料，不能拿它冒充生产设施。清单目录0700、当前服务所有；清单和材料普通文件0600，不允许symlink或仓库内目录。配置／策略不得组写或其他人写，推荐0600。
2. 批准快照源 `docs/data-security/phase3-policy.json` 引用本次隔离批准：`phase3-isolated-20261105.v1`，摘要 `dea5acb0212fcf04760bba8c1c3817ff053a3d193cdbc04c7486cfcc25fdf2be`。安装时复制到仓库外0600批准文件，核验摘要，再绑定其精确版本和hash；不要直接使用可能0660的工作树文件。无latest、无默认仓储回退、无管理页或运行时审批。
3. 框架签名UTF-8至少50字符，DATA和AUDIT各32字节，所有已启用途材料独立；PROVIDER引用族含厂商名。普通厂商材料为单值，Wenxin为AK与SK两段，Spark为APPID/APIKey/APISecret三段（竖线分隔），仅M7消费。数据库不存这些值；框架密钥不用于数据加密。
4. 每次resolve重读清单，精确匹配引用／用途／版本／状态／环境／服务身份；retired和关闭用途拒绝，文件删除／权限失配立即不可用。写用active，旧只读状态不授权新写；撤销测试不等于已轮换真实账号。
5. 周期按本期批准为180天或比赛周期，暴露立即按授权处理。执行者不自行生成生产主密钥、不自行撤销外部账号。批准缺失或错误引用使相关功能停止，不能回退SECRET_KEY、明文或裸provider。

`providers`每项仅 `endpoint_ref/base_url/models/key_ref`；base_url精确匹配M7内置官方地址（§5.2六厂商仍保留）。`models`为批准列表，qwen/volcano才支持embedding。清单未启项保持关闭；测试模型名不代表真实账号可用性／条款批准。标准配置结构可参考 `data_security/tests/phase3_fixtures.py`，**仅供结构复验，禁止作为生产密钥生成器**。

### 7.3 模型、日志与基础审计

业务仅拿ProviderHandle及受控DTO，不拿SDK client/api_key/raw_response。业务最小化与截断前保护 → 中立请求 → M7完整厂商prepare → 既有凭据保密和ProtectionPort → 必需认证 → send。HTTP不继承环境代理、不跟随重定向；Wenxin认证仅官方OAuth及query，Spark签名仅协议query和app_id。每次重试／换厂商重新保护，不重用前厂商受保护请求。

响应上限1MiB，stream先收完有界结果再整体保护，然后切块；无法完整取得／保护时不交付部分原文。CTF答案和内部提示词规则在DTO之后由B注入业务回调，未移入M7。三类Detect不扩展；显式凭据字段、实际认证值和旧规则已命中内容另行保护，不宣称可自动识别任意凭据文本。

embedding配置仅空值选择既有确定性本地开发向量（非模型）；qwen/volcano及旧别名dashscope/ark经受控handle，未知厂商或缺handle直接失败，不静默回本地。教学HTTP／SSE异常返回固定MODEL_CALL_FAILED，不返回原始异常。旧 `mainline1.semantic.LangChainSemanticAdapter` 源码仍保留，但默认backend为空、未接B或启用；它不计为已迁移的正式出口，不能手工接入裸SDK绕过本边界。

正式日志丢弃message/args/exception/extra原文，只留固定原因码、类型和计数；Nginx关闭含URI的access log及原始请求错误文本，应用保留受控原因码。AuditGateway唯一入口，DjangoAuditSink私有writer不回调Gateway。SecurityAuditRecord按event_id去重；durable只代表本地持久化，ledger-confirmed才有旧v1条目字段。旧链仍无密钥哈希链，不称新链认证、checkpoint或防管理员改写。Risk/Quota交付未启用。

同步内容构造器从async业务调用时，M9仅将同步保护／审计移到worker并等待，worker关闭自己打开的Django连接；不打开Django异步不安全开关。ProviderHandle的异步请求也使用同一连接释放边界。

### 7.4 TLS与数据库备份

本机Nginx终止TLS1.2/1.3；HTTP308，Secure Session/CSRF Cookie，HSTS300，不preload／includeSubdomains。Gunicorn绑定127.0.0.1、可信代理仅127.0.0.1/::1；Django不自行信任外部转发头。Compose frontend与backend共用网络命名空间，frontend代理loopback，宿主仅loopback发布80/443。同机隔离PG使用local/disable；跨机不允许不安全sslmode，需verify-full与另行批准拓扑。

启动脚本不再插值环境密码到Python命令或无人值守创建管理员；Compose移除bootstrap账号密码注入。数据库URL只经B读取，Gunicorn访问日志仅状态码与耗时。TLS证据记录当前start.sh摘要及bash语法校验，但不声称执行过完整start.sh或Compose部署。FRP停止清理也只记固定结果码。

备份配置可为null（关闭），或包含 `database/directory/checks/age/pg_dump/pg_restore`；本期B只接受本机无密码隔离DB。目录预建0700；checks为标识与稳定ORDER BY查询的二元组。在线BackupPort只有独立BACKUP_PUBLIC，离线对象另装仅BACKUP_PRIVATE清单，不把私钥放在线清单。

导出在repeatable-read导出快照下运行pg_dump→age，清单／计数／摘要／一致性点在同一密文包中；无明文dump落盘，私钥经FD不进argv。恢复必须先完整验真，再流入空库，核对计数和摘要才出本地durable收据。失败产物不登记成功，不用仅校验密文外层hash代替age验真。成熟工具版本和许可证见E3，下载工具未系统安装。

这是数据库迁移前演练，不覆盖真实字段迁移、完整数据库＋文件恢复、生产保留份数、RPO/RTO或独立导出服务TLS。独立执行器未部署，仍在清单中并仅跑原隔离回归；不能把主后端TLS外推给它。共享Docker生命周期原未验项仍明确保留。

### 7.5 本期C任务与失败处置

| 子任务 | 当前实施／结项边界 |
|---|---|
| C01/C02/C03/C09 | 正式教学／法律／对话／重试／切换／embedding接线与最终send测试；默认旧业务golden保留。最终结项须本期全门禁及独立验收 |
| C07/C10 | 单一M5/B、关闭旧dotenv／浏览器token／固定秘密配送；生产账号存量／吊销未操作 |
| C08 | 独立CryptoPort字段门面与取消Fernet回退；无真实字段写入／迁移，旧格式留第4期授权 |
| C12/C13 | 新事件最小化、唯一Gateway、持久化/旧链分离；新认证链和checkpoint留第6期 |
| C15 | 仅embedding外发封口；历史chunk/vector/cache和完整pipeline留第7期 |
| C16 | age数据库备份及空库恢复；私有文件和完整恢复留第6期 |

出现缺钥、未批策略、审计失败或传输失败，停止相关外发／敏感写入；保留格式、版本和已存在密文，不退回默认兼容模式维持正式服务。回退演练只删除测试拥有的合成key/policy引用，验证发送为0、字段失败关闭和既有认证／密码哈希保留。不git reset、不移动真实数据、不恢复浏览器token／框架派生，不释放unknown额度。证据E3目录0700／文件0600，失败历史保留；本段保留第3期执行时的边界，后续第4期开工及批准以R和下节为准。

## 8. 第4期：字段、索引与维护（仅隔离合成范围）

2026-11-05 20:06 CST的D4/D5/D9批准及20:45 metadata补批已全部落实为实施输入，不再是前置待授权。仅隔离合成范围、非生产批准；不推送、不建PR、不接生产，第5期不开工。候选、完成状态及实际通过/失败/未验以R及E4为准；冻结待验候选不等于全部门禁通过。

### 8.1 已选所有者与未治理对象

必要原文加密仅15字段：CTFUser.email；AIMessage.content/metadata；UserMemory.memory_value/metadata；LegalAnalysisTask.input_text；LegalReport.content；OnboardingInterview.answers；StudentProfileReport.raw_interview；Challenge.flag；ChallengeSolution.content；TheoryQuestion.correct_answer；ExamAnswer.user_answer；Submission.flag；LegalFactSnapshot.manual_notes。密码沿Django不可逆哈希，不进入envelope。

脱敏保存沿各owner的`redacted_fields`：AgentRun过程/结果/错误；获批legal标题、摘要、metadata、evidence摘录、compliance输入输出、snapshot自动事实与warnings；画像衍生自由文本、report_data/summary、interview分析；AuditEvent.detail；ChallengeSolution.hint_map。数字评分保持数字，AuditEvent.ip_address按批准保留，evidence_refs保持结构。不因临近字段存在而扩大原文保留。

AIAuditLog新写与历史回填沿第3期最小化：provider/model为withheld，正文/错误/模式清空，耗时与token估计归零、IP不保留；用户/题目关系、成功状态与时间保留，不增加可恢复正文。该owner的`minimized_fields`由所有者声明，M6执行同一写入和回填规则、PG约束禁止sealed行写回旧内容。会话列表的实际标题来源是Challenge.title，输出经现有保护入口，不新增对话标题列，也不擅自改变题目标题的原存储决定。

对话类必要原文保留在本隔离环境登记为最长30天口径；只作元数据登记，不是生产保留承诺，不借此提前实施第7期全域删除/恢复后重放。

ParsedArtifact.payload留第5期；旧AuditLedgerEntry.payload/SecurityAuditRecord.event不原地重写，留第6期；历史RAG chunk/vector/cache留第7期。新的解答索引副本使用保护后的源值，不据此称旧知识包/历史索引全部已清理。任何未被本期实际迁移和核对的对象继续标记未治理。

### 8.2 装配、策略和请求范围

`ds.bootstrap.v2`增加闭合`policy_repository={kind:file|orm,writable:bool}`，ORM时policy_file为null。文件和ORM共用版本/CAS规则；失败不回落另一库。M4 PolicyCatalog独占草稿/批准/撤销；保存新内容必须新版本/新摘要，业务请求仍固定binding。v1及无正式配置的默认测试行为保留，不能用测试预绑定代替启动。

可选`field_storage`含`legacy_reads`、1–2个`index_keys`、0–2个只读`read_keys`、`recovery_record={path,sha256}`；双索引另需aware ISO `index_deadline`，单索引不带截止。enc-data/query-index/framework/audit/provider材料分开，经唯一M5。封装AAD绑定环境、owner、UUID、字段和revision，不自动解密整个模型。普通serializer即使缺request也遮蔽，formal过渡期的legacy行同样遮蔽；admin不展示未迁移的答案对象。

邮箱去外围空白、只小写域名、本地部分大小写保留；只精确HMAC候选，先按CourseDataGrant限定候选主体，再显式解密比较。学生仅本人；教师/管理员只有实际未过期课程授权才看其他主体；is_staff、课程负责人标志和自发课程进度不推导授权。管理员统计与列表使用相同范围。规范化重复邮箱登记冲突，禁止自动合并账号。CourseDataGrant目前是受控ORM配置，不宣称存在授权管理UI。

`/api/data-security/policies/`和`preview/`仅提供管理员策略元数据、key_ref元数据和四种服务端固定合成预览；任意正文、客户端授权上下文拒绝。无原文查看、完整导出、密钥取回或草稿/批准管理HTTP。页面没有自由正文输入/持久化正文。构建通过不替代浏览器实际交互。

### 8.3 备份前提、回填、停止旧读

schema迁移仅增加安全列、分阶段UUID和旧列约束，不在schema迁移里加密历史值。新写使用envelope并清空旧值；**现存legacy行普通save拒绝转换**，只能经备份门禁的离线维护入口转换，不能仅凭第3期能力演练记录清历史数据。显式legacy-v0且legacy_reads开启才允许过渡业务读；未知state/损坏envelope/缺钥不回落旧列。

1. 暂停相应历史敏感写入，用B组装的FieldBackfill.checks对22个已选owner生成有序投影；列由PostgreSQL转text，避免Django与独立备份连接的JSON typecaster差异。通过既有PostgresAgeBackup在线age备份，并使用另一个只有离线私钥的M5身份恢复到空隔离库。保存真实durable恢复记录；在线服务不得持有恢复私钥。
2. `prepare`必须接收真实restore记录，并与当前所有者投影的计数/摘要完全一致。扫描legacy字段的Fernet格式候选；发现候选即停，不猜格式、不生成假迁移。只记录字段计数，零候选结论必须限于真实扫过的数据库和字段。
3. 仓库和E4外0700目录放0600 checkpoint；内容只有backup/event引用、owner、PK、revision、源摘要、固定状态/原因，不放原文。`backfill`逐行锁定和CAS，失败清单保留；已成功行在中断重入时验真但不重新加密。恢复失败项须显式retry，不能忽略失败后启用。
4. 应迁移=成功+失败+未处理；失败/未处理都为0后，将配置legacy_reads关闭并切单索引。`finish`验真全部已选对象、旧列空值、索引与重复邮箱冲突；通过后在22表加sealed-only约束，旧程序/原始SQL不得再写legacy状态。旧文本/JSON列保留为空的schema兼容槽，不保留邮箱明文影子或模糊索引；是否删除物理列与数据清零严格区分。
5. 冻结写入后再切换应用到已验证配置；不要用默认无绑定程序服务密文。备份内旧原文残留仍是加密备份，另记演练窗口与销毁结果；不承诺未经批准的生产保留/RPO/RTO。

维护CLI为`tools.data_security.field_maintenance`，仅接受既有专用集群中`phase4_fields_src_<12hex>`或`phase4_fields_dst_<12hex>`数据库，所有动作只经B工厂，不依赖HTTP。参数为`operation --config <绝对配置> --database <隔离库>`；prepare另需`--checkpoint/--recovery`，backfill/finish需checkpoint，回填/轮换可设`--limit`。动作inventory/prepare/backfill/finish/rotate/rotation-finish；不会自动创建或覆盖数据库，退出/失败输出仅元数据和固定原因。

### 8.4 根密钥和索引轮换／回退

由受控操作安装新enc-data版本与独立query-index版本，旧enc-data改只读并在read_keys显式列出；B缺新钥则拒绝启动。双索引配置有截止，超过截止相关邮箱查询/写入/回填停止，不静默保留旧索引。FieldRotation逐行锁定/CAS，使用已认证原文重封装，不重放Submission判题/计分。以实际envelope/index状态重入，坏密文停且不覆盖。

重加密完成后切单新索引，再运行维护清空email_index_previous；核对无旧envelope后移除read_keys和旧在线manifest条目/文件，执行rotation-finish。finish验证活跃封装/索引，但不会擅自删除密钥文件；离线恢复保管另由获授权角色负责。mask-link/mask-pseudonym仍关闭，不形成或记录新旧原文映射。

回退先停维护和敏感写入，保留密文、revision、checkpoint及失败清单；只退到仍批准的策略与理解sealed-v1的兼容程序。各owner的逆schema保护拒绝丢掉已有密文列；禁止把已迁数据还原成长期开明文双写。不回退第3期P0模型/日志入口、密码哈希或对象鉴权。当前浏览器环境限制等未验项须如实保留，不能凭构建/单测给整期完成信号。

第2期`phase2_rollback`的“屏蔽B再启动旧程序”仅适用于未装配阶段；第3期起正式settings必须导入B，因此本期该额外探针在启动时退出1是断接被拒绝，不是安全恢复方案。原探针、断言与失败证据保留，不删B或设明文fallback使其变绿。当前G07使用正式`phase3_rollback`失败关闭与第4期sealed配置恢复/逆schema拒绝证据，适用阶段和结果分别见acceptance §8.1。

备份验证工具生成的新raw回执同时记录`log`和准确输出字节的`log_sha256`，成功与失败退出码均原样保存；第4期只对回执写出作隔离单元验证，不为此重跑已过的真实备份16项。旧缺hash回执不回填改写，追加关联观察也不能冒充其产生时已绑定哈希。

## 9. 第5期：表格安装、限额、拒绝与停止

### 安装和显式资源边界

在隔离worktree根构建`python -m pip wheel --no-deps .`；将该wheel与执行支线原requirements一起安装。不把tasks路径塞进sys.path，不在同一Django进程注册两个服务。`phase5_package_verify --label <新标签>`实际构建普通wheel、建空venv、仅装运行依赖，再用`-I`运行无Django/无网络独立验证。运行依赖固定cryptography44.0.0、openpyxl3.1.5、defusedxml0.7.1、python-magic0.4.27；系统需libmagic。后端维护者负责这组解析器及libmagic的安全更新和golden复验。python-magic/defusedxml分别为MIT/PSF许可，openpyxl为MIT；它们不是新的服务。

- M8不读取Django settings或环境。执行支线service边界把原三项CONTROLLED_EXPORT_MAX_*配置构造成M0 Limits后显式传入；直接兼容函数默认使用已冻结BASELINE_LIMITS，不继承隐式Django配置。
- 资源上限沿limits-2026-11-04.v1：原对象20MiB、文本65536码点、16 sheets、100000源行（含表头）、512列、100000 cells、1000 ZIP成员、100MiB展开体积。可以收紧，不能提高。旧执行器较松的成员/展开限制不再沿用。
- ZIP逐成员压缩比上限200:1，先核成员总量/展开总量/路径/重复名/加密标志，再用defusedxml禁止DTD/实体/外部资源，检查真实行列坐标与完整网格预算。openpyxl仅read_only读取，不信任dimension提示；共享字符串数量也受cells上限。输出Excel字符串另受32767字符限制，拒绝而不让openpyxl静默截断。
- 实际类型先经python-magic判断，再验证UTF-8 CSV或OOXML结构；扩展名/声明MIME不能将PDF、普通ZIP等伪装成表格。空/畸形/超限/隐藏/合并/公式/链接/批注/嵌入/复杂渠道拒绝，不能跳过后称全覆盖。仅从源文本重建输出，不复制未知工作簿部件。

### 拒绝和恢复

M0入口返回ProtectionError固定代码及非原文trace；旧门面映射到原ContractError/UnsupportedContent。不能转成成功空表、忽略未知sheet/列、按重复展示名猜列或悄悄扩大范围。CSV危险表头转义发生碰撞时停止；算法需要整格而源仅批准字符范围时，交回M4/M2重新解析并重新批准，而不是M8自己升级。

ParsedArtifact新发布仅接受`ds.parsed-artifact.v1`治理路径。M0 JSON上限可能比原ParseResult可解析体积更小，发布拒绝时保留任务失败原因，不落回asdict(result)。不原地改旧raw记录、不读旧raw作为新受控快照；历史记录如需重建须走owner授权的原解析任务。内部表格快照仍含受控原文，不写普通日志、错误或公开证据。

停止新M8使用即可独立回退本期入口；保留已治理私有格式及原源版本，不重写成旧raw payload、不恢复不安全列计划、不创建公开下载。`phase5_rollback`禁止新M8模块导入后运行既有正式保护失败关闭探针，证明三期模型/日志/字段门与框架认证不因停表格而失效；四期sealed格式恢复及逆schema拒绝继续在累计套件中验证。第2期断接B探针仍仅保留历史诊断，不作当前应成功的回退。

本期未生成正式交付、未结算配额、未迁移媒体，unknown交付和密钥版本没有可自动回滚状态；这些能力保持关闭。验收口径应为「适配已验收，交付尚未开放」，其中“已验收”须等待独立验收写入R，不由实现者提前宣告。第6期仍需独立亲验通过后的新授权。
