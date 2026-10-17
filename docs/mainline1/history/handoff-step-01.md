# 主线一交接

实际交接目录：`docs/mainline1/`（本轮未找到既有正式目录，故新建）。

当前：第 1 步源码核查完成；等待第 2 步指令。主线一业务能力尚未实现。详细证据与可复现命令见 [step-01.md](step-01.md)。没有需要阻塞本步的待决项，后续受影响范围见 Q01—Q05。

```json
{
  "step": "01",
  "status": "complete",
  "stage_result": {
    "schema": "mainline1.stage1.v1 / E7",
    "data": {
      "repository_state": {
        "repository_root": "D:\\aaa10\\16015478源码\\project-code",
        "revision": "f4ac82caf32a4112c047cdb8848cab135acbb3c6",
        "branch": "feature/Sensitive-data-recognition",
        "initial_untracked": [
          "docs/主线一-上下文敏感数据识别-任务提示词.md",
          "docs/主线一-分阶段实施验证提示词.md",
          "docs/受控外发与执行-分阶段实现提示词-数据库增强版.md"
        ],
        "handoff_location": "docs/mainline1",
        "tracked_changes_at_start": []
      },
      "capabilities": [
        {
          "id": "C01",
          "name": "认证与角色基础",
          "capability_status": "Implemented",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E08"
          ],
          "limitations": "只评价现有认证/角色代码；主线一对象权限尚需适配"
        },
        {
          "id": "C02",
          "name": "上传和私有资产存储",
          "capability_status": "Partial",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E03",
            "E04"
          ],
          "limitations": "有上传/受控下载，但不可直接满足敏感资产域隔离和不可变版本"
        },
        {
          "id": "C03",
          "name": "CSV/XLSX 精确定位解析",
          "capability_status": "Missing",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E05",
            "E12"
          ],
          "limitations": "限定已检索 backend Python 与当前 RAG 链路；有文本转换不等于目标定位解析"
        },
        {
          "id": "C04",
          "name": "扫描任务底座",
          "capability_status": "Partial",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E06",
            "E12"
          ],
          "limitations": "可借用持久状态/事务/令牌模式，尚无完整扫描调度、取消与尝试契约"
        },
        {
          "id": "C05",
          "name": "真实模型传输适配",
          "capability_status": "Implemented",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E07"
          ],
          "limitations": "只确认真实 API 调用代码，不确认运行可用或敏感分类能力"
        },
        {
          "id": "C06",
          "name": "已批准且可用的主线一语义后端",
          "capability_status": "Unknown",
          "evidence_status": "Verified",
          "verification_status": "Blocked",
          "confidence": "Medium",
          "evidence_refs": [
            "E07"
          ],
          "limitations": "未提供主线一模型、数据出域与预算批准；真实验证 Blocked"
        },
        {
          "id": "C07",
          "name": "最小审计与下游通知",
          "capability_status": "Partial",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E09",
            "E12"
          ],
          "limitations": "已有数据库审计/账本，需最小化载荷；可靠事件发布尚缺"
        },
        {
          "id": "C08",
          "name": "分类/画像/复核/计划/版本适用性闭环",
          "capability_status": "Missing",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E10",
            "E05",
            "E06"
          ],
          "limitations": "限本次 backend/frontend 源码检索范围；法律业务的类似名称不等价"
        },
        {
          "id": "C09",
          "name": "前端操作基础",
          "capability_status": "Partial",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E11"
          ],
          "limitations": "现有框架可直接复用，扫描业务页面需适配或新建；delivery_mode 未定"
        },
        {
          "id": "C10",
          "name": "当前解释器依赖一致性",
          "capability_status": "Partial",
          "evidence_status": "Verified",
          "verification_status": "Untested",
          "confidence": "High",
          "evidence_refs": [
            "E02",
            "E13"
          ],
          "limitations": "仅当前 Python，未核查其他环境；未安装/升级任何包"
        }
      ],
      "dependency_map": {
        "incoming": [
          "资源/RAG/agent-runtime/学习分析/知识库入口，详见 step-01 dependency_map"
        ],
        "outgoing": [
          "ORM、私有存储候选、外部 provider、共享向量库和审计，详见 step-01"
        ],
        "implicit_contracts": [
          "RAG 全局 hash 去重/同步重入/可见性角色不等于资产权限；完整约定见 step-01"
        ]
      },
      "reuse_decisions": [
        {
          "target": "认证、Django ORM 事务、Axios/基础布局",
          "decision": "可直接复用基础组件",
          "evidence_refs": [
            "E02",
            "E08",
            "E11"
          ]
        },
        {
          "target": "上传校验与受控下载",
          "decision": "需要适配",
          "evidence_refs": [
            "E03",
            "E04"
          ]
        },
        {
          "target": "RAG parser/pipeline",
          "decision": "不作为精确表格解析器复用；新建表格解析及位置映射",
          "evidence_refs": [
            "E05",
            "E13"
          ]
        },
        {
          "target": "任务持久化与 ownership token",
          "decision": "需要适配机制；新建主线一 scan/attempt 领域",
          "evidence_refs": [
            "E06"
          ]
        },
        {
          "target": "BaseProvider/ChatResponse",
          "decision": "需要适配",
          "evidence_refs": [
            "E07"
          ]
        },
        {
          "target": "AuditEvent/AuditLedgerService",
          "decision": "需要适配",
          "evidence_refs": [
            "E09"
          ]
        },
        {
          "target": "分类政策、可信上下文、发现画像、人工复核、适用状态、计划纯校验",
          "decision": "新建",
          "evidence_refs": [
            "E10"
          ]
        },
        {
          "target": "真实后端/部署资产服务/正式跨线契约",
          "decision": "未知",
          "evidence_refs": [
            "E01",
            "E07"
          ]
        }
      ],
      "open_questions": [
        {
          "id": "Q01",
          "status": "Unknown",
          "blocking_scope": "后续资产/范围/画像/事件/执行契约接入",
          "resolution_needed": "正式 owner 和已批准契约位置 Unknown。第2步先提交 Proposed 契约，明确资产所有者、定位基数/Unicode 单位、版本/范围/hash、画像替代、权威适用状态、事件延迟/去重以及计划组合语义；不得自行批准跨线不兼容变化。"
        },
        {
          "id": "Q02",
          "status": "Unknown",
          "blocking_scope": "真实语义调用及 A/B/C 效果验收",
          "resolution_needed": "semantic_backend、允许数据、调用预算 Unknown。推荐先保持网络调用禁用；第2步形成固定 provider/model、合成样本烟测、超时/成本上限的可审阅方案，再请求具体批准。真实敏感原文外发仍禁止。"
        },
        {
          "id": "Q03",
          "status": "Unknown",
          "blocking_scope": "后续持久化实现与迁移",
          "resolution_needed": "approved_schema_changes Unknown，现有任务表不满足目标。推荐先设计独立领域表及与资产 owner 的引用；迁移文件编写、隔离测试库验证、业务库执行分别确认范围；本步均不做。"
        },
        {
          "id": "Q04",
          "status": "Unknown",
          "blocking_scope": "运行/部署与安全验收",
          "resolution_needed": "资源存储部署、任务执行方式、崩溃恢复机制、依赖基线 Unknown；当前解释器版本漂移。推荐第2步列不新增队列依赖的受管执行方案与引入队列的成本对照，未经批准不安装/升级；已有 openpyxl 可优先评估。"
        },
        {
          "id": "Q05",
          "status": "Unknown",
          "blocking_scope": "验收配置与交付范围",
          "resolution_needed": "delivery_mode、效果阈值、资源/并发预算、数据保留时限 Unknown。以完整提示词 B/C/J 为产品与验收内容基线；不编造阈值。第2步提出 backend_only/minimal_ui 的具体范围及配置供决定。"
        }
      ]
    }
  },
  "mission": {
    "solved": [
      "版本/规则/修改边界确认",
      "主要复用边界、直接调用方、出向依赖与隐式约定有源码证据",
      "CSV/XLSX 定位、任务持久化和真实模型代码专项核查",
      "未知、依赖授权与跨任务线契约问题已记录"
    ],
    "not_solved": [
      "后续阶段的设计、实现和验收（不在本步）",
      "真实后端可用性、部署私有性、数据库并发行为和模型效果"
    ]
  },
  "artifacts": [
    {
      "path": "docs/mainline1/step-01.md",
      "purpose": "完整本步结果与证据/命令"
    },
    {
      "path": "docs/mainline1/HANDOFF.md",
      "purpose": "最小恢复入口与结构化阶段摘要"
    }
  ],
  "findings": {
    "evidence_index": "step-01.md findings.evidence_index E01—E13",
    "capabilities": "stage_result.data.capabilities",
    "boundary": "源码 Verified；行为 Untested；真实语义 Blocked"
  },
  "changes": [
    {
      "target": "docs/mainline1/step-01.md 与 HANDOFF.md",
      "motivation": "固化第1步核查结果、证据与授权边界",
      "scope": "仅新建本任务两份文档；不改业务代码/接口/配置/数据库",
      "dependencies": [
        "两份主线一任务提示词",
        "当前源码与会话授权"
      ],
      "priority": "P1",
      "authorization": "用户本轮明确允许核查与交接文档",
      "important_alternatives": "未发现正式交接目录，故使用规定目录；不侵入旧 agent-rag 文档或其他任务线提示词",
      "unverified_assumptions": "运行环境、部署私有性与后续契约均未验证",
      "rollback": "仅在确认两份文档仍为本轮版本且无后续追加后，删除这两份新文件；若已有后续记录，仅撤回本步新增内容。不得 git reset/clean 或删除其他文件。"
    }
  ],
  "verification": {
    "Passed": [
      "V01 源码/调用链核查",
      "V02 180文件 AST",
      "V03 解释器依赖元数据检查",
      "V08 文档结构、原提示词摘要不变、tracked/index diff 为空"
    ],
    "Untested": [
      "V04 数据库/行为测试",
      "V05 Mock/规则执行",
      "V07 UI/部署/端到端"
    ],
    "Blocked": [
      "V06 真实语义验证（批准缺失）"
    ],
    "detail": "step-01.md verification"
  },
  "approved_decisions": [
    {
      "decision": "仅执行第1步，允许只读源码/已有检查与本任务文档",
      "source": "当前用户消息"
    },
    {
      "decision": "使用完整提示词基线及共同交接约定；结束停止等待第2步",
      "source": "当前与上一条用户消息"
    }
  ],
  "judgment_changes": [
    {
      "previous": "初次在会话 cwd 查询 Git 失败，仓库根位置待确认",
      "current": "真实 Git 仓库是 project-code；并非无 Git 信息",
      "new_evidence_refs": [
        "E01"
      ],
      "affected_decisions": [
        "版本记录与全部核查路径"
      ]
    },
    {
      "previous": "CSV/XLSX 扩展名、task/provider 模块仅为能力线索（Unknown）",
      "current": "精确表格定位 Missing；任务底座 Partial；真实传输代码 Implemented，主线一运行后端 Unknown",
      "new_evidence_refs": [
        "E04",
        "E05",
        "E06",
        "E07",
        "E12",
        "E13"
      ],
      "affected_decisions": [
        "不直接复用 RAG 解析和任务入口",
        "模型代码与可用性/效果分开记录"
      ]
    }
  ],
  "open_questions": [
    {
      "id": "Q01",
      "status": "Unknown",
      "blocking_scope": "后续资产/范围/画像/事件/执行契约接入",
      "resolution_needed": "正式 owner 和已批准契约位置 Unknown。第2步先提交 Proposed 契约，明确资产所有者、定位基数/Unicode 单位、版本/范围/hash、画像替代、权威适用状态、事件延迟/去重以及计划组合语义；不得自行批准跨线不兼容变化。"
    },
    {
      "id": "Q02",
      "status": "Unknown",
      "blocking_scope": "真实语义调用及 A/B/C 效果验收",
      "resolution_needed": "semantic_backend、允许数据、调用预算 Unknown。推荐先保持网络调用禁用；第2步形成固定 provider/model、合成样本烟测、超时/成本上限的可审阅方案，再请求具体批准。真实敏感原文外发仍禁止。"
    },
    {
      "id": "Q03",
      "status": "Unknown",
      "blocking_scope": "后续持久化实现与迁移",
      "resolution_needed": "approved_schema_changes Unknown，现有任务表不满足目标。推荐先设计独立领域表及与资产 owner 的引用；迁移文件编写、隔离测试库验证、业务库执行分别确认范围；本步均不做。"
    },
    {
      "id": "Q04",
      "status": "Unknown",
      "blocking_scope": "运行/部署与安全验收",
      "resolution_needed": "资源存储部署、任务执行方式、崩溃恢复机制、依赖基线 Unknown；当前解释器版本漂移。推荐第2步列不新增队列依赖的受管执行方案与引入队列的成本对照，未经批准不安装/升级；已有 openpyxl 可优先评估。"
    },
    {
      "id": "Q05",
      "status": "Unknown",
      "blocking_scope": "验收配置与交付范围",
      "resolution_needed": "delivery_mode、效果阈值、资源/并发预算、数据保留时限 Unknown。以完整提示词 B/C/J 为产品与验收内容基线；不编造阈值。第2步提出 backend_only/minimal_ui 的具体范围及配置供决定。"
    }
  ],
  "next_step_constraints": [
    "仅等待用户第2步指令，不自动实施设计或实现。",
    "第2步使用本记录与产品基线，先形成 Proposed 方案/契约/验收再提出具体实质决策；不能把本步复用建议当批准。",
    "不覆盖初始三个未跟踪提示词；后续开始时重查 Git 和交接，保留并行任务线新修改。",
    "不擅自更改跨模块语义、新增依赖、执行迁移、调用真实模型或外发真实原文；权限缺失只阻塞相关工作。",
    "设计优先考虑现有 csv 标准库/openpyxl、认证、事务、受管任务与最小审计；不得将 Mock/local-hash/教学 fallback 作为语义结果。"
  ],
  "authorization_remaining": [
    "本步授权已完成；没有后续实现、依赖变更、数据库执行或真实模型调用的新增批准"
  ]
}
```
