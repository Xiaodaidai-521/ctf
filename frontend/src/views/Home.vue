<template>
  <div class="home-page">
    <section class="cover">
      <div class="cover-copy">
        <p class="kicker">CTF TRAINING JOURNAL / LIVE DESK</p>
        <h1 class="hero-title">把每一次攻防训练，排成清晰的成长版面。</h1>
        <p class="hero-subtitle">网络安全与信息安全教学平台，围绕题库、学习路径、AI 辅导和训练数据，组织一套可持续推进的学习节奏。</p>
        <div class="hero-actions">
          <router-link to="/challenges" class="btn btn-primary btn-large">
            <i class="bi bi-crosshair"></i>
            进入题库
          </router-link>
          <router-link :to="userStore.isAuthenticated ? '/learning-paths' : '/register'" class="btn btn-outline btn-large">
            <i class="bi bi-signpost-split"></i>
            {{ userStore.isAuthenticated ? '查看学习路径' : '建立学习档案' }}
          </router-link>
        </div>
      </div>

      <aside class="cover-board">
        <div class="board-top">
          <span>LAB BRIEF</span>
          <span>LIVE</span>
        </div>
        <div class="board-focus">
          <span class="focus-index">01</span>
          <div>
            <p>本周专题</p>
            <h2>Web 渗透基础链路</h2>
          </div>
        </div>
        <div class="signal-grid">
          <div class="signal">
            <i class="bi bi-grid-3x3-gap"></i>
            <strong>{{ stats.challenges }}</strong>
            <small>训练题目</small>
          </div>
          <div class="signal">
            <i class="bi bi-diagram-3"></i>
            <strong>{{ stats.categories }}</strong>
            <small>课程分类</small>
          </div>
          <div class="signal">
            <i class="bi bi-people"></i>
            <strong>{{ stats.users }}</strong>
            <small>学员总数</small>
          </div>
          <div class="signal">
            <i class="bi bi-activity"></i>
            <strong>{{ stats.submissions }}</strong>
            <small>完成次数</small>
          </div>
        </div>
      </aside>
    </section>

    <section class="featured-section">
      <div class="container">
        <div class="section-header">
          <div>
            <p class="section-kicker">VIEW 01 / Training Desk</p>
            <h2 class="section-title">推荐题目</h2>
          </div>
          <router-link to="/challenges" class="section-more">查看全部</router-link>
        </div>
        <div class="featured-grid" v-if="featuredChallenges.length > 0">
          <ChallengeCard
            v-for="challenge in featuredChallenges"
            :key="challenge.id"
            :challenge="challenge"
          />
        </div>
      </div>
    </section>

    <section class="features-section">
      <div class="container">
        <div class="features-layout">
          <article class="lead-story">
            <div class="round-icon"><i class="bi bi-terminal"></i></div>
            <p class="section-kicker">Platform Features</p>
            <h2>平台特色</h2>
            <p>围绕网络安全学习、题库练习、实时排行和学习数据，提供稳定清晰的训练入口。</p>
          </article>

          <div class="story-list">
            <article class="story-row">
              <span class="story-no">A1</span>
              <span class="story-mark"><i class="bi bi-braces-asterisk"></i></span>
              <div>
                <h3>丰富题库</h3>
                <p>涵盖 Web、Crypto、Pwn、Reverse 等多个领域，满足不同水平的练习需求。</p>
              </div>
            </article>
            <article class="story-row">
              <span class="story-no">B2</span>
              <span class="story-mark"><i class="bi bi-trophy"></i></span>
              <div>
                <h3>实时排行</h3>
                <p>实时更新排行榜，帮助学员了解自己的学习进度和当前位置。</p>
              </div>
            </article>
            <article class="story-row">
              <span class="story-no">C3</span>
              <span class="story-mark"><i class="bi bi-clipboard2-data"></i></span>
              <div>
                <h3>数据统计</h3>
                <p>提供解题统计和进度追踪，帮助学员复盘练习效果并继续提升。</p>
              </div>
            </article>
            <article class="story-row">
              <span class="story-no">D4</span>
              <span class="story-mark"><i class="bi bi-shield-check"></i></span>
              <div>
                <h3>安全可靠</h3>
                <p>保持训练环境、容器访问和提交链路稳定，保障平台日常使用。</p>
              </div>
            </article>
          </div>
        </div>
      </div>
    </section>
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
.home-page {
  color: var(--text-primary);
}

.cover {
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto;
  min-height: calc(100vh - 64px);
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(360px, 0.72fr);
  align-items: center;
  gap: 56px;
  padding: 64px 0 48px;
}

.kicker {
  margin: 0 0 22px;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 950;
  text-transform: uppercase;
}

.hero-title {
  max-width: 760px;
  margin: 0 0 24px;
  font-size: 64px;
  line-height: 0.98;
  font-weight: 950;
}

.hero-subtitle {
  max-width: 650px;
  margin: 0 0 36px;
  color: var(--text-secondary);
  font-size: 18px;
  line-height: 1.85;
}

.hero-actions {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.btn-large {
  min-height: 48px;
  padding: 0 20px;
  font-size: 16px;
}

.cover-board {
  padding: 26px;
  border-radius: 8px;
  color: #f8f1e8;
  background: var(--bg-dark);
  box-shadow: 18px 18px 0 var(--bg-paper-2);
}

.board-top {
  display: flex;
  justify-content: space-between;
  padding-bottom: 18px;
  border-bottom: 1px solid rgba(248, 241, 232, 0.18);
  color: var(--secondary-color);
  font-size: 12px;
  font-weight: 950;
  text-transform: uppercase;
}

.board-focus {
  display: grid;
  grid-template-columns: 78px 1fr;
  gap: 18px;
  align-items: end;
  padding: 30px 0;
}

.focus-index {
  color: var(--secondary-color);
  font-size: 64px;
  line-height: 0.85;
  font-weight: 950;
}

.board-focus p {
  margin: 0 0 8px;
  color: rgba(248, 241, 232, 0.66);
}

.board-focus h2 {
  margin: 0;
  font-size: 31px;
  line-height: 1.1;
}

.signal-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  border: 1px solid rgba(248, 241, 232, 0.18);
}

.signal {
  min-height: 118px;
  padding: 18px;
  border-right: 1px solid rgba(248, 241, 232, 0.18);
  border-bottom: 1px solid rgba(248, 241, 232, 0.18);
}

.signal:nth-child(2n) {
  border-right: 0;
}

.signal:nth-last-child(-n + 2) {
  border-bottom: 0;
}

.signal i {
  color: var(--secondary-color);
  font-size: 20px;
}

.signal strong {
  display: block;
  margin-top: 14px;
  font-size: 30px;
}

.signal small {
  color: rgba(248, 241, 232, 0.62);
}

.featured-section,
.features-section {
  padding: 72px 0;
  border-top: 1px solid var(--border-color);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 24px;
  margin-bottom: 28px;
}

.section-title {
  margin-top: 6px;
  color: var(--text-primary);
  font-size: 40px;
  line-height: 1.08;
  font-weight: 950;
}

.section-more {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  padding: 0 14px;
  border: 1px solid var(--text-primary);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 850;
}

.section-more:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.featured-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
  gap: 16px;
}

.features-section {
  background: var(--bg-dark);
  color: #f5eee4;
}

.features-layout {
  display: grid;
  grid-template-columns: minmax(0, 0.85fr) minmax(320px, 1fr);
  gap: 44px;
}

.lead-story {
  padding-top: 32px;
  border-top: 6px solid #f5eee4;
}

.round-icon {
  width: 64px;
  height: 64px;
  display: grid;
  place-items: center;
  margin-bottom: 8px;
  border: 1px solid #f5eee4;
  border-radius: 50%;
  color: var(--secondary-color);
  font-size: 28px;
}

.lead-story h2 {
  margin: 16px 0 0;
  font-size: 40px;
  line-height: 1.08;
  font-weight: 950;
}

.lead-story p:last-child {
  margin: 22px 0 0;
  color: rgba(245, 238, 228, 0.68);
  font-size: 16px;
  line-height: 1.85;
}

.story-list {
  border-top: 1px solid rgba(245, 238, 228, 0.16);
}

.story-row {
  display: grid;
  grid-template-columns: 48px 58px 1fr;
  gap: 18px;
  align-items: start;
  padding: 24px 0;
  border-bottom: 1px solid rgba(245, 238, 228, 0.16);
}

.story-no {
  color: var(--secondary-color);
  font-weight: 950;
}

.story-mark {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: var(--bg-dark);
  background: #f5eee4;
  font-size: 22px;
}

.story-row h3 {
  margin: 0 0 8px;
  color: #f5eee4;
  font-size: 20px;
}

.story-row p {
  margin: 0;
  color: rgba(245, 238, 228, 0.66);
  line-height: 1.7;
}

@media (max-width: 980px) {
  .cover,
  .features-layout {
    grid-template-columns: 1fr;
  }

  .cover {
    min-height: auto;
    padding-top: 48px;
  }

  .hero-title {
    font-size: 48px;
  }
}

@media (max-width: 640px) {
  .cover {
    width: min(100% - 28px, 1180px);
    gap: 32px;
  }

  .hero-title {
    font-size: 38px;
  }

  .hero-subtitle {
    font-size: 15px;
  }

  .hero-actions {
    flex-direction: column;
  }

  .btn-large {
    width: 100%;
  }

  .signal-grid,
  .story-row {
    grid-template-columns: 1fr;
  }

  .signal {
    border-right: 0;
  }

  .signal:nth-last-child(-n + 2) {
    border-bottom: 1px solid rgba(248, 241, 232, 0.18);
  }

  .signal:last-child {
    border-bottom: 0;
  }

  .section-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .section-title,
  .lead-story h2 {
    font-size: 30px;
  }
}
</style>
