<template>
  <section class="guide-page" :class="{ 'student-layout': isStudent }">
    <header class="guide-heading"><span class="guide-mark"><icon-compass /></span><div><p class="guide-eyebrow">{{ names.guide }} · 你的学习工作台</p><h1>今天，想学会什么？</h1><p>从一个问题开始，让教学智能体陪你理解、尝试，再独立完成。</p></div></header>
    <div class="guide-console">
    <form class="guide-input" @submit.prevent="ask">
      <label for="guide-question">说说你的学习目标或卡住的地方</label>
      <textarea id="guide-question" v-model="question" placeholder="例如：我想理解访问控制，应该先练什么？" rows="3" maxlength="2000" @keydown.ctrl.enter.prevent="ask" />
      <div class="input-footer"><span><icon-safe /> 先给思路与分级提示，不代做答案</span><a-button html-type="submit" type="primary" :disabled="!question.trim()">开始导学 <icon-arrow-right /></a-button></div>
    </form>
    <div class="guide-shortcuts" aria-label="导学快捷问题"><button v-for="prompt in prompts" :key="prompt" @click="question = prompt">{{ prompt }}<icon-plus /></button><button @click="openTutor(router)">继续导学对话<icon-message /></button></div>
    <ol class="teaching-steps" aria-label="四步教学闭环"><li v-for="(step, index) in steps" :key="step"><span>{{ index + 1 }}</span>{{ step }}<icon-right v-if="index < steps.length - 1" /></li></ol>
    </div>

    <div class="guide-section-heading"><div><h2>接下来这样学</h2><p>根据你的学习记录整理。可以从这里继续，也可以告诉智能体调整方向。</p></div><a-button type="text" :loading="loading" @click="load">刷新</a-button></div>
    <a-alert v-if="failed.length" type="warning" class="guide-notice">{{ failed.join('、') }}暂时无法读取。已读取的内容仍可使用，请稍后刷新。</a-alert>
    <a-spin :loading="loading" class="guide-loading" tip="正在整理学习记录…">
      <div class="guide-results">
        <section class="result-block" aria-labelledby="continue-heading"><div class="block-title"><icon-history /><h3 id="continue-heading">继续上次</h3></div>
          <PathNextStep v-if="lastPath && isStudent" :step="nextStep" :pending="entering" :show-adjust="true" @confirm="enterNext" @adjust="askAdjust" />
          <template v-else-if="lastPath"><h4>{{ lastPath.current_module_title || lastPath.path_title }}</h4><p>{{ lastPath.path_title }}<template v-if="hasChapterCounts"> · 已完成 {{ lastPath.completed_modules || 0 }} / {{ lastPath.total_modules || 0 }} 个章节</template></p><router-link :to="pathTarget(lastPath)">继续学习 <icon-arrow-right /></router-link></template>
          <template v-else-if="conversation"><h4>{{ conversation.title || '上次的导学对话' }}</h4><p>回看讲解，接着梳理尚未理解的部分。</p><button class="text-action" @click="openTutor(router)">继续对话 <icon-arrow-right /></button></template>
          <template v-else><p>{{ failed.includes('学习记录') || failed.includes('导学对话') ? '记录暂时无法读取，不代表没有学习记录。' : '还没有进行中的学习。从感兴趣的航线开始吧。' }}</p><router-link to="/learning-paths">探索{{ names.paths }} <icon-arrow-right /></router-link></template>
        </section>
        <section class="result-block" aria-labelledby="plan-heading"><div class="block-title"><icon-calendar /><h3 id="plan-heading">今日计划</h3></div>
          <p v-if="failed.includes('学习记录') || failed.includes('复习提醒') || artifacts?.failures?.length">部分记录未能读取，暂不据此安排新的学习顺序。</p>
          <ol v-else class="plan-list"><li v-for="(item, index) in plan" :key="`${index}-${item.title}`"><router-link :to="item.to">{{ item.title }}</router-link><p>{{ item.reason }}</p></li></ol>
        </section>
        <section class="result-block" aria-labelledby="review-heading"><div class="block-title"><icon-book /><h3 id="review-heading">待复习</h3></div>
          <ul v-if="reviews.length" class="review-list"><li v-for="review in reviews" :key="review.id"><router-link :to="reviewTarget(review)">{{ review.concept_name }}</router-link><p>{{ reviewReason(review) }}</p></li></ul>
          <template v-else><p>{{ failed.includes('复习提醒') ? '提醒暂时无法读取，请稍后刷新。' : '目前没有待复习提醒。学完一小节后，试着不用提示复述要点。' }}</p><router-link to="/my-results">查看学习复盘 <icon-arrow-right /></router-link></template>
        </section>
        <section class="result-block" aria-labelledby="path-heading"><div class="block-title"><icon-branch /><h3 id="path-heading">我的路径下一步</h3></div>
          <template v-if="lastPath"><h4>{{ lastPath.path_title }}</h4>
            <p v-if="updatedLabel" class="source-note">依据记录更新于 {{ updatedLabel }}</p><p>当前章节：{{ lastPath.current_module_title || '后台未返回当前章节；请在航线中按顺序选择' }}</p><p class="teaching-reason">按已加入航线的顺序推进，先掌握当前章节，再进入后续内容。</p><router-link :to="pathTarget({ learning_path: lastPath.learning_path })">查看{{ names.paths }} <icon-arrow-right /></router-link></template>
          <template v-else><p>{{ failed.includes('学习记录') ? '航线记录暂时无法读取。' : '先选一条适合自己的航线。每个章节都有明确目标，学与练循序推进。' }}</p><router-link to="/learning-paths">选择{{ names.paths }} <icon-arrow-right /></router-link></template>
        </section>
      </div>
    </a-spin>
    <nav class="learning-tools" aria-label="学习工具"><router-link v-for="item in learningLinks" :key="item.key" :to="item.path"><component :is="item.icon" />{{ item.label }}</router-link></nav>
  </section>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { createAccountGuard } from '@/shared/state/accountScope.js'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { names } from '@/shared/navigation/names.js'
import { learningLinks } from '@/shared/navigation/config.js'
import { openTutor } from '@/learning/agent/public.js'
import { guideApi } from './api.js'
import { pathsApi } from '@/learning/paths/api.js'
import PathNextStep from '@/learning/paths/components/PathNextStep.vue'
import { nextStepView } from '@/learning/paths/presentation.js'
import { growthApi } from '@/learning/growth/api.js'
import { readArtifacts } from '@/learning/agent/artifacts.js'
import { asList, orderedPaths, latestConversation, guidePlan, pathTarget, reviewTarget, reviewReason } from './model.js'
const user = useUserStore()
const isStudent = computed(() => user.userInfo?.role === 'student')
const router = useRouter()
const question = ref('')
const paths = ref([])
const reviews = ref([])
const conversation = ref(null)
const failed = ref([])
const loading = ref(true)
let generation = 0
const account = createAccountGuard()
const lastPath = computed(() => paths.value.find(path => !path.completed_at))
// 章节目录只用于读出真实章节标题与先修名称；读取失败时按后台记录的当前章节说明。
const moduleCatalog = ref([])
const moduleFailure = ref('')
const entering = ref(false)
const nextStep = computed(() => nextStepView(lastPath.value, moduleCatalog.value, lastPath.value?.learning_path))
const hasChapterCounts = computed(() => [lastPath.value?.completed_modules, lastPath.value?.total_modules].every(value =>
  (typeof value === 'number' || (typeof value === 'string' && value.trim() !== '')) && Number.isInteger(Number(value)) && Number(value) >= 0
))
const artifacts = ref(null)
const updatedLabel = computed(() => {
  const time = Date.parse(artifacts.value?.loadedAt)
  return Number.isFinite(time) ? new Date(time).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''
})
// 今日计划来自真实航线/复习记录整理；后端没有持久计划接口时明确标为“依据记录整理”。
const plan = computed(() => {
  const artifact = artifacts.value?.plan
  if (artifact?.items?.length) return artifact.items.map(item => ({ to: pathTarget(lastPath.value) || '/learning-paths', title: item.title, reason: item.reason || artifact.summary || '来自教学建议' }))
  return guidePlan(paths.value, reviews.value)
})
const prompts = ['帮我梳理今天的学习目标', '用提问检查我的理解']
const steps = ['评估', '讲解', '练习', '检验']
function ask() { if (question.value.trim()) openTutor(router, { prompt: question.value, userId: user.userInfo?.id }) }
// 调整目标只开启对话；不跳过前置、不自动改写教师航线、不自动标记完成。
function askAdjust() {
  openTutor(router, {
    prompt: '我想调整当前学习航线的目标或节奏。请先根据我的真实进度说明下一步，再等我确认，不要自动开始或标记完成章节。',
    userId: user.userInfo?.id,
  })
}
async function enterNext() {
  const target = nextStep.value?.to
  if (!target || entering.value) return
  entering.value = true
  try {
    await router.push(target)
  } finally {
    entering.value = false
  }
}
async function loadModules(path, version) {
  if (!path) { moduleCatalog.value = []; moduleFailure.value = ''; return }
  try {
    const modules = await pathsApi.modules({ learning_path: path.learning_path })
    if (!account.current() || version !== generation) return
    moduleCatalog.value = asList(modules)
    moduleFailure.value = ''
  } catch {
    if (!account.current() || version !== generation) return
    moduleCatalog.value = []
    moduleFailure.value = '章节列表暂时未能读取。'
  }
}
async function load() {
  const version = ++generation
  loading.value = true
  const [data, artifactData] = await Promise.all([
    Promise.allSettled([guideApi.paths(), guideApi.reviews(), guideApi.conversations()]),
    readArtifacts({ plan: () => growthApi.teachingPlan(), paths: () => pathsApi.my(), reviews: () => guideApi.reviews() }),
  ])
  if (!account.current() || version !== generation) return
  failed.value = data.flatMap((result, index) => result.status === 'rejected' ? [['学习记录', '复习提醒', '导学对话'][index]] : [])
  paths.value = data[0].status === 'fulfilled' ? orderedPaths(data[0].value) : []
  reviews.value = data[1].status === 'fulfilled' ? asList(data[1].value) : []
  conversation.value = data[2].status === 'fulfilled' ? latestConversation(data[2].value) : null
  artifacts.value = artifactData
  await loadModules(lastPath.value && isStudent.value ? lastPath.value : null, version)
  if (!account.current() || version !== generation) return
  loading.value = false
}
onMounted(load)
onBeforeUnmount(() => { generation++; account.dispose(); question.value = ''; moduleCatalog.value = []; paths.value = []; reviews.value = []; artifacts.value = null })
</script>
<style scoped>
.guide-page { width: min(var(--reading-width), calc(100% - var(--page-gutter) * 2)); margin: var(--space-6) auto 0; }
.guide-heading { display: flex; align-items: flex-start; gap: var(--space-2); margin-bottom: var(--space-3); }
.guide-heading h1 { margin-bottom: var(--space-2); }
.guide-heading p { margin-bottom: 0; color: var(--ink-secondary); }
.guide-heading .guide-eyebrow { margin-bottom: var(--space-1); color: var(--agent-accent); font-weight: var(--weight-medium); }
.guide-mark { display: grid; place-items: center; width: var(--space-6); height: var(--space-6); flex-shrink: 0; border-radius: var(--radius-panel); background: var(--agent-soft); color: var(--agent-accent); font-size: var(--text-page); }
.guide-input { padding: var(--space-3); background: var(--surface); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); box-shadow: var(--shadow-raised); }
.guide-input:focus-within { border-color: var(--action); }
.guide-input label { display: block; font-weight: var(--weight-medium); }
.guide-input textarea { width: 100%; resize: vertical; border: 0; background: transparent; color: var(--ink); padding: var(--space-2) 0; font-size: var(--text-body); line-height: var(--leading-body); }
.guide-input textarea::placeholder { color: var(--ink-muted); }
.input-footer { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); }
.input-footer span { color: var(--ink-secondary); font-size: var(--text-caption); }
.guide-shortcuts { display: flex; flex-wrap: wrap; gap: var(--space-1); margin: var(--space-2) 0 var(--space-3); }
.guide-shortcuts button { display: flex; align-items: center; gap: var(--space-1); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); background: transparent; color: var(--ink-secondary); cursor: pointer; }
.guide-shortcuts button:hover { color: var(--action); background: var(--action-soft); }
.teaching-steps { display: flex; align-items: center; gap: var(--space-2); list-style: none; padding: 0; color: var(--ink-secondary); }
.teaching-steps li { display: flex; align-items: center; gap: var(--space-1); }
.teaching-steps li span { color: var(--agent-accent); }
.teaching-steps svg { color: var(--ink-muted); }
.guide-section-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); margin-top: var(--space-5); margin-bottom: var(--space-2); }
.guide-section-heading h2 { margin-bottom: var(--space-1); }
.guide-section-heading p { margin: 0; color: var(--ink-secondary); }
.guide-notice { margin-bottom: var(--space-2); }
.guide-loading { display: block; width: 100%; }
.guide-results { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); background: var(--surface); border-radius: var(--radius-panel); overflow: hidden; }
.result-block { min-width: 0; padding: var(--space-3); border-bottom: var(--stroke) solid var(--line); }
.result-block:nth-child(odd) { border-right: var(--stroke) solid var(--line); }
.result-block:nth-last-child(-n+2) { border-bottom: 0; }
.block-title { display: flex; align-items: center; gap: var(--space-1); margin-bottom: var(--space-2); color: var(--ink-secondary); }
.block-title h3 { margin: 0; color: var(--ink); font-size: var(--text-card); }
.result-block h4 { font-size: var(--text-body); margin-bottom: var(--space-1); }
.result-block p { margin: 0 0 var(--space-2); color: var(--ink-secondary); }
.plan-list { padding-left: var(--space-2); margin: 0; }
.review-list { padding: 0; margin: 0; list-style: none; }
.plan-list p, .review-list p { margin-top: var(--space-1); }
.text-action { border: 0; background: transparent; color: var(--action); padding: 0; cursor: pointer; }
.source-note { color: var(--ink-muted); font-size: var(--text-caption); }
.learning-tools { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-3); margin-top: var(--space-3); }
.learning-tools a { display: flex; align-items: center; gap: var(--space-1); color: var(--ink-secondary); }
.learning-tools a:hover { color: var(--action); }
.is-compact .guide-page { margin-top: var(--space-3); }
.is-compact .guide-results { grid-template-columns: 1fr; }
.is-compact .result-block { border-right: 0; border-bottom: var(--stroke) solid var(--line); }
.is-compact .result-block:last-child { border-bottom: 0; }
.is-compact .input-footer { align-items: flex-end; }
.is-compact .input-footer > span { max-width: 55%; }

/* 学生布局契约；其他角色沿用上方原工作台规则。 */
.guide-page.student-layout { width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin-top: var(--space-8); }
.student-layout .guide-heading { flex-direction: column; align-items: center; gap: var(--space-2); max-width: var(--reading-width); margin: 0 auto var(--space-5); text-align: center; }
.student-layout .guide-heading h1 { font-size: var(--student-hero-size, clamp(var(--text-page), 5vw, calc(var(--text-page) * 1.8))); line-height: var(--leading-tight); letter-spacing: -.025em; }
.student-layout .guide-heading > div > p:last-child { max-width: var(--search-width); margin-inline: auto; }
.student-layout .guide-console { max-width: var(--reading-width); margin-inline: auto; padding: var(--space-4); border: var(--stroke) solid var(--line); border-radius: var(--student-console-radius, var(--radius-panel)); background: var(--surface); box-shadow: var(--shadow-raised); }
.student-layout .guide-console:focus-within { border-color: var(--action); }
.student-layout .guide-input { padding: 0; border: 0; border-radius: 0; box-shadow: none; }
.student-layout .guide-input textarea { box-sizing: border-box; min-height: var(--tile-height); }
.student-layout .guide-shortcuts { margin-block: var(--space-3); }
.student-layout .teaching-steps { justify-content: center; flex-wrap: wrap; gap: var(--space-3); margin-bottom: 0; padding-top: var(--space-3); border-top: var(--stroke) solid var(--line); }
.student-layout .guide-section-heading { margin-top: var(--space-6); justify-content: flex-start; }
.student-layout .guide-results { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-2); background: transparent; overflow: visible; }
.student-layout .result-block:nth-child(n) { border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-raised); padding: var(--space-3); overflow-wrap: anywhere; }
.student-layout .result-block:nth-child(1),
.student-layout .result-block:nth-child(4) { grid-column: span 3; }
.student-layout .learning-tools { gap: var(--space-2); margin-top: var(--space-3); }
.student-layout .learning-tools a { padding: var(--space-2); background: var(--surface); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); }
@supports (background-clip: text) {
  .student-layout .guide-heading h1 { background: var(--student-hero-gradient, linear-gradient(100deg, var(--agent-accent), var(--action))); background-clip: text; color: transparent; }
}
@media (max-width: 1120px) {
  .student-layout .guide-results { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .student-layout .result-block:nth-child(1),
  .student-layout .result-block:nth-child(4) { grid-column: auto; }
}
@media (max-width: 768px) {
  .guide-page.student-layout { margin-top: var(--space-5); }
  .student-layout .guide-console { padding: var(--space-3); }
  .student-layout .guide-results { grid-template-columns: minmax(0, 1fr); }
  .student-layout .guide-section-heading { align-items: flex-start; margin-top: var(--space-4); }
  .guest-layout .guide-results, .student-layout .guide-results { grid-template-columns: minmax(0, 1fr); }
  .guest-layout .input-footer, .student-layout .input-footer { flex-direction: column; align-items: stretch; }
  .guest-layout .input-footer > span, .student-layout .input-footer > span { max-width: 100%; }
  .guest-layout .input-footer :deep(.arco-btn), .student-layout .input-footer :deep(.arco-btn) { width: 100%; min-height: var(--space-6); }
  .guest-layout .guide-shortcuts button, .student-layout .guide-shortcuts button { min-height: var(--control-height); max-width: 100%; overflow-wrap: anywhere; }
  .guest-layout .guide-section-heading > div, .student-layout .guide-section-heading > div { min-width: 0; }
  .student-layout .teaching-steps { gap: var(--space-2); }
}
</style>
