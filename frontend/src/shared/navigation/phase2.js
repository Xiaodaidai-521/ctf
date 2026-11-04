// 二期统一落点：只做路由规划与旧深链解析，不在此处读取任何用户数据。
export const GROWTH_SECTIONS = Object.freeze(['overview', 'activity', 'results', 'capability'])
export const GROWTH_SECTION_LABELS = Object.freeze({
  overview: '总览', activity: '学习分析', results: '结果与复盘', capability: '能力探索',
})

export function parseGrowthSection(value) {
  return GROWTH_SECTIONS.includes(value) ? value : 'overview'
}

export function growthDestination(section = 'overview', query = {}) {
  const target = parseGrowthSection(section)
  const params = new URLSearchParams()
  if (target !== 'overview') params.set('section', target)
  for (const key of ['window', 'review']) if (query[key] !== undefined && query[key] !== null) params.set(key, query[key])
  const text = params.toString()
  return text ? `/dashboard?${text}` : '/dashboard'
}

export const examHistoryDestination = () => '/exam-center/history'
export const examResultDestination = id => `/exam-center/result/${id}`

// 旧深链全部落到二期新位置；未知路径返回 null，由路由自身处理。
export function compatDestination(path, query = {}) {
  if (!path) return null
  if (path === '/analytics') return growthDestination('activity', query)
  if (path === '/my-results') return growthDestination('results', query)
  if (path === '/exam-history') return examHistoryDestination()
  const result = String(path).match(/^\/exam-result\/([^/]+)\/?$/)
  if (result) return examResultDestination(result[1])
  return null
}

// /dashboard 角色分发：学生成长总览，教师保留教学数据，管理员去治理驾驶舱。
export function dashboardOwner(role) {
  if (role === 'teacher') return 'teacher'
  if (role === 'admin') return 'admin'
  return 'student'
}

export function dashboardRouteName(role) {
  const owner = dashboardOwner(role)
  return owner === 'teacher' ? 'StudentDashboard' : owner === 'admin' ? 'AdminDashboardHome' : 'GrowthOverview'
}

// KeepAlive 只保留明确列出的壳层状态，避免整站缓存。
export const KEEP_ALIVE_ROUTES = Object.freeze([
  'Challenges', 'StudentDashboard', 'ExamHistory', 'LearningPaths', 'MultiAgent',
])

export function shouldKeepAlive(routeName) {
  return KEEP_ALIVE_ROUTES.includes(routeName)
}
