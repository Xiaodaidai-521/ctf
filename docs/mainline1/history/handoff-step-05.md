# 主线一交接

更新时间：2026-10-14。实际交接目录：`docs/mainline1/`，继续复用。仓库`project-code`，分支`feature/Sensitive-data-recognition`，基线`f4ac82caf32a4112c047cdb8848cab135acbb3c6`。

**当前第5步 / status: partial。已停止，等待第6步指令。** 内部语义边界、融合与降级已实现；真实模型路径及正式业务组合规则Blocked。实际模型调用0次，不能证明上下文改善识别。前一步完整交接原样保存在[history/handoff-step-04.md](history/handoff-step-04.md)，其中“等待第5步”是历史状态。

| step / status | mission / 证据 |
|---|---|
| 01 / complete | [源码核查](step-01.md)，保持原样 |
| 02 / complete | [设计记录](step-02.md)、[设计](design.md)、[Schema](contracts/schema.json)、[验收](acceptance.md)；14个公共对象仍Proposed |
| 03 / partial | [解析与任务](step-03.md)；内部实现与隔离PostgreSQL有证据，真实owner/生产部署仍缺前置 |
| 04 / partial | [规则基线](step-04.md)；开发draft配置已验，正式政策/公共接入未批准 |
| 05 / partial | [本步记录](step-05.md)、[语义边界与烟测方案](semantic-design-v1.md)；内部独立工作完成，真实路径Blocked |

## artifacts / findings / verification

- [semantic.py](../../backend/mainline1/semantic.py)：显式适配接口、固定模板、输出校验及超时/失败/授权/预算门禁；构造仅用替身验证，真实端点未验。
- [fusion.py](../../backend/mainline1/fusion.py)：规则/语义去重、冲突、来源追踪、原文映射和分层覆盖；组合默认关闭，test_only关系候选不等于业务策略。
- [89项实际验证](step-05-verification.json)：24项本步局部测试＋65项前序回归Passed，4个新增Python源文件AST Passed。内部边界：Implemented / Verified / High / Passed。真实运输及业务策略：Partial / Verified（仅阻塞与源码范围） / High / Blocked。真实效果：Unknown / Unknown / Low / Untested。
- [固定样本](step-05-smoke-fixture.json)、[A/B/C预检](step-05-smoke.json)：3个目标固定，B/C文本一致，A规则结果筛至同目标；B/C推理not_run，metrics=null。测试替身不计真实效果。
- [最终保护检查](step-05-final-check.json)：前序文件/公共契约/用户提示词保护、交接字段、链接及测试源摘要。复现命令：仓库根`python -B docs/mainline1/verify_step05.py`。
- 前序[PostgreSQL证据](step-03-postgres-verification.json)只证明其记录的13项隔离数据库验证；本步未改数据库代码、未重跑SQL检查。解析任务成功仍仅代表parsed_asset，不能当扫描完成。

## changes / approved_decisions / judgment_changes

批准来源：用户第5步指令及continue；完整提示词B3/B4允许缺失实质授权时完成独立内部工作。前序内部实现授权继续有效。本步未批准真实模型、原文外发、费用、业务组合规则、生产政策、公共发布或业务库迁移。

新增semantic.py、fusion.py、semantic_smoke.py、tests/test_semantic.py及本步合成样本/核查/交接文档；仅增量更新README、acceptance、HANDOFF。未改前序实现、公共Schema、依赖清单、生产配置或业务数据库。所有任务文件仍未跟踪、未提交。

判断变化：由第4步“语义/组合均未实现”更新为“内部适配/融合及test_only组合引擎已验”；真实调用及业务组合仍未执行。证据是89项本地检查，不扩大为模型效果。复用已有运输库但绕开自动加载环境和跨provider路由的注册入口；未读取凭据或.env。

未验证假设/限制：调用方需由真实owner完成鉴权并可信注入授权receipt；单批预算不是跨尝试/多worker持久化总账；实际SDK端点/token计数/计费及服务端取消未验。内部快照含受控原文，不是公共响应；生产留存/ACL/画像存储及权威适用性未接入。

回滚：仅撤回上述4个新增源码及本步文档，按差异撤回README/acceptance/HANDOFF增量，保留历史交接、前序代码、用户文件和其他任务工作；不用reset/clean，不执行业务库操作。

## open_questions / next_step_constraints

| 待决事项 | 可审阅选项与取舍 | 阻塞范围 |
|---|---|---|
| D04模型/数据/预算 | 保持关闭；或批准兼容HTTPS模型仅发送固定合成样本（B3+C3最多6次，无重试）；或指定本地后端。需provider/model/endpoint、合成输入授权、token计数与币种/总金额/token上限，详见语义方案 | 真实烟测/效果，内部工作已完成 |
| D05组合策略 | 默认关闭；或由政策owner批准类别组合、关系含义、等级及版本。不能将测试L3直接激活 | 业务组合发现 |
| Q4-policy、D02/D03 | 延续前序：提供正式类别/等级政策、私有资产owner契约及部署/持久化授权；当前draft不能生产使用 | 正式分类、鉴权、画像存储/适用性、公共接入与生产部署 |

决策依据来自用户本步前置输入与执行1/5及完整提示词的授权约束；不是重新请求常规内部实现许可。没有新的效果门槛。后续必须保留rule/semantic/fusion来源、原始未校准分数、四层覆盖及版本快照；不能以测试替身填补真实语义或将用户描述当事实。第6步需用户另行指令，不自动开展复核/计划/外发或独立效果实验，不撤销其他模块决策。

历史清理附记：第3步首次临时目录mainline1-synthetic-pg-633pg7hs已停止，删除被自动审批以blocked by policy拒绝，保留且未绕过；本步未执行清理或数据库操作。

## stage_result

以下为E7阶段4中4A的本步子集，完整ChangeItem/VerificationItem/证据与批准边界见step-05.md。

```json
{
  "schema": "mainline1.step5.semantic.v1 / E7-stage4-4A-subset",
  "data": {
    "milestone_results": {
      "4A": {
        "delivered": [
          "显式真实运输适配接口（网络未验）、固定模板及输入组织",
          "严格结构/类别/长度数量/定位/证据校验、无工具调用、失败降级",
          "规则与语义融合去重、冲突、复核原因、不可变来源链",
          "显式配置的test_only同一行不同字段共现引擎（默认关闭）",
          "原文映射、私有快照/指纹、缓存关闭、分层覆盖与原始未校准分数",
          "24项新增本地测试及固定3格A/B/C输入预检"
        ],
        "not_delivered": [
          "真实模型烟测、上下文改善识别效果结论",
          "获批业务组合规则及生产分类政策",
          "生产累计费用持久化、公共接口/画像存储与权威适用性",
          "后续复核/通知/计划/外发及独立效果实验"
        ],
        "changes": [
          {
            "target": "backend/mainline1/semantic.py",
            "motivation": "实现可独立验证的语义边界、保守融合及固定样本预检",
            "dependencies": [
              "第3步ParseResult",
              "第4步RuleResult/开发政策",
              "现有langchain_openai；测试使用已有jsonschema"
            ],
            "priority": "P1",
            "authorization": "用户第5步执行1及完整提示词B3/B4；真实模型授权不在此列",
            "rollback": "仅撤回本步新增文件和交接增量，不改前序实现",
            "evidence_refs": [
              {
                "source": "repository",
                "location": "step-05-verification.json",
                "observation": "89 tests Passed: 24 semantic/fusion boundary tests using doubles and 65 existing tests; 4 new Python files AST Passed",
                "supports": "local output validation, fusion, downgrade, source tracing and regression scope",
                "does_not_support": "real backend availability, semantic effectiveness, business combination approval or production integration"
              }
            ]
          }
        ],
        "verification": [
          {
            "name": "本地行为及前序回归",
            "level": 2,
            "status": "Passed",
            "scope": "backend: python -B -m unittest discover -s mainline1/tests -v；89项（24本步+65前序）",
            "evidence_refs": [
              {
                "source": "repository",
                "location": "step-05-verification.json",
                "observation": "89 tests Passed: 24 semantic/fusion boundary tests using doubles and 65 existing tests; 4 new Python files AST Passed",
                "supports": "local output validation, fusion, downgrade, source tracing and regression scope",
                "does_not_support": "real backend availability, semantic effectiveness, business combination approval or production integration"
              }
            ],
            "gap": "后端是测试替身；不支持效果结论"
          }
        ]
      },
      "4B": {
        "delivered": [],
        "not_delivered": [
          "非本步范围，未执行"
        ],
        "changes": [],
        "verification": []
      },
      "4C": {
        "delivered": [],
        "not_delivered": [
          "非本步范围，未执行"
        ],
        "changes": [],
        "verification": []
      },
      "4D": {
        "delivered": [],
        "not_delivered": [
          "非本步范围，未执行"
        ],
        "changes": [],
        "verification": []
      }
    },
    "open_questions": [
      {
        "id": "D04-model/data/budget",
        "status": "Unknown",
        "blocking_scope": "真实烟测及识别效果；不阻塞内部实现",
        "resolution_needed": "见semantic-design-v1.md烟测方案：维持关闭，或批准现有兼容服务仅发送固定合成样本，或指定本地后端；提供provider/model/endpoint、数据路径、token及币种/总金额上限和价格依据。建议B3+C3共6次、无重试；未批准。"
      },
      {
        "id": "D05-combination",
        "status": "Unknown",
        "blocking_scope": "业务组合发现启用",
        "resolution_needed": "默认关闭，或由政策owner批准类别组合、关系含义、等级映射及版本；测试L3不转为生产政策。"
      },
      {
        "id": "D02/D03/Q4-policy",
        "status": "Unknown",
        "blocking_scope": "正式资产鉴权、公共发布、生产注册/存储及正式类别政策",
        "resolution_needed": "延续第3/4步：指定owner与契约并限定部署/数据保留授权；当前draft政策和内部配置不成为公共授权凭据。"
      }
    ]
  }
}
```
