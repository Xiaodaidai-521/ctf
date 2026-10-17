# 第5步：真实语义、上下文融合与组合发现

2026-10-14；**status: partial**。独立内部实现完成，真实模型与业务组合批准缺失，相关路径Blocked。没有执行第6步。

[实现边界与烟测方案](semantic-design-v1.md) · [89项实际验证](step-05-verification.json) · [固定样本预检](step-05-smoke.json)

测试替身、真实规则路径与真实模型状态分开：24项新增局部测试+65项前序回归Passed；真实模型调用0次，独立效果指标为空。

```json
{
  "step": "05",
  "status": "partial",
  "recorded_on": "2026-10-14",
  "repository_state": {
    "root": "D:\\aaa10\\16015478源码\\project-code",
    "revision": "f4ac82caf32a4112c047cdb8848cab135acbb3c6",
    "branch": "feature/Sensitive-data-recognition",
    "existing_modifications": "前序未跟踪mainline1代码/文档及用户3份提示词；初始摘要step-05-input-state.json",
    "rules": "未找到AGENTS；遵守完整提示词、共同交接、.editorconfig。用户continue延续本步",
    "input_configuration": {
      "model_approval": "Unknown",
      "data_path_approval": "Unknown",
      "budget_approval": "Unknown",
      "public_contract": "Proposed",
      "production_policy": "未批准；只使用开发draft",
      "dependencies": "未新增",
      "delivery_mode": "内部backend_only，不表示正式交付选择已批准"
    }
  },
  "mission": {
    "solved": [
      "显式真实运输适配接口（网络未验）、固定模板及输入组织",
      "严格结构/类别/长度数量/定位/证据校验、无工具调用、失败降级",
      "规则与语义融合去重、冲突、复核原因、不可变来源链",
      "显式配置的test_only同一行不同字段共现引擎（默认关闭）",
      "原文映射、私有快照/指纹、缓存关闭、分层覆盖与原始未校准分数",
      "24项新增本地测试及固定3格A/B/C输入预检"
    ],
    "not_solved": [
      "真实模型烟测、上下文改善识别效果结论",
      "获批业务组合规则及生产分类政策",
      "生产累计费用持久化、公共接口/画像存储与权威适用性",
      "后续复核/通知/计划/外发及独立效果实验"
    ]
  },
  "stage_result": {
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
            },
            {
              "target": "backend/mainline1/fusion.py",
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
            },
            {
              "target": "backend/mainline1/semantic_smoke.py",
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
            },
            {
              "target": "backend/mainline1/tests/test_semantic.py",
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
            },
            {
              "name": "Proposed Finding/Profile兼容",
              "level": 3,
              "status": "Passed",
              "scope": "测试验证来源、融合发现和画像符合未改公共Schema；不发布公共服务",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-05-verification.json",
                  "observation": "89 tests Passed: 24 semantic/fusion boundary tests using doubles and 65 existing tests; 4 new Python files AST Passed",
                  "supports": "local output validation, fusion, downgrade, source tracing and regression scope",
                  "does_not_support": "real backend availability, semantic effectiveness, business combination approval or production integration"
                }
              ],
              "gap": "内部snapshot不是公共ScanRunSnapshot；画像持久化/权威适用性未接入"
            },
            {
              "name": "静态和前序文件保护",
              "level": 1,
              "status": "Passed",
              "scope": "4个新增Python AST；更新交接前全部已有文件摘要未变；最终保护见step-05-final-check.json",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-05-verification.json",
                  "observation": "89 tests Passed: 24 semantic/fusion boundary tests using doubles and 65 existing tests; 4 new Python files AST Passed",
                  "supports": "local output validation, fusion, downgrade, source tracing and regression scope",
                  "does_not_support": "real backend availability, semantic effectiveness, business combination approval or production integration"
                }
              ],
              "gap": null
            },
            {
              "name": "固定A/B/C输入预检",
              "level": 2,
              "status": "Passed",
              "scope": "3个相同目标；A规则候选筛至同目标；B/C规范化文本和坐标相同",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-05-smoke.json",
                  "observation": "target_equivalence=Passed; actual_live_calls=0; metrics=null",
                  "supports": "固定输入组织可运行",
                  "does_not_support": "B/C真实推理或上下文效果"
                }
              ],
              "gap": "B/C未执行推理"
            },
            {
              "name": "真实模型小样本烟测",
              "level": 3,
              "status": "Blocked",
              "scope": "真实适配网络/计数器/批准模型/数据路径/费用预算",
              "evidence_refs": [],
              "gap": "没有已批准后端、数据路径或金额预算；零真实调用"
            },
            {
              "name": "正式组合策略",
              "level": 3,
              "status": "Blocked",
              "scope": "正式分类/关系/保护等级策略启用",
              "evidence_refs": [],
              "gap": "只有显式test_only共现引擎测试，没有业务规则批准"
            },
            {
              "name": "独立识别效果评测",
              "level": 4,
              "status": "Untested",
              "scope": "precision/recall/F1/上下文提升及独立测试集",
              "evidence_refs": [],
              "gap": "本步只预检，不提前执行后续实验或设定门槛"
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
  },
  "artifacts": [
    {
      "file": "semantic-design-v1.md",
      "role": "内部语义/融合约定、待批准烟测与回滚"
    },
    {
      "file": "step-05-smoke-fixture.json",
      "role": "固定合成工程样本"
    },
    {
      "file": "step-05-smoke.json",
      "role": "实际A/B/C输入预检；真实路径Blocked"
    },
    {
      "file": "step-05-verification.json",
      "role": "命令/实际输出/AST/摘要；本地测试89项"
    },
    {
      "file": "step-05-final-check.json",
      "role": "最终交接/链接/前序保护检查"
    },
    {
      "file": "verify_step05.py",
      "role": "无模型/无数据库本地复现脚本"
    },
    {
      "file": "history/handoff-step-04.md",
      "role": "前一步交接原样存档"
    },
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
    },
    {
      "target": "backend/mainline1/fusion.py",
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
    },
    {
      "target": "backend/mainline1/semantic_smoke.py",
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
    },
    {
      "target": "backend/mainline1/tests/test_semantic.py",
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
  "findings": [
    {
      "id": "F5-local",
      "claim": "语义边界、融合和降级局部行为已实现验证",
      "capability_status": "Implemented",
      "evidence_status": "Verified",
      "verification_status": "Passed",
      "confidence": "High",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-05-verification.json",
          "observation": "89 tests Passed: 24 semantic/fusion boundary tests using doubles and 65 existing tests; 4 new Python files AST Passed",
          "supports": "local output validation, fusion, downgrade, source tracing and regression scope",
          "does_not_support": "real backend availability, semantic effectiveness, business combination approval or production integration"
        }
      ]
    },
    {
      "id": "F5-live",
      "claim": "真实运输代码存在，但真实后端与效果未验证",
      "capability_status": "Partial",
      "evidence_status": "Verified",
      "verification_status": "Blocked",
      "confidence": "High",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "semantic-design-v1.md",
          "observation": "显式适配实现及可审阅烟测方案；无真实批准与调用",
          "supports": "真实路径当前阻塞范围",
          "does_not_support": "真实模型识别能力"
        }
      ]
    },
    {
      "id": "F5-effect",
      "claim": "上下文改善程度未知",
      "capability_status": "Unknown",
      "evidence_status": "Unknown",
      "verification_status": "Untested",
      "confidence": "Low",
      "evidence_refs": []
    },
    {
      "id": "F5-combination",
      "claim": "局部关系候选引擎有替身/规则测试，业务组合未激活",
      "capability_status": "Partial",
      "evidence_status": "Verified",
      "verification_status": "Passed",
      "confidence": "High",
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
  "changes": {
    "items": [
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
      },
      {
        "target": "backend/mainline1/fusion.py",
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
      },
      {
        "target": "backend/mainline1/semantic_smoke.py",
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
      },
      {
        "target": "backend/mainline1/tests/test_semantic.py",
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
    "scope": "4个新增代码文件及本步文档，README/acceptance/HANDOFF增量；前序业务代码/Schema/生产配置/DB/依赖未改",
    "important_alternatives": [
      "显式运输适配替代会自动加载环境与跨provider路由的registry",
      "整格拒绝坏模型输出，不做正则JSON恢复或模糊定位",
      "默认组合关闭，仅可信owner配置启用；测试策略不当业务事实",
      "缓存关闭，避免未经证明的模型输出复用"
    ],
    "unverified_assumptions": [
      "生产owner执行逐次鉴权并可信注入批准凭据",
      "指定模型token计数、价格上界、服务端取消及SDK端点兼容待验",
      "输入和模型输出包含私有原文；仅返回内存，未来存储/清理需owner负责",
      "预算仅单批本地；生产多尝试/并发需要持久化总账"
    ],
    "rollback": "按清单撤回4个新增源文件及本步文档/README等增量；前序HANDOFF已存档。保留用户/其他任务文件，不reset/clean；无业务库变化"
  },
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
    },
    {
      "name": "Proposed Finding/Profile兼容",
      "level": 3,
      "status": "Passed",
      "scope": "测试验证来源、融合发现和画像符合未改公共Schema；不发布公共服务",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-05-verification.json",
          "observation": "89 tests Passed: 24 semantic/fusion boundary tests using doubles and 65 existing tests; 4 new Python files AST Passed",
          "supports": "local output validation, fusion, downgrade, source tracing and regression scope",
          "does_not_support": "real backend availability, semantic effectiveness, business combination approval or production integration"
        }
      ],
      "gap": "内部snapshot不是公共ScanRunSnapshot；画像持久化/权威适用性未接入"
    },
    {
      "name": "静态和前序文件保护",
      "level": 1,
      "status": "Passed",
      "scope": "4个新增Python AST；更新交接前全部已有文件摘要未变；最终保护见step-05-final-check.json",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-05-verification.json",
          "observation": "89 tests Passed: 24 semantic/fusion boundary tests using doubles and 65 existing tests; 4 new Python files AST Passed",
          "supports": "local output validation, fusion, downgrade, source tracing and regression scope",
          "does_not_support": "real backend availability, semantic effectiveness, business combination approval or production integration"
        }
      ],
      "gap": null
    },
    {
      "name": "固定A/B/C输入预检",
      "level": 2,
      "status": "Passed",
      "scope": "3个相同目标；A规则候选筛至同目标；B/C规范化文本和坐标相同",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-05-smoke.json",
          "observation": "target_equivalence=Passed; actual_live_calls=0; metrics=null",
          "supports": "固定输入组织可运行",
          "does_not_support": "B/C真实推理或上下文效果"
        }
      ],
      "gap": "B/C未执行推理"
    },
    {
      "name": "真实模型小样本烟测",
      "level": 3,
      "status": "Blocked",
      "scope": "真实适配网络/计数器/批准模型/数据路径/费用预算",
      "evidence_refs": [],
      "gap": "没有已批准后端、数据路径或金额预算；零真实调用"
    },
    {
      "name": "正式组合策略",
      "level": 3,
      "status": "Blocked",
      "scope": "正式分类/关系/保护等级策略启用",
      "evidence_refs": [],
      "gap": "只有显式test_only共现引擎测试，没有业务规则批准"
    },
    {
      "name": "独立识别效果评测",
      "level": 4,
      "status": "Untested",
      "scope": "precision/recall/F1/上下文提升及独立测试集",
      "evidence_refs": [],
      "gap": "本步只预检，不提前执行后续实验或设定门槛"
    }
  ],
  "approved_decisions": [
    {
      "decision": "仅实施第5步内部适配/校验/融合/降级与合成测试；没有实质授权时独立工作继续",
      "source": "用户第5步执行1及本轮continue；完整提示词B3/B4"
    },
    {
      "decision": "保留前序有效内部实现授权；不覆盖其他任务，不安装新依赖",
      "source": "用户本步共同约束；前序HANDOFF"
    }
  ],
  "judgment_changes": [
    {
      "previous": "第4步语义与组合均未实现/未执行",
      "current": "语义/融合内部实现与测试替身路径已验；真实路径Blocked、业务组合默认关闭",
      "new_evidence_refs": [
        {
          "source": "repository",
          "location": "step-05-verification.json",
          "observation": "89 tests Passed: 24 semantic/fusion boundary tests using doubles and 65 existing tests; 4 new Python files AST Passed",
          "supports": "local output validation, fusion, downgrade, source tracing and regression scope",
          "does_not_support": "real backend availability, semantic effectiveness, business combination approval or production integration"
        }
      ],
      "affected_decisions": [
        "可供后续内部组件消费，但不能声称真实模型效果或批准业务组合"
      ]
    },
    {
      "previous": "仅接口构造与超时异常注入证据",
      "current": "增加实际async等待超时、费用预留不退还、上下文指纹隔离和跨行不组合验证",
      "new_evidence_refs": [
        {
          "source": "repository",
          "location": "step-05-verification.json",
          "observation": "89 tests Passed: 24 semantic/fusion boundary tests using doubles and 65 existing tests; 4 new Python files AST Passed",
          "supports": "local output validation, fusion, downgrade, source tracing and regression scope",
          "does_not_support": "real backend availability, semantic effectiveness, business combination approval or production integration"
        }
      ],
      "affected_decisions": [
        "限本地替身，不扩展为真实运输/远端计费保证"
      ]
    }
  ],
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
  ],
  "next_step_constraints": [
    "本步结束停止，等待第6步；不得自动调用模型或推进复核/计划/独立实验",
    "正式后端必须先批准模型、数据路径及累计预算；本地单批费用预留不是跨运行持久化总账",
    "默认没有业务组合规则；test_only及替身证据不得进入生产或效果报告",
    "保留规则/语义/fusion来源与原始未校准分数，不把上下文描述当事实",
    "公共契约仍Proposed；第6步不得自行发布接口、撤销其他主线决策或修改外发政策",
    "真实owner、production政策/部署/画像存储/适用性服务仍受前序待决项限制"
  ],
  "next_stage_constraints": [
    "本步结束停止，等待第6步；不得自动调用模型或推进复核/计划/独立实验",
    "正式后端必须先批准模型、数据路径及累计预算；本地单批费用预留不是跨运行持久化总账",
    "默认没有业务组合规则；test_only及替身证据不得进入生产或效果报告",
    "保留规则/语义/fusion来源与原始未校准分数，不把上下文描述当事实",
    "公共契约仍Proposed；第6步不得自行发布接口、撤销其他主线决策或修改外发政策",
    "真实owner、production政策/部署/画像存储/适用性服务仍受前序待决项限制"
  ],
  "authorization_remaining": [
    "真实模型/数据路径/总预算",
    "正式类别与组合政策",
    "生产接入及公共契约发布"
  ]
}
```
