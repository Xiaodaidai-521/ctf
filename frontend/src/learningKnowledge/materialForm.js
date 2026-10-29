const sourceLimits = {
  title: 300, publisher: 200, source_version: 100, source_snapshot: 100000,
  license_id: 100, attribution_text: 1000, reuse_scope: 200, applicability: 2000,
}
const optionalLimits = { source_url: 200, license_url: 200, change_note: 1000, conflict_group: 100 }
const sourceFields = [...Object.keys(sourceLimits), ...Object.keys(optionalLimits),
  'source_date', 'verified_at', 'recheck_due_at']
const classes = ['lesson', 'hint', 'student_analysis', 'teacher_answer', 'grading_secret']
const types = ['teacher_authored', 'article', 'resource', 'knowledge_concept', 'legal_clause']

function fail(message) { throw new Error(message) }
function object(value, fields, label) {
  if (!value || Array.isArray(value) || typeof value !== 'object') fail(`${label} 必须是 JSON 对象。`)
  const extras = Object.keys(value).filter(key => !fields.includes(key))
  if (extras.length) fail(`${label} 不支持字段：${extras.join('、')}。`)
}
function text(value, limit, label, optional = false) {
  if (typeof value !== 'string' || (!optional && !value.trim()) || [...value].length > limit) {
    fail(`${label} 必须为${optional ? '可空' : '非空'}字符串，最多 ${limit} 字。`)
  }
}

export function parseMaterialForm(json, mode) {
  let data
  try { data = JSON.parse(json) } catch { fail('请输入严格 JSON：使用双引号，不含注释或尾随逗号。') }
  const registering = mode === 'register'
  object(data, registering
    ? ['catalog_version', 'task_ids', 'material_class', 'hint_level', 'source_type', 'source_object_id', 'metadata']
    : ['task_ids', 'metadata'], '请求')
  if (!Array.isArray(data.task_ids) || data.task_ids.length < 1 || data.task_ids.length > 20
    || data.task_ids.some(id => !Number.isSafeInteger(id) || id < 1)) {
    fail('task_ids 必须包含 1–20 个正整数任务数据库 ID，不能使用任务键。')
  }
  if (registering) {
    text(data.catalog_version, 64, 'catalog_version')
    if (!classes.includes(data.material_class)) fail(`material_class 只能为 ${classes.join(' / ')}。`)
    if (data.source_type !== undefined && !types.includes(data.source_type)) fail(`source_type 只能为 ${types.join(' / ')}。`)
    if (data.source_object_id != null && (!Number.isSafeInteger(data.source_object_id) || data.source_object_id < 1)) {
      fail('source_object_id 必须为正整数或 null。')
    }
    if (data.material_class === 'hint' && ![1, 2, 3, 4].includes(data.hint_level)) fail('hint 必须提供 1–4 的 hint_level。')
    if (data.material_class !== 'hint' && data.hint_level != null) fail('只有 hint 可设置 hint_level。')
  }
  object(data.metadata, sourceFields, 'metadata')
  for (const [key, limit] of Object.entries(sourceLimits)) text(data.metadata[key], limit, `metadata.${key}`)
  for (const [key, limit] of Object.entries(optionalLimits)) {
    if (data.metadata[key] !== undefined) text(data.metadata[key], limit, `metadata.${key}`, true)
  }
  for (const key of ['source_date', 'verified_at']) {
    const value = data.metadata[key]
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)
      || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) {
      fail(`metadata.${key} 必须为有效 YYYY-MM-DD 日期。`)
    }
  }
  const due = data.metadata.recheck_due_at
  if (due != null && (typeof due !== 'string' || !/^\d{4}-\d{2}-\d{2}T/.test(due) || !Number.isFinite(Date.parse(due)))) {
    fail('metadata.recheck_due_at 必须为 ISO 日期时间或 null。')
  }
  return data
}

export function materialExample(mode) {
  const data = {
    task_ids: [1],
    metadata: {
      title: '示例：来源核验说明（提交前替换）',
      publisher: '实际编写者或发布机构',
      source_url: '',
      source_version: '1.0',
      source_date: '2026-01-01',
      verified_at: '2026-01-02',
      source_snapshot: '第一段原文，仅纯文本。\n\n第二段原文；空行用于分段。',
      license_id: '替换为真实许可标识',
      license_url: '',
      attribution_text: '替换为要求保留的署名',
      reuse_scope: '替换为许可允许的使用范围',
      applicability: '替换为适用课程、任务与前提；不适用情形也应注明',
      change_note: '说明本次登记或修订原因',
      recheck_due_at: null,
      conflict_group: '',
    },
  }
  return JSON.stringify(mode === 'register' ? {
    catalog_version: '替换为实际课程目录版本',
    material_class: 'lesson',
    source_type: 'teacher_authored',
    source_object_id: null,
    ...data,
  } : data, null, 2)
}
