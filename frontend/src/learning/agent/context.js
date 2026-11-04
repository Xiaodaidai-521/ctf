// 智能体上下文只包含学生已经授权的当前对象引用与可读信息。
// 任何上下文都不是授权凭据；后端仍独立校验。绝不夹带 Flag、答案输入或其他用户数据。
const ALLOWED_KINDS = new Set(['challenge', 'path', 'module', 'concept'])

export function sanitizeContext(input) {
  if (!input || typeof input !== 'object') return null
  const kind = ALLOWED_KINDS.has(input.kind) ? input.kind : null
  if (!kind) return null
  const ref = input.ref ?? input.id ?? null
  if (ref === null || ref === undefined || String(ref).trim() === '') return null
  const context = {
    kind,
    ref: String(ref),
    title: typeof input.title === 'string' ? input.title.slice(0, 120) : '',
    reason: typeof input.reason === 'string' ? input.reason.slice(0, 200) : '',
  }
  if (kind === 'path') {
    context.pathTitle = typeof input.pathTitle === 'string' ? input.pathTitle.slice(0, 120) : ''
    if (Number.isFinite(Number(input.progress))) context.progress = Number(input.progress)
  }
  if (kind === 'module') {
    context.pathRef = input.pathRef != null ? String(input.pathRef) : ''
    context.pathTitle = typeof input.pathTitle === 'string' ? input.pathTitle.slice(0, 120) : ''
  }
  if (kind === 'concept') context.subtitle = typeof input.subtitle === 'string' ? input.subtitle.slice(0, 120) : ''
  // 题面是否存在作者公开提示：只作区分标记，不携带提示正文。
  if (kind === 'challenge' && input.authorHint === true) context.authorHint = true
  return context
}

export function contextLabel(context) {
  if (!context) return ''
  const map = { challenge: '当前题目', path: '当前学习航线', module: '当前章节', concept: '当前知识点' }
  return `${map[context.kind] || '当前学习'}：${context.title || context.ref}`
}

export function sameContext(a, b) {
  return Boolean(a && b && a.kind === b.kind && String(a.ref) === String(b.ref))
}
