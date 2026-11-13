# pgvector 与外部模型联调：火山文本嵌入 + DeepSeek（2026-11-14 更新）

当前选择火山 `doubao-embedding-vision-251215` 为知识库生成文本向量，DeepSeek 负责聊天与基于引用生成回答。通义 `text-embedding-v4` 保持弃置，旧通义开通和充值步骤已取消。下面是当前方案的目标配置，实际配置是否生效、模型是否成功，以本轮最终探针报告为准。

本轮已实际通过单次探测：[火山 + DeepSeek 探测报告](../artifacts/knowledge-ark-deepseek-probe-20261114.json) 中两家均返回 HTTP 200。火山返回一个 1024 维有限数值向量，DeepSeek 真实回复“连接成功”；qwen 为 disabled。隔离 PostgreSQL 和临时密钥已清理，退出码为 0。此结果仅证明连接与向量格式，尚未评测语料召回和回答引用质量。

先运行单次探针，再决定完整评测规模。本指南提供完整评测命令，没有执行完整评测。保留 PostgreSQL / pgvector 数据库结构、现有知识库数据及业务加密密钥。

## 1. 分清嵌入模型和聊天模型

| 用途 | 配置 | 接口 |
| --- | --- | --- |
| 火山文本嵌入 | `EMBEDDING_PROVIDER=volcano`、`EMBEDDING_MODEL=doubao-embedding-vision-251215`、`EMBEDDING_DIMENSION=1024` | `POST https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal` |
| DeepSeek 聊天 | 保留 `DEEPSEEK_MODEL` 与 `DEEPSEEK_API_KEY` | `POST https://api.deepseek.com/chat/completions` |
| 可选火山聊天 | `ARK_MODEL` 填实际可调用的火山聊天模型，配 `ARK_API_KEY` | 火山 `/chat/completions` |

`EMBEDDING_API_KEY` 应填写火山方舟密钥，可以使用已有且允许调用该嵌入模型的方舟密钥。它不再填写通义密钥。`ARK_MODEL` 仅用于可选火山聊天，**不要把 `doubao-embedding-vision-251215` 填入 `ARK_MODEL`**；只做火山嵌入时无需新增火山聊天配置。

同时配置火山聊天和嵌入时，该评测组合使用同一个火山 provider 密钥；`EMBEDDING_API_KEY` 与 `ARK_API_KEY` 若同时填写，应为同一密钥。

模型名称含 vision，本轮输入为纯文本。当前适配器发出的文本请求形状是：

```json
{"model":"doubao-embedding-vision-251215","input":[{"type":"text","text":"SQL injection prevention"}],"dimensions":1024,"encoding_format":"float"}
```

每个文本请求返回一个向量，代码明确请求并校验 1024 维，还需验证数值有限。模型名可用或 HTTP 200 不能代替返回维度检查。

## 2. 核对本地配置

项目 `.env` 与仓库外 `D:\ctf-deploy\remote-eval.env` 应采用：

```dotenv
EMBEDDING_PROVIDER=volcano
EMBEDDING_MODEL=doubao-embedding-vision-251215
EMBEDDING_DIMENSION=1024
EMBEDDING_API_KEY=REPLACE_WITH_ARK_EMBEDDING_API_KEY
DEEPSEEK_MODEL=REPLACE_WITH_AVAILABLE_DEEPSEEK_CHAT_MODEL_ID
DEEPSEEK_API_KEY=REPLACE_WITH_DEEPSEEK_API_KEY
LEGAL_KB_RAG_USE_LLM=true
LEGAL_KB_RAG_AGENT_ID=legal_reviewer
```

占位符只用于说明。现有已填写配置由开发者按本轮最终验证更新，密钥保留在本地；不要覆盖用户已经填写好的文件，也不要把密钥发送到聊天或提交到仓库。

新环境可复制模板，目标文件存在时保留：

```powershell
Set-Location -LiteralPath 'D:\aaa10\16015478源码\project-code'
New-Item -ItemType Directory -Path 'D:\ctf-deploy' -Force | Out-Null
if (-not (Test-Path -LiteralPath 'D:\ctf-deploy\remote-eval.env')) {
    Copy-Item -LiteralPath 'D:\aaa10\16015478源码\project-code\docs\remote-eval.env.example' -Destination 'D:\ctf-deploy\remote-eval.env'
}
notepad 'D:\ctf-deploy\remote-eval.env'
```

两个旧检索通道开关 `KNOWLEDGE_RAG_SEMANTIC_ENABLED`、`AGENT_RUNTIME_SEMANTIC_RETRIEVAL` 保持现状，默认 true，让学生与代理继续使用共享知识库。实际结果是语义还是 BM25，应核对响应的 `retrieval` 与 `vector_space`。

## 3. 先运行火山嵌入与 DeepSeek 聊天探针

```powershell
$env:PYTHONUTF8 = '1'
& 'D:\aaa10\16015478源码\project-code\.state\full-audit-20261113\venv\Scripts\python.exe' 'D:\aaa10\16015478源码\project-code\backend\scripts\evaluate_remote_knowledge.py' --env-file 'D:\ctf-deploy\remote-eval.env' --pg-bin 'C:\Program Files\PostgreSQL\16\bin' --probe-only --output 'D:\aaa10\16015478源码\project-code\artifacts\knowledge-ark-deepseek-probe-20261114.json'
$LASTEXITCODE
```

探针建立、迁移并停止隔离 PostgreSQL，检查 pgvector，并分别执行选中的 embedding 和已配置 chat 任务。当前方案应包含一次火山文本嵌入和一次 DeepSeek 聊天；额外配置火山聊天时还有独立聊天探针。`--probe-only` 不读取源 SQLite、不批量嵌入语料，不评测召回或答案质量。

```powershell
$probeReport = Get-Content -LiteralPath 'D:\aaa10\16015478源码\project-code\artifacts\knowledge-ark-deepseek-probe-20261114.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$probeReport | Select-Object evaluation_mode, status, completed, embedding_disabled, remote_embedding_status, remote_probe_succeeded, remote_quality_evaluated, remote_quality_status, pgvector_version, isolated_postgres_stopped, temporary_keys_deleted, temporary_runtime_key_deleted
$probeReport.providers | Format-Table provider, purpose, model, status, dimension, finite, error_code
$probeReport.http_observations | Format-Table host, status, error_category, transport_error_type
$probeReport.errors | Format-Table type, code
```

通过条件：

- 退出码 0，`evaluation_mode=probe_only`、`status=complete_probe`、`completed=true`、`remote_probe_succeeded=true`。
- `embedding_disabled=false`，选中的 `provider=volcano`、`purpose=embedding`、模型为 `doubao-embedding-vision-251215`，`status=success`、`dimension=1024`、`finite=true`。
- `provider=deepseek`、`purpose=chat`、`status=success`，有真实聊天回复。可选火山聊天与火山嵌入是不同任务，不能用聊天成功代替嵌入成功。
- 在 volcano 配置下 qwen 为 `status=disabled`，没有通义请求。远程向量阶段以选中的 embedding 任务成功判定，不再要求 qwen 成功。
- `remote_quality_evaluated=false` 是探针的预期值。只通过探针不能证明语义召回和回答质量。
- `pgvector_version` 有实际版本号，`errors` 为空；`isolated_postgres_stopped`、`temporary_keys_deleted`、`temporary_runtime_key_deleted` 均为 true。

新输出文件保留此前通义失败证据。临时凭据与保护密钥会在正常退出时清理，源评测配置和业务加密密钥保留。本脚本使用 Windows `.exe` 工具名，不能原样搬到 Linux。

## 4. 完整评测会产生大量火山请求

下面命令留作探针成功后的下一步，先确认供应商余额和限流、愿意承担用量，再执行：

```powershell
$env:PYTHONUTF8 = '1'
& 'D:\aaa10\16015478源码\project-code\.state\full-audit-20261113\venv\Scripts\python.exe' 'D:\aaa10\16015478源码\project-code\backend\scripts\evaluate_remote_knowledge.py' --env-file 'D:\ctf-deploy\remote-eval.env' --pg-bin 'C:\Program Files\PostgreSQL\16\bin' --workers 1 --postgres-tests --output 'D:\aaa10\16015478源码\project-code\artifacts\knowledge-ark-pg-evaluation-20261114.json'
$LASTEXITCODE
```

完整版只读复制 `D:\aaa10\16015478源码\database\db.sqlite3` 到隔离 PostgreSQL，依赖现有 `artifacts/knowledge-import.json` 和 `artifacts/knowledge-retrieval-evaluation.json`。此前公开语料约 4106 个片段；Vision 当前每片段单独发一次 API 请求，所以首次完整嵌入可能产生约 4106 次请求，此外还有查询嵌入和聊天评测。实际新嵌入数量以本轮报告为准。`--workers 1` 降低并发，不能减少总请求数。

验收需同时检查选中 embedding 与 DeepSeek chat 的成功状态、`embedding_index.completed` 达到 `total`、实际 1024 维，以及 `remote_exact`、`remote_hnsw`、`production_hybrid` 的逐查询证据。还要有真实 DeepSeek `answers`，人工核对引用与结论；退出 0 或 `remote_quality_evaluated=true` 不能单独证明聊天和回答质量。

`--postgres-tests` 的合成向量回归仅证明数据库分支，不能替代真实模型质量评测；它不能与 `--probe-only` 同用。

## 5. 业务启动组合与索引接入

隔离探针不会自动绑定正在运行的业务 provider。业务 `.env` 也不会自行装配模型凭据，仍需仓库外 bootstrap JSON、key manifest、密钥文件和批准策略，设置 `DATA_SECURITY_CONFIG` 为进程内可访问的绝对路径。当前 bootstrap 只支持 `environment=evaluation`，先用于独立测试部署，正式生产支持仍须开发验证。

启动组合应按用途配置火山 embedding 模型和 DeepSeek chat 模型。`LEGAL_KB_RAG_AGENT_ID=legal_reviewer` 绑定 DeepSeek；嵌入模型不能当作聊天模型。可选火山聊天必须另填实际聊天模型 ID。

已有 backend / worker 要重新创建容器或重启进程读取新环境。Compose 环境文件修改后应重新创建相关容器；仅重启旧容器不能保证载入新环境。settings、EmbeddingService 和 provider manager 不会自动刷新。

完成启动组合后，在独立测试部署进入 `python manage.py shell`，各做一次真实请求：

```python
from legal_kb.services.embedding_service import EmbeddingService
s = EmbeddingService()
v = s.embed_text('SQL injection prevention')
assert s.provider == 'volcano' and s.uses_remote_provider
assert s.model == 'doubao-embedding-vision-251215' and len(v) == 1024
print(s.model, len(v), s.vector_space)

import asyncio
from ai_providers import get_manager, Message
p = get_manager().get_provider('deepseek')
assert p is not None, 'DeepSeek provider 未绑定'
r = asyncio.run(p.chat([Message('user', '仅回复：连接成功')]))
print(r.provider, r.model, r.content)
```

真实远程向量存放在 `embedding_vector`，固定 1024 维；`embedding` 仍保留 128 维字符向量，该字符向量不是语义模型。核对 `metadata.vector_model` 和 `metadata.vector_space=volcano/doubao-embedding-vision-251215/1024/raw-v1`。历史向量和本地字符向量不能充当这个新空间的语义索引。

先在测试库选择一条已有公开法条及现有管理员，用 `rebuild_legal_kb --actor <管理员用户名> --source-type legal_clause --object-id <法条ID> --dry-run` 核对，再去掉 `--dry-run` 重建该对象。第二条会请求火山并更新目标索引，先确认小样本成功再决定扩大规模。新测试库没有源正文和分块时，应先准备公开测试材料。

随后检查 `POST /api/legal-kb/retrieve/`：应有真实 DeepSeek provider/model、可追溯 citations，以及与新空间一致的语义召回证据。仅见 `lexical` 时检查匹配空间的远程向量、查询和数据库分支；词法结果本身不能计为语义通过。向量数量非零、HNSW 索引存在或引用编号合法，都不能单独证明这条链路通过。

## 6. 人工验收与失败排查

| 场景 | 通过条件 |
| --- | --- |
| 正常问题 | 召回正确材料，DeepSeek 回答与原文一致 |
| 同义改写 | 减少原文关键词后仍召回正确证据，并检查实际语义模式和新向量空间 |
| 无答案问题 | 明确说明证据不足，不编造事实或法条 |
| 各用户身份 | 管理员、教师、学生及未登录身份只能访问允许范围；学生访问知识库管理接口 403 属于当前设计，学生功能另行验证 |
| 回答引用 | 引用可追溯，原文支持每项结论；编号合法不等于内容正确 |

| 现象 | 检查与处理 |
| --- | --- |
| 火山 embedding 未配置或模型错误 | 检查 EMBEDDING 配置、方舟密钥和用途；不要把 embedding 模型填入 ARK_MODEL |
| 火山 / DeepSeek HTTP 401、429 | 核对所选模型的密钥、访问权限、余额和限流；结合报告类别判断 |
| `EMBEDDING_SHAPE_INVALID` | 检查实际返回是否 1024 维及有限数值，不能截断入库 |
| 仍出现 qwen 请求 | 检查当前进程配置与启动组合，通义应保持 disabled |
| `MODEL_CALL_FAILED` / 本地模板回答 | 核对 DeepSeek 独立聊天任务、业务 bootstrap 与实际错误类别 |
| 清理字段缺失或不为 true | 核查专用 PostgreSQL 和临时目录；保留现有业务加密密钥 |

程序配置、数据库分支、模型适配、索引和日志诊断可以由我处理；供应商账户操作、实际回答与教学适用性的评阅，需要你或领域教师确认。
