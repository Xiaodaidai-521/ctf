"""Versioned acceptance selectors; missing infrastructure is never a pass.

Run the union of selectors with Django's test command. These are fixed regression
cases maintained by developers, not an independent final acceptance dataset.
"""

VERSION = 'm8-phase1-acceptance/2'
FACTOR_SETS = [
    {'dataset_version': 'm8-synthetic-regression/1', 'mode': 'deterministic_replay',
     'factors': ['export_record_limit'], 'case_count': 25, 'provider_calls': False,
     'tests': ['evaluation_center.tests.test_evaluations']},
    {'dataset_version': 'm8-live-export-classification/1', 'mode': 'live_gateway',
     'factors': ['prompt_version', 'model_id'], 'case_count': 6, 'provider_calls': True,
     'input_source': 'synthetic', 'repeat_count': 2,
     'models': ['deepseek-v4-flash', 'deepseek-v4.1'],
     'prompts': ['export-classifier/v1', 'export-classifier/v2'],
     'tests': ['evaluation_center.tests.test_live_evaluations', 'evaluation_center.tests.test_gateway'],
     'live_command': 'run_live_evaluation --settings=evaluation_center.scratch_settings',
     'automated_tests_use_mock_transport': True},
]
SCENARIOS = [
    {'id': 1, 'title': '原版本与映射', 'tests': [
        'evaluation_center.tests.test_projections.ProjectionTests.test_distinct_versions_are_not_combined',
        'evaluation_center.tests.test_projections.ProjectionTests.test_unmapped_history_is_excluded',
        'learning_map.tests.test_module1.ModuleOneServiceTests.test_freeze_and_publish_after_signoff',
    ], 'dependencies': ['实际课程目录及材料签收']},
    {'id': 2, 'title': '角色/归属/材料授权', 'tests': [
        'evaluation_center.tests.test_api.LearningAPITests',
        'teaching_agent.tests.test_context_permissions',
        'teaching_agent.tests.test_api_failures.APITutoringFailureTests.test_success_call_facts_permission_aware_cache_and_withdrawal',
    ], 'dependencies': ['模块三全部检索路径及撤权联调']},
    {'id': 3, 'title': '正式/演示/离线隔离与只读', 'tests': [
        'evaluation_center.tests.test_api.LearningAPITests.test_explicit_demo_is_readonly_and_never_fallback',
        'evaluation_center.tests.test_evaluations.EvaluationTests.test_no_source_teaching_scores_profiles_or_policies_are_written',
        'evaluation_center.tests.test_acceptance.FixedAcceptanceTests.test_03_08_10_network_isolation_and_actual_execution_remain_unverified',
    ], 'dependencies': []},
    {'id': 4, 'title': '帮助/解析/首次/复测口径', 'tests': [
        'evaluation_center.tests.test_projections.ProjectionTests',
        'teaching_agent.tests.test_hints_state',
    ], 'dependencies': ['平台外帮助不可观测，不作排除承诺']},
    {'id': 5, 'title': '保存失败/去重/迟到/恢复', 'tests': [
        'evaluation_center.tests.test_acceptance.FixedAcceptanceTests.test_05_source_save_rollback_retry_and_idempotency',
        'evaluation_center.tests.test_acceptance.FixedAcceptanceTests.test_05_todo_save_error_is_retryable_without_false_success',
        'evaluation_center.tests.test_operations.OperationsTests',
        'learning_map.tests.test_module1.ModuleOneServiceTests.test_claim_rolls_back_when_event_write_fails',
    ], 'dependencies': ['真实跨服务故障与并发压测；M6提交HTTP数据库错误仍为通用失败']},
    {'id': 6, 'title': '断连/超时/429/额度/全模型停用', 'tests': [
        'evaluation_center.tests.test_acceptance.FixedAcceptanceTests',
        'teaching_agent.tests.test_no_ai_flow',
        'teaching_agent.tests.test_api_failures',
    ], 'dependencies': ['真实供应商故障与恢复；真实十秒等待上限实测']},
    {'id': 7, 'title': '无AI必评/教师处理/复测', 'tests': [
        'evaluation_center.tests.test_acceptance.FixedAcceptanceTests',
        'evaluation_center.tests.test_operations.OperationsTests',
    ], 'dependencies': []},
    {'id': 8, 'title': '网络实例与宿主/生产隔离', 'tests': [
        'evaluation_center.tests.test_acceptance.FixedAcceptanceTests.test_03_08_10_network_isolation_and_actual_execution_remain_unverified',
    ], 'dependencies': ['模块五真实靶场：网络边界、凭证、资源时限、暂停/回收均未联调']},
    {'id': 9, 'title': '冻结重放/预算/完整性/报告信任', 'tests': [
        'evaluation_center.tests.test_evaluations.EvaluationTests',
        'evaluation_center.tests.test_live_evaluations',
        'evaluation_center.tests.test_gateway',
        'feedback_center.tests.test_forged_report_repro',
        'feedback_center.tests.test_phase3.CandidateStateMachineTests',
    ], 'dependencies': ['真实网关批次须显式单独执行，不以mock测试代替；知识库API对比未开展']},
    {'id': 10, 'title': '两主线教师处理到新场景复测', 'tests': [
        'evaluation_center.tests.test_acceptance.FixedAcceptanceTests',
        'skill_review.tests.test_module6.Module6UnavailableVerifierTests.test_unconnected_server_verifier_never_passes',
    ], 'dependencies': ['数据线现为M1/M2/M6合成规则闭环，模块四实验台未接通；网络线缺模块五服务端证据']},
]


def test_labels():
    labels = {label for scenario in SCENARIOS for label in scenario['tests']}
    return sorted(label for label in labels if not any(
        label.startswith(parent + '.') for parent in labels if parent != label
    ))
