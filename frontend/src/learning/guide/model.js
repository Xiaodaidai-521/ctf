export const asList = data => Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : []
const id = value => /^\d+$/.test(String(value)) ? String(value) : null
export function pathTarget(path) {
  const pathId = id(path?.learning_path)
  if (!pathId) return '/learning-paths'
  const moduleId = id(path.current_module)
  return moduleId ? `/learning-paths/${pathId}/modules/${moduleId}` : `/learning-paths/${pathId}`
}
export function reviewTarget(review) {
  const challengeId = id(review?.challenge?.id)
  return challengeId ? `/challenge/${challengeId}` : '/capability-map'
}
export function reviewReason(review, now = Date.now()) {
  if (review.mastery_level != null && Number(review.mastery_level) < 0.5) return '这个知识点还需巩固，先回忆思路，再用练习检验。'
  if (review.recall_probability != null && Number(review.recall_probability) < 0.65) return '记忆需要巩固，短时回顾有助于减少遗忘。'
  if (review.next_review_at && new Date(review.next_review_at).getTime() <= now) return '已到建议复习时间，试着独立复述，再检查理解。'
  return '还没有完整的复习记录，先检查自己的理解。'
}
export function guidePlan(paths, reviews) {
  const path = paths.find(item => !item.completed_at)
  const items = []
  if (reviews[0]) items.push({ title: `复习：${reviews[0].concept_name || '已学知识'}`, reason: reviewReason(reviews[0]), to: reviewTarget(reviews[0]) })
  if (path) items.push({ title: path.current_module_title || path.path_title || '继续当前航线', reason: '沿已加入的航线继续，先完成当前章节，保持知识衔接。', to: pathTarget(path) })
  if (!items.length) items.push({ title: '从一次基础诊断开始', reason: '还没有足够的学习记录。先了解起点，再选择合适的练习。', to: '/capability-map' })
  return items
}
export function orderedPaths(data) {
  return asList(data).slice().sort((a, b) => (Date.parse(b.last_accessed) || 0) - (Date.parse(a.last_accessed) || 0))
}
export function latestConversation(data) {
  return asList(data).filter(item => item.message_count > 0).sort((a, b) => (Date.parse(b.updated_at) || 0) - (Date.parse(a.updated_at) || 0))[0] || null
}
