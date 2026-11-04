// 练习环境状态映射：只解释服务端真实状态，不做定时增长的预计百分比，也不把超时当就绪。
export const ENVIRONMENT_LABELS = Object.freeze({
  not_started: '未启动', pending: '启动中', running: '运行中', stopped: '已停止', destroyed: '已销毁', error: '暂不可用',
})

export function normalizeEnvironment(value) {
  if (!value || typeof value !== 'object') return { status: 'not_started', label: '未启动', running: false, accessUrl: '', expiresAt: null }
  const status = ENVIRONMENT_LABELS[value.status] ? value.status : 'not_started'
  // 已规范化的对象再次传入时保持原值（服务端蛇形字段与本地驼峰字段都认）。
  const accessUrl = typeof value.access_url === 'string' ? value.access_url : typeof value.accessUrl === 'string' ? value.accessUrl : ''
  return {
    status,
    label: ENVIRONMENT_LABELS[status],
    running: value.is_running === true || status === 'running',
    expired: value.is_expired === true || value.expired === true,
    accessUrl,
    expiresAt: value.expires_at || value.expiresAt || null,
  }
}

// 服务端已运行但未给 expires_at 时明确“未提供”，不自造 30 分钟。
export function countdown(from, now = Date.now()) {
  if (!from) return { text: '未提供', seconds: null }
  const diff = Date.parse(from) - now
  if (!Number.isFinite(diff)) return { text: '未提供', seconds: null }
  if (diff <= 0) return { text: '已到期', seconds: 0 }
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  return { text: `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`, seconds }
}

// 启动响应只认明确成功；running 但无访问地址时保持“正在读取状态”，不提前给可用结论。
export function phaseFor(value) {
  const env = normalizeEnvironment(value)
  if (env.expired) return 'expired'
  if (env.running && env.accessUrl) return 'ready'
  if (env.running) return 'waiting'
  if (env.status === 'pending') return 'waiting'
  if (env.status === 'error') return 'error'
  return 'idle'
}
