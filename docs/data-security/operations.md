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

embedding配置仅空值选择既有确定性本地开发向量（非模型）；qwen/volcano及旧别名dashscope/ark经受控handle，未知厂商或缺handle直接失败，不静默回本地。教学HTTP／SSE异常返回固定MODEL_CALL_FAILED，不返回原始异常。旧 `mainline1.semantic.LangChainSemanticAdapter` 的裸SDK实现已移除，仅保留构造即报 `SEMANTIC_BACKEND_DISABLED` 的兼容名称；默认backend为空、未接B或启用。该拒绝入口不计为已迁移的正式出口，未来启用仍须批准并接M7。

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

## 10. 第6期：短事务、对账与恢复前提（实施中）

用户于2026-11-06批准六期开工；生产来源／契约未获批准，交付仍未开放。测试仅使用专用隔离PostgreSQL合成数据。`DjangoQuotaPort(environment=..., window_key=..., limit=..., ttl_seconds=...)`显式注入配置，不读取HTTP或环境变量；M6 `active_until`仅供风险检查使用。RiskPort已实现请求范围适配、消费注入的active_until；ExportFlow及B正式装配尚未完成，不能把局部测试接线当生产启用。

- 准备／大文件／外部调用不持交付事务锁。ExportFlow.commit负责提交段：先锁报告、再风险决策和授权、额度绑定与原域锁、私有对象和审计；锁等待后重新取时，不以早先MAC替代当前期限。RiskPort.consume须处于外层UoW，内部复核当前授权及hold后消费原授权；不重新claim或写额度。UoW中任何ProtectionError都停止并保持未commit，commit标记后异常也必须回滚。
- 风险`decide`在预占前调用原域资格检查，锁后取当前时间并检查最新授权／审批；不创建hold或执行授权。拒绝决策可留存审计，但不得继续预占。后续issue与consume仍须重新检查，不能把准入引用当通行证。
- 风险共享契约入口为`data_security.tests.test_phase6_risk_contract`与`export_risk.tests.test_phase6_contract`，原样继承19项。后者使用普通manage.py和专用PG、TransactionTestCase及真实DjangoUnitOfWork，不能用TestCase隐含外层事务掩盖autocommit拒绝。两侧分别使用有状态内存额度／正式额度端口，不设置第二个reserve；PG仍由原风险／额度writer写表。测试内存work只标记作用域，不可用于B／真实事务或恢复；当前许可和研判为显式合成owner，不是业务授权签发或生产批准。
- 未知交付保持unknown和全额额度，保存回执、候选和幂等绑定。不能在finally、超时处理、进程恢复或清理任务中无条件release；不能因文件ready／HTTP开始发送宣称已收全。
- 额度共享契约测试分别运行`data_security.tests.test_phase6_quota_contract`（有状态内存实现及提交段消费）与`export_quota.test_phase6_contract`（普通manage.py、专用PG）。两者继承同一案例，不按实现分支放宽预期；内存实现只在tests内，不用于B／实际交付、并发或UoW回滚，不替代原PG故障／锁测试。运行时使用既有隔离环境和唯一证据label，不能改默认／bound／pure入口来预绑定。
- ReportAuthenticator已由内部TableReportExecutor在实际转换／完整输出复检／私有候选验真后调用，尚未接入真实owner交付；不得开放客户端报告签名入口，或将客户端报告中的hash当verify的期望值。后续Flow必须从owner记录取计划／完整执行／对象绑定和实际输入／输出／密文摘要，验证ReportProof，再做当前风险授权／额度复核；MAC不能替代复检实际执行。签发仍须active的audit-auth密钥；验证可由owner显式注入同版本read-only引用，经verify_authentication只返回验证结果，不取得新MAC。保留原签发proof字节，resolver收到的是当前受限状态。不会自动找旧key、续期或批准真实轮换／恢复。
- 表格prepare没有客户端报告入口。输出复检包括实际cells与保留的XLSX标题，且要求规范roundtrip字节相等；原五期局部golden不自动成为完整可交付文件。当前严格拒绝任何剩余三类候选，keyed动作未装配；未获owner批准时不得自行补动作。认证失败可留下verified但未发布密文，应保留给后续受管清理／恢复，不能凭猜测state下载。
- ReportRepository保存不可变准备证据及独立的可空逻辑交付回执，重试先由owner完整binding加载旧记录，不重新生成随机密文后覆盖原报告。记录默认禁止序列化，不把低熵输入摘要写普通日志；库内摘要不是MAC，加载后仍须认证及当前权限复核。过期记录保留供恢复，DB错误不可当不存在；短UoW中put成功也不代表外层已提交。报告外键阻止常规删除其引用对象，但文件系统清理仍须受管，不手工删除文件。已有回执只能查历史逻辑状态，不新授予下载权限。内部execute已串联reserve／prepare及unknown分流，正式owner／B及内部release／reconcile的业务恢复入口尚未接线；内部恢复审计增量22项PG已通过，不据此开放下载。新提交段只发带实际报告／密文摘要的v2事件，拒绝旧v1／仅outbox回执；v2适配可在隔离环境显式注入，B与真实owner尚未接线，不能用测试替身启用生产交付。
- 0006增加准备所有权和终止状态：begin只让新创建者获得准备权，短UoW实际提交后才能继续；不能把返回false当再次执行许可。abort与put／交付共用报告行锁，已成功返回原回执，缺行或读取错误不视为零交付；终止后禁止迟到put和交付，保留已有文件与报告。仓储本身不释放或对账额度，原31项准备隔离PG测试已分轮聚合通过；Flow已有内部execute及释放／对账编排，正式owner闭环尚待接线。回退读取器须认识新nullable准备行与aborted状态，不能直接回退0006丢失终止约束。
- 对账以可信确切交付证明驱动；同操作、数量、证据引用返回原回执。内部ExportFlow.release／reconcile已以报告锁内abort作为零逻辑交付证明：缺行／坏回执拒绝；当前恢复权限供应器必须显式配置，并在锁等待后返回绑定本execution／reservation的AUDIT／SECURITY_AUDIT ProtectionContext；布尔值不再够用，须提供当前actor和恢复authorization_ref，不能拿旧导出许可代替。已有成功返回旧回执且不重复额度操作；未交付才在同一UoW终止并释放reserved或对unknown按零结算。固定证据引用由Flow生成，不接客户端数量或字符串。任一错误不提交，提交确认丢失返回DELIVERY_UNKNOWN，保留候选与账务供同操作重试。该内部增量6项PG已通过，包含真实提交后确认丢失和并发对账；新的恢复身份／审计增量22项PG已通过，正式恢复入口仍未接线，不能据此开放交付。停止新交付不删除QuotaExecution或原额度记录，不能通过逆迁移抹掉回执获得“重新执行”机会。
- 显式恢复权限适配已增加RecoveryPermission（security_policies.0007）和DjangoRecoveryAuthorization。签发／认证入口尚未提供，测试仅创建合成许可；不得把模型存在理解为任何角色获权。可信调用方须提供已认证主体和明确引用，短UoW锁序为报告→权限→额度→审计；权限缺失、主体／完整binding不符、操作未授予、撤销或到期都拒绝，DB不可用返回DELIVERY_UNKNOWN，不回退旧导出许可。当前报告锁等待后到期／撤销的两个真实PG场景通过；13项前组只保留逐项ok记录，runner退出未确认，不写整组成功。恢复许可元数据和历史回执须随完整一致性点备份，不能逆迁移删许可来跳过权限检查；正式B／业务恢复入口仍关闭。
- 内部execute须由可信owner显式提供request、对象上下文、loader和executor，默认未配置时拒绝。风险准入通过后短UoW内begin／单次reserve，正常提交后才issue／claim并在锁外加载原文、转换和加密；不在quota锁内反向领取风险锁。只有begin新建者继续，pending竞争者不重复预占或abort赢家。已知准备失败仅经当前恢复权限走release；UNKNOWN先隔离未来发布，再尝试登记unknown并保留全额额度，不把未知当零。若真实提交已成功却确认丢失，保留原交付，重试只读历史回执。当前36项单测及真实PG execute8＋受影响commit5项共13项通过，额外执行故障／完整binding冲突6项也通过；并不代表HTTP／正式owner已接线。
- 恢复关键事件现与abort／quota同库提交，独立QuotaRecoveryEvent由唯一Gateway／Sink进入ds.audit.v2；旧v1、仅outbox或缺v2材料不能满足。终止审计失败不释放；unknown登记审计失败时保留原hold，调用方仍UNKNOWN，不伪称已登记。自动unknown事件沿用本次execute已验证的准备owner身份，显式release／reconcile事件用当前恢复操作者身份。重试记录新的操作者观察，嵌套原QuotaReceipt及其observed_at不变，不将审计条数当结算次数。新增纯组90项及恢复／受影响执行路径22项真实PG全部通过，业务恢复供应器／B仍关闭。
- 0002_quota_execution新增M6绑定／回执表，0003_private_object新增密文身份／候选状态表，0004_export_report新增不可变报告记录及PROTECT私有对象引用，0005_delivery_receipt新增独立逻辑回执字段；均已在隔离测试建库应用，0005后schema drift无变化（delivery-receipt-drift-01）。不得通过逆迁移删除回执来获得重试机会。私有文件迁移前仍必须先建立数据库＋私有文件＋恢复清单一致性恢复点；现有数据库单独备份不能替代。不对生产运行迁移。
- PrivateStore必须显式装配owner受控0700私有根与CryptoPort；拒绝生产装配，不读取公开MEDIA配置。文件先持久化再登记DB，不承诺跨资源原子；DB失败／回滚留下的密文孤儿不可下载。清理与恢复接线未完成前保留孤儿，不任意删除回执或已引用文件。
- 新上传解析边界`PrivateUploadBoundary`必须由B显式注入Limits并置于所有POST／FILES消费者之前，view在返回前同步校验／加密消费上传；当前尚未在B或业务路由安装。每对象按实际字节限长、请求内驻留对象按原max_inflight_objects限制，不能改成请求总量20 MiB，也不能据此宣称跨请求限流已完成。失败不回退普通磁盘处理器，finally关闭本请求内存buffer；不返回被关闭的上传流作为下载。原资源／封面格式校验保留。ASGI及网关可能早于中间件缓冲请求体，Django自身ASGIHandler.read_body仍用SpooledTemporaryFile，须另行覆盖，不能仅部署此handler就宣称原文零落盘；交换保护窄项仍未验。
- 新资源owner可由B的assemble_resource_uploads显式构造，必须配合前述请求边界和服务器serializer context注入；此辅助函数未被start_application或默认路由启用，不是上线开关。原件／封面经原格式校验后只写入私有verified密文，Resource只存内部引用、实际长度和pending状态；上传主体从数据库复核。context显式为None时拒绝，不回退FileField；未注入时保留旧unbound基线，不能将旧路径称为私有上传。新资源原file／cover字段为空，旧审核approved也不能开放下载。封面或Resource入库失败保留不可下载密文候选。B现注入原唯一Gateway及明确binding／clock／data key reference；文件准备后短atomic内保存资源和原件／可选封面各自的PROTECTION新链事件。任一v1／仅outbox／坏回执或审计错误整体回滚资源及所有本次事件，密文保留；提交确认丢失保留已提交资源／事件并返回UNKNOWN，不自动重试／删除／publish。清理、unknown对账与恢复接线仍待，不以失败后删除密文或假装跨资源事务补偿。resources.0004只增元数据字段，已在隔离PG应用且drift无变化，不迁移旧媒体；回退不得逆迁移抹掉私有引用或恢复明文直链。
- 资源原件内部读取必须另向`assemble_resource_uploads`显式传`source_reads=True`；bool参数和v2认证链在B准入，默认不注入。只在autocommit且无外层事务时调用`read_original(user=..., resource_id=...)`，当前上传者／is_staff及全部认证引用复核完成后才打开原件；封面仅核引用、不读原文。M6只读verified，文件权限／长度／SHA及完整AES-GCM／Limits通过后才返回内部BoundedPayload。不要绕过owner直接把StoredObject当访问许可，不要将该返回值接HTTP或当作源计划／请求批准。失败保留原密文与状态，不自动重传、修复、发布或删除；停止该能力只需保持source_reads=False，不作数据／schema回退。原PrivateStore.read仍只接受published且只返回密文，正式入口拒绝门和旧FileField行为不变。没有新增迁移或全局配置，当前还不是完整导出来源供应器、下载或恢复开通。
- 资源原件至交付的合成集成仅在`resources.test_phase6_source_delivery`中装配：原TXT上传仍为BINARY，测试loader明确声明CSV解释，资产映射、冻结请求、源批准和风险授权都是夹具；不是新的格式支持或正式来源供应器。真实目标审批不能代替当前原件访问权或认证PROTECTION，原件读取失败时不执行转换／发布。本例没有配置恢复授权，已知读取失败仍保留reserved／preparing／claiming；打开原件后撤销目标审批则保留prepared及verified产物、拒绝最终提交，也不自动release。不要把这些reserved负例写成unknown。成功后的B与仓储重装只验证历史逻辑回执重放，不重新读取原件、预占或发布，不等于进程崩溃恢复或新的下载许可；正式HTTP拒绝门保持。
- B1补齐内部已交付产物读取的风险owner／Django／Memory实现。`recheck_delivered`核原decision／consumed授权／完整签发binding及当前授权，沿decision→authorization锁序但不修改业务状态，不读active hold或重新研判／领取；`read_committed`只观察原已结算效果，不是新下载许可。完整文件open在交付锁外，额度／审计等待后再次核原较短期限和当前授权，失败不返回产物、放行尝试事件随UoW回滚。只有放行尝试的AUTHORIZATION，不宣称拒绝尝试、HTTP发送或网络结果已留痕。默认Crypto／事件读取仍未向正式下载入口注入，不自动release／重传／修复原交付；历史缺完整binding签发摘要不能自动补写成可下载。相关纯组61项及额度PG26项已通过，真实读取／风险组合结果见acceptance，不计整期完成。
- 新反馈owner由B的assemble_feedback_uploads显式构造，只能用于合成隔离配置及有界内存上传。原10 MiB业务上限、扩展名、student／submitter工单归属和教师visibility规则保留，当前角色、active与工单从数据库复核。feedback_center.0003新增内部引用，file不写原文；失败密文保留，私有下载明确关闭。反馈owner现将附件与新链PROTECTION事件放在加密／文件处理之后的同库短事务，使用原唯一Gateway；需要明确配置ds.audit.v2，旧链／仅outbox／坏回执不放行。审计拒绝或入链后事务失败回滚附件和事件，不清掉事务前密文；提交确认丢失保留实际已提交的附件／新链，返回DELIVERY_UNKNOWN，不自动重试或删除。原业务访问日志不替代关键审计回执，上传保护成功不等于发布或客户端收全。B另注入同一Sink的认证读取；owner的authenticated_reference先复核当前用户／工单／visibility，后比对认证PROTECTION事件与全部当前上传metadata、原Context和密文摘要，再返回当前访问者上下文及内部StoredObject。此方法不打开文件、解密、发布、重签或提供下载URL；metadata／归属绑定不符、缺证据或旧FileField均拒绝，不用裸JSON回退。读取只是当时权限及引用核对，不代替交付时重新授权、文件验真或unknown提交对账；原事务内读取仍不能证明持久提交。旧附件不迁移，恢复、清理和unknown对账仍待；回退不能删除新引用或恢复私有文件明文直链。
- 未开通的资源及反馈附件上传已在正式配置启动时关闭真实入口：B把拒绝middleware放在首位，WSGI在任何请求体消费者前返回空503／no-store；根ASGI wrapper在调用Django handler或receive前拒绝，含挂载前缀及尾斜线变体，不再让该正式入口先落默认spool。当前不是可用上传功能，不绕过该门直接启用候选owner；完整生命周期、关键审计、恢复及资源门禁达成后再接线。无DATA_SECURITY_CONFIG保留原unbound应用，其他路径不改。反向代理／ASGI服务器前置缓冲不在此应用探针的证明范围，不能将拒绝入口算作上传性能或全清单G06通过。
- 私有存储共享契约入口为`data_security.tests.test_phase6_private_contract`和`resources.test_phase6_private_contract`；后者使用普通manage.py、专用PG及测试拥有的0700临时根。两者继承相同案例，故障只操作本次合成密文／记录，不接现有业务私有根。内存实现位于tests，不用于B／业务交付，不替代真实文件权限、fsync、锁、事务回滚、20 MiB完整链或G06扫描证据。
- 资源上传容量观测使用原显式测试组合，不绕过正式入口拒绝门上线。`resource-upload-capacity-observations-01.json`只记录一次20 MiB上传：计时含multipart构造、解析、原业务校验、owner、加解密验真、私有文件及新链提交，不含输入生成、上传后认证引用读取和文件扫描；tracemalloc自身开销计入。Python分配峰值约209.211 MiB；Linux ru_maxrss为测试runner整个生命周期高水位，前158.496／后395.031 MiB，不是该操作独占峰值或PG／子进程树RSS，不能以二者差额冒充操作RSS。单次约1.606秒／12.457 MiB/s不代表生产吞吐；没有新增资源合格阈值、并发限流或调整Limits。20 MiB＋1在prepare前拒绝并关闭活动buffer；本次正常关闭不证明崩溃清理、交换保护或内存绝对清零。私有密文／普通MEDIA局部检查不代替G06全清单扫描。
- `resource-upload-crash-postgres-01`以三个测试自有worker验证20 MiB上传崩溃窗口，fork前关闭父进程PG连接，worker仅向自身发送SIGKILL，父进程join／回收，不杀服务或外部会话。登记前留下未登记密文；验真后资源创建前留下verified记录；资源与保护事件提交后留下可按已知业务ID观察的原记录，均不开放read。重装B、完整认证和两次正向观察不改／删密文，不把unknown当零。子进程正常finally没有执行，父fixture在断言结束后的清理不等于产品具备崩溃清理。受控清理、部分写入／登记中断窗口、丢失业务ID的恢复、代理／ASGI前置缓冲及swap仍不在本次证明内；完整一致性点及当前授权未具备前不能据此自动删除孤儿或重传。
- 新二进制封装把20 MiB原始文件与≤4 KiB类型／Limits头分开计量，一次AES-GCM认证，不自研分块算法；旧JSON封装可读且原限制保留。回退只能使用同时认识两个显式格式的读取器，不能把新格式改名为旧版或恢复明文直链。PrivateStore.read返回内部密文封套；公开下载必须在上层完成当前授权与完整open，现仍未开通。
- 新链须显式注入CryptoPort、AUDIT key和隔离ObjectContext。v1原writer／验证算法保留，v2用独立audit 0007表及链锁；不将原记录原地改写或升级。当前／保留key由owner显式给定，库记录不能自选新key。验证使用只读接口，签发须ACTIVE，M6不回调Gateway。checkpoint_root须owner预建0700目录，文件为0600不可覆盖的内容寻址对象。只能在无外层事务时创建已提交链检查点；文件与目录fsync前不返回引用，失败文件保留、不自动覆盖。后续验证必须由可信库外管理记录显式提供checkpoint_ref；禁止从待恢复DB选“最新”或缺文件时降级。未选择引用时是无锚验证，即使目录里有文件也不声称截尾保护；检查点后缀仍有窗口。当前没有定期维护／恢复开通接线或旧源迁移；下述归档批准只适用隔离捕获，不据此声明6-F05完成。
- 旧链捕获组件`DjangoLegacyAuditArchive`在同一个只读PG快照中按原算法验链并流式写age副本；Limits分别限制两表行数和单行大小，不把业务20 MiB当整份归档限额。目录须服务所有且0700，文件0600；只用公钥，保留源表，不迁移／删除。离线age解密实证只针对合成小样本，不开放历史原文下载、不把旧时间或裸SecurityAuditRecord正文升级为已认证。
- 隔离归档须显式调用`assemble_legacy_archives(config_path=..., directory=..., age=..., recipient=...)`，配置必须已有新链，recipient为ACTIVE BACKUP_PUBLIC；目录／工具路径来自可信装配，不从HTTP请求接受。以认证user调用owner.run(operation='capture', expected_count=..., expected_tail=...)；当前数据库active用户及明确archive_auditledgerentry权限必须通过，audit.0008不自动赋权。无外层事务才可执行。M4先记录精确count／tail的AUTHORIZATION v2，再捕获，随后经同一个Gateway桥接BACKUP；本地回执fsync后才返回成功。批准事件可能存在而捕获失败，不据批准认定已有归档。
- 桥接写前／写后确认丢失或sidecar保存失败返回带原archive_ref的错误并保留密文；数据库与文件不是跨资源原子。重启后以当前授权user调用owner.run(operation='reconcile', archive_ref=原引用)，只核原文件／有界登记、原认证批准，再以原event_id重放桥接并保存回执，不重新capture。不可用本地confirmed或receipt代替认证链；load只核权限、大小和SHA，不是age解密／标签认证。缺失或篡改拒绝，不当作零效果；partial／age／不完整登记保持隔离，不自动删除／重传。旧源迁移／隔离／删除、离线业务恢复和密钥轮换未完成；仅隔离显式入口，无默认HTTP／生产开通，不把对账成功当历史原文访问批准。
- 内部离线内容检查可调用M6 `verify_content`：由可信调用方预先取得并核对StoredObject与原认证BACKUP事件，另外提供可由原KeyResolver解析的BACKUP_PRIVATE引用和隔离服务上下文；不要把sidecar或归档header作为批准来源。该方法不查询数据库，也不替调用方认证传入证据／复核当前业务权限。密文目录0700、文件0600；私钥只经memfd交给age，不写命令行正文／日志／仓库。按行有界解密并复用原v1算法，拒绝错钥、截断、header／行数／链／引用不符和额外尾部，必须读完且age退出0。返回仅为内容与可信预期相符，不输出原文、不写源表／新链或恢复库，不授予下载；旧时间及裸事件保证不升级。原capture／reconcile行为不变；失败保留原文件，不能凭此自行迁移、清理或轮换密钥。
- 显式归档装配可另传`identity=BACKUP_PRIVATE引用`启用owner的`verify`操作，READ_ONLY私钥可用于检查、RETIRED或错用途在装配边界拒绝；不提供identity时仍仅捕获／对账，verify不读文件即拒绝。认证user每次仍需当前active及archive_auditledgerentry权限，并须无外层事务。以原archive_ref调用verify，M4加载登记后从同一新链Sink认证读取原BACKUP事件，必须与登记事件完整相等，再将可信证据交给原M6内容检查；sidecar写confirmed不补出缺失桥接。当前只读检查不写Gateway、create或confirm；有原桥接但缺本地confirmed也不自行修改登记。该组合仍查询权限与新链数据库，不能称整条链离线或代替空库恢复；HTTP、历史原文输出和恢复开通仍关闭。
- 内部可信审计证据必须经`AuditSink.read_authenticated(event_id)`取得，不能直接把事件表JSON当已认证。该方法复用完整链扫描与显式库外锚点，找到目标仍继续验证后缀，在链锁内保留已验证DTO，返回前不重新查询原始行。无目标／仅outbox／旧链／其他链／坏正文及缺key或检查点拒绝；拒绝不是“确切无交付”，不能据此释放额度、删除候选或重新发布。读取不签发新事件／检查点，不选latest，不改变原链锁序；全链验证不是短事务内的大文件处理，扫描开销随链长度增长，尚无长期链规模吞吐保证。读取复用调用方事务，能看到自身尚未提交事件但不会提交外层UoW；认证成功不等于持久提交确认，unknown对账不能用原未完成事务内的读取冒充提交证明。两域owner现已接入当前权限和metadata比对。两域reconcile只接受已知业务ID，在autocommit且无外层atomic时开启自身只读事务，正常退出后返回认证引用；调用方未提交事件不能据此确认。缺行／拒绝不证明零效果，不自动重传／清理／发布；完整unknown操作标识及生命周期仍待接线。这仍不是公开交付或恢复开通能力。
- 审计共享契约入口为`data_security.tests.test_phase6_audit_contract`与`audit.test_phase6_contract`。两者继承原15项及新增可信读取7项、相同断言；前者为独立内存状态，后者使用普通manage.py、专用PG及测试拥有的0700检查点目录。故障钩子只修改本轮合成记录／文件，不暴露为生产接口。内存不用于B、账本迁移或恢复，不模拟外层UoW、锁、fsync与持久保存；旧PG并发／回滚／文件权限专项不因新增契约组而重跑或被替代。证据使用新label保留首轮失败，仅续失败或实际受影响项。
- B新增可选audit_chain配置（仅ds.bootstrap.v2／evaluation），显式给定链身份、当前维护授权、READ_ONLY历史key引用及库外检查点目录／引用；不自动创建目录、选最新锚点、找历史key或升级旧事件。签发沿用独立ACTIVE audit_key，同一Gateway供catalog／protection及后续交付；配置显式checkpoint_ref时启动装配先完整验证，缺／坏文件或缺历史key直接拒绝。无此选项仍是原旧链配置，新事件拒绝而非降级。该B增量13项PG通过，实际新配置启动与ORM／字段4项补充验证也通过；不代表业务恢复ACL、ExportFlow owner、归档、检查点维护调用或下载开通完成。
- 内部PostgresAgeBackup可显式配置v2：private_root／code_version／required_keys三者一起给定，test／evaluation专用；B仅在ds.bootstrap.v2中接受这三个完整显式选项；原六字段配置仍为数据库v1，不默认升级。数据库导出及M6引用的不可变私有密文共用一个PG快照，两个age文件必须一起保管，主manifest绑定文件包摘要／大小／目录；StoredObject大小／hash仅表示主文件。在线只需公钥，离线身份另行解析声明的恢复key，不猜latest或扫描目录找key；声明可解析还不等于全部引用齐全、数据key正确或完整业务恢复完成。
- v2恢复先核空库／空私有目录、代码／格式／key引用、两包完整age认证，再流式写0600密文、比对目录并恢复SQL，最后回验数据库文件投影。缺包／截断／错age私钥／缺声明key均失败；manifest目录不符或pg_restore失败可留下密文，但无成功记录且下一次拒绝覆盖非空目录。目标隔离目录须保持不可下载，残留由受控恢复流程处理；不能用删除原文件或忽略错误换取成功。此端口不验证链／检查点，不自动发布候选，也不签发下载许可。
- 完整主库隔离演练已恢复178表，12个有序投影及真实交付的报告／额度／恢复许可、候选／已发布状态和实际密文open均核验；未登记源孤儿不入包。新链仍依赖明确保留在库外的原检查点，旧链仍按旧算法；故意损坏检查点或替换已声明data／audit key内容，恢复后的独立验真拒绝。此处验证由测试owner编排，不是已实现的业务恢复／下载开通服务；BackupPort的DURABLE不能替代这些检查。单次恢复SQL／文件耗时约18.846秒，不证明备份周期、全规模RPO／RTO或保留政策达标。
- 资源／反馈新私有文件恢复须由可信装配声明同一M6根及完整原框架／数据／审计key引用，独立保留配置、policy与选定的库外checkpoint；age私钥仅授离线备份身份。空库／空目录完成v2恢复后，再重装原B和两个owner，验证当前主体、工单／visibility、metadata、认证PROTECTION及每个原件／封面／附件的完整open摘要。当前B重装仍使用原ACTIVE引用，不代表轮换或只读恢复专用入口。BackupPort回执只证明恢复步骤，不能替代上述业务检查；停用用户、坏metadata、错误data／audit字节均须继续拒绝，不自动publish或开通HTTP。测试故障只修改本次恢复副本／独立保留的合成key，不能用这种测试写入方式操作真实恢复点。
- 后续恢复必须在空隔离环境验证全部业务引用与key、链、孤立候选、过期任务和分享状态；完成前下载关闭。当前v2仅M6单根，不含全部资源／反馈／独立执行器旧文件。age流式大备份不受20 MiB业务单对象上限限制；约24 MiB密文包局部验证通过，Python分配观测不等于全进程树RSS或完整业务链资源验收。7个日备份＋4个周备份的显式受管保留现有局部实测（见下文），周期执行及全业务RPO≤24h／RTO≤4h仍未达成验证，不宣称完整恢复达标。

D8保留操作仅面向显式隔离v2配置：通过`assemble_backup_retention`取得owner，创建双包时显式选择daily或weekly；缺省不纳管，旧v1、无登记v2和孤儿不能按mtime补成可删对象。UTC自然日／ISO周各取槽内最新一份，分别留最近7个日槽及4个周槽，不用7／28天TTL替代份数；没有足够备份时保留已有槽，不宣称补齐周期。在线只持BACKUP_PUBLIC，离线私钥、数据key和外部检查点不随退役删除。

维护窗口串行执行：先preview查看确切记录，再由可信调用方以该tuple调用apply；apply重新验库存，变动则拒绝、不自动采用新清单。Limits.max_actions限制登记扫描数（含退役登记）；达到上界必须单独评估登记归档，不能临时调大超过M0上限或跳过未知项。只要受管保留集或淘汰集存在缺包／坏摘要／坏登记，就不清理任何新集合。删除只指向已确认双包，旧未纳管文件保持不变；保留retiring／retired元数据与本地回执，不把这些回执称为v2链记录。

若中途I/O失败或确认丢失，停止批次并保留UNKNOWN；先检查每个登记的retiring／retired和两个文件的实际存在情况，已成功项不重做，未知项不能当未删或已删。当前没有自动修复retiring或并行清理／恢复协调器，须另行核准残留处置；不得删登记来掩盖中断。新增6项真实PG／age测试覆盖保留后离线恢复、正式B／文件公钥、坏新包、边界限额、v1拒绝纳管及双包中途失败；只证明合成单根维护行为，不开放业务下载、不保证备份调度和全规模RPO／RTO。

恢复许可管理仅在B显式调用时装配：当前Django add_recoverypermission／change_recoverypermission权限分别控制签发／撤销，不自动赋权；业务role和is_staff不能代替该权限。许可与v2事件同事务，提交确认丢失返回带许可引用的UNKNOWN，禁止自动再次签发。仅恢复入口用原Flow执行release／reconcile，报告锁后重取当前active用户及明确许可；装配缓存身份不能绕过后续停用。传入的窗口／限额／TTL必须与原预占一致，否则完整绑定冲突，不猜测配置或使用过期导出授权代替恢复许可。不能把已授权零结算当作客户端未收到文件的通用证明；零证据仍由原报告准备隔离及回执仓储产生。

B1新增仅引用恢复HTTP：v2／evaluation的可信配置明确提供export_recovery的window_key、limit、ttl_seconds并已有认证v2链，普通start_application才注入原Flow恢复入口；缺省503，不自动启用。POST `/api/data-security/exports/recovery/release/`或`reconcile/`只收execution_ref／permission_ref，以当前认证用户操作服务端保留的完整binding，客户端不能提交binding／数量／成功证明或配置。没有文件输出、execute／commit或权限签发HTTP，不是B2下载开放。返回逻辑状态并明确network_delivery_confirmed=false；失败保留原候选、报告与额度，提交确认丢失后只按同引用授权对账，禁止自动重传或release。

上述HTTP为已写入但未通过验证的组合，不可按已验入口开通：`b1-risk-delivery-recovery-postgres-01`的9项HTTP均在子进程退出检查失败，未取得父测试的响应／效果断言结果；同组最终审计锁定位1项亦失败。210项为200 ok／10 FAIL、退出1，根因未确认、未修复或续跑；不能以内部恢复入口原2项通过替代HTTP验证。继续保留默认不配置export_recovery及正式交付／下载关闭，完整记录见acceptance §10.1。

security_policies.0009新增可空binding_document，测试库已实际应用；begin及直接put新建时保留完整执行意图。原prepared可从旧报告取binding，无意图的旧preparing保持UNKNOWN，不回填猜测。停止恢复HTTP只需保留配置缺省关闭，不能逆迁移删意图／许可／额度或交给旧清理器；本轮没有迁移原运行库，完整回退／恢复点与候选drift状态见验收记录。

目标计划审批通过`assemble_export_plan_approvals(config_path=...)`显式装配，必须有新链配置。可信调用方传入draft ActionPlan／完整ExecutionBinding／ObjectContext及当前认证user：`manage(operation='approve', requester=...)`复核请求者active、binding主体及两人分离，批准者需add_exportplanapproval权限；`manage(operation='revoke', ...)`需change权限并传入原approved plan，不传requester。返回`(approved_plan, AuditReceipt)`才是已确认管理结果，不是交付／源访问许可；无外层atomic且autocommit时才允许管理。security_policies.0008只新增许可表，迁移不自动赋权或改变旧报告／额度，不逆迁移删审批状态掩盖撤销。

审批UNKNOWN保留稳定approval_ref和原draft／binding／context，不自动重新批准。以当前active且有add_exportplanapproval权限的管理者调用`reconcile(user=..., approval_ref=..., plan=原draft, binding=..., context=...)`；只能在autocommit且无外层atomic时执行。M6核原精确许可及经read_authenticated取得的原AUTHORIZATION metadata，锁后检查撤销／期限，自身读事务正常退出后返回含原Approval的ActionPlan，不生成新ID、不再写事件。缺行、换绑、坏链、撤销／过期或读事务退出错误不能确认成功，也不是确切零效果，不能自动重新批准／释放／删除。当前请求者在后续authorize另行复核，管理观察不把停用主体重新启用；不能把许可行存在或裸事件JSON当作已确认成功。`authorize`供原Flow在预占前和报告锁后调用：当前active请求者、完整精确许可及锁后期限均须通过，准备中撤销不能提交，已预占额度仍按原恢复权限处理，不擅自release。来源真实记录、请求供应器、完整交付B及HTTP仍未接线，测试中的合成来源标签／approval_basis不授予生产来源批准；历史交付回执重放不授予当前下载。

旧执行器新增私有模式仍只供显式内部调用，不开HTTP。需先应用`controlled_export.0002_private_preparation`及原M6迁移；新增app属于同进程库，不加载主后端Django工程。当前隔离测试库已实际应用这些迁移，check及makemigrations --check --dry-run通过；本轮未对原ds_phase1_export业务库执行migrate，不把测试库成功当运行库已升级。原旧文件及ProtectedArtifact引用未迁移。回退须保留private_candidate、prepared／unknown状态及密文，不逆迁移删新引用，不将其交给只认识旧candidates/artifacts的清理器。

显式prepare传原M4绑定方法、可信project_ref及完整Limits；只允许evaluation、无外层atomic且autocommit，不能借新入口提高旧执行器限额。claim先提交稳定attempt上下文，锁外准备后再次检查授权／lease／fence，只保存不可下载verified候选。出现repair_required／unknown时，保留原上下文与原幂等绑定；重放只观察，不重传、不释放配额或删文件。expire_stale_attempts对新私有意图只封为unknown并保留密文，旧模式仍stale／failed；命令不是私有候选清理或效果判定。prepared也不代表PROTECTION新链、可信报告、交付或可创建分享。正式B、原HTTP入口／临时上传、完整下载分享、执行器任务及文件恢复尚未接线。

蜜标内部工具仅供显式隔离owner调用，目录来自受控CanarySeed元数据，不能从请求正文中补任意检测值或目标。plant要求当前授权和合成目标owner持久化回执；测试回调不是正式权限或业务落地。check返回空tuple／新链回执tuple／ProtectionError三种结果，错误不可当无泄露。未装配新链、钥不可用或旧链回执均不得报告告警成功；不在失败处理中递归写日志。实际OfficialAI、SafeLogFormatter／install_safe_logging及TableReportExecutor已有可选CanaryCheckPort注入点，默认不启用蜜标；现有AgentGateway支持显式CanaryToolRegistry注入，但缺省工具为空，三个目标owner、B启用、模型tool-call协议及重启目录恢复／退役均未完成，不能宣称业务已部署。模型检查在最终业务payload保护后、认证与发送前；日志只查已经清洗／格式化的文本，不为查蜜标恢复原文，失败固定输出且不递归日志；表格检查实际serialize→parse结果和保留标题，命中在加密／写候选前拒绝。表格owner必须另供绑定当前execution／对象的检查身份，不能从ObjectContext自造审批。记录为拟输出发现，不是客户端收到或实际泄露证明；不启动线程／cron，不修改原三期封口或M8格式语义。

运行时注册时由装配方提供plant、CanaryCheckPort、resolve_context和load_output；后两者必须依据当前可信用户及操作／对象版本授权并读取对应实际产物。持有admin角色、缓存的用户is_active或模型提供的引用均不是许可。网关只向安全工具转交调用，不将其混进自动学习检索，也不另存原文工具结果到AgentRun。未注入时明确返回CANARY_TOOLS_DISABLED；异常只返回CANARY_TOOL_FAILED，不携带正文或自动重试。生产owner和B装配未实现前，不把显式测试注册当上线，不开启下载。

2026-11-06 16:05用户仅批准6-F04的tmpfs／交换保护实证按环境受限未验登记，不计通过、不降低D7／20 MiB、不执行swapoff。20 MiB处理／超限／峰值内存／吞吐／崩溃清理和6-F03／G06文件级原文扫描仍须实际执行。完整私有文件／审计新链／恢复及canary工具尚未完成，禁止据该窄登记开通下载或进入第7期。

B1当前另登记P6-B1-SOURCE-CONTRACT待授权，细节见实施报告和E6的b1-source-contract-review-01.md。原P5批准不重开，也不请求生产开通；待明确首个正式evaluation来源／冻结请求的登记与源批准、当前使用许可和风险输入权威，以及mainline1环境不兼容时的正向范围。现有TXT→CSV、资产映射及风险ALLOW夹具不接正式B，M8和真实PLAN_APPROVAL_REQUIRED不改。报告binding重取仅供已保留执行恢复，不能替代完整请求／源计划。最后在途组的失败结果已归档，B1已停工但未完成；来源建议未获用户批准，10项失败未修复，本轮不再新增实现或重跑。只读收尾核无相关测试进程／其他PG客户端及遗留的默认／执行器测试库，原库owner不变、检查连接已关闭；这不是看护或全量验收。不启动下一块，不提交候选、推送或开PR。

### B1四点批准后停止边界（2026-11-08，09:24批准前历史）

上一段和§10.1验收记录中的来源待批是批准前截点；用户四点来源批准仍有效，P6-B1-SOURCE-CONTRACT不重新登记待批。新P6-B1-RISK-AUTHORITY需明确现有可用风险画像／真实条件审批读取路线，或另行授权必要的COLUMN_V1持久化供应器；固定政策目录已存在，保持缺画像REQUIRE_APPROVAL及缺历史非零语义，不用测试provider、源／目标批准或MAC绕过。

原十项仅fixture修正后复验为8 ok／2 FAIL，最后两项诊断为2 FAIL、49.471s、exit 1，child均exit 0；默认503的既有5xx审计只新增SecurityAuditRecord，unknown release按原owner契约映射403而新fixture期待409。未抑制审计、改M4／Quota拒绝码或改断言凑绿；失败保留，后两次200不冒充未执行的效果断言通过。临时诊断已封存移除，HTTP只保留secure=True，可精确逆向重建批准起点全文；清理后未重跑。

此历史postflight核owned PG目录、原三库owner、无测试进程／其他客户端／遗留测试库且检查连接关闭，冻结AST／diff通过；当时dirty见E6的`b1-resume-blocked-working-tree-01.json`。这不是G06、drift、看护或候选成绩。正式来源供应器、完整交付B、6-F02 owner矩阵及6-B02 HTTP验收当时未完成，执行方待授权收尾停下；保留密文／意图／许可／回执／审计与unknown容量，不逆迁移或自动释放。此后批准与继续实施见下，不将旧阻断当当前停工状态。

### B1按需最小新建批准后操作边界（2026-11-08，实施中）

09:24批准仅解除已核缺口，06:50来源四点继续有效。内部显式v2 export_delivery仅接受private_root／project_ref／window_key／limit／ttl_seconds，要求evaluation和认证v2链；没有配置仍关闭，没有新增交付、下载或权限签发HTTP。所有权限由明确管理流程授予，迁移不自动赋权；禁止把验收账号、测试预绑定或旧golden的approved标签接入正式B。

内部调用顺序：实际资源私有原件→受限source.register（完整请求／计划／输入／资产身份）→真实第二人source.approve→当前source.grant→grant_risk和原admit→需要时由有change_columnriskpermission的第二人批准→bind保留完整执行→approve_target单独目标批准→唯一ExportFlow执行。原件仍只按获批对象解释CSV；画像缺失仍缺失，不能换policy、改environment、重标mainline1或用目标批准填补风险。risk grant原始完整研判经认证保留，当前授权和审批状态另重取，历史批准人的后续权限丧失不自动改写有效批准，但当前请求者失权会阻断。

同绑定重放与产物读取不做第二次逻辑交付；只有后者在成功授权读取时增加单独观察审计，不重开原件、重研判、reserve／publish／settle。未知效果保留额度与候选，已提交赢家不得退款／重结算；已知准备失败也不能在缺恢复权限时自动release。恢复仍以服务端重取binding＋当前操作专属permission执行，缺报告／意图或数据库错误不证明零；明确fence和零结算共短UoW。HTTP unknown release为403，默认关闭503照旧写既有5xx审计，不抑制审计。

目前独立两项HTTP裁定与8项普通启动修正smoke通过；完整60项owner／故障／恢复组合为58 ok／2 FAIL，仅修新测试的object_ref见证查询和既有logically_delivered状态预期。后续18项为17 ok／1 FAIL，三处真实锁等待均通过；唯一目标审批故障注入需包裹正式B已保存的write_permission，而不是装配后替换类方法。只修测试后，审批确认丢失／原许可对账与新双进程存活准备owner竞争2项完整通过，后者竞争者无业务效果、赢家只一次交付／结算，安全元数据已归档。产品不改；pure同166项只改回工作树根目录调用后全过，不把首轮cwd错误或18／60项失败改成成功，不拼接suite。首轮8项因环境重启停在迁移、0测试结果；自有PG按原identity受控helper恢复，同会话续跑，不覆盖中断证据。没有对生产或原运行库迁移／开通；B1完成前不进B2–B5，候选提交及全量回归归B5。

原十项已有相同 command／cwd 的完整 10 ok；原域 373 的 180 ok／193 无结果仍为中断记录，不称整体通过。四项遗漏后来由主线程普通启动 PG 实际复现为 3 FAIL＋4 FAIL；approval 首轮另有迁移中断、0 测试，原日志保留，只按原 identity 重启自有 PG 并检查／清理遗留测试库后续跑。只读委托误触发技能的 SQLite／35 单测自述始终排除正式 PG 证据。

现行最小修复要求：产物输出或逻辑回执前最后等待后重取当前源／目标／精确 policy，提交还须通过原 consumed 授权的观察复核；到期或撤销不能留下新的成功回执。新条件批准在 decision／permission 锁后重取当前审批者；不追溯改写历史有效批准。approve_target 已得到真实批准 A 后发生源指针保存或确认错误，错误 trace_id 保留 A；用该返回引用调用原 reconcile_target，不重新 approve，不因指针缺失释放或删除。两种故障分别覆盖未保存／已保存源指针，均两次对账保留唯一 A 和认证事件，再完成一次交付／2 条结算。

原样七项反例 `b1-authority-repairs-postgres-01` 已 7 ok、218.646s、exit 0，原 pure 入口 169 项完整通过；实际 postflight 核 871 份源码、精确 ID、0600 与无 runner／测试库／其他客户端。当前完整 457 唯一 ID（正式 84＋原域 373）正在单次串行运行，尚不据子组通过开通或宣告 B1 完成。没有产品全局开关、生产迁移或 HTTP 生命周期扩围；B2–B5 不动，候选全量仍归 B5。详情见 `b1-formal-authority-review-01.md` 与实施报告。

### B2 私有 HTTP、对账与扫描操作（2026-11-08；待独立测试）

以下为副本实现的操作说明，不覆盖上文历史验证记录，不是生产或恢复开通批准。B2 工作会话只写代码并做分钟级无数据库检查；PG、完整运行快照和块裁定由主会话分发。不得在未配置 PG 的 B2 副本启动数据库或以 SQLite 代替。

**主后端显式配置。** 保留现有 `DATA_SECURITY_CONFIG` 的 v2／evaluation／FileKeyResolver／认证 audit_chain 配置，按服务器管理流程准备同 uid 的 0700 密文根，然后增加：

```json
"private_files": {"private_root": "/srv/ctf-private", "project_ref": "ctf/evaluation"}
```

这是既有配置的片段，示例路径不自动创建；根不能位于公开 MEDIA／STATIC 内，也不能反向包住它们。若同时设置 export_delivery，project_ref／private_root 必须一致。普通 django.setup／start_application 才注入原件 owner、分享及最前置 middleware／ASGI 边界；手动 assemble 不等于 HTTP 已绑定。缺 private_files 时正式上传仍 body 前 503，其他正式私有调用拒绝，不回落 FileField。正式 MEDIA 猜路径拒绝不代表外部代理已正确配置，代理仍不能直挂私有根。

| 方法与路由 | 输入及权限／结果 |
| --- | --- |
| POST `/api/resources/upload/` | 原 multipart／格式校验；当前上传权限；需 `X-File-Operation-ID` 规范 UUID；服务器生成密码对象身份 |
| GET `/api/resources/{id}/download/`、`cover/download/` | 当前上传者或 active is_staff；完整认证后附件响应，不因 approved 对他人开放 |
| POST／DELETE `/api/resources/file-operations/{uuid}/` | 原操作主体：正向重取／显式终止后精确清理；返回 operation_id、state、result_id、network_delivery_confirmed=false |
| POST `/api/resources/{id}/shares/`、`cover/shares/` | 同原件当前 ACL；以新的操作 UUID 创建固定 5 分钟引用，不增添读者权利 |
| POST `/api/feedback/{ticket}/attachments/` | 原 multipart、工单归属／visibility 与 10 MiB 限额；同操作 UUID 规则 |
| GET `/api/feedback/{ticket}/attachments/{attachment}/download/` | 每次重取当前工单与 visibility，不用缓存归属或旧 FileField |
| POST／DELETE `/api/feedback/{ticket}/file-operations/{uuid}/` | 同原操作主体与工单；result_id 为附件 UUID，不是整数 pk |
| POST `/api/feedback/{ticket}/attachments/{attachment}/shares/` | 同工单／附件 ACL；需操作 UUID |
| GET／DELETE `/api/data-security/files/shares/{uuid}/` | GET 仍需原件当前 ACL；DELETE 仅原签发者且仍有原件权限；撤销保留证据 |
| POST `/api/data-security/exports/resources/{execute\|download}/` | JSON 仅 source_ref、permission_ref；复用已配置 B1 owner／Flow，不接客户端批准／binding／成功证明 |

先保存调用方操作 UUID，再发送上传；确认丢失时按原引用观察，或携相同元数据／文件重试，不换 UUID 强行再创建。prepared／missing／UNKNOWN 都不是零效果或可发布；没有确切意图不能删看似孤儿的文件。活跃 flock 持有者存在时观察／清理拒绝，不靠时长接管；进程退出后同根重新装配再正向对账。锁文件保持原路径与权限，不手工删除；此机制不承诺网络文件系统或多个私有根间协调。

显式 DELETE 先将当前授权及终止意图入链／提交，随后只清理该操作保留的精确密文。提交确认或 unlink 确认丢失时保留 tombstone，用同一 DELETE 继续，不删除业务引用、操作行、分享或审计以伪造“没有发生”。published 输出不走此候选清理；已经被逻辑交付消费的额度也不在此退款。新增迁移为 `security_policies.0010_privatefileoperation`，包含操作和分享表；回退必须保留这些表、v2 上传引用及 retired 状态，不能逆迁移抹掉终止约束。备份 live-files 不要求 retired 对应文件，DB dump 仍保留行；备份／清理应在既有串行维护窗口安排，不宣称跨文件系统／数据库原子快照。

**独立执行器。** `CONTROLLED_EXPORT_PRIVATE_CONFIG` 指向受保护、规范绝对路径的 JSON（≤64 KiB）；必须是 `ds.executor-preparation.v1`，精确字段为 schema_version、environment=evaluation、key_manifest、data_key、private_root、project_ref、limits。另保留明确 framework SECRET_KEY、原服务内部凭据、EXECUTION_AUTHORITY_HMAC_SECRET；DATA key 必须 ACTIVE，私有密文根与旧 CONTROLLED_EXPORT_PRIVATE_ROOT 分离，Limits 不提高原执行器上限。普通 app.ready 调用本工程 B，不加载主后端 Django 工程，也不启动额外服务。

原 POST `/api/controlled-export/executions/` 的可信服务认证、X-Caller-ID、授权签名、Idempotency-Key、authorization／plan／file 均保留。新增 GET `/api/controlled-export/executions/{execution_id}/preparation/` 观察；空 body POST 同一路径正向核验保留候选。不能提交 context／候选／成功证明或换 caller 接管。即使 candidate_verified=true，也只称 prepared 或原 repair_required，不补成功事件、发布、结算、分享或负向清理；该独立入口的完整交付仍未开放。正式模式旧 shares／deliveries 路径 body 前关闭，PrivateStorage 拒绝。停能力时保持正式关闭门，不通过清空所有正式配置回到旧明文存储。

两套 ASGI 的引用路由实际总 body 预算 64 KiB；上传按实际接收字节有界驻留，不因伪造／缺失 Content-Length 落默认 spool。业务单对象 20 MiB 与反馈 10 MiB 不变，原件／封面最多 2 个驻留对象。完整验证后才组装内存下载响应；no-store／nosniff 不是网络收讫证据，也不是代理、swap 或所有并发资源的验证。停止新交付／私有下载应撤下对应 private_files／export_delivery 能力并保留 `DATA_SECURITY_CONFIG` 的三、四期安全绑定，不删密文、账本、unknown 额度或退役证据。

**全清单原文扫描。** `tools/data_security/phase6_plaintext_scan.py` 读取操作者事先封存的 `ds.b2-plaintext-scan.v1` 清单，精确字段为 schema_version、scope、targets、max_expanded_bytes；每个 target 仅 category 与绝对 path。runtime 必须登记 private、media、temporary、executor-legacy、backups、logs、evidence、screenshots、production-source 九类，包括实际为空的目录；目录未复制、遗漏、不可读、symlink、快照变化或不支持格式均不能记零。清单须覆盖全部实际根，工具只能证明 declared_inventory_only，不会发现操作者漏报的另一目录。

标记输入为 ID→合成原样值映射（每批 1–100 项，值 8–4096 UTF-8 字节）；使用本轮真实上传原件、附件、导出原文及既有登记语料，不临时换成未用过的随机值。超过 100 项分批扫描相同完整清单，逐批保留结果，不抽样。工具扫描 UTF-8／UTF-16／JSON 转义／base64，原文件流式读；ZIP/XLSX/gzip 只在内存有界展开，不解压到磁盘或运行内容。图片／PDF／嵌套或不支持内容仍是 unscanned；如需渲染审查，另留明确逐文件证据，不能把字节未命中改成 OCR 已通过。

从可信代码目录用本副本 Python `-I -B` 调用脚本，显式传 `--manifest`、`--markers`、`--output`；控制输入和输出放在待扫快照外，不拿扫描器刚创建的空文件充数。输出只含标记 ID、文件／内容摘要、数量和未扫原因，不含命中正文或业务文件名；新输出使用独占创建及 0600。清理前（含故障残留）与显式终止清理后分别封存／扫描；不能先由 fixture teardown 删除产物再报零。源码 scope=source-only 永远不返回 runtime_scope_verified=true；既有合成样例的非零命中保留原结果并单独说明，不删源样例、排除命中或替换标记凑绿。此处没有新识别器、后台扫描、恢复／轮换或蜜标业务接线。

### B3 隔离恢复和旧源维护（2026-11-08；待独立 PG／age 验证）

本节是显式维护接口的使用条件，不是部署、生产删除、密钥销毁或第 6 期验收批准。工作会话只运行无数据库检查；真实演练交独立封存测试树。恢复目标必须为本次获准的隔离空数据库＋新建空私有根（同 uid、0700），不能把这里的 close 当成关闭现有非空线上根的通用开关。先从外部隔离目标网络，核验目标数据库／代码／密钥配置，再操作；不启动 HTTP 来完成恢复。

**完整备份与周期。** 原 `ds.bootstrap.v2` 的 backup 字段保留 database、directory、checks、age、pg_dump、pg_restore、private_root、code_version、required_keys，显式增加 `full_inventory: true`。database 沿原本地 loopback／无内嵌 password 限制，private_root 须与 private_files／export_delivery 相同，project_ref 也保留原值（如 `ctf/evaluation`），不能为了恢复改成 domain。库外目录、工具、清单均由服务器受控输入；checks 不代替全表清单。required_keys 登记包括旧 envelope 读取、索引、审计／报告在内的必要精确引用；遗漏不会被自动补齐为成功。

在线 `assemble_backup_cycle(config_path=..., recipient=...)` 仅接受 ACTIVE BACKUP_PUBLIC 引用，调用 `run_due(context)` 检查完整 daily（24 小时）／weekly（7 日），到期才建立新包。无 full 清单的旧包不算本周期达标。没有新增 cron、线程或自动恢复／清理；接入调度另走运行授权。D8 仍由原 `assemble_backup_retention` 预览并显式确认七日槽＋四周槽删除；保留失败、unknown 和旧无登记包，不以时间到期自行删除。轮换或旧源变更前重新演练并留档，不拿周期新建成功替代恢复演练。

**离线恢复顺序。** 离线清单保留实际需要的旧读钥及明确选定 BACKUP_PRIVATE identity，在线服务只拿 recipient，不能把私钥清单用于普通 HTTP 启动。主站使用 `ctf_backend.security_bootstrap.assemble_recovery(config_path=..., identity=..., archive_directory=..., archive_identity=...)`；归档参数只在确有旧审计归档时显式提供，目录内容要另外受控复制并核验。工厂只构造离线端口，不读待恢复表。context 是原可信服务入口构造的 evaluation／ctf／service/security／SERVICE／STORAGE 上下文，不能由 HTTP 客户端自填。

1. `run_ref = flow.run('close', context)`：对空私有根落受控 journal，保存本次引用；这是演练停服计时起点。构造前的主机／目标库准备不在该计时内，记录时不得宣称生产故障开始时间。
2. `flow.run('restore', context, backup=selected_backup)`：只传保留的原 StoredObject，读取匹配的离线 identity；完整 age 认证后才 SQL 恢复。恢复前／后都不开通流量，数据库恢复成功也不等于 owner 核验。
3. 将离线 Django 连接明确指向该目标 NAME／HOST／PORT，使用同一目标配置调用 `flow.run('verify', context)`。PG 必须 autocommit 且不在外层事务；核验器自行建立只读 repeatable-read。提供原外部 checkpoint，不能重建锚；旧审计隔离／删除记录还必须配原实际归档和匹配 identity。检查 complete、opening_allowed、未知／终态计数、真实未锚后缀与外部 key 清单缺口。
4. 检查完整 DB／密文／pending 清单及 owner 核验记录后，由获准维护者显式 `flow.run('open', context, approved_run_ref=run_ref)`。该调用再比清单并重做 owner 核验；错引用、源变化、旧明文未治理、缺钥／锚、RPO>24h 或 RTO>4h 均不开放。RPO 从实际备份 snapshot_at 到 close，RTO 从 close 到最终 open；记录停服至恢复、恢复、核验、人工确认四段实际时间，不能填合成时钟成绩。
5. 只有完成该过程后，在线配置中的同一 full backup／私有根身份才能通过恢复门。WSGI／ASGI 的所有 HTTP 路径（含健康／未知路由）及 websocket 都受关闭门约束；ASGI 在 body 前拒绝。无 journal 只保持从未恢复部署的旧基线；不得删除 journal 绕过隔离，也不得通过撤掉安全配置回退旧存储。

每步须检查 ProtectionError，不把返回对象存在当成功。失败保留 journal、partial 目标、原备份、源及未知意图；restoring 失败不允许自动重入覆盖目标。另行批准新隔离目标后重新演练，原失败证据保留。`status` 只读状态；核验后的 `flow.journal.proof(context)` 只返回本地证明路径和 SHA，不是认证账本事件。后续 open 会改变 journal；给治理 owner 固定证明时应在所选最后状态封存受控副本，保持父目录0700／文件0600和精确 SHA，不能使用随后被改写的路径。

**旧源治理。** 先应用 `security_policies.0011_privatefileoperation_legacy_sources` 到获准测试库；工作树的小检查没有执行该迁移。用原 `assemble_private_maintenance(config_path, private_root, project_ref, legacy_root, recovery_proof)` 返回的资源／反馈 owner，传当前用户、原对象／工单 ID 和稳定 operation_id。动作顺序为 stage→实际 full 备份及关闭态 restore/verify→带源专属 proof 的 migrate 或 quarantine→另外授权的 delete；资源方法为 `maintain_legacy(user, resource_id, operation_id, action, replaces=None)`，反馈另需 ticket_id／attachment_id，均用关键字调用。stage 不改 FileField、不授下载或删除；rotate 只替换未切换 staging，实际重加密并保留旧候选，replacement 必须另做恢复证明。staff 不能覆盖当前原上传者及原 ACL。原源字节变化、仍被别的 owner 引用、缺审计／证明都拒绝；删旧源不删新密文、旧意图、tombstone 或历史回执。

旧审计沿 `assemble_legacy_archives(..., identity=..., recovery_proof=...)` 和原 `LegacyArchiveOwner.run`：原捕获／认证桥接→离线验内容→精确源恢复证明→quarantine→单独 delete。当前权限重新检查；法务 FK 拒绝删除时保留引用和全部源，不改成 SET_NULL。旧 payload／event／timestamp 原样保留，历史未认证字段不升级保证。归档目录不是 private 包的一部分，缺原归档时不能把 deleted 标记认作空 genesis。

**密钥和退役。** DATA 轮换在显式 retained_data_keys 登记旧 READ_ONLY 引用，新写只用当前 ACTIVE；旧签名 envelope 保留原 ACTIVE 标签，仅在读取材料时选择明确保留引用，原 resolver 精确匹配不放宽。字段沿原 FieldRotation；不能就地改已签上传／报告／回执的 key_ref。audit retained_keys 保留认证历史，新备份 recipient 只影响新包，旧 identity 离线保留并验证实际能读旧包。恢复结果列 data／index／audit／report／归档 identity 引用；`backup.key_inventory(context, limits)` 仅本地 retained 包诊断，metadata_age_authenticated=False、retirement_allowed=False；私有维护 key_inventory 也不是全域退役授权。汇总保留包、其他归档／checkpoint、opaque 文件和 recipient↔identity 映射，实际离线验包后另行决定，不能凭本地零引用销毁 key。

**独立执行器。** 新 `ds.executor-preparation.v2` 在原 v1 精确字段外增加 retained_data_keys 和 recovery_target_identity；旧 v1 行为保留，target 绑定原完整 BackupPort 的 source_identity。独立工程 `assemble_recovery(backups=..., crypto=..., project_ref=..., limits=...)` 只接显式离线原端口，复用同一 close/restore/verify/open 顺序，不加载主站 owner。核验范围仅原私有 preparation：prepared／unknown 不晋升，过期记录不自动清除，旧 artifact／candidate_storage_ref 未入包则不开通，outbox 不冒称 v2。此处没有执行器发布、下载、分享或负向清理批准。

**测试分发。** 精确 56 ID 与预期见 `~/workspace/data-security-seven-phases/logs/phase-06-block-b3-worklog.md` 的“测试分发请求”。完整主库 fixture 另需 `DS_B3_FULL_RECOVERY_RUN=1`、封存树自有 `.state/postgres.json`（synthetic_only、匹配 socket／port、test_ds_phase1_main）、DS_PHASE3_TOOLS 和唯一绝对路径 DS_B3_RECOVERY_EVIDENCE。正例通过才写真实时间／数量，不写 key 或源正文。adapter／recipient 组沿 `DS_PHASE3_BACKUP_RUN=1` 和每次全新的仓外0700 DS_PHASE3_CONTROLLED。执行器用其独立工程／专用库。禁止在本工作会话跑这些 PG／age 组；测试方须在 teardown 前保留本轮实际产物用于原文扫描，收集 ID 不等于验证通过。

## B4 蜜标隔离部署与维护（2026-11-09；实现不等于验收）

先在获准隔离测试库应用 `security_policies.0012_canaryregistration`、`legal_kb.0006_legaldocument_canary_payload`、`resources.0006_resourcecache_canary_payload`、`challenges.0010_challenge_canary_payload`。本工作会话只做 migration drift，没有连接数据库或执行迁移。不得用生产资料或现有有正文的业务行充当目标。

显式 v2 bootstrap 的 `canary` 段精确包含：

- `seeds`：原 CanarySeed wire 列表，环境 evaluation、域 ctf；三类 target_ref 分别为 knowledge/database/challenge 加实际正整数 pk。
- `project_ref`：固定可信项目 namespace，用于原 CryptoService AAD；恢复时不得替换。
- `provider_ref`：实际配置的 volcano/deepseek/moonshot/qwen 之一。audit_chain 必须 ds.audit.v2，backup 必须原 full_inventory=True；所有数据／审计读钥和 checkpoint 按既有离线清单保留。

目标分别是本人空 draft/other 文档、本人空 ResourceCache、staff 可管理的 inactive 空题目。只增加业务表专用加密字段，不发布或自动检索；三处普通正文与原 ACL 保持不变。新目录 model 的 Django permission 不自动授予用户：plant 需 add_canaryregistration＋目标 change；check 需 view_canaryregistration＋目标 view；retire 需 change_canaryregistration＋目标 change，另检查当前 active actor 与本人范围。没有默认 admin/teacher 批准。

可信内部调用 `runtime = assemble_canary_runtime(config_path=...)` 后，显式传当前 user 和已授权任务给 `runtime.run_security_task(user=..., message=...)`。模型只传 seed_id 或 artifact_ref；check 引用格式为 `canary/<seed_id>`，不是文件路径，实际原样产物只由 owner 从业务密文解密。模型按需选择工具，无固定流程、自动重试、HTTP 新入口或普通学习任务自动写操作。任务只返回状态和安全 metadata；不要把原样值、seed、请求正文或异常详情写日志／界面。缺工具／provider 注入直接关闭。

退役由可信维护调用 `components['canary']['owner'].retire(seed_id=..., user=...)` 显式进行，不是模型自动步骤，也不删除任何密文。当前权限仍必须有效；重复退役读取原认证结果，相同 seed 不复活。保留 planted/retired 元数据和配置 seed；不能删配置绕开历史检测。退役不是毁钥批准。

恢复仍用 B3 原 close/restore/verify/open。B 在原 owner 核验之后追加目录只读核验，检查三业务字段、目录、packet／event 和当前选定 checkpoint；孤立密文、遗漏目录配置、错钥／AAD／hash／链都保持失败。成功 metadata 包含 planted/retired 计数和 data_key_refs，不含原样值；引用合并进原恢复清单。两个顺序只读快照不宣称原子跨资源快照。核验不补种、改状态、发锚、开放流量或销毁 key；完整 age 恢复与三出口正式 B 的 PG 结果仍交独立测试会话，详见 B4 工作日志“测试分发请求”。

## 第 7 期文本 RAG、原文申请与统计（2026-11-10；开发状态，非部署批准）

本节补充前述历史截点；六期候选／独立验收仍为七期总验前置，不接手 B5。当前分轮结果与待批事项以 `~/workspace/data-security-seven-phases/evidence/phase-07/INDEX.md`、`GATE-STATUS.md` 和实施报告为准，不能把源码存在或配置片段当作已启用／已验收。

**文本与历史。** RAG pipeline 由 B 显式注入既有 parser／chunker／embedder／repository，正文、标题／文件名／metadata 在切块和 embedding 前保护；查询、召回、cache 读写及再次外发继续过现有保护入口。未绑定的历史基线不因此成为获准发布模式；回退只能使用已验证的脱敏索引或保持不可用，不能靠撤掉安全配置回到原文索引。图片／OCR 已按用户改令搁置，图片拒绝外发；不得据旧图文简报执行 OCR＋遮罩。火山方舟文本 vision 路径固定 `doubao-embedding-vision-251215`、显式 `dimensions=1024`、官方 `/api/v3/embeddings/multimodal`、响应 `data.embedding`；不本地截断或改向量列。凭据仅用既有 key_ref 安全注入，不从本机探测厂商；捕获桩不等于真实语义联调。

**原文申请。** 原 `ds.bootstrap.v2` 可选 `reveal_requests: {"enabled": true}`，需要已绑定字段存储和认证审计；缺配置或关闭不提供能力。仅普通 `start_application` 绑定 M9，单独 assemble 不代表 HTTP 已启动。本期新增 `security_policies.0013_reveal_request` 和 `0014_reveal_request_metadata`，隔离测试迁移证据不授权对运行库或生产执行迁移。

| 路由（统一前缀 `/api/data-security/`） | 使用口径 |
| --- | --- |
| GET `reveal-source/` | 仅 source_id、field、field_ref，可选 course_id，单值参数。由现有资料列表的业务编号定位 UUID／当前版本，只返回已获准对象元数据，不创建申请／批准。 |
| GET `reveal-requests/` | 当前可见申请元数据；offset 默认 0、limit 默认 50／最大 100。不是原文列表。 |
| POST `reveal-requests/` | object_ref、object_version、fields、purpose、reason，可选 course_id。当前调查用途；ID、申请者、时间、批准和 grant 均由服务端生成。 |
| POST `reveal-requests/{request_ref}/{approve\|reject\|revoke}/` | 空 JSON 对象，不接受客户端批准人、期限或 grant。继续复核当前对象／角色权限；申请与批准分离。 |
| POST `reveal-requests/{request_ref}/read/` | 空 JSON 对象，只走限时单次原文读取；持有申请号不等于有权读取，不提供长期明文下载。 |
| GET `stats/` | 仅当前 active admin；只接受单值 offset，每页固定最多 20 条，next_offset 指向后页。不接受客户端 limit。 |

资料定位支持 email→`users.ctfuser/email`、evidence→`legal.legalanalysistask/input_text`、report→`legal.legalreport/content`。学生仅本人邮箱；教师／管理员扩大用户范围仍需原有效课程授权；法律对象还受原 IsLegalReviewer 与实际 task owner 规则限制。管理员、生成者、CourseDataGrant 或 read_protected 均不等于原文批准；不开放会话、手工事实、密码或密钥。核对后字段／业务编号／课程发生变化须重新定位，提交仍会拒绝旧版本或已撤销权限。

申请／定位 API 沿 IsAuthenticated 和原 owner 权限；管理页路由仍限管理员。理由先保护后保存，列表不泄露申请原样理由；审批最长 900 秒，读取在同 PG UOW 内先单次消费再解密，成功须有同 event_id 的 ds.audit.v2／LEDGER_CONFIRMED 收据。所有新 HTTP 响应均 no-store/private、Pragma=no-cache，不将原文或统计写入浏览器持久存储。管理界面不展示真实原文样本。

**统计。** 沿已启用的第四期管理装配提供只读 reader，不另增统计配置或采集系统。逐报告区分原处理／复扫、单位、资产／Coverage／策略版本；报告重建后还须通过历史 MAC 验证。历史 MAC 只证明完整性，不代表当前授权、交付、网络收讫或验收。缺分母显示未知；确有 eligible=0 时 numerator=denominator=0、ratio=null，并标 NO_ELIGIBLE_UNITS。unknown_records 是未知报告份数，不是字段或单元格数。字段／文本／出口缺完整 Coverage 时明确未知，不能从事件数量反推比例。当前能力只报告 disabled 或 enabled-unverified，不自动升级为已验收。

**保留与恢复后的治理仍未落实。** D8 的七日槽＋四周槽沿原显式预览／批准入口，不是自动 TTL 或最长 28 天销毁承诺。D4 对话类最长 30 天仍只有隔离元数据登记；七期各对象到期起算、例外、派生副本与证据范围列为 P7-RETENTION-SCOPE 待确认，不能直接自动删库／文件。P7-HISTORY-GOV 未批，历史切块／向量／缓存／直链只清点。当前恢复核验能检查恢复快照和原锚，但尚无七期恢复点之后删除／撤销重放成绩，包含新 RevealRequest；不得据恢复成功开通这些未验能力。详见 E7 `LIFECYCLE-SCOPE-01.md`，不另建恢复通道、不绕过原清单或 journal。

**关闭与未验。** 关闭 reveal capability 不删除授权历史；如需撤销未消费批准，须由原有权限路径显式执行，不直改库或清空证据。保留前期字段／P0 保护、密文、账本和 unknown 额度。浏览器因本地网络检查受限，构建与 node --check 不代表页面交互或窄屏通过；不关检查或外露服务绕过。完整候选 default／bound／pure 全量及相关性能／总验部分按 2026-11-10 07:17 改令暂缓，等用户再令，不把文档命令或分轮开发结果计入累计。
