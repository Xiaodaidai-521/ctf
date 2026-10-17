# 主线一交接：第6步

2026-10-14；**step / status: 06 / partial**。内部复核、持久化适用性和事件适配已验证；正式公共接入仍缺批准。停止等待第7步，不自动推进。

## mission / artifacts

已解决对象权限门禁、全遮蔽待复核分页、确认/纠错/误报/补录、manual来源及依据、追加历史、政策重算、幂等和唯一后继、同资产其他范围重评估、权威适用性和事务outbox。正式owner、生产政策/部署及真实事件投递未解决。

- [第6步结构化交接](step-06.md)：本步全部结果、变更、证据和限制。
- [调用及正式接入方案](review-design-v1.md)：服务入口、数据语义、保守边界、可审阅待决方案和回滚。
- [复核服务](../../backend/mainline1/review.py)、[PostgreSQL适配](../../backend/mainline1/review_repository.py)、新增0002迁移及tests/test_review.py、tests/postgres_review_cases.py。
- [第5步交接原样归档](history/handoff-step-05.md)；第1—5步记录、公共Schema和用户提示词保留不变。

## findings / verification

- [本地验证](step-06-verification.json)：109项Passed（20本步＋89前序）；8个相关Python文件AST Passed；前序文件摘要保护Passed。真实规则合成输入；ACL和事件接收器是替身。
- [隔离数据库验证](step-06-postgres-verification.json)：36项Passed（23本步＋13前序），包括不同PostgreSQL连接并发、重连、事务回滚、确认丢失重放；system check、迁移漂移、正反向迁移均Passed。全新集群已停止、删除，未连接既有业务库。
- 内部能力 Implemented / Verified / High / Passed；正式接入 Partial / Verified（边界） / High / Blocked；真实语义效果仍Unknown / Unknown / Low / Untested。没有真实模型或真实事件中心调用。
- 当前draft政策下，所有画像usable_for_new_decision=false；current只表示本链当前版本。老画像superseded、历史仍可审计。计划生成/验证不在本步。

## changes / approved_decisions / judgment_changes

授权来源为用户第6步及continue、完整提示词B3/B4。允许独立内部实现、既有依赖、迁移文件及全新合成隔离验证；不包含公共契约批准、生产注册/迁移、真实外发/模型/事件接入。

新增复核服务、Django持久化适配、0002迁移、测试和本步文档；仅增量修改models.py、已有隔离runner的可选参数、README和本HANDOFF。未改历史迁移、公共契约、依赖或其他任务文件；未提交。

判断从“只有内存适配”更新为“持久化事务在隔离PostgreSQL已验”；生产owner仍待接。首轮跨范围测试误用已消费的幂等键，已修正测试输入并保留正确的幂等冲突语义。完整证据与判断变化见step-06。

限制与未验证假设：全局单行aggregate上限16MiB，不能当高吞吐设计；生产ACL/保留/删除及部署未验证；组合画像明确拒绝复核；事件默认未连接，死信保留但无运维重驱动/SLA；资格查询不自动迁移人工结论。

回滚只撤回本步新增文件和上述增量，保留前序历史与其他任务工作；不reset/clean，不反向迁移任何既有业务数据。

## open_questions / next_step_constraints

正式接入的具体方案见review-design-v1：推荐暂留内部使用；需发布时由相关owner批准现有复核/替代/适用性/事件语义，提供真实资产ACL、生产政策、目标部署/迁移环境及保留规则，指定事件信封、调度与不可查询时处理。未批准项只阻塞正式接入。

前序D04真实模型/数据路径/费用、D05组合策略及D02/D03生产owner待决继续有效。历史临时集群清理拒绝记录继续保留在前序交接，本次没有绕过或处理旧目录。

等待第7步指令。下一步只能消费已验证且满足前置的画像/状态；不能把本步测试、进入下一步或current状态当作生产授权。旧计划本体保持不变，后续校验必须读取权威适用性及版本；不修改外部模块决策或数据库，不自动训练/发布政策。

## stage_result

结构化E7 4B及4C通知子集、ChangeItem/VerificationItem/证据/批准记录完整保存在[step-06.md](step-06.md)。

```json
{
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
```
