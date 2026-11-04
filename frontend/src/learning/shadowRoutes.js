// 四期影子入口兼容；只规划落点，不读取数据或改变后台授权。
export const DATA_SECURITY_TOPIC = '/resources/topics/data-security'
export const TEACHER_DATA_CASES = '/teacher/data-cases'
export const CAPABILITY_HISTORY = 'capability-history'

export function shadowDestination(to, role) {
  const path = String(to.path || '').replace(/\/+$/, '')
  const query = { ...to.query }
  const hash = to.hash || ''
  if (path === '/data-lab') return { path: DATA_SECURITY_TOPIC, query, hash }
  // 两端使用各自布局，原管理功能与后台授权不变。
  if (path === '/data-lab/teacher' && ['teacher', 'admin'].includes(role)) {
    return { path: role === 'teacher' ? TEACHER_DATA_CASES : '/admin/data-cases', query, hash }
  }
  if (path === '/capability-map/changelog') {
    return { path: '/capability-map', query: { ...query, history: '1' }, hash: `#${CAPABILITY_HISTORY}` }
  }
  return null
}

export function wantsCapabilityHistory(route) {
  return route?.query?.history === '1' || route?.hash === `#${CAPABILITY_HISTORY}`
}
