# 后端业务检查与修复记录

日期：2026-11-13（Asia/Shanghai）。全部动态检查使用本轮独立 PostgreSQL 16 / pgvector 集群与合成账号、合成题库；未修改真实业务数据库或启用正式发布开关。

## 检查证据

- 修复前：`backend-feature-before.log` / `.json`，21 个新回归测试，1 个通过，22 条断言失败与22条异常（一个测试内的多组参数分别计入失败/异常）。这些用例覆盖已实证的 HTTP 500、越权与伪造结果。
- 第一批修复后：`backend-feature-after.log` / `.json`，26 个回归全部通过。
- 扩大相关应用检查：`backend-feature-final.log` / `.json`，66 个测试；其中9个失败来自旧阶段证据文件的 Linux 绝对路径，本机缺少对应历史文件；另发现的实验核验缺模块和已满足前置条件的 LOCKED 模块未解锁已继续修复。
- 第二批修复后：`backend-feature-confirmed.log` / `.json`，33 个回归全部通过。
- 最终回归：`backend-feature-complete.log` / `.json`，36 个回归全部通过，新增服务器时限、考试限次和管理员角色测试。
- 最后复核补合法管理员读取草稿考试；定向检查首次复用仍在销毁的测试库而产生数据库创建/销毁碰撞（`backend-role-check.log`，未执行测试断言），随后换独立测试库重跑（`backend-role-confirmed.log`）。该碰撞是检查编排错误，未影响业务数据。
- 修改文件 `git diff --check` 通过。
- 项目全量构建、全部应用测试、部署、页面浏览器检查由主检查任务另行汇总，本文不把这36个定向测试当作全项目通过。

## 已自主修复

| 范围 | 原问题与结果 | 主要代码 |
| --- | --- | --- |
| 社区文章 | 匿名及普通用户传 `status=pending/rejected` 能查看他人未审核全文；统一先按公开/本人/管理员划定范围，查询状态无法扩大权限。作者能读取并编辑自己的待审核稿件。 | `backend/articles/views.py` 的 `visible_articles/get_queryset` |
| 社区个人页 | 匿名访问“我的文章/收藏”导致异常，作者“我的文章”漏掉待审/拒绝记录；个人列表强制登录，正确读取本人各状态。 | `ArticleViewSet.get_permissions/my/my_favorites` |
| 评论 | 可修改他人评论、把评论搬到其他文章、通过收藏/评论读取撤回稿件，或评论他人未发布文章；补作者权限、锁定文章/父评论关系、统一私稿范围。 | `backend/articles/views.py`、`serializers.py` |
| 列表参数 | 排行榜、用户/提交列表非法页码与0页长500；文章非法作者/分类/排序/limit500。正整数验证返回400、页长最多100。 | `backend/users/pagination.py`、users/submissions/articles views |
| 排行榜 | 一页所有用户显示同一排名；改为逐行且跨页连续的实际排名。 | `backend/users/serializers.py:169`、`views.py:171` |
| 考试公开入口 | 匿名访问考试列表使用不存在的 `AnonymousUser.is_teacher` 而500；安全读取发布考试，合法管理员角色与staff账号都能管理。 | `backend/exams/views.py` |
| 实战组卷 | 非管理员可生成题目；导入/循环/删除被损坏注释吞掉，难度大小写与模型不符；恢复代码、权限和事务，重生成替换旧题组。 | `PracticeExamViewSet.generate_questions` |
| 考试创建/结果 | 创建漏掉创建者；普通PATCH能改考试记录所有者、分数、通过状态；创建绑定服务端账号，结果仅由答题/交卷动作更新。 | exams views/serializers |
| 答题校验 | 重复 `validate` 覆盖了恰一个题目ID与非负时长校验；待开始/已放弃记录能答题、交卷；恢复校验并仅接受进行中状态。 | `SubmitAnswerSerializer`、`ExamRecordViewSet.answer/submit` |
| 服务器考试规则 | 服务器未遵守时限与 `max_attempts`；到期拒绝新答案但允许结算已保存答案，重复同卷启动及超过限次返回400。记录行锁保护答题/交卷，用户行锁保护启动限次。 | exams views/serializers |
| 综合考试 | 两个抽样语句被注释吞掉；实战题库不足会留下半个理论考试；乱码前缀破坏理论/实战配对。先验证两部分题库再原子建卷，以一致前缀和唯一后缀配对；完成理论部分后启动实战部分；生成卷仅所属学生及教学管理角色可读。 | `backend/exams/comprehensive.py` |
| 实战正确答题 | `challenges.utils` 缺失；正确答案生成 Submission 缺IP导致500；补精确服务端flag比较与请求元数据，奖励字段映射真实 `score`。 | `backend/challenges/utils.py`、exams views/serializers |
| 考试解析隔离 | 学生可在题库及考试题接口提前读取答案解析；解析保留给教学管理角色，学生试题接口隐藏。 | `TheoryQuestionSerializer` |
| 航线管理 | 创建序列化器含不存在的字段；缺slug/learning_path/content/id，教师读不到草稿；恢复与模型、现有前端编辑器一致的创建/更新/读回合同，生成缺省slug，学生只读发布路径及章节。 | `backend/learning_paths/views.py`、`serializers.py` |
| 航线学习 | 选修完成计入必修分母导致超过100%；LOCKED模块满足条件后仍不能启动；重复完成重复记账。仅计必修、满足前置后解锁、禁止绕过启动完成、完成重试幂等；难度排序保留QuerySet以支持详情。 | learning_paths models/views |
| 遗留实验API | 查询/序列化器/保存均使用模型不存在的字段；恢复实际 `LabAttempt` 合同，服务端核验flag，禁止客户端改成功结果，保存核验摘要而不把flag复制到JSON，正确记录首次完成时间。自由练习仍要求独立核验。 | learning_paths views/serializers |
| 航线推荐 | 在用接口导入不存在的 RecommendationEngine 而500；使用现存序列规则与实际知识点-章节登记关联返回发布航线，明确规则来源，无关联返回空态。没有伪造“已训练模型”或私人学习数据。 | `backend/learning_paths/recommendations.py` |
| 反馈状态 | 配置已开启第三阶段时 `/status/` 仍固定报告关闭；读取同一动态开关契约，README更新为“已实现，默认关闭”。 | `backend/feedback_center/views.py:468`、README |

## 无法自主补造，需要决策或接入

| 事项 | 现状与证据 | 需要决定/提供 |
| --- | --- | --- |
| 通用外部核验器 | 模块六的 `server_verifier/external/isolated_challenge` 明确返回 `server_evidence_not_connected`，不会给出假的通过；模块五/模块四专有证据链不等于这一路通用核验已实现。 | 核验协议、可信服务端证据来源、运行宿主与开放范围。`skill_review/services/verification.py:52` |
| M6/M4→M7/M8主动回传 | 模块六和案例台向M1回传事实；M7/M8 notices仍标 `target_connected=False/not_connected`，读查询并不等于主动投递闭环。 | 下游接收合同、失败重试/对账责任、何时创建反馈与评测任务。`skill_review/services/handoff.py:175/203`、`data_lab/handoff.py:244` |
| 课程资料及开放范围 | 候选目录、法规依据、课程资料与靶场签收须有真实负责人审核，不能用测试数据代替。 | 正式课程/任务/知识点映射、资料审核者、发布范围。以实际数据库与当前签收记录为准，旧README状态不能代替实查。 |
| 反馈第三阶段与执行 | 候选、报告核验、审批/发布/观察/回退已有代码，写入与发布默认关闭；实际执行反馈仍关闭。 | 何时启用哪些范围、审批人/报告来源；是否进入里程碑I实际执行验收。本轮未开启。 |
| 真实模型与推荐 | 已有规则排序；仓库没有训练好的DKT/AKT/S3Rec模型。评测知识库来源与真实成本仍存在未接通/价格未知表达。 | 是否投入训练模型、正式数据/模型/价格与评测集；无映射推荐空态是当前诚实行为。`sequence_recommender.py:1`、`evaluation_center/live_evaluations.py:79` |
| 历史业务数据 | 本轮验证了新建数据的完整链路，未更改真实库的乱码综合考试标题、历史成绩、授权关系或课程签收。 | 历史数据修复/兼容与已有数据库升级的目标环境和验收范围。 |

## 需要用户联调的独立清单

1. 使用目标部署的学生/教师/管理员账号检查Cookie+CSRF登录、退出、课程授权撤销、私有媒体访问。
2. 真实业务库迁移、旧综合考试记录配对、真实题库数量与服务器倒计时；完成理论→实战→评分刷新全流程。前端仍在本轮独立修复考试页行为，须以主任务最终浏览器报告为准。
3. 教师创建草稿航线/章节、刷新回读、发布后学生查看；正式实验映射、前置章节/实验关联编辑与评分同步不在本次最小CRUD合同内，前端须继续明确不可保存/不可执行部分。
4. M3资料审核→授权读取→撤回，M4识别/复核→M6核验→M1事实→M7/M8接收，以及M6教师复核/更正→复测回传。
5. M5真实Docker/FRP/代理/核验/暂停/回收/跨账号隔离与物理清理；自动测试的模拟输出来不代表靶场隔离成立。
6. 真实模型网关、知识库召回质量、超时/429/额度故障恢复及可信报告发布流程；真实调用费用和发布操作需要确定范围。

## 验证限制

本报告的成功结论仅对应合成数据下明确测试的业务行为。主任务会合并全部后端测试、前端测试/构建、浏览器页面、部署配置及外部依赖结果，保留失败与未验证项。旧阶段文件依赖、正式配置关闭与真正未实现的功能分别记录，不能互相替代。
