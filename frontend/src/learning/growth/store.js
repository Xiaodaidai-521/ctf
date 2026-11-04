import { asList, finiteNumber } from '../contracts.js'
import { completionFrom, growthApi, growthWindow, weeklyReport } from './api.js'

// 成长面状态工厂：分区加载、分区报错、迟到响应不覆盖新账号；时间窗独立读取。
export function createGrowthState({ apiClient = growthApi, now = () => Date.now(), userId = null } = {}) {
  let account = userId === null ? null : String(userId)
  let accountGen = 0
  let coreGen = 0
  let effectGen = 0
  const state = {
    window: 7,
    profile: null, persona: null, report: null, insights: null, weekly: null,
    plan: null, effect: null, recommendations: [], reviews: [], paths: [],
    stats: null, errors: {}, loading: false, effectLoading: false,
    loadedAt: null,
  }

  function reset() {
    state.profile = state.persona = state.report = state.insights = state.weekly = null
    state.plan = state.effect = state.stats = null
    state.recommendations = state.reviews = state.paths = []
    state.errors = {}
    state.loading = false
    state.effectLoading = false
    state.loadedAt = null
  }

  function setAccount(nextUserId) {
    const next = nextUserId === null || nextUserId === undefined ? null : String(nextUserId)
    if (next === account) return false
    account = next
    accountGen++
    coreGen++
    effectGen++
    reset()
    return true
  }

  // 核心分区并行读取；任何一区失败只影响该区，其余照常显示。
  async function loadCore() {
    const accountAtStart = accountGen
    const version = ++coreGen
    state.loading = true
    state.errors = {}
    const jobs = [
      ['profile', () => apiClient.profile(), value => { state.profile = value || null }],
      ['persona', () => apiClient.persona(), value => { state.persona = value || null }],
      ['report', () => apiClient.progressReport(), value => { state.report = value || null }],
      ['insights', () => apiClient.insights(), value => { state.insights = value || null }],
      ['weekly', () => apiClient.weeklySummary(), value => { state.weekly = weeklyReport(value, new Date(now())) }],
      ['plan', () => apiClient.teachingPlan(), value => { state.plan = value || null }],
      ['recommendations', () => apiClient.recommendations(), value => { state.recommendations = asList(value) }],
      ['reviews', () => apiClient.reviewReminders(), value => { state.reviews = asList(value) }],
      ['paths', () => apiClient.myPaths(), value => { state.paths = asList(value) }],
      ['stats', () => apiClient.submissionStats(), value => { state.stats = value || null }],
    ]
    const current = () => version === coreGen && accountAtStart === accountGen
    await Promise.all(jobs.map(async ([key, call, apply]) => {
      try {
        const value = await call()
        if (!current()) return
        apply(value)
      } catch {
        if (current()) state.errors = { ...state.errors, [key]: '暂时未能读取，请稍后重试。' }
      }
    }))
    if (current()) {
      state.loading = false
      state.loadedAt = now()
    }
  }

  async function loadEffect(days = state.window) {
    const window = growthWindow(days)
    state.window = window
    const accountAtStart = accountGen
    const version = ++effectGen
    state.effect = null
    state.effectLoading = true
    state.errors = { ...state.errors, effect: '' }
    try {
      const value = await apiClient.learningEffect(window)
      if (version !== effectGen || accountAtStart !== accountGen) return
      state.effect = value || null
    } catch {
      if (version === effectGen && accountAtStart === accountGen) {
        state.errors = { ...state.errors, effect: '暂时未能读取，请稍后重试。' }
      }
    } finally {
      if (version === effectGen && accountAtStart === accountGen) state.effectLoading = false
    }
  }

  async function completeReview(id) {
    const value = await apiClient.completeReview({ reminder_id: id })
    state.reviews = state.reviews.filter(item => String(item.id ?? item.reminder_id) !== String(id))
    return value
  }

  function completion() {
    return completionFrom(state.report, state.stats)
  }

  function latestReport() {
    const reports = asList(state.profile?.reports || state.report?.reports)
    return reports.slice().sort((a, b) => (Date.parse(b.created_at || 0) || 0) - (Date.parse(a.created_at || 0) || 0))[0] || null
  }

  // 复习提醒必须带真实概率/日期/理由；缺失就不显示该词条。
  function reviewViews() {
    return state.reviews.map(item => ({
      id: item.id ?? item.reminder_id,
      concept: item.concept_name || item.concept || item.title || '待复习内容',
      probability: finiteNumber(item.forgetting_probability ?? item.probability),
      dueAt: item.review_date || item.due_at || item.scheduled_at || null,
      reason: item.reason || item.review_reason || '',
      pathId: item.learning_path ?? item.path_id ?? null,
    })).filter(item => item.id !== undefined && item.id !== null)
  }

  return { state, setAccount, loadCore, loadEffect, completeReview, completion, latestReport, reviewViews }
}

export { asList }
