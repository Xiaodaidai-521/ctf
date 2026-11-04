import { asList, finiteNumber } from '../contracts.js'
import { readPreferences, writeFilters, writeLastVisit } from './preferences.js'

// 靶场中枢状态工厂（与 Vue 无关，便于真实契约测试）。
// 保存的是“本次页面会话内的筛选/滚动/读取结果”，不是持久学习数据。
export function createHubState({ apiClient, storage = null, now = () => Date.now() } = {}) {
  const state = {
    categories: [], challenges: [], solved: new Set(), stats: null,
    filters: { category: null, difficulty: null, status: null },
    errors: { categories: '', list: '', stats: '', solved: '' },
    loading: { categories: false, list: false, stats: false, solved: false },
    loadedCount: 0, totalCount: null, generation: 0, scrollTop: 0,
    lastVisit: null,
  }

  // 与靶场页面共用同一份本机筛选/上次题目引用。
  function restore() {
    const saved = readPreferences(storage)
    state.filters = saved.filters
    state.scrollTop = saved.scrollTop
    state.lastVisit = saved.lastVisit
  }
  function persist() { writeFilters(storage, state.filters, state.scrollTop) }

  // 只记录题目引用、标题与访问时间，不保存 Flag 或题面答案。
  function rememberVisit(challenge) {
    const id = finiteNumber(challenge?.id)
    if (id === null) return
    state.lastVisit = { id, title: String(challenge.title || ''), at: now() }
    writeLastVisit(storage, state.lastVisit, state.lastVisit.at)
  }

  async function loadCategories() {
    state.loading.categories = true
    state.errors.categories = ''
    try {
      const value = await apiClient.categories()
      state.categories = asList(value).map(item => ({ id: item.id, name: item.name }))
    } catch { state.errors.categories = '分类暂时未能加载，仍可查看全部题目。' }
    finally { state.loading.categories = false }
  }

  async function loadList(params = {}) {
    const version = ++state.generation
    state.loading.list = true
    state.errors.list = ''
    try {
      const query = {}
      if (params.category) query.category = params.category
      if (params.difficulty) query.difficulty = params.difficulty
      const value = await apiClient.list(query)
      if (version !== state.generation) return // 迟到响应不覆盖新筛选
      const items = asList(value)
      state.challenges = items
      state.loadedCount = items.length
      state.totalCount = finiteNumber(value?.count)
    } catch {
      if (version !== state.generation) return
      state.errors.list = '题目暂时未能加载，请重试。'
      state.challenges = []
    } finally {
      if (version === state.generation) state.loading.list = false
    }
  }

  async function loadSolved() {
    state.loading.solved = true
    state.errors.solved = ''
    try {
      const value = await apiClient.solved()
      const ids = asList(value).map(item => finiteNumber(item?.challenge_id ?? item?.id ?? item)).filter(v => v !== null)
      state.solved = new Set(ids.map(String))
    } catch { state.errors.solved = '本人解题记录暂时未能读取。' }
    finally { state.loading.solved = false }
  }

  async function loadStats() {
    state.loading.stats = true
    state.errors.stats = ''
    state.stats = null
    try { state.stats = await apiClient.stats() } catch { state.errors.stats = '提交统计暂时未能加载。' }
    finally { state.loading.stats = false }
  }

  function isSolved(challenge) {
    if (typeof challenge?.is_solved === 'boolean') return challenge.is_solved
    return state.solved.has(String(challenge?.id))
  }

  function filtered() {
    return state.challenges.filter(item => {
      if (!state.filters.status) return true
      return state.filters.status === 'solved' ? isSolved(item) : !isSolved(item)
    })
  }

  // 当前筛选内的已解数只在已完整读取时给结论，否则页面标注“当前已加载题目”。
  function solvedInFilter() {
    const list = filtered()
    // 以当前真正持有的题目数判断是否读完，跨页追加后也能给出完整结论。
    const complete = state.totalCount !== null && state.challenges.length >= state.totalCount
    return { solved: list.filter(isSolved).length, scope: complete ? 'filter' : 'loaded' }
  }

  function resumeCandidate() {
    const visit = state.lastVisit
    if (!visit) return null
    const challenge = state.challenges.find(item => String(item.id) === String(visit.id))
    if (!challenge) return { ...visit, available: false }
    return { ...visit, title: challenge.title || visit.title, available: true }
  }

  function setFilter(patch) {
    state.filters = { ...state.filters, ...patch }
    persist()
  }

  return {
    state, restore, persist, rememberVisit, loadCategories, loadList, loadSolved, loadStats,
    isSolved, filtered, solvedInFilter, resumeCandidate, setFilter,
  }
}
