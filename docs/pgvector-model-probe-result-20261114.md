# pgvector 与外部模型真实探针结果（2026-11-14）

以下为停用通义前的历史实测记录。通义远程嵌入已按用户要求弃置；短暂本地检索方案之后，用户确认可用的 `doubao-embedding-vision-251215`，当前选择火山文本嵌入 + DeepSeek 聊天。火山当前配置和真实返回以本轮最终探针报告为准。PostgreSQL / pgvector 结构、现有数据及业务加密密钥保留。最新操作见 [当前联调指南](pgvector-model-quickstart-20261113.md)。

停用前，本轮 PostgreSQL、pgvector 和 DeepSeek 聊天探针通过；通义 `text-embedding-v4` 返回 HTTP 400，尚未生成真实向量。外部语义召回和回答质量尚未评测。

证据文件：

- [真实探针报告](../artifacts/knowledge-remote-pg-probe.json)
- [通义请求诊断](../artifacts/knowledge-qwen-probe-diagnostic-20261114.json)

## 已取得的真实结果

| 检查项 | 本轮结果 | 可以证明的范围 |
| --- | --- | --- |
| 隔离 PostgreSQL | PostgreSQL 16.14，迁移与连接检查通过 | 隔离数据库可用 |
| pgvector | vector 扩展 0.8.2，通过 | 扩展可用；尚未取得真实通义向量 |
| 运行时保护 | `isolated=true`、`enabled=true` | 本轮启用了隔离的运行时保护 |
| DeepSeek | `deepseek-flash`，HTTP 200，真实回复“连接成功” | 该模型的本次聊天请求成功 |
| DeepSeek 用量 | `prompt_tokens=35`、`completion_tokens=3` | 本次聊天探针的返回用量 |
| 通义 | `text-embedding-v4`，HTTP 400 | 嵌入请求失败；没有生成向量 |
| 退出清理 | 临时 provider 密钥和运行时保护密钥已删除；专用 PostgreSQL 已停止 | 本轮隔离实例完成清理 |

DeepSeek 单次聊天成功不能代替业务功能或回答质量验收。由于通义嵌入探针未通过，本轮没有完成外部语义质量评测。

## 通义错误目前能确认到哪里

请求诊断显示：模型字段匹配 `text-embedding-v4`，输入为单条字符串数组，`encoding_format=float`。这些检查未发现本次请求的字段形状异常。

诊断中的 `message_hints` 对“模型”和 `access_or_permission` 为 true，其他参数、区域相关提示为 false；错误枚举仍未分类。因此目前只能称为**模型访问相关错误**，不能断言具体是模型权限、业务空间授权或区域不匹配。区域提示为 false 也不能代替控制台核对。

当时用户在北京业务空间里找不到 `text-embedding-v4`，或尚不能确定该模型是否可调用。之后用户认为该模型可能没有额度，并明确要求弃置相关部分；这不改变历史 HTTP 400 只能归为模型访问相关错误的诊断边界。

## 原通义排查计划已取消

原计划是在 [百炼控制台](https://bailian.console.aliyun.com/) 核对北京区域、API Key 所属业务空间和模型授权，并参考 [文本嵌入同步 API](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api) 后重试。这些链接与步骤只保留作历史说明，当前不再要求执行通义开通、授权、充值或向量重试。之后改用火山嵌入是用户明确选择的新方案。

## 当前下一步

沿用 [当前联调指南](pgvector-model-quickstart-20261113.md) 先验证火山 `doubao-embedding-vision-251215` 的纯文本 multimodal 嵌入和 DeepSeek 聊天。报告应分别显示 `purpose=embedding` 与 `purpose=chat`，以选中的 embedding 任务成功判断远程向量阶段；qwen 保持 `disabled`。火山实际向量必须 1024 维，探针的 `remote_quality_evaluated=false` 不能解释为质量通过。

本历史文件不构成火山成功证据。完整评测约 4106 个公开片段，当前 Vision 每片段一次请求，先检查单次探针及用量后再决定是否执行完整评测。

保留两个旧共享检索通道开关的现状。已有服务需重建或重启读取配置；业务启动组合按用途配置火山 embedding 与 DeepSeek chat，`legal_reviewer` 绑定 DeepSeek。`ARK_MODEL` 仅用于可选火山聊天，不能填写 embedding 模型。

现有 PostgreSQL / pgvector 结构、知识库数据和业务加密密钥保留，不要更改或删除旧业务 key。本轮历史探针的临时密钥清理与业务加密密钥是不同的对象。
