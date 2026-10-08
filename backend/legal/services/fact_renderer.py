"""Render confirmed fact snapshots for compliance analysis."""

from django.conf import settings

WARNING_LABELS = {
    'missing_start_event': '未找到成功启动事件，过程证据可能不完整',
    'missing_terminal_event': '未找到停止或过期清理事件，需人工核对最终状态',
    'missing_resource_limit': '未在审计事件中确认完整的 CPU/内存限制',
    'container_operation_failure': '存在容器启动或停止失败事件',
    'legacy_event_schema': '包含旧版审计事件，关联可靠性较低',
}


def render_for_analysis(snapshot) -> str:
    facts = snapshot.automated_facts or {}
    runtime = facts.get('runtime_seconds')
    runtime_text = f'{round(runtime / 60, 1)} 分钟' if runtime is not None else '无法计算'
    warnings = [WARNING_LABELS.get(item, item) for item in (snapshot.warnings or [])]
    lines = [
        '【系统自动归集事实】',
        f"题目：{facts.get('challenge_title') or '-'}",
        f"容器状态：{facts.get('container_status') or '-'}；运行时长：{runtime_text}",
        f"启动成功/失败：{facts.get('start_success_count', 0)}/{facts.get('start_failure_count', 0)}；停止成功/失败：{facts.get('stop_success_count', 0)}/{facts.get('stop_failure_count', 0)}",
        f"镜像：{facts.get('image') or '-'}；CPU 限制：{'已记录' if facts.get('has_cpu_limit') else '未确认'}；内存限制：{'已记录' if facts.get('has_memory_limit') else '未确认'}",
        f"Flag 提交：{facts.get('flag_submission_count', 0)} 次；正确：{facts.get('correct_submission_count', 0)} 次",
        f"审计事件：{facts.get('event_count', 0)} 条；账本引用：{len(snapshot.evidence_refs or [])} 条",
        '【证据完整性提示】',
        '；'.join(warnings) if warnings else '未发现明显证据缺口。',
        '【人工补充事实】',
        snapshot.manual_notes or '无。',
    ]
    limit = int(getattr(settings, 'LEGAL_FACT_MAX_MODEL_CHARS', 12000))
    return '\n'.join(lines)[:limit]
