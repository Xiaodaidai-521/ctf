import { landingFor, names, renameCopy } from './names.js'
import { loginDestination } from './returnTarget.js'

export function canOpen(meta = {}, role = 'guest') {
  if ((meta.requiresAuth || meta.requiresTeacher || meta.requiresAdmin || meta.requiresTeacherOnly) && role === 'guest') return false
  if (meta.requiresAdmin) return role === 'admin'
  if (meta.requiresTeacherOnly) return role === 'teacher'
  if (meta.requiresTeacher) return ['teacher', 'admin'].includes(role)
  return true
}
export function pageTitle(route, role) {
  const titles = {
    Guide: names.guide, Home: '网络安全学习', Challenges: names.practice,
    Resources: names.resources, ExamCenter: names.exams, ExamHistory: `${names.exams} · 测评记录`,
    ExamResult: `${names.exams} · 测评结果`, MultiAgent: `${names.guide} · 导学对话`, MultiAgentChallenge: `${names.guide} · 题目辅导`,
    StudentDashboard: role === 'teacher' ? `${names.insights} · 教学数据` : names.growth,
    GrowthOverview: names.growth, GrowthActivity: `${names.growth} · 学习分析`, GrowthResults: `${names.growth} · 结果与复盘`,
    LearningAnalytics: `${names.growth} · 学习分析`, MyResults: `${names.growth} · 结果与复盘`,
    CapabilityExplorer: names.capability,
    TeacherHome: names.teacher, AdminDashboardHome: names.admin, AdminStudentLearningHome: names.globalInsights,
    TeacherKnowledgeLibrary: names.knowledge, AdminLegalKbHome: names.foundation,
    AdminLegalKbTools: names.indexTools, AdminLegalKbHealth: names.indexHealth, AdminLegalKbAuthorization: names.authorizationSupervision, AdminLegalKbMaterials: names.materialMaintenance,
    DataLab: '智库 · 数据安全专题', DataLabTeacher: '数据安全案例', AdminDataCases: '数据安全案例', TeacherDataCases: '数据安全案例',
    TeachingKnowledge: names.materials, TeacherMaterials: names.materials, TeacherResources: names.resourceReview,
    TeacherLearningScores: names.assessment, TeacherLearningEffect: names.insights,
    TeacherStudentGrowth: `${names.growth} · 教师视角`, TeacherTeachingActions: names.teachingActions,
    TeacherFeedbackQueue: names.feedbackProcessing, TeacherFeedbackReconciliation: names.eventReconciliation,
    AdminArticlesHome: `${names.resourceReview} · 文章`, AdminLearningScoresHome: names.assessmentSupervision,
    Profile: '个人资料',
  }
  return titles[route.name] || renameCopy(route.meta?.title || '')
}
export function guardDestination(to, user) {
  const role = user.isAuthenticated ? user.userInfo?.role || 'guest' : 'guest'
  if (!canOpen(to.meta, role)) return role === 'guest' ? loginDestination(to.fullPath || to.path) : '/access-denied'
  if (to.name === 'Home' && role !== 'guest') return landingFor(role)
  if (to.name === 'Guide' && ['teacher', 'admin'].includes(role)) return landingFor(role)
  if (to.name === 'KnowledgeLibrary') return role === 'teacher' ? '/teacher/knowledge' : '/admin/legal/kb'
  if (to.path === '/dashboard' && role === 'admin') return landingFor(role)
  return undefined
}
