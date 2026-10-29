# 评估中心与教师运营台（模块八，第一阶段）

模块八消费 M1/M6 的事实，不提供成绩写入接口，不复制模块七审批状态机。

## 数据与指标边界

- `projections.py` 的查询不写任务、事件、成绩、画像或推荐。M6 当前 VerificationResult 是当前判定；原 SubmissionSnapshot 与历史更正均保留。
- 正式学生为未在 `NonFormalAccount` 标记的 student 账号。演示/离线账号需部署负责人显式登记，不能靠用户名猜测。内置页面演示使用单独的合成返回值，不创建用户/成绩/快照；旧 learning_analytics 合成快照不作为 M8 成绩来源。
- 指标固定带 numerator、denominator、missing、value、status、window、versions、source；零分母或未知值返回 null。三组指标不产生总分。
- `not_connected` 表示阶段内证据源未接通，`no_data` 表示没有样本，`not_started`/`not_evaluated` 表示阶段外。模块三/四/五未就绪；只读风险回放不等于实际保护。
- 任何帮助/独立判定仅覆盖平台可观测帮助；事件不是通过证据。不能把核验失败、人工待评、未参加复测当知识错误。

数据库迁移仅创建本应用表。无需新增 Python/Node 运行依赖。

## 教师协作（M8-3）

- `GET/POST /api/evaluation/todos/`：独立分组队列 / 创建待办，可绑定本人调整提案；不改变提案状态。
- `POST todos/sync/`：幂等导入 M2 求助、M6 开放题必评、常规抽查（含 needs_correction）和争议；源快照保存导入时的状态与抽查依据，另以 source_current_status 只读展示源队列实时状态（含已完成/需更正）。源处理仍走原模块。
- `POST todos/<uuid>/`：`revision` 加 `action=claim/transfer/handle/verify`；转交/处理需摘要，转交需教师 assignee_id，验证可带真实 retest_id。过期 revision 返回 409；每次更新和审计同事务；数据库保存失败返回503 / save_pending_retry，不先报成功。
- `GET/POST receipts/`：查看 / 显式消费 M6 module8 通知。以 notice_key 幂等记录本应用回执，按学生、任务/目录版本与原提交日窗口重算；保留原结果引用。源 notice 维持原状，不把本地消费伪装成上游推送已接通。部署可定时调用受保护的消费服务；本阶段未新增后台调度平台。
- 复测必须同学生、关联原尝试、不同场景且能力重合、干预后实际提交，当前结果为平台内独立通过。更正使证据失效时重新进入待验证；即便尚未消费通知，读侧也复验已验证证据，不展示陈旧成功。`verified` 仅指复测证据达标，不是因果效果结论。
- 教师页的协作区是全平台队列，不受上方学情筛选控制；演示模式不展示。前端构建已通过；浏览器/真实后端联调尚未验证。

## 隔离评测与模块七接缝（M8-4）

迁移 0003 增加 EvaluationRun、EvaluationCaseResult、EvaluationReport 及 manage_evaluation 权限。报告为合成回归，不是独立终验或实际教学效果证明。

- `GET/POST /api/evaluation/runs/`：列表 / 以 candidate_id、purpose、max_cases、max_duration_ms 创建冻结运行。
- `GET runs/<uuid>/`：受权限保护的运行元数据；不返回任意配置正文。
- `POST runs/<uuid>/execute/`、`interrupt/`：执行 / 将中断运行封存为不完整报告；逐例结果持久化。预算耗尽、缺例、依赖缺失不得建议通过。
- `GET reports/<uuid>/`：带 reference、版本、三组指标、逐例差异、预算/完整性、审核待办与限制说明的 JSON 报告；下载可保存此响应，无额外免鉴权路径。
- 读取须管理员/超级管理员，或持有 `evaluation_center.manage_evaluation` 的教师；普通教师权限不等于系统评测权限。
- 写服务仅在 `EVALUATION_ISOLATED_TESTS=True` 且 `ROOT_URLCONF=evaluation_center.test_urls` 时可用，操作者还必须是独立、有效、有管理权限且标记 offline 的账号。正式配置下不能运行，即使是管理员。
- `evaluation_center.test_settings` 使用内存数据库与本地缓存，不适合生产或持久服务部署。服务适配器只在 test_urls 注册；独立令牌 `Authorization: Evaluation <token>` 及服务端账号 `EVALUATION_SERVICE_ACCOUNT_ID` 必须显式配置，无默认有效令牌。请求只传冻结 run_id，不接受角色、URL 或案例输入。
- 固定合成集合 `m8-synthetic-regression/1` 仅支持 TASK-X@1.0.0 的教学 export_record_limit 单因素；100→120 正例与超出授权边界的反例走已有 export_risk 纯规则/回放。其它任务范围、模型、提示、知识库或组合配置均不能借此获得通过建议。该合成集合没有真实 API 比较；另设的真实网关集合见下文，两者都不产生真实学生学习提升指标。
- 同版本逻辑证据用 replay_digest 对比；report_digest 覆盖完整报告（含真实运行 ID、时间和耗时），不同运行不要求后者相同。模型/token/费用未知保持 null。
- M7 登记、完成评测、审批、发布前解析真实报告，验证 run/report/digest、候选身份、完整配置内容摘要、基准/候选版本及任务范围；不能复制候选摘要来伪造报告。审批/发布/回退仍由 M7 持有，其第三阶段开关默认不变。

## 固定验收与复跑（M8-5）

`acceptance.py` 的 `m8-phase1-acceptance/2` 将场景1–10映射到真实测试，并登记合成规则与真实模型/提示两种集合，同时逐项列外部依赖。固定选择器可用以下命令在Django测试库运行（不是对正式数据库跑评测）：

```sh
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test_evaluation_acceptance
```

全部本应用测试用 `manage.py test evaluation_center --noinput`；最终项目回归用 `manage.py test backend --noinput`。确切已运行命令和结果见根目录 PROGRESS.md / DELIVERY.md，提供命令不代表已经执行过该命令。

固定集成案例在注入断连、超时、429、额度耗尽，以及关闭生成/语义检索/重排条件下，实际调用M1/M2/M6 API完成领取、只读练习、规则提交、人工必评、教师协作和无提示新场景复测。注入超时使用缩短的50ms测试预算，并核对小于10秒；不是对真实供应商做十秒SLA证明。恢复/迟到响应沿已有M2测试验证，不重放工具或覆盖结果。

仍须真实联调/签收的项目：课程材料/目录；模块三全部检索、缓存与撤权；模块四实验台；模块五服务端挑战/修复与网络、宿主、凭证、资源回收隔离；真实供应商故障、跨模型泛化与知识库API对比；本轮单一提示比较的实测结果单列在交付记录。M6源提交接口数据库异常仍返回通用失败，本应用没有擅改其HTTP错误契约。现有本地测试不能据此宣称两条试点任务已在真实设施全面开放。

## 显式真实网关批次（第二轮）

- `live_fixtures.py` 登记 `m8-live-export-classification/1`：6个合成输入、每个配置每例2次观测；允许 `prompt_version` 或 `model_id` 单因素，不能改变任意地址、角色、输入或工具。原25例 `m8-synthetic-regression/1` 内容摘要有固定回归断言，不受扩展影响。
- 两个已登记模型为 deepseek-v4-flash / deepseek-v4.1，两个提示为 export-classifier/v1 / v2。基准/候选完整安全配置与提示正文冻结入manifest；每次只发送该例输入与对应提示，不发送预期答案、其他用例、学生信息或源表。
- `create_run(..., dataset_version='m8-live-export-classification/1')` / API的dataset_version字段选择登记集合。默认仍是无网络合成回放。真实模式还要求 `EVALUATION_LIVE_GATEWAY_ENABLED=True`；读取/校验报告不需要开启网络。
- 真实模式仍复用 EvaluationRun / EvaluationCaseResult / EvaluationReport、完整摘要验证和M7原有挂接/完成评测服务。报告 `mode=live_gateway, simulated=false, input_source=synthetic` 表示传输真实、输入合成，**不表示真实学生实验或物理隔离**。不完整结果不予挂接；完整失败/证据不足报告可以登记，但进入needs_revision而非审批通过。
- `gateway.py` 固定连接127.0.0.1:8317，不走环境代理、不跟随重定向。客户端密钥只从本机config.yaml内存读取：新结构是 `access.api-keys`，顶层 `api-keys` 是上游供应商分组，不能混用；兼容旧版顶层数组。配置、报告与日志均不保存密钥。现有LangChain环境已包含PyYAML，本轮未安装新依赖。
- 429/502/503/504、连接错误及超时最多3次尝试，退避2/4秒；401/403不盲重试。每次socket超时至多30秒，批次统一截止时间；这不是对恶意慢流的硬墙钟取消或真实供应商SLA保证。默认批次900秒，最多72次尝试、每次最多256个输出token；费用价格未知，不假设免费。
- token按响应观测，缺失及重试的不明消耗分别报告，未知总数与费用为null。两次观测不一致不能得到pass，不伪称可确定重放；接口只保留规范化action和白名单用量/错误元数据，不保留原始模型正文、推理或错误体。

独立持久scratch操作示例（需事先授权真实调用；不是测试套件自动联网）：

```sh
scratch_dir=$(mktemp -d /tmp/m8-scratch-example.XXXXXX)
export EVALUATION_SCRATCH_DATABASE="$scratch_dir/evaluation.sqlite3"
export DATABASE_BACKEND=sqlite
/home/hatch/workspace/ctf-venv/bin/python backend/manage.py migrate evaluation_center --noinput --settings=evaluation_center.scratch_settings
/home/hatch/workspace/ctf-venv/bin/python backend/manage.py migrate --noinput --settings=evaluation_center.scratch_settings
EVALUATION_LIVE_GATEWAY=1 /home/hatch/workspace/ctf-venv/bin/python backend/manage.py run_live_evaluation --settings=evaluation_center.scratch_settings
```

命令只接受专用 `/tmp/m8-scratch-*/*.sqlite3` 磁盘库，拒绝存在正式账号的库；创建独立offline账号与明确标识的M7合成问题组。M7发布开关始终关闭，不审批或发布候选。也可显式选择 `--factor model_id`；提供此选项不代表跨模型实测已经运行。普通 `test_evaluation_acceptance` 只跑mock传输契约，不产生计费请求；实际运行ID、结果与未完成边界以根目录记录为准。
