// Content is handed over only within this signed-in session, never in a URL or storage.
let pending = null
export const teachingIdentity = user => `${user?.id ?? ''}:${user?.role ?? ''}`
export function clearTeachingTransfer() { pending = null }
export function teachingSource(detail) {
  if (!detail || ['teacher_answer', 'grading_secret'].includes(detail.material_class)) return null
  const full = detail.full_text || detail.source_snapshot
  if (typeof full === 'string' && full.trim()) return full.length <= 100000 ? { text: full, excerpt: false } : null
  const chunks = Array.isArray(detail.chunks) ? detail.chunks.filter(chunk => typeof chunk.text === 'string' && chunk.text.trim()) : []
  if (!chunks.length) return null
  const text = '以下为已授权资料的段落摘录，不代表完整原文。请核对来源、许可和教学适用范围后再发布。\n\n' + chunks.map((chunk, index) => `摘录 ${index + 1}\n${chunk.text}`).join('\n\n')
  return text.length <= 100000 ? { text, excerpt: true } : null
}
export function prepareTeachingTransfer(user, kind, detail) {
  pending = null
  if (user?.role !== 'teacher' || !user?.id || !['material', 'path'].includes(kind)) throw new Error('请使用教师账号准备教学内容。')
  if (['teacher_answer', 'grading_secret'].includes(detail?.material_class)) throw new Error('答案与评分保密材料不能转为学生学习任务。请在材料工坊按原分类审阅。')
  const content = teachingSource(detail)
  if (!content) throw new Error('请先打开原文或授权段落，再准备教学内容。')
  const { text, excerpt } = content
  const source = {
    title: `${detail.title || '教学资料'}${excerpt ? '（段落摘录）' : ''}`, publisher: detail.publisher || '',
    source_version: detail.source_version || '', source_url: detail.source_url || '',
    license_id: detail.license_id || '', license_url: detail.license_url || '',
    attribution_text: detail.attribution_text || '', reuse_scope: detail.reuse_scope || '',
    source_date: detail.source_date || '', verified_at: detail.verified_at || '',
    applicability: detail.applicability || '',
  }
  pending = { identity: teachingIdentity(user), createdAt: Date.now(), kind, title: source.title, text, excerpt, source,
    materialClass: detail.material_class || 'lesson' }
}
export function consumeTeachingTransfer(identity, kind) {
  const value = pending
  pending = null
  return value?.identity === identity && value.kind === kind && Date.now() - value.createdAt < 120000 ? value : null
}
