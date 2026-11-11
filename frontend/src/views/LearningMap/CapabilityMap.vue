<template>
  <div class="capability-page">
    <div class="page-header">
      <div class="header-copy">
        <span class="eyebrow">双主线 · {{ names.capability }}</span>
        <h1>{{ names.capability }}</h1>
        <p class="subtitle">
          选一项能力，看看要练成什么、需要哪些基础，以及最近的练习结果，再安排下一步。
        </p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn btn-secondary" :disabled="loading" @click="loadAll">
          <AppIcon name="bi-arrow-clockwise" /> 刷新
        </button>
        <router-link v-if="canManageCatalog" to="/teacher/capability-map" class="btn btn-secondary">
          <AppIcon name="bi-sliders" /> 目录审核
        </router-link>
      </div>
    </div>

    <KnowledgeConceptSource v-if="$route.query.concept" />

    <div v-if="loading" class="state-box" aria-live="polite">
      <div class="spinner"></div>
      <p>正在读取{{ names.capability }}…</p>
    </div>

    <div v-else-if="error" class="state-box state-error" role="alert">
      <AppIcon name="bi-exclamation-octagon" />
      <h2>{{ errorTitle }}</h2>
      <p>{{ error }}</p>
      <p v-if="errorCode === 'catalog_not_published'" class="hint">
        课程目录尚未开放，请等待教师发布后再查看。
      </p>
      <button type="button" class="btn btn-secondary" @click="loadAll">重试</button>
    </div>

    <template v-else>
      <div v-if="diagnosisResult" class="diagnosis-banner">
        <div>
          <strong>诊断已完成</strong>
          <span>已回答 {{ diagnosisResult.answeredCount }} / {{ diagnosisResult.questionCount }} 题；{{ diagnosisResult.note }}</span>
          <ul>
            <li v-for="entry in diagnosisResult.items" :key="entry.title">
              {{ entry.title }}：{{ entry.label }}
            </li>
          </ul>
        </div>
        <button type="button" class="icon-btn" aria-label="关闭诊断结果" @click="diagnosisResult = null">
          <AppIcon name="bi-x-lg" />
        </button>
      </div>

      <div class="bento">
        <div class="bento-main">
          <CapabilityExplorer
            :catalog="catalog"
            :summary="summary"
            :tracks="tracks"
            :selected-key="selectedKey"
            @select="selectCapability"
            @diagnose="openDiagnosis"
          />
        </div>

        <aside class="bento-side">
          <CapabilityDetail :capability="selectedCapability">
            <div class="related-toolbar">
              <p class="related-note">按主线查看推荐任务，可直接领取。</p>
              <label class="track-filter">
                <span>主线</span>
                <select v-model="goalTrack" class="select" @change="loadRecommendations">
                  <option value="both">双主线</option>
                  <option value="data">数据安全</option>
                  <option value="network">网络安全</option>
                </select>
              </label>
            </div>
            <CapabilityTaskList
              :items="recommendationList"
              :loading="recommendationsLoading"
              :error="recommendationsError"
              :claiming-id="claimingId"
              :claim-message="claimFeedback.message"
              :claim-detail="claimFeedback.detail"
              :claim-error="claimFeedback.error"
              @claim="claim"
              @diagnose="openDiagnosis"
              @retry="loadRecommendations"
            />
            <p v-if="recommendationUpdated !== '—'" class="rec-foot">推荐更新于 {{ recommendationUpdated }}</p>
          </CapabilityDetail>

          <section v-if="!selectedCapability" class="panel" aria-labelledby="rec-heading">
            <div class="panel-head">
              <h2 id="rec-heading">下一步推荐</h2>
              <label class="track-filter">
                <span>主线</span>
                <select v-model="goalTrack" class="select" @change="loadRecommendations">
                  <option value="both">双主线</option>
                  <option value="data">数据安全</option>
                  <option value="network">网络安全</option>
                </select>
              </label>
            </div>
            <CapabilityTaskList
              :items="recommendationList"
              :loading="recommendationsLoading"
              :error="recommendationsError"
              :claiming-id="claimingId"
              :claim-message="claimFeedback.message"
              :claim-detail="claimFeedback.detail"
              :claim-error="claimFeedback.error"
              @claim="claim"
              @diagnose="openDiagnosis"
              @retry="loadRecommendations"
            />
          </section>

          <section class="panel panel-muted" aria-labelledby="rules-heading">
            <h2 id="rules-heading">状态怎么算</h2>
            <ul class="rule-list">
              <li>自己独立完成并通过，记为“独立通过”。</li>
              <li>看过提示或讲解后才通过，记为“提示后通过”，需要换一道新题再做一次。</li>
              <li>没有通过就继续练；这次结果不会把之前的记录抹掉。</li>
              <li>还没做、还没批完或环境出问题时会单独说明，不会显示成没通过。</li>
              <li>“独立”指这次练习中没有看过提示或讲解。</li>
            </ul>
            <button type="button" class="panel-link text-action" @click="openHistory">查看学习历史 →</button>
          </section>
        </aside>
      </div>
    </template>

    <details :id="CAPABILITY_HISTORY" ref="historySection" class="history-section" :open="historyOpen" @toggle="historyOpen = $event.target.open">
      <summary>学习历史 <span>重看能力状态与变化原因</span></summary>
      <ChangeLog v-if="historyVisited" v-show="historyOpen" />
    </details>

    <div v-if="showDiagnosis" class="modal-mask" @click.self="closeDiagnosis">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="diagnosis-title" @keydown.esc="closeDiagnosis">
        <div class="modal-head">
          <div>
            <span class="eyebrow">基础诊断</span>
            <h2 id="diagnosis-title">{{ diagnosisTrack === 'data' ? '数据安全' : '网络安全' }}</h2>
          </div>
          <button type="button" class="icon-btn" aria-label="关闭诊断" @click="closeDiagnosis"><AppIcon name="bi-x-lg" /></button>
        </div>
        <p class="modal-note">
          诊断只用来安排学习顺序，不代表已经学会；没有作答的题不会算作不会。
        </p>
        <p v-if="questionsLoading" class="state-note" role="status">正在加载诊断题…</p>
        <p v-else-if="questionsError" class="state-note is-error" role="alert">
          {{ questionsError }}
          <button type="button" class="text-action" @click="openDiagnosis(diagnosisTrack)">重试</button>
        </p>
        <div v-else-if="!questionList.length" class="empty-block">
          <p>该主线暂无可用的诊断题，请等待课程补充。</p>
        </div>
        <form v-else @submit.prevent="submitDiagnosis">
          <div v-for="question in questionList" :key="question.key" class="question">
            <span class="question-meta">{{ question.capabilityTitle }} · {{ question.dimensionLabel }}</span>
            <p class="question-prompt">{{ question.prompt }}</p>
            <label v-for="option in question.options" :key="option.key" class="option">
              <input
                type="radio"
                :name="question.key"
                :value="option.key"
                v-model="answers[question.key]"
              />
              <span>{{ option.key }}. {{ option.label }}</span>
            </label>
          </div>
          <p v-if="diagnosisError" class="state-note is-error" role="alert">{{ diagnosisError }}</p>
          <div class="modal-actions">
            <button type="button" class="btn btn-secondary" @click="closeDiagnosis">取消</button>
            <button type="submit" class="btn btn-primary" :disabled="diagnosisSubmitting">
              {{ diagnosisSubmitting ? '提交中…' : '提交诊断' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import ChangeLog from './ChangeLog.vue'
import { CAPABILITY_HISTORY, wantsCapabilityHistory } from '@/learning/shadowRoutes.js'
import { names } from '@/shared/navigation/names'
import service from '@/api'
import { useUserStore } from '@/store/user'
import KnowledgeConceptSource from '@/learningKnowledge/KnowledgeConceptSource.vue'
import CapabilityExplorer from '@/learning/capability/components/CapabilityExplorer.vue'
import CapabilityDetail from '@/learning/capability/components/CapabilityDetail.vue'
import CapabilityTaskList from '@/learning/capability/components/CapabilityTaskList.vue'
import {
  allCapabilities, catalogSummary, claimResult, diagnosisView, errorText, formatDateTime, questionView,
  recommendationViews, trackViews,
} from '@/learning/capability/presentation.js'

const userStore = useUserStore()
const route = useRoute()
const historyOpen = ref(false)
const historyVisited = ref(false)
const historySection = ref(null)
watch(historyOpen, open => { if (open) historyVisited.value = true }, { flush: 'sync' })
async function openHistory() {
  historyOpen.value = true
  await nextTick()
  historySection.value?.scrollIntoView({ block: 'start', behavior: 'auto' })
}
watch(() => [route.query.history, route.hash], () => {
  if (wantsCapabilityHistory(route)) void openHistory()
}, { immediate: true })
const loading = ref(true)
const error = ref('')
const errorCode = ref('')
const map = ref(null)

const recommendations = ref(null)
const recommendationsLoading = ref(false)
const recommendationsError = ref('')
const goalTrack = ref('both')
const claimingId = ref(null)
const claimFeedback = reactive({ message: '', detail: '', error: false })

const selectedKey = ref('')
const showDiagnosis = ref(false)
const diagnosisTrack = ref('data')
const questions = ref([])
const questionsLoading = ref(false)
const questionsError = ref('')
const answers = reactive({})
const diagnosisSubmitting = ref(false)
const diagnosisError = ref('')
const diagnosisResult = ref(null)

const canManageCatalog = computed(() => Boolean(userStore.userInfo?.can_manage_catalog))
const errorTitle = computed(() => (errorCode.value === 'catalog_not_published' ? '目录尚未开放' : '读取失败'))

const catalog = computed(() => catalogSummary(map.value))
const tracks = computed(() => trackViews(map.value))
const summary = computed(() => catalog.value)
const capabilities = computed(() => allCapabilities(map.value))
const selectedCapability = computed(() => capabilities.value.find(item => item.key === selectedKey.value) || null)

const recommendationList = computed(() => recommendationViews(recommendations.value, goalTrack.value))
const recommendationUpdated = computed(() => formatDateTime(recommendations.value?.generated_at))
// 学生端任务推荐不带主线标签；这里不按标题/编号猜主线，只呈现当前筛选下的整组推荐。
const trackRecommendations = computed(() => recommendationList.value)

const questionList = computed(() => questions.value.map(questionView))

function selectCapability(key) {
  selectedKey.value = key
  if (window.innerWidth < 1120) {
    document.getElementById('detail-heading')?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }
}

async function loadAll() {
  loading.value = true
  error.value = ''
  errorCode.value = ''
  try {
    map.value = await service.learningMap.myMap()
    const visible = allCapabilities(map.value)
    if (!visible.some(item => item.key === selectedKey.value)) {
      selectedKey.value = visible[0]?.key || ''
    }
    await loadRecommendations()
  } catch (err) {
    error.value = errorText(err)
    errorCode.value = err?.response?.data?.code || err?.response?.data?.detail?.code || ''
    map.value = null
  } finally {
    loading.value = false
  }
}

async function loadRecommendations() {
  if (!map.value) return
  recommendationsLoading.value = true
  recommendationsError.value = ''
  claimFeedback.message = ''
  claimFeedback.detail = ''
  claimFeedback.error = false
  try {
    recommendations.value = await service.learningMap.myRecommendations({ goal_track: goalTrack.value })
  } catch (err) {
    recommendations.value = null
    recommendationsError.value = errorText(err)
  } finally {
    recommendationsLoading.value = false
  }
}

function resetDiagnosisAnswers() {
  for (const key of Object.keys(answers)) delete answers[key]
}

function closeDiagnosis() {
  showDiagnosis.value = false
  diagnosisError.value = ''
}

async function openDiagnosis(track) {
  diagnosisTrack.value = track === 'network' ? 'network' : 'data'
  showDiagnosis.value = true
  diagnosisError.value = ''
  questions.value = []
  questionsError.value = ''
  questionsLoading.value = true
  resetDiagnosisAnswers()
  try {
    const payload = await service.learningMap.diagnosticQuestions({ track: diagnosisTrack.value })
    questions.value = Array.isArray(payload?.questions) ? payload.questions : []
  } catch (err) {
    questionsError.value = errorText(err)
  } finally {
    questionsLoading.value = false
  }
}

async function submitDiagnosis() {
  if (diagnosisSubmitting.value) return
  diagnosisSubmitting.value = true
  diagnosisError.value = ''
  try {
    const payload = await service.learningMap.submitDiagnosis({
      goal_track: diagnosisTrack.value,
      answers: { ...answers },
    })
    diagnosisResult.value = diagnosisView(payload.result)
    showDiagnosis.value = false
    await loadAll()
  } catch (err) {
    diagnosisError.value = errorText(err)
  } finally {
    diagnosisSubmitting.value = false
  }
}

// 领取使用服务器返回的真实 attempt；没有工作面时如实说明，不跳证据页、不假定 DataLab。
async function claim(item) {
  if (!item?.task || claimingId.value !== null) return
  claimingId.value = item.task.id
  claimFeedback.message = ''
  claimFeedback.detail = ''
  claimFeedback.error = false
  try {
    const payload = await service.learningMap.claimTask(item.task.id)
    const result = claimResult(payload)
    claimFeedback.message = result.ok ? result.message : result.reason
    claimFeedback.detail = result.ok ? result.reason : ''
    claimFeedback.error = !result.ok
  } catch (err) {
    claimFeedback.message = `领取未完成：${errorText(err)}`
    claimFeedback.error = true
  } finally {
    claimingId.value = null
  }
}

function onKeydown(event) {
  if (event.key === 'Escape' && showDiagnosis.value) closeDiagnosis()
}
onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  loadAll()
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.history-section { margin-top: var(--space-3); padding: var(--space-2); border-top: var(--stroke) solid var(--line); scroll-margin-top: calc(var(--header-height) + var(--space-3)); }
.history-section summary { min-height: var(--control-height); cursor: pointer; font-weight: var(--weight-strong); }
.history-section summary span { margin-left: var(--space-1); color: var(--ink-muted); font-size: var(--text-caption); font-weight: var(--weight-normal); }
.history-section summary:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.capability-page {
  width: min(var(--page-width), calc(100% - var(--page-gutter) * 2));
  margin: 0 auto;
  padding: var(--space-3) 0 var(--space-8);
  color: var(--ink);
}
.page-header {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  align-items: flex-end;
  border-bottom: calc(var(--stroke) * 2) solid var(--line-strong);
  padding-bottom: var(--space-3);
  margin-bottom: var(--space-3);
}
.eyebrow {
  display: inline-block;
  font-size: var(--text-caption);
  letter-spacing: .18em;
  text-transform: uppercase;
  color: var(--action);
  font-weight: var(--weight-strong);
  margin-bottom: var(--space-1);
}
h1 {
  font-family: var(--font-family);
  font-size: clamp(var(--text-section), 4vw, var(--text-page));
  line-height: 1.1;
  letter-spacing: -.02em;
  margin: 0;
}
.subtitle {
  max-width: var(--reading-width);
  color: var(--ink-secondary);
  margin-top: var(--space-1);
  font-size: var(--text-caption);
}
.header-actions { display: flex; flex-wrap: wrap; gap: var(--space-1); flex-shrink: 0; }
.btn {
  display: inline-flex;
  align-items: center;
  gap: calc(var(--space-1) / 2);
  min-height: var(--control-height);
  padding: 0 var(--space-2);
  border: var(--stroke) solid var(--line-strong);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink);
  font: inherit;
  font-size: var(--text-caption);
  font-weight: var(--weight-strong);
  cursor: pointer;
}
.btn:hover:not(:disabled) { border-color: var(--action); color: var(--action); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--action); border-color: var(--action); color: var(--on-action); }
.btn-primary:hover:not(:disabled) { color: var(--on-action); }
.btn-secondary { background: var(--surface); }
.btn-small { min-height: calc(var(--control-height) - var(--space-1)); padding: 0 var(--space-1); font-size: var(--text-caption); }
.diagnosis-banner {
  display: flex; justify-content: space-between; gap: var(--space-2); align-items: flex-start;
  margin-bottom: var(--space-2); padding: var(--space-2);
  border: var(--stroke) solid var(--positive); border-left: calc(var(--space-1) / 2) solid var(--positive);
  border-radius: var(--radius-control); background: var(--positive-soft);
  font-size: var(--text-caption); color: var(--ink-secondary);
}
.diagnosis-banner strong { display: block; color: var(--positive); margin-bottom: calc(var(--space-1) / 2); }
.diagnosis-banner ul { display: flex; flex-wrap: wrap; gap: calc(var(--space-1) / 2) var(--space-2); margin: calc(var(--space-1) / 2) 0 0; padding: 0; list-style: none; }
.bento { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(20rem, .85fr); gap: var(--space-3); align-items: start; }
.bento-main { min-width: 0; }
.bento-side { display: grid; gap: var(--space-2); min-width: 0; }
.panel { padding: var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-raised); }
.panel-muted { box-shadow: none; border-color: var(--line); }
.panel-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--space-1); }
.panel h2 { margin: 0; font-size: var(--text-card); }
.panel-note { margin: var(--space-1) 0; color: var(--ink-muted); font-size: var(--text-caption); }
.track-filter { display: inline-flex; align-items: center; gap: var(--space-1); color: var(--ink-muted); font-size: var(--text-caption); }
.select { min-height: var(--control-height); padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); }
.state-note { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.state-note.is-error { background: var(--negative-soft); color: var(--negative); }
.text-action { margin-left: var(--space-1); padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.related-toolbar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: var(--space-1) var(--space-2); }
.related-note { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.rec-foot { margin: var(--space-1) 0 0; color: var(--ink-muted); font-size: var(--text-caption); }
.rule-list { display: flex; flex-direction: column; gap: var(--space-1); margin: var(--space-1) 0 0; padding: 0; list-style: none; color: var(--ink-secondary); font-size: var(--text-caption); }
.rule-list li { position: relative; padding-left: var(--space-1); }
.rule-list li::before { content: "—"; position: absolute; left: 0; color: var(--action); }
.panel-link { display: inline-flex; align-items: center; min-height: var(--control-height); margin-top: var(--space-1); color: var(--action); font-size: var(--text-caption); font-weight: var(--weight-strong); }
.empty-block { padding: var(--space-3) var(--space-1); text-align: center; color: var(--ink-muted); }
.state-box { padding: var(--space-8) var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); text-align: center; }
.state-box .app-icon { font-size: var(--text-page); color: var(--warning); }
.state-error h2 { margin: var(--space-1) 0 calc(var(--space-1) / 2); font-size: var(--text-card); }
.hint { margin-top: var(--space-1); color: var(--ink-muted); font-size: var(--text-caption); }
.spinner { width: var(--space-3); height: var(--space-3); margin: 0 auto var(--space-1); border: var(--focus-width) solid var(--line); border-top-color: var(--action); border-radius: 50%; animation: spin var(--motion-loop) linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) {
  .spinner { animation: none; border-top-color: var(--action); }
}
.modal-mask { position: fixed; inset: 0; z-index: var(--z-overlay); display: flex; align-items: center; justify-content: center; padding: var(--space-2); background: var(--overlay); }
.modal { width: min(var(--search-width), 100%); max-height: 88vh; overflow: auto; padding: var(--space-3); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-overlay); }
.modal-head { display: flex; justify-content: space-between; gap: var(--space-1); padding-bottom: var(--space-1); margin-bottom: var(--space-1); border-bottom: var(--stroke) solid var(--line); }
.modal-head h2 { margin: 0; font-size: var(--text-section); }
.icon-btn { display: inline-flex; align-items: center; justify-content: center; min-width: var(--control-height); min-height: var(--control-height); border: 0; background: transparent; color: var(--ink); font-size: var(--text-card); cursor: pointer; }
.modal-note { margin: 0 0 var(--space-1); color: var(--ink-muted); font-size: var(--text-caption); }
.question { padding: var(--space-2) 0; border-top: var(--stroke) solid var(--line); }
.question-meta { color: var(--action); font-size: var(--text-caption); font-weight: var(--weight-strong); }
.question-prompt { margin: calc(var(--space-1) / 2) 0 var(--space-1); font-size: var(--text-caption); }
.option { display: flex; align-items: flex-start; gap: var(--space-1); min-height: var(--control-height); padding: calc(var(--space-1) / 2) 0; color: var(--ink-secondary); font-size: var(--text-caption); cursor: pointer; }
.modal-actions { display: flex; justify-content: flex-end; gap: var(--space-1); margin-top: var(--space-2); }
.btn:focus-visible, .text-action:focus-visible, .panel-link:focus-visible, .icon-btn:focus-visible, .select:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
@media (max-width: 1120px) {
  .bento { grid-template-columns: 1fr; }
  .page-header { flex-direction: column; align-items: flex-start; }
}
@media (max-width: 480px) {
  .capability-page { width: calc(100% - var(--space-3) * 2); }
  .panel, .modal { padding: var(--space-2); }
}
</style>
