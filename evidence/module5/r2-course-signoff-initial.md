# 模块五第二轮第 4 项：课程教师签收材料（待人工审核）

> **状态：候选送审包，不是签收记录，不代表课程或靶场已开放。**
> 本文仅完成材料整理、静态代码对照和核对路径编制；所有审核人、审核日期、审核结论与待办填写栏均留空。不得以文件存在、哈希一致、接口返回成功或已有测试记录代替教师判断，不得替教师填写签名。

- 文档版本：`m5-r2-course-signoff-draft-v1`；编制日期：2026-10-29（**不是审核日期**）。
- 工作区：`/home/hatch/workspace/ctf-module5`；本次仅新增本文及 `evidence/module5/r2-course*` 文件，不修改代码、`PROGRESS.md`、`DELIVERY.md`，不 commit/push。
- 依据：`DELIVERY.md` 第 6 节第 4 项；其余真实镜像、身份/网络隔离、资源回收、延迟复测及 PostgreSQL 验收依赖仍独立存在。
- 使用对象：课程负责人、网络安全教师、第二复核人；本文不是学生挑战解析。只记录目标、核验条件及材料引用，不提供完整挑战解法、目标文档路径、载荷、flag 或可直接提交的修复答案。
- 证据范围：本轮未读取业务数据库，未执行 seed、迁移、测试、任务领取、课程审核/发布或环境放行接口。种子数据结论是**新建记录时的代码默认值**，不是现有数据库事实。

## 1. 送审对象、版本及证据锚点

### 1.1 对象版本

| 对象 | 本轮可确认的源码值 | 教师须核对的运行态值 / 记录空栏 |
|---|---|---|
| Git 基点 | `dc997fee4a39f4e48da534a1d62c21c47ebee7d1`，分支 `feat/module5-practical-training` | |
| 工作树状态 | 已有未提交/未跟踪的模块五实现；不能用 Git 基点代表本次材料代码 | |
| 原挑战任务 | `M5-JUICE-DOCUMENT@1.0.0`；机密文档暴露核验；`verification` | |
| 新场景修复任务 | `M5-DOCUMENT-REPAIR@1.0.0`；新场景：资料库访问控制修复方案；`retest` | |
| 材料引用 | `module5:document-access-v1` / `module5:document-policy-lab-v1`；目前是 JSON 内的逻辑引用，不是可下载文件 URL | |
| 映射目标 | `confidentialDocumentChallenge`；`ChallengeMapping.task` 与 `repair_task` 指向模块一任务 | |
| 验证器 | 原任务 `m5-juice-confidential-v1`；修复任务 `m5-document-policy-v1`；合成测试套件 `synthetic-document-acl-v1` | |
| 外部教材参考 | OWASP WSTG `4.2`，`WSTG-ATHZ-02`，Testing for Bypassing Authorization Schema | |
| 镜像配置 | `bkimminich/juice-shop:v20.2.0@sha256:8739101ade29358abb5469ee66ae78e582c97ed0a5543a4ad102e5fa5193526b` | |
| 目录 / 能力 / 知识点 | seed 从 `--catalog` / `--capability` 选择已有网络能力；本轮未查询实际 ID、目标和先修 | |
| 运行态映射签收摘要 | 本轮未生成、未登记 `review_hash`，不能拿下方文件摘要冒充 | |

### 1.2 文件哈希与引用规则

以下路径均相对于本工作区根；行号为本次源码定位，后续版本应先比对哈希再定位。

| 文件 | SHA-256 |
|---|---|
| `backend/practical_training/curriculum.py` | `5ef17f1fc60c27eaf04ce019e574011d9ba23c57fc577b5bc1d4a911a9183d23` |
| `backend/practical_training/management/commands/seed_practical_training.py` | `5d97aeed26368fe37582eaa204be0daf761424ca2b3477f5d0fe69626dc26c0e` |
| `backend/practical_training/services.py` | `8f5e55dff3cd1418ac3e7a28df92fed21e68d8cf0ff00fbcfb8b321b079cf4fd` |
| `backend/practical_training/lifecycle.py` | `3355b06ad5280dc12ad8a8b340c99ced31d0ae9c49c88c9804b41349b83244c8` |
| `backend/practical_training/verifiers.py` | `bfe7fd0b3018ce0bab806b3737d40e3f380a4a9dba148f6de5c521f50b2f864a` |

证据文件：

1. `evidence/module5/r2-course-source-snapshot.json`：23 项依据文件的 SHA-256、编制前 Git 状态、631 项代码/登记文件保护摘要、材料字面量摘要。既有 `final-code-sha256.json` 的 25 项与本次源码一致，**只证明版本一致，不是重新运行 48 项测试**。
2. `evidence/module5/r2-course-references.json`：固定版本外部场景及许可的 URL、访问时间、HTTP 状态、原始响应 SHA-256、最小标题/许可元数据；不保存题解正文。
3. `evidence/module5/r2-course-generation-manifest.json`：本轮生成文件清单、文件摘要、静态文档检查、保护文件前后比对结果及未执行事项。清单自身不自哈希，避免递归。

材料对象另外采用 `SHA256(UTF-8(JSON(sort_keys=True, ensure_ascii=False, separators=(',', ':'))))`：

| 对象 | 字面量内容摘要（不是运行态签收摘要） |
|---|---|
| `MATERIAL` | `73fbdc88acf51b1cc3ee895c0c6ba76858579e26be91bd57cf3aa3530aefd197` |
| `HINTS` | `51465b6eee1e52c0e16685bc5e408ebea60d9a962941f09242a4af3c0fd053e5` |
| `REPAIR_MATERIAL` | `5f20b83b90f71ed10c625229dccfeeef322378aa299e6042839a6d2124aecaa3` |

`services.py:54–69` 的真实 `mapping_hash` 包含两份 `task_snapshot` 和 `challenge_key`：任务数据库 ID、任务版本、目录数据库 ID、challenge ID、标题、能力 ID/可观察目标、知识点 ID、任务先修 ID、materials、hints、acceptance、validator、retest_task_keys。它**不包含**完整外部引用正文、知识点说明、能力 dimension/source_refs、能力自身先修关系、`student_solution_ref`、目录版本文字或运行镜像字节；任务开放状态等部分字段由其它条件单独检查。故教师必须归档这些额外对象的版本和附件摘要，不能声称一个 `review_hash` 覆盖了全部课程语义或许可证。

## 2. 能力 / 知识点 / 任务映射逐项清单

逐项由真实审核人员核对；空白不是默认同意。建议结论填写“通过 / 退回 / 不适用（说明理由）”，并填入证据引用；不适用不得豁免代码硬门槛。

| ID | 待核对事项与可执行路径 | 审核人 | 日期 | 结论 / 证据引用 | 待办 |
|---|---|---|---|---|---|
| M01 | 从教师目录 GET（第 7 节）核对目录版本、两个 task ID/key/version 和 ChallengeMapping ID；两个任务同目录、不同 task_key，修复用途为 retest；原任务题池**恰好**为绑定修复任务键。对照 `services.py:78–92`。 | | | | |
| M02 | 查看 TaskPackage → capabilities → knowledge_points；逐个填写稳定 ID、名称、dimension、可观察目标及知识点关联，确认不是仅因同属 network 就绑定。本轮未指定实际能力 ID。 | | | | |
| M03 | 原任务不得绑定任何 `dimension=repair` 能力；仅观察挑战状态不足以自动证明解释能力或生产修复能力。修复任务与原任务至少共享一个能力；若要授予独立修复能力，须在修复任务另外映射并人工论证，seed 未自动增加。 | | | | |
| M04 | 对两个任务分别核对学习目标能否被本题观察证据支持；对“识别暴露 / 服务端核验 / 解释 / 修复”分开记录，不能把单一 solved 信号泛化为全部目标达成。 | | | | |
| M05 | 核对任务 `prerequisite_capabilities`、能力自身 `prerequisites` 及知识点先修；建议至少判断身份与授权、资源分类、租户/所有权的入门基础。具体 ID 和“无需先修”的理由均由教师填写，seed 没有设置任务先修。 | | | | |
| M06 | 核对 Challenge 的真实数据库 ID、配置镜像及 challenge key 的真实镜像兼容性。源代码只检查既定契约，现有 HTTP fixture 不是 v20.2.0 实测。 | | | | |
| M07 | 教师逐条打开实际 materials/hints/acceptance/validator；`has_required_parts` 只看材料引用、提示级别集合及非空字段，不审查教学质量、引用可访问性、提示唯一性或目标语义。 | | | | |
| M08 | 核对目录 published、两个任务 frozen、未撤回、环境可用、无 milestone-I 依赖。审核接口还要求正确验证器字典；这些状态不能替代课程、实例或网络验收。 | | | | |
| M09 | 核对回传事实粒度：`delivery.py:18–33` 对每个任务能力生成事实，但知识点引用取该能力排序后的**首个**知识点，不是逐知识点评分。不得把所有关联知识点写成均已验证。 | | | | |

实际映射填写表（不预填虚构 ID）：

| 任务 / 用途 | 目录版本 | task ID / version | 能力 stable_id / dimension / 目标 | 知识点 stable_id / 名称 | 任务先修 / 能力先修 | 观察证据与覆盖边界 |
|---|---|---|---|---|---|---|
| 原挑战 verification | | | | | | |
| 新场景 retest（共同能力） | | | | | | |
| 新场景 retest（如增加修复能力） | | | | | | |

## 3. WSTG 选材、原创与引用 / 许可清单

### 3.1 材料来源边界

| 材料 | 本轮认定的来源类型 | 不能扩大宣称的内容 |
|---|---|---|
| `curriculum.py:MATERIAL` 中文知识卡、`HINTS` 四张卡 | 文件头和 README 声明为本项目原创候选；是项目编写的教学措辞，引用 WSTG 编号作参考 | 不等于 OWASP 官方翻译、课程教师批准或已做全面原创性/权属审查。作者权属与对外分发许可仍由负责人确认。 |
| `REPAIR_MATERIAL`、合成资料库任务及评价清单 | 本项目候选教学设计；合成数据与声明式方案练习；本轮量表也是待审建议 | 不是 WSTG 原文题目，也不是 Juice Shop 在线修复；不应把方案量表标成 OWASP 官方评分标准。 |
| WSTG 4.2 / ATHZ-02 | 外部测试指南的固定版本场景参考；标题已从官方仓库固定版本核对 | 指南不是能力目录；一个编号不代表自动转译审核，也不代表覆盖整个授权测试章节。 |
| Juice Shop v20.2.0 | 外部软件/挑战运行载体，官方该版本软件许可为 MIT | 不把 Juice Shop 代码、素材、攻略归为本项目原创；镜像依赖/第三方素材许可不因顶层 MIT 自动核清。 |

### 3.2 固定版本引用与许可

- WSTG 场景：OWASP Web Security Testing Guide v4.2，**Testing for Bypassing Authorization Schema**，`WSTG-ATHZ-02`。官方固定版本源码：<https://github.com/OWASP/wstg/blob/v4.2/document/4-Web_Application_Security_Testing/05-Authorization_Testing/02-Testing_for_Bypassing_Authorization_Schema.md>。
- WSTG 许可：<https://github.com/OWASP/wstg/blob/v4.2/LICENSE>，Creative Commons Attribution-ShareAlike 4.0 International（CC BY-SA 4.0）。若采用受许可约束的摘录/翻译/改编，须按适用条件保留署名、来源与许可链接、说明修改，并处理相同方式共享要求；这里只列核对事项，**不代做法律或权属结论**。
- Juice Shop 软件许可：<https://github.com/juice-shop/juice-shop/blob/v20.2.0/LICENSE>，MIT 条款；版权声明为 `Copyright (c) 2014-2026 Bjoern Kimminich & the OWASP Juice Shop contributors`。分发复制件或重要部分须保留版权和许可声明；课程另用图片、教程或依赖时须另查其许可。
- 本轮 2026-10-29 的三个官方 raw 固定版本响应均为 HTTP 200，正文摘要在 `r2-course-references.json`。WSTG 旧网页入口返回 308，重定向目标抓取超时；误用的 `LICENSE.md` 返回 404，已改查 `LICENSE`。未把失败抓取记成成功。
- 本文只保留标题、编号、来源及许可概述，没有复制外部挑战操作步骤；后续教师取用任何新材料须重新建立来源表，不从当前的“原创候选”说明推导整份课件可任意再许可。

| ID | 待核对事项与可执行路径 | 审核人 | 日期 | 结论 / 证据引用 | 待办 |
|---|---|---|---|---|---|
| W01 | 打开固定 v4.2 场景，核对版本/ID/标题；明确选材仅聚焦服务端资源授权判断和未授权暴露，不声称覆盖所有水平/垂直越权场景。 | | | | |
| W02 | 在 `/admin/learning_map/wstgmapping/` 和教师目录 GET 中核对 capability、练习引用、先修 ID、difficulty、acceptance_evidence、notes；由网络教师填写转译理由，再由第二人复核。seed 不创建 WSTGMapping。 | | | | |
| W03 | 填入真实 translator、reviewer、reviewed_at 及分歧处理。模型说明要求转译/复核两方；发布代码只查部分字段存在，**不自动保证第二人独立性或课程语义**。 | | | | |
| W04 | 核对每项原创/引用/改编归属、署名、许可链接、修改说明、分发范围；`MATERIAL.source_refs` 目前只有文字编号，`REPAIR_MATERIAL` 没有 source_refs。需要新增引用时在新版本中补齐。 | | | | |
| W05 | 检查学生可见内容没有完整挑战题解、敏感文件路径、flag、可直接提交的策略答案；教学目标和实验边界可以公开，受控解析另行审核并记录曝光。 | | | | |

外部选材/转译填写栏：

| 场景版本与编号 | 采用范围 / 不采用范围 | 本地材料引用与版本 | 原创 / 摘录 / 翻译 / 改编说明 | 署名与许可处理 | 转译人 | 第二复核人 | 日期 | 分歧 / 结论 / 待办 |
|---|---|---|---|---|---|---|---|---|
| WSTG 4.2 / ATHZ-02 | | | | | | | | |

## 4. 四级提示逐条核对

定位 `curriculum.py:11–16`；以下只做语义摘要，不复制完整解题步骤。四级梯度标签是**本送审包建议**，不是代码自带评分规则。

| ID | 级别 / 当前意图 | 教师待核对内容 | 审核人 | 日期 | 结论 / 证据引用 | 待办 |
|---|---|---|---|---|---|---|
| H01 | L1：区分公开/内部资料及服务端控制 | 是否只提示观察维度，适合初学者；不泄露目标文件和解法。 | | | | |
| H02 | L2：授权应在服务端读取前实施 | 是否比 L1 多给原理、而非重复；学生能否区分导航隐藏与真实授权。 | | | | |
| H03 | L3：在个人实例观察文档入口及匿名可见性 | 是否与真实固定镜像入口、AUP 和授课目标一致；是否会诱导越界或过早透露定位。 | | | | |
| H04 | L4：聚焦文档公开暴露并重申范围 | 是否在不提供完整解法的前提下形成更强帮助；与 L3 的差异需教师实读判断，当前代码不检查递进程度。 | | | | |
| H05 | 修复任务提示适配 | **两个 seed 任务复用同一 HINTS**，其中 L3/L4 指向原挑战文档入口；并非为合成策略修复分别编写。教师须决定改写/替换并走新版本复核，不能写成两套提示已齐备。 | | | | |
| H06 | 四级提示的交付及独立性 | 在授权测试环境按第 7 节区分 request 与 display：请求不交付卡片，display 才写 shown；交付即计帮助，不依赖学生 ACK。最高实际交付级别进入帮助快照。 | | | | |
| H07 | 修复阶段与解析曝光 | 模块五 hints 入口绑定原 assignment 的 attempt；原尝试核验后拒绝继续取卡，未提供独立的修复四级提示入口。修复提示交付路径须另核对现有模块六能力；看过解析会影响独立性，不可拿本文作学生解析引用。 | | | | |

**解释独立性时应使用代码真实口径：**`skill_review/services/submissions.py:32–91` 仅统计提交前已展示记录；只有请求未展示不计有效帮助。已展示卡片通常为 assisted；解析曝光或记录缺失为 unknown。模块五适配器对既有 level=0 教师帮助保留 unknown，不编造 1–4 级。`delivery.py:70–87` 中复测流程 status=completed 表示已产出结果，可能是失败；通过但受助/未知的 outcome 也不记作独立通过。

## 5. 解释评价口径及新场景修复核对

### 5.1 代码事实与人工评价的分界

- `repairs.py:15–22` 对 explanation 仅检查字符串、去空白后非空、原字符串长度不超过 2000；**不自动评分，不判断解释正确性**。错误解释也可能伴随程序项通过。
- `handoff.py:41–52` 固定 `manual_required=False`、`manual_status=not_applicable`；不能只改任务 JSON 中 `acceptance.manual_required` 就声称已接入人工解释评分或人工合格门槛。若课程要求解释决定通过，须另提代码/流程改造，本轮不改代码。
- 修复 POST 只冻结主张；必须独立调用 repair verify 才执行固定合成请求。`RepairClaim.completed` 取决于已关联结果的 overall_status=passed，不含人工解释分数，也不要求 independence=independent。
- `verifiers.py:38–67` 检查五类主体与四类资料的 20 个固定合成判定，包含正常访问对照、跨租户/所有权边界与未知类型默认拒绝；deny-all 不能替代合格策略。本文不附完整预期矩阵或通过方案 JSON。
- 这不是执行学生任意代码、不是在线修改 Juice Shop，也不是三天/七天延迟保持实验。原挑战通过后安排的 `due_days=0` 是即时新场景复测（`evidence.py:118–119`）。
- 六项 ReviewCard 是结构化复盘记录；非空、长度校验和 completed 冻结不等于解释质量评分。

### 5.2 教师人工解释量表（待审建议，未接入自动结果）

建议逐维记录“达标 / 需补充 / 错误 / 证据不足”并附学生证据引用；**总分、权重和通过阈值留给教师确定，不预设为生产规则**。不要提供标准解法让学生照抄。

| 维度 | 可接受的核对证据 | 应指出的问题 | 审核人 | 日期 | 结论 / 证据引用 | 待办 |
|---|---|---|---|---|---|---|
| E01 成因与边界 | 能区分身份验证、授权和前端可见性，结合本次受控观察说明判断依据 | 仅复述“成功/失败”，把隐藏链接当授权，或引用实例外数据 | | | | |
| E02 事实与推断 | 明确哪些是服务端观察、哪些是学生主张/猜测，并说明证据范围 | 将自报当核验，把一个挑战状态推广到整站或所有知识点 | | | | |
| E03 修复原则 | 说明资源范围、主体边界、默认行为及为何既需拒绝越权又需保留合法访问 | 只说明全部拒绝，或仅靠前端控制；不要求在本表填写完整通过策略 | | | | |
| E04 验证解释 | 能讨论正/反对照、边界场景及失败项含义，引用独立复核记录 | 把提交方案当已复核，把固定 20 项通过当一般形式证明 | | | | |
| E05 迁移与局限 | 能说明新场景与原挑战的共同原理、差异及合成实验限制 | 声称生产补丁、镜像已改、合规认证或延迟保持已证明 | | | | |

| 解释量表版本 | 总分 / 权重（如采用） | 通过阈值（如采用） | 人工结果存放位置 | 与程序结果合并规则 / 改造依赖 | 审核人 | 日期 | 结论 | 待办 |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

### 5.3 修复任务可执行核对清单

| ID | 待核对事项与路径 | 审核人 | 日期 | 结论 / 证据引用 | 待办 |
|---|---|---|---|---|---|
| R01 | 逐读 `REPAIR_MATERIAL`，确认是不同资源场景的方案验证而非原漏洞重做；目标/先修/提示应适合此场景，不伪造更换场景的效果证据。 | | | | |
| R02 | 对照 `repair_ready`：须有原挑战可信当前通过结果，模块六所选题必须是绑定的新场景修复任务，修复任务摘要与领取快照一致。 | | | | |
| R03 | 在经批准测试环境分别观察未提交、提交未核验、核验失败/故障、核验通过四种状态；记录 claim/evidence/result/retest ID，区分 claim.completed 与 retest.status/outcome。 | | | | |
| R04 | 核对固定 20 项测试的覆盖范围与课程需求；教师私下查验证器，不将完整预期矩阵、通过方案或挑战解法复制进学生材料。 | | | | |
| R05 | 核对解释人工评价、受助状态、即时复测、六项复盘各自独立；本轮仅提供量表建议，未评分、未形成任何学生能力或课程签收结论。 | | | | |

## 6. 种子数据评审表

依据 `seed_practical_training.py:21–46`。以下“默认值”均限首次创建；重复运行通过 get_or_create **不覆盖**已有任务材料、能力或映射，stdout 的候选提示也不证明库中记录是新建草案。

| 评审项 | 原挑战 seed 默认 | 修复 seed 默认 | 需教师核对 / 缺口 | 审核人 | 日期 | 结论 | 待办 |
|---|---|---|---|---|---|---|---|
| S01 标识与用途 | `M5-JUICE-DOCUMENT@1.0.0`，verification | `M5-DOCUMENT-REPAIR@1.0.0`，retest | 核对真实 ID、目录、版本唯一性；已有同键同版本不覆盖 | | | | |
| S02 执行与开放 | network / isolated_challenge / draft / environment_available=false | 同左 | 默认不能领取，不等于已冻结或有环境；两者均绑定同一导入 Challenge，不说明修复真的在该容器打补丁 | | | | |
| S03 能力与知识点 | 新建时绑定命令所选 network 能力 | 新建时绑定同一能力 | 不创建目录/能力/知识点；不检查所选能力的教学适配；若所选维度为 repair，后续原任务映射校验会拒绝 | | | | |
| S04 目标 / 先修 | 目标通过已有能力解析；不设置任务先修 | 同左 | 不能把“未填任务先修”写成教师确认无先修；实际知识点/目标未在本轮查库 | | | | |
| S05 材料 / 引用 | MATERIAL，含 WSTG 编号 | REPAIR_MATERIAL，无 source_refs | 逻辑引用与展示内容、来源/许可须可追溯；没有自动生成 WSTGMapping | | | | |
| S06 四级提示 | HINTS L1–L4 | 同一 HINTS L1–L4 | 修复提示未独立适配；四级齐全只是结构条件，不是质量通过 | | | | |
| S07 验证器 | server_verifier / m5-juice-confidential-v1 | server_verifier / m5-document-policy-v1 | 与固定服务端适配器对应；模块六通用学生提交不因此自动接通 | | | | |
| S08 验收语义 | 服务端绑定证据；manual_required=false；隔离未确认 | 同左，scope 明确仅方案重执行 | 解释不自动评分；不得用材料签收替代真实环境验收 | | | | |
| S09 题池 | 仅 M5-DOCUMENT-REPAIR | 空列表 | 原题池必须与绑定任务一致；教师核对修复任务与共同能力的衔接 | | | | |
| S10 学生解析引用 | 未设置 student_solution_ref | 未设置 student_solution_ref | 模块一开放能力的完整任务包检查涉及解析引用；不能把本文填为学生解析，不在本轮补全题解 | | | | |
| S11 签收 / 环境 | 不设置 reviewed_by/at/ref/hash；不生成实例 | 映射共同受审；不生成实例 | 模型默认 paused=false 不代表放行；未审核、草案和环境关闭门槛仍有效 | | | | |
| S12 幂等 / 新版本 | 固定创建版本 1.0.0；重复保留原值 | 同左 | 换 `--capability` 不会改旧记录；任务已属其它目录会报错。命令无 `--version`，新版本须受控人工建版，不能重跑 seed 冒充更新 | | | | |

## 7. 教师核对、冻结、发布与变更重审流程

以下是**以后由具有权限的人员在指定环境执行的步骤**，本轮未执行；不提供可直接假签收/假放行的脚本。占位符必须由教师填写真实值，空白表单不得作为 `review_ref` 的已签附件。

### 7.1 只读盘点及人工评审

1. 固定待审代码/材料包，保留本轮三份证据，先比对文件哈希。由教师确认目标服务地址、课程目录、账号权限；不要默认本机数据库就是目标课程。
2. 以课程教师账号登录，调用：
   - `GET /api/learning-map/teacher/catalog/?version=<实际目录版本>`：读取能力、知识点 ID、目标、先修、WSTG 转译和 `readiness.missing`。
   - `GET /api/learning-map/delivery-register/?version=<实际目录版本>`：检查所需交付条目及附件，不能用本文代替其它交付项。
   - `GET /api/practical-training/mappings/`：找到 mapping ID / task IDs。这里的 `reviewed` 仅为 `bool(reviewed_at)`，**不会校验当前内容哈希**，不能据此判定仍有效。
3. 在 Django 管理后台 `/admin/learning_map/taskpackage/`、`capability/`、`knowledgepoint/`、`wstgmapping/`（均在 `/admin/learning_map/` 下）打开原始字段；使用管理后台另需 staff/模型权限，普通 teacher 角色不自动拥有后台权限。只查看，不先改为 frozen/reviewed。模块五未提供完整映射管理后台，运行摘要可由授权管理员按下方只读方法导出。
4. 教师完成第 2–6 节逐项审核，将真实目录/任务快照、许可清单、人工签署附件存入课程受控证据位置。建议附件名称用 `evidence/module5/r2-course-teacher-<版本>-<日期>.*`；本轮不创建这些假附件。

授权管理员只读获取运行摘要示例（在此 worktree 根运行；**教师准备真实环境后才执行，本轮未执行**）：

```sh
M5_MAPPING_ID='<实际数字ID>' /home/hatch/workspace/ctf-venv/bin/python \
  /home/hatch/workspace/ctf-module5/backend/manage.py shell -c '
import json, os
from practical_training.models import ChallengeMapping
from practical_training.services import mapping_hash, task_snapshot
m = ChallengeMapping.objects.select_related("task__catalog", "repair_task__catalog").get(pk=int(os.environ["M5_MAPPING_ID"]))
print(json.dumps({
    "mapping_id": m.pk, "challenge_key": m.challenge_key,
    "catalog_version": m.task.catalog.version,
    "task_key": m.task.task_key, "repair_task_key": m.repair_task.task_key,
    "paused": m.paused, "reviewed_by_id": m.reviewed_by_id,
    "reviewed_at": str(m.reviewed_at) if m.reviewed_at else None,
    "review_ref": m.review_ref, "stored_review_hash": m.review_hash,
    "current_mapping_hash": mapping_hash(m),
    "task": task_snapshot(m.task), "repair_task": task_snapshot(m.repair_task)
}, ensure_ascii=False, sort_keys=True, indent=2))'
```

该命令不保存对象、不计算教师结论；输出仍不覆盖第 1 节列明的摘要外字段，需单独归档。不要把可能带有学生/受控材料的导出公开。查询已有 assignments 的 API 可能触发到期状态补偿，不属于本轮只读盘点方式。

### 7.2 任务冻结、目录发布、映射签收登记的先后顺序

1. **保持关闭**：候选任务维持 draft，真实实训开关保持关闭；需要维护已有映射时，教师先 `POST /api/practical-training/mappings/<id>/control/`，body 为 `{"action":"pause","reason":"<真实维护原因>"}`。暂停不等于物理断网，已有实例安全由运维处理。
2. **先人工审材料**：完成上述清单，修复缺项，形成真实签署附件。`review_mapping` 会验证两个任务开放条件，因此不能靠对 draft 调 review 来完成冻结，也不能先随意置 true 绕门槛。
3. **冻结任务包**：由有权限管理员在模块一 TaskPackage 后台保存审核过的版本与附件引用，再将两个任务设为 frozen。当前没有单独的 task freeze REST API；目录 freeze API 不会替每个任务冻结。学生解析引用必须另有受控材料、展示时机和曝光规则，本文不提供完整解析。
4. **核对目录门槛**：通过教师目录 GET / delivery-register GET 重查 readiness。若目录是 candidate，由管理员真实完成交付项、已冻结完整任务、网络 WSTG 复核及诊断题等要求后，依次调用 `POST /api/learning-map/admin/catalog/<version>/freeze/` 和 `POST .../publish/`。仅 candidate 可 freeze，仅 frozen 可 publish；不得直接在目录后台改 status 冒充通过门槛。目录发布会弃用其它已发布目录，须先做课程影响确认。
5. **已有 published 目录也须检查**：seed 复用已有目录不等于新增任务已经审过。若仅新增受控任务版本，仍重新核对完整性并存档；若能力含义、知识点/先修、WSTG 转译或目录规则改变，建立新目录版本并走完整流程，不覆盖旧目录语义。
6. **环境可用标记必须属实**：模块五 review 要求两个任务 `is_recommendable`，其中包括 environment_available=true；未获得真实环境准备依据就保持 false 并等待，不能把它设 true 来试审核。课程材料的人工评审附件可先完成，但运行态登记暂不能越过此门槛。逐实例 approve、总开关及网络/身份验收仍是另三类检查，任何一项不能互相替代。
7. **由教师本人登记映射审核**：条件确实齐备后，教师账号调用 `POST /api/practical-training/mappings/<id>/review/`，仅提交 `{"review_ref":"<真实已签材料的受控引用，1–255字符>"}`。服务端自行写审核账号、时间和当前内容哈希，校验失败则事务回滚；客户端不填写 reviewed_by/at/hash。保存响应的 mapping_id/review_hash、真实审核附件版本及审计引用。
8. **显式恢复及正式开放另行批准**：暂停映射可审核，但 review 不自动 resume。教师检查摘要和全部环境依赖后，才可显式 control resume。未完成 DELIVERY 第 6 节真实镜像/网络/资源依赖，不对学生开放；本材料不授权修改开关、创建实例或伪填环境 checks=true。

### 7.3 获准测试环境中的核对路径（待执行，不含解题操作）

- 通过模块一 task claim 获取本人 attempt，再经 mapping claim 绑定 AUP 和已验收个人实例；start 必须先读到干净的未解出基线才交付入口。不得用 fixture 的状态变化声称已完成真实挑战。
- 提示：对原 assignment 请求 `POST .../hints/`（level 1–4），记录 record_id / shown=false；再调用 `POST .../hints/<record_id>/display/` 获取卡片，核对 AssistanceRecord.shown / shown_at 及后续 assistance_snapshot。四级分别核对内容，避免提前展示使独立性统计失真。
- 原挑战核验：仅调用授权 assignment 的 verify，保存最小证据引用与来源/版本；自报不作成绩。失败/故障不改写为通过，首次有效提交不能覆盖。
- 新场景：原挑战可信通过后，从 repair GET 取当前材料；由测试者独立提交 explanation 与合法结构的 policy，再单独 repair verify。仅记结果/引用，不把测试者策略全文或完整挑战解法复制到本包。
- 核对人工解释结果与程序结果分列；跟踪复测 outcome 的 assisted/unknown 与六项复盘，不将流程完成误记为独立能力通过。可定位 `tests.MappingTests`、`tests.RepairTests`、`test_lifecycle.LifecycleTests` 及 `test_acceptance.AcceptanceTests` 中相关测试作为代码证据，**本轮未重跑**。

### 7.4 材料变更、撤回与重新审核

1. 教师先暂停映射并登记真实原因；涉及安全事件须另行隔离/回收实例，平台 pause 不能证明旧直连地址已不可达。
2. 记录变更前映射 ID、任务/目录版本、review_ref、stored/current hash、受影响 assignment/attempt 清单；保持旧尝试、首提交、ServerEvidence、模块六结果、事实和旧快照，不回填或覆盖。
3. 比对 materials/hints/目标/先修/验收/验证器/修复场景/引用许可等差异。既有签收摘要外字段（如解析引用、知识点说明、能力维度或外部引用内容）变化也需人工重审，不能等 hash 自动发现。
4. 已冻结/已领取材料发生实质变化时，受控新建 TaskPackage 版本及必要的新 ChallengeMapping；如涉及稳定 ID 含义则新建目录版本。seed 固定 1.0.0，不支持靠重跑自动升版；不要覆盖旧任务行再期待老 assignment 可以继续。
5. 重新审核受影响及关联项目，包括原挑战/修复任务共同能力和四级提示、WSTG 转译、解释量表、许可证与环境兼容性。生成新来源/材料/签收附件摘要，由真实教师按 7.2 登记 review，再显式决定 resume。
6. 代码会在领取/活动检查中比对映射摘要和任务快照，修复阶段还比对 `repair_task_hash`。材料变化后即使重审成功，也不能让不匹配的旧 assignment 继续；新学习使用新尝试/新分配，旧证据只保留查询与复盘，不以重审覆盖历史。
7. 如果只是暂停后的同版核对且未改材料、快照与环境仍一致，可由教师重新 review 后显式 resume；这只是控制流程可行性，**不等于已执行任何一次签收**。

## 8. 尚待补齐的缺口与人工签收空栏

### 8.1 本轮发现的待决事项（不是教师结论）

1. 未查实际目录/能力/知识点/任务数据库，具体目标、先修、WSTG 转译人与复核人、任务及映射审核状态均待教师实核。
2. seed 两题同用原挑战 HINTS；修复题需要教师确认或重做提示梯度，且模块五没有独立修复提示交付入口。
3. seed 未设置 student_solution_ref，也未创建 WSTGMapping；逻辑材料引用没有独立发布附件和分发许可结论。本包禁止补充完整题解，受控解析需单独安排。
4. 解释仅保存不评分，固定适配器不执行人工门槛。若课程要求“解释合格才通过”，当前实现存在流程/代码缺口；不能在签收文档中自行写成已实现。
5. 单个 mapping review_hash 不涵盖全部课程语义/外部材料；需补存目录、能力、知识点、解析引用、许可与外部附件版本摘要。
6. 真实镜像/API、实例隔离/资源/清理、延迟保持和目标数据库并发等依赖仍待专门验收；本轮没有新增运行通过证据。

### 8.2 教师最终填写（全部留空）

| 审核范围 | 审核人（本人填写） | 日期（本人填写） | 结论（本人填写） | 待办 / 负责人 / 截止时间 | 已签附件引用 / 版本 / 哈希 |
|---|---|---|---|---|---|
| 能力 / 知识点 / 先修 / 目标映射 | | | | | |
| WSTG 选材与转译（转译人） | | | | | |
| WSTG 选材与转译（第二复核人） | | | | | |
| 原创 / 引用 / 许可与分发范围 | | | | | |
| 原挑战四级提示 | | | | | |
| 新场景修复材料及四级提示 | | | | | |
| 解释评价量表及结果使用方式 | | | | | |
| 种子数据与运行态版本核对 | | | | | |
| 课程负责人汇总结论 | | | | | |

| 运行态登记项 | 由真实操作人员填写 |
|---|---|
| 目标服务 / 目录版本 / mapping ID | |
| 原任务及修复任务 ID / key / version | |
| 教师签署附件 review_ref | |
| 服务端 reviewed_by / reviewed_at / review_hash | |
| 目录冻结 / 发布操作与证据 | |
| 映射 pause / review / resume 操作与审计引用 | |
| 环境开放的独立验收引用（非本文代办） | |
| 未通过事项处置与复审时间 | |

## 9. 可追加到 PROGRESS 的真实结果（本轮未修改 PROGRESS）

> 第二轮第 4 项已新增待审教师材料 `docs/module5-r2-course-signoff.md`，整理映射、WSTG/许可、四级提示、解释评价、新场景修复和 seed 逐项核对表，以及冻结/发布/材料变更重审路径。证据为 `evidence/module5/r2-course*`。本轮仅做静态源码与引用核对，未调用业务审核/发布接口、未读写业务数据库、未执行测试；教师签收、课程开放及真实环境验收仍未完成。已明确两题共用提示、缺少 seed 解析引用/WSTG 转译记录、解释不自动评分和摘要覆盖边界等待决项。未修改代码、PROGRESS/DELIVERY，未 commit/push。
