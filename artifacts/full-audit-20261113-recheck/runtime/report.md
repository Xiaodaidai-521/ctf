# 部署、权限与内部服务复查（2026-11-13，Asia/Shanghai）

本轮读取当前源码、重新执行检查并生成独立证据，没有覆盖前两轮结果。使用 `.state/full-audit-20261113/venv/Scripts/python.exe`（Python 3.12.8，Django 6.0.3）。所有数据库测试连接核验过 data_directory 的本轮合成 PostgreSQL 集群；测试环境不加载业务 `.env`，禁止供应商、Docker daemon 和无关服务器连接。运行时配置专项只读检查了业务环境是否具备外部配置，没有输出配置值或密钥。

## 本轮自主修复

1. `backend/data_security/adapters/persistence/models.py` 的 RevealRequest 两个用户外键硬编码 `users.CTFUser`，独立 controlled-export 服务只安装标准 `auth.User`，因此整个服务启动检查报 E300/E307，103 项测试在执行前被终止。改用 `settings.AUTH_USER_MODEL`。迁移 `0013_reveal_request.py` 本来已经使用 `swappable_dependency(settings.AUTH_USER_MODEL)` 和可切换外键，改动使运行模型与迁移一致，无需新迁移。平台和独立服务的系统检查、迁移一致性均通过。
2. `tasks/controlled-export-execution/controlled_export_service/security_bootstrap.py` 用 POSIX mode 校验配置文件。在项目文档支持的 Windows 环境中，即使原生 DACL 已正确隔离，mode 仍是 0666，受保护模式也会被拒绝。改用已有 `is_private_path()`，在 Windows 检查真实所有者、受保护 DACL、禁止外部读取者及 reparse point，在 POSIX 要求当前用户和 0600 权限。新增两个真实 Windows ACL 回归：正确隔离的配置进入 schema 验证，仅 chmod 的非私有配置仍被拒绝。2/2 通过；没有放宽权限守卫。

## 重新验证的结果

| 检查 | 当前结果 | 证据 |
| --- | --- | --- |
| 隔离 Nginx 1.28.0 + stdlib HTTP fixture | 16/16 通过 | runtime-smoke-results.json |
| 依赖冲突 | pip check 退出 0 | runtime-recheck.json |
| 当前 Compose 结构（占位外部路径） | 退出 0，无警告 | runtime-recheck.json |
| 当前实际 Compose 环境 | 退出 1，TLS_CERT_DIR 未配置 | runtime-recheck.json |
| Django 系统检查 | 退出 0 | ../supplement/recheck-rt-check.log |
| 平台迁移一致性 | makemigrations --check --dry-run 退出 0 | ../supplement/recheck-rt-migration-check.log |
| 平台迁移计划 | showmigrations --plan 退出 0 | ../supplement/recheck-rt-migration-plan.log |
| 独立 controlled-export 系统检查/迁移一致性 | 均退出 0 | ../supplement/recheck-rt-export-check.log、recheck-rt-export-migration-check.log |
| mainline1 内部纯逻辑 | 157/157 通过 | ../supplement/recheck-rt-mainline-pure.json |
| mainline1 真实 PostgreSQL 事务/多连接/独立进程 | 67/67 通过 | ../supplement/recheck-rt-mainline-postgres.json |
| 安全工具纯逻辑 | 12 个测试方法，11 个成功；备份回执方法的两个 subtest 失败 | ../supplement/recheck-rt-tool-pure.json |
| 独立 controlled-export 全组 | 最终结果见 ../supplement/report.md | ../supplement/recheck-rt-export-final.json |

Nginx 覆盖配置语法、TLS/HSTS、SPA 深链、Django 静态与媒体路径优先级、资源/反馈私有路径 404、靶场 JS 代理、可信 scheme、2MiB 上传、57MiB 拒绝、无私有请求/代理临时文件以及健康探针成功/故障分支。使用新生成的一小时临时 TLS 证书、随机 loopback 端口与独立临时目录。结束后 Nginx/fixture 已停止，TLS 私钥已删除。该结果不表示真实 Gunicorn/PostgreSQL/FRP 链路已验收。

补充 PostgreSQL 复测使用 `--keepdb` 保留唯一合成测试库，避免 Windows 全集群 DROP DATABASE checkpoint 的重复等待；未关闭 fsync 或放宽数据库持久化。旧检查日志与仍在收尾的命令不会作为本轮完成证据。

## 仍需要定夺或补充前提

| 项目 | 本轮实证/源码状态 | 所需决定或前提 |
| --- | --- | --- |
| Linux Docker 部署 | Docker version 没有 Server；dockerDesktopLinuxEngine 管道不存在；HypervisorPresent=False | 选择恢复本机 Docker 模式并安排重启，或使用 Linux 测试服务器。 |
| TLS、FRPS、域名/拓扑 | 本轮 .env/进程中 TLS_CERT_DIR、FRPS_CONFIG_FILE 未配置 | 提供正式外部文件，确认域名、Host/Origin 与跨容器 FRP 网络；占位路径只证明 YAML 结构。 |
| Windows libmagic 分发 | 当前隔离测试用真实 DLL；requirements 中 wrapper 本身不包含系统 DLL，Linux 镜像已有 libmagic1 | 明确 Windows 系统 DLL 部署方式，或采用 Linux 部署。 |
| Windows/备份测试工具与夹具 | phase3 Linux `/tmp`、chmod fixture 不满足 Windows native DACL；备份回执工具依赖 Linux age 路径并断言 0600，当前两个 subtest 是 Windows mode 差异 | 在 Linux 验证原契约，或明确把备份验收工具、密钥夹具迁移到 Windows；不能造旧恢复证明或放宽校验。 |
| 旧 standalone Nginx 入口 | `backend/start_nginx.sh` 仍使用旧绝对挂载路径、ctf-bridge、仅映射 80，缺 TLS；`backend/nginx.conf` 指向旧 frps-server 名称。当前 Compose 不使用它 | 决定废弃旧入口或按正式拓扑重做；本轮没有运行它的停删旧容器操作。 |
| 模块四课程开放 | `docs/data-lab/teacher-signoff.md` 尚无两位教师签收，行业目录未选、50/51 阈值 draft | 真实领域审校、冻结材料及目录/阈值/开放范围决定。 |
| 模块五教学语义 | `docs/module5-r2-course-signoff.md` 记录共用修复提示、受控解析/WSTG/许可版本缺口；解释保存但不评分，固定适配器 manual_required=False | 决定是否解释人工合格才允许通过，以及提示梯度、解析曝光/分发许可、课程版本。前端入口最终状态以本轮前端专项为准。 |
| 通用模块六网络核验/下游调度 | verification.py 的 server_verifier/external/isolated_challenge 仍返回 server_evidence_not_connected；下游消费/复测到期仍需运营调度 | 明确具体验证器与受控环境、正式消费/重试/提醒策略。专用模块四/五适配器和本轮交接修复不能替代通用网络验证。 |
| 正式功能开关 | 本轮 PRACTICAL_TRAINING_ENABLED、FEEDBACK_PHASE3_ENABLED、FEEDBACK_PHASE3_RELEASE_ENABLED、EVALUATION_LIVE_GATEWAY_ENABLED 均未开启 | 在业务检查与真实联调完成后决定开放。默认关闭不等同于接口未实现。 |
| 真实模型/向量服务 | 本轮未访问供应商；历史 2026-11-12 报告记录 401/429 | 有效凭据、权限、额度到位后重新实测。不能把历史状态写成本轮测得。 |

## 需要用户参与的联调

1. Linux Docker、Nginx、Gunicorn、PostgreSQL、FRP：真实证书与域名、Host/CSRF/Session Cookie、跨容器请求、健康状态、SPA 深链及首次迁移后调度启动。
2. 双学生真实靶场：创建/领取/启动、跨学生拒绝、JS/CSS/WebSocket、实际主机名、并发与资源上限、停止/到期/故障回收。
3. 模块四/五：真实教师审校与学生身份、冻结版本、提示曝光与帮助记录、解释评分口径、复测和 day3/day7 教学保持观察。
4. 模块六/七/八：真实持久评测报告、独立审批、提交/更正/争议、仅后续任务生效、观察/稳定/回退/事件对账。业务修复的最终清单见本轮业务专项。
5. 远程嵌入、语义召回、回答引用、真实质量/并发，以及供应商鉴权故障、限流处理。

本专项没有启动正式部署、重启宿主、修改虚拟化设置、操作业务数据库、伪签课程审批或修改正式开关。
