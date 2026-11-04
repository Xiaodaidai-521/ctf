import { errorMessage } from './api.js'

export const canManageLibrary = role => role === 'teacher' || role === 'admin'
export const statusLabel = value => ({
  draft: '草稿', in_review: '审阅中', approved: '已批准', published: '已发布', withdrawn: '已撤回',
  completed: '已入库', failed: '未完成', pending: '待处理', processing: '处理中', active: '有效',
  indexed: '已收录', ready: '可用', stale: '已过期', running: '处理中',
  not_indexed: '待处理', versioned: '已收录', legacy_lexical: '已收录',
}[value] || '未提供')
export const classLabel = value => ({
  lesson: '学习材料', hint: '分级提示', student_analysis: '学生解析', teacher_answer: '教师答案', grading_secret: '评分密钥',
}[value] || '教学材料')
export function formatLocator(value) {
  if (typeof value === 'string') {
    if (/^\s*[\[{]/.test(value)) return ''
    if (/^知识点\s*·/.test(value)) return '知识点'
    const parts = value.replace(/索引块\s*(\d+)（原文定位待补齐）/g, '段落 $1')
      .split(/\s*\/\s*/).filter(part => part && !/^[\w.]*[-_:][\w.:-]+$/.test(part))
    return [...new Set(parts)].join(' / ')
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return ''
  const heading = Array.isArray(value.heading_path) ? value.heading_path.map(formatLocator).filter(Boolean) : []
  const parts = [...heading, ...[value.chapter, value.article_number].filter(item => typeof item === 'string').map(formatLocator)]
  for (const [key, label] of [['page', '页'], ['paragraph', '段落']]) {
    if (Number.isSafeInteger(value[key]) && value[key] > 0) parts.push(`${label} ${value[key]}`)
  }
  return parts.filter(Boolean).join(' / ')
}

export function sourceText(text, sourceType) {
  if (sourceType !== 'resource' || typeof text !== 'string') return text
  // The resource projection appends its type enum after the source description/tags.
  const types = { document: '文档', video: '视频', report: '报告', zip: '压缩包', ai_resource: 'AI 资料' }
  return text.replace(/(^|\n)(document|video|report|zip|ai_resource)\s*$/, (_, prefix, type) => `${prefix}${types[type]}`)
}

// Only the presentation is simplified; controller errors and upload results remain intact.
export function libraryError(message) {
  if (!message) return ''
  if (message.startsWith('登录已失效')) return '登录已失效，请重新登录。'
  if (message.startsWith('服务器拒绝') || message.includes('无权访问')) return '无法查看或操作此资料，请确认账号权限。'
  if (message.startsWith('材料或证据当前不可用')) return '资料暂不可用，请刷新列表。'
  if (message.startsWith('修订或状态冲突')) return '资料已更新，请刷新后重试。'
  if (message.startsWith('授权服务暂不可用')) return '暂时无法读取资料，请稍后重试。'
  if (message.startsWith('服务器未接受请求')) return '提交内容有误，请检查后重试。'
  if (message.startsWith('请先选择')) return '请先选择需要上传的文档。'
  if (message.startsWith('知识点链接无效')) return '知识点链接无效，请返回资料库重新打开。'
  if (/大小|too large/i.test(message)) return '文件过大，请缩小后重试。'
  if (/embedding|provider|配置|解析|入库失败/i.test(message)) return '文档处理失败，请检查文件内容或联系管理员。'
  return '操作未完成，结果尚未确认。请重新加载；若刚上传文档，请先核对资料列表，避免重复上传。'
}
export function safeSourceLink(value) {
  if (typeof value !== 'string' || /[\s\\\u0000-\u001f]/.test(value)) return ''
  if (/^\/(?!\/)/.test(value)) return value
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) ? url.href : ''
  } catch { return '' }
}

export function initialLibraryState() {
  return {
    group: 'teaching', query: '', sourceType: '', page: 1, rows: [], count: 0,
    next: false, previous: false, detail: null, searched: false, busy: false, error: '',
    uploadOpen: false, uploadTitle: '', uploadVisibility: 'internal', file: null, uploadResult: null,
  }
}

// Shared by teacher/admin layouts. Client role checks do not replace server authorization.
// State is reactive in the component, plain in tests; every response uses the existing privacy ticket.
export function createLibraryController({ state, privacy, api, getRole }) {
  const managing = () => canManageLibrary(getRole())
  function clearResults() {
    Object.assign(state, {
      rows: [], count: 0, next: false, previous: false, detail: null, searched: false,
    })
  }
  function clear() {
    const group = state.group
    Object.assign(state, initialLibraryState(), { group })
  }
  function failure(error) {
    // A denied detail invalidates the list too: it may have been withdrawn since search.
    clearResults()
    state.uploadResult = null
    state.error = errorMessage(error)
  }
  function allowed() {
    if (managing()) return true
    clear()
    state.error = '当前身份无权访问知识资料库；仅教师和管理员可使用。'
    return false
  }
  async function search(page = 1) {
    if (!allowed() || state.busy) return
    const ticket = privacy.begin()
    if (!ticket) return
    const group = state.group
    const query = state.query.trim()
    clearResults()
    state.error = ''
    state.page = page
    state.busy = true
    try {
      if (group === 'teaching') {
        // Search authorized titles/current snapshots server-side, never fetch all source bodies.
        const result = await api.materialSearch(query, ticket.signal)
        if (!ticket.isCurrent()) return
        state.rows = result.results || []
        state.count = state.rows.length
      } else {
        const params = { group, q: query, page }
        if (state.sourceType) params.source_type = state.sourceType
        const result = await api.library(params, ticket.signal)
        if (!ticket.isCurrent()) return
        state.rows = result.results || []
        state.count = result.count
        state.next = Boolean(result.next)
        state.previous = Boolean(result.previous)
      }
      state.searched = true
    } catch (error) {
      if (ticket.isCurrent()) failure(error)
    } finally {
      if (ticket.isCurrent()) state.busy = false
      ticket.finish()
    }
  }
  async function inspect(row) {
    if (!allowed() || state.busy) return
    const ticket = privacy.begin()
    if (!ticket) return
    state.detail = null
    state.error = ''
    state.busy = true
    try {
      const result = state.group === 'teaching'
        ? await api.inspect(row.material_id, row.revision, ticket.signal)
        : await api.libraryDetail(row.source_type, row.object_id, ticket.signal)
      if (ticket.isCurrent()) state.detail = result
    } catch (error) {
      if (ticket.isCurrent()) failure(error)
    } finally {
      if (ticket.isCurrent()) state.busy = false
      ticket.finish()
    }
  }
  async function upload() {
    if (!allowed() || state.busy) return
    if (!state.file) {
      state.error = '请先选择需要入库的文档。'
      return
    }
    const ticket = privacy.begin()
    if (!ticket) return
    const body = new FormData()
    body.append('file', state.file)
    body.append('title', state.uploadTitle.trim() || state.file.name)
    body.append('visibility', state.uploadVisibility)
    state.error = ''
    state.uploadResult = null
    state.busy = true
    try {
      const result = await api.upload(body, ticket.signal)
      if (!ticket.isCurrent()) return
      clearResults()
      state.uploadResult = result
      if (result.status !== 'completed') state.error = result.error_message || '服务器未确认索引完成，请核对入库状态。'
      state.file = null
    } catch (error) {
      if (!ticket.isCurrent()) return
      failure(error)
      const job = error.response?.data
      if (job && typeof job.status === 'string') {
        state.uploadResult = job
        state.error = job.error_message || '入库失败，服务器未完成索引。'
      } else if (error.response?.status === 413) {
        state.error = error.response.data?.detail || '文件超过服务器允许的大小。'
      }
    } finally {
      if (ticket.isCurrent()) state.busy = false
      ticket.finish()
    }
  }
  return { clear, clearResults, search, inspect, upload }
}
