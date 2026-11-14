import { names } from './names.js'

const page = (key, label, path, icon, group, aliases = []) => ({ key, label, path, icon, group, aliases, roles: ['admin'] })
export const governancePages = Object.freeze([
  page('admin', names.admin, '/admin/dashboard', 'icon-apps', '治理', ['待办', '仪表盘']),
  page('users', '用户管理', '/admin/users', 'icon-user-group', '用户与权限', ['账户', '角色', '授权']),
  page('resources', names.resourceReview, '/admin/resources', 'icon-check-square', '内容审核', ['资源', '讲义']),
  page('articles', `${names.resourceReview} · 文章`, '/admin/articles', 'icon-file', '内容审核', ['文章审核']),
  page('challenges', '题目管理', '/admin/challenges', 'icon-code', '题目与记录', ['靶场', '练习']),
  page('categories', '分类管理', '/admin/categories', 'icon-tag', '题目与记录', ['题目分类']),
  page('submissions', '提交记录', '/admin/submissions', 'icon-history', '题目与记录', ['异常提交']),
  page('data-cases', '数据安全案例', '/admin/data-cases', 'icon-code', '题目与记录', ['案例监督', '数据实验室']),
  page('foundation', names.foundation, '/admin/legal/kb', 'icon-book', '基座治理', ['资料库', '知识基座']),
  page('index-tools', names.indexTools, '/admin/legal/kb/tools', 'icon-search', '基座治理', ['检索', '向量化', '索引重建']),
  page('index-health', names.indexHealth, '/admin/legal/kb/health', 'icon-check-circle', '基座治理', ['异常', '健康检查']),
  page('foundation-authorization', names.authorizationSupervision, '/admin/legal/kb/authorization', 'icon-safe', '基座治理', ['材料授权', '资料权限']),
  page('material-maintenance', names.materialMaintenance, '/admin/legal/kb/materials', 'icon-safe', '基座治理', ['受限资料', '原材料工坊']),
  page('global', names.globalInsights, '/admin/student-learning', 'icon-bar-chart', '平台', ['平台统计', '用户学习报表']),
  page('assessment', names.assessmentSupervision, '/admin/learning-scores', 'icon-eye', '平台', ['评分记录', '动态评测']),
  page('announcements', '公告管理', '/admin/announcements', 'icon-notification', '平台', ['通知']),
  page('compliance', '合规中心', '/admin/legal/dashboard', 'icon-safe', '合规', ['合规治理']),
  page('data-security', '数据保护', '/admin/data-security', 'icon-safe', '合规', ['数据安全', '受控导出', '保护策略']),
  page('legal-workspace', '数智合规官', '/admin/legal/agent', 'icon-safe', '合规', ['合规工作台']),
  page('audit', '合规审计', '/admin/legal/audit', 'icon-history', '合规', ['审计日志', '事件']),
  page('violations', '违规记录', '/admin/legal/violations', 'icon-exclamation-circle', '合规', ['违规处理']),
  page('reports', '合规报告', '/admin/legal/reports', 'icon-file', '合规', ['报告']),
  page('protocols', '协议签署', '/admin/legal/protocols', 'icon-file', '合规', ['协议', '签署']),
  page('exercises', '合规演练', '/admin/legal/exercises', 'icon-code', '合规', ['演练']),
])

export function searchGovernance(query = '') {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return governancePages.filter(item => terms.every(term => [item.label, item.group, ...item.aliases].join(' ').toLocaleLowerCase().includes(term)))
}

export function governancePage(path = '') {
  const normalized = path.split(/[?#]/)[0].replace(/\/$/, '')
  return governancePages.find(item => item.path === normalized)
}
