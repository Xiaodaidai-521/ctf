<template>
  <div class="capability-page">
    <div class="page-header">
      <div class="header-copy">
        <span class="eyebrow">双主线 · 能力地图</span>
        <h1>能力地图与下一步</h1>
        <p class="subtitle">
          用平台核验过的任务结果更新能力状态，并按当前证据安排下一步。
        </p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="loadAll" :disabled="loading">
          <i class="bi bi-arrow-clockwise"></i> 刷新
        </button>
        <router-link v-if="canManageCatalog" to="/teacher/capability-map" class="btn btn-secondary">
          <i class="bi bi-sliders"></i> 目录审核
        </router-link>
      </div>
    </div>

    <div v-if="loading" class="state-box">
      <div class="spinner"></div>
      <p>正在读取能力地图...</p>
    </div>

    <div v-else-if="error" class="state-box state-error">
      <i class="bi bi-exclamation-octagon"></i>
      <h2>{{ errorTitle }}</h2>
      <p>{{ error }}</p>
      <p class="hint" v-if="errorCode === 'catalog_not_published'">
        课程目录尚未开放，请等待教师发布后再查看。
      </p>
    </div>

    <template v-else>
      <div v-if="diagnosisResult" class="diagnosis-banner">
        <div>
          <strong>诊断已完成</strong>
          <span>已回答 {{ diagnosisResult.answered_count }} / {{ diagnosisResult.question_count }} 题；未作答项不记为不会。</span>
          <ul>
            <li v-for="entry in diagnosisResult.items" :key="entry.title">
              {{ entry.title }}：{{ entry.result_label }}
            </li>
          </ul>
        </div>
        <button class="icon-btn" @click="diagnosisResult = null"><i class="bi bi-x-lg"></i></button>
      </div>

      <div class="notice-row">
        <span class="notice notice-ok"><i class="bi bi-journal-check"></i> 目录 {{ map.catalog.version_label }}</span>
        <span class="notice" :class="map.catalog.is_published ? 'notice-ok' : 'notice-warn'">
          {{ map.catalog.status_label }}
        </span>
        <span class="notice"><i class="bi bi-shield-check"></i> 能力状态只由核验结果更新</span>
        <span class="notice notice-warn"><i class="bi bi-box-seam"></i> 执行类能力暂未开放</span>
      </div>

      <div class="summary-grid">
        <article class="summary-card">
          <span class="summary-label">开放能力</span>
          <strong>{{ map.summary.open_capabilities }}</strong>
          <span class="summary-meta">覆盖数据安全与网络安全两条主线</span>
        </article>
        <article class="summary-card">
          <span class="summary-label">已有独立证据</span>
          <strong>{{ map.summary.independent_count }}</strong>
          <span class="summary-meta">核验通过且未使用帮助</span>
        </article>
        <article class="summary-card">
          <span class="summary-label">受助或待复测</span>
          <strong>{{ map.summary.assisted_count }}</strong>
          <span class="summary-meta">需要换新场景完成无提示复测</span>
        </article>
      </div>

      <div class="layout">
        <main class="map-column">
          <section v-for="track in map.tracks" :key="track.track" class="track-card">
            <div class="track-head">
              <div>
                <h2>{{ track.label }}</h2>
                <p>{{ track.track === 'data' ? '分类分级依据、敏感项复核与风险决策回放。' : '授权边界、对象级授权与修复验证。' }}</p>
              </div>
              <button class="btn btn-ghost" @click="openDiagnosis(track.track)">
                <i class="bi bi-clipboard-pulse"></i> 做一次诊断
              </button>
            </div>

            <div class="dimension-row">
              <div v-for="dimension in track.dimensions" :key="dimension.dimension" class="dimension-chip">
                <span>{{ dimension.label }}</span>
                <strong :class="'tone-' + dimension.tone">{{ dimension.display_label }}</strong>
              </div>
            </div>

            <div class="capability-list">
              <article v-for="capability in track.capabilities" :key="capability.title" class="capability-card">
                <div class="capability-main">
                  <div class="capability-title-row">
                    <h3>{{ capability.title }}</h3>
                    <span class="dimension-tag">{{ capability.dimension_label }}</span>
                    <span class="status-tag" :class="capability.availability_label === '已开放' ? 'tag-open' : 'tag-muted'">
                      {{ capability.availability_label }}
                    </span>
                  </div>
                  <p class="objective">{{ capability.observable_objective }}</p>
                  <div class="capability-meta">
                    <span><i class="bi bi-bar-chart"></i> 难度 {{ capability.difficulty }}/5</span>
                    <span v-for="point in capability.knowledge_points" :key="point.name" class="kp">{{ point.name }}</span>
                  </div>
                  <div v-if="capability.prerequisites.length" class="prereq-row">
                    <span class="meta-label">先修</span>
                    <span v-for="prereq in capability.prerequisites" :key="prereq.title" class="prereq" :class="'tone-' + prereq.tone">
                      {{ prereq.title }} · {{ prereq.state_label }}
                    </span>
                  </div>
                </div>
                <div class="capability-side">
                  <span class="state-pill" :class="'tone-' + capability.tone">{{ capability.state_label }}</span>
                  <div class="evidence">
                    <span class="meta-label">最近证据</span>
                    <template v-if="capability.evidence.latest">
                      <span>{{ capability.evidence.fact_count }} 条 · {{ capability.evidence.latest.outcome_label }}</span>
                      <span v-if="capability.evidence.latest.task_title">{{ capability.evidence.latest.task_title }}</span>
                      <span v-if="capability.evidence.latest.assisted" class="assist-note">使用了帮助</span>
                      <span class="date-note">{{ formatDate(capability.evidence.latest.occurred_at) }}</span>
                    </template>
                    <span v-else>暂无证据，不补成低分</span>
                  </div>
                  <div v-if="capability.retest_due_at" class="retest">
                    复测安排：{{ formatDate(capability.retest_due_at) }}
                  </div>
                </div>
              </article>
            </div>
          </section>

          <p class="data-source">
            数据来源：{{ map.versions.data_source_label }} · 更新于 {{ formatDate(map.versions.updated_at) }}
          </p>
        </main>

        <aside class="side-column">
          <section class="panel">
            <div class="panel-head">
              <h2>下一步推荐</h2>
              <select v-model="goalTrack" class="select" @change="loadRecommendations">
                <option value="both">双主线</option>
                <option value="data">数据安全</option>
                <option value="network">网络安全</option>
              </select>
            </div>
            <p class="panel-note">
              先安排到期复测，再补先修或练习，最后进入新能力任务。
            </p>

            <div v-if="recommendationsLoading" class="mini-loading">正在计算...</div>
            <template v-else-if="recommendations">
              <div v-if="!recommendations.items.length" class="empty-block">
                <i class="bi bi-inbox"></i>
                <p>{{ recommendations.notice }}</p>
              </div>
              <article v-for="item in recommendations.items" :key="item.priority" class="rec-item">
                <div class="rec-head">
                  <span class="rec-category">{{ item.category_label }}</span>
                </div>
                <h3>{{ item.kind === 'task' ? item.task.title : (item.track_label + '基础诊断') }}</h3>
                <p class="rec-reason">{{ item.reason_text }}</p>
                <div class="rec-actions">
                  <span class="rec-version" v-if="item.task">
                    {{ item.task.version_label }} · {{ item.task.purpose_label }}
                  </span>
                  <span class="rec-version" v-else>诊断</span>
                  <button
                    v-if="item.kind === 'diagnosis'"
                    class="btn btn-primary btn-small"
                    @click="openDiagnosis(item.track_label === '数据安全' ? 'data' : 'network')"
                  >开始诊断</button>
                  <button
                    v-else
                    class="btn btn-primary btn-small"
                    :disabled="claimingId === item.task.id"
                    @click="claim(item)"
                  >{{ claimingId === item.task.id ? '领取中...' : '领取任务' }}</button>
                </div>
              </article>
              <div class="rec-foot">
                <span>更新于 {{ formatDate(recommendations.generated_at) }}</span>
              </div>
            </template>
            <p v-if="claimMessage" class="claim-message">{{ claimMessage }}</p>
          </section>

          <section class="panel panel-muted">
            <h2>证据口径</h2>
            <ul class="rule-list">
              <li>只有平台核验结果才更新能力状态。</li>
              <li>提交前实际使用过帮助会记为受助；只请求但未展示不算。</li>
              <li>受助通过不等于独立掌握，需要换新场景完成无提示复测。</li>
              <li>待评、未知、环境异常分别显示，不扣能力、不冒充通过。</li>
              <li>独立完成只代表系统可观测范围内未使用帮助。</li>
            </ul>
            <router-link to="/capability-map/changelog" class="panel-link">查看路径变更记录 →</router-link>
          </section>
        </aside>
      </div>
    </template>

    <div v-if="showDiagnosis" class="modal-mask" @click.self="showDiagnosis = false">
      <div class="modal">
        <div class="modal-head">
          <div>
            <span class="eyebrow">基础诊断</span>
            <h2>{{ diagnosisTrack === 'data' ? '数据安全' : '网络安全' }}</h2>
          </div>
          <button class="icon-btn" @click="showDiagnosis = false"><i class="bi bi-x-lg"></i></button>
        </div>
        <p class="modal-note">
          诊断只用于安排学习顺序，不构成掌握证据；未作答不记为不会。
        </p>
        <div v-if="questionsLoading" class="mini-loading">正在加载诊断题...</div>
        <div v-else-if="!questions.length" class="empty-block">
          <p>该主线暂无可用的诊断题，请等待课程补充。</p>
        </div>
        <form v-else @submit.prevent="submitDiagnosis">
          <div v-for="question in questions" :key="question.question_key" class="question">
            <span class="question-meta">{{ question.capability_title }} · {{ question.dimension_label }}</span>
            <p class="question-prompt">{{ question.prompt }}</p>
            <label v-for="option in question.options" :key="option.key" class="option">
              <input
                type="radio"
                :name="question.question_key"
                :value="option.key"
                v-model="answers[question.question_key]"
              />
              <span>{{ option.key }}. {{ option.label }}</span>
            </label>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn btn-secondary" @click="showDiagnosis = false">取消</button>
            <button type="submit" class="btn btn-primary" :disabled="diagnosisSubmitting">
              {{ diagnosisSubmitting ? '提交中...' : '提交诊断' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import service from '@/api'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const loading = ref(true)
const error = ref('')
const errorCode = ref('')
const map = ref(null)
const recommendations = ref(null)
const recommendationsLoading = ref(false)
const goalTrack = ref('both')
const claimingId = ref(null)
const claimMessage = ref('')
const showDiagnosis = ref(false)
const diagnosisTrack = ref('data')
const questions = ref([])
const questionsLoading = ref(false)
const answers = ref({})
const diagnosisSubmitting = ref(false)
const diagnosisResult = ref(null)

const canManageCatalog = computed(() => Boolean(userStore.userInfo?.can_manage_catalog))
const errorTitle = computed(() => errorCode.value === 'catalog_not_published' ? '目录尚未开放' : '读取失败')

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function extractError(err) {
  const data = err?.response?.data
  if (!data) return '网络或服务异常，请稍后重试。'
  if (typeof data === 'string') return data
  if (data.detail) {
    if (typeof data.detail === 'string') return data.detail
    if (data.detail.detail) return data.detail.detail
  }
  return '操作未完成，请稍后重试。'
}

async function loadAll() {
  loading.value = true
  error.value = ''
  errorCode.value = ''
  try {
    map.value = await service.learningMap.myMap()
    await loadRecommendations()
  } catch (err) {
    error.value = extractError(err)
    errorCode.value = err?.response?.data?.code || err?.response?.data?.detail?.code || ''
    map.value = null
  } finally {
    loading.value = false
  }
}

async function loadRecommendations() {
  if (!map.value) return
  recommendationsLoading.value = true
  try {
    recommendations.value = await service.learningMap.myRecommendations({ goal_track: goalTrack.value })
  } catch (err) {
    recommendations.value = null
    claimMessage.value = extractError(err)
  } finally {
    recommendationsLoading.value = false
  }
}

async function openDiagnosis(track) {
  diagnosisTrack.value = track || 'data'
  showDiagnosis.value = true
  diagnosisResult.value = null
  answers.value = {}
  questions.value = []
  questionsLoading.value = true
  try {
    const payload = await service.learningMap.diagnosticQuestions({ track: diagnosisTrack.value })
    questions.value = payload.questions || []
  } catch (err) {
    claimMessage.value = extractError(err)
  } finally {
    questionsLoading.value = false
  }
}

async function submitDiagnosis() {
  diagnosisSubmitting.value = true
  claimMessage.value = ''
  try {
    const payload = await service.learningMap.submitDiagnosis({
      goal_track: diagnosisTrack.value,
      answers: answers.value,
    })
    diagnosisResult.value = payload.result
    showDiagnosis.value = false
    await loadAll()
  } catch (err) {
    claimMessage.value = extractError(err)
  } finally {
    diagnosisSubmitting.value = false
  }
}

async function claim(item) {
  if (!item.task) return
  claimingId.value = item.task.id
  claimMessage.value = ''
  try {
    const payload = await service.learningMap.claimTask(item.task.id)
    claimMessage.value = `已领取《${payload.task.title}》，请按材料完成并提交。`
  } catch (err) {
    claimMessage.value = extractError(err)
  } finally {
    claimingId.value = null
  }
}

onMounted(loadAll)
</script>

<style scoped>
.capability-page {
  width: min(1240px, calc(100% - 40px));
  margin: 0 auto;
  padding: 40px 0 72px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-end;
  border-bottom: 2px solid var(--text-primary);
  padding-bottom: 22px;
  margin-bottom: 22px;
}
.eyebrow {
  display: inline-block;
  font-size: 12px;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: var(--primary-color);
  font-weight: 700;
  margin-bottom: 8px;
}
h1 {
  font-family: "Songti SC", "Noto Serif SC", serif;
  font-size: clamp(30px, 4vw, 48px);
  line-height: 1.1;
  letter-spacing: -.02em;
}
.subtitle {
  max-width: 720px;
  color: var(--text-secondary);
  margin-top: 10px;
}
.header-actions { display: flex; gap: 10px; flex-shrink: 0; }
.btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-primary);
  padding: 9px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 600;
  transition: all .16s ease;
}
.btn:hover { border-color: var(--text-primary); transform: translateY(-1px); }
.btn:disabled { opacity: .5; cursor: not-allowed; transform: none; }
.btn-primary { background: var(--text-primary); color: var(--bg-light); border-color: var(--text-primary); }
.btn-primary:hover { background: var(--primary-color); border-color: var(--primary-color); color: #fff; }
.btn-secondary { background: var(--bg-light); }
.btn-ghost { border-color: transparent; color: var(--primary-color); padding: 6px 8px; }
.btn-small { padding: 6px 10px; font-size: 12px; }
.diagnosis-banner {
  display: flex; justify-content: space-between; gap: 16px; align-items: flex-start;
  background: var(--bg-light); border: 1px solid var(--success-color);
  border-left: 4px solid var(--success-color); padding: 12px 14px; margin-bottom: 14px;
  font-size: 12px; color: var(--text-secondary);
}
.diagnosis-banner strong { display: block; color: var(--success-color); margin-bottom: 3px; }
.diagnosis-banner ul { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 6px 16px; }
.notice-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }
.notice {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; padding: 5px 9px;
  border: 1px solid var(--border-color); background: var(--bg-light);
}
.notice-ok { color: var(--success-color); border-color: rgba(79,124,82,.35); }
.notice-warn { color: var(--warning-color); border-color: rgba(201,135,33,.35); }
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 24px; }
.summary-card {
  background: var(--bg-light);
  border: 1px solid var(--text-primary);
  padding: 18px;
  box-shadow: var(--shadow-md);
  display: flex; flex-direction: column; gap: 4px;
}
.summary-label { font-size: 12px; letter-spacing: .08em; color: var(--text-muted); text-transform: uppercase; }
.summary-card strong { font-size: 30px; line-height: 1.1; }
.summary-meta { font-size: 12px; color: var(--text-secondary); }
.layout { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(320px, .8fr); gap: 20px; align-items: start; }
.track-card { background: var(--bg-light); border: 1px solid var(--border-color); margin-bottom: 18px; }
.track-head { display: flex; justify-content: space-between; gap: 16px; padding: 20px; border-bottom: 1px solid var(--border-color); }
.track-head h2 { font-family: "Songti SC", serif; font-size: 26px; }
.track-head p { color: var(--text-secondary); font-size: 13px; margin-top: 4px; }
.dimension-row { display: grid; grid-template-columns: repeat(4, 1fr); border-bottom: 1px solid var(--border-color); }
.dimension-chip { padding: 12px 14px; border-right: 1px solid var(--border-color); display: flex; flex-direction: column; gap: 4px; }
.dimension-chip:last-child { border-right: 0; }
.dimension-chip span { font-size: 11px; color: var(--text-muted); }
.dimension-chip strong { font-size: 13px; }
.capability-list { display: flex; flex-direction: column; }
.capability-card { display: grid; grid-template-columns: minmax(0, 1fr) 190px; gap: 16px; padding: 18px 20px; border-bottom: 1px solid var(--border-color); }
.capability-card:last-child { border-bottom: 0; }
.capability-title-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.capability-title-row h3 { font-size: 16px; }
.dimension-tag, .status-tag { font-size: 11px; padding: 2px 6px; border: 1px solid var(--border-color); color: var(--text-secondary); }
.tag-open { color: var(--success-color); border-color: rgba(79,124,82,.4); }
.tag-muted { color: var(--text-muted); }
.objective { color: var(--text-secondary); margin-top: 7px; font-size: 13px; }
.capability-meta { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 9px; font-size: 12px; color: var(--text-muted); }
.kp { background: var(--bg-gray); padding: 2px 6px; }
.prereq-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 10px; }
.meta-label { font-size: 11px; letter-spacing: .08em; color: var(--text-muted); text-transform: uppercase; }
.prereq { font-size: 12px; border-bottom: 1px dashed var(--border-color); }
.capability-side { border-left: 1px solid var(--border-color); padding-left: 16px; display: flex; flex-direction: column; gap: 10px; }
.state-pill { display: inline-block; font-size: 12px; font-weight: 700; padding: 4px 8px; border: 1px solid currentColor; align-self: flex-start; }
.evidence { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary); }
.assist-note { color: var(--warning-color); }
.date-note { font-size: 11px; color: var(--text-muted); }
.retest { font-size: 12px; color: var(--warning-color); }
.tone-success { color: var(--success-color); }
.tone-danger { color: var(--error-color); }
.tone-warning { color: var(--warning-color); }
.tone-muted { color: var(--text-muted); }
.tone-neutral { color: var(--text-secondary); }
.state-pill.tone-success { background: rgba(79,124,82,.08); }
.state-pill.tone-danger { background: rgba(183,53,45,.07); }
.state-pill.tone-warning { background: rgba(201,135,33,.09); }
.state-pill.tone-muted { background: var(--bg-gray); }
.state-pill.tone-neutral { background: var(--bg-paper-2); }
.side-column { display: flex; flex-direction: column; gap: 16px; position: sticky; top: 84px; }
.panel { background: var(--bg-light); border: 1px solid var(--text-primary); padding: 18px; box-shadow: var(--shadow-md); }
.panel-muted { box-shadow: none; border-color: var(--border-color); }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.panel h2 { font-family: "Songti SC", serif; font-size: 20px; }
.panel-note { font-size: 12px; color: var(--text-muted); margin: 8px 0 12px; }
.select { border: 1px solid var(--border-color); background: var(--bg-paper); padding: 5px 8px; }
.rec-item { border-top: 1px solid var(--border-color); padding: 13px 0; }
.rec-head { display: flex; justify-content: space-between; gap: 8px; font-size: 11px; }
.rec-category { color: var(--primary-color); font-weight: 700; letter-spacing: .06em; }
.rec-item h3 { font-size: 15px; margin-top: 4px; }
.rec-reason { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.rec-actions { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 9px; }
.rec-version { font-size: 11px; color: var(--text-muted); }
.rec-foot { display: flex; justify-content: space-between; gap: 8px; font-size: 10px; color: var(--text-muted); border-top: 1px solid var(--border-color); padding-top: 10px; margin-top: 10px; }
.rule-list { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; font-size: 12px; color: var(--text-secondary); }
.rule-list li { padding-left: 12px; position: relative; }
.rule-list li::before { content: "—"; position: absolute; left: 0; color: var(--primary-color); }
.panel-link { display: inline-block; margin-top: 12px; font-size: 12px; font-weight: 600; }
.claim-message { margin-top: 12px; font-size: 12px; color: var(--warning-color); }
.empty-block { text-align: center; color: var(--text-muted); padding: 24px 8px; }
.empty-block i { font-size: 26px; display: block; margin-bottom: 6px; }
.state-box { background: var(--bg-light); border: 1px solid var(--border-color); padding: 64px 24px; text-align: center; }
.state-box i { font-size: 40px; color: var(--warning-color); }
.state-error h2 { margin: 10px 0 6px; font-family: "Songti SC", serif; }
.hint { font-size: 12px; color: var(--text-muted); margin-top: 8px; }
.mini-loading { font-size: 12px; color: var(--text-muted); padding: 12px 0; }
.data-source { font-size: 11px; color: var(--text-muted); padding: 10px 2px; }
.modal-mask { position: fixed; inset: 0; background: rgba(24,23,19,.55); display: flex; align-items: center; justify-content: center; padding: 20px; z-index: 1000; }
.modal { background: var(--bg-light); width: min(680px, 100%); max-height: 88vh; overflow: auto; border: 1px solid var(--text-primary); box-shadow: var(--shadow-lg); padding: 22px; }
.modal-head { display: flex; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; margin-bottom: 12px; }
.modal-head h2 { font-family: "Songti SC", serif; }
.icon-btn { border: 0; background: transparent; font-size: 18px; cursor: pointer; }
.modal-note { font-size: 12px; color: var(--text-muted); margin-bottom: 12px; }
.question { border-top: 1px solid var(--border-color); padding: 14px 0; }
.question-meta { font-size: 11px; color: var(--primary-color); font-weight: 700; }
.question-prompt { margin: 5px 0 8px; }
.option { display: flex; gap: 8px; align-items: flex-start; font-size: 13px; padding: 4px 0; cursor: pointer; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px; }
.spinner { width: 26px; height: 26px; border: 3px solid var(--border-color); border-top-color: var(--primary-color); border-radius: 50%; margin: 0 auto 12px; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 980px) {
  .layout { grid-template-columns: 1fr; }
  .side-column { position: static; }
  .summary-grid { grid-template-columns: 1fr; }
  .dimension-row { grid-template-columns: repeat(2, 1fr); }
  .capability-card { grid-template-columns: 1fr; }
  .capability-side { border-left: 0; border-top: 1px solid var(--border-color); padding-left: 0; padding-top: 12px; }
  .page-header { flex-direction: column; align-items: flex-start; }
}
</style>
