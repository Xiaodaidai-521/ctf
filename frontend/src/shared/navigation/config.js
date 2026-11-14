import { names, landingFor } from './names.js'
import { searchGovernance } from './governance.js'

const entry = (key, label, path, icon, roles, matches = []) => ({ key, label, path, icon, roles, matches })
const student = ['student', 'guest']
const teacher = ['teacher']
const admin = ['admin']
export const navigation = Object.freeze({
  student: [
    { label: '学习', items: [
      entry('guide', names.guide, '/guide', 'icon-compass', student, ['/multi-agent', '/learning-paths']),
      entry('practice', names.practice, '/challenges', 'icon-code', student, ['/challenge/']),
      entry('resources', names.resources, '/resources', 'icon-book', student),
      entry('growth', names.growth, '/dashboard', 'icon-bar-chart', student, ['/analytics', '/my-results', '/capability-map']),
    ] },
  ],
  teacher: [
    { label: '教学', items: [entry('teacher', names.teacher, '/teacher', 'icon-apps', teacher)] },
    { label: '备课', items: [
      entry('challenges', '题目管理', '/teacher/challenges', 'icon-code', teacher),
      entry('paths', names.paths, '/teacher/learning-paths', 'icon-branch', teacher, ['/learning-paths']),
      entry('data-cases', '数据安全案例', '/teacher/data-cases', 'icon-code', teacher, ['/data-lab/teacher']),
      entry('resources', names.resourceReview, '/teacher/resources', 'icon-check-square', teacher),
      entry('knowledge', names.knowledge, '/teacher/knowledge', 'icon-book', teacher),
      entry('materials', names.materials, '/teacher/materials', 'icon-file', teacher, ['/teaching-knowledge']),
    ] },
    { label: '布置与验收', items: [
      entry('arrangements', names.teachingActions, '/teacher/teaching-actions', 'icon-edit', teacher),
      entry('review', '验收与抽查', '/teacher/skill-review', 'icon-check-circle', teacher),
      entry('capability', `${names.capability}审核`, '/teacher/capability-map', 'icon-mind-mapping', teacher),
    ] },
    { label: '跟踪与评测', items: [
      entry('insights', names.insights, '/teacher/learning-effect', 'icon-bar-chart', teacher, ['/teacher/students', '/dashboard']),
      entry('assessment', names.assessment, '/teacher/learning-scores', 'icon-edit', teacher),
    ] },
    { label: '反馈', items: [
      entry('feedback', names.feedbackProcessing, '/teacher/feedback', 'icon-message', teacher),
      entry('reconciliation', names.eventReconciliation, '/teacher/feedback/reconciliation', 'icon-history', teacher),
    ] },
  ],
  admin: [
    { label: '治理', items: [entry('admin', names.admin, '/admin/dashboard', 'icon-apps', admin)] },
    { label: '用户与权限', items: [entry('users', '用户管理', '/admin/users', 'icon-user-group', admin)] },
    { label: '内容审核', items: [
      entry('resources', names.resourceReview, '/admin/resources', 'icon-check-square', admin),
      entry('articles', `${names.resourceReview} · 文章`, '/admin/articles', 'icon-file', admin),
    ] },
    { label: '题目与记录', items: [
      entry('challenges', '题目管理', '/admin/challenges', 'icon-code', admin),
      entry('categories', '分类管理', '/admin/categories', 'icon-tag', admin),
      entry('submissions', '提交记录', '/admin/submissions', 'icon-history', admin),
      entry('data-cases', '数据安全案例', '/admin/data-cases', 'icon-code', admin),
    ] },
    { label: '基座与平台', items: [
      entry('foundation', names.foundation, '/admin/legal/kb', 'icon-book', admin),
      entry('global', names.globalInsights, '/admin/student-learning', 'icon-bar-chart', admin),
      entry('assessment', names.assessmentSupervision, '/admin/learning-scores', 'icon-eye', admin),
      entry('legal', '合规中心', '/admin/legal/dashboard', 'icon-safe', admin),
      entry('data-security', '数据保护', '/admin/data-security', 'icon-safe', admin),
      entry('announcements', '公告管理', '/admin/announcements', 'icon-notification', admin),
    ] },
  ],
})
export function groupsFor(role = 'guest') {
  const groups = navigation[role] || navigation.student
  return groups.map(group => ({ ...group, items: group.items.filter(item => item.roles.includes(role)) })).filter(group => group.items.length)
}
export function entriesFor(role) { return groupsFor(role).flatMap(group => group.items) }
export function activeEntry(role, path) {
  return entriesFor(role).filter(item => path === item.path || (item.path !== '/teacher' && path.startsWith(`${item.path}/`)) || item.matches.some(prefix => path.startsWith(prefix)))
    .sort((a, b) => b.path.length - a.path.length)[0]?.key
}
export const personalLinks = [
  entry('profile', '个人资料', '/profile', 'icon-user', ['student', 'teacher', 'admin']),
  entry('community', '社区', '/community', 'icon-message', ['student', 'teacher', 'admin']),
  entry('feedback', '反馈', '/feedback', 'icon-edit', ['student']),
]
export const learningLinks = [
  entry('paths', names.paths, '/learning-paths', 'icon-branch', ['student']),
  entry('capability', names.capability, '/capability-map', 'icon-mind-mapping', ['student']),
  entry('analytics', `${names.growth} · 学习分析`, '/analytics', 'icon-bar-chart', ['student']),
  entry('review', `${names.growth} · 结果与复盘`, '/my-results', 'icon-history', ['student']),
  entry('data-topic', '智库 · 数据安全专题', '/resources/topics/data-security', 'icon-book', ['student']),
]
export function searchEntries(role, query = '') {
  if (role === 'admin') return searchGovernance(query)
  const links = [...entriesFor(role), ...personalLinks.filter(item => item.roles.includes(role)), ...(role === 'student' ? learningLinks : [])]
  if (role === 'student') links.push(entry('exams', names.exams, '/exam-center', 'icon-trophy', ['student']))
  const normalized = query.trim().toLocaleLowerCase()
  return links.filter(item => !normalized || item.label.toLocaleLowerCase().includes(normalized))
}
export { landingFor }
