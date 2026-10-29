# 模块四首期交付记录

日期：2026-10-29。工作位置 `/home/hatch/workspace/ctf-module4`，分支 `feat/module4-case-lab`，基线/当前 HEAD `dc997fe`。本轮未 commit、未 push，未操作主检出或其他 worktree，未修改公共依赖清单/锁文件或安装 Python 依赖。

> **教学演练：只看决策，不执行导出。**
> 当前为候选交付，**不开放课程**。D4-1—D4-5 已完成实现与本地验证；D4-6 固定验收10项通过，教学相关套件141/141通过（含data_lab 57项）。最终全量SQLite：**695发现、678通过、11跳过、5 FAIL、1 ERROR**；失败/错误测试ID与用户提供的dc997fe基线完全一致，新增57项均通过。全量进程exit 1，不是全绿。人工签收和跨模块开放验收未通过，不能把候选状态称为生产可用。

## 1. 按包结果

| 工作包 | 实现与本地结果 | 未替代的人工/联调事项 |
|---|---|---|
| D4-1 | 客户表、独立日志复测各6行合成CSV；事实/依据引用、三个不同结论、教师目标与四层提示、独立版本及摘要；6项材料测试通过 | 两名教师真实审校、依据卡现行性审核未做 |
| D4-2 | 固定资源白名单，受限进程调用原parser/rules；原ReviewService四动作、每扫描独立资产、DB账本与CAS、归属权限；8项测试通过 | 部署同类数据库真实并发与隔离验收未做 |
| D4-3 | 四轮纯决策，冻结B-v1 draft/时刻/输入；先存学生判断再揭示；3项回放测试通过 | 不构成授权或实际保护验证；里程碑I不在范围 |
| D4-4 | 学生五步页、教师状态/尝试/帮助页；独立附件权限；API、前端25项Node测试与生产构建通过 | 未做真实浏览器交互验收 |
| D4-5 | 不可变证据快照、事件事务、幂等重试、服务端核验上下文、六真实核验和人工队列、一真实事实接收；提交6项及交接16项通过 | 七/八仍not_connected；六通用教师入口对象ACL未联动 |
| D4-6 | 五类无AI完整双案流程、执行哨兵、扫描中断恢复、证据损坏、撤回、CAS、草案登记共10项通过；§12矩阵及最终全量对账完成，无新增失败 | 开放验收仍有阻断，不标全部通过 |

逐包原始过程及中断记录见 `PROGRESS.md`；完整16项验收对照见 `docs/data-lab/acceptance.md`。材料包中的 `module6-plan-ref.md` 实际是模块七方案，模块六接点按本 worktree 的 skill_review 源码和测试核对，没有臆造外部接口。

## 2. 数据与教学边界

- 客户表 SHA-256：`dcf4ffff7bdce31f886a90750125384c4c761b98fb0a9d38cad13d7b5011f02d`。
- 日志表 SHA-256：`943ba09621a17c3b7b5c5a5d79ffc38204ce6f918979d17e6e64b170e41f3368`。
- 只接登记的 fixture ID，不收任意路径、URL、生产副本或客户端提供的可信授权/策略/环境/来源/摘要覆盖。
- 逻辑行列一基，CSV表头占逻辑行；字符零基Unicode码点半开区间，前端使用码点切片。样本含中文、emoji、换行、空值、重复标识、设备难负例和全角漏报。
- 客户原检测精确位置+类别指标：10个目标、9个候选，TP8 / FP1 / FN2，precision 8/9，recall 8/10。原检测、人工补录、复核后指标分列；补录不提高原始召回。这只是6行固定合成集，不外推生产检测能力或法律等级。
- 规则0.60是未校准规则分，不是概率。实体类别、个人信息属性、分类分级三个结论分开；依据卡引用不是预制法规结论。
- A1为mask，A2为deny，A3为defer，A4请求次数50→51为mask→require_approval；每次10条与次数分开，B-v1仍为draft。冻结教师参考画像不是学生扫描完整覆盖。
- 提示请求不等于实际展示；展示后计受助，教师帮助有来源/层级；旧解析暴露不因新尝试消失，缺失追踪不冒充独立。没有AI提示入口。
- 教师目标/答案留在后端；学生材料白名单、受控教师附件与学生解析解锁各自处理。模块前端和生产dist中扫描 `teacher_answer` / `grading_secret` 无命中。

## 3. 真实本地交接与故障恢复

1. 四先原子保存版本、依据、扫描/复核、学生解释、四轮输入/判断/程序建议和摘要，并写同事务事件。
2. 再以服务器内部 `data_lab_evidence` 上下文进入六的 SubmissionSnapshot / VerificationResult / ManualReviewTask；通用HTTP提交不能自行提供此可信上下文。
3. 程序结果与人工评阅分开；程序passed仍可为overall pending_manual。四不另建成绩表，不计执行或保护分。
4. 六→一通过冻结notice、稳定限长ID、固定时间、UUID规范化和全字段幂等校验写入真实VerificationFact。sent才表示本地接收确认；七/八明确not_connected。
5. 四的保存事务失败整体回滚；六的事件失败回滚六的半成品，保留四的证据待重试。损坏证据不写通过/知识错误。重试不重跑扫描或改变冻结证据，旧revision不覆盖新revision。
6. 扫描最后事务丢失后，超过30秒的running在下一次扫描请求时转失败；旧键不重跑，新键生成新扫描，旧worker不覆盖终态。
7. 复盘及复测分配复用六的真实服务。自动测试以模拟到期时刻领取独立日志任务并完成核验，不等于观察到真实三日后的学习效果。

恢复为请求/API或运维服务重试，**没有部署异步后台对账worker**。目前无六结果时DTO的program_status保持pending，即使handoff_status为verification_failed；排障须结合handoff_status/failure_code，不把pending当作程序通过。重复有效提交不重计分时的通用消息仍待细化。

## 4. 只读与无模型证据

固定验收的断网、超时、429、额度耗尽、全部模型禁用五种情形，均真实执行：领取→扫描→四动作复核→四轮回放→保存证据→六核验→一记录→复盘→分配日志复测→再次提交核验。

每种情形均断言：

- `export_risk.decisions.service.prepare_execution / claim / consume` 调用数 **0**。
- 父进程 `requests.sessions.Session.request` 与 `socket.socket.connect` 调用数 **0**。
- 生成/教学AI、embedding、检索/排序入口、语义检测调用数 **0**。
- ExecutionAuthorizationRecord、QuotaReservation、DeliveryRecord、RiskDecision 记录数各 **0**。
- 执行状态固定 `not_started`，保护状态固定 `not_assessed`。

故障通过测试替身配置，未制造真实外部429或耗尽真实模型额度。没有独立rerank方法，测试封住整个检索/排序入口。规则worker为固定导入的资源受限独立进程；父进程mock不跨进程传播，这不是通用网络沙箱证明。教学链仅调用纯 `assess_risk`，不接执行凭据或下载保护副本。

## 5. 测试证据与基线对账

统一Python：`/home/hatch/workspace/ctf-venv/bin/python`；Django测试使用 `DATABASE_BACKEND=sqlite` 和 `PYTHONDONTWRITEBYTECODE=1`。日志在 `docs/data-lab/evidence/`。

| 验证 | 真实结果 | 日志 |
|---|---|---|
| D4-1材料 | 6/6 | d4-1.log |
| D4-2识别/复核 | 8/8 | d4-2.log |
| D4-3回放/哨兵 | 3/3 | d4-3.log |
| D4-4阶段后台 | 25/25，65.217秒 | d4-4-backend.log |
| D4-4附件权限追加 | 8/8，21.283秒 | d4-4-api-final.log |
| Node前端 | 25/25 | d4-4-frontend-node.log |
| Vite构建 | 成功，3685 modules，42.75秒；全站大chunk警告 | d4-4-frontend-build.log |
| 前端禁用键扫描 | 无命中；未做浏览器验证 | d4-4-frontend-audit.log |
| D4-5真实提交 | 6/6，9.485秒 | d4-5-submissions-retry.log |
| D4-5交接 | 16/16，1.588秒 | d4-5-handoff.log |
| D4-6修复后固定验收 | 10/10，14.859秒 | d4-6-acceptance-final.log |
| 修复后教学相关套件 | 141/141，234.924秒；其中data_lab 57/57 | d4-final-related-fixed.log |
| 修复后全量SQLite | 695发现/678通过/11跳过/5 FAIL/1 ERROR，465.972秒；exit 1，无新增失败 | d4-full-sqlite-final.log |
| Django check | 0问题 | d4-check.log |
| 迁移漂移检查 | No changes detected；常驻SQLite库打不开，历史一致性检查warning | d4-migrations-check.log |
| 最终工作树审计 | HEAD/分支未变，diff --check通过，依赖清单无差异，材料SHA匹配，前端禁用键无命中 | d4-worktree-audit.log |

### 全量对账（已完成）

| 指标 | 用户提供的dc997fe基线 | 修复后实际全量 | 变化 |
|---|---:|---:|---:|
| 发现 | 638 | 695 | +57 |
| 通过 | 621 | 678 | +57 |
| 跳过 | 11 | 11 | 0 |
| FAIL | 5 | 5 | 0 |
| ERROR | 1 | 1 | 0 |

机器核对总数及失败/错误ID集合一致，`new_failure_ids=[]`；见 `docs/data-lab/evidence/d4-reconciliation.json`（含最终日志SHA-256）。这是对用户提供基线的对账，不冒称本轮另跑过完整干净基线。全量仍失败，未修改或掩盖以下既有问题。

基线既有问题（不在本模块修复范围）：

- `challenges.tests.ChallengeProxyAccessTests.test_access_url_does_not_include_reusable_token`
- `challenges.tests.ChallengeProxyAccessTests.test_proxy_accepts_authenticated_owner_without_cookie`
- `challenges.tests.ChallengeProxyAccessTests.test_proxy_rejects_authenticated_non_owner`
- `challenges.tests.ChallengeProxyAccessTests.test_proxy_rejects_unsafe_session_request_without_csrf`
- `mainline1.tests.test_semantic.SemanticTests.test_real_transport_constructor_pins_options_without_provider_registry`
- `mainline1.test_settings` 导入ERROR：缺少 `MAINLINE1_TEST_PORT`。

失败/中断记录没有隐藏：早期开工 `baseline.log` 被600秒超时停止，不能作为本地完整基线；`d4-5-submissions.log` 中断于迁移；`d4-final-related.log` 被120秒时限停止。首次完整相关141项为140通过/1 ERROR，首次完整全量695项为677通过/11跳过/5 FAIL/2 ERROR；新增ERROR来自登记测试与全局任务版本唯一键冲突。已修复登记命令及独立测试夹具，明确拒绝跨目录同版本、不覆盖签收，10项验收已通过；最终相关141项全部通过，全量恢复到基线相同的5 FAIL/1 ERROR集合。

复现最终命令（全量必须从本worktree的backend目录发现测试）：

```sh
# 在 /home/hatch/workspace/ctf-module4
PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_BACKEND=sqlite \
  /home/hatch/workspace/ctf-venv/bin/python backend/manage.py test \
  data_lab skill_review learning_map teaching_agent --noinput -v 2

(cd backend && PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_BACKEND=sqlite \
  /home/hatch/workspace/ctf-venv/bin/python manage.py test --noinput -v 2)

node --test frontend/src/views/DataLab/*.test.js
npm --prefix frontend run build
```

## 6. 变更与部署范围

新增实现集中在 `backend/data_lab/`，含一份初始迁移、草案登记命令、两案材料及测试；页面在 `frontend/src/views/DataLab/`；文档在 `docs/data-lab/`。

既有文件的实际增量：

- settings、后端总路由、前端router：仅本应用注册/路由。
- mainline1：两个固定合成检测器和可选scan_columns，默认调用方式保留；复用原parser/rule/review/codec。
- skill_review：仅data_lab专用证据上下文/验证器/handoff注册，有界事件ID，核验返回的量表版本；未重写其他任务流程。
- 未修改依赖清单或lock文件；未改export执行服务、配额服务或其他worktree。

只在临时测试数据库运行新迁移，未迁移常驻业务库。草案登记命令仅在自动测试执行；部署命令模板、恢复说明见 `docs/data-lab/README.md`。不能把测试库的发布/签收fixture复制为课程签收证据。

## 7. 开放阻断与未做项

**当前不开放。** 以下仍须完成，未标通过：

1. **权限阻断**：data_lab自己的教师入口有角色+CasePackage对象ACL，但模块六通用教师队列/详情/帮助等仍只有既有角色级授权。本轮未改这些公共视图，不能宣称跨模块教师对象隔离完成。
2. 两名教师真实审校签收、依据卡现行性审核、真实人工评分；`teacher-signoff.md` 全部待签收。
3. 模块三知识包/权限服务、模块八评估中心跨worktree联调；七/八通知not_connected，不冒充真实下游回执。
4. 部署同类数据库的多进程并发验收；当前CAS测试只覆盖失效版本竞争，不是生产并发结论。
5. 真实浏览器交互、普通抽查流程专门验证、真实三日复测学习效果观察。
6. Presidio隔离验证未做，未安装到公共venv；不称为“验证失败后降级”。
7. 自动后台对账、AI帮助展示未接入；故障/重复提交的DTO提示还有可细化项。

里程碑I、执行授权、真实导出、保护产物均不在此次范围。任何allow/mask等建议均不构成执行许可或实际脱敏证明。
