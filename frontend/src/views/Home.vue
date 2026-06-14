<template>
  <div class="home-page">
    <!-- 头部横幅 -->
    <div class="hero-banner">
      <div class="hero-content">
        <h1 class="hero-title">在线学习平台</h1>
        <p class="hero-subtitle">网络安全与信息安全教学平台，提升你的专业技能</p>
        <div class="hero-actions">
          <router-link to="/challenges" class="btn btn-primary btn-large">
            开始学习
          </router-link>
          <router-link to="/register" class="btn btn-outline btn-large">
            立即注册
          </router-link>
        </div>
      </div>
    </div>

    <!-- 统计信息 -->
    <div class="stats-section">
      <div class="container">
        <div class="stats-grid">
          <div class="stat-item">
            <div class="stat-value">{{ stats.challenges }}</div>
            <div class="stat-label">学习题目</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">{{ stats.users }}</div>
            <div class="stat-label">学员总数</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">{{ stats.submissions }}</div>
            <div class="stat-label">完成次数</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">{{ stats.categories }}</div>
            <div class="stat-label">课程分类</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 热门题目 -->
    <div class="featured-section">
      <div class="container">
        <div class="section-header">
          <h2 class="section-title">推荐题目</h2>
          <router-link to="/challenges" class="section-more">查看更多 →</router-link>
        </div>
        <div class="featured-grid" v-if="featuredChallenges.length > 0">
          <ChallengeCard
            v-for="challenge in featuredChallenges"
            :key="challenge.id"
            :challenge="challenge"
          />
        </div>
      </div>
    </div>

    <!-- 平台特色 -->
    <div class="features-section">
      <div class="container">
        <h2 class="section-title text-center">平台特色</h2>
        <div class="features-grid">
          <div class="feature-item">
            <div class="feature-icon">🎯</div>
            <h3 class="feature-title">丰富题库</h3>
            <p class="feature-desc">涵盖Web、Crypto、Pwn、Reverse等多个领域，满足不同水平的练习需求</p>
          </div>
          <div class="feature-item">
            <div class="feature-icon">🏆</div>
            <h3 class="feature-title">实时排行</h3>
            <p class="feature-desc">实时更新的排行榜，让你了解自己在选手中的位置</p>
          </div>
          <div class="feature-item">
            <div class="feature-icon">📊</div>
            <h3 class="feature-title">数据统计</h3>
            <p class="feature-desc">详细的解题统计和进度追踪，帮助你提升技能</p>
          </div>
          <div class="feature-item">
            <div class="feature-icon">🔒</div>
            <h3 class="feature-title">安全可靠</h3>
            <p class="feature-desc">专业的安全防护机制，保障比赛环境的稳定与安全</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { useChallengeStore } from '@/store/challenge'
import ChallengeCard from '@/components/ChallengeCard.vue'

const router = useRouter()
const userStore = useUserStore()
const challengeStore = useChallengeStore()

const stats = ref({
  challenges: 12,
  users: 6,
  submissions: 0,
  categories: 6
})

const featuredChallenges = ref([])

onMounted(async () => {
  try {
    await challengeStore.fetchChallenges()
    featuredChallenges.value = challengeStore.challenges.slice(0, 6)
  } catch (error) {
    console.error('加载数据失败:', error)
  }
})
</script>

<style scoped>
.hero-banner {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 80px 20px;
  text-align: center;
  color: white;
}

.hero-content {
  max-width: 800px;
  margin: 0 auto;
}

.hero-title {
  font-size: 48px;
  font-weight: bold;
  margin-bottom: 16px;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
}

.hero-subtitle {
  font-size: 18px;
  opacity: 0.9;
  margin-bottom: 32px;
}

.hero-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
}

.btn-large {
  padding: 12px 32px;
  font-size: 16px;
}

.stats-section {
  background: white;
  padding: 48px 0;
  box-shadow: var(--shadow-sm);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 32px;
}

.stat-item {
  text-align: center;
}

.stat-value {
  font-size: 48px;
  font-weight: bold;
  color: var(--primary-color);
  margin-bottom: 8px;
}

.stat-label {
  font-size: 14px;
  color: var(--text-secondary);
}

.featured-section {
  padding: 48px 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.section-title {
  font-size: 24px;
  font-weight: bold;
  color: var(--text-primary);
}

.section-more {
  color: var(--primary-color);
  font-size: 14px;
  text-decoration: none;
  transition: color 0.3s;
}

.section-more:hover {
  color: #40a9ff;
}

.featured-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.features-section {
  background: white;
  padding: 48px 0;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 32px;
}

.feature-item {
  text-align: center;
  padding: 24px;
}

.feature-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.feature-title {
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.feature-desc {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
}

@media (max-width: 768px) {
  .hero-title {
    font-size: 32px;
  }

  .hero-subtitle {
    font-size: 14px;
  }

  .hero-actions {
    flex-direction: column;
    align-items: center;
  }

  .stats-grid,
  .featured-grid,
  .features-grid {
    grid-template-columns: 1fr;
  }
}
</style>
