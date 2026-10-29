# 模块五第二轮：本机真实验收工具

这是 **2026-10-29 的一次性运维验收设施**，不是新生产运行时、通用 HTTP 代理或容器管理平台。只绑定回环地址，只测试本次创建的合成学生和私有数据库。它不修复既有 `challenges` proxy/直连路径，不代替课程签收或生产环境验收。

## 已运行的内容与边界

- 官方 Juice Shop v20.2.0 的 `node24_linux_x64` 预编译发行包，Node v24.22.1；没有使用 Docker。
- 包 SHA-256：`dbb457f74e908e28c41d7787e36d30d121d5b9f6178524720567b4aeb41f2968`，与官方 release 元数据核对一致。下载/解包位置记录在 `evidence/module5/r2-extraction.json`。
- 两个独立应用副本，各自 user/mount/PID/net namespace + chroot，只启用 loopback，应用执行前清空 capabilities、设置 NoNewPrivs，Node 不继承宿主凭证环境。未挂载宿主 proc，没有获得独立宿主 UID。
- 私有 UNIX relay 连接隔离内的 Node；宿主只读观察网关仅允许 `GET /api/Challenges`。学生网关仅实现本次所需 GET，每次调用实际平台 assignment HTTP API 校验身份/状态，并丢弃平台认证头再转发。它不是兼容完整 Juice 前端/所有方法的生产网关。
- 固定服务端 reader 对两实例记录未解基线；学生 B 通过真实应用 HTTP 获取挑战文档，B solved=true、A=false。真实源证据通过现有模块六/模块一持久化契约回传。
- 生产 `PRACTICAL_TRAINING_ENABLED=false`，真实 start API 拒绝；课程/任务保留 draft、environment_available=false，**没有创建人工审核或 EnvironmentApproval**。驱动仅在专用 DB 记录运维验收基线和状态，再调用可信证据交接。不能把这条路径说成生产 claim/start/verify 全链路通过。
- 资源实际为 Node `RLIMIT_AS=2 GiB`、`RLIMIT_NOFILE=256`、单 CPU affinity、Node heap 参数 256 MiB。地址空间分配探针实际触发 MemoryError。它们不等同 768 MiB RSS/整组内存、CPU 带宽或 256 PID 限额；本机没有相应 cgroup 委派/system bus，实际 Max processes=27153。
- 按真实 12 秒授权截止时间停实例进程组、关闭端口；旧凭证撤销，物理确认后才写 destroyed 回执/confirmed_by_runtime。修复代码测试仍是合成访问控制方案验证，未在线修补 Juice。

可信宿主 root 和宿主内部 observer 端口在学生进程隔离边界之外；不证明宿主所有本地用户隔离、多宿主网关/VPN、生产 ACL 或高可用/崩溃恢复。

## 文件分工

| 文件 | 用途 |
|---|---|
| `sandbox_bootstrap.py` | 建立私有挂载、最小设备、chroot、清空能力后启动 worker |
| `worker.py` | 隔离内 Node/UNIX relay、网络与资源探针；不继承宿主敏感环境 |
| `host_lab.py` | 两实例/回环网关/控制面 canary，真实时钟清理，保存运行清单 |
| `platform_server.py` | 私有 SQLite 上的真实 Django HTTP 服务，生产/模型开关关闭 |
| `live_acceptance.py` | 真实 HTTP、固定 reader、跨学生对照、证据交接与回收断言 |
| `delayed_observation.py` | 只读未来观察资格检查，不改时钟、不生成通过成绩 |

## 实际成功运行的命令

以下是成功运行所用路径与命令，不是让操作者直接覆盖当前证据的安装脚本。`host_lab.py` 和 `live_acceptance.py` **固定写入本 worktree 的 `evidence/module5/r2-*` 文件**；重跑前必须先完整另存这些证据并核对待覆盖对象。另用全新数据库，不复用本次保留的已解基线。脚本只接受专用本地资源，不向共享库运行。

前提：Linux 支持本次用到的 unshare/chroot/mount/setpriv 能力；Node 24、现有 venv、util-linux；空闲端口；`/var/tmp` 有两个约 440 MiB 应用副本的空间。下载包是不可信数据：各下载/解包放新空目录，脚本放本目录；Python 读取归档用 `-I`，不在下载目录运行解释器。未新增应用 npm/Python 依赖。

本次路径：

```sh
ROOT=/home/hatch/workspace/ctf-module5
PY=/home/hatch/workspace/ctf-venv/bin/python
DB="$ROOT/evidence/module5/r2-live-corrected-60T78i.sqlite3"
RELEASE=/home/hatch/module5-r2-release-83dxnqzu/juice-shop_20.2.0
```

首次使用空 DB，在 **backend** 目录迁移：

```sh
DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH="$DB" "$PY" -u manage.py migrate --noinput
DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH="$DB" "$PY" manage.py makemigrations --check --dry-run
```

保持两个终端/受管理后台任务运行（命令从本 worktree 调用，不从解包目录调用）：

```sh
"$PY" -I -u "$ROOT/scripts/module5_r2/host_lab.py" "$RELEASE"
"$PY" -I -u "$ROOT/scripts/module5_r2/platform_server.py" "$DB"
```

等 `TWO_REAL_JUICE_INSTANCES_READY` 且平台实际 HTTP 可响应，再在第三个终端运行：

```sh
"$PY" -I -u "$ROOT/scripts/module5_r2/live_acceptance.py" "$DB"
```

本次输出：`REAL_CHALLENGE_AND_ATTRIBUTION_PASSED`、`REAL_EXPIRY_PORTS_AND_CREDENTIALS_PASSED`。发生启动失败/断言错误不是通过；检查相应日志，停止本人启动的控制器。禁止宽泛 `pkill node`，禁止对未知 PID 发信号。控制器收到 TERM/INT 或最迟 3600 秒时自行执行清理，但 Django 平台服务须单独停止。本次两个 Juice 实例和平台服务均已停止。

| 服务 | 端口 |
|---|---|
| 平台 HTTP | 18380 |
| 宿主控制面正向 canary | 18390 |
| A / B 隔离内 Node | 18211 / 18212（各自 namespace） |
| A / B 学生网关 | 18411 / 18412 |
| A / B 只读 observer | 18111 / 18112 |

精确运行/清理路径及 PID 见 `r2-live-manifest.json`、`r2-runtime-cleanup.json`。旧 PID 只作证据，不可在未来不核对进程身份就用于清理。进程已停止不代表临时文件已删除，保留的 release/runtime 副本不能被误说成还在运行。

## 延迟观察：只登记，不冒充时间经过

实际解出基线为 `2026-10-29T05:45:42.991558+00:00`；计划及证据/attempt/result 关联位于 `r2-delayed-retest-plan.json`，专用 SQLite 一并保留。

- day3：`2026-11-01T05:45:42.991558+00:00`。
- day7：`2026-11-05T05:45:42.991558+00:00`。
- `r2-delayed-retest-calendar.ics` 仅为待人工导入的 tentative 文件；没有创建外部日历事件、自动调度或承诺到时自动执行。

安全只读检查可重复执行，不会覆盖 DB/原证据：

```sh
"$PY" -I "$ROOT/scripts/module5_r2/delayed_observation.py" \
  --plan "$ROOT/evidence/module5/r2-delayed-retest-plan.json" --checkpoint day3
"$PY" -I "$ROOT/scripts/module5_r2/delayed_observation.py" \
  --plan "$ROOT/evidence/module5/r2-delayed-retest-plan.json" --checkpoint day7
```

2026-10-29 两次实际检查均为 awaiting_real_time、retention_proven=false（`r2-day3-eligibility.log` / `r2-day7-eligibility.log`）。即便到期，工具也只输出需真实学习者/新证据，不自动认定保持通过。

教师须先审核课程和环境，按模块一/六契约准备新场景、全新未解实例、关联新尝试与新服务端证据；不得重放旧 solved。当前账号是操作者驱动的合成学生：它可验证未来流程，**不能证明人的学习保持**。真实学习者须有自己的真实初测基线及对应三天/七天等待期，不能直接继承合成账号的成绩或时间。

## PostgreSQL 与回归

PostgreSQL 专项不使用此真实 Juice 运行；其两进程测试用 HTTP fixture + 真 PG 行锁，隔离两种证据口径。

- 报告：`evidence/module5/r2-pg-report.md`。
- 工具：`backend/scripts/r2_pg_verify.sh`、`r2_pg_concurrency.py`、`r2_pg_assertions.sql`。
- PG 16.13 / pgvector 0.8.1 为私有测试安装，未改系统服务/venv；本地 trust 认证不可用于部署。driver 路径和固定端口仅适用于此次私有集群，已有数据时不要直接重新执行 `all` 或清库。
- 50 个模块五 PG 测试通过；五组真实双进程竞争及原生只读 SQL 数量/唯一约束检查通过，不是压力/所有交错覆盖。具体命令/耗时/停服记录以专项报告为准。

SQLite 受影响套件的成功命令（cwd 为本 worktree `backend`）：

```sh
DATABASE_BACKEND=sqlite /home/hatch/workspace/ctf-venv/bin/python -u manage.py test \
  practical_training skill_review.tests learning_map.tests --noinput --verbosity 2
```

结果 119/119 OK，187.525 秒。本轮没有重跑全量；首轮 686 项的 5 FAIL/1 ERROR 是历史基线结果，不得写成当前全量全绿。

## 证据交接

`r2-http-*.json` 含真实应用响应和解题相关材料，虽已脱敏认证头，仍属于**受控验收附件**，不是学生公开课程资料；不送模型、不自动上传/发布。成功验收数据库只含此次合成账号，测试 Token 已撤销；失败运行 DB 保留历史测试状态，不可用它重开旧授权。初始失败、真实 key 勘误、资源/权限失败均保留，不能只拷贝 PASS 标记。

`.log` 和 SQLite 文件可能被 gitignore 排除；交接时须另行受控保存实际文件及最终摘要清单，而不是只看 git diff。完整结论与未覆盖事项见根目录 `DELIVERY.md` 的“保留项补做（第二轮）”及 `PROGRESS.md`。
