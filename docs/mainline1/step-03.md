# 第3步：解析、定位与任务控制底座

2026-10-13 审查补齐。**status: partial**：本轮可独立实施的解析、定位、持久化任务和受管执行骨架已完成并验证；真实资产owner/生产权限与部署接入仍缺前置，不将其写成完成。未执行第4步。

| 用户要求 | 实际交付 | 边界 |
|---|---|---|
| 1 摘要/私有读取/范围 | read_private、verify_asset、normalize_scope；绑定固定字节和原坐标 | PrivateSource真实owner仍待指定；合成替身不能证明生产鉴权 |
| 2 CSV | 编码/方言/引号/多行/重复表头/逻辑记录全部有实际字节测试 | 不猜编码；失败显式报错 |
| 3 XLSX | sheet/隐藏/合并/公式文本/缓存状态/非单元格排除 | 不执行公式，不将缓存当新鲜输入；不支持路径拒绝 |
| 4 定位与逆映射 | 一基行列、零基Unicode码点；identity和内部NFKC逆映射 | 不可靠映射和部分连字操作拒绝；公共v1未扩展 |
| 5 资源/覆盖 | 大小、格/网格、ZIP声明及实际解压、XML、协作式时间/取消 | 非强制CPU/RSS隔离；失败不保留部分原文，也不伪装空成功 |
| 6 任务底座 | 三表持久化、唯一约束/CAS、取消/租约/重试/旧写回拒绝、原子产物、单次worker | 真实PostgreSQL验证；生产未注册/迁移/部署 |
| 7 配置与未执行识别 | 配置/范围/预算/解析器/Unicode版本快照，检测三层not_run | 任务成功只代表parsed_asset，不是扫描/复核/外发成功 |

操作说明见 [README](../../backend/mainline1/README.md)。验证原始结果见 [内部检查](step-03-verification.json) 和 [PostgreSQL检查](step-03-postgres-verification.json)。A01—A08/A27逐项实测边界见 [验收清单](acceptance.md)。

```json
{
  "step": "03",
  "status": "partial",
  "recorded_on": "2026-10-13",
  "repository_state": {
    "repository_root": "D:\\aaa10\\16015478源码\\project-code",
    "revision": "f4ac82caf32a4112c047cdb8848cab135acbb3c6",
    "branch": "feature/Sensitive-data-recognition",
    "tracked_changes": "none",
    "existing_work_preserved": [
      "用户三个未跟踪任务提示词",
      "step-01.md及history/handoff-step-01.md"
    ],
    "new_scope": [
      "backend/mainline1/",
      "docs/mainline1/"
    ],
    "rules": "未找到适用AGENTS；沿用.editorconfig及任务规范B4/F/E7；未读取.env或真实业务原文"
  },
  "mission": {
    "solved": [
      "固定字节摘要/私有读取端口/范围规范化",
      "实际CSV/XLSX解析、可靠坐标、显式排除和预算",
      "identity与内部可逆NFKC映射，不可靠位置禁止字符操作",
      "Django/PostgreSQL运行与尝试持久化、幂等/CAS/取消/租约/显式受限重试/旧尝试拒绝",
      "受管单次worker骨架、私有解析产物与完成状态原子发布、版本化配置快照",
      "41项内部测试、13项真实PostgreSQL测试、空隔离库正反迁移；补齐交接"
    ],
    "not_solved": [
      "真实资产owner未指定；生产鉴权/稳定读取/TOCTOU和部署私有性未验收",
      "公共契约仍Proposed，没有发布API/生产任务注册或业务库迁移",
      "生产进程强制CPU/RSS/累计墙钟预算与故障注入未验证；跨语言公共规范化/hash契约未验证"
    ]
  },
  "stage_result": {
    "schema": "mainline1.stage3.v1 / E7",
    "data": {
      "changes": [
        "新增独立mainline1内部模块/测试/迁移与交接；未改既有业务模块、公共接口、生产配置或依赖清单"
      ],
      "parser_adapters": [
        {
          "format": "csv",
          "implementation": "backend/mainline1/parsing.py _csv",
          "supports": "显式utf-8/utf-8-sig/gb18030、单字符分隔符、引号/双引号转义、多行字段、逻辑记录、重复/空表头按列号保留",
          "failure": "空文件/编码/列宽/格式/预算拒绝；无自动编码猜测"
        },
        {
          "format": "xlsx",
          "implementation": "backend/mainline1/parsing.py _xlsx（含ZIP/XML预检）",
          "supports": "版本内sheet ID、多sheet/隐藏行列sheet、合并锚点与别名、原始数值/类型/number_format、公式文本及缓存存在状态",
          "failure": "不执行公式；缓存不检测/不声称新鲜；复杂公式/错误格/宏/加密/越界ZIP/XML明确拒绝；批注/超链接目标/图片/文本框排除"
        }
      ],
      "location_contract": {
        "rows_columns": "一基；CSV按逻辑记录含表头，默认表头不检测；XLSX绝对格坐标",
        "characters": "零基Unicode码点半开[start,end)，不是UTF16/字节/字素；source_span输入规范化文本区间，返回原文区间",
        "normalization": "默认identity-v1；内部可选nfkc-mapped-v1，原文不覆盖、组合序列/展开字符必须整体映射；跨组组合无法证明时拒绝字符操作",
        "version": "internal-table-v2；Unicode数据版本保存到运行及解析快照；公共草案v1仍仅identity",
        "scope": "按资产版本绑定、闭区间排序去重合并、sheet唯一、原坐标不重编号；缺合并锚点拒绝"
      },
      "version_checks": [
        "read_private每次要求owner鉴权；本层核对principal/domain/state、大小、sha256并关闭流",
        "parse_table再核对输入摘要/大小/状态；scope资产版本不匹配拒绝",
        "运行快照含原资产引用/配置/预算/范围/解析器/Unicode版本；幂等请求指纹含trusted domain/environment/evaluation/principal",
        "发布核对输入版本/hash、解析版本、config_hash及显式scope_hash；不同配置不发布"
      ],
      "task_skeleton": {
        "mechanism": "复用Django ORM/transaction.atomic/select_for_update及现有RAG令牌模式；不能直接复用RAG会embedding的同步管线/其业务表",
        "storage": "ParseRun/ParseAttempt/ParsedArtifact独立私有领域表，唯一作用域幂等键、unique(run,number)、PROTECT引用；未创建资产管理表",
        "run_attempt": "一个逻辑run，claim创建独立attempt/token；旧attempt终态不可覆盖；同run受限重试保持快照，重扫需新幂等键",
        "atomicity": "父行锁跨run/attempt读取，revision CAS；成功和产物单事务提交，产物写失败回滚状态；cancel先提交则不生成产物，成功先提交则取消被拒绝",
        "recovery": "租约到期通过recover_expired标旧尝试expired/failed；有cancel则cancelled；显式retry携带expected_attempt和幂等键；最多max_attempts（默认2）",
        "execution": "run_parse_worker每次最多检查100个运行并执行一个任务，由外部进程管理器调度；不创建Web线程、不安装队列；缺source factory时关闭",
        "budgets": "固定Limits每次读取/解析协作式截止，lease=2*max_seconds+30；重试次数不重置；不声称生产累计CPU/墙钟/费用强制预算",
        "result": "只有parsed_asset；detection_status=not_run、scan_quality=unavailable；不等于ScanResult成功/复核完成/外发授权"
      },
      "coverage_behavior": {
        "parse": "配置和选区内有效格作为分母，表头/隐藏/合并别名独立逐项排除；实际processed坐标可枚举；零分母ratio=null",
        "detection": "rule/semantic/combination=not_run，target=null、processed=0、ratio=null",
        "failure": "错误/超限/取消返回稳定原因码；当前不保存部分解析原文；任务失败不以空结果代替",
        "public_boundary": "内部DTO不是公共契约序列化；需要owner可信meta、公共ID/范围/hash/覆盖/映射适配，见design §13"
      },
      "verification": [
        "step-03-verification.json",
        "step-03-postgres-verification.json",
        "acceptance.md 第3步实际验收范围"
      ],
      "open_questions": [
        {
          "id": "D02",
          "status": "Unknown",
          "blocking_scope": "真实资产私有读取、对象权限、公共ParsedAsset/TaskReference接入",
          "resolution_needed": "由哪个既有owner提供逐次鉴权的固定版本读取？推荐提供现有私有资产服务契约/适配位置；若选择扩展resources，需另确认其公开审核语义、域ACL和不可变版本改造，不能直接把resources文件接入。跨线owner共同确认Proposed v1后才能公开发布。"
        },
        {
          "id": "D03",
          "status": "Unknown",
          "blocking_scope": "生产启用三个解析领域表、生产worker及业务库迁移",
          "resolution_needed": "推荐继续隔离运行直至指定部署环境与迁移窗口；选择生产启用须独立确认app注册、私有库权限、保留/备份和进程限制。本轮内部代码和新建合成测试库已经完成，不再重复申请。"
        },
        {
          "id": "D01/D04/D05",
          "status": "Unknown",
          "blocking_scope": "第5/8步真实语义、交付界面、生产保留/资源预算",
          "resolution_needed": "design.md §12列具体选项。推荐backend_only、真实模型关闭；minimal_ui另含页面验收成本；真实后端需model/数据路径/金额预算；生产保留期限不采用开发候选值自动删除。"
        }
      ]
    }
  },
  "artifacts": [
    {
      "path": "backend/mainline1/parsing.py",
      "purpose": "受限解析、版本读取端口与可靠位置"
    },
    {
      "path": "backend/mainline1/tasks.py",
      "purpose": "不可变运行/尝试状态机"
    },
    {
      "path": "backend/mainline1/models.py + migrations/0001_initial.py + repository.py",
      "purpose": "PostgreSQL持久化/原子发布，迁移仅测试库验证"
    },
    {
      "path": "backend/mainline1/worker.py + management/commands/run_parse_worker.py",
      "purpose": "同步受管执行单元，等待真实owner注入"
    },
    {
      "path": "backend/mainline1/tests/ + test_settings.py",
      "purpose": "合成解析/状态机/真实PostgreSQL定向测试与隔离环境，不加载生产settings"
    },
    {
      "path": "backend/mainline1/README.md",
      "purpose": "运行方式、内部契约、局限和回滚"
    },
    {
      "path": "docs/mainline1/step-03-verification.json + step-03-postgres-verification.json",
      "purpose": "实际命令输出、源码摘要和验证范围"
    }
  ],
  "findings": [
    {
      "claim": "解析/映射/状态机内部能力已实现并通过定向合成测试",
      "capability_status": "Implemented",
      "evidence_status": "Verified",
      "confidence": "High",
      "verification_status": "Passed",
      "evidence_refs": [
        "backend/mainline1/tests/test_parsing.py",
        "backend/mainline1/tests/test_tasks.py",
        "step-03-verification.json"
      ]
    },
    {
      "claim": "真实PostgreSQL持久化、多连接竞争及独立进程读取可用；不是内存测试替身或SQLite结论",
      "capability_status": "Implemented",
      "evidence_status": "Verified",
      "confidence": "High",
      "verification_status": "Passed",
      "evidence_refs": [
        "backend/mainline1/tests/postgres_cases.py",
        "step-03-postgres-verification.json"
      ]
    },
    {
      "claim": "真实owner/生产调度和跨模块公共接入尚未完成",
      "capability_status": "Partial",
      "evidence_status": "Verified",
      "confidence": "High",
      "verification_status": "Blocked",
      "evidence_refs": [
        "backend/mainline1/parsing.py PrivateSource",
        "backend/mainline1/management/commands/run_parse_worker.py",
        "design.md D02/D03"
      ]
    },
    {
      "claim": "完整规则/语义/联合风险尚未执行，不能声称识别完成",
      "capability_status": "Missing",
      "evidence_status": "Verified",
      "confidence": "High",
      "verification_status": "Untested",
      "evidence_refs": [
        "coverage_json",
        "Run.detection_status",
        "用户只审查第2/3步指令"
      ]
    }
  ],
  "changes": {
    "motivation": "修补只有纯状态机、缺真实持久化/恢复验收、NFKC映射和交接缺失",
    "scope": "仅新mainline1内部领域，不触动既有业务代码/接口/数据库/生产配置",
    "dependencies": [
      "已有Django/psycopg2/openpyxl",
      "Python标准库csv/unicodedata",
      "已安装PostgreSQL16仅测试",
      "jsonschema仅草案检查；未安装升级或新增requirements"
    ],
    "important_alternatives": [
      "拒绝用RepositoryDouble/SQLite证明数据库并发",
      "不把敏感资产送入自动embedding的RAG管线",
      "不为主线一新建跨模块资产系统",
      "无新Celery/Redis，采用Django命令受管执行单元"
    ],
    "unverified_assumptions": [
      "真实owner能提供逐次对象鉴权和稳定流",
      "生产DB角色/保留/worker隔离需部署方案"
    ],
    "rollback": "本轮业务库未改变；按文件清单回退本任务新文件/交接增量，保留用户提示词、step01和其他任务修改；不用git reset/clean。空合成库reverse已通过，不能外推含真实数据可直接drop；以后生产启用先停新任务/worker并评估历史引用/保留。"
  },
  "verification": [
    {
      "command": "python -B -m unittest discover -s mainline1/tests -v",
      "cwd": "backend",
      "status": "Passed",
      "actual": "41项，真实CSV/XLSX解析+状态机测试替身；不是模型/生产owner验证",
      "evidence": "step-03-verification.json checks[0]"
    },
    {
      "command": "python -B mainline1/tests/run_isolated_postgres.py",
      "cwd": "backend",
      "status": "Passed",
      "actual": "13项真实PostgreSQL事务/多连接/子进程测试；check无问题、makemigrations --check无漂移、空库正反迁移；最终临时集群已停止并清理",
      "evidence": "step-03-postgres-verification.json"
    },
    {
      "command": "ast.parse on backend/mainline1/**/*.py",
      "status": "Passed",
      "actual": "18文件静态语法检查，SHA256见证据；非类型/安全全覆盖",
      "evidence": "step-03-verification.json ast/code_sha256"
    },
    {
      "command": "python -B docs/mainline1/contracts/validate_examples.py",
      "status": "Passed",
      "actual": "29场景396对象；仅第2步草案，不算第3步功能测试",
      "evidence": "step-03-verification.json checks[1]"
    },
    {
      "status": "Failed",
      "scope": "中间验证过程，已修复并重跑",
      "actual": "第一次Windows pg_ctl输出管道挂起，未运行测试；改为文件输出。第二次一个测试误期望PARSE_FAILED，实际read_private按既定语义正确返回ASSET_UNAVAILABLE；修正期望。输出编码随后改UTF-8，解决GBK日志打印错误。初次makemigrations连接未启动的隔离端口被拒，未写任何库。"
    },
    {
      "status": "Blocked",
      "scope": "真实资产/生产持久化接入、生产worker、公共契约发布",
      "actual": "见D02/D03，未把合成owner替身算作生产权限验收"
    },
    {
      "status": "Untested",
      "scope": "规则/语义/联合识别、UI、下游执行、公共跨语言hash、生产进程硬限制",
      "actual": "不在本轮实现或无真实前置；真实模型未发起调用"
    }
  ],
  "approved_decisions": [
    {
      "decision": "只审查并补齐第2/3步；允许对应内部代码/合成样本/定向测试/交接，不进入第4步",
      "source": "本轮用户指令及后续continue（继续同一任务）"
    },
    {
      "decision": "内部迁移文件与新建合成隔离库验证按普通内部实现推进；不执行既有业务库迁移",
      "source": "本轮补齐指令 + 完整提示词B4明确分开判断迁移编写/隔离验证/业务库执行"
    }
  ],
  "judgment_changes": [
    {
      "previous": "任务底座只有状态机/RepositoryDouble，真实数据库实现及验证被整体标Blocked",
      "current": "新增真实Django/PostgreSQL后端、原子产物、受管执行单元并经13项实际测试；生产接入仍Blocked",
      "new_evidence_refs": [
        "规范B4",
        "本轮补齐授权",
        "step-03-postgres-verification.json"
      ],
      "impact": "不再让常规内部实现等批准；不把测试环境授权扩大为业务库执行"
    },
    {
      "previous": "仅identity映射，其他规范化显式拒绝",
      "current": "保留默认identity，补充内部nfkc-mapped-v1且不可靠映射拒绝字符级操作；公共v1未改变",
      "new_evidence_refs": [
        "test_nfkc_maps_fullwidth_emoji_and_combining_to_source",
        "test_unproven_cross_cluster_mapping_disables_character_operations",
        "test_normalization_expansion_obeys_cell_budget"
      ],
      "impact": "满足全角/组合字符规范化验证；公共导出仍必须走已确认版本适配"
    },
    {
      "previous": "HANDOFF停留第1步，step03未落盘",
      "current": "第2步设计收尾complete；第3步内部底座完成、真实owner及生产接入仍partial；最终HANDOFF已更新",
      "new_evidence_refs": [
        "step-02.md",
        "step-03.md",
        "HANDOFF.md"
      ],
      "impact": "后续只消费已验证范围，不误认为公共/生产扫描已上线"
    }
  ],
  "open_questions": [
    {
      "id": "D02",
      "status": "Unknown",
      "blocking_scope": "真实资产私有读取、对象权限、公共ParsedAsset/TaskReference接入",
      "resolution_needed": "由哪个既有owner提供逐次鉴权的固定版本读取？推荐提供现有私有资产服务契约/适配位置；若选择扩展resources，需另确认其公开审核语义、域ACL和不可变版本改造，不能直接把resources文件接入。跨线owner共同确认Proposed v1后才能公开发布。"
    },
    {
      "id": "D03",
      "status": "Unknown",
      "blocking_scope": "生产启用三个解析领域表、生产worker及业务库迁移",
      "resolution_needed": "推荐继续隔离运行直至指定部署环境与迁移窗口；选择生产启用须独立确认app注册、私有库权限、保留/备份和进程限制。本轮内部代码和新建合成测试库已经完成，不再重复申请。"
    },
    {
      "id": "D01/D04/D05",
      "status": "Unknown",
      "blocking_scope": "第5/8步真实语义、交付界面、生产保留/资源预算",
      "resolution_needed": "design.md §12列具体选项。推荐backend_only、真实模型关闭；minimal_ui另含页面验收成本；真实后端需model/数据路径/金额预算；生产保留期限不采用开发候选值自动删除。"
    }
  ],
  "next_step_constraints": [
    "本轮结束停止，不自动进入第4步或修改其他任务线",
    "第4步只可在用户另行指令及分类字典/等级政策前置满足后消费已验证内部解析产物；解析成功不是扫描成功",
    "真实资产接入先确认D02的owner/对象权限/版本稳定读取；发布公共契约必须经相关owner确认，所有草案仍Proposed",
    "未批准生产app注册、业务库迁移、生产worker部署、依赖安装、真实模型调用/原文外发、数据删除或下游决策撤销",
    "失败/取消必须保留任务原因码和未执行识别状态；不以空内容成功/Mock/规则路径替代真实语义证据"
  ],
  "local_cleanup_note": "首轮已停止的临时集群目录 mainline1-synthetic-pg-633pg7hs 递归清理被自动审批策略拒绝，仅给出blocked by policy，已保留，未绕过；后续脚本创建的集群正常停止并清理。残留仅新建合成隔离目录，不含业务原文或凭据。"
}
```
