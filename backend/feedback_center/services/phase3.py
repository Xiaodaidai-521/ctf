"""Phase 3 contract metadata.

Issue groups, candidates, approval, activation, observation and rollback are
implemented.  Writes are gated by ``FEEDBACK_PHASE3_ENABLED`` and release
actions by ``FEEDBACK_PHASE3_RELEASE_ENABLED``; both default to false so the
first phase cannot publish a teaching configuration by accident.  This module
only describes the contract and the gate state; the behaviour lives in
``services/issue_groups.py`` and ``services/candidates.py``.
"""

from django.conf import settings

from .. import constants


def _phase3_enabled():
    return bool(getattr(settings, 'FEEDBACK_PHASE3_ENABLED', False))


def _release_enabled():
    return bool(getattr(settings, 'FEEDBACK_PHASE3_RELEASE_ENABLED', False))


def contract_payload():
    return {
        'schema_version': constants.PHASE3_CONTRACT_VERSION,
        'enabled': _phase3_enabled(),
        'implemented': True,
        'candidate_management_enabled': _phase3_enabled(),
        'candidate_release_enabled': _release_enabled(),
        'reason': (
            '第三阶段功能已实现；写入与发布默认关闭，需在评测或第三阶段环境显式开启。'
            if not _phase3_enabled() else '第三阶段功能已启用。'
        ),
        'invariants': [
            '反馈“已处理”不等于新规则已生效，也不等于教学效果已验证。',
            '候选只能引用已确认、证据完整且映射完整的反馈；重复记录和缺证记录不能作为独立证据。',
            '跨尝试问题组必须由反馈负责人人工确认成员，保存纳入/排除理由、版本和审核人。',
            '候选必须绑定唯一改动因素、任务版本、目录版本、基准配置摘要和回退版本。',
            '模块八持有评测集、运行与报告；模块七持有候选审核、发布与回退状态，不复制评测或成绩系统。',
            '审批绑定确切配置摘要和完整评测报告；配置、范围或报告变化后旧审批失效，必须重新评测审批。',
            '发布只影响后续教学任务；已开始尝试保留领取时版本，旧判定与成绩不追溯改写。',
            '回退保留前后版本、审批、评测和事件；发布/回退失败不得报成功，未知状态保留待对账。',
            '全模型停用（生成、向量化、模型重排）时，规则汇总、人工复核、问题组和候选登记仍可工作。',
        ],
        'issue_group': {
            'group_id': 'uuid',
            'category': 'recognition|decision|teaching',
            'issue_type': 'stable issue type',
            'task_key': 'string',
            'task_version': 'string',
            'catalog_version': 'string',
            'knowledge_point_ids': ['stable ID'],
            'time_window': {'from': 'ISO 8601', 'to': 'ISO 8601'},
            'member_feedback_ids': ['feedback UUID'],
            'excluded_feedback_ids': ['feedback UUID'],
            'exclusion_reasons': {'feedback UUID': 'reason'},
            'counts': {
                'raw_feedback': 'int',
                'deduplicated_instances': 'int',
                'distinct_students': 'int',
                'missing_evidence': 'int',
            },
            'reviewed_by': 'teacher id',
            'reviewed_at': 'ISO 8601',
            'version': 'int',
            'supersedes_group_id': 'uuid|null',
            'split_merge_history': ['audit entries'],
        },
        'candidate': {
            'candidate_id': 'uuid',
            'issue_group_ids': ['uuid'],
            'baseline_config_version': 'string',
            'candidate_config_version': 'string',
            'single_changed_factor': 'string',
            'target_task_versions': ['task@version'],
            'excluded_scope': ['string'],
            'expected_risk': 'string',
            'owner_id': 'teacher/admin id',
            'rollback_version': 'string',
            'state': 'draft|pending_eval|evaluating|needs_revision|pending_approval|approved_pending_release|observing|stable|rolled_back|withdrawn',
            'config_digest': 'sha256',
            'evaluation_report_ref': {
                'module': 'module8',
                'run_id': 'string',
                'report_id': 'string',
                'report_version': 'string',
                'report_digest': 'sha256',
                'recommendation': 'pass|fail|insufficient_evidence',
            },
            'approval': {
                'approver_id': 'id',
                'approved_at': 'ISO 8601',
                'approved_config_digest': 'sha256',
                'approved_report_id': 'string',
                'scope': 'string',
                'observation_window': 'string',
                'rollback_condition': 'string',
            },
            'activation': {
                'activated_by': 'id',
                'activated_at': 'ISO 8601',
                'applicable_future_tasks': ['task@version'],
                'effective_config_digest': 'sha256',
            },
            'observation': {
                'status': 'observing|stable|insufficient_evidence|paused',
                'report_id': 'string',
                'new_failures': 'int',
                'normal_block_rate': 'numerator/denominator/missing',
                'unauthorized_allow_rate': 'numerator/denominator/missing',
            },
            'rollback': {
                'rolled_back_by': 'id',
                'rolled_back_at': 'ISO 8601',
                'from_version': 'string',
                'to_version': 'string',
                'reason': 'string',
                'result': 'success|failed|unknown_pending_reconciliation',
            },
        },
        'module8_report_reference': {
            'run_id': 'string',
            'report_id': 'string',
            'report_version': 'string',
            'report_digest': 'sha256',
            'dataset_version': 'string',
            'baseline_config_digest': 'sha256',
            'candidate_config_digest': 'sha256',
            'recommendation': 'pass|fail|insufficient_evidence',
            'completed': 'bool',
            'missing_cases': 'int',
        },
        'manual_approval': {
            'required_roles': ['authorized approver', 'release operator'],
            'cannot_be_same_person': True,
            'approval_does_not_trigger_release': True,
        },
        'activation_observation_rollback': {
            'activation_affects_future_tasks_only': True,
            'old_attempts_and_scores_unchanged': True,
            'rollback_is_manual_and_audited': True,
            'unknown_state_requires_reconciliation': True,
        },
        'next_tasks': [
            'M7-P3-1 跨尝试问题组：人工成员确认、去重实例数、不同学生数、缺证数与拆并组历史。',
            'M7-P3-2 候选与配置版本：草稿、待评测、评测中、待审批、已批准待发布、观察中、已稳定/已回退/已撤回。',
            'M7-P3-3 模块八报告引用：run_id/report_id/report_version/report_digest 与逐例差异链接，不复制报告。',
            'M7-P3-4 人工审批：审批绑定确切配置摘要与报告；审批不触发执行。',
            'M7-P3-5 生效与观察：只影响后续任务，记录生效时间、适用任务和观察窗口。',
            'M7-P3-6 回退：保留前后版本、操作者、原因和结果；未知状态待对账。',
            'M7-P3-7 首个候选：教学模拟导出阈值 T=100→T=120；正常/越权/缺事实/边界案例与独立终验。',
        ],
    }


def disabled_response():
    return {
        'enabled': False,
        'code': constants.PHASE3_WRITE_DISABLED,
        'detail': '第三阶段候选管理未启用；本轮只采集与处理反馈。',
        'contract_version': constants.PHASE3_CONTRACT_VERSION,
    }
