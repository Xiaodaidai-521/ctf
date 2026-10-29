# 模块三首期接口与边界

## 当前可运行的入口

所有模块三API须登录，响应（含拒绝）为 `Cache-Control: private, no-store`，`Vary: Authorization, Cookie`。课程准入映射现有 `CatalogVersion` + 显式 `CourseGrant`，不是新课程体系。`attempt_id` 属于当前会话用户、任务版本一致、目录发布、任务可用及课程授权须同时成立。教师管理权限不转化为学生尝试读取权。

- `POST /api/learning-knowledge/search/`：`{attempt_id, request_id(<=64), query?(<=500), knowledge_point_ids?}`。空query为静态材料；非空为本地纯词项。显式空知识点列表返回空集。请求未知字段（role/source_type/include_raw/extra_filters/purpose等）400拒绝。没有向量服务或LLM依赖。
- `GET /api/learning-knowledge/evidence/{uuid}/` 与 `.../download/`：实时复核用户、任务、源hash、发布/撤回、ACL版本、块hash，仅返回相同短投影；无权/不存在均404。download不是完整文件下载；既有`/media/resources/*`禁用路由保留。
- `POST /api/learning-knowledge/evidence-issues/`：`{attempt_id,request_id,reason,evidence_id?}`。reason为insufficient/conflict/stale/unlocated/material_error。同一尝试+来源修订+原因的未关闭票复用，关闭后新票；证据必须属于该尝试，调用真实模块七服务，不复制原文。
- `POST /api/teaching-knowledge/grants/`：admin独立管理已有用户/目录的active/can_review/maintain_secrets。普通教师不能授权；评分秘密要求admin且有active maintain_secrets职责。
- `GET/POST /api/teaching-knowledge/materials/`：管理列表/来源登记。登记包含catalog_version、task_ids、material_class、hint_level?、source_type、source_object_id?、metadata。材料分级不可在新修订中降级。
- `GET .../materials/{material_uuid}/chunks/?revision=N`：独立管理预览，纯文本原快照、段落、来源许可、日期、作者/审阅者、任务映射与影响任务数。
- `POST .../materials/{material_uuid}/revisions/`：`{task_ids, metadata}`，不可变新快照，不覆盖旧修订。
- `POST .../materials/{material_uuid}/{submit|approve|publish|withdraw}/`：`{expected_revision,idempotency_key(<=64),reason(<=500)}`。同键异内容拒绝。发布要求当前修订、独立作者/审阅者及当前职责、有效来源、未过期、完整可校验块；替换令旧修订superseded，不删除审计。withdraw为材料级即时拒绝，旧提示卡失活。

## 学生证据投影

`request_id, mode(static|lexical), evidence_status, notice, results[]`。状态有sufficient、insufficient、stale、conflict、unlocated；sufficient只是存在已授权匹配材料，不表示足以支撑业务结论。

每张卡片包含：

- `evidence_id`、`material_id`、`material_revision`、`chunk_ref`
- `permission_decision_ref`、`issued_at`（审计引用，不是可复用授权令牌）
- `title`、`source_kind`、`source_ref`、`source_url`、`source_version`、`publisher`
- `license_id`、`attribution_text`、`applicability`
- `locator`、`location_status`、`location_notice`、`excerpt`（最多360字符）
- `knowledge_point_ids`、`catalog_version`、`view_endpoint`

段落定位指保存快照中的实际段落，不冒充原出版物页码。无法定位时明确待人工补齐。官方HTTPS来源地址只展示登记白名单域名，不抓取URL，不允许材料指令触发工具。材料在Vue中按文本展示，不执行HTML/脚本。

## 实际接通与未接通

- **模块二/六，本地真实服务和HTTP**：hint发布同步既有HintCard；request只记录请求，display重新鉴权并以源快照交付，再调用模块六request/show。analysis仅真实通过核验后静态交付、记录analysis_view，不计作普通提示。基础阅读不记帮助。新材料撤回不抹去此前展示事实。无提示复测不调用模型、不交付提示。
- **模块七，本地真实服务**：材料补查调用create_feedback；来源修订引用保留；工单不能代替教师审核、不能自动修正模块六成绩。
- **模块四，尚未接通的消费契约**：只消费本接口当前用户的evidence_id/source_version/applicability/locator/短excerpt；实际读取时再鉴权。不得将sufficient、引用存在或模型肯定措辞当作适用性/合规判定；缺证必须保留needs_review。没有访问其他worktree，没有宣称真实数据任务联调。
- **模块八，尚未接通的授权契约**：证据ID、source_ref、材料正文都不是tool permission；本API不接收tool_name/arguments/execute，也不发工具授权。执行仍须该模块独立可信身份、任务范围和工具白名单。没有新增执行、交付或结算路径。

## 模型与缓存

首期检索完全为静态/纯词项，不安装RAGFlow，不创建第二向量表。保留既有LegalKnowledgeEmbedding关联，尚未写入候选素材向量。旧语义+关键词组装门面必须显式可信Scope；无Scope不回退旧包。旧完整包、旧无来源回复缓存不复用。新检索缓存仅候选chunk ID，命中仍与当前授权修订、课程和知识点相交。

模块三任务不接受未经审阅的模型推论或“有效引用ID即证明结论”。当前模块二模型调用如产生解释，提交前再鉴权，首期退回已审静态一级卡片（无卡则无正文不可用说明）；不缓存该模型解释。模型输入只有受控材料引用，不含教师答案、评分密钥、学生完整解析。生成中撤权不能用旧卡fallback；重复请求重新投影，不重放存储正文。模块二未接模块三材料的原有合规流程仍保留。

已展示的授权内容和用户主动下载的本机文件不能远程抹除；“即时撤回”指后续检索/详情/下载/缓存命中/响应提交复核拒绝，不是撤回用户记忆或本机副本。页面失焦/离页/切用户或任务会清除内存正文并作废旧请求，无localStorage正文。

## 运维与待人工事项

`import_candidate_materials --actor <已有用户主键> --catalog <已有目录版本>`仅登记draft/internal。必须事先由管理员明确设置课程权限；不能运行命令自动给全体学生授权。重复导入不覆盖已审修订。`LicenseRef-Project-Internal-Pending` 候选许可被发布门禁明确拒绝，需登记已确认许可的新修订并重新独立审核，不能将导入成功视为发布批准。30条台账见candidate-register.md；未在测试库之外执行导入。原创待审不是法规原文、正式标准答案、许可确认或靶场运行证据。

同hash文档导入保留最严visibility，不因重新上传降级；若需放宽必须独立管理员审核现有管理权限，不把hash命中作为授权。原子替换、旧worker令牌均保留。SQLite可验证顺序和故障回滚，不能证明PostgreSQL并发互斥；真实PG并发/ANN、真实供应商故障及计费、浏览器人工演示、教师双人签收均需另行验证。
