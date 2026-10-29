# M3-03 原创候选素材来源台账

## 状态与责任边界

- 台账版本 / 候选来源版本：`m3-original-candidates-1`；本版本登记日期：`2026-10-29`。
- 原始素材：`backend/learning_knowledge/candidate_materials.py`，30 张原创教学候选卡。不是法规原文、外部指南译文、真实学生成果或已签署教师答案。
- 登记责任人：执行命令时显式指定的已有 `--actor` 账号。写入 `Material.owner`、`MaterialRevision.author` 和带用户名、user_id 的 `attribution_text`；这里的技术字段不代表登记人已署名创作或完成教学审核。
- 内容审核责任：数据主线教师 / 网络主线教师及独立复核人，均待实际指派、审阅；许可确认责任：项目负责人，待确认。本台账不虚填具体教师姓名或审核日期。
- 本任务只在 Django 临时测试库中使用 synthetic 用户、目录、能力与知识点关系；没有在生产、开发或其他持久数据库执行导入，没有真实导入责任人或审阅签字。
- 每次首次登记产生 `Material.created_at`、`MaterialRevision.created_at` 的真实数据库时间；`source_date` 是上面的候选版本登记日期。`verified_at` 是本地快照登记当天日期，**不是**法规现行性核验、外网核查、许可确认或教师审批日期。命令同时将这一限制写入 `change_note`。

## 来源与许可

全部卡片使用以下来源声明，不挪用其他来源的许可字段。

| 字段 | 记录与含义 |
| --- | --- |
| `source_type` | `teacher_authored`：现有系统对原创教学快照的技术分类，不表示教师已审核或署名 |
| `publisher` | 项目内部原创候选素材（待教师审核） |
| `source_version` | `m3-original-candidates-1`，与任务版本分别记录 |
| `license_id` | `LicenseRef-Project-Internal-Pending`，内部待确认标记，**不是已获许可证明** |
| `license_url` / `source_url` | 留空；本地原创素材没有已确认外部授权或原文来源地址 |
| `attribution_text` | 原创待教师审核；实际登记责任人；本地来源文件；权属和复用许可待确认；非法规原文、非 WSTG 翻译转载、不声明 CC 授权 |
| `reuse_scope` | 项目内部待确认；仅限指定课程的候选审阅，不得据此对外转载或发布 |
| `source_hash` | 每张卡 `source_snapshot` 的原样 UTF-8 字节 SHA-256；不含标题、不补换行、不做文本归一化 |
| 分块证据 | 复用现有段落解析器，保存起止位置、段落定位、标题路径和逐块 SHA-256；不生成向量索引 |

**WSTG 边界**：网络主线只参考 **OWASP WSTG v4.2**（`https://wstg.owasp.org/v4.2/`）的测试方法组织授权问题。链接是版本明确的方法参考，不是本批正文的来源地址；不翻译转载、不复制指南正文、不宣称继承其内容许可，不借 WSTG 名义宣布课程能力、任务隔离或评分标准已通过验收。本任务没有访问外网或验证该站点现状。

**数据主线边界**：只做合成案例中的事实梳理、人工复核和只读风险决策回放。不导入法规条文，不把已有依据卡的未核验引用改写成已核验法律来源；行业适用性、现行性和具体结论仍待教师确认。执行、交付、结算均未开展。

## 四个现有任务及候选映射

版本与 `learning_map/management/commands/seed_learning_map.py` 使用的 `fixtures/module1_candidate_v1.json` 对齐。已有 seed 的目录名为 `v1-candidate`，但导入命令**没有默认目录**：必须显式传入实际已有目录的 `CatalogVersion.version`。不调用 seed，不创建或迁移任务。

| 台账前缀 | 精确任务键与版本 | 卡片数 | 现有 seed 的任务目标能力 | 这些能力关联的知识点（去重展示） |
| --- | --- | ---: | --- | --- |
| `DS` | `TASK-DS-CUSTOMER-TABLE-001@1.0.0-candidate` | 12 | `DS-001, DS-002, DS-005, DS-006, DS-009` | `KP-DS-01, KP-DS-02, KP-DS-03, KP-DS-05` |
| `NS` | `TASK-NS-OBJECT-AUTH-001@0.1.0-candidate` | 12 | `NS-001, NS-004, NS-009, NS-010` | `KP-NS-01, KP-NS-03, KP-NS-05` |
| `DS-RETEST` | `TASK-DS-LOG-RETEST-001@1.0.0-candidate` | 3 | `DS-005, DS-006, DS-009` | `KP-DS-03, KP-DS-05` |
| `NS-RETEST` | `TASK-NS-RETEST-001@0.1.0-candidate` | 3 | `NS-004, NS-009, NS-010` | `KP-NS-03, KP-NS-05` |

实际登记以所选目录内上述**精确任务版本的实时关系**为准，由现有 `review.register` / `review.new_revision` 写入 `TaskMaterial.capability_ids` 和 `knowledge_point_ids`；不硬编码上表覆盖数据库，不猜测跨目录映射。任务缺失、版本不符、无能力、能力无知识点或关联跨目录时，整批拒绝。

这些是**任务级候选映射，不是逐卡教学适用性审批**。例如“最小必要”相关的 `KP-DS-04`、“认证”相关的 `KP-NS-02` 并未出现在上述主任务的目标映射中；命令不会自动扩充任务能力或知识点来掩盖这一缺口。教师须在后续正式审阅中逐卡核查、区分先修知识与目标能力并形成新修订记录。

- 两个主任务各有：5 `lesson`、4 `hint`（严格对应 1–4 级）、1 `student_analysis`、1 `teacher_answer`、1 `grading_secret`。
- 两个复测任务各只有 3 `lesson`；不导入复测提示或解析，不预填完成、通过或保持成绩。
- 总计：16 `lesson`、8 `hint`、2 `student_analysis`、2 `teacher_answer`、2 `grading_secret`。
- 新创建的 30 张全部为 `draft` / `internal`，解析为 `completed` 仅表示本地分块成功。`reviewer`、`reviewed_at`、`published_at` 均为空，不自动生成 `ReviewAction`、`HintCard` 或 `StudentAnalysis`。

## 逐卡快照登记

卡位格式为 `任务前缀/类别-同类序号`；`hint-01` 至 `hint-04` 分别为提示 1 至 4 级。每行继承上面的版本、日期、责任人规则、来源许可、适用范围和任务映射。以下是**包内候选版本**的哈希，不是导入后经教师修改的新修订哈希。

| 卡位 | 标题 | source_snapshot SHA-256 |
| --- | --- | --- |
| `DS/lesson-01` | 先区分事实与依据 | `8076aa64427b5fb101127c3eecf1b589c487150300cea92a6555a830fe4d2db9` |
| `DS/lesson-02` | 个人信息属性与数据分级分开 | `0d857a39f34a4f41855862c56f608b157f28db16026d90c83b37d8d7503654e0` |
| `DS/lesson-03` | 最小必要的检查顺序 | `6a0eb5c32655ab85a55995a1b340806a27c5ad3dfec95e30d7ead16bdf5a5c77` |
| `DS/lesson-04` | 复核规则检出 | `3a798de74730a2db87df7fd8240dbb2f01d24fe81245c6118993e023d253deeb` |
| `DS/lesson-05` | 只读演练与证据边界 | `1ecf2cd7a9aba846b1e02afab083e155b8e20a17a9eb98413cc5fa59d4408987` |
| `DS/hint-01` | 方向：先看任务事实 | `50e3309195f19c4739582d7b125afa336acde08418678207421367a7ddfd77b8` |
| `DS/hint-02` | 知识：核查适用范围 | `d77df432990f8cb80426323e39a8f483ce26b1b9a90d2d432f5a100aead4e8ac` |
| `DS/hint-03` | 线索：对照必要字段 | `85107470a01dfe0977a53e1fc6c53ee5dbdb3f9777749b5f5dd56b9d1f211722` |
| `DS/hint-04` | 步骤：组织可复核理由 | `65991512c19f9c67d5945eb0b805ef24a1b9a320ed2ff6d3671291a9fe3d0bc9` |
| `DS/student_analysis-01` | 学生复盘：数据案例方法 | `c20ad9c05d7e4c2a2451342cd4e56fda0217f5a8c405e516be94f8f4c74caaca` |
| `DS/teacher_answer-01` | 教师审阅样例：数据案例 | `4b58bb8c953a030642aba3f820d3553c9a9bdcb39c634a275aff36e21e9ff1f9` |
| `DS/grading_secret-01` | 评分维护样例：数据案例 | `5882323d14222ded6031d8a13a90ba5ff03fb11567f3856d8f65fb1842527fbe` |
| `NS/lesson-01` | 对象级授权的证据 | `97907a2fc2920345f16210bbf6c3b30c52a19e5019bbdcf4d684f6de5e191589` |
| `NS/lesson-02` | 任务范围先于测试 | `939109e579207bb136a75e1e315277be8bb58f7761d169a2fcf6fc7893aaaf2d` |
| `NS/lesson-03` | 服务端独立校验 | `65abf33183b1974bb7658256e4e886e2782dbbca1639afcc9c8d5bd1defe12fa` |
| `NS/lesson-04` | 修复验证的正负样本 | `0560af53592fc2a7933d055f2242a7ff76f418056e0db8a5ad949e537e04d34c` |
| `NS/lesson-05` | WSTG阅读边界 | `325939144993c82e3610debef1f4b2c1ae2592d15ae12d53499e2b3cc1bc46fa` |
| `NS/hint-01` | 方向：定位授权判断 | `19569be7deab27ceb466db0b09d7df941466e888625397d8f00992a6dd7e2a93` |
| `NS/hint-02` | 知识：区分认证和授权 | `70c6b0021ceaaf18d2bd478e8b675040f2b919b5c301114230894e03cf191fc2` |
| `NS/hint-03` | 线索：检查不可信对象标识 | `68410de1fd839200869e3b3a9e40f47734b9fd4750ef361c87e78db9e2b096e8` |
| `NS/hint-04` | 步骤：复验正向和拒绝路径 | `6e45cd91bd8e613e489caedc4ca9e36f8cd77fce2e16aefa742d9714ed69e74a` |
| `NS/student_analysis-01` | 学生复盘：授权案例方法 | `29bce4a61a898cfb7f5e21e262221c977b8517854a47c2ca25a1a36094cf3e88` |
| `NS/teacher_answer-01` | 教师审阅样例：授权案例 | `a2b872be1825b350067a498f03d4cbc415b38bd1cd294b15fb5285ca77a41e34` |
| `NS/grading_secret-01` | 评分维护样例：授权案例 | `6829f639bf69fd9d8f86e90b545bc7026c1405e1ee9b516c272f994122ffa3c2` |
| `DS-RETEST/lesson-01` | 新场景与原题分离 | `0ab7352a4140bef3513e00afc4881c067342cfd92bcd7f45b81853fa3dc3ef8c` |
| `DS-RETEST/lesson-02` | 无提示复测规则 | `9a700b50d55fb9b7aa839185204f07222d48a150096bf758c3cacfaea966c756` |
| `DS-RETEST/lesson-03` | 复测证据保存 | `16c03a5a5c2e865b06d6ed8dfa6e5eba7b4b5830340ba35c178fdbef3a6968a0` |
| `NS-RETEST/lesson-01` | 新场景与原题分离 | `0ab7352a4140bef3513e00afc4881c067342cfd92bcd7f45b81853fa3dc3ef8c` |
| `NS-RETEST/lesson-02` | 无提示复测规则 | `9a700b50d55fb9b7aa839185204f07222d48a150096bf758c3cacfaea966c756` |
| `NS-RETEST/lesson-03` | 复测证据保存 | `16c03a5a5c2e865b06d6ed8dfa6e5eba7b4b5830340ba35c178fdbef3a6968a0` |

复测正文复用相同原创方法说明，因此哈希相同；它们绑定不同任务，分别登记为 6 张卡，不合并跨任务身份。两张 `grading_secret` 仅含隔离测试用合成标记，不是真实 flag、密码或生产验证规则；台账不展示正文。

## 命令契约与幂等性

命令名：`import_candidate_materials`。下式仅说明参数形式，**本任务没有在测试外执行**。

```text
/home/hatch/workspace/ctf-venv/bin/python /home/hatch/workspace/ctf-module3/backend/manage.py import_candidate_materials --actor <已有用户整数主键> --catalog <已有目录version>
```

1. `--actor` 和 `--catalog` 均必填。catalog 是版本字符串，不是数据库主键；不根据“最新目录”或当前登录用户猜测。
2. 固定整批 30 张，包含评分秘密，因此 actor 必须为启用的 admin（现有 policy 也认可 superuser），并已具有所选目录中 `active=True, maintain_secrets=True` 的 `CourseGrant`。普通教师即使有 `can_review` 或 `maintain_secrets` 也不能执行整批导入；staff 身份不等于 admin。superuser 也不绕过该 grant。命令绝不创建、修改 grant。
3. 只查找上述四个任务的精确版本；不新增任务、目录、用户、能力或知识点，不改任务状态、材料引用、提示、验证器或环境开关。
4. 复用 `review.register` 与 `review.parse_candidate`。整个批次使用一个外层事务，注册、绑定、稳定 ID 安装或解析任意一步失败均原子回滚；成功前不输出计数或正文。
5. 稳定身份为 `uuid5(NAMESPACE_URL, key)`；key 是 `['m3-original-candidate', catalog.version, task_key, task.version, material_class, 同类序号]` 的紧凑 JSON（`ensure_ascii=False, separators=(',', ':')`）。不以标题、正文哈希、actor、登记时间或候选来源版本作为去重键。
6. 重复运行跳过已有身份，**不更新**任何旧修订、正文、标题、知识映射、责任人、时间、hash、分块、ingestion token、ACL、审阅动作或发布状态；不同导入人也不会接管旧素材。即使源码正文或来源版本改变，也不会绕过已有审阅而自动覆盖或新建重复素材。
7. 已登记卡位应保持同类序号稳定，不重排、不在同类旧卡之前插入。修订已有内容须通过正式审阅流程新建 revision。本命令不是刷新或修复旧材料的工具；已有身份不一致或没有 revision 时拒绝，留待人工检查。
8. 支持只有部分稳定身份已存在的场景：仅创建缺失卡，已有审阅成果保持不变。每次运行，包括全部跳过的运行，仍重查 actor 的评分维护授权与四个任务及知识映射。
9. 支持行锁的数据库按目录行锁串行化此命令；稳定 UUID 的数据库唯一约束阻止重复插入。SQLite 不提供等价行锁，应串行执行；并发冲突可整批失败后重试。本次没有验证 PostgreSQL 或多进程并发行为。
10. 默认输出只有 `created` / `skipped` 汇总和状态说明，不输出标题、正文或合成秘密。命令没有自动授权、提交、审批、发布、强制覆盖或选用其他任务版本的选项。

首次成功应报告 `created=30, skipped=0`；未变化的重复运行应报告 `created=0, skipped=30`。这里的 draft/internal 指**新创建**卡片；已有经教师审批、发布、撤回或 superseded 的记录不会被重置为草稿。后续正式审阅需遵循现有 author、独立 reviewer、实时管理权限和旧发布修订 superseded 规则；导入命令不实现也不绕过这些规则。

## 验证记录与限制

仅运行新增 `learning_knowledge.tests.test_candidates`，不改动或重跑其他测试。测试自己创建 synthetic fixture，不调用 `seed_learning_map`，也不导入持久业务数据库。

```bash
PYTHONDONTWRITEBYTECODE=1 DATABASE_BACKEND=sqlite SQLITE_DATABASE_PATH=:memory: \
  /home/hatch/workspace/ctf-venv/bin/python \
  /home/hatch/workspace/ctf-module3/backend/manage.py \
  test learning_knowledge.tests.test_candidates --verbosity 2 --noinput
```

2026-10-29 验证结果：**36 tests，6.057s，OK，退出码 0**；Django system check 为 0 issues。测试库已应用现有 `learning_knowledge.0002_materialrevision_author` 迁移。完整 stdout/stderr、实际命令、时间及退出码保存到 `artifacts/module3/m3-03-candidates.log`。覆盖显式参数、角色和维护 grant、精确任务版本、目录与知识映射、30 卡分类/提示层级/哈希/来源声明及台账一致性、草稿学生不可读、同一/不同 actor 幂等、权限失效后的重复运行、已审阅/已发布/撤回/superseded 与新修订保护、部分已有记录续导入，以及注册/末卡解析/数据库/身份冲突故障回滚。测试中的审批发布仅用于构造“既有审阅成果”并验证命令不覆写，不是导入命令的行为。

本交付只补齐候选登记；没有教师内容审核、权属许可确认、法规现行性核验、WSTG 外网核验、靶场隔离验收、生产导入、自动发布或真实学习效果验收。任务级知识映射的逐卡适用性缺口仍明确保留，不能将通过 synthetic 测试等同于课程已可上线。
