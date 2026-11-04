import { computed, ref } from 'vue'
import { createAccountGuard } from '../../shared/state/accountScope.js'
import { createWorkspace } from './workspaceStore.js'
import { normalizeEnvironment, countdown, phaseFor } from './environment.js'
import { readDraft, writeDraft, clearDraft } from './drafts.js'
import { submitFeedback } from './workspaceView.js'
import { collectChallengeSubmissions, SUBMISSION_SCAN_PAGES } from './submissions.js'

// 一个题目工作台会话：直达页与弹层共用同一套状态动作，避免两处各自提交/轮询。
// apiClient 由宿主注入（组件传 practiceApi），便于契约测试不依赖 @/别名。
export function createWorkspaceSession({
  apiClient, challengeId, userId = null, now = () => Date.now(),
  schedule = (fn, ms) => setTimeout(fn, ms), cancel = timer => clearTimeout(timer),
  pollInterval = 3000, maxPolls = 20, maxSubmissionPages = SUBMISSION_SCAN_PAGES,
} = {}) {
  const account = createAccountGuard()
  const current = () => !destroyed && account.current()
  const workspace = createWorkspace({ apiClient, challengeId, userId, now, isValid: current })

  const challenge = ref(null)
  const loading = ref(true)
  const error = ref('')
  const related = ref({ articles: [], resources: [], sameCategory: [] })

  const flag = ref(readDraft(userId, challengeId))
  const submitting = ref(false)
  const message = ref('')
  const messageType = ref('')

  const submissions = ref({ items: [], count: null, hasNext: false, loaded: 0, page: 0, pagesRead: 0 })
  const submissionsLoading = ref(false)
  const submissionsError = ref('')

  const environment = ref({ phase: 'idle', info: null, error: '', starting: false, stopping: false })
  const remainingSeconds = ref(null)
  const countdownText = ref('未提供')
  const environmentStatus = computed(() => normalizeEnvironment(environment.value.info))

  let pollTimer = null
  let countdownTimer = null
  let polls = 0
  let destroyed = false
  let suspended = false
  let environmentEpoch = 0, environmentRead = 0

  function sync() {
    challenge.value = workspace.state.challenge
    loading.value = workspace.state.loading
    error.value = workspace.state.error
    related.value = { ...workspace.state.related }
  }

  async function load() {
    await workspace.load()
    if (!current()) return
    sync()
    if (workspace.state.challenge) await workspace.loadRelated()
    if (!current()) return
    related.value = { ...workspace.state.related }
  }

  // “我的提交”没有按题目过滤的参数：从当前页起逐页找本题记录，
  // 找到后再由“加载更早记录”继续往后翻；读不完时保留范围说明，不冒充全量。
  async function loadSubmissions({ more = false } = {}) {
    if (!current() || submissionsLoading.value) return
    if (more && !submissions.value.hasNext) return
    const startPage = more ? submissions.value.page + 1 : 1
    submissionsLoading.value = true
    submissionsError.value = ''
    try {
      const info = await collectChallengeSubmissions({
        fetchPage: page => apiClient.mySubmissions({ page }),
        challengeId, startPage,
        maxPages: maxSubmissionPages,
        shouldStop: () => !current(),
      })
      if (!current()) return
      const items = more ? mergeSubmissions(submissions.value.items, info.items) : info.items
      submissions.value = {
        items, count: info.count, hasNext: info.hasNext,
        page: info.pagesRead, pagesRead: info.pagesRead, loaded: items.length,
      }
    } catch {
      if (current()) submissionsError.value = '本题提交记录暂时未能读取。'
    } finally {
      if (current()) submissionsLoading.value = false
    }
  }

  function setFlag(value) {
    if (!current()) return
    flag.value = value
    writeDraft(userId, challengeId, value)
  }

  async function submit() {
    if (!current()) return { ok: false, cancelled: true }
    if (submitting.value) {
      message.value = '正在提交，请稍候。'
      messageType.value = 'info'
      return { ok: false, busy: true }
    }
    const text = String(flag.value || '').trim()
    if (!text) {
      message.value = '请输入 Flag'
      messageType.value = 'error'
      return { ok: false, message: message.value }
    }
    submitting.value = true
    message.value = ''
    messageType.value = ''
    workspace.state.flag = text
    try {
      const result = await workspace.submit()
      if (!current() || result.cancelled) return { ok: false, cancelled: true }
      const feedback = submitFeedback(result)
      // 服务端/网络错误的具体提示记录在 workspace.state.submitMessage，优先于兜底文案。
      message.value = result.busy ? '正在提交，请稍候。' : (result.value?.message || workspace.state.submitMessage || feedback.message)
      messageType.value = result.busy ? 'info' : (result.ok ? 'success' : 'error')
      if (result.ok) {
        clearDraft(userId, challengeId)
        flag.value = ''
        sync()
        await loadSubmissions()
      } else if (result.value?.message) {
        // 未通过时保留输入，便于核对后重试。
        writeDraft(userId, challengeId, text)
      }
      return result
    } finally {
      if (current()) submitting.value = false
    }
  }

  function stopPolling() {
    if (pollTimer !== null) { cancel(pollTimer); pollTimer = null }
  }
  function stopCountdown() {
    if (countdownTimer !== null) { cancel(countdownTimer); countdownTimer = null }
  }

  function tickCountdown() {
    stopCountdown()
    if (!current() || suspended) return
    const value = countdown(environment.value.info?.expiresAt, now())
    remainingSeconds.value = value.seconds
    countdownText.value = value.text
    if (value.seconds === null || value.seconds <= 0) return
    countdownTimer = schedule(() => { if (current() && !suspended) tickCountdown() }, 1000)
  }

  // 只读服务端真实状态；未拿到访问地址前不宣称可用，超时也不假装就绪。
  async function refreshEnvironment() {
    if (!current() || !userId) return environment.value
    const epoch = environmentEpoch, version = ++environmentRead
    const latest = () => current() && epoch === environmentEpoch && version === environmentRead
    try {
      const value = await apiClient.container(challengeId)
      if (!latest()) return environment.value
      const info = normalizeEnvironment(value)
      environment.value = { ...environment.value, info, phase: phaseFor(value), error: '' }
      // 到期时也解释一次时间，让面板显示“已到期”而不是停留“未提供”。
      if (['ready', 'expired'].includes(environment.value.phase)) tickCountdown()
      return environment.value
    } catch (err) {
      if (latest()) {
        environment.value = {
          ...environment.value,
          phase: 'error',
          error: err?.response?.status === 503
            ? '练习环境状态暂时不可读取，请稍后重试。'
            : '练习环境状态暂时不可读取。',
        }
      }
      return environment.value
    }
  }

  function startPolling() {
    stopPolling()
    if (!current() || suspended) return
    polls = 0
    const run = async () => {
      if (!current() || suspended) return
      polls += 1
      await refreshEnvironment()
      if (!current() || suspended) return
      if (environment.value.phase === 'ready' || environment.value.phase === 'error') return
      if (polls >= maxPolls) {
        environment.value = { ...environment.value, phase: 'timeout', error: '环境状态读取超时，可重试读取或联系教师。' }
        return
      }
      pollTimer = schedule(run, pollInterval)
    }
    pollTimer = schedule(run, pollInterval)
  }

  async function startEnvironment() {
    if (!current()) return { ok: false, cancelled: true }
    if (!userId) { environment.value = { ...environment.value, error: '请先登录后再启动环境。' }; return { ok: false } }
    if (environment.value.starting) return { ok: false, busy: true }
    const epoch = ++environmentEpoch
    environment.value = { ...environment.value, starting: true, error: '' }
    try {
      const value = await apiClient.startEnvironment(challengeId)
      if (!current() || epoch !== environmentEpoch) return { ok: false, cancelled: true }
      if (value?.success === false) {
        environment.value = { ...environment.value, starting: false, phase: 'error', error: value.message || '练习环境启动失败，请稍后重试。' }
        return { ok: false, message: environment.value.error }
      }
      const info = normalizeEnvironment(value?.container)
      environment.value = { ...environment.value, info, phase: phaseFor(value?.container), starting: false, error: '' }
      // 启动响应只是第一步；状态仍需轮询确认，不显示预计百分比。
      if (['ready', 'expired'].includes(environment.value.phase)) tickCountdown()
      else startPolling()
      return { ok: true, message: value?.message || '练习环境正在启动。' }
    } catch (err) {
      if (!current() || epoch !== environmentEpoch) return { ok: false, cancelled: true }
      const status = err?.response?.status
      environment.value = {
        ...environment.value, starting: false, phase: 'error',
        error: status === 503
          ? '练习环境暂时无法启动，请稍后重试或联系教师。'
          : '练习环境启动失败，请稍后重试。',
      }
      return { ok: false, message: environment.value.error }
    }
  }

  async function stopEnvironment() {
    if (!current()) return { ok: false, cancelled: true }
    if (environment.value.stopping) return { ok: false, busy: true }
    const epoch = ++environmentEpoch
    environment.value = { ...environment.value, stopping: true, error: '' }
    try {
      const value = await apiClient.stopEnvironment(challengeId)
      if (!current() || epoch !== environmentEpoch) return { ok: false, cancelled: true }
      if (value?.success === false) {
        environment.value = { ...environment.value, stopping: false, error: value.message || '停止环境失败，请稍后重试。' }
        return { ok: false, message: environment.value.error }
      }
      stopPolling()
      stopCountdown()
      remainingSeconds.value = null
      countdownText.value = '未提供'
      environment.value = { phase: 'idle', info: null, error: '', starting: false, stopping: false }
      return { ok: true, message: value?.message || '练习环境已停止。' }
    } catch {
      if (!current() || epoch !== environmentEpoch) return { ok: false, cancelled: true }
      environment.value = { ...environment.value, stopping: false, error: '停止环境失败，请稍后重试。' }
      return { ok: false, message: environment.value.error }
    }
  }

  async function copyAccess() {
    if (!current()) return { ok: false, cancelled: true }
    const url = environment.value.info?.accessUrl
    if (!url) return { ok: false }
    try {
      await apiClient.clipboard.writeText(url)
      if (!current()) return { ok: false, cancelled: true }
      return { ok: true, message: '访问地址已复制。' }
    } catch {
      if (!current()) return { ok: false, cancelled: true }
      return { ok: false, message: '复制失败，请手动复制访问地址。' }
    }
  }

  function suspend() {
    suspended = true
    stopPolling(); stopCountdown()
  }
  async function resume() {
    if (!current()) return
    suspended = false
    await refreshEnvironment()
    if (current() && ['starting', 'pending', 'waiting'].includes(environment.value.phase)) startPolling()
  }
  function destroy() {
    if (destroyed) return
    destroyed = true
    account.dispose(); workspace.destroy()
    stopPolling(); stopCountdown()
    flag.value = ''; challenge.value = null; related.value = { articles: [], resources: [], sameCategory: [] }
    submissions.value.items = []; environment.value = { phase: 'idle', info: null, error: '', starting: false, stopping: false }
  }

  return {
    workspace, challenge, loading, error, related,
    flag, submitting, message, messageType,
    submissions, submissionsLoading, submissionsError,
    environment, remainingSeconds, countdownText, environmentStatus,
    load, loadSubmissions, setFlag, submit,
    refreshEnvironment, startEnvironment, stopEnvironment, copyAccess,
    suspend, resume, destroy,
  }
}

function mergeSubmissions(existing, incoming) {
  const seen = new Set(existing.map(item => String(item.id)))
  return [...existing, ...incoming.filter(item => !seen.has(String(item.id)))]
}
