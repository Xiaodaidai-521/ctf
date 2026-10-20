# 第7步：脱敏计划生成与纯业务校验

2026-10-15；**step / status: 07 / partial**。独立内部实现及必要验证完成；正式保护要求/共同操作契约仍为 Proposed，生产 owner 和真实执行层未接入。停止等待第8步。

[接入与待决方案](plan-design-v1.md) · [契约样例](plan-examples-v1.json) · [本地验证](step-07-verification.json) · [隔离数据库验证](step-07-postgres-verification.json)

141项本地测试（32本步＋109前序）Passed；39项隔离PostgreSQL测试（3本步＋36前序）Passed，另有system check、迁移漂移、正反向迁移检查。真实解析、规则、复核逻辑使用合成输入；资产/政策/许可/ACL为测试替身。真实语义调用0次，实际执行层Untested。

```json
{
  "step": "07",
  "status": "partial",
  "recorded_on": "2026-10-15",
  "repository_state": {
    "root": "D:/aaa10/16015478源码/project-code",
    "revision": "f4ac82caf32a4112c047cdb8848cab135acbb3c6",
    "branch": "feature/Sensitive-data-recognition",
    "rules": "未找到适用AGENTS/CLAUDE；遵循完整任务提示词、共同交接约定及.editorconfig",
    "existing_work": "前序mainline1与用户提示词均未跟踪；step-07-input-state.json保存原摘要；未提交",
    "input_configuration": {
      "product_spec": "完整任务提示词B/C/D/F/J",
      "approved_contracts": "Unknown；现有公共契约为Proposed",
      "approved_change_scope": "第7步独立内部实现、样例、测试和交接",
      "approved_dependencies": "未新增；标准库及现有测试依赖",
      "approved_schema_changes": "本步无迁移或数据库schema变更；仅全新合成隔离库验证既有迁移",
      "semantic_backend": "Unknown；零调用",
      "data_policy": "合成输入，无原文外发",
      "delivery_mode": "内部后端组件；不视为正式交付模式批准",
      "acceptance_targets": "本步指定功能及失败边界；生产效果/性能门槛Unknown",
      "resource_budget": "内部每实例100计划、每请求100要求、1000目标/操作；非生产容量承诺"
    }
  },
  "mission": {
    "solved": [
      "计划绑定固定资产/内容摘要/扫描/画像/范围/解析配置/政策/规范化要求",
      "白名单操作、受控内容匹配、原始快照组合语义及不确定项处理",
      "独立覆盖和冲突校验、当前适用性复查、无业务写入",
      "固定计划摘要、分页一致性、有限进程内幂等及可审阅契约样例"
    ],
    "not_solved": [
      "正式保护政策、要求来源与执行方共同契约批准",
      "生产资产/政策owner的权威读取组合、跨owner检查与使用之间的并发保护",
      "真实执行适配及外发验证、生产持久化计划与跨进程幂等、生产性能和保留策略"
    ]
  },
  "artifacts": [
    {"file": "backend/mainline1/planning.py", "purpose": "PlanService.build/validate/page与内部输入端口、操作/覆盖校验"},
    {"file": "backend/mainline1/review.py", "purpose": "read协议、内存只读快照、read_plan_basis权限门禁"},
    {"file": "backend/mainline1/review_repository.py", "purpose": "Django只读SELECT路径，不创建缺失账本"},
    {"file": "backend/mainline1/tests/test_planning.py", "purpose": "32项定向合成行为测试"},
    {"file": "backend/mainline1/tests/postgres_planning_cases.py", "purpose": "3项真实隔离SQL只读及重连检查"},
    {"file": "backend/mainline1/tests/run_planning_postgres.py", "purpose": "复用全新集群生命周期并单独保存第7步证据"},
    {"file": "docs/mainline1/verify_step07.py", "purpose": "本地回归、样例校验/生成、源码摘要及前序保护证据"},
    {"file": "docs/mainline1/plan-design-v1.md", "purpose": "契约、状态、限制、具体待决及回滚"},
    {"file": "docs/mainline1/plan-examples-v1.json", "purpose": "虚构许可ready/实际draft invalid/固定分页样例；不含敏感原文"},
    {"file": "docs/mainline1/history/handoff-step-06.md", "purpose": "原样保留第6步HANDOFF"}
  ],
  "findings": [
    {
      "id": "F7-internal-plan",
      "claim": "计划生成、纯校验和分页在合成规则路径已实现并验证",
      "capability_status": "Implemented", "evidence_status": "Verified", "confidence": "High", "verification_status": "Passed",
      "evidence_refs": [{"source": "repository", "location": "step-07-verification.json", "observation": "141 tests Passed; AST/example/preservation Passed", "supports": "32本步功能边界及109前序回归", "does_not_support": "生产政策、真实语义或交付执行"}]
    },
    {
      "id": "F7-readonly",
      "claim": "成功/失败/缺失账本校验只执行SELECT，重连后拒绝被人工补录替代的旧画像计划",
      "capability_status": "Implemented", "evidence_status": "Verified", "confidence": "High", "verification_status": "Passed",
      "evidence_refs": [{"source": "repository", "location": "step-07-postgres-verification.json", "observation": "39 tests and 4 system/migration checks Passed; fresh cluster stopped and removed", "supports": "隔离真实PostgreSQL只读及前序事务回归", "does_not_support": "生产owner ACL、跨owner原子执行或业务库部署"}]
    },
    {
      "id": "F7-public-execution",
      "claim": "公共契约仍Proposed，真实执行未接入；draft条件不能产生可用计划",
      "capability_status": "Partial", "evidence_status": "Verified", "confidence": "High", "verification_status": "Blocked",
      "evidence_refs": [{"source": "repository", "location": "plan-design-v1.md", "observation": "默认批准标记false；当前draft画像usable=false；无生产InputSource或执行适配", "supports": "正式接入边界及待决方案", "does_not_support": "已批准或生产可外发"}]
    }
  ],
  "changes": [
    {
      "target": "planning.py、计划测试、样例、校验脚本和第7步文档",
      "motivation": "生成定位明确的计划并独立检查指定要求覆盖",
      "dependencies": ["第3步解析快照", "第4—5步发现/画像", "第6步适用性", "既有Proposed Schema"],
      "priority": "P1", "authorization": "用户第7步及continue；完整提示词B3/B4允许内部适配和验证",
      "alternatives": "直接公开API/执行文件缺批准且超本步；持久化计划服务延后；不改变共同语义",
      "unverified_assumptions": "生产InputSource按契约鉴权、只读且返回一致权威观察；版本不可变",
      "rollback": "只撤回本步新增文件；不reset/clean或处理业务数据",
      "evidence_refs": [{"source": "repository", "location": "step-07-verification.json", "observation": "本地测试及样例检查Passed", "supports": "内部可验证行为", "does_not_support": "生产接入"}]
    },
    {
      "target": "review.py、review_repository.py、run_isolated_postgres.py、README.md、HANDOFF.md",
      "motivation": "独立只读入口避免atomic路径创建账本；复用隔离测试并保存本步证据",
      "dependencies": ["既有ReviewRepository和Django模型", "已安装PostgreSQL16"],
      "priority": "P1", "authorization": "本步内部必要适配及隔离验证",
      "alternatives": "复用atomic会在空仓储get_or_create；改为单次SELECT读取固定aggregate",
      "unverified_assumptions": "单行aggregate适用于小规模内部验证；未验证生产吞吐",
      "rollback": "撤回新增read/read_plan_basis、证据文件白名单和README增量；恢复history/handoff-step-06.md；无数据库回滚",
      "evidence_refs": [{"source": "repository", "location": "step-07-postgres-verification.json", "observation": "捕获查询均SELECT；缺失账本保持不存在", "supports": "无业务写入副作用", "does_not_support": "全平台生产部署"}]
    }
  ],
  "verification": [
    {"name": "本地行为与前序回归", "level": 2, "status": "Passed", "scope": "仓库根python -B docs/mainline1/verify_step07.py；141项=32本步+109前序", "evidence_refs": [{"source": "repository", "location": "step-07-verification.json", "observation": "exit_code=0; 141 tests OK", "supports": "本步定向功能及前序回归", "does_not_support": "真实语义或执行"}], "gap": "许可/ACL/资产政策源是替身"},
    {"name": "隔离数据库只读与回归", "level": 3, "status": "Passed", "scope": "backend: python -B -m mainline1.tests.run_planning_postgres；39项=3本步+36前序；另4项系统/迁移检查", "evidence_refs": [{"source": "repository", "location": "step-07-postgres-verification.json", "observation": "全部Passed; stopped=true; temporary_cluster_removed=true", "supports": "实际SELECT/不存在时不创建/重连失效", "does_not_support": "既有业务库迁移或生产ACL"}], "gap": "全新合成集群"},
    {"name": "静态/样例/保留检查", "level": 1, "status": "Passed", "scope": "7个相关Python文件AST；ready/invalid兼容未改Proposed Schema；分页重组hash；前序摘要保护", "evidence_refs": [{"source": "repository", "location": "step-07-verification.json", "observation": "ast_status/example_status/preservation_status=Passed", "supports": "草案结构与改动边界", "does_not_support": "公共契约批准或跨语言实现"}], "gap": null},
    {"name": "真实执行层", "level": 3, "status": "Untested", "scope": "脱敏文件输出、执行顺序实现、外发与跨owner检查后变化防护", "evidence_refs": [], "gap": "本步不接入或执行"},
    {"name": "正式公共接入", "level": 3, "status": "Blocked", "scope": "权威保护要求、共同操作契约、生产owner与政策", "evidence_refs": [], "gap": "前序和本步没有实质批准记录"},
    {"name": "真实语义与生产规模", "level": 4, "status": "Untested", "scope": "真实模型效果、生产吞吐、跨进程持久化幂等", "evidence_refs": [], "gap": "零模型调用；内部有限内存计划登记，非生产发布"}
  ],
  "approved_decisions": [
    {"decision": "执行第7步内部生成/校验/测试/交接，结束等待第8步", "source": "用户第7步指令及continue"},
    {"decision": "使用既有依赖、内部适配和全新合成隔离库验证；不包含公共批准或业务库操作", "source": "完整提示词B3/B4、前序有效授权及本步必要验证"}
  ],
  "judgment_changes": [
    {"previous": "第6步没有计划能力", "current": "内部计划/纯校验/分页已实现并验证；正式执行仍未接入", "new_evidence_refs": ["step-07-verification.json", "step-07-postgres-verification.json"], "affected_decisions": ["可交接内部产物；不能交接为生产外发就绪"]},
    {"previous": "首轮成功用例使用默认semantic_required=true", "current": "原校验正确识别覆盖不完整；成功用例显式采用仅规则扫描策略，另测不完整覆盖", "new_evidence_refs": ["tests/test_planning.py", "step-07-verification.json"], "affected_decisions": ["不放宽覆盖判断来使测试通过"]},
    {"previous": "首轮游标过期被ValueError通用分支转换为CURSOR_INVALID", "current": "单独保留InputError，返回CURSOR_EXPIRED", "new_evidence_refs": ["test_cursor_signature_scope_expiry_and_page_size"], "affected_decisions": ["稳定错误码已修正"]},
    {"previous": "首轮受限环境initdb失败，尚无数据库验证证据", "current": "既有隔离验证命令经沙箱升级运行成功并清理新集群", "new_evidence_refs": ["step-07-postgres-verification.json"], "affected_decisions": ["仅将隔离数据库路径提升为Verified；未连接业务库"]}
  ],
  "open_questions": [
    {"id": "Q7-contract-policy", "status": "Unknown", "blocking_scope": "正式保护要求、公共计划接入和执行层验证", "resolution_needed": "审阅plan-design-v1.md；推荐保持内部Proposed。发布前由政策owner/执行方共同确认原快照组合语义、不确定项政策、要求来源及版本、权威状态/匹配端口、权限及检查后变化规则"},
    {"id": "inherited-D02-D03-D04-D05-Q6", "status": "Unknown", "blocking_scope": "生产owner/部署、真实模型及数据费用、组合政策、事件信封和保留", "resolution_needed": "沿用前序交接待决及已有批准；本步不撤回授权也不扩大授权"}
  ],
  "next_step_constraints": [
    "停止等待第8步；进入下一步不是当前或前序验收证据",
    "只消费满足前置且已验证的内部画像/解析/适用性/计划产物；样例ready仅合成许可",
    "plan_hash不等于授权；执行前再次查权威状态并校验；不得依赖通知或历史valid永久放行",
    "不生成交付副本、不预占额度、不创建共享、不单方规定执行内部算法",
    "无生产公共发布、真实原文外发、模型调用或业务库执行授权"
  ],
  "stage_result": {
    "schema": "mainline1.step7.plan.v1 / E7-stage4-4C-plan-subset",
    "data": {
      "milestone_results": {
        "4C": {
          "delivered": ["内部计划生成与纯校验", "固定摘要、进程内幂等、分页", "只读复核仓储适配", "契约样例、功能及隔离数据库证据"],
          "not_delivered": ["正式契约及保护政策批准", "生产权威输入组合", "真实执行层", "生产持久化计划服务"],
          "changes": [{"target": "backend/mainline1/planning.py及本步列示增量", "motivation": "第7步计划与纯校验", "dependencies": ["第3—6步已验证内部产物"], "priority": "P1", "authorization": "用户第7步及continue；B3/B4内部实现", "rollback": "仅撤回本步新增文件和列示增量；保留前序与业务数据", "evidence_refs": [{"source": "repository", "location": "step-07-verification.json", "observation": "141 tests Passed", "supports": "内部计划及回归", "does_not_support": "生产执行"}]}],
          "verification": [{"name": "计划行为与数据库只读", "level": 3, "status": "Passed", "scope": "141本地及39隔离数据库测试", "evidence_refs": [{"source": "repository", "location": "step-07-postgres-verification.json", "observation": "39 tests Passed and cluster removed", "supports": "SQL只读/旧画像失效及回归", "does_not_support": "生产部署或外发"}], "gap": "真实执行未接入；合成许可不代表批准"}]
        }
      },
      "open_questions": [{"id": "Q7-contract-policy", "status": "Unknown", "blocking_scope": "公共接入与真实执行", "resolution_needed": "按plan-design-v1.md由政策owner和执行方共同批准后接入"}]
    }
  }
}
```
