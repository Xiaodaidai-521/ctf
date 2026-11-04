const labels = {
  title: '标题', name: '名称', label: '项目', description: '说明', summary: '摘要', reason: '理由', note: '说明', notes: '备注', remarks: '评语', text: '内容', content: '内容', explanation: '解释', answer: '回答', result: '结果',
  task: '任务', student: '学生', username: '账号', version: '版本', task_version: '任务版本', catalog_version: '目录版本', rubric_version: '量表版本', verifier_version: '核验规则版本',
  status: '状态', overall_status: '综合结果', program_status: '核验结果', manual_status: '评阅结果', outcome: '结果', independence: '独立性', assistance: '帮助记录', level: '帮助层级', shown: '已展示', source: '来源', tracking: '帮助记录情况', requested_not_shown: '请求但未展示', answer_exposure: '接触过解析',
  items: '分项', item_results: '分项结果', score: '得分', max_points: '满分', total_score: '总分', max_total_score: '满分', passed: '通过', decision: '结论', correct: '正确', expected: '预期', actual: '实际',
  basis: '依据与范围', causal: '因果解释', evidence: '证据与不确定项', improvement: '改进与验证', risk_reasons: '风险原因', selection_reason: '抽选依据', findings: '复核发现',
  created_at: '记录时间', submitted_at: '提交时间', claimed_at: '开始时间', effective_at: '生效时间', due_at: '到期时间', completed_at: '完成时间', updated_at: '更新时间',
  capabilities: '能力', knowledge_points: '知识点', events: '事件记录', facts: '学习事实', versions: '版本', metrics: '指标', numerator: '分子', denominator: '分母', missing: '缺失', rate: '比例', records: '记录', cases: '样例', case: '样例', checks: '检查', message: '说明', detail: '详情', errors: '未通过项', count: '数量', expected_outcome: '预期结果',
  status_label: '状态', kind_label: '评阅方式', independence_label: '独立性', level_label: '帮助层级', source_label: '来源', tracking_label: '帮助记录情况',
  web: 'Web安全', crypto: '密码学', pwn: '二进制安全', reverse: '逆向工程', forensics: '数字取证', misc: '综合杂项',
  time_score: '学习投入指数', completion_score: '完成指数', mastery_score: '掌握指数', retention_score: '记忆保持指数', consistency_score: '学习节奏指数', efficiency_score: '学习效率指数', engagement_score: '参与指数', focus_score: '专注指数', total_effect_score: '综合学习效果指数',
}
const values = {
  passed: '通过', failed: '未通过', pending: '待完成', scored: '已评分', pass: '通过', fail: '未通过', unknown: '未知', pending_review: '待教师评阅', pending_manual: '待教师评阅', reviewed: '已评阅', independent: '平台内独立', assisted: '受助', not_submitted: '未提交', not_run: '未核验', not_applicable: '不适用', environment_affected: '受环境影响', verification_failed: '核验未完成', partial: '部分缺失', complete: '完整', available: '可核对', none: '无', student: '学生', teacher: '教师', program: '程序核验', manual: '人工评阅', completed: '已完成', pending_item: '待补题', overdue: '已超期',
  high_risk: '高风险抽选', random: '随机抽选', census: '全部查看', independent_retest: '无提示复测', spaced_retest: '间隔复测', equivalent_task: '同能力新场景',
}

export function recordRows(value, path = '') {
  if (value == null) return []
  if (Array.isArray(value)) return value.flatMap((item, index) => recordRows(item, `${path}${index + 1} · `))
  if (typeof value !== 'object') return [{ label: path || '内容', value: readableValue(value) }]
  return Object.entries(value).flatMap(([key, entry]) => {
    const label = Object.hasOwn(labels, key) ? labels[key] : ''
    if (!label) return [{ label: `${path}补充资料`, value: entry == null || entry === '' ? '未提供' : '已记录，完整内容可下载核对' }]
    if (entry && typeof entry === 'object') return recordRows(entry, `${path}${label} · `)
    return [{ label: `${path}${label}`, value: readableValue(entry) }]
  })
}

function readableValue(value) {
  if (value == null || value === '') return '未提供'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'number') return String(value)
  if (Object.hasOwn(values, value)) return values[value]
  if (/^\d{4}-\d{2}-\d{2}(T[\d:.+-]+Z?)?$/.test(value) || /^v?\d+(?:[.-]\d+)*$/i.test(value)) return value
  if (/[㐀-鿿]/.test(value) && !/[a-z]+_[a-z]|[0-9a-f]{8}-[0-9a-f-]{27,}/i.test(value)) return value
  return '已记录，完整内容可下载核对'
}
