# 第2步：设计、契约与验收基线

2026-10-13 审查补齐：**complete（设计交付）**，所有公共契约仍为 **Proposed**。此前中断导致交接不完整，现已收尾；不将草案通过算作业务功能通过。

| 要求 | 审查结论与证据 |
|---|---|
| 1 所有权、数据流、适配 | design.md §2、§13；消费既有资产owner，不新建跨模块资产管理系统 |
| 2 十四个核心对象 | contracts/schema.json 与 catalog.json；每个对象字段/类型/来源及约束已列 |
| 3 必填/空值/坐标/状态/错误/分页/幂等/不可变 | design.md §1、§3—9，Schema及有限跨字段校验；成功/质量/复核/授权分别建模 |
| 4 异步/运行与尝试/生成执行契约 | design.md §4、§7；202 TaskReference草案，执行前权威重校验 |
| 5 复核并发/替代/通知/适用性 | design.md §5—6；CAS、追加历史、outbox和下游自主重评估 |
| 6 快照/缓存/保留/模型路径/delivery_mode | design.md §4、§8、§10；backend_only推荐，真实模型默认关闭 |
| 7 文件/依赖/迁移/回滚 | design.md §11—13；编写、隔离验证、业务库执行分别记录 |
| 8 功能与实验验收 | acceptance.md A01—A27、分组切分/严格匹配/指标/失败计入分母；无数值门槛不造门槛 |
| 合成JSON及兼容性 | 29场景通过，覆盖正常、partial、冲突、取消、版本变化、复核后旧计划及失败；旧调用方不变，公共消费者尚未实际接入 |

设计和待决选项见 [design.md](design.md)，验收见 [acceptance.md](acceptance.md)。下列结构化记录保留此前判断变化；当前结论以顶部状态及最后追加记录为准。

```json
{
  "step": "02",
  "status": "complete",
  "recorded_on": "2026-10-13",
  "mission": {
    "solved": [
      "八项设计要求及合成契约验证已具备可审阅产物；完成本轮逐项审查和交接收尾",
      "14个公共对象保持Proposed；授权与未决项分开",
      "澄清资产owner适配、内部解析任务与公共扫描契约边界、数据库编写/隔离验证/生产执行边界"
    ],
    "not_solved": [
      "公共契约正式发布/生产接入/真实语义不是本步实现目标；待决事项不冒充批准"
    ]
  },
  "stage_result": {
    "schema": "mainline1.stage2.v1 / E7",
    "data": {
      "module_ownership": [
        {
          "module": "mainline1",
          "owns": "解析、任务、发现画像、复核、适用性、计划；见 design.md §2"
        },
        {
          "module": "asset owner",
          "owns": "原始私有资产及删除；未指定正式实现，不另建跨模块资产系统"
        },
        {
          "module": "执行/主线二/审计/评估",
          "owns": "各自决定/执行/事件/实验，见 design.md §2"
        }
      ],
      "data_flow": [
        "鉴权→固定资产→快照→异步任务→解析/检测→画像→追加复核→后继状态/通知→计划/只读校验；全部为草案"
      ],
      "contracts": [
        {
          "name": "AssetVersionRef",
          "owner": "既有资产所有者（待跨线指定；主线一只适配，不另建资产系统）",
          "consumers": [
            "主线一受控 AssetReader",
            "主线二",
            "执行支线"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "asset",
              "type": "#/$defs/AssetKey",
              "required": true,
              "nullable": false,
              "meaning": "固定版本与原始字节摘要"
            },
            {
              "name": "owner_service",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "资产对象所有者服务，草案候选 asset_registry"
            },
            {
              "name": "format",
              "type": "[\"csv\", \"xlsx\"]",
              "required": true,
              "nullable": false,
              "meaning": "仅支持首版格式"
            },
            {
              "name": "private_storage_ref",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "不透明私有句柄；不可用作路径/URL/下载授权"
            },
            {
              "name": "byte_size",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "固定原始字节数"
            },
            {
              "name": "state",
              "type": "[\"ready\", \"deleted\", \"unavailable\"]",
              "required": true,
              "nullable": false,
              "meaning": "来自对象所有者的当前状态观察"
            },
            {
              "name": "state_version",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "状态观察版本；内容引用不变"
            },
            {
              "name": "deleted_at",
              "type": "[{\"type\": \"string\", \"format\": \"date-time\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "删除时保留最小墓碑时间"
            }
          ],
          "invariants": [
            "asset 字节和版本不可变；state 是独立权威观察，state_version 单调",
            "deleted 必须 deleted_at；private_storage_ref 不是访问授权"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "ASSET_DELETED",
            "ASSET_VERSION_MISMATCH"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "BusinessContext",
          "owner": "主线一",
          "consumers": [
            "主线一上下文/检测服务",
            "获授权配置/复核人员",
            "隔离评估服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "context_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "上下文对象 ID"
            },
            {
              "name": "version",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "不可变版本"
            },
            {
              "name": "asset_version_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "适用资产版本"
            },
            {
              "name": "scope_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "适用范围摘要"
            },
            {
              "name": "scenario",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "业务场景，仅授权读取"
            },
            {
              "name": "purpose",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "用途描述"
            },
            {
              "name": "table_description",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "表说明"
            },
            {
              "name": "field_descriptions",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "字段说明按坐标，允许重复表头"
            },
            {
              "name": "source",
              "type": "[\"admin_config\", \"confirmed_dictionary\", \"user_input\", \"model_inferred\"]",
              "required": true,
              "nullable": false,
              "meaning": "记录来源不改写历史"
            },
            {
              "name": "confirmation",
              "type": "[\"unconfirmed\", \"confirmed\", \"conflicted\"]",
              "required": true,
              "nullable": false,
              "meaning": "确认状态"
            },
            {
              "name": "confirmed_by",
              "type": "[{\"type\": \"integer\", \"minimum\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "现有用户整数 ID；已确认才非空"
            },
            {
              "name": "confirmed_at",
              "type": "[{\"type\": \"string\", \"format\": \"date-time\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "确认时间"
            },
            {
              "name": "content_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "受控规范化内容摘要，不进入普通日志"
            },
            {
              "name": "supersedes_context_id",
              "type": "[{\"type\": \"string\", \"format\": \"uuid\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "确认或修正创建新版本引用"
            }
          ],
          "invariants": [
            "confirmed 必须确认者/时间；model_inferred 不可直接 confirmed",
            "确认生成新版本，适用 asset_version/scope 不可跨域"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "CONTEXT_INVALID"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "ClassificationPolicy",
          "owner": "主线一",
          "consumers": [
            "主线一检测/等级/复核",
            "授权政策管理员",
            "评估服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "policy_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "政策 ID"
            },
            {
              "name": "version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "不可变政策版本"
            },
            {
              "name": "dictionary_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "类别字典版本"
            },
            {
              "name": "ruleset_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "规则集版本"
            },
            {
              "name": "state",
              "type": "[\"draft\", \"active\", \"retired\"]",
              "required": true,
              "nullable": false,
              "meaning": "发布须单独批准"
            },
            {
              "name": "effective_at",
              "type": "[{\"type\": \"string\", \"format\": \"date-time\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "active 时生效时间"
            },
            {
              "name": "levels",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "有序内部等级，非法律结论"
            },
            {
              "name": "categories",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "字典和映射"
            },
            {
              "name": "rule_refs",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "允许规则版本列表"
            },
            {
              "name": "conflict_strategy",
              "type": "\"review_no_downgrade\"",
              "required": true,
              "nullable": false,
              "meaning": "冲突复核，不依据弱描述自动降级"
            },
            {
              "name": "review_policy_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "复核触发策略版本"
            },
            {
              "name": "content_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "政策规范化摘要"
            }
          ],
          "invariants": [
            "类别/规则 ID 唯一，映射等级必须存在，引用无悬空",
            "active 有生效时间；发布后修改必须新版本"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "POLICY_INVALID"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "DataScope",
          "owner": "主线一",
          "consumers": [
            "主线一解析/任务",
            "执行支线",
            "评估服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "asset_version_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "固定版本"
            },
            {
              "name": "coordinate_version",
              "type": "\"one-based-codepoint-v1\"",
              "required": true,
              "nullable": false,
              "meaning": "行列一基，字符零基半开"
            },
            {
              "name": "selections",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "不重叠、排序的选区；不可用空数组暗示全部"
            },
            {
              "name": "include_header",
              "type": "boolean",
              "required": true,
              "nullable": false,
              "meaning": "是否扫描表头文字；无论是否扫描都计入行号"
            },
            {
              "name": "scope_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "资产版本和规范化选择/坐标/include_header 的摘要"
            }
          ],
          "invariants": [
            "每 sheet 唯一，选区排序合并且 start<=end；空范围不是全选",
            "scope_hash 包含固定资产版本和坐标语义"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "SCOPE_INVALID"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "ParsedAsset",
          "owner": "主线一",
          "consumers": [
            "主线一检测/计划服务（受控内部）",
            "授权评估服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "parsed_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "不可变解析结果 ID"
            },
            {
              "name": "asset",
              "type": "#/$defs/AssetKey",
              "required": true,
              "nullable": false,
              "meaning": "输入版本"
            },
            {
              "name": "scope_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "输入范围"
            },
            {
              "name": "parser_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "解析器实现版本"
            },
            {
              "name": "parser_config_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "解析配置摘要"
            },
            {
              "name": "structure_ref",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "sheet 列表/合并区域/隐藏内容/逻辑记录清单受控引用"
            },
            {
              "name": "mappings",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "样例内联；生产按固定 parsed_id 分页或私有清单"
            },
            {
              "name": "coverage",
              "type": "#/$defs/Coverage",
              "required": true,
              "nullable": false,
              "meaning": "四层独立覆盖；解析阶段其余可 not_run"
            },
            {
              "name": "excluded_contents",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "未纳入的非单元格内容等"
            },
            {
              "name": "warnings",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "稳定警告码"
            },
            {
              "name": "errors",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "解析错误码"
            }
          ],
          "invariants": [
            "mappings 绑定源格；unmappable 禁止生成 span 操作",
            "解析失败有错误与覆盖缺口，不能空文本 complete"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "PARSE_FAILED",
            "RESOURCE_LIMIT",
            "LOCATION_MISMATCH"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "Finding",
          "owner": "主线一",
          "consumers": [
            "授权画像/复核消费者",
            "主线二",
            "执行支线受控计划依据",
            "评估服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "finding_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "追加不可变发现"
            },
            {
              "name": "scan_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "逻辑扫描 ID"
            },
            {
              "name": "kind",
              "type": "[\"field\", \"entity\", \"combination\"]",
              "required": true,
              "nullable": false,
              "meaning": "列、字符实体、关系发现"
            },
            {
              "name": "locations",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "一个或多个原位置"
            },
            {
              "name": "category_id",
              "type": "[{\"type\": \"string\", \"minLength\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "无法判定时 null，不使用待复核类别"
            },
            {
              "name": "judgment",
              "type": "[\"determined\", \"insufficient\", \"conflict\", \"pending_review\"]",
              "required": true,
              "nullable": false,
              "meaning": "内容判断状态"
            },
            {
              "name": "source_type",
              "type": "[\"rule\", \"semantic\", \"fusion\", \"manual\"]",
              "required": true,
              "nullable": false,
              "meaning": "来源独立于判断"
            },
            {
              "name": "detector_id",
              "type": "[{\"type\": \"string\", \"minLength\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "非人工来源检测器标识；人工为 null"
            },
            {
              "name": "detector_version",
              "type": "[{\"type\": \"string\", \"minLength\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "非人工来源检测器版本；人工为 null"
            },
            {
              "name": "source_finding_ids",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "fusion 至少含两个依据发现"
            },
            {
              "name": "relation_type",
              "type": "[{\"type\": \"string\", \"minLength\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "combination 关系类型，否则 null"
            },
            {
              "name": "evidence",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "私有证据引用，不内联原文"
            },
            {
              "name": "uncertainty_reasons",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "未确定或冲突原因"
            },
            {
              "name": "raw_score",
              "type": "[{\"type\": \"number\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "原始分数不当作概率"
            },
            {
              "name": "score_meaning",
              "type": "[{\"type\": \"string\", \"minLength\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "原始分数口径"
            },
            {
              "name": "calibrated_probability",
              "type": "[{\"type\": \"number\", \"minimum\": 0, \"maximum\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "未校准必须 null"
            },
            {
              "name": "calibration_version",
              "type": "[{\"type\": \"string\", \"minLength\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "概率非空时必须提供校准版本"
            },
            {
              "name": "created_by",
              "type": "[{\"type\": \"integer\", \"minimum\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "manual 必须为服务端操作者 ID"
            },
            {
              "name": "review_id",
              "type": "[{\"type\": \"string\", \"format\": \"uuid\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "manual 必须引用追加复核记录"
            }
          ],
          "invariants": [
            "manual 无 detector 且有 actor/review；fusion 有来源发现",
            "span 非空且不越界；calibrated_probability 非空须 calibration_version",
            "判断/类别/来源分离，combination 有关系类型及多个位置"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "MODEL_OUTPUT_INVALID",
            "LOCATION_MISMATCH"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "ReviewRecord",
          "owner": "主线一",
          "consumers": [
            "授权复核人员",
            "主线一画像服务",
            "审计支线最小投影"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "review_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "追加复核记录"
            },
            {
              "name": "base_profile_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "提交基于的不可变画像"
            },
            {
              "name": "expected_state_version",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "期望当前适用性版本"
            },
            {
              "name": "idempotency_key",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "作用域+主体+operation 内幂等键"
            },
            {
              "name": "request_fingerprint",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "规范化请求指纹"
            },
            {
              "name": "actor_id",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "服务端用户整数 ID"
            },
            {
              "name": "action",
              "type": "[\"confirm\", \"correct\", \"false_positive\", \"add_manual\"]",
              "required": true,
              "nullable": false,
              "meaning": "内容操作"
            },
            {
              "name": "finding_ids",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "目标或新人工发现 ID"
            },
            {
              "name": "reason",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "必要原因，访问受控，不复制原文到通用日志"
            },
            {
              "name": "before_category",
              "type": "[{\"type\": \"string\", \"minLength\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "复核前类别"
            },
            {
              "name": "after_category",
              "type": "[{\"type\": \"string\", \"minLength\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "确认/修正/新增类别；误报为 null"
            },
            {
              "name": "workflow_status",
              "type": "[\"pending\", \"completed\"]",
              "required": true,
              "nullable": false,
              "meaning": "复核是否完成"
            },
            {
              "name": "request_status",
              "type": "[\"accepted\", \"rejected\"]",
              "required": true,
              "nullable": false,
              "meaning": "请求处理与内容结论分离"
            },
            {
              "name": "conclusion",
              "type": "[{\"enum\": [\"confirmed\", \"corrected\", \"false_positive\", \"manual_added\"]}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "仅已接受完成时非空"
            },
            {
              "name": "successor_profile_id",
              "type": "[{\"type\": \"string\", \"format\": \"uuid\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "已接受完成必须有后继；拒绝不产生后继"
            },
            {
              "name": "completed_at",
              "type": "[{\"type\": \"string\", \"format\": \"date-time\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "完成时间"
            }
          ],
          "invariants": [
            "拒绝请求无内容结论和后继；完成接受必须有一致结论和后继",
            "base profile/expected version/幂等指纹在同事务检查"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "REVIEW_VERSION_CONFLICT",
            "IDEMPOTENCY_CONFLICT"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "SensitivityProfile",
          "owner": "主线一",
          "consumers": [
            "主线二",
            "执行支线",
            "授权查询/复核",
            "评估服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "profile_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "不可变画像 ID"
            },
            {
              "name": "asset",
              "type": "#/$defs/AssetKey",
              "required": true,
              "nullable": false,
              "meaning": "绑定资产版本"
            },
            {
              "name": "scan_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "追溯固定运行快照"
            },
            {
              "name": "scope_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "范围绑定"
            },
            {
              "name": "quality",
              "type": "[\"complete\", \"partial\", \"unavailable\"]",
              "required": true,
              "nullable": false,
              "meaning": "按扫描政策计算完整性"
            },
            {
              "name": "coverage",
              "type": "#/$defs/Coverage",
              "required": true,
              "nullable": false,
              "meaning": "四层覆盖"
            },
            {
              "name": "finding_ids",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "稳定发现清单；分页固定此画像"
            },
            {
              "name": "category_counts",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "类别计数"
            },
            {
              "name": "combination_finding_ids",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "组合关系引用"
            },
            {
              "name": "protection_level",
              "type": "[{\"type\": \"string\", \"minLength\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "政策算出的内部等级；证据不足 null"
            },
            {
              "name": "policy_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "分类政策版本"
            },
            {
              "name": "detector_versions",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "检测器版本清单"
            },
            {
              "name": "review_status",
              "type": "[\"not_required\", \"pending\", \"completed\"]",
              "required": true,
              "nullable": false,
              "meaning": "流程状态，不是类别"
            },
            {
              "name": "supersedes_profile_id",
              "type": "[{\"type\": \"string\", \"format\": \"uuid\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "唯一当前链上的前驱"
            },
            {
              "name": "applicability_ref",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "权威适用状态引用，独立于不可变内容"
            },
            {
              "name": "limitations",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "未知、降级与覆盖限制"
            },
            {
              "name": "person_count",
              "type": "[{\"type\": \"integer\", \"minimum\": 0}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "未知人数必须 null"
            }
          ],
          "invariants": [
            "内容不可变，只有适用性对象可追加变更；当前链唯一",
            "quality complete 必须覆盖快照要求层，不意味着外发授权"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "PROFILE_NOT_READY",
            "COVERAGE_INSUFFICIENT"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "ScanRunSnapshot",
          "owner": "主线一",
          "consumers": [
            "主线一 worker",
            "授权重放/评估服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "scan_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "逻辑运行 ID"
            },
            {
              "name": "asset",
              "type": "#/$defs/AssetKey",
              "required": true,
              "nullable": false,
              "meaning": "固定输入版本"
            },
            {
              "name": "scope",
              "type": "#/$defs/DataScope",
              "required": true,
              "nullable": false,
              "meaning": "固定规范化选区"
            },
            {
              "name": "context_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "上下文引用"
            },
            {
              "name": "context_version",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "上下文固定版本"
            },
            {
              "name": "context_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "上下文摘要"
            },
            {
              "name": "policy_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "政策版本"
            },
            {
              "name": "dictionary_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "字典版本"
            },
            {
              "name": "ruleset_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "规则集版本"
            },
            {
              "name": "model",
              "type": "#/$defs/ModelSpec",
              "required": true,
              "nullable": false,
              "meaning": "固定模型配置/禁用策略"
            },
            {
              "name": "fusion_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "融合版本"
            },
            {
              "name": "parser_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "解析实现版本"
            },
            {
              "name": "parser_config",
              "type": "#/$defs/ParserConfig",
              "required": true,
              "nullable": false,
              "meaning": "解析完整配置"
            },
            {
              "name": "parser_config_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "解析配置摘要"
            },
            {
              "name": "sampling",
              "type": "#/$defs/Sampling",
              "required": true,
              "nullable": false,
              "meaning": "采样与随机种子"
            },
            {
              "name": "budget",
              "type": "#/$defs/Budget",
              "required": true,
              "nullable": false,
              "meaning": "固定预算"
            },
            {
              "name": "semantic_required",
              "type": "boolean",
              "required": true,
              "nullable": false,
              "meaning": "语义是否是质量完整条件"
            },
            {
              "name": "combination_required",
              "type": "boolean",
              "required": true,
              "nullable": false,
              "meaning": "组合是否是质量完整条件"
            },
            {
              "name": "scan_policy_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "扫描完整性政策版本"
            },
            {
              "name": "request_fingerprint",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "所有影响结果输入及可信域/主体/评估身份摘要"
            },
            {
              "name": "snapshot_ref",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "受控完整快照引用"
            },
            {
              "name": "reproducibility_limits",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "不可固定模型修订等限制"
            }
          ],
          "invariants": [
            "创建后不可变，影响结果输入完整固定并进入请求指纹",
            "disabled model 无外部调用；重试不更换快照和预算"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "CONTEXT_INVALID",
            "POLICY_INVALID",
            "BUDGET_EXHAUSTED"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "ProfileApplicability",
          "owner": "主线一权威状态；主线二/执行支线消费",
          "consumers": [
            "主线二",
            "执行支线",
            "授权查询服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "applicability_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "稳定查询 ID"
            },
            {
              "name": "profile_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "画像 ID"
            },
            {
              "name": "asset_version_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "资产版本"
            },
            {
              "name": "state_version",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "单调递增并发版本"
            },
            {
              "name": "status",
              "type": "[\"current\", \"superseded\", \"reevaluation_required\", \"unverifiable_deleted\"]",
              "required": true,
              "nullable": false,
              "meaning": "权威适用状态"
            },
            {
              "name": "successor_profile_id",
              "type": "[{\"type\": \"string\", \"format\": \"uuid\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "superseded 时后继"
            },
            {
              "name": "reason_codes",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "变化原因"
            },
            {
              "name": "changed_at",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "状态变化时间"
            },
            {
              "name": "affected_scope_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "需要重评估范围"
            },
            {
              "name": "usable_for_new_decision",
              "type": "boolean",
              "required": true,
              "nullable": false,
              "meaning": "仅 current 且业务条件满足可 true，仍非授权"
            },
            {
              "name": "historical_audit_available",
              "type": "boolean",
              "required": true,
              "nullable": false,
              "meaning": "历史是否可审计，不保证原文永久保留"
            }
          ],
          "invariants": [
            "非 current 不能 usable_for_new_decision；superseded 必有后继",
            "变化增加 state_version，不修改画像和计划本体"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "PROFILE_SUPERSEDED",
            "PROFILE_REEVALUATION_REQUIRED",
            "PROFILE_UNVERIFIABLE"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "RedactionPlan",
          "owner": "主线一生成；执行支线共同维护操作语义",
          "consumers": [
            "执行支线",
            "授权查询/评估服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "plan_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "不可变计划 ID"
            },
            {
              "name": "plan_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "完整规范化计划摘要，排除 plan_hash/meta.trace_id，自身不是授权"
            },
            {
              "name": "asset",
              "type": "#/$defs/AssetKey",
              "required": true,
              "nullable": false,
              "meaning": "输入固定版本"
            },
            {
              "name": "scan_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "扫描引用"
            },
            {
              "name": "profile_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "依据画像"
            },
            {
              "name": "scope_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "范围"
            },
            {
              "name": "parser_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "解析实现版本"
            },
            {
              "name": "parser_config_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "解析配置摘要"
            },
            {
              "name": "policy_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "分类政策版本"
            },
            {
              "name": "redaction_policy_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "脱敏政策版本"
            },
            {
              "name": "requirements",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "规范化保护要求快照"
            },
            {
              "name": "requirements_hash",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "要求快照摘要"
            },
            {
              "name": "operation_contract_version",
              "type": "\"original-snapshot-v1-proposed\"",
              "required": true,
              "nullable": false,
              "meaning": "待执行方确认的组合语义版本"
            },
            {
              "name": "operations",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "完整固定快照操作清单"
            },
            {
              "name": "operation_count",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "清单总数"
            },
            {
              "name": "unresolved",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "尚未满足的要求/位置原因码"
            },
            {
              "name": "validation_errors",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "稳定错误码"
            },
            {
              "name": "status",
              "type": "[\"ready\", \"partial\", \"invalid\"]",
              "required": true,
              "nullable": false,
              "meaning": "计划就绪≠外发授权"
            },
            {
              "name": "checked_applicability_version",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "最近生成校验观察版本，执行前仍须重新查"
            },
            {
              "name": "validation_ref",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "无业务写入校验结果的受控引用"
            }
          ],
          "invariants": [
            "ready 无未解决项/错误，完整操作数等于 operation_count",
            "只定位原始快照，冲突拒绝，操作/要求引用完整",
            "状态/hash不授权，使用前重新查画像/资产权威状态"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "PLAN_CONFLICT",
            "PLAN_HASH_MISMATCH",
            "COVERAGE_INSUFFICIENT"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "ScanResult",
          "owner": "主线一",
          "consumers": [
            "授权调用者",
            "任务查询/评估服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "scan_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "逻辑扫描 ID"
            },
            {
              "name": "attempt_id",
              "type": "[{\"type\": \"string\", \"format\": \"uuid\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "当前/最后尝试，未认领 null"
            },
            {
              "name": "task_status",
              "type": "[\"queued\", \"running\", \"succeeded\", \"failed\", \"cancelled\"]",
              "required": true,
              "nullable": false,
              "meaning": "仅任务生命周期"
            },
            {
              "name": "quality",
              "type": "[\"complete\", \"partial\", \"unavailable\"]",
              "required": true,
              "nullable": false,
              "meaning": "独立结果质量"
            },
            {
              "name": "profile_id",
              "type": "[{\"type\": \"string\", \"format\": \"uuid\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "已发布画像或 null"
            },
            {
              "name": "snapshot_ref",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "不可变配置引用"
            },
            {
              "name": "stage",
              "type": "[\"queued\", \"parse\", \"rule\", \"semantic\", \"fusion\", \"publish\", \"done\"]",
              "required": true,
              "nullable": false,
              "meaning": "真实处理阶段"
            },
            {
              "name": "processed_count",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "阶段实际数量"
            },
            {
              "name": "total_count",
              "type": "[{\"type\": \"integer\", \"minimum\": 0}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "未知总数 null"
            },
            {
              "name": "progress_ratio",
              "type": "[{\"type\": \"number\", \"minimum\": 0, \"maximum\": 1}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "阶段比例，未知/零分母 null"
            },
            {
              "name": "coverage",
              "type": "#/$defs/Coverage",
              "required": true,
              "nullable": false,
              "meaning": "分层覆盖"
            },
            {
              "name": "cancel_requested_at",
              "type": "[{\"type\": \"string\", \"format\": \"date-time\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "取消请求时间，不等于已经停机"
            },
            {
              "name": "warnings",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "降级等警告"
            },
            {
              "name": "errors",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "失败原因码"
            },
            {
              "name": "started_at",
              "type": "[{\"type\": \"string\", \"format\": \"date-time\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "开始时间"
            },
            {
              "name": "completed_at",
              "type": "[{\"type\": \"string\", \"format\": \"date-time\"}, {\"type\": \"null\"}]",
              "required": true,
              "nullable": true,
              "meaning": "终态时间"
            }
          ],
          "invariants": [
            "终态 failed/cancelled 不能 quality complete；succeeded 可 partial",
            "总量未知/零时 progress_ratio=null，不伪造百分比"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "TASK_CANCELLED",
            "STALE_ATTEMPT"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "ScanComparison",
          "owner": "主线一",
          "consumers": [
            "授权复核/查询",
            "主线二重评估适配",
            "评估服务"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "comparison_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "固定比较结果"
            },
            {
              "name": "before_scan_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "旧扫描"
            },
            {
              "name": "after_scan_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "新扫描"
            },
            {
              "name": "before_profile_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "旧画像"
            },
            {
              "name": "after_profile_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "新画像"
            },
            {
              "name": "before_asset_version_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "旧资产版本"
            },
            {
              "name": "after_asset_version_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "新资产版本"
            },
            {
              "name": "matching_version",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "匹配规则版本"
            },
            {
              "name": "added",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "新增发现"
            },
            {
              "name": "disappeared",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "旧发现消失，不等于删除已执行"
            },
            {
              "name": "category_changes",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "类别变化映射"
            },
            {
              "name": "unmatched",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "无法可靠匹配，不强行按坐标继承"
            },
            {
              "name": "limitations",
              "type": "array",
              "required": true,
              "nullable": false,
              "meaning": "版本/移动/覆盖差异限制"
            }
          ],
          "invariants": [
            "before/after版本和匹配版本固定，无法匹配显式 unmatched",
            "不按移动后的相同坐标继承人工结论"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "ASSET_VERSION_MISMATCH"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        },
        {
          "name": "TaskReference",
          "owner": "主线一",
          "consumers": [
            "授权扫描调用者",
            "后续 UI/管理命令"
          ],
          "fields": [
            {
              "name": "meta",
              "type": "#/$defs/Meta",
              "required": true,
              "nullable": false,
              "meaning": "可信公共上下文"
            },
            {
              "name": "task_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "拟议等于 scan_id，不新增多余任务身份"
            },
            {
              "name": "scan_id",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "逻辑运行 ID"
            },
            {
              "name": "status",
              "type": "[\"queued\", \"running\", \"succeeded\", \"failed\", \"cancelled\"]",
              "required": true,
              "nullable": false,
              "meaning": "幂等重放可返回已终态任务"
            },
            {
              "name": "query_path",
              "type": "string",
              "required": true,
              "nullable": false,
              "meaning": "仅拟议新路由，不改变旧接口"
            },
            {
              "name": "retry_after_seconds",
              "type": "integer",
              "required": true,
              "nullable": false,
              "meaning": "轮询建议间隔，不代表完成时限"
            }
          ],
          "invariants": [
            "task_id=scan_id；run_scan 只返回此对象",
            "查询权限与创建权限分开；幂等重放可返回终态引用"
          ],
          "errors": [
            "AUTHENTICATION_REQUIRED",
            "OBJECT_NOT_FOUND",
            "DOMAIN_MISMATCH",
            "IDEMPOTENCY_CONFLICT",
            "TASK_TERMINAL"
          ],
          "compatibility": "新增独立 namespace；不改变资源/RAG/agent-runtime 既有返回；跨线类型映射需共同确认",
          "approval_status": "proposed"
        }
      ],
      "change_plan": [
        {
          "target": "backend/mainline1 与必要适配点（拟议）",
          "motivation": "独立主线一领域，不侵入教学语义",
          "dependencies": [
            "已批准资产/公共契约",
            "数据库范围",
            "模型数据政策"
          ],
          "priority": "P1",
          "authorization": "第2步设计授权；本轮另授权补齐第3步内部实现及合成隔离测试，生产迁移/接口发布仍未授权",
          "rollback": "design.md §11",
          "evidence_refs": [
            "step-01.md E03—E11"
          ]
        }
      ],
      "acceptance_cases": [
        {
          "id": "A01—A27",
          "source": "acceptance.md",
          "scope": "预登记功能及实验基线；第3步实际覆盖见新增状态表，后续步骤仍Untested"
        }
      ],
      "decisions_required": [
        {
          "id": "D01",
          "topic": "backend_only或minimal_ui；建议前者"
        },
        {
          "id": "D02",
          "topic": "资产所有者及跨线坐标/版本/执行契约共同确认"
        },
        {
          "id": "D03",
          "topic": "只剩生产持久化接入/业务库执行待决；内部迁移与隔离PostgreSQL验证已完成"
        },
        {
          "id": "D04",
          "topic": "真实后端/合成数据路径/费用预算，默认关闭"
        },
        {
          "id": "D05",
          "topic": "资源/保留策略与通知时限"
        }
      ],
      "open_questions": [
        {
          "id": "D01—D05",
          "status": "Unknown",
          "blocking_scope": "仅对应生产资产/公共契约发布/生产迁移/真实语义/交付模式与保留策略",
          "resolution_needed": "design.md §12，选项/推荐/取舍已列；内部实现和新建合成隔离库不再阻塞"
        }
      ]
    }
  },
  "artifacts": [
    "design.md",
    "contracts/schema.json",
    "contracts/catalog.json",
    "contracts/examples.json",
    "contracts/validate_examples.py",
    "acceptance.md",
    "history/handoff-step-01.md"
  ],
  "findings": [
    {
      "claim": "八项要求对应设计、Schema/catalog、29场景及预登记验收；草案检查通过不等于业务验收",
      "capability_status": "Implemented",
      "evidence_status": "Verified",
      "verification_status": "Passed",
      "confidence": "High",
      "evidence_refs": [
        "design.md",
        "acceptance.md",
        "step-03-verification.json checks[1]"
      ],
      "scope": "仅设计产物及有限草案约束，非识别实现"
    }
  ],
  "changes": {
    "motivation": "补齐遗漏交接并纠正过度阻塞判断",
    "scope": "设计注释/资产所有权说明/阶段记录与验收状态；公共schema和样例语义未改",
    "dependencies": [
      "第1步证据",
      "用户本轮审查补齐授权"
    ],
    "important_alternatives": "保留公共契约Proposed并开发内部适配端口，不单方面发布接口；不新建跨模块资产系统",
    "unverified_assumptions": "真实资产owner和执行方公共契约尚未提供",
    "rollback": "仅回退本轮docs增量；保留历史记录、用户提示词及第3步有效证据，不整体覆盖HANDOFF为第1步"
  },
  "verification": [
    {
      "command": "python -B docs/mainline1/contracts/validate_examples.py",
      "status": "Passed",
      "actual": "29场景/396对象/3个Schema拒绝/14个一致性拒绝；2026-10-13重跑",
      "scope": "草案校验，不是功能测试",
      "evidence": "step-03-verification.json checks[1]"
    },
    {
      "status": "Failed",
      "scope": "第2步中间一次合成样例校验",
      "actual": "正例因样例构建共享可变对象误把删除列2改为列1而PLAN_CONFLICT；修正样例后通过，未改变业务代码/拒绝规则"
    }
  ],
  "approved_decisions": [
    {
      "decision": "允许第2步设计与草案检查",
      "source": "用户第2步指令"
    },
    {
      "decision": "审查并补齐第2/3步已授权工作；不进入后续步骤",
      "source": "本轮用户消息"
    }
  ],
  "judgment_changes": [
    {
      "previous": "第2步已开始但尚无阶段记录",
      "current": "补记为partial，产物已存在，正式授权未补齐",
      "new_evidence_refs": [
        "当前工作区与会话"
      ],
      "impact": "第3步仅推进不依赖待批准内容的内部实现"
    },
    {
      "previous": "交接收尾缺失记partial，并把迁移编写/隔离测试一并待批准",
      "current": "设计已收尾complete；B4与当前补齐指令支持内部迁移和新建隔离合成库验证，生产执行仍未批准",
      "new_evidence_refs": [
        "用户本轮补齐第2/3步指令",
        "完整提示词B4",
        "step-03-postgres-verification.json"
      ],
      "impact": "移除常规内部工作的误阻塞；不推导公共契约Approved"
    }
  ],
  "open_questions": [
    {
      "id": "D01—D05",
      "status": "Unknown",
      "blocking_scope": "仅对应生产资产/公共契约发布/生产迁移/真实语义/交付模式与保留策略",
      "resolution_needed": "design.md §12，选项/推荐/取舍已列；内部实现和新建合成隔离库不再阻塞"
    }
  ],
  "next_step_constraints": [
    "第2步完成仅指可审阅设计，不代表14个公共契约已获批准",
    "第3步当前状态详见step-03.md；本轮不执行第4步",
    "真实公共接入先满足D02；生产配置/迁移及模型调用不得从本轮验证推导授权"
  ]
}
```
