<template>
  <div class="growth-view">
    <div class="growth-inner">
      <section id="growth-overview" class="growth-block" aria-label="成长总览">
        <details class="length-disclosure" :open="expandedSections['growth-overview']" @toggle="onSectionToggle('growth-overview', $event)">
          <summary class="length-disclosure__summary">成长总览</summary>
          <div class="length-disclosure__body">
            <GrowthSummary
              :display-name="displayName"
              :profile="profile"
              :persona="persona"
              :progress-report="progressReport"
              :submission-stats="submissionStats"
              :recommendations="recommendations"
              :exam-count="examCount"
            />
          </div>
        </details>
      </section>

      <nav class="section-nav" aria-label="成长图谱分区">
        <a v-for="section in sections" :key="section.id" :href="`#${section.id}`" :class="{ active: section.id === activeSection }" @click.prevent="goSection(section.id)">{{ section.label }}</a>
      </nav>

      <div class="section-stack">
        <section id="growth-mastery" class="growth-block" aria-label="掌握与方向">
          <details class="length-disclosure" :open="expandedSections['growth-mastery']" @toggle="onSectionToggle('growth-mastery', $event)">
            <summary class="length-disclosure__summary">掌握与方向</summary>
            <div class="length-disclosure__body">
              <MasteryOverview :directions="directions" :growth="growth" :teaching-plan="teachingPlan" />
            </div>
          </details>
        </section>
        <section id="growth-activity" class="growth-block" aria-label="学习分析">
          <details class="length-disclosure" :open="expandedSections['growth-activity']" @toggle="onSectionToggle('growth-activity', $event)">
            <summary class="length-disclosure__summary">学习分析</summary>
            <div class="length-disclosure__body">
              <LearningActivity :initial-days="windowDays" @window-change="onWindowChange" />
            </div>
          </details>
        </section>
        <section id="growth-report" class="growth-block" aria-label="学习结论与报告">
          <details class="length-disclosure" :open="expandedSections['growth-report']" @toggle="onSectionToggle('growth-report', $event)">
            <summary class="length-disclosure__summary">学习结论与报告</summary>
            <div class="length-disclosure__body">
              <LearningReport
                :teaching-plan="teachingPlan"
                :teaching-loading="teachingLoading"
                :teaching-error="teachingError"
              />
            </div>
          </details>
        </section>
        <section id="growth-review" class="growth-block" aria-label="待复习">
          <details class="length-disclosure" :open="expandedSections['growth-review']" @toggle="onSectionToggle('growth-review', $event)">
            <summary class="length-disclosure__summary">待复习</summary>
            <div class="length-disclosure__body">
              <ReviewReminders />
            </div>
          </details>
        </section>
        <section id="growth-recommend" class="growth-block" aria-label="学习推荐">
          <details class="length-disclosure" :open="expandedSections['growth-recommend']" @toggle="onSectionToggle('growth-recommend', $event)">
            <summary class="length-disclosure__summary">学习推荐</summary>
            <div class="length-disclosure__body">
              <LearningRecommendations @loaded="recommendations = $event" />
            </div>
          </details>
        </section>
        <section id="growth-results" class="growth-block" aria-label="测评记录与复盘">
          <details class="length-disclosure" :open="expandedSections['growth-results']" @toggle="onSectionToggle('growth-results', $event)">
            <summary class="length-disclosure__summary">测评记录与复盘</summary>
            <div class="length-disclosure__body">
              <header class="results-head">
                <h2>测评记录与复盘</h2>
                <router-link :to="recordsPath" class="text-link">全部测评记录 →</router-link>
              </header>
              <div v-if="examLoading" class="state-note" role="status">正在读取最近测评…</div>
              <p v-else-if="examError" class="state-note is-error" role="alert">{{ examError }}</p>
              <ul v-else-if="recentExams.length" class="exam-list">
                <li v-for="record in recentExams" :key="record.id">
                  <router-link v-if="record.href" :to="record.href" class="exam-item">
                    <span class="exam-type">{{ record.typeLabel }}</span>
                    <span class="exam-title">{{ record.title }}</span>
                    <span class="exam-date">{{ formatDate(record.date) }}</span>
                    <span class="exam-score" :class="{ passed: record.status === 'completed' && record.passed === true, failed: record.status === 'completed' && record.passed === false }">{{ record.score === null ? '—' : `${record.score}分` }}</span>
                    <span class="exam-status">{{ record.statusLabel }}</span>
                  </router-link>
                </li>
              </ul>
              <p v-else class="state-note">还没有测评记录；完成一次测评后会在这里显示摘要。</p>
              <p class="results-note">这里显示最近测评摘要；逐题结果请进入测评记录查看。逐份提交的复盘、复测与复核在下方。</p>
              <div class="results-actions">
                <router-link :to="recordsPath" class="text-link">测评记录</router-link>
                <router-link to="/exam-center" class="text-link">试炼中心</router-link>
              </div>

              <div class="results-stack">
                <RetestList ref="retestList" />
                <SubmissionReview ref="submissionReview" @card-saved="onCardSaved" />
              </div>
            </div>
          </details>
        </section>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { createAccountGuard } from '@/shared/state/accountScope.js'
import { useRoute, useRouter } from 'vue-router'
import api from '@/api'
import { useUserStore } from '@/store/user'
import { growthDestination } from '@/shared/navigation/phase2.js'
import '@/shared/layout/disclosure.css'
import { RECORDS_PATH, examsApi, recordView } from '@/learning/exams/api.js'
import { formatDate } from './presentation.js'
import { growthSectionQuery, growthSectionTarget, growthWindow } from './sections.js'
import GrowthSummary from './components/GrowthSummary.vue'
import MasteryOverview from './components/MasteryOverview.vue'
import LearningActivity from './components/LearningActivity.vue'
import LearningReport from './components/LearningReport.vue'
import ReviewReminders from './components/ReviewReminders.vue'
import LearningRecommendations from './components/LearningRecommendations.vue'
import RetestList from './components/RetestList.vue'
import SubmissionReview from './components/SubmissionReview.vue'

const route = useRoute()
const account = createAccountGuard()
let active = true
const ownsRoute = () => active && (!route.path || route.name === 'StudentDashboard' || route.path === '/dashboard')
const router = useRouter()
const userStore = useUserStore()
const recordsPath = RECORDS_PATH
const retestList = ref(null)
const submissionReview = ref(null)
const sections = [
  { id: 'growth-overview', label: '总览' },
  { id: 'growth-mastery', label: '掌握与方向' },
  { id: 'growth-activity', label: '学习分析' },
  { id: 'growth-report', label: '结论与报告' },
  { id: 'growth-review', label: '待复习' },
  { id: 'growth-recommend', label: '学习推荐' },
  { id: 'growth-results', label: '结果与复盘' },
]
const activeSection = ref(sections[0].id)
const defaultExpandedSections = () => Object.fromEntries(sections.map(section => [section.id, section.id === 'growth-overview']))
const expandedSections = ref(defaultExpandedSections())

// details 只隐藏正文；子组件始终挂载，保留已读取记录、输入草稿和复盘刷新引用。
function onSectionToggle(id, event) {
  expandedSections.value[id] = event.currentTarget.open
  if (event.currentTarget.open) {
    nextTick(() => {
      if (expandedSections.value[id] && typeof window !== 'undefined' && typeof window.Event === 'function') {
        window.dispatchEvent(new window.Event('resize'))
      }
    })
  }
}

function openSection(id) {
  if (!sections.some(section => section.id === id)) return false
  expandedSections.value[id] = true
  activeSection.value = id
  return true
}

const windowDays = ref(growthWindow(route?.query?.window) || 7)
const profile = ref(null)
const persona = ref(null)
const growth = ref(null)
const directions = ref([])
const teachingPlan = ref(null)
const teachingLoading = ref(true)
const teachingError = ref('')
const progressReport = ref(null)
const submissionStats = ref(null)
const recommendations = ref([])
const recentExams = ref([])
const examCount = ref(null)
const examLoading = ref(true)
const examError = ref('')

const displayName = computed(() => userStore.userName || userStore.userInfo?.nickname || '同学')

// 兼容旧入口：/analytics 落“学习分析”区，/my-results 落“结果与复盘”区；
// 参数名沿用 shared/navigation/phase2.js 的四个真实分区，不再另起一套看板。
const sectionFromQuery = query => growthSectionTarget(query?.section)

function scrollToSection(id) {
  if (!account.current() || !ownsRoute()) return
  const element = typeof document !== 'undefined' ? document.getElementById(id) : null
  element?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
}

function goSection(id) {
  if (!openSection(id)) return
  const section = growthSectionQuery(id)
  if (section) {
    const query = section === 'activity' ? { window: windowDays.value } : {}
    router.replace(growthDestination(section, query))
  } else {
    router.replace({ path: '/dashboard', hash: `#${id}` })
  }
  nextTick(() => scrollToSection(id))
}

// 活动窗口属于 URL 契约的一部分：刷新或分享后仍回到同一窗口。
function onWindowChange(days) {
  if (!account.current() || !ownsRoute()) return
  windowDays.value = growthWindow(days) || 7
  router.replace(growthDestination('activity', { window: days }))
}

async function loadProfile() {
  try {
    const data = await api.studentProfile.get()
    if (!account.current()) return false
    if (data && data.onboarding_completed === false) {
      router.replace('/profile/setup')
      return false
    }
    profile.value = data
  } catch {
    if (!account.current()) return false
    profile.value = null
  }
  return true
}

async function loadIndependent() {
  const settle = async (request, assign) => {
    try { const value = await request(); if (account.current()) assign(value) } catch { if (account.current()) assign(null) }
  }
  await Promise.all([
    settle(() => api.studentProfile.persona(), value => { persona.value = value }),
    settle(() => api.studentProfile.growth(), value => { growth.value = value }),
    settle(() => api.studentProfile.learningDirections(), value => { directions.value = Array.isArray(value) ? value : [] }),
    // 教学方案接口每次 GET 都会重算，只允许请求一次。
    (async () => {
      try {
        const plan = await api.analytics.teachingPlan()
        if (!account.current()) return
        teachingPlan.value = plan
        teachingError.value = ''
      } catch {
        if (!account.current()) return
        teachingPlan.value = null
        teachingError.value = '教学方案暂时未能读取，请重试。'
      } finally {
        if (account.current()) teachingLoading.value = false
      }
    })(),
    settle(() => api.analytics.progressReport(), value => { progressReport.value = value }),
    settle(() => api.submission.stats(), value => { submissionStats.value = value }),
  ])
}

async function loadExams() {
  if (!account.current()) return
  examLoading.value = true
  examError.value = ''
  try {
    const history = await examsApi.myHistory()
    if (!account.current()) return
    const records = Array.isArray(history?.records) ? history.records : []
    examCount.value = records.length
    recentExams.value = records.slice(0, 5).map(recordView)
  } catch {
    if (!account.current()) return
    recentExams.value = []
    examCount.value = null
    examError.value = '最近测评暂时未能读取；这不代表没有测评记录。'
  } finally {
    if (account.current()) examLoading.value = false
  }
}

function applyHash() {
  if (!account.current() || !ownsRoute()) return
  const fromQuery = sectionFromQuery(route?.query)
  const hash = (route?.hash ?? (typeof window !== 'undefined' ? window.location.hash : '')).replace(/^#/, '')
  const target = sections.some(section => section.id === hash) ? hash : fromQuery
  if (!target || !openSection(target)) return
  if (target === 'growth-overview') return
  nextTick(() => scrollToSection(target))
}

// 完成复盘后后台可能新增复测安排；刷新复测清单即可读回，不自行拼造任务。
function onCardSaved(result) {
  if (result?.completed && !result?.failed) retestList.value?.load?.()
}

watch(() => [route?.path, route?.query?.section, route?.query?.window, route?.hash], () => {
  if (!ownsRoute() || !account.current()) return
  if (Object.hasOwn(route.query || {}, 'window')) windowDays.value = growthWindow(route.query.window) || 7
  applyHash()
})
onActivated(() => { active = true; if (Object.hasOwn(route.query || {}, 'window')) windowDays.value = growthWindow(route.query.window) || 7; applyHash() })
onDeactivated(() => { active = false })
onBeforeUnmount(() => { account.dispose(); profile.value = null; persona.value = null; teachingPlan.value = null; recentExams.value = [] })
// App 的 account:role 路由 key 负责账号数据隔离；本地展开选择不跨账号继承。
watch(() => [userStore.userInfo?.id, userStore.userInfo?.role], () => {
  expandedSections.value = defaultExpandedSections()
  activeSection.value = sections[0].id
}, { flush: 'sync' })

onMounted(async () => {
  const ready = await loadProfile()
  if (!ready) return
  await Promise.all([loadIndependent(), loadExams()])
  applyHash()
})
defineExpose({ loadIndependent, loadExams, applyHash, goSection, profile, persona, growth, directions, recommendations, recentExams, activeSection, expandedSections })
</script>
<style scoped>
.growth-view { min-height: calc(100vh - var(--space-8)); padding: var(--space-3) 0 var(--space-6); background: var(--surface-page); color: var(--ink); }
.growth-inner { width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: 0 auto; display: grid; gap: var(--space-2); }
.section-nav { position: sticky; top: 0; z-index: 1; display: flex; flex-wrap: wrap; gap: var(--space-1); padding: var(--space-1) 0; background: var(--surface-page); }
.section-nav a { display: inline-flex; align-items: center; min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); color: var(--ink-secondary); font-size: var(--text-caption); text-decoration: none; }
.section-nav a.active { border-color: var(--action); color: var(--action); }
.section-stack { display: grid; gap: var(--space-4); }
.growth-block { scroll-margin-top: var(--space-4); }
.results-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-1) var(--space-2); margin-bottom: var(--space-2); }
.results-head h2 { margin: 0; font-size: var(--text-section); }
.state-note { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); }
.state-note.is-error { background: var(--negative-soft); color: var(--negative); }
.exam-list { display: grid; gap: var(--space-1); margin: 0 0 var(--space-2); padding: 0; list-style: none; }
.exam-item { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto auto; align-items: center; gap: var(--space-2); padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); text-decoration: none; }
.exam-type, .exam-status { padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.exam-title { font-weight: var(--weight-strong); overflow-wrap: anywhere; }
.exam-date { color: var(--ink-secondary); font-size: var(--text-caption); }
.exam-score { font-weight: var(--weight-strong); }
.exam-score.passed { color: var(--positive); }
.exam-score.failed { color: var(--negative); }
.results-note { margin: 0 0 var(--space-1); color: var(--ink-muted); font-size: var(--text-caption); }
.results-actions { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.results-stack { display: grid; gap: var(--space-4); margin-top: var(--space-4); }
.text-link { display: inline-flex; align-items: center; min-height: var(--control-height); color: var(--action); font-size: var(--text-caption); text-decoration: none; }
.is-compact .exam-item { grid-template-columns: minmax(0, 1fr) auto; }
.is-compact .exam-date { grid-column: 1; }
.section-nav a:focus-visible, .exam-item:focus-visible, .text-link:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
@media (max-width: 768px) {
  .section-nav { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); position: static; }
  .section-nav a { justify-content: center; min-width: 0; padding-inline: var(--space-1); }
  .exam-item { grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-1); }
  .exam-title { grid-column: 1 / -1; }
  .exam-date { grid-column: 1; }
}
@media (prefers-reduced-motion: reduce) { .section-nav a { scroll-behavior: auto; } }
</style>
