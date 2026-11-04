<template>
  <div class="leaderboard-page">
    <div class="container">
      <div class="page-header">
        <h1 class="page-title"><AppIcon name="bi-trophy" /> 排行榜</h1>
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
                <span v-if="index === 0" class="rank-icon rank-1" role="img" aria-label="第1名"><AppIcon name="bi-trophy" /></span>
                <span v-else-if="index === 1" class="rank-icon rank-2" role="img" aria-label="第2名"><AppIcon name="bi-trophy" /></span>
                <span v-else-if="index === 2" class="rank-icon rank-3" role="img" aria-label="第3名"><AppIcon name="bi-trophy" /></span>
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
            <div class="empty-icon"><AppIcon name="bi-inbox" /></div>
            <p class="empty-text">暂无排名数据</p>
          </div>
        </div>

        <!-- 统计信息 -->
        <div class="stats-sidebar">
          <div class="stat-card">
            <div class="stat-icon"><AppIcon name="bi-people" /></div>
            <div class="stat-content">
              <div class="stat-value">{{ totalUsers }}</div>
              <div class="stat-label">参赛选手</div>
            </div>
          </div>

          <div class="stat-card">
            <div class="stat-icon"><AppIcon name="bi-bullseye" /></div>
            <div class="stat-content">
              <div class="stat-value">{{ totalChallenges }}</div>
              <div class="stat-label">题目总数</div>
            </div>
          </div>

          <div class="stat-card">
            <div class="stat-icon"><AppIcon name="bi-trophy" /></div>
            <div class="stat-content">
              <div class="stat-value">{{ topScore }}</div>
              <div class="stat-label">最高分</div>
            </div>
          </div>

          <div v-if="userStore.isAuthenticated && myRank" class="stat-card highlight">
            <div class="stat-icon"><AppIcon name="bi-geo-alt" /></div>
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
  padding:var(--space-3) 0;
  min-height:calc(100vh - var(--space-7));
}

.page-header {
  text-align:center;
  margin-bottom:var(--space-4);
}

.page-title {
  font-size:var(--text-page);
  font-weight:bold;
  color:var(--text-primary);
  margin-bottom:var(--space-1);
}

.page-subtitle {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.leaderboard-container {
  display:grid;
  grid-template-columns:1fr var(--menu-width);
  gap:var(--space-3);
}

.leaderboard-table {
  background:var(--surface);
  border-radius:var(--radius-md);
  box-shadow: var(--shadow-raised);
  overflow:hidden;
}

.table-header {
  display:grid;
  grid-template-columns:var(--space-10) var(--sidebar-width) var(--row-label-width) var(--row-label-width) var(--row-label-width);
  gap:var(--space-2);
  padding:var(--space-2) var(--space-3);
  background: var(--surface-muted);
  border-bottom:calc(var(--stroke) * 2) solid var(--line);
  font-weight: var(--weight-strong);
  color:var(--text-primary);
}

.header-rank,
.header-user,
.header-team,
.header-score,
.header-solved {
  display:flex;
  align-items:center;
  font-size:var(--text-caption);
}

.table-body {
  max-height:var(--content-height);
  overflow-y:auto;
}

.table-row {
  display:grid;
  grid-template-columns:var(--space-10) var(--sidebar-width) var(--row-label-width) var(--row-label-width) var(--row-label-width);
  gap:var(--space-2);
  padding:var(--space-2) var(--space-3);
  border-bottom:var(--stroke) solid var(--line);
  transition:all var(--motion-normal);
  align-items:center;
}

.table-row:hover {
  background:var(--surface);
}

.table-row.top-three {
  background: var(--surface-muted);
}

.table-row.top-three:hover {
  background: var(--surface-muted);
}

.cell-rank {
  display:flex;
  align-items:center;
  justify-content:center;
}

.rank-icon {
  font-size:var(--text-section);
}

.rank-1 {
  animation:glow var(--motion-loop) ease-in-out infinite;
}

@keyframes glow {
  0%, 100% {
    transform:scale(1);
  }
  50% {
    transform:scale(1.1);
  }
}

.rank-number {
  font-size:var(--text-card);
  font-weight:bold;
  color:var(--text-primary);
}

.cell-user {
  display:flex;
  align-items:center;
  gap:var(--space-1);
}

.user-avatar {
  width:var(--space-5);
  height:var(--space-5);
  border-radius:50%;
  background: var(--surface-muted);
  display:flex;
  align-items:center;
  justify-content:center;
  color:var(--ink);
  font-weight:bold;
  font-size:var(--text-body);
}

.user-info {
  display:flex;
  flex-direction:column;
}

.user-name {
  font-size:var(--text-caption);
  font-weight: var(--weight-medium);
  color:var(--text-primary);
}

.user-id {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.cell-team {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.cell-score {
  display:flex;
  flex-direction:column;
  align-items:center;
}

.score-value {
  font-size:var(--text-card);
  font-weight:bold;
  color:var(--primary-color);
}

.score-label {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.cell-solved {
  display:flex;
  flex-direction:column;
  align-items:center;
}

.solved-value {
  font-size:var(--text-card);
  font-weight:bold;
  color:var(--success-color);
}

.solved-label {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.loading,
.empty-state {
  padding:var(--space-10) var(--space-2);
  text-align:center;
  color:var(--text-secondary);
}

.empty-icon {
  font-size:var(--text-page);
  margin-bottom:var(--space-2);
}

.stats-sidebar {
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
}

.stat-card {
  background:var(--surface);
  padding:var(--space-3);
  border-radius:var(--radius-md);
  box-shadow: var(--shadow-raised);
  display:flex;
  align-items:center;
  gap:var(--space-2);
  transition:all var(--motion-normal);
}

.stat-card:hover {
  box-shadow: var(--shadow-raised);
  transform:translateY(calc(calc(var(--stroke) * 2) * -1));
}

.stat-card.highlight {
  background: var(--surface-muted);
  border:calc(var(--stroke) * 2) solid var(--primary-color);
}

.stat-icon {
  font-size:var(--text-page);
}

.stat-content {
  flex:1;
}

.stat-value {
  font-size:var(--text-section);
  font-weight:bold;
  color:var(--text-primary);
  margin-bottom:calc(var(--space-1) / 2);
}

.stat-label {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

/* 滚动条样式 */
.table-body::-webkit-scrollbar {
  width:calc(var(--space-1) / 2);
}

.table-body::-webkit-scrollbar-track {
  background:transparent;
}

.table-body::-webkit-scrollbar-thumb {
  background:var(--surface);
  border-radius:var(--radius-control);
}

.table-body::-webkit-scrollbar-thumb:hover {
  background:var(--surface-muted);
}

/* 响应式设计 */
@media (max-width: 1120px) {
  .leaderboard-container {
    grid-template-columns:1fr;
  }

  .stats-sidebar {
    display:grid;
    grid-template-columns:repeat(auto-fit, minmax(var(--row-value-width), 1fr));
  }
}

@media (max-width: 768px) {
  .table-header,
  .table-row {
    grid-template-columns:var(--space-7) 1fr var(--row-label-width);
  }

  .header-team,
  .header-solved,
  .cell-team,
  .cell-solved {
    display:none;
  }

  .cell-score {
    flex-direction:row;
    gap:calc(var(--space-1) / 2);
  }

  .score-value {
    font-size:var(--text-body);
  }
}
</style>
