# 题目关联表设计说明

## 目标

为了让题库中“题目与题目之间的关联”更加明确、可维护、可检索，新增显式关联表 `ChallengeRelation`，用于描述：

- 哪道题是另一道题的前置题
- 哪道题是下一阶段进阶题
- 哪些题属于同一知识主题
- 哪些题使用相同攻击思路或防御思路
- 哪些题适合作为推荐延伸练习

这张表不仅用于后台管理，也已经接入知识包生成逻辑，后续多智能体在 `current` 范围回答时，可以优先读取显式维护的题目关系，而不是只依赖关键词猜测。

---

## 数据库表

表名：

`challenges_challengerelation`

对应 Django Model：

`backend/challenges/models.py` 中的 `ChallengeRelation`

---

## 表结构

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主键 |
| `source_challenge_id` | `ForeignKey -> challenges_challenge.id` | 源题目 ID |
| `target_challenge_id` | `ForeignKey -> challenges_challenge.id` | 目标题目 ID |
| `relation_type` | `CharField(30)` | 关系类型 |
| `strength` | `PositiveSmallIntegerField` | 关系强度，默认 `3` |
| `sort_order` | `PositiveIntegerField` | 排序值，默认 `0` |
| `reason` | `CharField(255)` | 关联说明，便于人工维护和展示 |
| `is_bidirectional` | `BooleanField` | 是否双向关系，默认 `False` |
| `is_active` | `BooleanField` | 是否启用，默认 `True` |
| `created_at` | `DateTimeField` | 创建时间 |
| `updated_at` | `DateTimeField` | 更新时间 |

---

## relation_type 枚举

| 值 | 含义 | 适用场景 |
| --- | --- | --- |
| `prerequisite` | 前置题 | 先做这题，再做目标题 |
| `progression` | 进阶题 | 当前题做完后，适合继续练 |
| `similar` | 相似题 | 题型或解题方式接近 |
| `same_topic` | 同主题题 | 同一知识点或同一章节 |
| `same_attack` | 同攻击面题 | 比如都围绕 SQL 注入、文件上传、XSS |
| `same_defense` | 同防御思路题 | 适合从防守视角串联 |
| `recommended` | 推荐题 | 教学路径或练习路线上的推荐题 |

---

## 约束设计

### 1. 唯一约束

避免同一种关系重复录入：

`(source_challenge_id, target_challenge_id, relation_type)` 唯一

这意味着：

- 可以同时存在多种关系
- 但同一对题目不能重复插入同一种关系

例如可以同时存在：

- `26 -> 57 prerequisite`
- `26 -> 57 same_topic`

但不能重复两条：

- `26 -> 57 prerequisite`
- `26 -> 57 prerequisite`

### 2. 自关联限制

禁止题目关联自己：

`source_challenge_id != target_challenge_id`

### 3. 索引

已建立如下索引以提升检索速度：

- `(source_challenge_id, relation_type, is_active)`
- `(target_challenge_id, relation_type, is_active)`

适合以下常见查询：

- 查询某题的所有下游关联题
- 查询某题被哪些题关联
- 按关系类型筛选推荐题
- 只读取当前生效关系

---

## 推荐使用方式

### 1. 作为知识库主关联源

当前知识包生成逻辑中，题目关联的生成顺序为：

1. 先读取 `ChallengeRelation` 的显式关系
2. 如果显式关系不足，再补充同分类/同关键词的启发式关联

这样可以保证：

- 题目之间的学习路径更清晰
- 推荐关系更稳定
- 多智能体回答时上下文更可靠

### 2. 后台维护建议

建议由出题人或教研人员维护以下几类关系：

- `prerequisite`
- `progression`
- `same_topic`
- `recommended`

这四类对题库练习路径最有价值，也最能直接提升回答质量与速度。

---

## 示例

以第 26 题 `SQL注入入门` 为例，可以考虑维护以下关系：

| 源题 | 目标题 | 关系类型 | 说明 |
| --- | --- | --- | --- |
| 26 | 57 | `prerequisite` | 先掌握基础认知，再理解注入利用 |
| 26 | 58 | `recommended` | 适合作为入门后的检测练习 |
| 26 | 52 | `progression` | 从基础注入过渡到绕过登录 |
| 26 | 51 | `progression` | 从入门继续到 UNION 查询利用 |
| 26 | 59 | `same_topic` | 同属 SQL 注入数据检索方向 |

---

## 对应 SQL 结构参考

```sql
CREATE TABLE challenges_challengerelation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_challenge_id BIGINT NOT NULL,
    target_challenge_id BIGINT NOT NULL,
    relation_type VARCHAR(30) NOT NULL,
    strength SMALLINT NOT NULL DEFAULT 3,
    sort_order INTEGER NOT NULL DEFAULT 0,
    reason VARCHAR(255) NOT NULL DEFAULT '',
    is_bidirectional BOOLEAN NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT unique_challenge_relation_type
        UNIQUE (source_challenge_id, target_challenge_id, relation_type),
    CONSTRAINT prevent_self_challenge_relation
        CHECK (source_challenge_id != target_challenge_id),
    FOREIGN KEY (source_challenge_id) REFERENCES challenges_challenge(id),
    FOREIGN KEY (target_challenge_id) REFERENCES challenges_challenge(id)
);
```

索引参考：

```sql
CREATE INDEX idx_challenge_relation_source_type_active
ON challenges_challengerelation (source_challenge_id, relation_type, is_active);

CREATE INDEX idx_challenge_relation_target_type_active
ON challenges_challengerelation (target_challenge_id, relation_type, is_active);
```

---

## 当前状态

截至 `2026-06-14`，该表已经完成：

- 模型定义
- Django Admin 注册
- 数据库迁移
- 实际建表
- 接入知识包生成逻辑

当前数据库校验结果：

- 表已存在：`True`
- 当前关系记录数：`0`

说明表结构已经可用，下一步只需要补充具体题目之间的关系数据即可。
