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

          <!-- 题目列表 -->
          <div class="challenges-grid" v-if="filteredChallenges.length > 0">
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
        </div>

        <!-- 右侧边栏 -->
        <div class="challenges-sidebar">
          <div class="sidebar-card sidebar-card-dark">
            <div class="sidebar-top">
              <span>LAB BRIEF</span>
              <span>LIVE</span>
            </div>
            <h3 class="sidebar-title">解题统计</h3>
            <div v-if="userStore.isAuthenticated">
              <div class="stat-row">
                <span class="stat-label">我的积分</span>
                <span class="stat-value">{{ userStore.userInfo?.score || 0 }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">已解决题目</span>
                <span class="stat-value">{{ solvedCount }}</span>
              </div>
              <div class="stat-row">
                <span class="stat-label">总提交次数</span>
                <span class="stat-value">{{ submissionStats.total_submissions || 0 }}</span>
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
            <h3 class="sidebar-title">实时动态</h3>
            <div class="activity-list">
              <div v-for="(activity, index) in recentActivities" :key="index" class="activity-item">
                <span class="activity-time">{{ activity.time }}</span>
                <span class="activity-text">{{ activity.text }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 题目详情悬浮窗 -->
    <ChallengeDetailModal
      v-if="selectedChallenge"
      :challenge-id="selectedChallenge.id"
      @close="closeChallengeModal"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useChallengeStore } from '@/store/challenge'
import { useUserStore } from '@/store/user'
import { useRouter } from 'vue-router'
import ChallengeCard from '@/components/ChallengeCard.vue'
import ChallengeDetailModal from '@/components/ChallengeDetailModal.vue'
import api from '@/api'

const challengeStore = useChallengeStore()
const userStore = useUserStore()
const router = useRouter()

const selectedChallenge = ref(null)
const selectedCategory = ref(null)
const selectedDifficulty = ref(null)
const selectedStatus = ref(null)

const difficulties = [
  { label: '简单', value: 'easy' },
  { label: '中等', value: 'medium' },
  { label: '困难', value: 'hard' },
  { label: '专家', value: 'expert' }
]

const submissionStats = ref({})

const recentActivities = ref([
  { time: '10分钟前', text: 'user1 解决了 hello_world' },
  { time: '25分钟前', text: 'user2 解决了 base64_decode' },
  { time: '1小时前', text: 'user3 解决了 misc_forensics' },
  { time: '2小时前', text: 'user4 解决了 simple_login' },
  { time: '3小时前', text: 'user5 解决了 steganography' }
])

const filteredChallenges = computed(() => {
  let challenges = challengeStore.challenges

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

const solvedCount = computed(() => {
  return challengeStore.challenges.filter(c => c.is_solved).length
})

const fetchChallenges = async () => {
  try {
    const params = {}
    if (selectedCategory.value) {
      params.category = selectedCategory.value
    }
    if (selectedDifficulty.value) {
      params.difficulty = selectedDifficulty.value
    }
    await challengeStore.fetchChallenges(params)
  } catch (error) {
    console.error('获取题目失败:', error)
  }
}

const fetchSubmissionStats = async () => {
  if (userStore.isAuthenticated) {
    try {
      submissionStats.value = await api.submission.stats()
    } catch (error) {
      console.error('获取统计失败:', error)
    }
  }
}

const handleRandom = () => {
  if (filteredChallenges.value.length === 0) return
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

watch([selectedCategory, selectedDifficulty, selectedStatus], () => {
  fetchChallenges()
})

onMounted(async () => {
  await Promise.all([
    challengeStore.fetchCategories(),
    fetchChallenges(),
    fetchSubmissionStats()
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
