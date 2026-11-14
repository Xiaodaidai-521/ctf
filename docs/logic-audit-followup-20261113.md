# 当前逻辑检查续查与处理分工

检查日期：2026-11-13（Asia/Shanghai）。以当前工作区及已有未提交修改为准。

上一轮的 16 类问题已逐项复核，仍存在。本轮补充确认 7 类新问题，合计 **23 类（12 类 P1、11 类 P2）**，并确认撤权聊天内容还会再次进入模型历史。P1 应优先处理核心流程、权限、考试成绩和部署入口，P2 为功能契约、体验或性能问题。检查没有修改业务代码、迁移真实数据库、调用真实模型或启动/停止真实靶场；新增的文件仅为报告和隔离复现脚本、证据。

## 原 16 类问题的当前状态

| 编号 | 优先级 | 已确认的问题与影响 | 分工 |
| --- | --- | --- | --- |
| 01 | P1 | 数据实验室交接调用传入接收函数不支持的 `data_lab_evidence`，保存证据后技能核验仍报 TypeError，后续能力事实不能形成 | 我可补可信证据交接、核验和幂等重试；教师验收量表与结论 |
| 02 | P1 | 理论考试到期才集中保存答案，后端已拒收，前端不能完成交卷；另行结算可能得 0 分 | 我可修保存时序、截止边界和恢复 |
| 03 | P1 | 综合考试待开始实战已计时，理论耗时消耗实战时限，可刚开始就超时 | 我可修状态和计时；你确认分段还是整场计时 |
| 04 | P1 | 重组实战试卷级联删除历史答案，已有成绩仍保留 | 我可冻结已使用试卷或引入版本；真实已丢明细需备份才能评估恢复 |
| 05 | P1 | 实战考试前端读取数字 challenge ID 的 description，漏掉真实 `challenge_description` 题面 | 我可统一契约；教师验收题面 |
| 06 | P1 | 已撤回文章详情 404，但真实知识检索仍召回旧正文 | 我可统一来源可见性和失效；真实向量召回需环境联调 |
| 07 | P1 | 来源撤权后聊天详情仍返回回答和来源摘录，继续提问又把旧回答送入模型；可信历史辅助函数没有接入实际读取和消息创建 | 我可补展示、重放、可信来源记录和历史兼容；你验收引用权限规则 |
| 08 | P1 | 独立内容生成缓存跨账号返回别人创建的内容，并忽略题数、图表类型、语言等输出参数 | 我可修账号隔离、缓存键及命中归属 |
| 09 | P2 | 管理员能看到 pending 审核列表，但审批前下载原文 404，无法先审原文 | 我可补受权审核下载 |
| 10 | P2 | 清空已保存多选答案后，前端跳过空值保存，后台仍按旧答案计分 | 我可统一清空/删除语义和真实后端回归 |
| 11 | P2 | 普通实战组卷抽到无 Flag 的自由练习，后续无法正常判题 | 我可补题池及可判题校验 |
| 12 | P2 | 四类生成内容共用数字 ID 详情路由，先命中的教程遮蔽同号测验，返回错类型或 404 | 我可改类型与 ID 联合定位并同步前端 |
| 13 | P2 | 重新生成仍命中原缓存，返回原 ID、原内容，模型调用为 0 | 我可补明确的绕过缓存语义 |
| 14 | P2 | 模型失败 fallback 被保存为生成成功，返回 201 和空测验 | 我可检查上游状态、结构和失败重试 |
| 15 | P2 | 匿名资源列表为了显示加密状态完整读取并解密每个文件，列表成本随大文件明显增长 | 我可用状态投影并保留下载核验，验证读取量 |
| 16 | P2 | 五套内置宠物 manifest 引用的 spritesheet 图片缺失，界面只能显示兜底 | 我可修引用和缺失体验；恢复原设计需要原图备份或你接受替代形象 |

原始逐项代码位置、复现与联调范围见 [上一轮详细报告](./current-logic-audit-20261113.md)。本轮重新复核证据位于 `.state/continue-audit-20261113/`。

## 本轮新增的确认问题

| 编号 | 优先级 | 问题及实际影响 | 当前代码与证据 | 分工 |
| --- | --- | --- | --- | --- |
| 17 | P1 | **启用加密后，刷新考试不能恢复已保存答案。** 后台仍有正确答案，考生本人读取却得到 `[REDACTED]`，前端跳过，页面显示未答。后台保存与恢复功能没有联通 | [答案序列化](D:/aaa10/16015478源码/project-code/backend/exams/serializers.py:158)、[跳过遮罩](D:/aaa10/16015478源码/project-code/frontend/src/views/ExamTaking.vue:436)。真实隔离 API 保存 1 条 sealed-v1 答案，返回 200；响应输入实际 SFC 后已答数为 0、恢复答案为空。证据 `exam-learning/encrypted-restore-api.json`、`exam-learning/frontend-probe.json` | 我可提供仅限受权考生恢复本人答案的接口投影，修恢复流程和回归；修后你做浏览器/手机刷新验收 |
| 18 | P1 | **当前 Compose 普通靶场与后端不在同一个 Docker 网络。** Compose 实际网络名为 `project-code_ctf-challenge`，容器管理器选择并另建 `ctf-challenge`，后端按容器别名转发时缺少共同网络 | [Compose 网络](D:/aaa10/16015478源码/project-code/docker-compose.yml:221)、[网络选择](D:/aaa10/16015478源码/project-code/backend/challenges/container_manager.py:32)、[按别名代理](D:/aaa10/16015478源码/project-code/backend/challenges/views.py:427)。真实 Compose 结构解析和当前管理器执行的 Docker 替身均确认网络名不一致，见 `deployment/topology-repro.json` | 我可统一网络名并验证配置；真实 DNS/HTTP/并发验收需运行中的 Linux Docker。此项针对普通容器代理，不能泛化为独立网络的 Juice Shop 也使用同一路径 |
| 19 | P1 | **当前 Compose 返回的普通靶场地址指向未发布的 8000 端口。** 生成地址为 `https://localhost:8000/challenge/...`，Compose 仅发布 80/443，Gunicorn 的 8000 只绑定容器 loopback。远程学生的 localhost 还指向各自电脑 | [地址构造](D:/aaa10/16015478源码/project-code/backend/challenges/access.py:13)、[发布端口](D:/aaa10/16015478源码/project-code/docker-compose.yml:29)、[Gunicorn 绑定](D:/aaa10/16015478源码/project-code/backend/start.sh:33)。实际 Compose 环境和当前地址构造函数输出见 `deployment/topology-repro.json` | 我可使入口与实际域名、协议和代理端口一致；你/环境负责人提供目标部署地址，修后真实浏览器验收 |
| 20 | P2 | **已上传图片文档没有图片预览入口。** 前端只用 `file_name` 后缀判断，但资源详情序列化没有返回该字段 | [图片判断](D:/aaa10/16015478源码/project-code/frontend/src/components/ResourceDetailModal.vue:193)、[返回字段](D:/aaa10/16015478源码/project-code/backend/resources/serializers.py:25)。真实 PNG 文档详情 200，实际 SFC 的 `isImageFile=false`、`canPreview=false`，见 `integration/image-resource-detail.json`、`integration/resource-modal-probe.json` | 我可补安全的文件类型/展示字段并同步预览判断，不依赖私有存储路径 |
| 21 | P2 | **导学保留视频详情能打开，内嵌播放却 404。** 详情请求携带 `highlight_resource`，返回的 file_url 丢失该访问上下文，video 标签随后请求被拒绝 | [file_url](D:/aaa10/16015478源码/project-code/backend/resources/serializers.py:62)、[保留资源检查](D:/aaa10/16015478源码/project-code/backend/resources/views.py:291)、[video 地址](D:/aaa10/16015478源码/project-code/frontend/src/components/ResourceDetailModal.vue:97)。真实 API：带 highlight 详情 200，返回 URL 下载 404，同一文件带 highlight 下载 200，见 `integration/resource-preview-repro.log` | 我可统一详情与播放授权上下文，回归保留资源播放和普通下载权限 |
| 22 | P2 | **资源切换时旧请求会覆盖新详情或正文。** A 的慢响应在 B 之后完成，页面重新显示 A；也可显示 B 的标题配 A 的正文 | [详情读取](D:/aaa10/16015478源码/project-code/frontend/src/components/ResourceDetailModal.vue:211)、[正文读取](D:/aaa10/16015478源码/project-code/frontend/src/components/ResourceDetailModal.vue:240)、[切换监听](D:/aaa10/16015478源码/project-code/frontend/src/components/ResourceDetailModal.vue:296)。执行实际 SFC，仅 API 边界控制完成顺序；选中 ID 2 后显示 ID 1，另一次选中 ID 2 却显示旧正文，见 `integration/resource-modal-probe.json` | 我可补请求代次/取消和状态归属，自动验证乱序响应；此证据证明资源错配，未证明跨账号泄露 |
| 23 | P1 | **理论考试交卷前泄露判题结果，可反复试选项得到满分。** 保存答案就返回正确性和得分，同一题可反复覆盖；进行中 result 接口也返回判题字段。即使题目接口隐藏正确答案，仍能逐项试出答案 | [反复覆盖答案](D:/aaa10/16015478源码/project-code/backend/exams/views.py:442)、[直接返回判题](D:/aaa10/16015478源码/project-code/backend/exams/views.py:454)、[结果读取](D:/aaa10/16015478源码/project-code/backend/exams/views.py:470)、[答案返回字段](D:/aaa10/16015478源码/project-code/backend/exams/serializers.py:167)。真实 API：B 返回错误/0 分，改 A 返回正确/10 分，未交卷 result 已显示判题，最后结算 10/10 分。证据 `exam-learning/theory-feedback-oracle.json` | 我可使正式理论考试交卷前仅确认保存，全部读取入口隐藏判题，交卷后统一显示。若教学设计刻意允许即时反馈，需要你确认；当前 UI 不展示该反馈，题目接口也隐藏答案 |

## 需要联调以及需要你参与的部分

| 链路 | 我能直接完成 | 你实际需要做什么 |
| --- | --- | --- |
| 考试：开始、答题保存、刷新恢复、截止、交卷、综合实战、历史 | 修 02–05、10–11、17、23，自动验证真实接口与前端状态、截止边界、判题隐藏和试卷历史 | 确认两段计时、正式理论考试反馈规则和通过标准；修复后在电脑及手机完成一次实际考试验收，教师核对题面 |
| 数据实验室 → 技能核验 → 能力事实/成长展示 | 修 01，验证可信证据、幂等交接和故障恢复 | 教师评阅材料、量表、结论和复测要求；不需要你先替我复现异常 |
| 资料审核/撤回 → 索引 → AI 检索/历史 → 资源预览 | 修 06–09、15、20–22，自动验证两账号、撤权、审阅权限和请求乱序 | 教师确认公开范围与引用质量；修后浏览器实际预览、播放和下载验收 |
| 生成内容 → 类型详情 → 缓存/重新生成 → 失败提示 | 修 08、12–14，模拟供应商成功/失败并验证账号、参数和类型 | 评阅生成内容是否正确、难度是否适合；真实供应商质量需要有效权限和额度 |
| 普通靶场、Juice Shop、FRP、回收、模块五 → 六 → 一 | 修 18–19，检查环境、容器限制、接口和自动化验收 | 提供可运行的 Linux/Docker、域名/TLS/网络；两名学生角色实际验收隔离、停止/到期/异常回收、访问和设备体验 |
| 反馈 → 候选 → 评测 → 审批 → 发布/观察/回退 | 可自动验证状态机、配置与报告绑定、事件对账、旧尝试版本稳定性 | 教师和独立审批人用真实教学候选验收发布/回退规则；当前未据此宣称生产通过 |
| PostgreSQL/pgvector、外部模型、Nginx/Gunicorn 流式对话 | 可以做真实环境联调、召回/断线/重试/Cookie/CSRF 检查 | 环境负责人准备服务器、证书、有效模型权限/额度；教师评阅回答和引用 |
| 原始资产、历史数据保护及恢复 | 可盘点、写迁移/恢复方案，先验证副本 | 提供原图/可用备份，确认替代设计与保留规则；已删除的数据不能仅靠改代码恢复 |

人工实测主要用于真实设备/网络体验、多学生环境隔离与资源回收、教学内容和能力评价、真实模型效果。可复现的代码缺陷可以由我修复并自动验证，技术联调在环境就绪后也可由我执行。

## 验证证据和边界

- 考试与实验室：本轮先运行 6 个隔离 SQLite 缺陷探针，再单独补跑 1 个理论判题反馈探针，均观察到预期问题；实际考试 SFC 再次验证到期保存、清空选择、漏题面及加密恢复。证据 `exam-learning/backend-repro.log`、`exam-learning/backend-probe-summary.json`、`exam-learning/frontend-probe.json`、`exam-learning/theory-feedback-repro.log`。
- AI：6 类旧问题重新动态复现；消息真正进入当前服务的本地替身供应商，未调用真实模型。证据及行号见 `.state/continue-audit-20261113/ai-access/report.md` 和三份 JSON。
- 资源：管理员原文 404、匿名列表完整解密 3 MiB、图片契约缺失、保留视频 404 均重新或新增复现。SFC 请求乱序使用替身 HTTP 边界，不能当作真实网络压测。
- 法律运行时导出：本轮 13 项现有回归通过，涵盖请求人/报告绑定、课程范围、撤权、文件完整性及审计失败；只能说明这些覆盖的条件通过。
- 部署：本轮 `docker version` 仍无法连接 Linux Engine；真实 `docker compose config --quiet` 仍因缺 `TLS_CERT_DIR` 失败。只在独立进程中提供占位 TLS/FRPS 路径解析 Compose 结构，未创建容器或验证真实证书。配置拓扑复现脚本为 `artifacts/continue_logic_deployment_repro.py`。
- 上一轮前端全量 938 项中 936 通过、2 个宠物资产相关失败，构建通过；后端四组 222 项中 212 通过、10 个实验室交接错误。它们是上一轮结果，本轮没有把局部探针或新增法律回归叠加成新的全量数字。

隔离探针退出 0 表示缺陷复现脚本按预期完成，不代表已修复。本轮没有执行正式 Linux 部署、真实模型质量评测、生产负载、历史库迁移或教师课程签收。未列出的问题不代表全项目逐接口都已验证无缺陷。

建议优先处理：实验室断链与 AI 权限/账号隔离，考试判题泄露、保存、恢复、计时和历史稳定性，以及普通靶场部署入口；随后修资源/生成内容契约，最后处理列表成本和宠物资产。
