<template>
  <div class="challenges-page">
    <div class="container">
      <div class="challenges-layout">
        <!-- 左侧题目列表 -->
        <div class="challenges-main">
          <div class="page-header">
            <div>
              <p class="section-kicker">VIEW 02 / Challenge Selection</p>
              <h1 class="page-title">题目矩阵</h1>
            </div>
            <button class="btn btn-primary random-btn" @click="handleRandom">
              <i class="bi bi-shuffle"></i>
              随机一题
            </button>
          </div>

          <!-- 筛选器 -->
          <div class="filter-section">
            <div class="filter-row">
              <div class="filter-label">题目分类：</div>
              <div class="filter-buttons">
                <button
                  class="filter-btn"
                  :class="{ active: selectedCategory === null }"
                  @click="selectedCategory = null"
                >
                  全部
                </button>
                <button
                  v-for="category in challengeStore.categories"
                  :key="category.id"
                  class="filter-btn"
                  :class="{ active: selectedCategory === category.id }"
                  @click="selectedCategory = category.id"
                >
                  {{ category.name }}
                </button>
              </div>
            </div>

            <div class="filter-row">
              <div class="filter-label">难度筛选：</div>
              <div class="filter-buttons">
                <button
                  class="filter-btn"
                  :class="{ active: selectedDifficulty === null }"
                  @click="selectedDifficulty = null"
                >
                  全部
                </button>
                <button
                  v-for="difficulty in difficulties"
                  :key="difficulty.value"
                  class="filter-btn"
                  :class="{ active: selectedDifficulty === difficulty.value }"
                  @click="selectedDifficulty = difficulty.value"
                >
                  {{ difficulty.label }}
                </button>
              </div>
            </div>

            <div class="filter-row">
              <div class="filter-label">状态筛选：</div>
              <div class="filter-buttons">
                <button
                  class="filter-btn"
                  :class="{ active: selectedStatus === null }"
                  @click="selectedStatus = null"
                >
                  全部
                </button>
                <button
                  class="filter-btn"
                  :class="{ active: selectedStatus === 'unsolved' }"
                  @click="selectedStatus = 'unsolved'"
                >
                  未解出
                </button>
                <button
                  class="filter-btn"
                  :class="{ active: selectedStatus === 'solved' }"
                  @click="selectedStatus = 'solved'"
                >
                  已解出
                </button>
              </div>
            </div>
          </div>

          <p v-if="categoriesError" role="alert">{{ categoriesError }} <button @click="fetchCategories">重读分类</button></p>
          <!-- 题目列表 -->
          <p v-if="listLoading" role="status">正在读取题目…</p>
          <p v-else-if="listError" role="alert">{{ listError }} <button @click="fetchChallenges">重新读取题目</button></p>
          <div class="challenges-grid" v-else-if="filteredChallenges.length > 0">
            <ChallengeCard
              v-for="challenge in filteredChallenges"
              :key="challenge.id"
              :challenge="challenge"
              @click="openChallengeModal"
            />
          </div>
          <div class="empty-state" v-else>
            <div class="empty-icon">📭</div>
            <p class="empty-text">暂无符合条件的题目</p>
          </div>
          <div v-if="!listLoading && !listError && hasMore" class="load-more">
            <button :disabled="loadingMore" @click="loadMore">加载更多题目（已显示 {{ loadedChallenges.length }} / {{ totalCount }}）</button>
            <p v-if="loadMoreError" role="alert">{{ loadMoreError }}</p>
          </div>
        </div>
        <!-- 右侧边栏 -->
        <div class="challenges-sidebar">
          <div class="sidebar-card sidebar-card-dark">
            <div class="sidebar-top">
              <span>LAB BRIEF</span>
              <span>LIVE</span>
            </div>
            <h3 class="sidebar-title">解题统计</h3>
            <p v-if="statsError" role="alert">{{ statsError }} <button @click="fetchSubmissionStats">重读统计</button></p>
            <div v-if="userStore.isAuthenticated">
              <div class="stat-row">
                <span class="stat-label">我的积分</span>
                <span class="stat-value">{{ userStore.userInfo?.score ?? '—' }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">已解决题目</span>
                <span class="stat-value">{{ solvedCount ?? '—' }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">总提交次数</span>
                <span class="stat-value">{{ submissionStats?.total_submissions ?? '—' }}</span>
              </div>
            </div>
            <div v-else>
              <p class="stat-hint">请先登录查看统计信息</p>
              <router-link to="/login" class="btn btn-primary btn-block">
                立即登录
              </router-link>
            </div>
          </div>

          <div class="sidebar-card">
            <h3 class="sidebar-title">本人最近提交</h3>
            <p v-if="activitiesLoading" role="status">正在读取提交…</p>
            <p v-else-if="activitiesError" role="alert">{{ activitiesError }} <button @click="fetchRecentActivities">重读提交</button></p>
            <p v-else-if="recentActivities.length === 0">暂无可展示的本人提交</p>
            <div class="activity-list">
              <div v-for="(activity, index) in recentActivities" :key="index" class="activity-item">
                <span class="activity-time">{{ activity.created_at ? new Date(activity.created_at).toLocaleString('zh-CN') : '—' }}</span>
                <span class="activity-text">{{ activity.challenge_title }} · {{ activity.is_correct === true ? '正确' : activity.is_correct === false ? '错误' : '状态待确认' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 题目详情悬浮窗 -->
    <ChallengeDetailModal
      v-if="selectedChallenge"
      :key="selectedChallenge.id"
      :challenge-id="selectedChallenge.id"
      @close="closeChallengeModal"
    />
  </div>
</template>

<script setup>
import { ref, computed, onDeactivated, onMounted, onUnmounted, watch } from 'vue'
import { useChallengeStore } from '@/store/challenge'
import { useUserStore } from '@/store/user'
import ChallengeCard from '@/components/ChallengeCard.vue'
import ChallengeDetailModal from '@/components/ChallengeDetailModal.vue'
import api from '@/api'
import { createAccountGuard } from '@/shared/state/accountScope.js'

const challengeStore = useChallengeStore()
const userStore = useUserStore()


const selectedChallenge = ref(null)
onDeactivated(() => { selectedChallenge.value = null })
const selectedCategory = ref(null)
const selectedDifficulty = ref(null)
const selectedStatus = ref(null)

const difficulties = [
  { label: '简单', value: 'easy' },
  { label: '中等', value: 'medium' },
  { label: '困难', value: 'hard' },
  { label: '专家', value: 'expert' }
]

const guard = createAccountGuard()
onUnmounted(guard.dispose)
const submissionStats = ref(null)
const recentActivities = ref([])
const listError = ref(''), categoriesError = ref(''), statsError = ref(''), activitiesError = ref('')
const listLoading = ref(true), activitiesLoading = ref(false), loadingMore = ref(false), loadMoreError = ref('')
const loadedChallenges = ref([]), totalCount = ref(null), nextPage = ref(2)
let generation = 0
const hasMore = computed(() => totalCount.value !== null && loadedChallenges.value.length < totalCount.value)
const filteredChallenges = computed(() => {
  let challenges = loadedChallenges.value

  // 只在前端筛选状态，分类和难度通过 API 参数筛选
  if (selectedStatus.value) {
    challenges = challenges.filter(c => {
      if (selectedStatus.value === 'solved') return c.is_solved
      if (selectedStatus.value === 'unsolved') return !c.is_solved
      return true
    })
  }

  return challenges
})

const solvedCount = computed(() => submissionStats.value?.solved_challenges ?? null)
const listParams = () => ({
  ...(selectedCategory.value ? { category: selectedCategory.value } : {}),
  ...(selectedDifficulty.value ? { difficulty: selectedDifficulty.value } : {}),
})
const fetchChallenges = async () => {
  const reading = ++generation
  listLoading.value = true; loadingMore.value = false; listError.value = ''; loadMoreError.value = ''; loadedChallenges.value = []; totalCount.value = null
  try {
    const response = await challengeStore.fetchChallenges({ ...listParams(), page: 1 })
    if (!guard.current() || reading !== generation) return
    loadedChallenges.value = Array.isArray(response) ? response : response?.results || challengeStore.challenges || []
    totalCount.value = Number.isFinite(response?.count) ? response.count : null
    nextPage.value = 2
  } catch {
    if (guard.current() && reading === generation) listError.value = '题目列表读取失败，请重试。'
  } finally {
    if (guard.current() && reading === generation) listLoading.value = false
  }
}
const loadMore = async () => {
  if (loadingMore.value || !hasMore.value) return
  const reading = generation
  loadingMore.value = true; loadMoreError.value = ''
  try {
    const response = await api.challenge.getChallenges({ ...listParams(), page: nextPage.value })
    if (!guard.current() || reading !== generation) return
    const rows = Array.isArray(response) ? response : response.results || []
    const seen = new Set(loadedChallenges.value.map(row => row.id))
    loadedChallenges.value.push(...rows.filter(row => !seen.has(row.id)))
    nextPage.value++
  } catch {
    if (guard.current() && reading === generation) loadMoreError.value = '更多题目读取失败，请重试。'
  } finally {
    if (guard.current() && reading === generation) loadingMore.value = false
  }
}
const fetchCategories = async () => {
  categoriesError.value = ''
  try { await challengeStore.fetchCategories() }
  catch { if (guard.current()) categoriesError.value = '题目分类读取失败，请重试。' }
}
const fetchSubmissionStats = async () => {
  submissionStats.value = null; statsError.value = ''
  if (!userStore.isAuthenticated) return
  try {
    const response = await api.submission.stats()
    if (guard.current()) submissionStats.value = response
  } catch { if (guard.current()) statsError.value = '解题统计读取失败，请重试。' }
}
const fetchRecentActivities = async () => {
  recentActivities.value = []; activitiesError.value = ''
  if (!userStore.isAuthenticated) return
  activitiesLoading.value = true
  try {
    const response = await api.submission.mySubmissions()
    if (!guard.current()) return
    const rows = Array.isArray(response) ? response : response.results || []
    recentActivities.value = rows.slice().sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, 5)
  } catch { if (guard.current()) activitiesError.value = '本人提交记录读取失败，请重试。' }
  finally { if (guard.current()) activitiesLoading.value = false }
}
const handleRandom = () => {
  if (listLoading.value || listError.value || filteredChallenges.value.length === 0) return
  const randomChallenge = filteredChallenges.value[
    Math.floor(Math.random() * filteredChallenges.value.length)
  ]
  selectedChallenge.value = randomChallenge
}

const openChallengeModal = (challenge) => {
  selectedChallenge.value = challenge
}

const closeChallengeModal = () => {
  selectedChallenge.value = null
}

watch([selectedCategory, selectedDifficulty], () => {
  fetchChallenges()
})

onMounted(async () => {
  await Promise.all([
    fetchCategories(),
    fetchChallenges(),
    fetchSubmissionStats(), fetchRecentActivities()
  ])
})
</script>

<style scoped>
.challenges-page {
  padding: 42px 0 72px;
  min-height: calc(100vh - 60px);
}

.challenges-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 24px;
  align-items: start;
}

.challenges-main {
  min-width: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 20px;
  margin-bottom: 24px;
}

.page-title {
  margin-top: 6px;
  font-size: 48px;
  line-height: 1;
  font-weight: 950;
  color: var(--text-primary);
}

.random-btn {
  display: flex;
  align-items: center;
  gap: 6px;
}

.filter-section {
  background: rgba(255, 250, 242, 0.72);
  padding: 18px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  margin-bottom: 18px;
  box-shadow: none;
}

.filter-row {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding-bottom: 14px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--border-color);
}

.filter-row:last-child {
  margin-bottom: 0;
}

.filter-label {
  padding-top: 6px;
  font-size: 13px;
  font-weight: 850;
  color: var(--text-primary);
  min-width: 78px;
}

.filter-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.filter-btn {
  min-height: 32px;
  padding: 5px 12px;
  border: 1px solid var(--border-color);
  background: rgba(255, 250, 242, 0.72);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 750;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s ease;
}

.filter-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.filter-btn.active {
  border-color: var(--text-primary);
  background: var(--text-primary);
  color: #fbf7ef;
}

.challenges-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.empty-state {
  background: rgba(255, 250, 242, 0.72);
  padding: 60px 20px;
  text-align: center;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: none;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.empty-text {
  font-size: 14px;
  color: var(--text-secondary);
}

.challenges-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: sticky;
  top: 84px;
}

.sidebar-card {
  background: rgba(255, 250, 242, 0.74);
  padding: 18px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: none;
}

.sidebar-card-dark {
  color: #fff8ed !important;
  background: #181713 !important;
  border-color: #181713 !important;
  box-shadow: 12px 12px 0 rgba(24, 23, 19, 0.12) !important;
}

.sidebar-top {
  display: flex;
  justify-content: space-between;
  padding-bottom: 14px;
  margin-bottom: 16px;
  border-bottom: 1px solid rgba(248, 241, 232, 0.18);
  color: var(--secondary-color);
  font-size: 12px;
  font-weight: 950;
  text-transform: uppercase;
}

.sidebar-title {
  font-size: 22px;
  font-weight: 950;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
}

.sidebar-card-dark .sidebar-title {
  border-color: rgba(248, 241, 232, 0.18);
  color: #fff8ed;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-color);
}

.sidebar-card-dark .stat-row {
  min-height: 40px;
  border-bottom-color: rgba(255, 248, 237, 0.18);
}

.stat-row:last-child {
  border-bottom: none;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.sidebar-card-dark .stat-label {
  color: rgba(255, 248, 237, 0.82);
}

.stat-value {
  font-size: 14px;
  font-weight: 950;
  color: var(--text-primary);
}

.sidebar-card-dark .stat-value {
  color: #ffd56f;
}

.stat-hint {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
  padding: 16px 0;
}

.btn-block {
  width: 100%;
  margin-top: 10px;
}

.activity-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  border-top: 1px solid var(--border-color);
}

.activity-item {
  padding: 12px 0;
  background: transparent;
  border-bottom: 1px solid var(--border-color);
  border-radius: 0;
  font-size: 12px;
}

.activity-time {
  color: var(--text-secondary);
  font-size: 11px;
  display: block;
  margin-bottom: 4px;
}

.activity-text {
  font-size: 12px;
  color: var(--text-primary);
}

@media (max-width: 1024px) {
  .challenges-layout {
    grid-template-columns: 1fr;
  }

  .challenges-sidebar {
    display: none;
  }
}

@media (max-width: 640px) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .page-title {
    font-size: 38px;
  }

  .challenges-grid {
    grid-template-columns: 1fr;
  }

  .filter-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .filter-buttons {
    width: 100%;
  }

  .filter-btn {
    flex: 1;
  }
}
</style>
