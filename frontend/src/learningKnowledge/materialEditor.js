import { parseMaterialForm } from './materialForm.js'
export { materialEditorSteps, useMaterialEditorSteps } from './materialEditorSteps.js'

export const materialClasses = [
  ['lesson', '学习材料'], ['hint', '分级提示'], ['student_analysis', '学生解析'],
  ['teacher_answer', '教师答案'], ['grading_secret', '评分保密材料'],
]
export const sourceTypes = [
  ['teacher_authored', '教师编写'], ['article', '文章'], ['resource', '学习资源'],
  ['knowledge_concept', '知识点资料'], ['legal_clause', '法律条文'],
]
export const metadataFields = [
  { key: 'title', label: '材料标题', max: 300, required: true },
  { key: 'publisher', label: '编写者或发布机构', max: 200, required: true },
  { key: 'source_version', label: '来源版本', max: 100, required: true },
  { key: 'source_url', label: '来源网址', max: 200, type: 'url' },
  { key: 'source_date', label: '来源日期', type: 'date', required: true },
  { key: 'verified_at', label: '来源核验日期', type: 'date', required: true },
  { key: 'license_id', label: '许可名称', max: 100, required: true },
  { key: 'license_url', label: '许可网址', max: 200, type: 'url' },
  { key: 'attribution_text', label: '署名要求', max: 1000, required: true, multiline: true },
  { key: 'reuse_scope', label: '许可允许的使用范围', max: 200, required: true, multiline: true },
  { key: 'applicability', label: '适用课程、任务与使用前提', max: 2000, required: true, multiline: true },
  { key: 'change_note', label: '本次变更说明', max: 1000, multiline: true },
  { key: 'conflict_group', label: '内容冲突分组', max: 100, help: '存在互相冲突的材料时，填写相同的分组名称；没有则留空。' },
  { key: 'source_snapshot', label: '完整原文', max: 100000, required: true, multiline: true, help: '保留完整内容与原有空行，保存后请逐段检查。' },
]
export const taskSelectionBlocker = '暂时无法按名称添加课程任务。请导入由课程负责人准备的材料文件；导入不代表已获授权，提交时仍需核验课程与任务权限。'

export function emptyMaterialDraft() {
  return {
    catalog_version: '', task_ids: [], material_class: 'lesson', hint_level: 1,
    source_type: 'teacher_authored', source_object_id: null,
    metadata: { ...Object.fromEntries(metadataFields.map(field => [field.key, ''])), recheck_due_at: null },
  }
}

export function importMaterialDraft(text, mode) {
  let data
  try { data = parseMaterialForm(text, mode) } catch {
    throw new Error('材料文件内容不完整或格式不正确，请按所选表单类型的模板准备，检查课程、任务、来源、日期与许可。')
  }
  return {
    ...emptyMaterialDraft(), ...data, metadata: { ...data.metadata },
    suppliedRegistrationFields: ['source_type', 'source_object_id', 'hint_level'].filter(key => Object.hasOwn(data, key)),
  }
}

// Empty placeholders are deliberately not a valid submission. Never hand out a
// sample task identity that might accidentally address a real course task.
export function materialTemplate(mode) {
  const { catalog_version, task_ids, material_class, source_type, source_object_id, metadata } = emptyMaterialDraft()
  return JSON.stringify(mode === 'register'
    ? { catalog_version, task_ids, material_class, source_type, source_object_id, metadata }
    : { task_ids, metadata }, null, 2)
}

// The legacy strict parser remains unchanged. This adapter retains every accepted
// metadata field (including omitted optional fields) and never copies an incomplete
// inspection into a new revision. Imported identities remain internal, not options
// fabricated by a name lookup, and all writes retain server authorization.
export function materialPayload(draft, mode) {
  if (!['register', 'revise'].includes(mode)) throw new Error('请选择登记或新修订。')
  if (!draft.task_ids?.length) throw new Error(taskSelectionBlocker)
  if (mode === 'register' && !draft.catalog_version) throw new Error('请选择课程。')
  for (const field of metadataFields) {
    const value = draft.metadata[field.key]
    if (field.required && (typeof value !== 'string' || !value.trim())) throw new Error(`请填写${field.label}。`)
    if (value === undefined && !field.required) continue
    if (typeof value !== 'string' || (field.max && [...value].length > field.max)) throw new Error(`请检查${field.label}的内容和长度。`)
    if (field.type === 'date' && (!/^\d{4}-\d{2}-\d{2}$/.test(value)
      || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value)) throw new Error(`请选择有效的${field.label}。`)
  }
  const body = { task_ids: [...draft.task_ids], metadata: { ...draft.metadata } }
  if (mode === 'register') {
    Object.assign(body, { catalog_version: draft.catalog_version, material_class: draft.material_class })
    const supplied = draft.suppliedRegistrationFields || ['source_type', 'source_object_id']
    for (const key of ['source_type', 'source_object_id']) {
      if (supplied.includes(key)) body[key] = draft[key]
    }
    if (draft.material_class === 'hint') body.hint_level = draft.hint_level
    else if (supplied.includes('hint_level')) body.hint_level = null
  }
  try { return parseMaterialForm(JSON.stringify(body), mode) } catch {
    throw new Error('材料内容不完整或选择已失效，请检查课程、任务、分类、来源和复查时间。')
  }
}

export function reviewError(error) {
  const status = error?.response?.status
  return ({
    400: '提交内容有误，或当前修订不满足操作条件。请检查表单、最新状态与独立审阅资格。',
    401: '登录已失效，请重新登录后再读取。',
    403: '无法完成操作，请确认登录状态与课程授权。',
    404: '材料或来源当前不可用，可能已撤回或授权变化。请重新加载核对。',
    409: '材料版本或状态已变化，请重新检查后操作。',
    503: '授权信息暂时无法确认，已停止展示内容。请稍后重新加载。',
  })[status] || '操作结果尚未确认，请先重新加载列表核对，避免重复提交。'
}

export const classLabel = value => materialClasses.find(([key]) => key === value)?.[1] || '教学材料'
export const statusLabel = value => ({ draft: '草稿', in_review: '审阅中', approved: '已批准', published: '已发布', withdrawn: '已撤回' }[value] || '状态暂不可用')
export const parseLabel = value => ({ pending: '等待整理', completed: '段落已就绪', failed: '段落整理失败' }[value] || '段落状态暂不可用')
export const scopeLabel = value => ({ internal: '仅内部使用', learner: '在授权任务内供学生使用' }[value] || '使用范围暂不可用')
export function dateLabel(value) {
  if (!value) return '未设置'
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return '日期暂不可用'
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
export function safeSourceLink(value) {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? value : ''
  } catch { return '' }
}

export function sourceChoices(result, type) {
  return (result?.results || []).filter(row => row.source_type === type
    && Number.isSafeInteger(row.object_id) && row.object_id > 0 && row.title?.trim())
    .map(row => ({ value: row.object_id, label: row.title }))
}

// Only the legal-document projection has clause identities. Embedding/document
// identities must never be submitted in place of a LegalClause primary key.
export function clauseChoices(detail, formatLocator) {
  if (detail?.source_type !== 'legal_document') return []
  return (detail.chunks || []).flatMap(chunk => {
    const match = /^clause:([1-9]\d*)$/.exec(chunk.id)
    if (!match || !Number.isSafeInteger(Number(match[1]))) return []
    const label = [chunk.title, formatLocator(chunk.locator)].filter(Boolean).join(' · ')
    return label ? [{ value: Number(match[1]), label }] : []
  })
}
