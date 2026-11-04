import { asList, finiteNumber, pageInfo } from '../contracts.js'
import { collectChallengeSubmissions, SUBMISSION_SCAN_PAGES } from './submissions.js'

// 题目工作台状态工厂：列表、弹窗、相关题目各自持有实例，避免共用 current/loading 互相覆盖。
export function createWorkspace({
  apiClient, challengeId, userId = null, now = () => Date.now(),
  maxSubmissionPages = SUBMISSION_SCAN_PAGES, isValid = () => true,
} = {}) {
  const state = {
    challengeId, userId, generation: 0,
    challenge: null, loading: true, error: '',
    flag: '', submitting: false, submitMessage: '', submitType: '',
    submissions: { items: [], count: null, hasNext: false, loaded: 0, scope: '' },
    submissionsLoading: false, submissionsError: '',
    environment: { phase: 'idle', info: null, error: '', starting: false, stopping: false },
    related: { articles: [], resources: [], sameCategory: [] },
  }
  let alive = true
  const isCurrent = version => alive && isValid() && version === state.generation

  async function load() {
    if (!alive || !isValid()) return
    const version = ++state.generation
    state.loading = true
    state.error = ''
    state.challenge = null
    state.related = { articles: [], resources: [], sameCategory: [] }
    try {
      const detail = await apiClient.detail(challengeId)
      if (!isCurrent(version)) return
      state.challenge = detail || null
      state.related = {
        articles: asList(detail?.recommended_articles),
        resources: asList(detail?.recommended_resources),
        sameCategory: [],
      }
    } catch {
      if (isCurrent(version)) state.error = '题目暂时未能读取，请重试。'
    } finally {
      if (isCurrent(version)) state.loading = false
    }
  }

  // 相关题目只用真实同分类列表，并排除当前题；理由明确写作“同分类练习”。
  async function loadRelated(listParams = {}) {
    const category = state.challenge?.category ?? listParams.category
    if (!category) return
    const version = state.generation
    try {
      const value = await apiClient.list({ category, page_size: 6 })
      if (!isCurrent(version)) return
      state.related.sameCategory = asList(value)
        .filter(item => String(item.id) !== String(challengeId))
        .filter(item => item.is_active !== false)
        .slice(0, 5)
    } catch { /* 相关题目失败不影响主工作台。 */ }
  }

  async function loadSubmissions() {
    if (!alive || !isValid()) return
    const version = state.generation
    state.submissionsLoading = true
    state.submissionsError = ''
    try {
      const info = await collectChallengeSubmissions({
        fetchPage: page => apiClient.mySubmissions({ page }),
        challengeId, maxPages: maxSubmissionPages, shouldStop: () => !isCurrent(version),
      })
      if (!isCurrent(version)) return
      state.submissions = { ...info, scope: info.hasNext ? '当前读取范围' : '' }
    } catch { if (isCurrent(version)) state.submissionsError = '本题提交记录暂时未能读取。' }
    finally { if (isCurrent(version)) state.submissionsLoading = false }
  }

  async function submit() {
    if (!alive || !isValid()) return { ok: false, cancelled: true }
    const version = state.generation
    const flag = String(state.flag || '').trim()
    if (state.submitting) return { ok: false, busy: true, message: '正在提交，请稍候。' }
    if (!flag) return { ok: false, message: '请输入 Flag' }
    state.submitting = true
    state.submitMessage = ''
    state.submitType = ''
    try {
      const value = await apiClient.submit(challengeId, flag)
      if (!isCurrent(version)) return { ok: false, cancelled: true }
      const ok = Boolean(value?.success)
      state.submitType = ok ? 'success' : 'error'
      state.submitMessage = value?.message || (ok ? '提交成功' : '提交未通过')
      if (ok) {
        state.flag = ''
        await load()
        await loadSubmissions()
      }
      return { ok, value }
    } catch (error) {
      if (!isCurrent(version)) return { ok: false, cancelled: true }
      const status = error?.response?.status
      state.submitType = 'error'
      state.submitMessage = status === 503
        ? '提交服务暂时不可用，请稍后重试。'
        : status === 400
          ? (error.response?.data?.message || '提交内容未通过校验，请检查后重试。')
          : '提交失败，请稍后重试。'
      return { ok: false, error }
    } finally { if (alive && isValid()) state.submitting = false }
  }

  function setEnvironmentPhase(phase, info = state.environment.info, error = '') {
    state.environment = { ...state.environment, phase, info, error, starting: false, stopping: false }
  }

  const countdownSeconds = () => {
    const expires = state.environment.info?.expires_at
    if (!expires) return null
    const diff = Date.parse(expires) - now()
    return Number.isFinite(diff) ? Math.max(0, Math.floor(diff / 1000)) : null
  }

  function destroy() {
    alive = false; ++state.generation; state.flag = ''; state.challenge = null
    state.related = { articles: [], resources: [], sameCategory: [] }; state.submissions.items = []
  }
  return { state, load, loadRelated, loadSubmissions, submit, setEnvironmentPhase, countdownSeconds, destroy }
}

export { pageInfo, finiteNumber }
