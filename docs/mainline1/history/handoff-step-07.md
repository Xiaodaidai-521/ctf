# 主线一交接：第7步

2026-10-15；**step / status: 07 / partial**。内部计划生成与纯校验已实现并验证；正式要求/共同操作契约仍Proposed，真实执行未接入。停止等待第8步。

## mission / artifacts

已解决固定快照绑定、白名单操作、受控内容匹配、覆盖/冲突检查、旧画像失效复查、摘要/分页及进程内幂等。无业务写入校验已经真实隔离PostgreSQL验证。

- [第7步结果](step-07.md)：结构化交接、变更、授权、验证、判断变化和回滚。
- [计划说明及待决方案](plan-design-v1.md)：服务入口、契约语义、限制、执行方前置及Q7。
- [契约样例](plan-examples-v1.json)：虚构测试许可ready、真实draft条件invalid、固定分页；没有外发授权。
- [实现](../../backend/mainline1/planning.py)：PlanService.build/validate/page；review.py与review_repository.py仅新增必要只读入口。
- [原第6步交接](history/handoff-step-06.md)：原样归档；实际交接目录继续复用docs/mainline1。

## findings / verification

[本地证据](step-07-verification.json)：141项Passed（32本步＋109前序）；7个相关Python文件AST、样例Schema/分页摘要、前序文件保护Passed。

[隔离数据库证据](step-07-postgres-verification.json)：39项Passed（3本步＋36前序）；system check、迁移漂移、正反向迁移检查Passed。校验成功/失败/缺失账本路径均仅SELECT；重连读取人工补录后的权威替代状态。新集群已停止并删除，未连接既有业务库。

内部能力：Implemented / Verified / High / Passed。正式公共接入：Partial / Verified（边界） / High / Blocked。真实执行：Unknown / Unknown / Low / Untested。真实规则/解析已运行；许可、ACL、资产政策源是测试替身；真实模型调用0次。

## changes / approved_decisions / judgment_changes

授权来源为用户第7步及continue、完整提示词B3/B4与前序仍有效授权。只包含独立内部实现、既有依赖、全新合成隔离验证及文档；不包含公共契约批准、生产政策/部署、业务库执行、真实原文或模型外发。

新增planning.py、定向测试、隔离runner、样例和验证/交接文档；增量修改review.py、review_repository.py的只读入口、现有隔离runner证据文件白名单、README和本HANDOFF。没有新增依赖、迁移或生产注册，未提交。

由“第6步尚无计划能力”更新为“内部计划与纯校验已验”。首轮成功测试误用要求语义完整的扫描策略，已显式改成仅规则策略；覆盖检查没有放宽。修正游标过期错误码被通用ValueError捕获的问题。首次沙箱内initdb失败，升级执行既有隔离验证后通过。详见step-07判断记录。

回滚仅撤回本步新增文件和上述增量，并恢复归档HANDOFF；不reset/clean，不更改历史迁移或业务数据。

## open_questions / next_step_constraints

Q7具体方案见plan-design-v1.md。推荐当前保留内部Proposed；正式接入前需政策owner/执行方共同批准保护要求来源及版本、原快照操作组合与不确定项语义，并指定资产/政策/匹配权威端口、权限及检查后变化防护。D02/D03/D04/D05/Q6前序待决与已有批准继续保留。

计划登记限单进程100个计划、每请求100要求及1000目标/操作，不提供跨进程持久化幂等或生产容量保证。复杂XLSX结构删除、生产owner集成和真实执行均未验证。

等待第8步指令。后续只消费已验证且满足前置的产物；当前draft画像usable=false，不能以样例ready证明可外发。plan_hash不代表授权；执行前再次读取权威状态并校验，异步通知不能替代此步骤。仍禁止本步生成交付副本、预占额度或创建共享。

## stage_result

```json
{
  "schema": "mainline1.step7.plan.v1 / E7-stage4-4C-plan-subset",
  "data": {
    "milestone_results": {
      "4C": {
        "delivered": [
          "内部计划生成与纯校验",
          "固定摘要、进程内幂等、分页",
          "只读复核仓储适配",
          "契约样例、功能及隔离数据库证据"
        ],
        "not_delivered": [
          "正式契约及保护政策批准",
          "生产权威输入组合",
          "真实执行层",
          "生产持久化计划服务"
        ],
        "changes": [
          {
            "target": "backend/mainline1/planning.py及本步列示增量",
            "motivation": "第7步计划与纯校验",
            "dependencies": [
              "第3—6步已验证内部产物"
            ],
            "priority": "P1",
            "authorization": "用户第7步及continue；B3/B4内部实现",
            "rollback": "仅撤回本步新增文件和列示增量；保留前序与业务数据",
            "evidence_refs": [
              {
                "source": "repository",
                "location": "step-07-verification.json",
                "observation": "141 tests Passed",
                "supports": "内部计划及回归",
                "does_not_support": "生产执行"
              }
            ]
          }
        ],
        "verification": [
          {
            "name": "计划行为与数据库只读",
            "level": 3,
            "status": "Passed",
            "scope": "141本地及39隔离数据库测试",
            "evidence_refs": [
              {
                "source": "repository",
                "location": "step-07-postgres-verification.json",
                "observation": "39 tests Passed and cluster removed",
                "supports": "SQL只读/旧画像失效及回归",
                "does_not_support": "生产部署或外发"
              }
            ],
            "gap": "真实执行未接入；合成许可不代表批准"
          }
        ]
      }
    },
    "open_questions": [
      {
        "id": "Q7-contract-policy",
        "status": "Unknown",
        "blocking_scope": "公共接入与真实执行",
        "resolution_needed": "按plan-design-v1.md由政策owner和执行方共同批准后接入"
      }
    ]
  }
}
```
