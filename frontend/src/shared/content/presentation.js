export const difficulties = [
  { value: 'easy', label: '简单' }, { value: 'medium', label: '中等' },
  { value: 'hard', label: '困难' }, { value: 'expert', label: '专家' },
]
export const statuses = [
  { value: 'pending', label: '待审核' }, { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已拒绝' }, { value: 'all', label: '全部' },
]
export const resourceTypes = [
  { value: 'document', label: '文档' }, { value: 'video', label: '视频' },
  { value: 'report', label: '报告' }, { value: 'zip', label: '压缩包' },
  { value: 'ai_resource', label: '智能体生成资源' },
]
export const resourceCategories = ['网络安全', 'Web安全', '逆向工程', '密码学', '渗透测试']
export const difficultyLabel = value => difficulties.find(item => item.value === value)?.label || '未标注'
export const statusLabel = value => statuses.find(item => item.value === value)?.label || '状态待确认'
export const resourceTypeLabel = value => resourceTypes.find(item => item.value === value)?.label || '其他资源'
export const redirectLabel = value => ({ http: '子域名访问', path: '路径访问', direct: '直接访问' })[value] || '未设置'
export const resourceIcon = value => ({ document: 'bi-file-text', video: 'bi-camera-video', report: 'bi-file-text', zip: 'bi-box-seam', ai_resource: 'bi-stars' })[value] || 'bi-folder2'
export const formatDate = value => value && Number.isFinite(new Date(value).getTime()) ? new Date(value).toLocaleString('zh-CN') : '未提供'
export function formatFileSize(bytes) {
  if (!Number.isFinite(Number(bytes)) || bytes == null || Number(bytes) < 0) return '未提供'
  const value = Number(bytes)
  const index = value === 0 ? 0 : Math.max(0, Math.min(3, Math.floor(Math.log(value) / Math.log(1024))))
  return `${(value / 1024 ** index).toFixed(2)} ${['B', 'KB', 'MB', 'GB'][index]}`
}
export function contentError(error, role, task) {
  const status = error?.response?.status
  if (status === 403 && role === 'teacher' && task === '读取资源') return '当前教师账号没有资源审核权限，暂时无法查看审核列表。请联系管理员处理审核；你仍可上传教学资源，或前往知识基座查找资料。'
  if (status === 403) return `当前账号无权${task}，请联系管理员确认权限。`
  if (status === 401) return '登录已过期，请重新登录后重试。'
  if (status === 404) return `${task}未完成，内容不存在、尚未获准访问或文件暂不可用。`
  if (status === 400) return `${task}未完成，请检查必填内容和文件格式后重试。`
  return `${task}暂时未完成，请稍后重试。`
}
// 不将无效响应或失败当成零条记录。
export function readList(response) {
  if (Array.isArray(response)) return { items: response, total: response.length, hasNext: false }
  if (!Array.isArray(response?.results) || !Number.isInteger(response.count) || response.count < 0) throw new Error('Invalid content list')
  return { items: response.results, total: response.count, hasNext: Boolean(response.next) }
}
export const challengeFields = ['title', 'category', 'difficulty', 'score', 'description', 'flag', 'hint', 'is_active', 'docker_image', 'redirect_port', 'redirect_type']
export function challengeForm(detail = {}) {
  const defaults = { title: '', category: null, difficulty: 'easy', score: 10, description: '', flag: '', hint: '', is_active: true, docker_image: '', redirect_port: null, redirect_type: '' }
  return Object.fromEntries(challengeFields.map(key => [key, detail[key] ?? defaults[key]]))
}
export function saveResourceFile(response, resource, documentObject = document, urlObject = URL) {
  const disposition = response.headers?.['content-disposition'] || ''
  const match = disposition.match(/filename\*?=(?:UTF-8''|\")?([^;\"]+)/i)
  let name = resource.file_name || resource.title || '学习资源'
  if (match) { try { name = decodeURIComponent(match[1].trim()) } catch { /* 保留可读文件名 */ } }
  const url = urlObject.createObjectURL(response.data)
  const link = documentObject.createElement('a')
  try {
    link.href = url
    link.download = name
    documentObject.body.appendChild(link)
    link.click()
  } finally { link.remove(); urlObject.revokeObjectURL(url) }
}
