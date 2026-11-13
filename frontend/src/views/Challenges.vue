<template>
  <div class="challenges-page">
    <div class="container practice-stack">
      <PracticeSummary
        :authenticated="userStore.isAuthenticated"
        :stats="submissionStats"
        :stats-error="statsError"
        :solved-count="globalSolvedCount"
        :solved-scope="''"
        @retry="fetchSubmissionStats"
      />

      <ResumePractice
        v-if="resume"
        :candidate="resume"
        :source="resume.source"
        @resume="openChallengeModal"
      />

      <div class="challenges-layout">
        <div class="challenges-main">
          <div class="page-header">
            <div class="page-heading-copy">
              <h1 class="page-title">题目列表</h1>
              <p class="page-subtitle">按分类、难度和解答状态筛选；进入题目后先读题面，再提交验证。</p>
            </div>
            <button class="btn random-btn" :disabled="listLoading || Boolean(listError) || !filteredChallenges.length" @click="handleRandom">
              <icon-swap aria-hidden="true" /> 随机一题
            </button>
          </div>

          <div class="filter-section">
            <div v-if="categoriesError" class="page-error" role="alert">
              {{ categoriesError }} <button class="btn" @click="fetchCategories">重试分类</button>
            </div>
            <div class="filter-row">
              <div class="filter-label">题目分类</div>
              <div class="filter-buttons">
                <button class="filter-btn" :class="{ active: selectedCategory === null }" :aria-pressed="selectedCategory === null" :disabled="listLoading" @click="selectedCategory = null">全部</button>
                <button v-for="category in challengeStore.categories" :key="category.id" class="filter-btn" :class="{ active: selectedCategory === category.id }" :aria-pressed="selectedCategory === category.id" :disabled="listLoading" @click="selectedCategory = category.id">{{ category.name }}</button>
              </div>
            </div>
            <div class="filter-row">
              <div class="filter-label">难度筛选</div>
              <div class="filter-buttons">
                <button class="filter-btn" :class="{ active: selectedDifficulty === null }" :aria-pressed="selectedDifficulty === null" :disabled="listLoading" @click="selectedDifficulty = null">全部</button>
                <button v-for="difficulty in difficulties" :key="difficulty.value" class="filter-btn" :class="{ active: selectedDifficulty === difficulty.value }" :aria-pressed="selectedDifficulty === difficulty.value" :disabled="listLoading" @click="selectedDifficulty = difficulty.value">{{ difficulty.label }}</button>
              </div>
            </div>
            <div class="filter-row">
              <div class="filter-label">状态筛选</div>
              <div class="filter-buttons">
                <button class="filter-btn" :class="{ active: selectedStatus === null }" :aria-pressed="selectedStatus === null" @click="selectedStatus = null">全部</button>
                <button class="filter-btn" :class="{ active: selectedStatus === 'unsolved' }" :aria-pressed="selectedStatus === 'unsolved'" @click="selectedStatus = 'unsolved'">未解出</button>
                <button class="filter-btn" :class="{ active: selectedStatus === 'solved' }" :aria-pressed="selectedStatus === 'solved'" @click="selectedStatus = 'solved'">已解出</button>
              </div>
            </div>
            <p v-if="userStore.isAuthenticated && !listLoading && !listError" class="filter-scope">{{ scopeNote }}</p>
          </div>

          <div v-if="listLoading" class="empty-state" role="status">正在加载题目…</div>
          <div v-else-if="listError" class="empty-state page-error" role="alert">
            <p>{{ listError }}</p><button class="btn" @click="fetchChallenges">重新加载题目</button>
          </div>
          <div v-else-if="filteredChallenges.length" class="challenges-grid">
            <ChallengeCard v-for="challenge in filteredChallenges" :key="challenge.id" :challenge="challenge" @click="openChallengeModal" />
          </div>
          <div v-else class="empty-state">
            <icon-search class="empty-icon" aria-hidden="true" />
            <p>{{ hasFilters ? '暂无符合条件的题目，可调整筛选条件。' : '题库暂时还没有题目。' }}</p>
            <button v-if="hasFilters" class="btn" @click="clearFilters">清除筛选</button>
          </div>

          <div v-if="!listLoading && !listError && hasMore" class="load-more">
            <button class="btn" :disabled="loadingMore" @click="loadMore">
              {{ loadingMore ? '正在加载…' : `加载更多题目（已显示 ${loadedChallenges.length} / ${totalCount}）` }}
            </button>
            <p v-if="loadMoreError" class="load-more-error" role="alert">{{ loadMoreError }}</p>
          </div>
          <p v-else-if="!listLoading && !listError && totalCount !== null && totalCount > 20" class="list-footnote">
            已显示全部 {{ totalCount }} 道符合条件的题目。
          </p>
        </div>

        <aside class="challenges-sidebar" aria-label="练习侧栏">
          <section class="sidebar-card">
            <h2 class="sidebar-title">我的最近提交</h2>
            <p v-if="!userStore.isAuthenticated" class="stat-hint">登录后查看自己的练习记录。</p>
            <p v-else-if="activitiesLoading" role="status" class="stat-hint">正在加载最近提交…</p>
            <div v-else-if="activitiesError" class="page-error" role="alert">{{ activitiesError }} <button class="btn" @click="fetchRecentActivities">重试记录</button></div>
            <ul v-else-if="recentActivities.length" class="activity-list">
              <li v-for="activity in recentActivities" :key="activity.id" class="activity-item">
                <time class="activity-time">{{ formatActivityTime(activity.created_at) }}</time>
                <span>{{ activity.challenge_title || '题目名称暂不可用' }}</span>
                <span class="activity-result" :class="{ 'is-correct': activity.is_correct === true, 'is-incorrect': activity.is_correct === false }">{{ activity.is_correct === true ? '已解出' : activity.is_correct === false ? '未通过' : '状态待确认' }}</span>
              </li>
            </ul>
            <p v-else class="stat-hint">还没有提交记录，选一道题开始练习吧。</p>
            <router-link v-if="!userStore.isAuthenticated" to="/login" class="btn btn-primary btn-block">立即登录</router-link>
          </section>

          <PathRecommendations
            :recommendations="pathRecommendations"
            :joined="joinedPaths"
            :optional="optionalPaths"
            :loading="pathsLoading"
            :error="pathsError"
            :authenticated="userStore.isAuthenticated"
            @retry="fetchPaths"
          />
        </aside>
      </div>
    </div>
    <ChallengeDetailModal v-if="selectedChallenge" :key="selectedChallenge.id" :challenge-id="selectedChallenge.id" @close="closeChallengeModal" />
  </div>
</template>

<script setup>
import { names } from '@/shared/navigation/names'
import { createAccountGuard } from '@/shared/state/accountScope.js'
import { accountMemoryStorage } from '@/shared/state/retention.js'
import { ref, computed, onMounted, onUnmounted, onDeactivated, watch, nextTick } from 'vue'
import { useChallengeStore } from '@/store/challenge'
import { useUserStore } from '@/store/user'
import ChallengeCard from '@/components/ChallengeCard.vue'
import ChallengeDetailModal from '@/components/ChallengeDetailModal.vue'
import { createHubState } from '@/learning/practice/hubStore'
import PracticeSummary from '@/learning/practice/components/PracticeSummary.vue'
import ResumePractice from '@/learning/practice/components/ResumePractice.vue'
import PathRecommendations from '@/learning/practice/components/PathRecommendations.vue'
import api from '@/api'

const challengeStore = useChallengeStore()
const userStore = useUserStore()

// Only this account's current browser session keeps UI preferences, never browser persistence.
const account = createAccountGuard()
const hub = createHubState({ storage: accountMemoryStorage('practice:hub') })
if (typeof localStorage !== 'undefined') {
  try { localStorage.removeItem('ctf:practice:filters'); localStorage.removeItem('ctf:practice:last-visit') } catch { /* storage may be unavailable */ }
}
hub.restore()

const selectedChallenge = ref(null)
const selectedCategory = ref(hub.state.filters.category)
const selectedDifficulty = ref(hub.state.filters.difficulty)
const selectedStatus = ref(hub.state.filters.status)
const listError = ref('')
const categoriesError = ref('')
const statsError = ref('')
const activitiesError = ref('')
const statsLoading = ref(false)
const activitiesLoading = ref(false)
const difficulties = [
  { label: '简单', value: 'easy' },
  { label: '中等', value: 'medium' },
  { label: '困难', value: 'hard' },
  { label: '专家', value: 'expert' }
]
const submissionStats = ref(null)
const recentActivities = ref([])
const resume = ref(null)
const totalCount = ref(null)
const page = ref(1)
const loadingMore = ref(false)
const loadMoreError = ref('')
const listRequest = ref(0)
const pathsLoading = ref(false)
const pathsError = ref('')
const pathRecommendations = ref([])
const joinedPaths = ref([])
const optionalPaths = ref([])

const loadedChallenges = ref([])
const listLoading = ref(false)
const filteredChallenges = computed(() => {
  let challenges = loadedChallenges.value
  // 只在前端筛选解答状态，分类和难度通过 API 参数筛选。
  if (selectedStatus.value) {
    challenges = challenges.filter(c => selectedStatus.value === 'solved' ? c.is_solved : !c.is_solved)
  }
  return challenges
})
const solvedCount = computed(() => filteredChallenges.value.filter(c => c.is_solved).length)
const globalSolvedCount = computed(() => {
  const value = submissionStats.value?.solved_challenges
  return value !== null && value !== undefined && Number.isFinite(Number(value)) ? Number(value) : null
})
const hasFilters = computed(() => Boolean(selectedCategory.value || selectedDifficulty.value || selectedStatus.value))
const hasMore = computed(() => totalCount.value !== null && loadedChallenges.value.length < totalCount.value)
// 只有全部页读完才把“当前筛选已解”当完整结论；否则明确是已加载范围。
const scopeNote = computed(() => {
  const loaded = loadedChallenges.value.length
  const complete = totalCount.value !== null && loaded >= totalCount.value
  if (complete) return `当前筛选共 ${totalCount.value} 道，已解出 ${solvedCount.value} 道。`
  if (totalCount.value !== null) return `当前已加载 ${loaded} / ${totalCount.value} 道，已解出 ${solvedCount.value} 道（只统计已加载题目）。`
  return `当前已加载 ${loaded} 道，已解出 ${solvedCount.value} 道。`
})

function currentParams() {
  const params = {}
  if (selectedCategory.value) params.category = selectedCategory.value
  if (selectedDifficulty.value) params.difficulty = selectedDifficulty.value
  return params
}
const fetchChallenges = async () => {
  if (!account.current()) return
  listLoading.value = true
  listError.value = ''
  loadingMore.value = false
  loadMoreError.value = ''
  loadedChallenges.value = []
  totalCount.value = null
  const request = ++listRequest.value
  try {
    const response = await challengeStore.fetchChallenges({ ...currentParams(), page: 1 })
    if (!account.current() || request !== listRequest.value) return // 迟到响应不覆盖新筛选
    loadedChallenges.value = listOf(response)
    totalCount.value = response?.count !== null && response?.count !== undefined && Number.isFinite(Number(response.count)) ? Number(response.count) : null
    page.value = 1

  } catch {
    if (account.current() && request === listRequest.value) listError.value = '题目暂时未能加载，请重试。'
  } finally { if (account.current() && request === listRequest.value) listLoading.value = false }
}
const fetchCategories = async () => {
  categoriesError.value = ''
  try {
    await challengeStore.fetchCategories()
  } catch {
    if (account.current()) categoriesError.value = '分类暂时未能加载，仍可查看全部题目。'
  }
}
const fetchSubmissionStats = async () => {
  if (!userStore.isAuthenticated) return
  statsLoading.value = true
  statsError.value = ''
  submissionStats.value = null
  try {
    const value = await api.submission.stats()
    if (!account.current()) return
    submissionStats.value = value
  } catch {
    if (account.current()) statsError.value = '提交统计暂时未能加载。'
  } finally {
    if (account.current()) statsLoading.value = false
  }
}
const fetchRecentActivities = async () => {
  if (!userStore.isAuthenticated) return
  activitiesLoading.value = true
  activitiesError.value = ''
  try {
    const response = await api.submission.mySubmissions()
    if (!account.current()) return
    const items = listOf(response)
    recentActivities.value = [...items].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 5)
    maybeRecentResume()
  } catch {
    if (account.current()) activitiesError.value = '最近提交暂时未能加载。'
  } finally {
    if (account.current()) activitiesLoading.value = false
  }
}
const fetchPaths = async () => {
  if (!userStore.isAuthenticated) {
    pathRecommendations.value = []; joinedPaths.value = []; optionalPaths.value = []
    pathsLoading.value = false; pathsError.value = ''
    return
  }
  pathsLoading.value = true
  pathsError.value = ''
  const jobs = [api.learningPaths.list({ page_size: 4 }), api.learningPaths.my()]
  if (userStore.isAuthenticated) jobs.push(api.learningPaths.recommendations())
  const results = await Promise.allSettled(jobs)
  if (!account.current()) return
  const [optional, joined, recommended] = results
  optionalPaths.value = optional.status === 'fulfilled' ? listOf(optional.value) : []
  joinedPaths.value = joined.status === 'fulfilled' ? listOf(joined.value) : []
  pathRecommendations.value = recommended?.status === 'fulfilled' ? listOf(recommended.value?.recommendations ?? recommended.value).map(normalizeRecommendation) : []
  const failures = []
  if (!userStore.isAuthenticated) failures.push('登录后可读取个性化推荐')
  else if (recommended?.status === 'rejected') failures.push('个性化推荐暂时未能读取')
  if (joined.status === 'rejected') failures.push('在学航线暂时未能读取')
  if (optional.status === 'rejected') failures.push('公开航线暂时未能读取')
  pathsError.value = failures.length ? `${failures.join('；')}。` : ''
  pathsLoading.value = false
}
const listOf = value => {
  if (Array.isArray(value)) return value
  if (Array.isArray(value?.results)) return value.results
  if (Array.isArray(value?.recommendations)) return value.recommendations
  return []
}
const normalizeRecommendation = item => ({
  path_id: item.path_id ?? item.path ?? item.learning_path ?? item.id,
  title: item.path_title ?? item.title,
  difficulty: item.path_difficulty ?? item.difficulty,
  estimated_hours: item.estimated_hours,
  // 只用后端给出的理由；没有就如实说明，不编造“适合你”。
  reason: item.reason || item.recommendation_type_display || '系统推荐（未提供具体理由）',
})

const formatActivityTime = (value) => {
  const date = new Date(value)
  return value && Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN') : '时间暂不可用'
}
const handleRandom = () => {
  if (listLoading.value || listError.value || !filteredChallenges.value.length) return
  openChallengeModal(filteredChallenges.value[Math.floor(Math.random() * filteredChallenges.value.length)])
}
const openChallengeModal = (challenge) => {
  hub.rememberVisit(challenge)
  resume.value = null
  selectedChallenge.value = challenge
}
const closeChallengeModal = async () => {
  selectedChallenge.value = null
  // 弹层内可能刚提交过答案：读回统计、最近提交与列表解答状态。
  if (userStore.isAuthenticated) {
    await Promise.allSettled([fetchSubmissionStats(), fetchRecentActivities(), fetchChallenges()])
  }
  // 关闭后可立即继续刚进入的题目。
  if (account.current()) await verifyResume()
}
const loadMore = async () => {
  if (loadingMore.value || !hasMore.value) return
  const request = listRequest.value
  loadingMore.value = true
  loadMoreError.value = ''
  try {
    const response = await api.challenge.getChallenges({ ...currentParams(), page: page.value + 1 })
    if (!account.current() || request !== listRequest.value) return
    const items = listOf(response)
    const known = new Set(loadedChallenges.value.map(item => String(item.id)))
    loadedChallenges.value.push(...items.filter(item => !known.has(String(item.id))))
    page.value += 1
    totalCount.value = response?.count !== null && response?.count !== undefined && Number.isFinite(Number(response.count)) ? Number(response.count) : totalCount.value
  } catch {
    if (account.current() && request === listRequest.value) loadMoreError.value = '更多题目暂时未能加载，请重试。'
  } finally {
    if (account.current() && request === listRequest.value) loadingMore.value = false
  }
}
const clearFilters = () => {
  selectedCategory.value = null
  selectedDifficulty.value = null
  selectedStatus.value = null
}

// 上次进入的题目优先；无法读取时说明失效并保留回列表入口。
const verifyResume = async () => {
  if (!account.current()) return
  const base = hub.resumeCandidate()
  if (!base) { maybeRecentResume(); return }
  try {
    const detail = await api.challenge.getChallengeDetail(base.id)
    if (!account.current()) return
    if (!detail || detail.id === undefined) throw new Error('empty')
    resume.value = {
      id: base.id, title: detail.title || base.title, available: true,
      isSolved: Boolean(detail.is_solved), source: 'local',
    }
  } catch {
    if (!account.current()) return
    resume.value = { id: base.id, title: base.title, available: false, source: 'local' }
  }
}
// 无本机访问记录时，用最近一次未通过的提交作替代，并如实叫“继续最近练习”。
const maybeRecentResume = () => {
  if (resume.value || hub.state.lastVisit || !userStore.isAuthenticated) return
  const latest = recentActivities.value.find(item => item.is_correct === false && item.challenge_id)
  if (!latest) return
  resume.value = {
    id: latest.challenge_id, title: latest.challenge_title || '最近练习的题目',
    available: true, source: 'recent',
  }
}

function saveScroll() {
  if (typeof window === 'undefined') return
  hub.state.scrollTop = window.scrollY || 0
  hub.persist()
}


watch([selectedCategory, selectedDifficulty], () => {
  hub.state.scrollTop = 0
  hub.setFilter({
    category: selectedCategory.value, difficulty: selectedDifficulty.value, status: selectedStatus.value,
  })
  if (typeof window !== 'undefined') window.scrollTo({ top: 0, behavior: 'auto' })
  fetchChallenges()
})
watch(selectedStatus, () => {
  hub.setFilter({
    category: selectedCategory.value, difficulty: selectedDifficulty.value, status: selectedStatus.value,
  })
})
onMounted(async () => {
  const jobs = [fetchCategories(), fetchChallenges(), fetchSubmissionStats(), fetchRecentActivities(), fetchPaths()]
  // 先等列表与最近提交，再决定继续项，避免把“最近练习”误当本机上次。
  await Promise.allSettled(jobs)
  await verifyResume()
})
// Returning does not collapse an already paged list back to its first page.
onDeactivated(() => { saveScroll(); selectedChallenge.value = null })
onUnmounted(() => {
  saveScroll(); account.dispose(); ++listRequest.value
  loadedChallenges.value = []; selectedChallenge.value = null; submissionStats.value = null; recentActivities.value = []
  pathRecommendations.value = []; joinedPaths.value = []; optionalPaths.value = []
})
</script>

<style scoped>
.challenges-page { padding: var(--space-3) 0 var(--space-6); }
.practice-stack { display: grid; gap: var(--density-gap); }
.challenges-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(var(--sidebar-width), .35fr); gap: var(--density-gap); align-items: start; }
.challenges-main { min-width: 0; display: grid; gap: var(--density-gap); }
.page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-2); }
.page-heading-copy { min-width: 0; }
.page-title { margin: 0; font-size: var(--text-page); line-height: var(--leading-tight); }
.page-subtitle { margin: var(--space-1) 0 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.random-btn { display: inline-flex; gap: var(--space-1); align-items: center; }
.filter-section { background: var(--surface); padding: var(--space-2); border-radius: var(--radius-panel); }
.filter-row { display: flex; align-items: start; gap: var(--space-2); padding: var(--space-1) 0; border-bottom: var(--stroke) solid var(--line); }
.filter-row:last-of-type { border: 0; }
.filter-label { padding-top: var(--space-1); font-size: var(--text-caption); font-weight: var(--weight-medium); white-space: nowrap; }
.filter-buttons { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.filter-btn { min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink-secondary); font: inherit; font-size: var(--text-caption); cursor: pointer; transition: background var(--motion-fast); }
.filter-btn:hover:not(:disabled) { background: var(--surface-hover); }
.filter-btn:active:not(:disabled) { background: var(--surface-muted); }
.filter-btn.active { border-color: var(--action); background: var(--action-soft); color: var(--action); }
.filter-btn:disabled { background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
.filter-scope { margin: var(--space-1) 0 0; color: var(--ink-muted); font-size: var(--text-caption); }
.challenges-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, var(--sidebar-width)), 1fr)); gap: var(--density-gap); }
.empty-state { padding: var(--space-6) var(--space-3); text-align: center; color: var(--ink-secondary); background: var(--surface); border-radius: var(--radius-panel); }
.empty-state .btn { margin-top: var(--space-2); }
.empty-icon { font-size: var(--text-section); }
.page-error { color: var(--negative); background: var(--negative-soft); padding: var(--space-2); border-radius: var(--radius-control); }
.page-error .btn { margin-top: var(--space-1); }
.load-more { display: grid; justify-items: center; gap: var(--space-1); }
.load-more-error { margin: 0; color: var(--negative); font-size: var(--text-caption); }
.list-footnote { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); text-align: center; }
.challenges-sidebar { display: grid; gap: var(--density-gap); min-width: 0; }
.sidebar-card { background: var(--surface); padding: var(--space-3); border-radius: var(--radius-panel); min-width: 0; }
.sidebar-title { font-size: var(--text-card); margin: 0 0 var(--space-2); }
.stat-hint { font-size: var(--text-caption); color: var(--ink-secondary); }
.btn-block { width: 100%; margin-top: var(--space-1); }
.activity-list { margin: 0; padding: 0; list-style: none; }
.activity-item { padding: var(--space-2) 0; border-top: var(--stroke) solid var(--line); font-size: var(--text-caption); overflow-wrap: anywhere; }
.activity-time { display: block; color: var(--ink-secondary); margin-bottom: var(--space-1); }
.activity-result { display: block; margin-top: var(--space-1); }
.is-correct { color: var(--positive); }
.is-incorrect { color: var(--negative); }
.is-compact .challenges-layout { grid-template-columns: 1fr; }
.is-compact .filter-row { flex-direction: column; gap: var(--space-1); }
.is-compact .sidebar-card { padding: var(--space-2); }
@media (max-width: 900px) {
  .challenges-layout { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 768px) {
  .page-header { align-items: stretch; flex-direction: column; }
  .random-btn { justify-content: center; }
  .filter-row { flex-direction: column; gap: var(--space-1); }
}
</style>
