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

## 3. pgvector / 外部模型：先做隔离评测

### 3.1 先确认供应商控制台

分别检查嵌入模型和聊天模型是否允许调用、凭据所属区域、余额 / 额度、限流。此前真实请求是通义 401、DeepSeek 401、火山 429，尚未得到真实嵌入或回答。

当前官方适配器只允许以下固定地址：

| 供应商 | 当前实现允许的地址 |
| --- | --- |
| 通义 qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| DeepSeek | `https://api.deepseek.com` |
| 火山 volcano | `https://ark.cn-beijing.volces.com/api/v3` |

本机 `.env` 的通义 BASE_URL 使用国际站地址，与当前适配器固定的国内站不同。单改 `EMBEDDING_BASE_URL` 不能切换官方适配器；联调需使用与上述接口匹配的凭据。如果必须使用国际站，需要先增加对应 endpoint 支持，再进行请求验证。

### 3.2 Windows：复用现有完整评测脚本

在仓库外建立专用文件，如 `D:/ctf-deploy/remote-eval.env`。以下占位内容必须替换；模型 ID 以控制台实际允许的模型为准：

```dotenv
EMBEDDING_PROVIDER=qwen
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024
EMBEDDING_API_KEY=<匹配国内站接口的有效通义密钥>
DEEPSEEK_API_KEY=<有效DeepSeek密钥>
DEEPSEEK_MODEL=<可调用的聊天模型ID>
```

如还要验火山聊天，可添加 `ARK_API_KEY` 和 `ARK_MODEL`。通义 `text-embedding-v3` 也是当前实现的默认候选，应按实际权限选择并验证 1024 维返回。

在当前项目根目录 PowerShell 运行：

```powershell
$env:PYTHONUTF8 = '1'
& '.state/full-audit-20261113/venv/Scripts/python.exe' backend/scripts/evaluate_remote_knowledge.py --env-file 'D:/ctf-deploy/remote-eval.env' --pg-bin 'C:/Program Files/PostgreSQL/16/bin' --workers 1 --postgres-tests --output 'artifacts/knowledge-remote-pg-retest.json'
```

这是**完整质量评测**：嵌入探针成功后会自动对约 4106 个公开片段请求嵌入，再做检索和聊天评测，会产生供应商调用用量。脚本没有 `--probe-only` 参数。先检查额度再运行；`--workers 1` 用于降低初次联调并发。

脚本只读读取现有 SQLite 知识库，建立独立临时 PostgreSQL 数据库；不覆盖业务 `.env`。正常退出时停止专用 PostgreSQL、删除临时凭据文件，并保留非秘密数据库和结果供诊断。正常退出才写入清理确认；若命令异常退出、清理字段缺失或不为 true，不能认为清理已完成，需要检查退出信息和临时目录。

**该脚本固定使用 `.exe` 程序名，不能原样搬到 Linux 执行。** 它验证隔离评测组合；并不把已成功的 provider 自动绑定到正在运行的业务进程。

打开输出 JSON，至少检查：

- qwen `status=success`，实际 `dimension=1024`。
- 所选聊天 provider `status=success`，有真实回答。
- `remote_quality_evaluated=true`，`completed=true`，没有阻断错误。
- `embedding_index.completed` 达到目标数；存在 `remote_exact`、`remote_hnsw`、`production_hybrid` 的逐查询结果。
- 有所选聊天模型的 `answers`，人工核对证据、结论和引用；范围正确的引用编号并不自动证明内容正确。
- `isolated_postgres_stopped`、`temporary_keys_deleted` 为 true。

只看到脚本退出 0、BM25 命中率高或 `remote_quality_evaluated=true`，都不足以证明全部模型和回答质量通过；该布尔值主要由嵌入探针决定。

## 4. 容器中的真实业务联调

### 4.1 先接入模型启动组合

业务代码将 `settings.EMBEDDING_API_KEY` 固定为空，provider manager 不会自动读取 `.env` 里的凭据。需要将仓库外的 bootstrap JSON、key manifest、密钥文件和批准策略挂入容器，设置 `DATA_SECURITY_CONFIG` 为**容器内绝对路径**。

当前 Compose 没有这些挂载；需要根据部署路径补 overlay。当前 bootstrap 仅支持 `environment=evaluation`，先用于独立测试环境；正式生产接入仍须处理部署支持。该部分适合由开发者制作和验证，避免人工拼凑策略、密钥引用与路径。

若采用“通义嵌入 + DeepSeek 聊天”，测试业务配置可使用：

```dotenv
EMBEDDING_PROVIDER=qwen
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024
EMBEDDING_BATCH_SIZE=10
LEGAL_KB_RAG_USE_LLM=true
LEGAL_KB_RAG_AGENT_ID=legal_reviewer
```

同时在启动组合中配置实际 DeepSeek 聊天模型。默认的 `compliance_officer` 绑定 qwen；如果 qwen 的首个允许模型是 embedding 模型，会先尝试把它用于 chat。使用绑定 DeepSeek 的 `legal_reviewer` 可以明确区分这两种用途。

### 4.2 检查数据库与单次真实请求

完成启动组合后，在独立测试部署运行：

```text
docker compose exec backend python manage.py check_legal_kb
docker compose exec postgres psql -U ctf_user -d ctf_platform -c "SELECT extversion FROM pg_extension WHERE extname='vector';"
docker compose exec backend python manage.py shell
```

`check_legal_kb` 应显示 PostgreSQL、存在 vector 扩展、远程配置启用、1024 维；该命令自身不请求模型。

在打开的 Python shell 中执行两次真实请求：

```python
from legal_kb.services.embedding_service import EmbeddingService
s = EmbeddingService()
v = s.embed_text('SQL injection prevention')
print(s.provider, s.model, len(v), s.vector_space)

import asyncio
from ai_providers import get_manager, Message
p = get_manager().get_provider('deepseek')
assert p is not None, 'DeepSeek provider 未绑定'
r = asyncio.run(p.chat([Message('user', '仅回复：连接成功')]))
print(r.provider, r.model, r.content)
```

预期得到真实 1024 维向量和真实聊天回答。这里使用项目的受保护官方 provider，适合先验证少量调用，再决定重建规模。

### 4.3 先重建一条公开法条，再看真实检索

要求测试库已有公开法条和分块，并有现有活跃管理员 / staff 账号。以下 `<...>` 是占位符，替换后再运行；`法条ID` 是 `LegalClause` 的 ID：

```text
docker compose exec backend python manage.py rebuild_legal_kb --actor <管理员用户名> --source-type legal_clause --object-id <法条ID> --dry-run
docker compose exec backend python manage.py rebuild_legal_kb --actor <管理员用户名> --source-type legal_clause --object-id <法条ID>
docker compose exec backend python manage.py check_legal_kb
```

dry-run 只校验和统计；第二条会请求模型并更新该法条索引。先对一个对象通过，再扩展为完整测试语料重建。若新 PostgreSQL 里没有知识库，先准备公开测试语料，重建命令不会替你导入源文档。

真实远程向量存放在 `embedding_vector`，字段固定 1024 维；便携 `embedding` 列仍保留 128 维字符向量。远程模型和空间应核对 `metadata.vector_model` / `metadata.vector_space`，不能仅按便携列的 `embedding_model` 判断。

再次进入 Django shell，使用可访问目标语料的测试管理员 / 教师：

```python
from django.contrib.auth import get_user_model
from legal_kb.services.retrieval_service import LegalRetrievalService
actor = get_user_model().objects.get(username='实际管理员用户名')
rows = LegalRetrievalService().retrieve(
    query='网站如何防止用户输入变成可执行的数据库语句？',
    top_k=5, user=actor)
print([(r['retrieval'], r['vector_space'], r['title']) for r in rows])
```

用适合测试语料的改写问题。返回中应有 `retrieval=semantic` 和与当前模型一致的向量空间。只有 `lexical` 说明使用词法路径，可能是向量为空、空间不同或 pgvector 分支异常。`PGVECTOR_NON_NULL>0` 只证明有向量；HNSW 索引存在也不证明小样本查询规划器一定使用它。

### 4.4 验证业务接口和人工质量

管理员 / 教师登录后，通过前端对应功能或浏览器 Network 观察 `POST /api/legal-kb/retrieve/`：

```json
{"query":"网站如何防止用户输入变成可执行的数据库语句？","top_k":5}
```

应返回真实聊天 provider / model、可追溯 citations，并且回答依据正确。如果是 `provider=local`、`model=rag-template-v1` 或出现 `provider_error=MODEL_CALL_FAILED`，不能计为外部聊天通过。该知识库管理接口限制管理员 / 教师，学生访问 403 属于当前权限设计。

用正常问题、改写问题、知识库没有答案的问题各测几条；核对引用原文支持结论，并用实际师生身份检验可见范围。正式保护模式可能不返回 raw results，检索方式可通过上面的服务层元数据验证。

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
| 有结果但只有 `lexical` | 远程向量、向量空间、数据库分支 | 开发者排查和重建 |
| 有回答但 `provider=local` | 聊天配置、模型用途、失败字段 | 开发者定位；凭据 / 额度问题由用户处理 |
| 引用编号正确但答案错误 | 对照法条 / 原文逐项评阅 | 用户或领域教师评阅，开发者据此改检索和提示 |

本说明对应的配置和代码：`docker-compose.yml`、`frontend/nginx.conf`、`backend/challenges/access.py`、`backend/challenges/frp_client_manager.py`、`backend/ctf_backend/security_bootstrap.py`、`backend/data_security/adapters/llm/official.py`、`backend/scripts/evaluate_remote_knowledge.py`、`backend/legal_kb/services/embedding_service.py`、`backend/legal_kb/services/retrieval_service.py`。

这两项联调的结果与 44 项正式私有附件测试分别记录；启动 Docker 或模型评测通过，不会自动使仍需 Linux / POSIX 权限环境的附件测试通过。
