# 题目阅读导引改造总结

## 一、改造目标

本次改造的目标不是把资源中心和社区文章内容继续注入多智能体上下文，而是做一层更轻量的“阅读导引”：

- 保留“题目 -> 文章 / 资源”的关联能力
- 这些关联只作为导读入口展示
- 不把文章正文、资源描述注入 AI 回答上下文
- 在题目详情页和 AI 助手旁边稳定展示“推荐阅读 / 相关资源”

这样做的核心收益是：

- 不增加多智能体回答时的上下文负担
- 不拖慢现有答题响应速度
- 仍然能把学生自然导向资源中心和社区继续学习

---

## 二、方案原则

本次采用的是“导读元数据”和“AI 推理上下文”分离的结构：

- 题目详情接口返回推荐文章和推荐资源
- 前端负责展示这些推荐入口
- AI 助手只给一句导引提示，不读取相关文章正文
- 多智能体知识上下文仍然只保留题目知识、分类知识、题目关联关系

也就是说：

- 文章 / 资源参与“导学”
- 不参与“推理”

这更符合你当前“提速优先”的目标。

---

## 三、后端改动

### 1. 新增题目导引关联表

文件：

- [backend/challenges/models.py](D:/xwechat_files/wxid_0x71zojosvp622_e4a7/msg/file/2026-06/sjh2/sjh2/ctf-platform-export-20260315_184335/project-code/backend/challenges/models.py)

新增模型：

- `ChallengeArticleRelation`
- `ChallengeResourceRelation`

用途：

- 显式维护题目与社区文章之间的导引关系
- 显式维护题目与资源中心内容之间的导引关系

主要字段包括：

- `challenge`
- `article` / `resource`
- `relation_type`
- `reason`
- `sort_order`
- `is_active`
- `created_at`
- `updated_at`

当前 `relation_type` 支持：

- `recommended_reading`
- `background`
- `practice_extension`
- `official_reference`

### 2. 新增迁移

文件：

- [backend/challenges/migrations/0006_challengearticlerelation_challengeresourcerelation.py](D:/xwechat_files/wxid_0x71zojosvp622_e4a7/msg/file/2026-06/sjh2/sjh2/ctf-platform-export-20260315_184335/project-code/backend/challenges/migrations/0006_challengearticlerelation_challengeresourcerelation.py)

已执行：

```bash
python manage.py migrate challenges
```

### 3. 后台管理支持

文件：

- [backend/challenges/admin.py](D:/xwechat_files/wxid_0x71zojosvp622_e4a7/msg/file/2026-06/sjh2/sjh2/ctf-platform-export-20260315_184335/project-code/backend/challenges/admin.py)

新增后台管理项：

- `ChallengeArticleRelationAdmin`
- `ChallengeResourceRelationAdmin`

这样后续可以直接在 Django Admin 中维护题目导读关系，不需要改代码。

### 4. 题目详情接口返回导引数据

文件：

- [backend/challenges/serializers.py](D:/xwechat_files/wxid_0x71zojosvp622_e4a7/msg/file/2026-06/sjh2/sjh2/ctf-platform-export-20260315_184335/project-code/backend/challenges/serializers.py)

`ChallengeSerializer` 新增字段：

- `recommended_articles`
- `recommended_resources`

返回内容包含：

- 标题
- 摘要
- 关联类型
- 导引原因
- 前端跳转链接

---

## 四、AI 侧改动

文件：

- [backend/ai_assistant/service.py](D:/xwechat_files/wxid_0x71zojosvp622_e4a7/msg/file/2026-06/sjh2/sjh2/ctf-platform-export-20260315_184335/project-code/backend/ai_assistant/service.py)

这部分是本次提速方向里最关键的改动。

### 已做的调整

- 保留题目知识包能力
- 保留分类知识包能力
- 保留题目与题目之间的关联关系
- 去掉文章和资源进入 `knowledge_context`
- `search_simple_knowledge()` 不再把 `Article` / `Resource` 混入检索结果

### 实际效果

- `current` / `category` 范围下，AI 只看题目知识与题目关联
- 社区文章与资源中心内容只作为导读元数据存在
- 多智能体回答更聚焦，输入更短，缓存也更容易命中

这正好符合“阅读导引，不参与推理”的设计原则。

---

## 五、前端改动

### 1. 题目详情弹窗增加“拓展阅读”

文件：

- [frontend/src/components/ChallengeDetailModal.vue](D:/xwechat_files/wxid_0x71zojosvp622_e4a7/msg/file/2026-06/sjh2/sjh2/ctf-platform-export-20260315_184335/project-code/frontend/src/components/ChallengeDetailModal.vue)

新增展示区：

- `相关文章`
- `相关资源`

展示内容包括：

- 标题
- 导引原因
- 摘要或资源类别
- 跳转按钮

并且明确提示：

> 这些内容只作为导读入口展示，不会注入 AI 回答上下文。

### 2. AIAssistant 增加稳定“阅读导引提示条”

文件：

- [frontend/src/components/AIAssistant.vue](D:/xwechat_files/wxid_0x71zojosvp622_e4a7/msg/file/2026-06/sjh2/sjh2/ctf-platform-export-20260315_184335/project-code/frontend/src/components/AIAssistant.vue)

新增逻辑：

- 当 `challengeInfo.recommended_articles` 或 `challengeInfo.recommended_resources` 有内容时
- 在 AI 助手顶部固定显示一个“阅读导引”提示条

提示条作用：

- 提醒学生可去题目详情查看相关文章和资源
- 不依赖模型临时生成
- 不混入聊天消息流
- 展示稳定，不影响 AI 回答逻辑

这比让模型每次自己输出“建议阅读”更稳，也更省 token。

---

## 六、批量初始化

文件：

- [backend/challenges/management/commands/init_challenge_guidance.py](D:/xwechat_files/wxid_0x71zojosvp622_e4a7/msg/file/2026-06/sjh2/sjh2/ctf-platform-export-20260315_184335/project-code/backend/challenges/management/commands/init_challenge_guidance.py)

已执行：

```bash
python manage.py init_challenge_guidance
```

初始化结果：

- `ChallengeArticleRelation`: 26 条
- `ChallengeResourceRelation`: 43 条

已覆盖的方向包括：

- Web
- SQL 注入
- XSS
- Crypto
- Pwn
- Reverse
- Forensics

---

## 七、示例效果

以第 26 题 `SQL注入入门` 为例，题目详情接口现在可返回：

### 推荐文章

- `安全开发生命周期（SDL）`
- `防火墙规则配置与优化`

### 推荐资源

- `Web安全入门指南 - 刘老师`
- `SQL注入攻击与防御 - 张老师`

同时，多智能体当前知识检索中只保留题目本身，不再混入文章或资源正文内容。

---

## 八、验证结果

已完成验证：

```bash
python manage.py check
python manage.py migrate challenges
python manage.py init_challenge_guidance
cmd /c npm run build
```

验证结论：

- 后端检查通过
- 数据库迁移通过
- 导引关系初始化成功
- 前端构建成功

说明：

- 在 PowerShell 下直接执行 `npm run build` 会受执行策略影响
- 使用 `cmd /c npm run build` 可正常构建

---

## 九、当前结论

这次改造已经把“题目知识推理”和“文章资源导读”清晰拆开：

- AI 负责解题，不读文章正文
- 题目页负责导读，不增加推理负担
- 学生既能更快拿到回答，也能继续沿着推荐内容深入学习

如果后续还要继续提速，这个结构也更适合继续叠加：

- 最终回答缓存
- 更严格的自动范围限制
- 更小粒度的题目知识包命中
- 更高命中率的本地缓存策略

从提速与可维护性的平衡来看，这是当前比较合适的一版实现。
