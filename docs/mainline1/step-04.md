# 第4步：分类配置、规则识别与基础画像

记录日期：2026-10-14；代码与测试于2026-10-13完成。**status: partial**：本步内部规则基线已完成并验证；正式分类/等级政策及公共接入前置仍缺失，未自行批准。没有进入第5步。

- 基线版本与调用边界：[rule-baseline-v1.md](rule-baseline-v1.md)。
- 实际验证：[step-04-verification.json](step-04-verification.json)，65项Passed（24本步＋41前序回归）。
- 来源区分：正例由真实规则实现检测；仅失败路径注入异常。未调用模型、未运行独立效果实验，未重跑或扩大第3步数据库验证。
- 公共兼容：BusinessContext、ClassificationPolicy、Finding、SensitivityProfile通过未改动的Proposed Schema；内部snapshot与覆盖清单另行标识，不伪造已存在的权威适用性服务。

```json
{
  "step": "04",
  "status": "partial",
  "scope": "内部规则基线已完成；正式政策/公共接入仍缺前置，不宣称生产就绪",
  "recorded_on": "2026-10-14",
  "repository_state": {
    "root": "D:/aaa10/16015478源码/project-code",
    "revision": "f4ac82caf32a4112c047cdb8848cab135acbb3c6",
    "branch": "feature/Sensitive-data-recognition",
    "existing_modifications": "第1—3步未跟踪mainline1目录及用户3份提示词；本步开始记录step-04-input-state.json",
    "rules": "未找到适用AGENTS；按主提示词、共同交接约定、.editorconfig执行",
    "input_configuration": {
      "product_spec": "完整任务提示词B/C/D/F/J基线",
      "approved_contracts": "Unknown；现有14个公共对象仍Proposed",
      "approved_change_scope": "本步内部配置/规则/上下文/画像/合成测试/交接",
      "approved_dependencies": "未新增；只用已有依赖",
      "approved_schema_changes": "本步无schema或业务库迁移",
      "semantic_backend": "Unknown，未调用",
      "data_policy": "只用合成样本；无原文外发",
      "acceptance_targets": "功能用例已给；数值效果门槛Unknown",
      "delivery_mode": "backend_only仅设计推荐，UI不在本步"
    }
  },
  "mission": {
    "solved": [
      "版本化字典/规则集/等级映射及重复/悬空/冲突/摘要校验",
      "来源/版本/确认状态明确的不可变上下文，用户描述及模型推断不自确认为事实",
      "ASCII邮箱/IPv4/Luhn数字候选检测、必要格式校验、原文位置及规则证据",
      "未命中/未检测/检测失败/证据不足/冲突独立表示",
      "兼容Proposed的rule Finding和基础SensitivityProfile，政策确定等级、四层覆盖分离",
      "完整运行快照与指纹、默认关闭且有TTL/容量/字节上限的私有缓存",
      "24项规则合成测试及41项回归通过，规则版本和局限固定"
    ],
    "not_solved": [
      "没有批准生产分类/等级政策，开发draft配置强制拒绝production",
      "公共发布/真实owner/画像持久化和权威适用性未接入；不把预留applicability_ref当服务可用",
      "真实语义/融合/复核/外发/独立效果评测不在本步"
    ]
  },
  "stage_result": {
    "schema": "mainline1.step4.rules.v1 / E7-stage4-4A-subset",
    "data": {
      "milestone_results": {
        "4A": {
          "delivered": [
            "规则基线与上下文、规则发现/基础画像、分层覆盖、固定快照和缓存隔离"
          ],
          "not_delivered": [
            "真实语义/融合/组合",
            "生产政策激活和公共接入"
          ],
          "changes": [
            {
              "target": "backend/mainline1/classification.py",
              "motivation": "建立可复现规则基线、可信上下文、候选发现/画像及定向验证",
              "dependencies": [
                "第3步ParseResult",
                "既有Proposed契约",
                "Python标准库；已有jsonschema仅测试"
              ],
              "priority": "P1",
              "authorization": "用户第4步指令；规范B3/B4允许契约待确认时独立内部实现",
              "rollback": "仅撤回本步新增文件和交接增量，保留第1—3步代码/用户提示词；无DB变更，不用reset/clean",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-04-verification.json",
                  "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
                  "supports": "internal reproducible rule baseline and profile builder",
                  "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
                }
              ]
            },
            {
              "target": "backend/mainline1/rules.py",
              "motivation": "建立可复现规则基线、可信上下文、候选发现/画像及定向验证",
              "dependencies": [
                "第3步ParseResult",
                "既有Proposed契约",
                "Python标准库；已有jsonschema仅测试"
              ],
              "priority": "P1",
              "authorization": "用户第4步指令；规范B3/B4允许契约待确认时独立内部实现",
              "rollback": "仅撤回本步新增文件和交接增量，保留第1—3步代码/用户提示词；无DB变更，不用reset/clean",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-04-verification.json",
                  "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
                  "supports": "internal reproducible rule baseline and profile builder",
                  "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
                }
              ]
            },
            {
              "target": "backend/mainline1/config/rule-baseline-v1.json",
              "motivation": "建立可复现规则基线、可信上下文、候选发现/画像及定向验证",
              "dependencies": [
                "第3步ParseResult",
                "既有Proposed契约",
                "Python标准库；已有jsonschema仅测试"
              ],
              "priority": "P1",
              "authorization": "用户第4步指令；规范B3/B4允许契约待确认时独立内部实现",
              "rollback": "仅撤回本步新增文件和交接增量，保留第1—3步代码/用户提示词；无DB变更，不用reset/clean",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-04-verification.json",
                  "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
                  "supports": "internal reproducible rule baseline and profile builder",
                  "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
                }
              ]
            },
            {
              "target": "backend/mainline1/tests/test_rules.py",
              "motivation": "建立可复现规则基线、可信上下文、候选发现/画像及定向验证",
              "dependencies": [
                "第3步ParseResult",
                "既有Proposed契约",
                "Python标准库；已有jsonschema仅测试"
              ],
              "priority": "P1",
              "authorization": "用户第4步指令；规范B3/B4允许契约待确认时独立内部实现",
              "rollback": "仅撤回本步新增文件和交接增量，保留第1—3步代码/用户提示词；无DB变更，不用reset/clean",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-04-verification.json",
                  "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
                  "supports": "internal reproducible rule baseline and profile builder",
                  "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
                }
              ]
            }
          ],
          "verification": [
            {
              "name": "规则与前序回归",
              "level": 2,
              "status": "Passed",
              "scope": "backend执行 python -B -m unittest discover -s mainline1/tests -v；65项，24本步+41既有；2026-10-13实际运行",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-04-verification.json",
                  "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
                  "supports": "internal reproducible rule baseline and profile builder",
                  "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
                }
              ],
              "gap": null
            },
            {
              "name": "草案契约兼容",
              "level": 3,
              "status": "Passed",
              "scope": "BusinessContext/ClassificationPolicy/Finding/SensitivityProfile 使用现有schema；公共schema未更改",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-04-verification.json",
                  "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
                  "supports": "internal reproducible rule baseline and profile builder",
                  "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
                }
              ],
              "gap": "内部snapshot不是公共ScanRunSnapshot；applicability_ref只预留，未发布权威服务"
            },
            {
              "name": "新文件静态/前序保护",
              "level": 1,
              "status": "Passed",
              "scope": "3个新增Python文件AST，4个代码/配置摘要；更新交接前全部已有文件摘要未变，tracked/index diff为空",
              "evidence_refs": [
                {
                  "source": "repository",
                  "location": "step-04-verification.json",
                  "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
                  "supports": "internal reproducible rule baseline and profile builder",
                  "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
                }
              ],
              "gap": null
            },
            {
              "name": "正式分类政策及生产接入",
              "level": 3,
              "status": "Blocked",
              "scope": "生产规则激活/资产鉴权/公共接口/画像持久化及权威适用性",
              "evidence_refs": [],
              "gap": "正式政策和跨线批准未知；开发政策仅draft且production拒绝"
            },
            {
              "name": "真实语义及独立A/B/C效果",
              "level": 4,
              "status": "Untested",
              "scope": "本步不调用模型、不执行第5/9步实验",
              "evidence_refs": [],
              "gap": "无已批准后端、数据路径或预算；不得以Mock或规则替代真实语义"
            }
          ]
        },
        "4B": {
          "delivered": [],
          "not_delivered": [
            "人工复核/替代画像；本步未授权开展"
          ],
          "changes": [],
          "verification": []
        },
        "4C": {
          "delivered": [],
          "not_delivered": [
            "计划/下游通知；本步未授权开展"
          ],
          "changes": [],
          "verification": []
        },
        "4D": {
          "delivered": [],
          "not_delivered": [
            "重扫比较/UI/公开入口/生产清理；本步未授权开展"
          ],
          "changes": [],
          "verification": []
        }
      },
      "open_questions": [
        {
          "id": "Q4-policy",
          "status": "Unknown",
          "blocking_scope": "正式类别/等级政策及生产激活；不阻塞本步合成内部规则验证",
          "resolution_needed": "推荐由分类政策owner提供正式字典/等级定义/映射及版本，再适配现有loader；替代由owner审阅rule-baseline-v1后另行确认可用类别与等级，当前L1/L2/L3只为合成开发配置，不能直接用于生产或法律结论。"
        },
        {
          "id": "D02/D03",
          "status": "Unknown",
          "blocking_scope": "真实资产读取鉴权、公共契约发布、画像存储及适用性接入",
          "resolution_needed": "延续第3步HANDOFF：指定现有资产owner及正式契约；按批准范围接入，不另建跨模块资产系统，不擅自迁移业务库。"
        },
        {
          "id": "D04",
          "status": "Unknown",
          "blocking_scope": "第5步真实语义验证",
          "resolution_needed": "仅在用户启动第5步后，选择已批准provider/model、允许输入路径和费用上限；否则只完成接口/降级验证，真实调用保持Blocked。"
        }
      ]
    }
  },
  "artifacts": [
    {
      "path": "backend/mainline1/classification.py",
      "purpose": "严格配置和不可变上下文"
    },
    {
      "path": "backend/mainline1/rules.py",
      "purpose": "格式检测、覆盖、候选画像、快照/指纹/缓存"
    },
    {
      "path": "backend/mainline1/config/rule-baseline-v1.json",
      "purpose": "draft开发字典/规则/政策"
    },
    {
      "path": "backend/mainline1/tests/test_rules.py",
      "purpose": "24项合成功能/契约测试"
    },
    {
      "path": "docs/mainline1/rule-baseline-v1.md",
      "purpose": "规则版本、输入可见性、契约用法和局限"
    },
    {
      "path": "docs/mainline1/step-04-verification.json",
      "purpose": "真实运行摘要/代码摘要与证据边界"
    },
    {
      "path": "docs/mainline1/step-04-input-state.json",
      "purpose": "本步修改前文件摘要，用于保护已有工作"
    }
  ],
  "findings": [
    {
      "claim": "内部规则基线、上下文、发现画像和缓存隔离实现且定向验证通过",
      "capability_status": "Implemented",
      "evidence_status": "Verified",
      "confidence": "High",
      "verification_status": "Passed",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-04-verification.json",
          "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
          "supports": "internal reproducible rule baseline and profile builder",
          "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
        }
      ],
      "limitations": "仅3类格式候选，不证明真实业务身份；只验证固定合成样本，未评估准确率/召回率"
    },
    {
      "claim": "当前配置是开发draft政策，不能进入production；跨线契约仍Proposed",
      "capability_status": "Partial",
      "evidence_status": "Verified",
      "confidence": "High",
      "verification_status": "Blocked",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "backend/mainline1/classification.py RuleConfiguration.load; rules.py scan_rules",
          "observation": "draft-only config and allowed_environments guard",
          "supports": "无自动生产激活",
          "does_not_support": "正式政策批准或公共鉴权"
        }
      ],
      "limitations": "公共接入前由owner确认"
    }
  ],
  "changes": {
    "items": [
      {
        "target": "backend/mainline1/classification.py",
        "motivation": "建立可复现规则基线、可信上下文、候选发现/画像及定向验证",
        "dependencies": [
          "第3步ParseResult",
          "既有Proposed契约",
          "Python标准库；已有jsonschema仅测试"
        ],
        "priority": "P1",
        "authorization": "用户第4步指令；规范B3/B4允许契约待确认时独立内部实现",
        "rollback": "仅撤回本步新增文件和交接增量，保留第1—3步代码/用户提示词；无DB变更，不用reset/clean",
        "evidence_refs": [
          {
            "source": "repository",
            "location": "step-04-verification.json",
            "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
            "supports": "internal reproducible rule baseline and profile builder",
            "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
          }
        ]
      },
      {
        "target": "backend/mainline1/rules.py",
        "motivation": "建立可复现规则基线、可信上下文、候选发现/画像及定向验证",
        "dependencies": [
          "第3步ParseResult",
          "既有Proposed契约",
          "Python标准库；已有jsonschema仅测试"
        ],
        "priority": "P1",
        "authorization": "用户第4步指令；规范B3/B4允许契约待确认时独立内部实现",
        "rollback": "仅撤回本步新增文件和交接增量，保留第1—3步代码/用户提示词；无DB变更，不用reset/clean",
        "evidence_refs": [
          {
            "source": "repository",
            "location": "step-04-verification.json",
            "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
            "supports": "internal reproducible rule baseline and profile builder",
            "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
          }
        ]
      },
      {
        "target": "backend/mainline1/config/rule-baseline-v1.json",
        "motivation": "建立可复现规则基线、可信上下文、候选发现/画像及定向验证",
        "dependencies": [
          "第3步ParseResult",
          "既有Proposed契约",
          "Python标准库；已有jsonschema仅测试"
        ],
        "priority": "P1",
        "authorization": "用户第4步指令；规范B3/B4允许契约待确认时独立内部实现",
        "rollback": "仅撤回本步新增文件和交接增量，保留第1—3步代码/用户提示词；无DB变更，不用reset/clean",
        "evidence_refs": [
          {
            "source": "repository",
            "location": "step-04-verification.json",
            "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
            "supports": "internal reproducible rule baseline and profile builder",
            "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
          }
        ]
      },
      {
        "target": "backend/mainline1/tests/test_rules.py",
        "motivation": "建立可复现规则基线、可信上下文、候选发现/画像及定向验证",
        "dependencies": [
          "第3步ParseResult",
          "既有Proposed契约",
          "Python标准库；已有jsonschema仅测试"
        ],
        "priority": "P1",
        "authorization": "用户第4步指令；规范B3/B4允许契约待确认时独立内部实现",
        "rollback": "仅撤回本步新增文件和交接增量，保留第1—3步代码/用户提示词；无DB变更，不用reset/clean",
        "evidence_refs": [
          {
            "source": "repository",
            "location": "step-04-verification.json",
            "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
            "supports": "internal reproducible rule baseline and profile builder",
            "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
          }
        ]
      }
    ],
    "scope": "新增4个代码/配置文件及本步文档，更新README/acceptance/HANDOFF；未改既有解析/任务代码、公共Schema、生产配置、DB或依赖清单",
    "important_alternatives": [
      "采用内置受限实现，拒绝任意外部正则/代码",
      "配置文件替代复杂后台；不伪造正式政策",
      "先供融合器消费稳定Finding，保持semantic/combination not_run；不因缺模型改公共字段",
      "缓存默认关闭；只做单进程私有复用，不引入新基础设施"
    ],
    "unverified_assumptions": [
      "真实owner逐次鉴权；ConfirmationReceipt只能由可信服务创建，非认证机制",
      "正式画像持久化与applicability需要后续owner服务"
    ],
    "rollback": "移除本步新增4文件及本步文档，按差异恢复README/acceptance/HANDOFF；不撤回第1—3步文件，不删除业务数据。"
  },
  "verification": [
    {
      "name": "规则与前序回归",
      "level": 2,
      "status": "Passed",
      "scope": "backend执行 python -B -m unittest discover -s mainline1/tests -v；65项，24本步+41既有；2026-10-13实际运行",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-04-verification.json",
          "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
          "supports": "internal reproducible rule baseline and profile builder",
          "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
        }
      ],
      "gap": null
    },
    {
      "name": "草案契约兼容",
      "level": 3,
      "status": "Passed",
      "scope": "BusinessContext/ClassificationPolicy/Finding/SensitivityProfile 使用现有schema；公共schema未更改",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-04-verification.json",
          "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
          "supports": "internal reproducible rule baseline and profile builder",
          "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
        }
      ],
      "gap": "内部snapshot不是公共ScanRunSnapshot；applicability_ref只预留，未发布权威服务"
    },
    {
      "name": "新文件静态/前序保护",
      "level": 1,
      "status": "Passed",
      "scope": "3个新增Python文件AST，4个代码/配置摘要；更新交接前全部已有文件摘要未变，tracked/index diff为空",
      "evidence_refs": [
        {
          "source": "repository",
          "location": "step-04-verification.json",
          "observation": "65 tests Passed: 24 new rule tests and 41 parsing/task-state regressions; unchanged proposed-schema compatibility checks",
          "supports": "internal reproducible rule baseline and profile builder",
          "does_not_support": "production policy approval, authorization, semantic effectiveness or public deployment"
        }
      ],
      "gap": null
    },
    {
      "name": "正式分类政策及生产接入",
      "level": 3,
      "status": "Blocked",
      "scope": "生产规则激活/资产鉴权/公共接口/画像持久化及权威适用性",
      "evidence_refs": [],
      "gap": "正式政策和跨线批准未知；开发政策仅draft且production拒绝"
    },
    {
      "name": "真实语义及独立A/B/C效果",
      "level": 4,
      "status": "Untested",
      "scope": "本步不调用模型、不执行第5/9步实验",
      "evidence_refs": [],
      "gap": "无已批准后端、数据路径或预算；不得以Mock或规则替代真实语义"
    }
  ],
  "approved_decisions": [
    {
      "decision": "只实施第4步；规则配置/上下文/格式检测/基础画像/快照缓存及合成验证",
      "source": "用户本步指令及两次continue延续同一任务"
    },
    {
      "decision": "契约未正式批准时可推进不绑定公共API的内部纯函数和测试",
      "source": "完整提示词B3/B4；用户要求缺失实质授权只阻塞相关工作"
    }
  ],
  "judgment_changes": [
    {
      "previous": "HANDOFF记录规则/语义/联合识别均未实现执行",
      "current": "新增内部规则识别/画像并验证；语义/组合仍not_run，生产政策和公共接入仍Blocked",
      "new_evidence": "65项测试及配置生产拒绝验证",
      "impact": "后续融合器可消费候选rule findings，不把规则当真实语义或已确认业务事实"
    },
    {
      "previous": "第4步需要正式分类政策，当前未提供",
      "current": "采用显式draft且仅test/development的合成开发政策推进独立实现；正式等级语义仍待owner",
      "new_evidence": "规范B3/B4和当前用户实施指令",
      "impact": "不重复请求常规内部实现许可，不改变外发政策或自行激活生产政策"
    }
  ],
  "open_questions": [
    {
      "id": "Q4-policy",
      "status": "Unknown",
      "blocking_scope": "正式类别/等级政策及生产激活；不阻塞本步合成内部规则验证",
      "resolution_needed": "推荐由分类政策owner提供正式字典/等级定义/映射及版本，再适配现有loader；替代由owner审阅rule-baseline-v1后另行确认可用类别与等级，当前L1/L2/L3只为合成开发配置，不能直接用于生产或法律结论。"
    },
    {
      "id": "D02/D03",
      "status": "Unknown",
      "blocking_scope": "真实资产读取鉴权、公共契约发布、画像存储及适用性接入",
      "resolution_needed": "延续第3步HANDOFF：指定现有资产owner及正式契约；按批准范围接入，不另建跨模块资产系统，不擅自迁移业务库。"
    },
    {
      "id": "D04",
      "status": "Unknown",
      "blocking_scope": "第5步真实语义验证",
      "resolution_needed": "仅在用户启动第5步后，选择已批准provider/model、允许输入路径和费用上限；否则只完成接口/降级验证，真实调用保持Blocked。"
    }
  ],
  "next_step_constraints": [
    "本步结束停止，等待用户第5步；不自动调用真实模型",
    "第5步保留规则输入可见性/字典/版本/样本及coverage口径；不得用语义结果覆盖rule来源或伪造概率",
    "正式分类/等级政策须owner确认；开发L1/L2/L3不得成为生产判定",
    "真实资产/公共接入仍受D02/D03约束；内部snapshot与DTO不可直接作为公共ScanRunSnapshot/权限凭据",
    "画像quality complete只代表显式规则扫描要求满足；不等于复核完成或外发授权；semantic/combination不曾执行不得写complete"
  ]
}
```
