import axios from 'axios'

// Deliberately independent of the shared API and its localStorage/redirect interceptor.
const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
})

const segment = value => encodeURIComponent(String(value))
const get = async (path, signal, params) => (await client.get(path, { signal, params })).data
async function post(path, body, signal) {
  await get('/users/csrf/', signal)
  // Axios also checks the aborted signal before sending the mutation.
  return (await client.post(path, body, { signal })).data
}

export const knowledgeApi = {
  materials: signal => get('/teaching-knowledge/materials/', signal),
  inspect: (id, revision, signal) => get(`/teaching-knowledge/materials/${segment(id)}/chunks/`, signal,
    revision ? { revision } : undefined),
  register: (body, signal) => post('/teaching-knowledge/materials/', body, signal),
  revise: (id, body, signal) => post(`/teaching-knowledge/materials/${segment(id)}/revisions/`, body, signal),
  transition: (id, action, body, signal) => {
    if (!['submit', 'approve', 'publish', 'withdraw'].includes(action)) throw new Error('不支持的审阅操作。')
    return post(`/teaching-knowledge/materials/${segment(id)}/${action}/`, body, signal)
  },
  search: (body, signal) => post('/learning-knowledge/search/', body, signal),
  evidence: (id, signal) => get(`/learning-knowledge/evidence/${segment(id)}/`, signal),
  download: (id, signal) => get(`/learning-knowledge/evidence/${segment(id)}/download/`, signal),
  issue: (body, signal) => post('/learning-knowledge/evidence-issues/', body, signal),
}

export function errorMessage(error) {
  const status = error.response?.status
  if (status === 401) return '登录已失效，请重新登录后再读取。'
  if (status === 403) return '服务器拒绝访问或 CSRF 校验失败；请确认登录与课程授权。客户端不能授予权限。'
  if (status === 404) return '材料或证据当前不可用（可能已撤回、过期或授权变化）。请重新加载或请求教师补查。'
  if (status === 409) return '修订或状态冲突，请重新检查最新修订后操作。'
  if (status === 503) return '授权服务暂不可用，已停止展示本次内容；请稍后重新加载。'
  if (status === 400) {
    // Validation errors are text only; never render an error as HTML or log request bodies.
    const flatten = value => typeof value === 'string' ? value
      : Array.isArray(value) ? value.map(flatten).join('；')
        : value && typeof value === 'object'
          ? Object.entries(value).map(([key, detail]) => `${key}: ${flatten(detail)}`).join('；') : ''
    return `服务器未接受请求：${flatten(error.response.data).slice(0, 1200) || '请检查字段、版本、状态与审阅资格。'}`
  }
  return '请求未完成，未确认服务器结果。写操作可能已生效，请先重新加载；审阅操作可保留同一幂等标识重试。'
}
