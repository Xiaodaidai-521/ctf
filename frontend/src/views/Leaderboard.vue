<template>
  <div class="leaderboard-page">
    <div class="container">
      <div class="page-header">
        <h1 class="page-title">🏆 排行榜</h1>
        <p class="page-subtitle">实时更新，展示最优秀的选手</p>
      </div>

      <div class="leaderboard-container">
        <div class="leaderboard-table">
          <div class="table-header">
            <div class="header-rank">排名</div>
            <div class="header-user">用户</div>
            <div class="header-team">战队</div>
            <div class="header-score">积分</div>
            <div class="header-solved">解题数</div>
          </div>

          <div v-if="loading" class="loading">
            加载中...
          </div>

          <div v-else-if="rankings.length > 0" class="table-body">
            <div
              v-for="(user, index) in rankings"
              :key="user.id"
              class="table-row"
              :class="{ 'top-three': index < 3 }"
            >
              <div class="cell-rank">
                <span v-if="index === 0" class="rank-icon rank-1">🥇</span>
                <span v-else-if="index === 1" class="rank-icon rank-2">🥈</span>
                <span v-else-if="index === 2" class="rank-icon rank-3">🥉</span>
                <span v-else class="rank-number">{{ user.rank }}</span>
              </div>
              <div class="cell-user">
                <div class="user-avatar">{{ user.nickname.charAt(0) || user.username.charAt(0) }}</div>
                <div class="user-info">
                  <div class="user-name">{{ user.nickname || user.username }}</div>
                  <div class="user-id">@{{ user.username }}</div>
                </div>
              </div>
              <div class="cell-team">{{ user.team || '-' }}</div>
              <div class="cell-score">
                <span class="score-value">{{ user.score }}</span>
                <span class="score-label">分</span>
              </div>
              <div class="cell-solved">
                <span class="solved-value">{{ user.solved_count }}</span>
                <span class="solved-label">题</span>
              </div>
            </div>
          </div>

          <div v-else class="empty-state">
            <div class="empty-icon">📭</div>
            <p class="empty-text">暂无排名数据</p>
          </div>
        </div>

        <!-- 统计信息 -->
        <div class="stats-sidebar">
          <div class="stat-card">
            <div class="stat-icon">👥</div>
            <div class="stat-content">
              <div class="stat-value">{{ totalUsers }}</div>
              <div class="stat-label">参赛选手</div>
            </div>
          </div>

          <div class="stat-card">
            <div class="stat-icon">🎯</div>
            <div class="stat-content">
              <div class="stat-value">{{ totalChallenges }}</div>
              <div class="stat-label">题目总数</div>
            </div>
          </div>

          <div class="stat-card">
            <div class="stat-icon">🏅</div>
            <div class="stat-content">
              <div class="stat-value">{{ topScore }}</div>
              <div class="stat-label">最高分</div>
            </div>
          </div>

          <div v-if="userStore.isAuthenticated && myRank" class="stat-card highlight">
            <div class="stat-icon">📍</div>
            <div class="stat-content">
              <div class="stat-value">#{{ myRank.rank }}</div>
              <div class="stat-label">我的排名</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useUserStore } from '@/store/user'
import api from '@/api'

const userStore = useUserStore()

const rankings = ref([])
const totalUsers = ref(0)
const loading = ref(false)

const totalChallenges = ref(12)

const topScore = computed(() => {
  return rankings.value.length > 0 ? rankings.value[0].score : 0
})

const myRank = computed(() => {
  if (!userStore.isAuthenticated || !userStore.userInfo) return null
  return rankings.value.find(r => r.username === userStore.userInfo.username)
})

const fetchLeaderboard = async () => {
  loading.value = true
  try {
    const response = await api.user.leaderboard({ page_size: 100 })
    rankings.value = response.rankings
    totalUsers.value = response.total
  } catch (error) {
    console.error('获取排行榜失败:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchLeaderboard()
})
</script>

<style scoped>
.leaderboard-page {
  padding: 24px 0;
  min-height: calc(100vh - 60px);
}

.page-header {
  text-align: center;
  margin-bottom: 32px;
}

.page-title {
  font-size: 32px;
  font-weight: bold;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
}

.leaderboard-container {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 24px;
}

.leaderboard-table {
  background: white;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.table-header {
  display: grid;
  grid-template-columns: 80px 250px 150px 120px 100px;
  gap: 16px;
  padding: 16px 24px;
  background: linear-gradient(135deg, #f0f0f0 0%, #fafafa 100%);
  border-bottom: 2px solid #e8e8e8;
  font-weight: 600;
  color: var(--text-primary);
}

.header-rank,
.header-user,
.header-team,
.header-score,
.header-solved {
  display: flex;
  align-items: center;
  font-size: 14px;
}

.table-body {
  max-height: 600px;
  overflow-y: auto;
}

.table-row {
  display: grid;
  grid-template-columns: 80px 250px 150px 120px 100px;
  gap: 16px;
  padding: 20px 24px;
  border-bottom: 1px solid #f0f0f0;
  transition: all 0.3s;
  align-items: center;
}

.table-row:hover {
  background: #fafafa;
}

.table-row.top-three {
  background: linear-gradient(135deg, #fffbe6 0%, #fff7cc 100%);
}

.table-row.top-three:hover {
  background: linear-gradient(135deg, #fff7cc 0%, #ffe58f 100%);
}

.cell-rank {
  display: flex;
  align-items: center;
  justify-content: center;
}

.rank-icon {
  font-size: 28px;
}

.rank-1 {
  animation: glow 2s ease-in-out infinite;
}

@keyframes glow {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.1);
  }
}

.rank-number {
  font-size: 18px;
  font-weight: bold;
  color: var(--text-primary);
}

.cell-user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: bold;
  font-size: 16px;
}

.user-info {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.user-id {
  font-size: 12px;
  color: var(--text-secondary);
}

.cell-team {
  font-size: 14px;
  color: var(--text-secondary);
}

.cell-score {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.score-value {
  font-size: 20px;
  font-weight: bold;
  color: var(--primary-color);
}

.score-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.cell-solved {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.solved-value {
  font-size: 18px;
  font-weight: bold;
  color: var(--success-color);
}

.solved-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.loading,
.empty-state {
  padding: 80px 20px;
  text-align: center;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.stats-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-card {
  background: white;
  padding: 24px;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  display: flex;
  align-items: center;
  gap: 16px;
  transition: all 0.3s;
}

.stat-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.stat-card.highlight {
  background: linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%);
  border: 2px solid var(--primary-color);
}

.stat-icon {
  font-size: 36px;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

/* 滚动条样式 */
.table-body::-webkit-scrollbar {
  width: 6px;
}

.table-body::-webkit-scrollbar-track {
  background: transparent;
}

.table-body::-webkit-scrollbar-thumb {
  background: #d9d9d9;
  border-radius: 3px;
}

.table-body::-webkit-scrollbar-thumb:hover {
  background: #bfbfbf;
}

/* 响应式设计 */
@media (max-width: 1024px) {
  .leaderboard-container {
    grid-template-columns: 1fr;
  }

  .stats-sidebar {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  }
}

@media (max-width: 768px) {
  .table-header,
  .table-row {
    grid-template-columns: 60px 1fr 100px;
  }

  .header-team,
  .header-solved,
  .cell-team,
  .cell-solved {
    display: none;
  }

  .cell-score {
    flex-direction: row;
    gap: 4px;
  }

  .score-value {
    font-size: 16px;
  }
}
</style>
