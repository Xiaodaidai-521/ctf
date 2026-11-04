const pathFields = ['title', 'description', 'difficulty', 'estimated_hours', 'color', 'order', 'is_published']
const moduleFields = ['title', 'description', 'module_type', 'content', 'order', 'estimated_minutes', 'is_required']
const pick = (value, fields) => Object.fromEntries(fields.filter(key => value[key] !== undefined).map(key => [key, value[key]]))
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const saveIssue = message => Object.assign(new Error(message), { userFacing: true })
export function pathSaveError(error) {
  const status = error.response?.status
  if (status === 401) return '登录已失效，请重新登录后核对航线。'
  if (status === 403) return '你没有保存这条航线的权限，请联系管理员。'
  if (status === 404) return '航线或章节当前不可访问，请重新读取或联系管理员核对。'
  if (status === 400) {
    const fields = Object.keys(error.response.data || {})
    const labels = { title: '标题', description: '描述', difficulty: '难度', estimated_hours: '预计学习时长', estimated_minutes: '章节时长', color: '主题色', slug: '访问地址名称', order: '排序' }
    const known = fields.map(field => labels[field]).filter(Boolean)
    return known.length ? `保存未被接受，请检查${known.join('、')}。` : '保存未被接受，请检查航线与章节的必填内容。'
  }
  if (status >= 500) return '保存服务出错，暂时无法完成保存。请保留填写内容并联系管理员核对。'
  return '保存结果尚未确认，请先重新读取航线核对，不要重复新建。'
}

// Existing endpoints are not a transaction. Keep each acknowledged ID so a
// partial failure cannot silently create a second path or chapter on retry.
export async function persistPath({ api, form, chapters, originalModules, current, acknowledged }) {
  const originals = new Map(originalModules.map(row => [row.id, row]))
  if (originalModules.some(row => !chapters.some(chapter => chapter.id === row.id))) throw saveIssue('暂不能保存章节删除，请重新读取原航线；本次内容尚未保存。')
  for (const chapter of chapters) {
    const original = originals.get(chapter.id)
    if (chapter.solution_hint && chapter.solution_hint !== (original?.solution_hint || '')) throw saveIssue('实验提示暂不能保存，请保留原提示后重试。')
    if (!same(chapter.prerequisites || [], original?.prerequisites || []) || !same(chapter.challenges || [], original?.challenges || [])) throw saveIssue('前置章节与实验关联暂不能保存更改，请保留原关联后重试。')
  }
  let pathId = form.id
  const data = pick(form, pathFields)
  const result = pathId ? await api.update(pathId, data) : await api.create({ ...data, ...(form.slug?.trim() ? { slug: form.slug.trim() } : {}) })
  if (!current()) return null
  if (!result?.id) throw saveIssue('保存结果缺少可核对的航线，请重新读取，不要重复新建。')
  pathId = result.id
  acknowledged('path', pathId)
  for (const chapter of chapters) {
    const body = pick(chapter, moduleFields)
    const saved = originals.has(chapter.id)
      ? await api.updateModule(chapter.id, body)
      : await api.createModule({ ...body, learning_path: pathId })
    if (!current()) return null
    if (!saved?.id) throw saveIssue('章节保存结果无法核对，请重新读取航线。')
    acknowledged('module', saved.id, chapter)
  }
  const [path, modules] = await Promise.all([api.detail(pathId), api.modules(pathId)])
  if (!current()) return null
  if (!Array.isArray(modules) || !path) throw saveIssue('保存已接受，但航线与章节暂未完整读回，请重新读取。')
  if (!Object.entries(data).every(([key, value]) => same(path[key], value))) throw saveIssue('保存已接受，但航线内容读回不一致，请重新读取核对。')
  for (const chapter of chapters) {
    const found = modules.find(row => row.id === chapter.id)
    if (!found || !Object.entries(pick(chapter, moduleFields)).every(([key, value]) => same(found[key], value))) throw saveIssue('保存已接受，但章节内容读回不一致，请重新读取核对。')
  }
  return { path, modules }
}
