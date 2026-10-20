# 第6步：人工复核、补录与画像适用性

2026-10-14；**status: partial**。内部实现及必要验证完成，正式接入前置仍缺，不宣称生产可授权或真实事件投递。

109项本地测试（20本步＋89前序）和36项隔离PostgreSQL测试（23本步＋13前序）通过；另通过system check、迁移漂移及正反向迁移检查。测试仅合成数据，ACL/通知接收器为替身，规则是真实实现，真实模型调用0次。

[调用与待决方案](review-design-v1.md) · [本地证据](step-06-verification.json) · [数据库证据](step-06-postgres-verification.json)

```json
{
  "step": "06",
  "status": "partial",
  "recorded_on": "2026-10-14",
  "repository_state": {
    "root": "D:\\aaa10\\16015478源码\\project-code",
    "revision": "f4ac82caf32a4112c047cdb8848cab135acbb3c6",
    "branch": "feature/Sensitive-data-recognition",
    "existing_modifications": "前序mainline1目录和用户提示词均未跟踪；已保存step-06-input-state.json；未提交",
    "rules": "未找到适用AGENTS；遵循完整提示词、共同交接约定及.editorconfig"
  },
  "mission": {
    "solved": [
      "对象权限门禁、固定画像分页和全遮蔽展示",
      "确认/类别修正/误报/漏检补录、manual操作者和依据、政策等级重算",
      "追加历史、幂等/CAS、唯一后继、同资产其他范围保守重评估",
      "持久化权威适用性和变化历史、事务outbox/事件适配及失败重放",
      "严格输入绑定的人工结论复用资格查询"
    ],
    "not_solved": [
      "正式owner/公共发布/生产政策及迁移执行",
      "真实事件中心投递、受管投递调度、死信重驱动/SLA",
      "组合画像复核（未批准业务组合）；第7步计划验证器未实施"
    ]
  },
  "artifacts": [
    {
      "file": "backend/mainline1/review.py",
      "role": "复核实现/隔离适配/验证"
    },
    {
      "file": "backend/mainline1/review_repository.py",
      "role": "复核实现/隔离适配/验证"
    },
    {
      "file": "backend/mainline1/migrations/0002_reviewledger.py",
      "role": "复核实现/隔离适配/验证"
    },
    {
      "file": "backend/mainline1/tests/test_review.py",
      "role": "复核实现/隔离适配/验证"
    },
    {
      "file": "backend/mainline1/tests/postgres_review_cases.py",
      "role": "复核实现/隔离适配/验证"
    },
    {
      "file": "backend/mainline1/tests/run_review_postgres.py",
      "role": "复核实现/隔离适配/验证"
    },
    {
      "file": "docs/mainline1/review-design-v1.md",
      "role": "调用说明、边界、正式接入待决方案"
    },
    {
      "file": "docs/mainline1/step-06-verification.json",
      "role": "本地实际证据"
    },
    {
      "file": "docs/mainline1/step-06-postgres-verification.json",
      "role": "隔离数据库实际证据"
    },
    {
      "file": "docs/mainline1/history/handoff-step-05.md",
      "role": "前序交接原样归档"
    }
  ],
  "findings": [
    {
      "id": "F6-internal",
      "claim": "本步内部复核与持久化适用性已实现，历史不可变及冲突在局部/隔离数据库验证",
      "capability_status": "Implemented",
      "evidence_status": "Verified",
      "verification_status": "Passed",
      "confidence": "High",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-06-verification.json",
          "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
          "supports": "local rule-driven review, permission boundaries, immutability and regression",
          "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
        },
        {
          "source": "repository",
          "location": "step-06-postgres-verification.json",
          "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
          "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
          "does_not_support": "production deployment, throughput, actual event-center delivery"
        }
      ],
      "limitations": [
        "仅合成小规模",
        "生产ACL未接入",
        "draft current也不可用于新授权"
      ]
    },
    {
      "id": "F6-integration",
      "claim": "正式接入和真实通知仍缺前置",
      "capability_status": "Partial",
      "evidence_status": "Verified",
      "verification_status": "Blocked",
      "confidence": "High",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "review-design-v1.md",
          "observation": "Proposed不变、默认adapter=None、生产未注册",
          "supports": "当前接入边界",
          "does_not_support": "真实投递可用性"
        }
      ],
      "limitations": [
        "不将替身通知计为真实投递"
      ]
    }
  ],
  "changes": {
    "items": [
      {
        "target": "backend/mainline1/review.py",
        "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
        "dependencies": [
          "第3步固定解析",
          "第4—5步画像及draft政策",
          "既有Django/PostgreSQL/标准库"
        ],
        "priority": "P1",
        "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
        "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
        "evidence_refs": [
          {
            "source": "repository",
            "location": "step-06-verification.json",
            "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
            "supports": "local rule-driven review, permission boundaries, immutability and regression",
            "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
          },
          {
            "source": "repository",
            "location": "step-06-postgres-verification.json",
            "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
            "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
            "does_not_support": "production deployment, throughput, actual event-center delivery"
          }
        ]
      },
      {
        "target": "backend/mainline1/review_repository.py",
        "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
        "dependencies": [
          "第3步固定解析",
          "第4—5步画像及draft政策",
          "既有Django/PostgreSQL/标准库"
        ],
        "priority": "P1",
        "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
        "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
        "evidence_refs": [
          {
            "source": "repository",
            "location": "step-06-verification.json",
            "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
            "supports": "local rule-driven review, permission boundaries, immutability and regression",
            "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
          },
          {
            "source": "repository",
            "location": "step-06-postgres-verification.json",
            "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
            "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
            "does_not_support": "production deployment, throughput, actual event-center delivery"
          }
        ]
      },
      {
        "target": "backend/mainline1/migrations/0002_reviewledger.py",
        "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
        "dependencies": [
          "第3步固定解析",
          "第4—5步画像及draft政策",
          "既有Django/PostgreSQL/标准库"
        ],
        "priority": "P1",
        "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
        "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
        "evidence_refs": [
          {
            "source": "repository",
            "location": "step-06-verification.json",
            "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
            "supports": "local rule-driven review, permission boundaries, immutability and regression",
            "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
          },
          {
            "source": "repository",
            "location": "step-06-postgres-verification.json",
            "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
            "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
            "does_not_support": "production deployment, throughput, actual event-center delivery"
          }
        ]
      },
      {
        "target": "backend/mainline1/tests/test_review.py",
        "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
        "dependencies": [
          "第3步固定解析",
          "第4—5步画像及draft政策",
          "既有Django/PostgreSQL/标准库"
        ],
        "priority": "P1",
        "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
        "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
        "evidence_refs": [
          {
            "source": "repository",
            "location": "step-06-verification.json",
            "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
            "supports": "local rule-driven review, permission boundaries, immutability and regression",
            "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
          },
          {
            "source": "repository",
            "location": "step-06-postgres-verification.json",
            "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
            "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
            "does_not_support": "production deployment, throughput, actual event-center delivery"
          }
        ]
      },
      {
        "target": "backend/mainline1/tests/postgres_review_cases.py",
        "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
        "dependencies": [
          "第3步固定解析",
          "第4—5步画像及draft政策",
          "既有Django/PostgreSQL/标准库"
        ],
        "priority": "P1",
        "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
        "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
        "evidence_refs": [
          {
            "source": "repository",
            "location": "step-06-verification.json",
            "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
            "supports": "local rule-driven review, permission boundaries, immutability and regression",
            "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
          },
          {
            "source": "repository",
            "location": "step-06-postgres-verification.json",
            "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
            "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
            "does_not_support": "production deployment, throughput, actual event-center delivery"
          }
        ]
      },
      {
        "target": "backend/mainline1/tests/run_review_postgres.py",
        "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
        "dependencies": [
          "第3步固定解析",
          "第4—5步画像及draft政策",
          "既有Django/PostgreSQL/标准库"
        ],
        "priority": "P1",
        "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
        "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
        "evidence_refs": [
          {
            "source": "repository",
            "location": "step-06-verification.json",
            "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
            "supports": "local rule-driven review, permission boundaries, immutability and regression",
            "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
          },
          {
            "source": "repository",
            "location": "step-06-postgres-verification.json",
            "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
            "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
            "does_not_support": "production deployment, throughput, actual event-center delivery"
          }
        ]
      }
    ],
    "scope": "新增6个后端文件；models.py追加ReviewLedger；复用隔离PG验证器增添可选测试模块和证据文件参数；README和交接增量",
    "important_alternatives": [
      "单行事务aggregate保证跨scope原子性，代价是16MiB/全局锁限制；未进行生产分区设计",
      "全遮蔽替代可能泄露未识别内容的部分掩码",
      "保守标记同资产全部其他范围，而非猜测重叠",
      "无正式事件信封时只接适配端口"
    ],
    "unverified_assumptions": [
      "生产owner提供实时具体对象权限",
      "生产数据保留、ACL和部署策略待批",
      "消费者去重/版本排序及最终准入规则需正式接入验证"
    ],
    "rollback": "仅撤回本步新增文件及models/隔离runner/README/HANDOFF增量；前序HANDOFF归档保留。不reset/clean；不反向迁移含业务数据表"
  },
  "verification": [
    {
      "name": "本地行为和前序回归",
      "level": 2,
      "status": "Passed",
      "scope": "仓库根 python -B docs/mainline1/verify_step06.py；109项=20本步+89前序",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-06-verification.json",
          "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
          "supports": "local rule-driven review, permission boundaries, immutability and regression",
          "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
        }
      ],
      "gap": "ACL/事件接收器为替身；规则是真实实现"
    },
    {
      "name": "隔离PostgreSQL及迁移",
      "level": 3,
      "status": "Passed",
      "scope": "backend: python -B -m mainline1.tests.run_review_postgres；36项=23本步+13前序；另4项系统/迁移检查",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-06-postgres-verification.json",
          "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
          "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
          "does_not_support": "production deployment, throughput, actual event-center delivery"
        }
      ],
      "gap": "全新合成测试集群；未连接业务库"
    },
    {
      "name": "Proposed对象兼容",
      "level": 3,
      "status": "Passed",
      "scope": "ReviewRecord/Finding/SensitivityProfile/ProfileApplicability/ProfileChangedEvent在本步测试中校验；Schema未修改",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-06-verification.json",
          "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
          "supports": "local rule-driven review, permission boundaries, immutability and regression",
          "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
        },
        {
          "source": "repository",
          "location": "step-06-postgres-verification.json",
          "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
          "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
          "does_not_support": "production deployment, throughput, actual event-center delivery"
        }
      ],
      "gap": "未发布公共契约"
    },
    {
      "name": "正式鉴权/生产政策/事件中心投递",
      "level": 3,
      "status": "Blocked",
      "scope": "正式owner、公共契约、生产启用及通知",
      "evidence_refs": [],
      "gap": "前序契约仍Proposed且owner/事件信封未批准；默认not_connected"
    },
    {
      "name": "真实语义与效果",
      "level": 4,
      "status": "Blocked",
      "scope": "继承第5步边界，本步零调用",
      "evidence_refs": [],
      "gap": "真实后端/数据/费用授权仍缺；不影响真实规则复核"
    },
    {
      "name": "生产负载和死信运维",
      "level": 4,
      "status": "Untested",
      "scope": "全局单行16MiB上限及人工死信处理",
      "evidence_refs": [],
      "gap": "只验证合成小规模；无生产吞吐/SLA/调度接入证据"
    }
  ],
  "approved_decisions": [
    {
      "decision": "执行第6步内部实现、必要验证和交接；不自动推进第7步",
      "source": "用户第6步指令及continue"
    },
    {
      "decision": "既有依赖、内部适配、迁移文件与全新合成隔离库验证",
      "source": "完整提示词B3/B4及前序隔离验证边界；不包含既有业务库执行"
    }
  ],
  "judgment_changes": [
    {
      "previous": "第5步画像存储/权威适用性未接入",
      "current": "内部持久化适用性和追加复核已通过隔离PostgreSQL验证；生产接入仍Blocked",
      "new_evidence_refs": [
        {
          "source": "repository",
          "location": "step-06-verification.json",
          "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
          "supports": "local rule-driven review, permission boundaries, immutability and regression",
          "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
        },
        {
          "source": "repository",
          "location": "step-06-postgres-verification.json",
          "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
          "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
          "does_not_support": "production deployment, throughput, actual event-center delivery"
        }
      ],
      "affected_decisions": [
        "第7步可消费内部权威状态，draft不可用于生产新授权"
      ]
    },
    {
      "previous": "初次跨范围测试复用了已有幂等键，期待适用性错误但实际为幂等冲突",
      "current": "测试改用新键验证适用性拒绝；保留同键不同内容优先冲突语义",
      "new_evidence_refs": [
        {
          "source": "repository",
          "location": "step-06-verification.json",
          "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
          "supports": "local rule-driven review, permission boundaries, immutability and regression",
          "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
        },
        {
          "source": "repository",
          "location": "step-06-postgres-verification.json",
          "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
          "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
          "does_not_support": "production deployment, throughput, actual event-center delivery"
        }
      ],
      "affected_decisions": [
        "稳定错误优先级不变"
      ]
    },
    {
      "previous": "最初只有内存事务适配",
      "current": "补充既有Django/PostgreSQL持久化适配，真实双连接并发和确认丢失重放已验",
      "new_evidence_refs": [
        {
          "source": "repository",
          "location": "step-06-postgres-verification.json",
          "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
          "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
          "does_not_support": "production deployment, throughput, actual event-center delivery"
        }
      ],
      "affected_decisions": [
        "不再仅以内存测试代表持久化"
      ]
    }
  ],
  "open_questions": [
    {
      "id": "Q6-contract-owner-event",
      "status": "Unknown",
      "blocking_scope": "正式公共接入、生产鉴权/政策/部署/迁移与真实事件投递",
      "resolution_needed": "见review-design-v1.md正式接入方案：保持内部使用（推荐），或由相关owner批准现有复核/替代/适用性/事件语义，指定资产ACL、目标环境及保留策略、事件信封和不可查询时处理规则"
    },
    {
      "id": "D04-model-data-budget",
      "status": "Unknown",
      "blocking_scope": "真实语义及效果",
      "resolution_needed": "沿用step-05及semantic-design-v1.md，不重复扩大授权"
    },
    {
      "id": "D05-combination",
      "status": "Unknown",
      "blocking_scope": "组合画像复核和生产组合策略",
      "resolution_needed": "仍需政策owner批准业务组合和等级；本步明确拒绝组合画像复核，不丢失等级"
    }
  ],
  "next_step_constraints": [
    "本步结束停止，等待第7步指令；该指令不代表验收/公共契约批准",
    "第7步需保持旧计划本体不变，使用权威适用性状态与版本；draft usable_for_new_decision=false不得绕过",
    "不撤销外部决策、不写其他模块数据库、不训练或发布全局政策",
    "仅消费无组合的已验证规则或默认降级画像；组合复核明确Blocked",
    "未批准正式契约、owner、生产政策与事件信封，不发布接口或执行业务库迁移",
    "前序真实语义/数据/费用待决继续有效"
  ],
  "authorization_remaining": [
    "公共契约正式批准",
    "生产owner/政策/数据保留及目标部署/迁移环境",
    "正式事件信封、投递调度及消费者处理约定",
    "真实语义/组合策略授权"
  ],
  "stage_result": {
    "schema": "mainline1.step6.review.v1 / E7-stage4-4B-and-4C-notification-subset",
    "data": {
      "milestone_results": {
        "4B": {
          "delivered": [
            "对象权限门禁、固定画像分页和全遮蔽展示",
            "确认/类别修正/误报/漏检补录、manual操作者和依据、政策等级重算",
            "追加历史、幂等/CAS、唯一后继、同资产其他范围保守重评估",
            "持久化权威适用性和变化历史、事务outbox/事件适配及失败重放",
            "严格输入绑定的人工结论复用资格查询"
          ],
          "not_delivered": [
            "正式owner/公共发布/生产政策及迁移执行",
            "真实事件中心投递、受管投递调度、死信重驱动/SLA",
            "组合画像复核（未批准业务组合）；第7步计划验证器未实施"
          ],
          "changes": [
            {
              "target": "backend/mainline1/review.py",
              "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
              "dependencies": [
                "第3步固定解析",
                "第4—5步画像及draft政策",
                "既有Django/PostgreSQL/标准库"
              ],
              "priority": "P1",
              "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
              "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                },
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ]
            },
            {
              "target": "backend/mainline1/review_repository.py",
              "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
              "dependencies": [
                "第3步固定解析",
                "第4—5步画像及draft政策",
                "既有Django/PostgreSQL/标准库"
              ],
              "priority": "P1",
              "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
              "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                },
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ]
            },
            {
              "target": "backend/mainline1/migrations/0002_reviewledger.py",
              "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
              "dependencies": [
                "第3步固定解析",
                "第4—5步画像及draft政策",
                "既有Django/PostgreSQL/标准库"
              ],
              "priority": "P1",
              "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
              "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                },
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ]
            },
            {
              "target": "backend/mainline1/tests/test_review.py",
              "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
              "dependencies": [
                "第3步固定解析",
                "第4—5步画像及draft政策",
                "既有Django/PostgreSQL/标准库"
              ],
              "priority": "P1",
              "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
              "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                },
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ]
            },
            {
              "target": "backend/mainline1/tests/postgres_review_cases.py",
              "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
              "dependencies": [
                "第3步固定解析",
                "第4—5步画像及draft政策",
                "既有Django/PostgreSQL/标准库"
              ],
              "priority": "P1",
              "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
              "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                },
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ]
            },
            {
              "target": "backend/mainline1/tests/run_review_postgres.py",
              "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
              "dependencies": [
                "第3步固定解析",
                "第4—5步画像及draft政策",
                "既有Django/PostgreSQL/标准库"
              ],
              "priority": "P1",
              "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
              "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                },
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ]
            }
          ],
          "verification": [
            {
              "name": "本地行为和前序回归",
              "level": 2,
              "status": "Passed",
              "scope": "仓库根 python -B docs/mainline1/verify_step06.py；109项=20本步+89前序",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                }
              ],
              "gap": "ACL/事件接收器为替身；规则是真实实现"
            },
            {
              "name": "隔离PostgreSQL及迁移",
              "level": 3,
              "status": "Passed",
              "scope": "backend: python -B -m mainline1.tests.run_review_postgres；36项=23本步+13前序；另4项系统/迁移检查",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ],
              "gap": "全新合成测试集群；未连接业务库"
            },
            {
              "name": "Proposed对象兼容",
              "level": 3,
              "status": "Passed",
              "scope": "ReviewRecord/Finding/SensitivityProfile/ProfileApplicability/ProfileChangedEvent在本步测试中校验；Schema未修改",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                },
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ],
              "gap": "未发布公共契约"
            },
            {
              "name": "正式鉴权/生产政策/事件中心投递",
              "level": 3,
              "status": "Blocked",
              "scope": "正式owner、公共契约、生产启用及通知",
              "evidence_refs": [],
              "gap": "前序契约仍Proposed且owner/事件信封未批准；默认not_connected"
            },
            {
              "name": "真实语义与效果",
              "level": 4,
              "status": "Blocked",
              "scope": "继承第5步边界，本步零调用",
              "evidence_refs": [],
              "gap": "真实后端/数据/费用授权仍缺；不影响真实规则复核"
            },
            {
              "name": "生产负载和死信运维",
              "level": 4,
              "status": "Untested",
              "scope": "全局单行16MiB上限及人工死信处理",
              "evidence_refs": [],
              "gap": "只验证合成小规模；无生产吞吐/SLA/调度接入证据"
            }
          ]
        },
        "4C": {
          "delivered": [
            "事务outbox、Proposed事件适配、持久化适用性查询"
          ],
          "not_delivered": [
            "正式事件中心投递",
            "第7步计划生成/验证"
          ],
          "changes": [
            {
              "target": "backend/mainline1/review.py",
              "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
              "dependencies": [
                "第3步固定解析",
                "第4—5步画像及draft政策",
                "既有Django/PostgreSQL/标准库"
              ],
              "priority": "P1",
              "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
              "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                },
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ]
            },
            {
              "target": "backend/mainline1/review_repository.py",
              "motivation": "第6步追加复核、持久化适用性、事件适配及必要验证",
              "dependencies": [
                "第3步固定解析",
                "第4—5步画像及draft政策",
                "既有Django/PostgreSQL/标准库"
              ],
              "priority": "P1",
              "authorization": "本步用户指令与continue；完整提示词B3/B4允许内部实现及隔离验证，不包含生产发布",
              "rollback": "撤回本步文件及对应增量；保留前序与其他任务工作；不操作业务库",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                },
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ]
            }
          ],
          "verification": [
            {
              "name": "隔离PostgreSQL及迁移",
              "level": 3,
              "status": "Passed",
              "scope": "backend: python -B -m mainline1.tests.run_review_postgres；36项=23本步+13前序；另4项系统/迁移检查",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ],
              "gap": "全新合成测试集群；未连接业务库"
            },
            {
              "name": "Proposed对象兼容",
              "level": 3,
              "status": "Passed",
              "scope": "ReviewRecord/Finding/SensitivityProfile/ProfileApplicability/ProfileChangedEvent在本步测试中校验；Schema未修改",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-06-verification.json",
                  "observation": "109 local tests Passed: 20 review tests and 89 previous tests; 8 changed/new Python files AST Passed; prior-file preservation Passed",
                  "supports": "local rule-driven review, permission boundaries, immutability and regression",
                  "does_not_support": "production ACL, live semantic effectiveness or actual external delivery"
                },
                {
                  "source": "repository",
                  "location": "step-06-postgres-verification.json",
                  "observation": "36 PostgreSQL tests Passed: 23 review tests and 13 existing parse-task tests; system/migration checks, forward/reverse migration Passed; fresh cluster stopped and removed",
                  "supports": "isolated durable transactions, two-connection CAS, reconnect, rollback and outbox acknowledgement-loss replay",
                  "does_not_support": "production deployment, throughput, actual event-center delivery"
                }
              ],
              "gap": "未发布公共契约"
            },
            {
              "name": "正式鉴权/生产政策/事件中心投递",
              "level": 3,
              "status": "Blocked",
              "scope": "正式owner、公共契约、生产启用及通知",
              "evidence_refs": [],
              "gap": "前序契约仍Proposed且owner/事件信封未批准；默认not_connected"
            }
          ]
        }
      },
      "open_questions": [
        {
          "id": "Q6-contract-owner-event",
          "status": "Unknown",
          "blocking_scope": "正式公共接入、生产鉴权/政策/部署/迁移与真实事件投递",
          "resolution_needed": "见review-design-v1.md正式接入方案：保持内部使用（推荐），或由相关owner批准现有复核/替代/适用性/事件语义，指定资产ACL、目标环境及保留策略、事件信封和不可查询时处理规则"
        },
        {
          "id": "D04-model-data-budget",
          "status": "Unknown",
          "blocking_scope": "真实语义及效果",
          "resolution_needed": "沿用step-05及semantic-design-v1.md，不重复扩大授权"
        },
        {
          "id": "D05-combination",
          "status": "Unknown",
          "blocking_scope": "组合画像复核和生产组合策略",
          "resolution_needed": "仍需政策owner批准业务组合和等级；本步明确拒绝组合画像复核，不丢失等级"
        }
      ]
    }
  }
}
```
