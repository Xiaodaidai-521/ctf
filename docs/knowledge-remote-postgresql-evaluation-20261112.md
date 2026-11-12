# 远程模型与 PostgreSQL 实测（2026-11-12）

PostgreSQL 的语料检索评测通过；远程供应商均未成功返回嵌入或回答，因此远程语义召回、HNSW 质量、回答准确性和引用一致性目前没有可评分的真实结果。

## 实测范围与结果

使用原始评测的 21 个问题及既定文档/法条标签，每个问题分别运行不筛选和按来源筛选，共 42 次。没有修改标签。业务 SQLite 以只读连接访问，仅复制知识库到本机临时 PostgreSQL，不导入真实用户凭据或调整生产配置。

源数据库：`D:\aaa10\16015478源码\database\db.sqlite3`。隔离数据库使用 PostgreSQL 16.14、pgvector 0.8.2，共 4205 个片段，其中新合并的公开 OWASP/法规片段为 4106 个。远程向量列为空；原存量是本地字符向量。以下检索指标属于 PostgreSQL 上的 BM25 词法路径。

| 项目 | 实测结果 |
| --- | --- |
| 前五条命中 | 42/42，100% |
| MRR@5 | 0.8429，与此前同批 SQLite 结果一致 |
| 查询中位耗时 | 254.7 ms |
| 查询 P95 | 308.8 ms |
| 无答案探针 | 4/4 返回空 |
| 内部文档权限 | 管理员/教师有结果，学生/匿名均为 0 |
| PostgreSQL 回归 | 14/14 通过，包含 2 项 pgvector 最近邻/权限测试 |

耗时为本次单机诊断样本，包含首次词法特征构建，不包含远程嵌入延迟，也不是并发负载性能评估。pgvector 回归使用合成向量，仅证明数据库分支和权限行为，不能充当远程模型或 HNSW 召回质量证据。

## 真实远程探针

请求经项目 `ProviderHandle → OfficialAI → 保护/审计 → 官方接口` 发出，使用已有配置的真实凭据。未使用裸 SDK、代理替换、合成返回或本地降级冒充远程成功。三轮正式接入后的探针均未成功，最终一轮结果如下。

| 模型 | 官方接口响应 | 结论 |
| --- | --- | --- |
| 通义 `text-embedding-v4`，目标 1024 维 | HTTP 401，错误类别为鉴权凭据无效 | 无真实嵌入，无法建立语义评测索引 |
| 火山 `doubao-seed-2-0-pro-260215` | HTTP 429 | 服务拒绝本次请求；现有证据不能进一步区分账户限制、额度或限流 |
| DeepSeek `deepseek-v4-pro` | HTTP 401 | 鉴权失败，没有真实回答 |

不带凭据的官方域名连接检查能完成 DNS、TLS 和 HTTP，因此没有证据表明这次失败源于网络不可达。401 仍需提供有效且有相应模型权限的凭据；429 需要检查供应商控制台的账户限制、额度与限流。此次没有更换供应商、伪造审批或修改业务 `.env`。

## 原因及逐点处理

| 原因 | 已完成处理 | 剩余事项 |
| --- | --- | --- |
| `.env` 写了模型名，但没有正式启动配置，进程的 provider manager 为空 | 用现有批准策略创建明确的隔离评测组合，真实请求已到达官方接口；保留 `EMBEDDING_NOT_CONFIGURED` 原始诊断 | 业务远程接入需配置有效的正式启动组合 |
| 密钥加载器依赖 `os.getuid()` 和 POSIX 权限，在 Windows 上不可用 | 增加 Windows 原生所有者/DACL 检查；拒绝其他用户允许项、继承/NULL DACL、重解析点及 ACL 读取失败；Linux 原规则保留 | 无 |
| 文件策略模块无条件导入 `fcntl`，Windows 不能启动只读策略 | 允许只读策略在 Windows 加载；无法使用 `fcntl` 的写入仍返回拒绝 | 此次不实现 Windows 策略写入或其他安全模块的完整平台迁移 |
| Windows `pg_ctl` 的子进程持有管道输出句柄，评测启动等待不结束 | 启动命令输出改用临时日志文件，并确保退出时停止专用 cluster | 无 |
| 调用者传递回归测试隐式依赖远程默认配置，在 PostgreSQL 下被鉴权问题干扰 | 该组排序/权限测试显式使用本地向量配置；真实供应商可用性由单独探针评测 | 14 项 PostgreSQL 回归已复测通过 |
| 真实远程凭据/供应商状态不满足调用条件 | 保留 HTTP 状态和固定错误类别证据，无凭据及供应商原始错误正文输出 | 需要有效凭据及可用火山账户后再跑远程质量阶段 |
| 存量没有真实 1024 维远程索引 | 脚本已实现对相同公开片段批量建索引，并比较精确向量、HNSW 与当前混合检索及基于检索的回答 | 远程探针通过后才运行；本轮实际远程向量数为 0 |

## 验证与已知测试缺口

Windows 原生 ACL 的 5 项正/负例通过，包括私有路径允许、其他用户可读拒绝、未保护 DACL 拒绝、NULL DACL 拒绝、原生 ACL 读取失败拒绝。真实 PostgreSQL 的 14 项回归通过。

额外扩大到 `python manage.py test legal_kb data_security.tests.test_windows_private_keys` 时，112 项执行结果存在 8 个失败、10 个错误、2 个跳过，不能宣称整个知识库测试套件通过。失败集中在既有 `tests_indexing`、`tests_platform_chunking` 和 `tests_write_permissions`：前两者引用当前实现及 Git HEAD 均不存在的 `EmbeddingUnavailableError`；写权限测试使用当前实现不支持的 `EMBEDDING_PROVIDER='local'` 和旧写入/命令契约。此次没有为使旧测试通过而放开远程失败降级或写权限边界。原始失败日志保留，需按当前安全写入架构另行迁移这些测试。

沿用上一轮明确的检索回归测试集合，并加入本轮 ACL 测试进行复测：179 项中 176 项通过、3 项跳过。结果见 `artifacts/knowledge-remote-pg-curated-tests.log`。

## 复现与证据

在项目根目录运行：

```powershell
$env:PYTHONUTF8='1'
python backend/scripts/evaluate_remote_knowledge.py --postgres-tests
```

更新有效凭据后，可通过 `--env-file <本地配置文件路径>` 使用单独的评测配置；脚本不会覆盖业务配置。评测先执行真实嵌入和聊天探针，成功后才将公开语料发往模型。远程不可用时仍完成 PostgreSQL 词法、无答案和权限评测，明确输出 `remote_quality_evaluated=false`。脚本的运行完成不代表远程质量通过。

最终逐查询证据：[knowledge-remote-pg-final.json](../artifacts/knowledge-remote-pg-final.json)。首次失败、诊断和修正前回归证据分别为 `knowledge-remote-pg-evaluation.json`、`knowledge-remote-pg-diagnosis.json`、`knowledge-remote-pg-verification.json`。脚本：[evaluate_remote_knowledge.py](../backend/scripts/evaluate_remote_knowledge.py)。

各次隔离 PostgreSQL 已停止，临时密钥文件已删除。远程准确率、真实 ANN 与混合检索命中率、回答引用和 token 用量仍待有效凭据评测，不以此前本地 100% 命中率代替。

后续删除两个已停止的临时 cluster 目录时，自动审批返回 `blocked by policy`；未执行删除。临时数据库目录仍保留，密钥文件已在评测退出流程中删除。
