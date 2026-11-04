const count = value => Number.isSafeInteger(value) && value >= 0 ? value : null
const activeFeedback = ['pending_fact_review', 'pending_evidence', 'confirmed', 'reopened']
const definitions = [
  ['resources', '成品待审核', '/teacher/resources?status=pending', '核对内容、许可与适用范围。'],
  ['materials', '材料待审阅', '/teacher/materials', '检查原文与段落，再由独立教师审阅。'],
  ['manual', '开放题待评阅', '/teacher/skill-review?tab=manual', '结合学生提交与量表进行评阅。'],
  ['sampling', '抽查待验收', '/teacher/skill-review?tab=sampling', '按已有抽查范围逐项核对。'],
  ['disputes', '评分待复核', '/teacher/skill-review?tab=disputes', '核对评分依据与学生申诉。'],
  ['feedback', '反馈待处理', '/teacher/feedback#queue', '先核实事实，再处理或要求补充依据。'],
  ['paths', '航线待完善', '/teacher/learning-paths?status=draft', '完善课程章节、练习与检验后再发布。'],
]
export function cockpitTiles(sources) {
  const data = key => sources[key]?.data
  const feedbackCounts = data('feedback')?.counts
  const feedbackValues = activeFeedback.map(key => count(feedbackCounts?.[key]))
  const materialRows = data('materials')?.results
  const pathRows = Array.isArray(data('paths')) ? data('paths') : data('paths')?.results
  const values = {
    resources: count(data('resources')?.counts?.pending ?? data('resources')?.count),
    materials: Array.isArray(materialRows) ? materialRows.filter(row => row.review_status === 'in_review').length : null,
    manual: count(data('reviews')?.counts?.manual_pending),
    sampling: count(data('reviews')?.counts?.sampling_pending),
    disputes: count(data('reviews')?.counts?.disputes_pending),
    feedback: feedbackValues.every(value => value !== null) ? feedbackValues.reduce((sum, value) => sum + value, 0) : null,
    paths: Array.isArray(pathRows) ? pathRows.filter(row => row.is_published === false).length : null,
  }
  return definitions.map(([key, title, href, description]) => {
    const source = ['manual', 'sampling', 'disputes'].includes(key) ? sources.reviews : sources[key]
    return { key, title, href, description, count: values[key], error: source?.error || '', loading: source?.loading ?? true,
      scope: key === 'paths' ? '本次已读取航线中的草稿' : key === 'materials' ? '当前有权管理的材料' : '' }
  })
}
export function cockpitPriorities(sources) {
  return (sources.feedback?.data?.items || []).filter(item => activeFeedback.includes(item.status)).slice(0, 5).map(item => ({
    title: item.task_title || '教学反馈', student: item.student_name || '学生姓名暂不可用',
    href: `/teacher/feedback/${encodeURIComponent(item.feedback_id)}`, reason: item.conflict_flag ? '有待核对的冲突' : '按影响与等待时间优先处理',
  }))
}
export function cockpitError(error) {
  return error?.response?.status === 403 ? '当前账号无法读取，请联系管理员核对授权。' : '暂时未能读取，请重试；这不代表没有待办。'
}
