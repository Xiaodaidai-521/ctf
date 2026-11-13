# pgvector 与外部模型联调：北京国内站快速操作

先用少量请求确认“PostgreSQL + pgvector + 通义嵌入 + DeepSeek 聊天”都能连接，再运行完整质量评测，最后接入测试业务进程。默认采用通义 `text-embedding-v4`、1024 维；DeepSeek 聊天模型 ID 需要填写控制台实际可调用的 ID。

这份说明配套新增的 `--probe-only` 模式。它建立隔离 PostgreSQL、检查 vector 扩展，并向每个已配置供应商发送一次探针请求；跳过源 SQLite、历史语料文件、批量嵌入和质量评测。本地已验证真实隔离 PostgreSQL 迁移与 pgvector，以及缺密钥、非法配置的失败路径；使用模拟网络响应确认了各一次 embedding/chat、源 SQLite 不存在也能探针、跳过质量阶段并完成清理。编写本说明时，尚未调用真实模型。下面命令需要有效凭据执行后，才能取得真实联调结论。

## 1. 在控制台准备两份凭据

| 用途 | 当前代码调用地址 | 你需要确认 |
| --- | --- | --- |
| 通义文本嵌入 | `https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings` | 北京国内站凭据有效；`text-embedding-v4` 可调用；额度和限流允许请求 |
| DeepSeek 聊天 | `https://api.deepseek.com/chat/completions` | DeepSeek 凭据有效；所选聊天模型可调用；余额和额度可用 |

通义国际站凭据与当前固定的国内站接口可能不匹配。当前官方适配器不会通过 `EMBEDDING_BASE_URL` 切换地址。

`EMBEDDING_DIMENSION=1024` 是代码校验的目标维度。当前普通通义 embedding 请求不显式传 `dimensions`，实际返回必须确认是 1024 维；配置值不能代替这个检查，也不能把其他维度的结果直接截断入库。

## 2. 复制配置，在本地填写密钥

打开 PowerShell，逐段执行。以下命令使用当前电脑的项目路径；配置文件放在仓库外。

```powershell
Set-Location -LiteralPath 'D:\aaa10\16015478源码\project-code'
New-Item -ItemType Directory -Path 'D:\ctf-deploy' -Force | Out-Null
if (-not (Test-Path -LiteralPath 'D:\ctf-deploy\remote-eval.env')) {
    Copy-Item -LiteralPath 'D:\aaa10\16015478源码\project-code\docs\remote-eval.env.example' -Destination 'D:\ctf-deploy\remote-eval.env'
}
notepad 'D:\ctf-deploy\remote-eval.env'
```

在打开的文件里，把密钥占位符替换成各自的真实密钥，把 DeepSeek 模型占位符替换成控制台实际可调用的聊天模型 ID，保存后关闭：

```dotenv
EMBEDDING_PROVIDER=qwen
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024
EMBEDDING_API_KEY=REPLACE_WITH_BEIJING_QWEN_API_KEY
DEEPSEEK_MODEL=REPLACE_WITH_AVAILABLE_DEEPSEEK_CHAT_MODEL_ID
DEEPSEEK_API_KEY=REPLACE_WITH_DEEPSEEK_API_KEY
```

将密钥保留在本地配置文件中。反馈联调结果时提供输出 JSON 和错误类别，密钥不需要发送到聊天或提交进仓库。已有配置文件不会被上面的复制命令覆盖。

## 3. 先运行少量请求探针

```powershell
$env:PYTHONUTF8 = '1'
& 'D:\aaa10\16015478源码\project-code\.state\full-audit-20261113\venv\Scripts\python.exe' 'D:\aaa10\16015478源码\project-code\backend\scripts\evaluate_remote_knowledge.py' --env-file 'D:\ctf-deploy\remote-eval.env' --pg-bin 'C:\Program Files\PostgreSQL\16\bin' --probe-only --output 'D:\aaa10\16015478源码\project-code\artifacts\knowledge-remote-pg-probe.json'
$LASTEXITCODE
```

这个模式会创建、迁移并停止一个独立 PostgreSQL 实例，需要本机 PostgreSQL 16、pgvector 扩展和现有 Python 环境。它也会产生少量真实模型用量。配置了上面的两份密钥时，预期各发一次通义嵌入、DeepSeek 聊天请求。未配置的火山 provider 会显示 `not_configured`。

读取结果，不读取密钥文件：

```powershell
$probeReport = Get-Content -LiteralPath 'D:\aaa10\16015478源码\project-code\artifacts\knowledge-remote-pg-probe.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$probeReport | Select-Object evaluation_mode, status, completed, remote_probe_succeeded, remote_quality_evaluated, pgvector_version, isolated_postgres_stopped, temporary_keys_deleted
$probeReport.providers | Format-Table provider, model, status, dimension, finite, error_code
$probeReport.http_observations | Format-Table host, status, error_category, transport_error_type
$probeReport.errors | Format-Table type, code
```

必须同时满足以下条件，才算探针通过：

- 退出码为 `0`，`evaluation_mode=probe_only`、`status=complete_probe`、`completed=true`、`remote_probe_succeeded=true`。
- `pgvector_version` 有实际版本号。
- qwen 为 `status=success`、`dimension=1024`、`finite=true`。
- DeepSeek 为 `status=success`，其 `content` 中有真实聊天回复。DeepSeek 若为 `not_configured`，说明本次没有验证聊天，需要检查配置文件是否填写了密钥和模型。
- `errors` 为空，`isolated_postgres_stopped=true`、`temporary_keys_deleted=true`。

探针的 `remote_quality_evaluated=false` 是预期值：它只确认连接和返回格式，尚未评测语义召回或答案质量。探针成功也不会自动把 provider 绑定到正在运行的业务服务。

## 4. 探针通过后，运行完整评测

确认愿意承担完整嵌入和聊天请求的用量后再执行：

```powershell
$env:PYTHONUTF8 = '1'
& 'D:\aaa10\16015478源码\project-code\.state\full-audit-20261113\venv\Scripts\python.exe' 'D:\aaa10\16015478源码\project-code\backend\scripts\evaluate_remote_knowledge.py' --env-file 'D:\ctf-deploy\remote-eval.env' --pg-bin 'C:\Program Files\PostgreSQL\16\bin' --workers 1 --postgres-tests --output 'D:\aaa10\16015478源码\project-code\artifacts\knowledge-remote-pg-retest.json'
$LASTEXITCODE
```

完整版默认只读读取 `D:\aaa10\16015478源码\database\db.sqlite3`，复制到独立临时 PostgreSQL，依赖现有 `artifacts/knowledge-import.json` 和 `artifacts/knowledge-retrieval-evaluation.json`。根据此前语料规模，会对约 4106 个公开片段进行嵌入，再执行查询和聊天评测；实际数量由本次数据决定。`--workers 1` 降低首次并发，但不会减少语料总量。`--probe-only` 不能和 `--postgres-tests` 一起使用。

```powershell
$fullReport = Get-Content -LiteralPath 'D:\aaa10\16015478源码\project-code\artifacts\knowledge-remote-pg-retest.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$fullReport | Select-Object status, completed, remote_quality_evaluated, postgres_regressions, isolated_postgres_stopped, temporary_keys_deleted
$fullReport.providers | Format-Table provider, model, status, dimension, error_code
$fullReport.embedding_index
$fullReport.retrieval.remote_exact.metrics
$fullReport.retrieval.remote_hnsw.metrics
$fullReport.retrieval.production_hybrid.metrics
$fullReport.answers | Select-Object provider, model, question, answer, citations_in_range, keyword_check, error_code
$fullReport.errors | Format-Table type, code
```

验收要看 qwen 与 DeepSeek 实际成功、`completed=true`、`remote_quality_evaluated=true`、没有阻断错误、`embedding_index.completed` 达到 `total`，以及三条远程检索分支的逐查询结果。还要确认 DeepSeek 有真实 `answers`，并人工评阅引用和答案。退出码、质量布尔值或 BM25 命中率不能单独证明这些条件成立。

`--postgres-tests` 使用合成向量检查数据库分支和权限回归；这部分通过不能代替真实模型召回质量。脚本正常结束后删除临时凭据文件，保留隔离数据库和报告供诊断；你的源配置文件仍保存在 `D:\ctf-deploy\remote-eval.env`。本脚本使用 Windows `.exe` 工具名，不能原样搬到 Linux。

## 5. 失败时按结果排查

| 现象 | 检查与处理 | 主要由谁处理 |
| --- | --- | --- |
| Python、`initdb.exe` 等路径不存在 | 核对上面的本机路径和依赖安装 | 我可以检查环境、调整命令 |
| vector 扩展不可用或迁移失败 | 核对 PostgreSQL 16 的 pgvector 安装、扩展版本和迁移日志 | 我可以定位配置和代码问题 |
| HTTP 401 | 核对密钥是否有效、通义是否为北京国内站、所选模型是否有权限 | 你操作供应商控制台；我解读诊断 |
| HTTP 429 | 查看 `error_category`，区分限流与账户余额/额度，再调整调用并发 | 你处理账户额度；我处理调用策略 |
| `not_configured` | 检查同一配置文件是否同时填写该 provider 的密钥和模型 | 你填写凭据；我检查配置读取 |
| `EMBEDDING_NOT_CONFIGURED` | 核对 provider 装配和启动组合 | 我检查 bootstrap 与绑定 |
| `AUTHORIZATION_DENIED` | 核对固定接口、模型允许列表、策略与密钥引用 | 我定位实际拒绝位置 |
| `EMBEDDING_SHAPE_INVALID` / `REAL_EMBEDDING_PROBE_INVALID` | 核对实际返回维度、有限数值与目标 1024 维 | 我处理协议适配；你确认可用模型 |
| 只有 `PROVIDER_UNAVAILABLE` | 查看报告中的 `http_observations`，业务错误码可能统一隐藏原始 HTTP 细节 | 我解读状态与错误类别 |
| 检索仅显示 `lexical` | 检查远程向量是否写入、查询与索引的 vector space 是否一致、PG 分支是否异常 | 我定位并重建测试索引 |
| 有回答但 `provider=local`、`model=rag-template-v1` 或 `MODEL_CALL_FAILED` | 核对聊天用途、启动组合、凭据和额度 | 我处理程序；账户问题由你处理 |
| `PG_STOP_FAILED` 或清理字段缺失/不为 true | 检查报告中的隔离工作目录和专用 PostgreSQL 状态，确认清理完成 | 我可以协助核查和清理隔离实例 |

不要只根据状态码猜原因。例如 429 可能代表账户限制，也可能代表速率限制，应结合控制台和报告类别判断。

## 6. 接入测试业务进程，再验收实际功能

隔离评测成功后，业务服务还需要独立接入模型启动组合。业务 `settings.EMBEDDING_API_KEY` 固定为空，provider manager 不会自动读取 `.env` 凭据。开发者需要准备仓库外的 bootstrap JSON、key manifest、密钥文件和批准策略，挂入测试容器，设置 `DATA_SECURITY_CONFIG` 为容器内绝对路径，再启动进程。

当前 bootstrap 只接受 `environment=evaluation`，因此先接入独立测试部署。正式生产接入支持仍需开发验证。当前 Compose 也没有自动完成上述文件挂载；这部分我可以制作配置并联调，不能把隔离评测成功当成业务启动配置已经完成。

通义嵌入配 DeepSeek 聊天的测试业务配置应包含：

```dotenv
EMBEDDING_PROVIDER=qwen
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024
EMBEDDING_BATCH_SIZE=10
LEGAL_KB_RAG_USE_LLM=true
LEGAL_KB_RAG_AGENT_ID=legal_reviewer
```

`legal_reviewer` 绑定 DeepSeek。默认 `compliance_officer` 绑定 qwen；如果 qwen 仅允许 embedding 模型，默认聊天调用可能误用该模型。启动组合中的 DeepSeek 模型还必须与控制台实际可调用模型一致。

接入后先运行 `check_legal_kb`，再通过项目的 `EmbeddingService` 和受保护聊天 provider 各发一次真实请求。`check_legal_kb` 自身不请求模型，不能单独证明模型可调用。随后选择一条公开测试法条，用 `rebuild_legal_kb --actor <现有管理员用户名> --source-type legal_clause --object-id <法条ID> --dry-run` 核对，再去掉 `--dry-run` 重建；扩展重建规模前先确认单条成功。新测试库没有源法条和分块时，需要先导入公开测试语料。

真实远程向量应写入 `embedding_vector`，其维度固定为 1024；`embedding` 仍保留 128 维字符向量。核对 `metadata.vector_model`、`metadata.vector_space`，以及检索的 `retrieval=semantic`。向量数量非零、HNSW 索引存在，都不能单独证明某个请求实际走了正确语义检索。

管理员或教师可在前端相应功能的浏览器 Network 中检查 `POST /api/legal-kb/retrieve/`，例如发送：

```json
{"query":"网站如何防止用户输入变成可执行的数据库语句？","top_k":5}
```

用适合实际测试语料的问题，并验证返回的真实聊天 provider/model、答案与 citations。当前知识库管理接口限制管理员/教师；学生访问该接口 403 属于权限设计。学生端的知识访问范围还应在实际学生功能入口验证。

最后由你或领域教师评阅以下场景：

| 场景 | 通过条件 |
| --- | --- |
| 正常问题 | 召回正确证据，答案与原文一致 |
| 同义改写 | 减少原文关键词后仍召回正确材料 |
| 无答案问题 | 明确说明证据不足，不编造事实和法条 |
| 管理员、教师、学生及未登录身份 | 各身份只能访问允许范围，受限材料不越权召回 |
| 回答引用 | 引用可以追溯到原文，而且原文逐项支持结论；编号合法不等于内容正确 |

供应商开户、密钥、区域、模型权限和余额需要你实际确认；程序配置、数据库分支、模型协议、测试索引、错误处理和日志诊断可以由我处理。实际回答质量与教学适用性需要你或领域教师给出最终判断。
