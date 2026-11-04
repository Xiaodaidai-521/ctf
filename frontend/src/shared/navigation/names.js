export const names = Object.freeze({
  guide: '智航', practice: '靶场', exams: '试炼场', resources: '智库',
  growth: '成长图谱', capability: '能力图谱', paths: '学习航线',
  teacher: '教学驾驶舱', insights: '学情洞察', assessment: '动态评测',
  knowledge: '知识基座', materials: '材料工坊', resourceReview: '资源审核',
  contentArea: '内容与资料', feedbackProcessing: '反馈处理', eventReconciliation: '事件核对', teachingActions: '教学安排',
  admin: '治理驾驶舱', foundation: '基座治理', globalInsights: '全局洞察', assessmentSupervision: '评测监督',
  indexTools: '索引工具', indexHealth: '索引健康', authorizationSupervision: '授权监督', materialMaintenance: '受限材料维护',
})

const legacyNames = [
  ['知识资料库', names.knowledge], ['材料创建与审阅', names.materials], ['教学材料审阅', names.materials],
  ['学习效果分析', names.insights], ['学习成效', names.insights], ['动态评分', names.assessment], ['学习评分', names.assessment],
  ['学习路径', names.paths], ['能力地图', names.capability], ['题库练习', names.practice], ['题目矩阵', names.practice],
  ['测试中心', names.exams], ['资源中心', names.resources], ['教学工作台', names.teacher], ['教师中心', names.teacher],
]
export const renameCopy = text => legacyNames.reduce((value, [old, name]) => value.replaceAll(old, name), String(text || ''))
export function landingFor(role) {
  return role === 'admin' ? '/admin/dashboard' : role === 'teacher' ? '/teacher' : '/guide'
}
