# 模块五第二轮 PostgreSQL 实测报告

日期：2026-10-29。仅在 `/home/hatch/workspace/ctf-module5` 执行本专项；未读取或修改其他 worktree 的应用文件，未编辑 PROGRESS/DELIVERY，未 commit/push。

## 1. 结论

- **真实 PostgreSQL 16.13 + pgvector 0.8.1 实测通过**，不是 SQLite，也没有 mock 数据库锁。
- 全库真实迁移成功，包含模块五 `0001_initial`、`0002_challengemapping_review_hash`、`0003_correct_juice_challenge_key`；未跳过或 fake 迁移。`makemigrations practical_training --check --dry-run` 返回无变更。
- 最终版 `practical_training` 两次真实 PG 套件均通过：首次 **50/50 OK，14.893 秒**；补充按 backend cwd 约束复验 **50/50 OK，9.246 秒**。第二次日志首行明确记录 `/home/hatch/workspace/ctf-module5/backend`，见第 7 节。两次均使用真正的 `test_module5_r2` PostgreSQL 测试库，结束后测试库已删除。
- 5 组、每组 2 个独立 OS 进程的并发检查全部通过；每组都观察到 PostgreSQL 行锁阻塞，且父锁释放后确实发生 worker 对 worker 的锁等待。
- 本轮没有为 PostgreSQL 修改任何应用实现或共享应用。主线程完成的 `directoryListingChallenge` 修正及 0003 迁移已纳入最终验证。
- **本人启动的 PostgreSQL 已关闭**，backend cwd 补验后也已再次关闭。最新 `pg_ctl status` 返回 3 / `no server running`，55465 和 HTTP fixture 58165 均无监听；详见 `r2-pg-status-backend.log`、`r2-pg-shutdown-backend.log`。先前的停服记录 `r2-pg-final-status.log`、`r2-pg-shutdown-verified.log` 同样保留。

## 2. 环境、安装与隔离边界

- 原环境没有可用的 `postgres/initdb/pg_ctl/psql`，未发现运行中的 PG；apt 本地索引无 PostgreSQL 候选。未运行系统安装、apt update 或更改共享服务。
- 指定 venv `/home/hatch/workspace/ctf-venv` 原有 Django 6.0.3、psycopg2-binary 2.9.10；未改 venv 依赖。
- 本 worktree compose 配置为 `pgvector/pgvector:pg16`，因此本次采用 PG 16 系列，并补齐完整迁移必需的 vector 服务端扩展。
- 工具源包、独立解包目录及 out-of-tree 构建产物均在 `/home/hatch/.local/share/module5-r2-pg-20261029/`。每份下载各用独立新空目录，所写脚本不在下载目录。
- 官方 PG 包：`https://ftp.postgresql.org/pub/source/v16.13/postgresql-16.13.tar.bz2`，独立下载官方 `.sha256` 并核对一致：`dc2ddbbd245c0265a689408e3d2f2f3f9ba2da96bd19318214b313cdd9797287`。
- pgvector 包：`https://codeload.github.com/pgvector/pgvector/tar.gz/refs/tags/v0.8.1`，本次下载 SHA-256 为 `a9094dfb85ccdde3cbb295f1086d4c71a20db1d26bf1d6c39f07a7d164033eb4`；此值是下载留档摘要，不宣称另有签名验证。
- 专用运行目录：`/tmp/module5-r2-pg-20261029-1328/`；PG 以 `nobody` 执行，数据目录 `cluster/`、Unix socket 目录 `socket/` 均为专用 0700 目录。
- 仅监听 `127.0.0.1:55465`；专用数据库 `module5_r2`、账号 `r2pg`。initdb 产生的 postgres/template 数据库同样仅属于此临时集群。测试框架只额外创建、删除本集群的 `test_module5_r2`。
- 本地临时 trust 认证只用于此次回环验收，不是部署安全配置；没有更改任何共享 PG 账号或数据。
- 数据库确认 `transaction_isolation = read committed`、`fsync = on`。

### 实际遇到的问题及处理

1. 初次 tar 恢复归档中的 UID/GID 被 user namespace 拒绝；改为在新空 `source-no-owner/` 中 `tar --no-same-owner`，不更改系统权限。
2. `/home/hatch` 祖先目录显示的组 65534 是 namespace 外未映射 GID，切换 nobody 后不能遍历。未 chmod/chgrp 共享祖先目录，而是复制已编译安装树到上述新建私有 `/tmp` 运行目录；父进程预先打开本 worktree 的日志文件再重定向给 PG。
3. 第一次真实迁移停在既有 `legal_kb.0002_enable_pgvector`：`extension "vector" is not available`。未改或跳过共享迁移；真实编译 pgvector 0.8.1 到私有 PG 安装目录后重跑迁移成功。
4. 主线程通知 challenge key 修正后，最终并发 HTTP fixture 改为读取映射 key 并断言 `directoryListingChallenge`。初期缺扩展失败的日志保留为 `r2-pg-pre-key-fix-migrate.log`；**没有声称旧 key 版本曾完整通过 PG 验收**。
5. 最终 10 个并发请求均无 429/503/数据库连接错误，重试数组全部为空。下载命令配置 `--retry 5 --retry-all-errors --retry-delay 3`，并发脚本对上述可恢复状态等待后重试当前请求；本次最终结果没有依靠重试掩盖错误。

## 3. 精确命令与脚本

三个新增、独立于应用实现的文件：

- `/home/hatch/workspace/ctf-module5/backend/scripts/r2_pg_verify.sh`
- `/home/hatch/workspace/ctf-module5/backend/scripts/r2_pg_concurrency.py`
- `/home/hatch/workspace/ctf-module5/backend/scripts/r2_pg_assertions.sql`

PG 构建的实际 argv（通过 `python -I` 的 `subprocess.run(..., cwd=...)` 执行，cwd 为独立 `build/` 而非下载/解包目录；完整输出为 `r2-pg-build.log`）：

```text
/home/hatch/.local/share/module5-r2-pg-20261029/source-no-owner/postgresql-16.13/configure --prefix=/home/hatch/.local/share/module5-r2-pg-20261029/install --without-readline --without-icu
make -j4
make install
```

pgvector 构建的实际 argv（cwd 为独立 `pgvector-build/`，预先创建 `src/`、`sql/`；详见 `r2-pg-pgvector-build.log`）：

```text
make -f /home/hatch/.local/share/module5-r2-pg-20261029/pgvector-source/pgvector-0.8.1/Makefile srcdir=/home/hatch/.local/share/module5-r2-pg-20261029/pgvector-source/pgvector-0.8.1 VPATH=/home/hatch/.local/share/module5-r2-pg-20261029/pgvector-source/pgvector-0.8.1 PG_CONFIG=/tmp/module5-r2-pg-20261029-1328/install/bin/pg_config OPTFLAGS= -j4
make -f /home/hatch/.local/share/module5-r2-pg-20261029/pgvector-source/pgvector-0.8.1/Makefile srcdir=/home/hatch/.local/share/module5-r2-pg-20261029/pgvector-source/pgvector-0.8.1 VPATH=/home/hatch/.local/share/module5-r2-pg-20261029/pgvector-source/pgvector-0.8.1 PG_CONFIG=/tmp/module5-r2-pg-20261029-1328/install/bin/pg_config OPTFLAGS= install
```

首次最终版本完整验收的实际执行序列如下，命令入口 cwd 为本 worktree 根目录。该次测试 cwd 不满足随后明确的 backend 入口约束，因此另补做第 7 节的 backend cwd PG 套件复验；不把原运行冒称为 backend cwd。driver `start`/`stop` 仅操作固定的专用数据目录，使用 EXIT trap 保证失败也停服：

```bash
SCRIPT=/home/hatch/workspace/ctf-module5/backend/scripts/r2_pg_verify.sh
LOG=/home/hatch/workspace/ctf-module5/evidence/module5
bash "$SCRIPT" start
trap 'bash "$SCRIPT" stop > "$LOG/r2-pg-shutdown-final.log" 2>&1' EXIT
bash "$SCRIPT" migrate > "$LOG/r2-pg-migrate-final.log" 2>&1
bash "$SCRIPT" test > "$LOG/r2-pg-tests-final.log" 2>&1
bash "$SCRIPT" concurrency > "$LOG/r2-pg-concurrency.log" 2>&1
```

driver 的数据库环境及实际 Django 命令：

```bash
export DATABASE_BACKEND=postgres
export DATABASE_URL=postgresql://r2pg@127.0.0.1:55465/module5_r2
export DEBUG=true ALLOWED_HOSTS=localhost,127.0.0.1,testserver SECURE_SSL_REDIRECT=false
export PRACTICAL_TRAINING_ENABLED=true PRACTICAL_TRAINING_VERIFIER_IP=127.0.0.1
/home/hatch/workspace/ctf-venv/bin/python /home/hatch/workspace/ctf-module5/backend/manage.py migrate --noinput --verbosity 2
/home/hatch/workspace/ctf-venv/bin/python /home/hatch/workspace/ctf-module5/backend/manage.py showmigrations practical_training
/home/hatch/workspace/ctf-venv/bin/python /home/hatch/workspace/ctf-module5/backend/manage.py makemigrations practical_training --check --dry-run
/home/hatch/workspace/ctf-venv/bin/python /home/hatch/workspace/ctf-module5/backend/manage.py test practical_training --verbosity 2 --noinput
/home/hatch/workspace/ctf-venv/bin/python /home/hatch/workspace/ctf-module5/backend/scripts/r2_pg_concurrency.py
```

并发前仅对本专用数据库执行 `ALTER DATABASE module5_r2 SET log_statement = 'all'`；各 worker 的完整 argv 已写入 `r2-pg-concurrency.log`。测试套件会保留自身既有 HTTP/失败注入 mock；下节独立并发脚本没有替换事务、SQL、行锁或验证器实现。

为了补抓最终只读 SQL 结果，在第一次最终停服后再次短暂启动同一专用集群，执行以下命令，然后 EXIT trap 再停服（`r2-pg-sql-capture.log`、`r2-pg-shutdown-verified.log`）：

```bash
LD_LIBRARY_PATH=/tmp/module5-r2-pg-20261029-1328/install/lib \
/tmp/module5-r2-pg-20261029-1328/install/bin/psql \
  --dbname=postgresql://r2pg@127.0.0.1:55465/module5_r2 \
  -X -a -v ON_ERROR_STOP=1 \
  -f /home/hatch/workspace/ctf-module5/backend/scripts/r2_pg_assertions.sql \
  > /home/hatch/workspace/ctf-module5/evidence/module5/r2-pg-sql-results.log 2>&1
```

当前 driver 已将只读 SQL 快照作为 `concurrency` 步骤的尾部命令，后续一次性运行不用另补抓。并发 fixture 有意使用固定测试身份且不自动删数据；在当前已经写入 fixture 的数据库上重复执行该步骤前，需另行明确重建这个专用测试数据库，不可针对共享库执行清理。`all` 面向初次准备好的私有工具/新库，不负责下载构建依赖。

## 4. 双进程真实锁与幂等结果

每组通过 `subprocess.Popen` 启动两份 Python/Django 进程。它们用 APIClient 调用真实 view/service/ORM，分别建立真实 PostgreSQL 会话。APIClient 身份由 fixture 强制设置，不宣称验证了生产认证网关。

父进程先用真实 `transaction.atomic` + `LabAssignment.objects.select_for_update()` 持有行锁，直到两名 worker 的真实 `SELECT ... FOR UPDATE` 都在数据库等待；之后释放父锁，继续采样 worker 相互阻塞。查询为：

```sql
SELECT pid, application_name, state, wait_event_type, wait_event,
       pg_blocking_pids(pid) AS blockers, query
FROM pg_stat_activity
WHERE application_name LIKE %s ORDER BY pid;

SELECT pid, locktype, mode, granted, relation::regclass::text,
       transactionid::text, page, tuple
FROM pg_locks WHERE pid = ANY(%s)
ORDER BY pid, locktype, mode;
```

`r2-pg-*-locks.json` 保存全部实际 SQL、`Lock` 等待事件、阻塞 PID、granted 状态。每个 worker 的 `r2-pg-*-sql.log` 保存其真实 ORM SQL、参数和耗时。PG 服务端同时开启 `log_lock_waits=on`、`deadlock_timeout=100ms`，构成独立于脚本布尔断言的服务器侧证据。

| 并发场景 | OS PID | PG PID | 响应 | 已证实结果 |
|---|---|---|---|---|
| 挑战相同证据 key | 18231 / 18232 | 18238 / 18239 | 201 / 200 | 同 evidence/result/submission ID；只执行一次挑战状态读取 |
| 修复主张重复提交 | 18247 / 18248 | 18255 / 18256 | 201 / 200 | 同 claim/attempt/retest ID，只有一份冻结主张 |
| 主张相同 key、内容冲突 | 18260 / 18261 | 18268 / 18267 | 200 / 400 | 原内容重放成功，异内容被拒绝，无新增主张 |
| 修复核验相同证据 key | 18269 / 18270 | 18280 / 18279 | 201 / 200 | 同 evidence/result/submission ID，复测只完成一次 |
| 已提交挑战换新 key 再提交 | 18286 / 18287 | 18310 / 18311 | 400 / 400 | 两次均拒绝，不增加结果，不重读上游 |

五组等待快照数分别为 35、4、3、15、3；均观察到父锁释放后的 worker 间实际阻塞。服务器日志示例：

- `r2-pg-server.log:3647`：PG PID 18239 等待 transaction 1687 的 ShareLock 超过 100ms；`:3963` 显示 **947.417ms 后获得锁**。
- `r2-pg-server.log:8250`：PG PID 18279 等待 transaction 1705 的 ShareLock；`:8423` 显示 **506.623ms 后获得锁**。

挑战 HTTP 来源是本脚本启动的 `127.0.0.1:58165` fixture，走真实 requests/HTTP 解析，key 为 `directoryListingChallenge`。总请求数为 **2：一次未解决基线、一次解决后核验**。这只是 PG 并发归因检查，不是重新进行 Juice Shop 镜像或隔离验收。修复核验运行真实声明式策略验证器的 20 个 synthetic cases，没有 monkeypatch 验证器。

## 5. 最终数据库数量与约束

原挑战并发结束时 evidence/submission/result/fact/notice/retest 各 1。所有五组结束后，独立 psql `BEGIN READ ONLY` 再次确认：

| 项目 | 数量 / 状态 |
|---|---|
| ServerEvidence | 2：原挑战、修复各 1；均 passed |
| SubmissionSnapshot | 2；各 attempt 恰好 1 条，sequence 均为 1 |
| first_effective | 2；各 attempt 恰好 1 条 |
| VerificationResult | 2 |
| VerificationFact | 2 |
| DownstreamNotice | 2；均 sent，attempts 最小/最大均 1 |
| RepairClaim | 1 |
| RetestAssignment | 1；completed / passed |
| 重复 evidence key 分组 | 0 |
| 重复 first_effective attempt 分组 | 0 |

psql 同时查询了真实 PostgreSQL unique constraints，包括 ServerEvidence.key、result_id；RepairClaim.key、attempt_id、retest_id、evidence_id；SubmissionSnapshot 的 `(attempt_id, sequence)`、`(student_id, client_submission_id)`。SQL 原文和结果位于 `r2-pg-sql-results.log`，不是仅凭 ORM 或内存对象计数。

## 6. 证据索引与剩余边界

所有本专项交付日志均在 `/home/hatch/workspace/ctf-module5/evidence/module5/r2-pg*`：

- `r2-pg-discovery.log`、`r2-pg-installability.log`：原机服务/二进制/依赖检查。
- `r2-pg-download.log`、`r2-pg-build.log`、`r2-pg-pgvector-download.log`、`r2-pg-pgvector-build.log`：下载摘要、真实构建。
- `r2-pg-driver.log`、`r2-pg-permissions.log`、`r2-pg-userns.log`、`r2-pg-pre-key-fix-migrate.log`：初期失败及原因，未隐藏。
- `r2-pg-migrate-final.log`、`r2-pg-tests-final.log`：最终迁移与 50 项 PG 测试通过。
- `r2-pg-concurrency.log`、`r2-pg-concurrency-results.json`、`r2-pg-lock-summary.log`、各 `*-locks.json` / `*-sql.log` / `*-result.json`：并发进程、响应、真锁、数量。
- `r2-pg-server.log`、`r2-pg-sql-results.log`：PG 服务端独立证据及最终原生 SQL 快照。
- `r2-pg-code-fingerprint.log`：本次最终应用/迁移/脚本 SHA-256，便于与主线程版本对应。
- `r2-pg-shutdown-verified.log`、`r2-pg-final-status.log`：最终停服、无监听。

剩余边界：此次覆盖同 assignment 的证据重放、修复主张重放/冲突、修复核验、已提交后换 key；不扩大声称为任意跨学生/跨映射/跨入口交织均已并发验收，也不是压力/高可用/崩溃恢复测试。未重复主线程 Juice Shop、网关/身份/网络隔离、资源回收联调，也未把 HTTP fixture、合成策略测试或即时复测解释为真实场景/长期保持能力证据。

专用 PG 集群与工具文件保留在上述私有目录供主线程追查，**进程已停止，未设自动启动或定时任务**。没有本专项剩余阻塞；原交付中非 PostgreSQL 的部署与课程验收边界由主线程分别跟踪。

## 7. 补充：严格从 backend cwd 复验 PG 套件

按主线程补充要求，仅重跑同一 PG `test` 步骤，不重跑专用数据库迁移步骤或并发脚本，不更改应用代码或 driver。通过指定 venv 的 `python -I` 调用 `subprocess.run(["bash", "-c", command], cwd="/home/hatch/workspace/ctf-module5/backend")`，使启动 PG、测试及停服操作的实际 cwd 均为 backend。测试所创建的新测试库由 Django 按正常机制自动迁移，不是另跑 `migrate` 命令。

实际 shell command 内容如下，外层 stdout/stderr 保存至 `r2-pg-backend-driver.log`，整个命令退出码为 0：

```bash
set -euo pipefail
SCRIPT=/home/hatch/workspace/ctf-module5/backend/scripts/r2_pg_verify.sh
LOG=/home/hatch/workspace/ctf-module5/evidence/module5
cleanup() {
    original_status=$?
    bash "$SCRIPT" stop > "$LOG/r2-pg-shutdown-backend.log" 2>&1 || true
    status=0
    bash "$SCRIPT" status > "$LOG/r2-pg-status-backend.log" 2>&1 || status=$?
    printf "pg_ctl_status_exit=%s (3 means no server running)\n" "$status" >> "$LOG/r2-pg-status-backend.log"
    ss -ltn "( sport = :55465 or sport = :58165 )" >> "$LOG/r2-pg-status-backend.log"
    exit "$original_status"
}
pwd > "$LOG/r2-pg-tests-backend.log"
bash "$SCRIPT" start > "$LOG/r2-pg-start-backend.log" 2>&1
trap cleanup EXIT
bash "$SCRIPT" test >> "$LOG/r2-pg-tests-backend.log" 2>&1
```

已证实结果及定位：

- `/home/hatch/workspace/ctf-module5/evidence/module5/r2-pg-tests-backend.log:1`：`/home/hatch/workspace/ctf-module5/backend`，为同一 shell 运行 `pwd` 的实际输出；driver 不改变 cwd，Django 进程继承此 cwd。
- 同文件 `:2`：`Found 50 test(s).`；`:170`：`Ran 50 tests in 9.246s`；`:172`：`OK`；`:173`：删除 `test_module5_r2`。
- `/home/hatch/workspace/ctf-module5/evidence/module5/r2-pg-shutdown-backend.log`：`server stopped`、`127.0.0.1:55465 - no response`。
- `/home/hatch/workspace/ctf-module5/evidence/module5/r2-pg-status-backend.log`：`no server running`，`pg_ctl_status_exit=3`；55465/58165 的监听查询只有表头，没有监听行。

因此两次 PG 套件分别为根目录 cwd 50/50 和符合约束的 backend cwd 50/50；最终采用后者作为测试入口约束的复验证据，原迁移、并发及原生 SQL 结果不变。补验后 PG 已由 EXIT trap 关闭，没有遗留服务。
