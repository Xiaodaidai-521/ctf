import { countValue, numberValue } from '../governance/data.js'
export const jobStatus = value => ({ pending: '等待处理', running: '处理中', completed: '已完成', failed: '处理失败' }[value] || '状态待确认')
export const documentStatus = value => ({ draft: '草稿', active: '使用中', superseded: '已替换', archived: '已归档' }[value] || '状态待确认')
export const documentType = value => ({ law: '法律', regulation: '法规', standard: '标准', policy: '政策', case: '案例', template: '模板', platform_content: '平台资料', other: '其他' }[value] || '类型未提供')
export const materialStatus = value => ({ draft: '草稿', in_review: '待审阅', approved: '已审阅', published: '已发布', withdrawn: '已撤回' }[value] || '状态待确认')
export const materialClass = value => ({ lesson: '课程材料', hint: '分级提示', student_analysis: '学习分析', answer: '答案材料', rubric: '评分依据', teacher_note: '教学笔记', confidential: '受限材料' }[value] || '教学材料')
export function indexIssue(row) {
  if (row.status === 'failed') return '处理失败，请核对资料后重新处理。'
  if (!['pending', 'running', 'completed'].includes(row.status)) return '处理状态待确认。'
  const total = countValue(row.total_chunks), ready = countValue(row.embedded_chunks)
  if (row.status === 'completed' && total !== null && ready !== null && total !== ready) return '已完成记录与可检索段落数量不一致，请核对。'
  return ''
}
export const chunkLabel = row => {
  const total = countValue(row.total_chunks), ready = countValue(row.embedded_chunks)
  return total === null || ready === null ? '段落数量未提供' : `${ready} / ${total} 段可检索`
}
export const retrievalScore = value => {
  const number = numberValue(value)
  return number === null ? '相关度未提供' : `相关度 ${number.toFixed(3)}`
}
export function grantPayload(form, people, catalog) {
  const person = people.find(row => String(row.id) === String(form.user))
  if (!person || !catalog?.version || person.is_active === false) throw new Error('请先选择可用课程与人员。')
  if (form.can_review && !['teacher', 'admin'].includes(person.role)) throw new Error('审阅职责只能授予教师或管理员。')
  if (form.maintain_secrets && person.role !== 'admin') throw new Error('受限材料维护职责只能授予管理员。')
  return { catalog_version: catalog.version, user_id: person.id, active: form.active,
    can_review: form.can_review, maintain_secrets: form.maintain_secrets }
}
export function supervisionFacts(detail, people) {
  const person = id => people.find(row => String(row.id) === String(id))?.username || '人员信息暂未提供'
  return [
    ['作者', detail.author_id == null ? '未提供' : person(detail.author_id)],
    ['审阅人', detail.reviewer_id == null ? '未安排或未提供' : person(detail.reviewer_id)],
    ['发布范围', ({ learner: '按课程向学生开放', internal: '内部使用' })[detail.published_scope] || '未发布或范围未提供'],
    ['独立审阅', detail.author_id == null || detail.reviewer_id == null ? '尚不能确认' : detail.author_id === detail.reviewer_id ? '作者与审阅人为同一人，请核对' : '作者与审阅人不同；其他审阅资格仍须核对'],
  ]
}
