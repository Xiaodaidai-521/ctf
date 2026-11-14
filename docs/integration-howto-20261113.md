# Docker / FRP 与 pgvector / 外部模型联调操作说明

适用当前项目，核查日期：2026-11-13。建议先在独立测试环境操作。

初次核查时：`docker version` 只有 Client，连接 `dockerDesktopLinuxEngine` 失败；PostgreSQL 16、pgvector 扩展文件、`.state/full-audit-20261113/venv/Scripts/python.exe` 均存在。

后续本地排障已生成仓库外的测试文件，并向项目 `.env` 添加：

```dotenv
TLS_CERT_DIR=D:/ctf-deploy/local-test/tls
FRPS_CONFIG_FILE=D:/ctf-deploy/local-test/frp/frps.ini
ALLOWED_ORIGINS=https://localhost,https://127.0.0.1
```

已核验证书与私钥匹配、localhost / 127.0.0.1 / ::1 域名覆盖、Windows 原生私有 ACL；使用真实文件路径运行 `docker compose config --quiet` 已通过。原 `.env` 的私有备份位于 `D:/ctf-deploy/local-test/env-before-local-test.backup`。测试证书有效至 2027-02-11，不代表正式部署证书；系统证书信任库未修改。Windows Hypervisor 已确认启用；请求启动 Docker Desktop 后，引擎仍未就绪。最新日志显示 `Docker/run/dockerInference` 运行文件无法清理，以及 WSL 错误 `0x80070422`；实际 `WSLService` 为 Stopped / Disabled。恢复服务需要管理员权限，本轮没有启用服务或创建容器。

对此本机状态，应先退出 Docker Desktop，再由当前 Windows 用户在管理员 PowerShell 中执行：

```powershell
Set-Service -Name WSLService -StartupType Manual
Start-Service -Name WSLService
cd 'D:\aaa10\16015478源码\project-code'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\repair-docker-runtime.ps1
docker version
```

现有修复脚本会检查并保留旧运行目录，再启动 Docker Desktop；若脚本遇到拒绝访问或其他报错，需要按实际输出继续诊断。只有 `docker version` 出现 Server 后，才继续 `docker compose up -d --build`。

## 1. Docker：先让平台和普通靶场跑通

### 1.1 启动 Linux 容器引擎

本机使用旧版 eNSP / VirtualBox，先保存拓扑并正常停止设备，退出 eNSP / VirtualBox。若仍处于关闭 Windows Hypervisor 的模式，在**管理员 PowerShell**执行：

```powershell
bcdedit.exe /set hypervisorlaunchtype auto
```

确认成功后重启 Windows，再启动 Docker Desktop。涉及设备加密的机器先按 [现有切换说明](virtualbox-docker-switching.md) 保存启动配置并确认恢复密钥可取得。

在普通 PowerShell 检查：

```powershell
docker version
docker info --format '{{.OSType}}'
```

通过标准：同时显示 Client 和 Server，操作系统输出 `linux`。若 Hypervisor 已启用但仍报 `engine.sock`，应按切换说明的故障分支诊断 Docker Desktop；继续切换 Hypervisor 不能解决独立的 socket 故障。

Linux 测试服务器直接使用已安装的 Docker Engine 与 Compose v2，执行同样的检查即可。

### 1.2 准备实际挂载文件、域名和 `.env`

以下是**本机 HTTPS 测试示例**；把路径换成实际路径。Linux 上使用 `/etc/ctf-platform/...` 等服务器绝对路径。

```dotenv
DEBUG=False
ALLOWED_HOSTS=platform.test,localhost,127.0.0.1
ALLOWED_ORIGINS=https://platform.test
CONTAINER_PROXY_HOST=platform.test
TLS_CERT_DIR=D:/ctf-deploy/tls
FRPS_CONFIG_FILE=D:/ctf-deploy/frp/frps.ini
DOCKER_NETWORK=ctf-challenge
```

原有 `SECRET_KEY`、`DB_PASSWORD` 等必填项也要有有效值。`ALLOWED_HOSTS` 不带协议；`ALLOWED_ORIGINS` 带 `https://`。当前 Compose 已设置 `CONTAINER_PROXY_MODE=network` 和 HTTPS Cookie。

- TLS 目录中必须有 `server.crt` 和 `server.key`，证书须覆盖实际访问的域名。测试 CA / 自签证书应加入测试浏览器信任；正式部署使用实际域名的有效证书。
- 本机测试可在管理员编辑的 `C:/Windows/System32/drivers/etc/hosts` 添加 `127.0.0.1 platform.test`，随后访问 `https://platform.test/`。
- `FRPS_CONFIG_FILE` 指向仓库外的真实文件。仓库的 `frp/frps.ini` 是模板，其中环境占位符没有通过当前 Compose 注入，不能直接作为部署文件。

仅用于**同宿主机 Docker 内网准备**的 FRPS 0.52.3 配置结构如下。先在仓库外把三项占位内容替换成独立随机凭据，限制文件读取权限；它不包含可用的默认凭据：

```ini
[common]
bind_addr = 0.0.0.0
bind_port = 7000
token = <独立随机FRP令牌>
vhost_http_port = 9123
subdomain_host = ctf.local
dashboard_addr = 127.0.0.1
dashboard_port = 7500
dashboard_user = <管理账号>
dashboard_pwd = <独立管理密码>
log_file = /dev/null
log_level = warn
```

`bind_addr=0.0.0.0` 指的是容器内监听；当前 Compose 没有向宿主机发布 FRPS 端口。dashboard 保持容器内 loopback，上述配置不提供跨容器 dashboard API 验收。以后若确有管理 API 需求，再按控制网络和认证方式调整。`subdomain_host=ctf.local` 是未来 frpc 子域名路由的后缀，与平台入口 `platform.test` 分别配置；使用子域名路由时还需配置对应 DNS / hosts。

### 1.3 启动并检查三条基础连接

在项目根目录执行；PowerShell 和 Linux Shell 都可运行以下 Docker 命令：

```text
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail 100 backend frontend frp-server docker-socket-proxy
docker compose exec frontend nginx -t
docker compose exec backend python /app/healthcheck.py
docker compose exec backend python -c "import docker; print(docker.from_env().ping())"
```

通过标准：服务持续运行；backend / postgres / frontend 变为 healthy；Nginx 配置检查成功；后端健康探针退出 0；Docker SDK ping 返回 `True`。`config --quiet` 只检查配置展开，不能证明证书有效、容器启动成功。

注意当前 Compose 使用 PostgreSQL，现有本地 SQLite 的账号与知识库**不会自动迁入**。应准备测试账号和测试语料；平台数据为空并不代表数据库连接失败。

当前平台端口只绑定 `127.0.0.1:80/443`。在 Linux 服务器上，远程电脑直接访问服务器 IP 会失败，需要实验网 / VPN 入口、SSH 转发，或按实际拓扑调整端口绑定。不要把环回地址当作对学生开放的访问地址。

### 1.4 用两名学生账号验证普通靶场

在两个不同浏览器会话中登录测试学生 A、B，进入题目矩阵，启动同一条配置了有效镜像和服务端口的普通题：

1. 两人分别得到不同的 `/challenge/<用户ID>-<容器UUID>/`。
2. A 能访问自己的页面，页面及 JS / CSS 请求成功。
3. B 访问 A 的实例被拒绝；已登录的越权访问应为 403。
4. A 停止实例后原地址失效，实际 Docker 容器删除；再次启动得到新实例。
5. 到期回收同样删除实例，清理服务持续运行。

辅助检查：

```text
docker network inspect ctf-challenge
docker compose exec backend python manage.py cleanup_containers --dry-run
docker compose logs --tail 50 container-cleanup
```

网络中应有后端和运行中的普通靶场。当前普通代理没有 WebSocket 桥接；课程若需要 WebSocket，需要补实现并单独验证。Nginx 的 Upgrade 请求头不能证明这条链路支持 WebSocket。

Juice Shop 使用独立网络和宿主机端口，操作步骤见 [Juice Shop Linux 部署](juice-shop-linux.md)。其默认绑定也是 loopback，远程学生测试需要填写实验网 IP / 主机名；不能把它与普通题的路径代理混为同一项验证。

## 2. FRP：当前项目还需要代码接入

当前普通题实际链路为：浏览器 → Nginx → Django → Docker 内网题目容器。`frp_client_manager.py` 和 `container_manager.py` 都明确禁用旧 FRP sidecar。

当前没有通过设置 `CONTAINER_PROXY_MODE=frp` 启用 FRP 的开关；代码只区分宿主机端口与内网代理。

因此 `frp-server` 成功启动，只能证明 FRPS 服务启动，**不能计为真实 FRP 转发通过**。当前没有自动启动的 frpc，也没有完整的跨主机入口。

如果需求只是同机 Docker 部署，先完成第 1 节即可。如果要求真正的跨主机 FRP，需要先确定 FRPS 在哪台机器、frpc 在哪台机器、最终域名、协议与可开放端口，然后补客户端、受控凭据挂载、代理注册、入口转发和生命周期清理。补好后按下面顺序验收：

1. frpc 到 FRPS 控制端口可连接并通过认证。
2. 代理注册成功，指定域名 / 端口请求到达目标测试服务。
3. 平台创建实例时注册正确路由，停止与到期时清理路由。
4. 学生从真实客户端访问，继续验证鉴权、账号隔离、静态资源和所需 WebSocket。

共享 Compose `ctf-control` 网络的容器之间使用服务名 `frp-server:7000`；同宿主机的其他网络容器不一定能解析或连接该服务名。跨主机需要真实可达地址和明确的端口发布。原 `FRPConfigManager` 中的旧 API 更新逻辑也不能直接当作 FRPS 0.52.3 的动态配置接口。

## 3. pgvector / 外部模型：火山文本嵌入 + DeepSeek 聊天

2026-11-14 更新：通义 `text-embedding-v4` 保持弃置，原通义开通、充值及重试步骤已取消。用户确认 `doubao-embedding-vision-251215` 可用后，当前选择火山文本嵌入 + DeepSeek 聊天；实际配置与返回以本轮最终探针报告为准。完整命令见 [最新联调指南](pgvector-model-quickstart-20261113.md)，通义失败证据保留在 [历史探针记录](pgvector-model-probe-result-20261114.md)。

### 3.1 按用途配置模型

```dotenv
EMBEDDING_PROVIDER=volcano
EMBEDDING_MODEL=doubao-embedding-vision-251215
EMBEDDING_DIMENSION=1024
EMBEDDING_API_KEY=REPLACE_WITH_ARK_EMBEDDING_API_KEY
LEGAL_KB_RAG_USE_LLM=true
LEGAL_KB_RAG_AGENT_ID=legal_reviewer
```

`EMBEDDING_API_KEY` 填火山方舟密钥，DeepSeek 凭据和聊天模型保留。`ARK_MODEL` 仅用于可选火山聊天，不要填入 embedding 模型。两个旧 `SEMANTIC` 检索通道开关保持现状，默认 true，使学生和代理继续使用共享知识库。

Vision 当前对纯文本调用 `POST https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal`，输入为 `[{"type":"text","text":"..."}]`，显式发送 `dimensions=1024`，每个文本请求返回一个向量。实际返回须检查 1024 维及有限数值。

保留 PostgreSQL / pgvector 结构、现有知识库数据和业务加密密钥。128 维本地字符向量仍可保存作便携数据，不能称为语义模型或代替火山新向量空间。

### 3.2 先探针，再决定完整评测

先用 `--probe-only` 检查隔离 PostgreSQL / pgvector、一次火山 embedding 和一次 DeepSeek chat。报告通过 `purpose=embedding` / `purpose=chat` 区分用途；远程向量阶段按选中的 embedding 任务成功判断。volcano 配置下 qwen 保持 `disabled`。探针不批量嵌入、不做质量评测，`remote_quality_evaluated=false` 是预期值，不能据此宣称召回与回答质量通过。

完整版会对约 4106 个公开片段生成向量，当前 Vision 每片段一次 API 请求，还要查询嵌入与聊天评测。`--workers 1` 降低并发，不减少总请求数。完整命令只作下一步参考；先确认探针和用量再执行。`--postgres-tests` 的合成向量检查仅验证数据库分支，不能与 `--probe-only` 同用。

脚本使用 Windows `.exe` 工具名，不能原样搬到 Linux。正常结束后核对专用 PostgreSQL 已停止、临时 provider 与保护密钥已删除；源配置和现有业务加密密钥保留。

## 4. 容器中的真实业务联调

### 4.1 业务模型仍需独立启动组合

隔离探针成功不会自动绑定运行中的 provider，`.env` 也不会自行装配业务模型凭据。启动组合应按用途配置火山 embedding 与 DeepSeek chat，需要仓库外 bootstrap JSON、key manifest、密钥文件和批准策略，并将 `DATA_SECURITY_CONFIG` 设为容器内绝对路径。当前 bootstrap 只支持 `environment=evaluation`，先接入独立测试环境；正式生产支持仍须开发验证。

`LEGAL_KB_RAG_AGENT_ID=legal_reviewer` 绑定 DeepSeek。嵌入模型不能当作聊天模型；可选火山聊天应另外配置实际聊天模型 ID。

已有 backend / worker 要重建容器或重启进程读取环境。Compose 环境文件修改后应重新创建相关容器，只重启旧容器不能保证新配置载入。settings、EmbeddingService 和 provider manager 不会自动刷新。

### 4.2 单次验证与测试索引

在完成启动组合的独立测试部署检查 `check_legal_kb`，再通过项目 `EmbeddingService` 做一次真实火山文本嵌入，核对 provider 为 volcano、模型为 `doubao-embedding-vision-251215`、实际 1024 维；通过受保护 DeepSeek provider 独立做一次聊天请求。详细 shell 代码见最新指南。`check_legal_kb` 自身不请求模型，不能单独证明可调用。

真实远程向量存放在 `embedding_vector`；核对 `metadata.vector_model` 与 `metadata.vector_space=volcano/doubao-embedding-vision-251215/1024/raw-v1`。先选一条已有公开法条 `dry-run`，再仅重建该测试对象，确认成功后决定规模。不要用旧通义、未知空间或本地字符向量冒充新语义索引，也无需清空整个知识库。

### 4.3 业务接口与人工质量

管理员 / 教师在实际功能入口检查 `POST /api/legal-kb/retrieve/`。应有与火山新空间一致的语义召回证据、真实 DeepSeek provider/model 和可追溯 citations。仅有 `lexical` 时检查当前空间的远程索引、查询和 PostgreSQL 分支。`provider=local`、`model=rag-template-v1` 或 `provider_error=MODEL_CALL_FAILED` 不算外部聊天通过。

该管理接口限制管理员 / 教师，学生访问 403 属于当前设计；学生知识库通道在实际学生功能入口另验。分别测正常问题、同义改写、无答案问题和不同身份权限，人工核对引用原文是否支持每项结论。向量非空、HNSW 索引存在和引用编号合法，都不能单独证明实际召回与回答质量。

## 5. 常见阻断的归属

| 现象 | 先查哪里 | 通常需要谁处理 |
| --- | --- | --- |
| Docker 只有 Client | Hypervisor / WSL2 / Docker Desktop | 用户交互式启动、管理员操作或 Linux 主机准备 |
| Compose 缺 TLS / FRPS 路径 | 实际文件、路径、证书域名 | 用户提供部署材料；开发者校验配置 |
| FRPS 启动但题目没走 FRP | 当前 frpc sidecar 禁用、拓扑缺失 | 开发者补接入；用户提供网络方案并做远程访问 |
| `EMBEDDING_NOT_CONFIGURED` / provider 为 None | 启动组合和容器挂载 | 开发者配置与修复 |
| HTTP 401 | 凭据是否有效、区域是否匹配、模型权限 | 用户供应商控制台操作 |
| HTTP 429 | 限流、余额 / 额度、账户限制 | 用户供应商控制台；开发者调整调用并发 |
| `AUTHORIZATION_DENIED` | 官方地址、模型允许列表、保护策略 | 开发者检查实际拒绝原因 |
| `EMBEDDING_SHAPE_INVALID` | 实际返回维度与索引维度 | 开发者处理适配；用户确认模型选择 |
| 结果仅有 `lexical` | 火山当前向量空间的索引、查询和数据库分支 | 开发者排查；词法结果不能计为语义通过 |
| 有回答但 `provider=local` | 聊天配置、模型用途、失败字段 | 开发者定位；凭据 / 额度问题由用户处理 |
| 引用编号正确但答案错误 | 对照法条 / 原文逐项评阅 | 用户或领域教师评阅，开发者据此改检索和提示 |

本说明对应的配置和代码：`docker-compose.yml`、`frontend/nginx.conf`、`backend/challenges/access.py`、`backend/challenges/frp_client_manager.py`、`backend/ctf_backend/security_bootstrap.py`、`backend/data_security/adapters/llm/official.py`、`backend/scripts/evaluate_remote_knowledge.py`、`backend/legal_kb/services/embedding_service.py`、`backend/legal_kb/services/retrieval_service.py`。

这两项联调的结果与 44 项正式私有附件测试分别记录；启动 Docker 或模型评测通过，不会自动使仍需 Linux / POSIX 权限环境的附件测试通过。
