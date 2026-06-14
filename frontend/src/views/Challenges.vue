<template>
  <div class="challenges-page">
    <div class="container">
      <div class="challenges-layout">
        <!-- 左侧题目列表 -->
        <div class="challenges-main">
          <div class="page-header">
            <h1 class="page-title">题目矩阵</h1>
            <button class="btn btn-primary random-btn" @click="handleRandom">
              🎲 随机一题
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
          <div class="sidebar-card">
            <h3 class="sidebar-title">📊 解题统计</h3>
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
            <h3 class="sidebar-title">🔥 实时动态</h3>
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
  padding: 16px 0;
  min-height: calc(100vh - 60px);
}

.challenges-layout {
  display: grid;
  grid-template-columns: 1fr 260px;
  gap: 16px;
  align-items: start;
}

.challenges-main {
  min-width: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-title {
  font-size: 20px;
  font-weight: bold;
  color: var(--text-primary);
}

.random-btn {
  display: flex;
  align-items: center;
  gap: 6px;
}

.filter-section {
  background: white;
  padding: 16px;
  border-radius: var(--radius-sm);
  margin-bottom: 16px;
  box-shadow: var(--shadow-sm);
}

.filter-row {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.filter-row:last-child {
  margin-bottom: 0;
}

.filter-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  min-width: 70px;
}

.filter-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.filter-btn {
  padding: 5px 12px;
  border: 1px solid var(--border-color);
  background: white;
  border-radius: var(--radius-sm);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.3s;
}

.filter-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.filter-btn.active {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: white;
}

.challenges-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.empty-state {
  background: white;
  padding: 60px 20px;
  text-align: center;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
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
  gap: 12px;
}

.sidebar-card {
  background: white;
  padding: 16px;
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
}

.sidebar-title {
  font-size: 14px;
  font-weight: bold;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 2px solid #f0f0f0;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.stat-row:last-child {
  border-bottom: none;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.stat-value {
  font-size: 13px;
  font-weight: bold;
  color: var(--text-primary);
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
  gap: 8px;
}

.activity-item {
  padding: 8px;
  background: #fafafa;
  border-radius: var(--radius-sm);
  font-size: 12px;
}

.activity-time {
  color: var(--text-secondary);
  font-size: 10px;
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
