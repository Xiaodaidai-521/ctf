<template>
  <div class="home-page" :class="{ 'guest-layout': !userStore.isAuthenticated, 'student-layout': userStore.userInfo?.role === 'student' }">
    <section class="welcome">
      <div class="welcome-copy">
        <p class="eyebrow">网络安全学习 · 学、练、测、问、复盘</p>
        <h1>从理解原理，到<span class="hero-emphasis">独立完成</span>一次安全练习。</h1>
        <p>让教学智能体陪你梳理目标，沿着学习航线循序推进，在练习中检验理解。</p>
      </div>
      <aside class="learning-intro" aria-labelledby="home-agent-heading">
        <icon-robot /><h2 id="home-agent-heading">陪你学会，而不是替你完成</h2>
        <p>从评估开始，用讲解建立理解，再通过练习与检验发现下一步。</p>
        <ol><li>评估已有理解</li><li>讲解关键原理</li><li>分级提示下尝试</li><li>检验与复盘</li></ol>
        <div class="welcome-actions">
          <router-link to="/login" class="btn btn-primary">开启{{ names.guide }} <icon-arrow-right /></router-link>
          <router-link to="/register">建立学习档案</router-link>
          <router-link to="/learning-paths">探索{{ names.paths }}</router-link>
        </div>
      </aside>
    </section>
    <div class="home-bento">
      <section class="practice-section">
        <header><div><p class="eyebrow">从练习开始</p><h2>{{ names.practice }}精选</h2><p>浏览不同方向的入门练习，进入题目后查看难度与知识点，选择适合自己的起点。</p></div><router-link to="/challenges">进入{{ names.practice }} <icon-arrow-right /></router-link></header>
        <a-spin :loading="loading" tip="正在读取题目…">
          <a-alert v-if="failed" type="warning">题目暂时无法读取。<a-button type="text" @click="load">重试</a-button></a-alert>
          <div v-else-if="featuredChallenges.length" class="featured-grid"><ChallengeCard v-for="challenge in featuredChallenges" :key="challenge.id" :challenge="challenge" /></div>
          <a-empty v-else-if="!loading" description="暂时没有公开练习" />
        </a-spin>
      </section>
      <section class="learning-features" aria-label="学习方式">
        <article class="understanding-feature"><icon-code /><h2>在练习中理解</h2><p>覆盖网站安全、密码学、二进制与逆向等方向，在授权实验环境中动手验证。</p><router-link to="/challenges">进入{{ names.practice }} <icon-arrow-right /></router-link></article>
        <article class="paths-feature"><icon-branch /><h2>沿航线循序推进</h2><p>保留章节、实验与学习记录，每次回来都知道可以从哪里继续。</p><router-link to="/learning-paths">探索{{ names.paths }} <icon-arrow-right /></router-link></article>
        <article class="evidence-feature"><icon-bar-chart /><h2>用证据看见成长</h2><p>查看掌握情况、测评记录与复盘结论，把下一次学习安排得更清楚。</p><router-link to="/analytics">查看{{ names.growth }} <icon-arrow-right /></router-link></article>
      </section>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { useChallengeStore } from '@/store/challenge'
import { useUserStore } from '@/store/user'
import { names } from '@/shared/navigation/names.js'
import ChallengeCard from '@/components/ChallengeCard.vue'
const challengeStore = useChallengeStore()
const userStore = useUserStore()
const featuredChallenges = ref([])
const loading = ref(true)
const failed = ref(false)
async function load() {
  loading.value = true
  failed.value = false
  try {
    await challengeStore.fetchChallenges()
    featuredChallenges.value = challengeStore.challenges.slice(0, 6)
  } catch { failed.value = true }
  finally { loading.value = false }
}
onMounted(load)
</script>
<style scoped>
.home-page { max-width: var(--page-width); margin-inline: auto; padding: var(--space-6) var(--page-gutter); }
.welcome { display: grid; grid-template-columns: 3fr 2fr; align-items: center; gap: var(--space-6); margin-bottom: var(--space-8); }
.welcome h1 { max-width: var(--search-width); margin-bottom: var(--space-3); }
p { color: var(--ink-secondary); }
.eyebrow { font-size: var(--text-caption); color: var(--agent-accent); }
.welcome-actions { display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-3); margin-top: var(--space-4); }
.learning-intro { padding: var(--space-4); border-radius: var(--radius-panel); background: var(--agent-soft); }
.learning-intro > svg { font-size: var(--text-page); color: var(--agent-accent); margin-bottom: var(--space-2); }
.learning-intro h2 { font-size: var(--text-card); }
.learning-intro ol { padding-left: var(--space-3); margin: 0; color: var(--ink-secondary); }
.practice-section header { display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); margin-bottom: var(--space-3); }
.practice-section header > a { flex-shrink: 0; }
.practice-section header h2 { margin-bottom: var(--space-1); }
.practice-section header p { margin-bottom: var(--space-1); }
.practice-section :deep(.arco-spin) { width: 100%; }
.featured-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, var(--sidebar-width)), 1fr)); gap: var(--space-3); }
.learning-features { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); margin-top: var(--space-6); padding-top: var(--space-4); border-top: var(--stroke) solid var(--line); }
.learning-features h2 { font-size: var(--text-card); margin-block: var(--space-2) var(--space-1); }
.learning-features svg { font-size: var(--text-section); color: var(--action); }
.is-compact .welcome, .is-compact .learning-features { grid-template-columns: 1fr; }
.is-compact .practice-section header { align-items: flex-start; flex-direction: column; }

/* 学生/访客布局契约；教师与管理员不进入此作用域。 */
.home-page:is(.student-layout, .guest-layout) { padding-top: var(--space-8); }
.home-page:is(.student-layout, .guest-layout) .welcome { grid-template-columns: minmax(0, 1fr); justify-items: center; gap: var(--space-6); }
.home-page:is(.student-layout, .guest-layout) .welcome-copy { width: 100%; max-width: var(--reading-width); text-align: center; }
.home-page:is(.student-layout, .guest-layout) .welcome h1 { max-width: var(--reading-width); margin-inline: auto; font-size: var(--student-hero-size, clamp(var(--text-page), 5vw, calc(var(--text-page) * 1.8))); line-height: var(--leading-tight); letter-spacing: -.025em; }
.home-page:is(.student-layout, .guest-layout) .welcome-copy > p:last-child { max-width: var(--search-width); margin-inline: auto; font-size: var(--text-body); }
.home-page:is(.student-layout, .guest-layout) .learning-intro { width: min(100%, var(--reading-width)); box-sizing: border-box; padding: var(--space-4); background: var(--surface); border: var(--stroke) solid var(--line); border-radius: var(--student-console-radius, var(--radius-panel)); box-shadow: var(--shadow-raised); }
.home-page:is(.student-layout, .guest-layout) .learning-intro ol { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-2) var(--space-4); }
.home-page:is(.student-layout, .guest-layout) .welcome-actions { border-top: var(--stroke) solid var(--line); padding-top: var(--space-3); }
.home-page:is(.student-layout, .guest-layout) .home-bento { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); grid-template-areas: 'practice practice practice understanding' 'paths paths evidence evidence'; gap: var(--space-2); align-items: stretch; }
.home-page:is(.student-layout, .guest-layout) .learning-features { display: contents; }
.home-page:is(.student-layout, .guest-layout) .practice-section,
.home-page:is(.student-layout, .guest-layout) .learning-features article { min-width: 0; padding: var(--space-3); background: var(--surface); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); box-shadow: var(--shadow-raised); }
.home-page:is(.student-layout, .guest-layout) .practice-section { grid-area: practice; }
.home-page:is(.student-layout, .guest-layout) .understanding-feature { grid-area: understanding; }
.home-page:is(.student-layout, .guest-layout) .paths-feature { grid-area: paths; }
.home-page:is(.student-layout, .guest-layout) .evidence-feature { grid-area: evidence; }
.home-page:is(.student-layout, .guest-layout) .featured-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
@supports (background-clip: text) {
  .home-page:is(.student-layout, .guest-layout) .hero-emphasis { background: var(--student-hero-gradient, linear-gradient(100deg, var(--agent-accent), var(--action))); background-clip: text; color: transparent; }
}
@media (max-width: 1120px) {
  .home-page:is(.student-layout, .guest-layout) .home-bento { grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-areas: 'practice practice' 'understanding understanding' 'paths evidence'; }
}
@media (max-width: 768px) {
  .home-page:is(.student-layout, .guest-layout) { padding-top: var(--space-5); }
  .home-page:is(.student-layout, .guest-layout) .welcome { gap: var(--space-4); margin-bottom: var(--space-4); }
  .home-page:is(.student-layout, .guest-layout) .learning-intro { padding: var(--space-3); }
  .home-page:is(.student-layout, .guest-layout) .home-bento { grid-template-columns: minmax(0, 1fr); grid-template-areas: 'practice' 'understanding' 'paths' 'evidence'; }
  .home-page:is(.student-layout, .guest-layout) .featured-grid { grid-template-columns: minmax(0, 1fr); }
  .home-page:is(.student-layout, .guest-layout) .practice-section header { align-items: flex-start; flex-direction: column; }
}
</style>
