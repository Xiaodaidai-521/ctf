import { asList, finiteNumber } from '../contracts.js'

// 教学产出：只映射后端已返回的结构化字段，不把自由文本解析成写指令。
export function planArtifact(plan, loadedAt = null) {
  if (!plan || typeof plan !== 'object') return null
  const stages = asList(plan.stages || plan.steps || plan.phases).map((stage, index) => ({
    index: index + 1,
    title: stage.title || stage.name || `阶段 ${index + 1}`,
    duration: stage.duration || stage.estimated_time || '',
    actions: asList(stage.actions || stage.tasks).map(action => typeof action === 'string' ? action : action?.title || action?.text || '').filter(Boolean),
    reason: stage.reason || stage.basis || '',
  }))
  const items = stages.length ? stages : asList(plan.plan || plan.items).map((item, index) => ({
    index: index + 1,
    title: item.title || item.name || '',
    duration: item.duration || '',
    actions: [],
    reason: item.reason || '',
  })).filter(item => item.title)
  if (!items.length && !plan.summary && !plan.title) return null
  return {
    kind: 'plan',
    title: plan.title || '教学建议',
    summary: plan.summary || plan.description || '',
    items,
    source: plan.source || '教学智能体',
    updatedAt: plan.updated_at || plan.generated_at || loadedAt,
    persisted: plan.persisted !== false,
    note: plan.persisted === false ? '这份建议尚未保存为长期计划。' : '',
  }
}

export function pathArtifact(paths, loadedAt = null) {
  const list = asList(paths).filter(item => !item.completed_at)
  if (!list.length) return null
  const latest = list.slice().sort((a, b) => (Date.parse(b.last_accessed || 0) || 0) - (Date.parse(a.last_accessed || 0) || 0))[0]
  const target = latest.current_module ? `/learning-paths/${latest.learning_path}/modules/${latest.current_module}` : `/learning-paths/${latest.learning_path}`
  return {
    kind: 'path',
    title: latest.path_title || latest.title || '我的学习航线',
    currentTitle: latest.current_module_title || '',
    completed: finiteNumber(latest.completed_modules),
    total: finiteNumber(latest.total_modules),
    target,
    reason: '按已加入航线的顺序推进，先掌握当前章节，再进入后续内容。',
    updatedAt: latest.last_accessed || loadedAt,
    source: '我的学习航线',
  }
}

// 复习提醒只显示真实概率/日期/理由；缺失字段留空，不补造。
export function reviewArtifact(reviews, loadedAt = null) {
  const list = asList(reviews).slice(0, 5).map(item => ({
    id: item.id ?? item.reminder_id,
    concept: item.concept_name || item.concept || item.title || '待复习内容',
    probability: finiteNumber(item.forgetting_probability ?? item.probability ?? item.recall_probability),
    dueAt: item.next_review_at || item.review_date || item.due_at || null,
    reason: item.reason || item.review_reason || '',
    pathId: item.learning_path ?? item.path_id ?? null,
  })).filter(item => item.id !== undefined && item.id !== null)
  return { kind: 'review', items: list, updatedAt: loadedAt, source: '复习提醒' }
}

// 重新读取真实接口，保持来源说明；失败区单列，不把旧数据当成新结果。
export async function readArtifacts({ plan = null, paths = null, reviews = null, now = () => Date.now() } = {}) {
  const loadedAt = new Date(now()).toISOString()
  const call = fn => typeof fn === 'function' ? Promise.resolve().then(fn) : Promise.resolve(null)
  const [planResult, pathResult, reviewResult] = await Promise.allSettled([call(plan), call(paths), call(reviews)])
  return {
    plan: planResult.status === 'fulfilled' ? planArtifact(planResult.value, loadedAt) : null,
    path: pathResult.status === 'fulfilled' ? pathArtifact(pathResult.value, loadedAt) : null,
    reviews: reviewResult.status === 'fulfilled' ? reviewArtifact(reviewResult.value, loadedAt) : { kind: 'review', items: [], updatedAt: loadedAt, source: '复习提醒', failed: true },
    failures: [
      planResult.status === 'rejected' ? '教学建议' : null,
      pathResult.status === 'rejected' ? '学习航线' : null,
      reviewResult.status === 'rejected' ? '复习提醒' : null,
    ].filter(Boolean),
    loadedAt,
  }
}

// 对话刚完成后是否要刷新产出：比较真实标识，不比较渲染文案。
export function shouldRefresh(previous, next) {
  const key = value => JSON.stringify(value && {
    plan: value.plan?.title || null,
    path: value.path?.target || null,
    reviews: (value.reviews?.items || []).map(item => item.id),
  })
  return key(previous) !== key(next)
}
