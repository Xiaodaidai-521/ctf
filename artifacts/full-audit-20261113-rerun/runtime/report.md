# 部署与课程准入复核（2026-11-13，Asia/Shanghai）

本轮在既有修改之上重新检查，没有覆盖历史证据。没有启动 Docker、重启宿主、改虚拟化设置、操作真实业务数据库或启用课程/发布开关。结论是：隔离代理与依赖检查通过，完整部署仍受当前主机和外部配置阻断，部分课程流程确有缺口；默认关闭和未做真实验收不能写成全部功能未实现。

## 本轮自主修复

| 项目 | 问题与改动 | 验证 |
| --- | --- | --- |
| Compose 调度启动顺序 | analytics-scheduler 原本只等 PostgreSQL 可连接，首次部署可早于后端迁移执行，三次管理命令查缺表后继续休眠 86400 秒。现在还等待 backend service_healthy；backend/start.sh 先迁移、收集静态再启动 Gunicorn，因此任务开始前表已就绪。container-cleanup 同样改为等待健康。 | runtime-before/after.json 记录依赖差异；占位外部路径下 docker compose config --quiet 退出 0。实际 Docker 启动未验收。 |
| 过时 Compose 属性 | 删除已被当前 Compose 忽略的 version 属性，消除每次校验的警告。 | 修复后结构校验退出 0、stderr 为空。 |
| 模块七文档矛盾 | 交接第8节仍说“无候选表、固定旧错误码”，结尾仍说“仓库无模块八报告生成”，与当前源码矛盾。改为当前已实现接口、真实开关错误码和已持久化报告事实，保留审批及真实验收要求。 | 对照 urls.py、迁移0002、CandidateError 和 evaluation_center 当前模型/服务。 |
| 模块六旧缺失说明 | docs/skill-review/README.md 把已有模块四页面、模块七争议桥、模块八报告/回执写成未实现。更新当前状态，保留真实缺口和历史测试时点。 | 前端专项确认M4页面已接、M5专用请求缺失；对照 dispute_link.py、evaluation_center/urls.py 与 skill_review/handoff.py。 |

上述是本轮新增改动。既有 Nginx 私有附件拒绝、代理优先级、上传大小/缓冲、健康探针、镜像依赖和 .dockerignore 修复予以保留，并重新验证其代理行为。

## 本轮实际结果

- Python 3.12.8、Django 6.0.3 的既有隔离 venv：pip check 退出0，无依赖冲突。
- 独立 Nginx 1.28.0、随机 loopback 端口、新生成一小时 TLS、独立静态目录和 HTTP fixture：16/16 检查通过，包含语法、TLS/HSTS、SPA深链、静态/媒体路径、私有文件拒绝、靶场静态转发、2MiB上传、57MiB拒绝、无私有代理临时文件、探针成功/失败。Nginx及fixture已停止，TLS私钥删除。这不是实际 Gunicorn/PostgreSQL/FRP 联调。
- Docker version 无 Server，Linux Engine 管道不存在；HypervisorPresent=False。没有尝试改变此状态。
- .env 与当前进程均没有配置 TLS_CERT_DIR、FRPS_CONFIG_FILE。真实配置 docker compose config --quiet 退出1；仅在独立子进程提供占位路径后结构校验退出0。占位路径不能用作证书/FRPS部署证明。
- PRACTICAL_TRAINING_ENABLED、FEEDBACK_PHASE3_ENABLED、FEEDBACK_PHASE3_RELEASE_ENABLED、EVALUATION_LIVE_GATEWAY_ENABLED 在本次读取的环境中均未开启，默认也为false；没有修改这些开关。
- backend/start.sh 当前CRLF数为0。依赖、Dockerfile、Nginx、健康探针等源码hash与已有runtime-code-hashes对照记录于runtime-before/after.json；Compose及修正文档的变化有记录。

## 真实缺口与需要定夺的部分

| 模块/项目 | 当前实现及不足 | 需要定夺/前提 |
| --- | --- | --- |
| 部署环境 | 当前无法构建/运行Linux Docker服务。TLS/FRPS外部文件和域名/网络方案缺失。 | 选择本机恢复Docker模式并重启，或提供Linux测试服务器；确认真实TLS、FRPS、域名和访问拓扑。已有说明见docs/virtualbox-docker-switching.md。 |
| Windows原生文件类型识别 | requirements中的python-magic wrapper不包含libmagic系统DLL。既有隔离测试借助真实DLL包通过；Linux镜像已安装libmagic1。 | 正式运行选择Linux或明确Windows DLL分发/运维方式；不能把临时测试DLL当正式依赖已交付。 |
| 旧standalone Nginx入口 | backend/start_nginx.sh仍硬编码旧绝对路径、ctf-bridge、仅80端口、无TLS挂载；backend/nginx.conf的frps-server不同于当前Compose服务名。当前Compose不调用它。 | 确认是否删除旧入口或按最终拓扑重做；本轮未运行这个会停删旧容器的脚本。 |
| 模块四课程 | 固定合成两案、扫描、复核、只读回放、提交、人工必评均有源码和页面。teacher-signoff明确无人双审，行业目录未选，50/51阈值仍draft。 | 两位领域教师审校材料/依据/量表，负责人确认目录、阈值和开放范围；跨课程教师对象权限与模块六通用入口联动需确认。 |
| 模块五学习页面 | 后端已有assignment/start/hints/verify/repair/reflection，前端无practical-training请求和专用实训闭环。CapabilityTaskList不能替代这些操作。 | 产品入口/学习流程仍须补齐；最终处置以主报告与前端专项为准。 |
| 模块五教学语义 | explanation仅非空与长度校验，handoff固定manual_required=False；错误解释也可随程序测试通过。独立修复四级提示入口、受控解析引用、外部附件版本和许可尚未完整。 | 决定是否要求解释人工合格才通过，以及提示梯度、解析解锁/曝光规则、课程版本与分发许可。不能自行设成绩口径或代签。 |
| 模块六通用网络核验 | services/verification.py对server_verifier/external/isolated_challenge返回server_evidence_not_connected。模块五专用可信适配器并不使通用网络核验自动接通。 | 确认应支持的具体任务/验证器和安全运行环境；按既有模块五契约实施后实测。 |
| 模块六下游/到期推进 | handoff仍记录M7/M8 target_connected=False、not_connected；M8已可显式消费回执，M7已有争议桥。复测到期推进仍教师/管理命令触发，无无人值守调度。 | 确认正式消费/重试频率、到期提醒/推进策略和事件对账运营方式；真实双向闭环需联调。 |
| 模块七/八 | M7候选/审批/生效/观察/回退和M8运行/报告/逐例结果均已实现，默认或配置限制运行。当前M7是否强制解析M8持久报告有重大校验风险，已交业务后端专项验证/修复。 | 必须按业务专项最终结果确认校验修复，再以真实持久报告、独立审批者完成闭环。真实供应商评测不能用合成回归替代。 |
| 远程模型/向量 | 已有2026-11-12证据记录embedding/DeepSeek 401、火山429；本轮未再次调用供应商。 | 有效凭据、权限与额度就绪后，真实嵌入/语义检索/引用/质量/并发复验。历史401/429不能当本轮重新测得。 |

模块四/五“里程碑I实际导出”当前未实现属于显式阶段边界；只读回放不产生执行授权。是否扩建应由需求负责人决定，不能在检查中打开实际执行能力或改写为已实现。

## 需要用户参与的独立联调清单

1. Linux Docker + Nginx + Gunicorn + PostgreSQL实际部署：证书、Host/CSRF/Session Cookie、数据库传输、FRP跨容器可达性、健康状态、SPA深链刷新及调度迁移依赖。
2. 两名学生真实靶场：创建/领取/启动、跨学生和宿主控制面拒绝、JS/CSS/WebSocket、不同主机名、CPU/内存/PID并发限额、停止/到期/失败回收、旧凭证拒绝。
3. 模块四/五课程：真实教师及学生身份、双审与冻结版本、提示及解析帮助记录、程序/人工结果口径、复测、day3/day7真实时间教学保持观察。
4. 模块六/七/八：真实提交/更正/争议/通知、完整持久报告、独立审批、仅后续任务激活、观察、稳定、回退与事件对账，保留旧尝试版本。
5. 远程模型/向量服务：真实嵌入、召回、回答引用和质量、供应商故障与限流处置；合成/替身测试仅证明本地分支行为。

证据文件：runtime-before.json、runtime-after.json、runtime-smoke-results.json及对应脚本。本专项16项代理检查可能与主检查覆盖相交，不应不加区分累加为全量独立测试数。
