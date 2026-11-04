<template>
  <div class="teacher-map-page">
    <div class="page-header">
      <div>
        <span class="eyebrow">能力目录 · 教师视图</span>
        <h1>{{ names.capability }}审核</h1>
        <p class="subtitle">
          查看候选目录、审核门禁、学生状态与证据，并记录教师调整。候选目录未签收前不能冻结或发布。
        </p>
      </div>
      <div class="header-actions">
        <router-link to="/capability-map" class="btn btn-secondary">学生视图</router-link>
        <button class="btn btn-secondary" @click="loadCatalog">刷新目录</button>
      </div>
    </div>

    <div class="toolbar">
      <label>
        目录版本
        <select v-model="catalogVersion" class="input"><option :value="catalogVersion">{{ versionLabel(catalogVersion) }}</option></select>
      </label>
      <label>
        选择学生
        <select v-model="studentId" class="input input-short">
          <option value="">请选择学生</option>
          <option v-for="student in students" :key="student.id" :value="String(student.id)">
            {{ student.username }}
          </option>
        </select>
      </label>
      <button class="btn btn-primary" @click="loadStudent">加载学生</button>
      <button class="btn btn-secondary" @click="exportCase">导出能力目录</button>
      <button v-if="isAdmin" class="btn btn-secondary" @click="freezeCatalog">冻结</button>
      <button v-if="isAdmin" class="btn btn-secondary" @click="publishCatalog">发布</button>
    </div>

    <ReferenceImport title="其他目录版本" :fields="versionFields" :model-value="{ catalog_version: catalogVersion }" @update:model-value="catalogVersion = $event.catalog_version; loadCatalog()" />
    <p v-if="message" class="message">{{ message }}</p>

    <div v-if="loadingCatalog" class="state-box">正在读取候选目录...</div>
    <template v-else-if="catalog">
      <div class="notice-row">
        <span class="notice" :class="catalog.status === 'published' ? 'notice-ok' : 'notice-warn'">
          {{ versionLabel(catalog.version) }} · {{ catalog.status_label }}
        </span>
        <span class="notice notice-dark">规则 {{ versionLabel(catalog.rule_version) }}</span>
        <span class="notice" :class="catalog.readiness.ready ? 'notice-ok' : 'notice-warn'">
          发布门禁：{{ catalog.readiness.ready ? '已满足' : '未满足（' + catalog.readiness.missing.length + ' 项缺失）' }}
        </span>
        <span class="notice">能力 {{ catalog.readiness.counts.capabilities }} · 开放 {{ catalog.readiness.counts.open_capabilities }} · 任务 {{ catalog.readiness.counts.tasks }}</span>
      </div>

      <section class="panel">
        <div class="panel-head">
          <h2>审核门禁缺失项</h2>
          <span class="muted">签收必须有真实复核人、附件位置和时间；不得代填。</span>
        </div>
        <div v-if="!catalog.readiness.missing.length" class="ok-block">全部检查通过。</div>
        <ul v-else class="missing-list">
          <li v-for="(item, index) in catalog.readiness.missing" :key="index">
            <span>{{ missingLabel(item) }}</span>
          </li>
        </ul>
        <RecordView :value="catalog.readiness" title="目录审核依据" />
      </section>

      <div class="two-col">
        <section class="panel">
          <h2>能力目录</h2>
          <div class="cap-table">
            <div class="cap-row cap-head">
              <span>序</span><span>能力</span><span>主线/维度</span><span>状态</span><span>先修</span>
            </div>
            <div v-for="(capability, index) in catalog.capabilities" :key="capability.capability_id" class="cap-row">
              <span>{{ index + 1 }}</span>
              <span>{{ capability.title }}</span>
              <span>{{ trackLabel(capability.track) }} / {{ dimensionLabel(capability.dimension) }}</span>
              <span>{{ capability.status_label }}</span>
              <span class="mono small">{{ prerequisiteTitles(capability) || '—' }}</span>
            </div>
          </div>
        </section>

        <section class="panel">
          <h2>教师调整</h2>
          <p class="muted">指定任务必须记录理由；任务环境不可用或尚未开放的任务不能指定。</p>
          <form class="adjust-form" @submit.prevent="submitAdjustment">
            <label>学生
              <select v-model="adjustment.student" class="input">
                <option value="">请选择学生</option>
                <option v-for="student in students" :key="student.id" :value="String(student.id)">
                  {{ student.username }}
                </option>
              </select>
            </label>
            <label>能力
              <select v-model="adjustment.capability_id" class="input">
                <option value="">请选择能力</option>
                <option v-for="capability in catalog.capabilities" :key="capability.capability_id" :value="capability.capability_id">
                  {{ capability.title }}
                </option>
              </select>
            </label>
            <label>动作
              <select v-model="adjustment.action" class="input">
                <option value="assign_task">指定任务</option>
                <option value="request_retest">安排复测</option>
                <option value="add_note">补充说明</option>
                <option value="refer_review">转交复核</option>
              </select>
            </label>
            <label>任务
              <select v-model="adjustment.task_key" class="input">
                <option value="">不指定任务</option>
                <option v-for="task in taskOptions" :key="task.task_key" :value="task.task_key">
                  {{ task.title }} · {{ task.version }}
                </option>
              </select>
            </label>
            <label>任务版本
              <select v-model="adjustment.task_version" class="input">
                <option value="">不限版本</option>
                <option v-for="version in taskVersions" :key="version" :value="version">{{ version }}</option>
              </select>
            </label>
            <label class="full">理由
              <textarea v-model="adjustment.rationale" class="input" rows="3" placeholder="写清楚证据、卡点和调整目的"></textarea>
            </label>
            <button class="btn btn-primary" type="submit" :disabled="submittingAdjustment">
              {{ submittingAdjustment ? '提交中...' : '记录调整' }}
            </button>
          </form>
        </section>
      </div>

      <section class="panel">
        <h2>学生证据与推荐</h2>
        <p v-if="loadingStudent" role="status">正在读取所选学生的学习记录…</p>
        <div v-else-if="studentError" role="alert" class="message">{{ studentError }} <button type="button" class="btn" @click="loadStudent">重试</button></div>
        <div v-if="!studentMap && !loadingStudent && !studentError" class="muted">选择学生后加载。</div>
        <template v-if="studentMap">
          <div class="student-head">
            <strong>{{ studentMap.student.username }}</strong>
            <span>目录 {{ versionLabel(studentMap.catalog.version) }}</span>
            <span>规则 {{ versionLabel(studentMap.catalog.rule_version) }}</span>
          </div>
          <RecordView :value="studentMap.catalog" title="学生目录与规则版本" />
          <div class="student-grid">
            <div class="student-map">
              <div v-for="track in studentMap.tracks" :key="track.track">
                <h3>{{ track.label }}</h3>
                <div v-for="(capability, index) in track.capabilities" :key="capability.capability_id" class="student-cap">
                  <span>{{ index + 1 }}</span>
                  <span>{{ capability.title }}</span>
                  <span class="state" :class="'state-' + capability.state">{{ capability.state_label }}</span>
                  <span class="muted small">
                    {{ capability.evidence.fact_count }} 条证据
                    <template v-if="capability.evidence.latest"> · {{ outcomeLabel(capability.evidence.latest.outcome) }}</template>
                  </span>
                </div>
              </div>
            </div>
            <div class="student-rec">
              <h3>当前推荐</h3>
              <p v-if="!studentRecommendations" class="muted">暂无推荐数据。</p>
              <template v-else>
                <div v-if="!studentRecommendations.items.length" class="muted">没有可推荐任务。</div>
                <article v-for="item in studentRecommendations.items" :key="item.priority + '-' + item.category">
                  <span class="rec-cat">{{ item.category_label }}</span>
                  <strong>{{ item.task ? item.task.title : item.track_label + '基础诊断' }}</strong>
                  <p class="muted small">{{ item.reason.text }}</p>
                </article>
                <div v-if="studentRecommendations.gaps.length" class="gaps">
                  <h4>缺口</h4>
                  <p v-for="gap in studentRecommendations.gaps" :key="gap.code + gap.capability_id">
                    {{ missingLabel(gap) }}
                  </p>
                </div>
              </template>
            </div>
          </div>
          <details id="student-capability-history" class="changelog" :open="historyOpen" @toggle="historyOpen = $event.target.open">
            <summary>学生学习历史</summary>
            <p class="muted">{{ studentMap.student.username }}的能力状态变化，保留时间、前后状态与原因。展示最近最多两百条记录。</p>
            <CapabilityHistoryTable :rows="historyRows" :loading="loadingStudent" :error="studentError" caption="所选学生能力状态变化记录" @retry="loadStudent" />
            <RecordView :value="changelog" title="完整学生状态历史" />
          </details>
        </template>
      </section>

      <div class="two-col">
        <section class="panel">
          <h2>场景转译（候选）</h2>
          <div v-for="mapping in catalog.wstg_mappings" :key="mapping.scenario_id" class="evidence-row">
            <span class="mono">{{ mapping.scenario_title }}</span>
            <span>{{ capabilityTitle(mapping.capability_id) }}</span>
            <span class="muted small">{{ statusLabel(mapping.status) }} · 复核人 {{ mapping.reviewer_name || '未指定' }}</span>
          </div>
        </section>
        <section class="panel">
          <h2>数据依据卡（候选）</h2>
          <div v-for="card in catalog.basis_cards" :key="card.card_id" class="evidence-row">
            <span class="mono">{{ card.source_title }} {{ card.source_clause }}</span>
            <span>{{ capabilityTitle(card.capability_id) }}</span>
            <span class="muted small">{{ statusLabel(card.status) }} · 核验日期 {{ card.verified_date || '未核验' }}</span>
          </div>
        </section>
      </div>

      <section class="panel">
        <h2>交付登记</h2>
        <p class="muted">状态必须由真实编制、复核和附件支撑；缺失时不能签收。</p>
        <div class="delivery-table">
          <div class="delivery-row head">
            <span>序</span><span>交付项</span><span>版本</span><span>状态</span><span>复核人</span><span>附件</span><span>未决问题</span>
          </div>
          <div v-for="(item, index) in deliveryItems" :key="item.delivery_no" class="delivery-row">
            <span>{{ index + 1 }}</span>
            <span>{{ item.title }}</span>
            <span class="mono small">{{ item.version }}</span>
            <span>{{ item.status_label }}</span>
            <span>{{ item.reviewer_name || '—' }}</span>
            <span>{{ item.attachment_path ? '已提供，完整登记可下载核对' : '未提供' }}</span>
            <span class="small">{{ item.open_issues || '—' }}</span>
          </div>
        </div>
        <RecordView :value="deliveryItems" title="完整交付登记" />
      </section>
    </template>
  </div>
</template>

<script setup>
import { names } from '@/shared/navigation/names'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import CapabilityHistoryTable from '@/shared/learning/CapabilityHistoryTable.vue'
import service from '@/api'
import ReferenceImport from '@/shared/forms/ReferenceImport.vue'
import RecordView from '@/shared/forms/RecordView.vue'
import { configurationVersionLabel } from './candidatePresentation.js'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.userInfo?.role === 'admin')
const canManageCatalog = computed(() => Boolean(userStore.userInfo?.can_manage_catalog))
const catalogVersion = ref('v1-candidate')
const studentId = ref('')
const students = ref([])
const catalog = ref(null)
const deliveryItems = ref([])
const studentMap = ref(null)
const studentRecommendations = ref(null)
const changelog = ref([])
const route = useRoute()
const historyOpen = ref(false)
const loadingStudent = ref(false)
const studentError = ref('')
let studentGeneration = 0
function clearStudent() {
  studentGeneration += 1
  studentMap.value = null
  studentRecommendations.value = null
  changelog.value = []
  loadingStudent.value = false
  studentError.value = ''
}
watch(() => [studentId.value, catalogVersion.value, userStore.userInfo?.id, userStore.userInfo?.role], clearStudent, { flush: 'sync' })
const historyRows = computed(() => changelog.value.map(item => ({
  title: item.capability_title || capabilityTitle(item.capability_id),
  from: item.from_state_label || stateLabel(item.from_state),
  to: item.to_state_label || stateLabel(item.to_state),
  reason: item.reason_label || reasonLabel(item.reason),
  timeLabel: formatDate(item.created_at),
})))
async function locateStudentHistory() {
  if (route.query.history !== '1' && route.hash !== '#student-capability-history') return
  historyOpen.value = true
  await nextTick()
  document.getElementById('student-capability-history')?.scrollIntoView({ block: 'start', behavior: 'auto' })
}
watch(() => [route.query.history, route.hash], locateStudentHistory, { immediate: true })
onBeforeUnmount(clearStudent)
const loadingCatalog = ref(false)
const message = ref('')
const submittingAdjustment = ref(false)
const adjustment = reactive({
  student: '',
  capability_id: '',
  action: 'assign_task',
  task_key: '',
  task_version: '',
  rationale: '',
})

const trackLabels = { data: '数据安全', network: '网络安全' }
const dimensionLabels = { explain: '能解释', identify: '能识别', operate: '能操作', repair: '能修复' }
const stateLabels = {
  not_attempted: '未开展', needs_diagnosis: '待诊断', diagnosed: '已完成诊断', needs_practice: '需要练习',
  assisted_pass: '受助通过', independent: '已有独立证据', retest_pending: '待复测',
  pending_review: '待教师评阅', pending_verification: '待核验', environment_affected: '受环境影响',
  unknown: '未知',
}
const outcomeLabels = {
  passed: '通过', failed: '未通过', pending_review: '待教师评阅', verification_failed: '核验失败',
  environment_affected: '受环境影响', unknown: '未知',
}
const reasonLabels = {
  independent_pass: '独立通过', assisted_pass: '受助通过', retest_independent_pass: '复测独立通过',
  retest_assisted_pass: '复测受助通过', verification_not_passed: '核验未通过', retest_failed: '复测未通过',
  pending_teacher_review: '等待教师评阅', verification_service_failed: '核验未完成',
  environment_affected: '受环境影响', help_record_unknown: '帮助记录不完整',
  unknown_evidence: '证据待确认', retest_due: '到达复测时间',
}
const statusLabels = {
  candidate: '候选', reviewing: '复核中', reviewed: '已复核', published: '已发布',
  open: '已开放', to_build: '待建设', draft: '草稿', verified: '已核验', pending: '待核验',
}
const trackLabel = value => trackLabels[value] || '—'
const dimensionLabel = value => dimensionLabels[value] || '—'
const stateLabel = value => stateLabels[value] || '状态待确认'
const outcomeLabel = value => outcomeLabels[value] || '结果待确认'
const reasonLabel = value => reasonLabels[value] || '变更原因待确认'
const statusLabel = value => statusLabels[value] || '状态待确认'
function capabilityTitle(id) {
  if (!id) return '—'
  return catalog.value?.capabilities?.find(item => item.capability_id === id)?.title || '能力名称暂不可用'
}
function prerequisiteTitles(capability) {
  const all = catalog.value?.capabilities || []
  return (capability.prerequisite_ids || [])
    .map(id => all.find(item => item.capability_id === id)?.title)
    .filter(Boolean)
    .join('、')
}
const taskOptions = computed(() => {
  const seen = new Map()
  for (const capability of catalog.value?.capabilities || []) {
    for (const task of capability.tasks || []) {
      if (task && task.task_key && !seen.has(task.task_key)) seen.set(task.task_key, task)
    }
  }
  return [...seen.values()]
})
const taskVersions = computed(() => [...new Set(taskOptions.value.map(task => task.version).filter(Boolean))])
const versionFields = [{ key: 'catalog_version', label: '目录版本' }]
const versionLabel = configurationVersionLabel
const missingLabels = {
  delivery_item_missing: '缺少交付登记', delivery_item_not_signed: '交付尚未签收', delivery_item_incomplete_signoff: '交付签收记录不完整',
  open_capability_without_task: '已开放但没有已冻结任务', task_package_incomplete: '任务材料、提示、解析、核验、验收或复测题池不完整',
  wstg_not_reviewed: '缺少已复核的安全测试场景', basis_card_not_reviewed: '缺少已复核的数据依据卡', diagnostic_missing: '主线缺少已冻结诊断题', wstg_version_missing: '安全测试场景缺少来源版本',
  no_task: '暂无可推荐任务', prerequisite_missing: '先修证据尚未满足', task_unavailable: '任务环境暂不可用',
}
function missingLabel(item) {
  const subject = item.capability_id ? capabilityTitle(item.capability_id) : item.track ? trackLabel(item.track) : ''
  const description = missingLabels[item.code] || '审核资料尚不完整，可下载完整依据核对'
  return [subject, description].filter(Boolean).join('：')
}
function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN') : '—' }
function extractError(err) {
  if (err?.response?.status === 403) return '当前账号无权查看或调整该能力目录。'
  if (err?.response?.status === 404) return '目录或学生记录不存在，请核对选择后重试。'
  if (err?.response?.data?.detail?.missing) return '目录审核资料尚不完整，请先核对缺失项。'
  return '操作未完成，请核对填写内容与审核条件后重试。'
}

async function loadCatalog() {
  loadingCatalog.value = true
  message.value = ''
  try {
    catalog.value = await service.learningMap.teacherCatalog({ version: catalogVersion.value })
    const register = await service.learningMap.deliveryRegister({ version: catalogVersion.value })
    deliveryItems.value = register.items || []
  } catch (err) {
    catalog.value = null
    deliveryItems.value = []
    message.value = extractError(err)
  } finally {
    loadingCatalog.value = false
  }
}

async function loadStudents() {
  if (!canManageCatalog.value) return
  try {
    const payload = await service.analytics.teacherStudentReport()
    students.value = (payload || []).map(item => ({
      id: item.id,
      username: item.username || '学生名称暂不可用',
    }))
  } catch {
    students.value = []
  }
}

async function loadStudent() {
  clearStudent()
  const token = studentGeneration
  message.value = ''
  const id = Number(studentId.value)
  if (!Number.isSafeInteger(id) || id <= 0) {
    message.value = '请先选择学生。'
    return
  }
  loadingStudent.value = true
  try {
    const params = { version: catalogVersion.value }
    const [map, recommendations, logs] = await Promise.all([
      service.learningMap.studentMap(id, params),
      service.learningMap.studentRecommendations(id, params),
      service.learningMap.studentChangelog(id, params),
    ])
    if (token !== studentGeneration) return
    studentMap.value = map
    studentRecommendations.value = recommendations
    changelog.value = logs.items || []
    await locateStudentHistory()
  } catch (err) {
    if (token === studentGeneration) studentError.value = extractError(err)
  } finally {
    if (token === studentGeneration) loadingStudent.value = false
  }
}

async function submitAdjustment() {
  submittingAdjustment.value = true
  message.value = ''
  try {
    await service.learningMap.createAdjustment({
      catalog_version: catalogVersion.value,
      student: Number(adjustment.student || studentId.value),
      capability_id: adjustment.capability_id || null,
      task_key: adjustment.task_key || null,
      task_version: adjustment.task_version || null,
      action: adjustment.action,
      rationale: adjustment.rationale,
    })
    adjustment.student = ''
    message.value = '教师调整已记录；下一次推荐会引用该调整。'
    adjustment.rationale = ''
    if (studentId.value) await loadStudent()
  } catch (err) {
    message.value = extractError(err)
  } finally {
    submittingAdjustment.value = false
  }
}

async function freezeCatalog() {
  message.value = ''
  try {
    const payload = await service.learningMap.freezeCatalog(catalogVersion.value)
    message.value = `目录已冻结：${versionLabel(payload.version)}`
    await loadCatalog()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function publishCatalog() {
  message.value = ''
  try {
    const payload = await service.learningMap.publishCatalog(catalogVersion.value)
    message.value = `目录已发布：${versionLabel(payload.version)}`
    await loadCatalog()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function exportCase() {
  message.value = ''
  try {
    const payload = await service.learningMap.exportCatalog(catalogVersion.value, { format: 'case' })
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `case-${catalogVersion.value}.json`
    link.click()
    URL.revokeObjectURL(url)
    message.value = '能力目录已导出。'
  } catch (err) {
    message.value = extractError(err)
  }
}

onMounted(() => {
  loadCatalog()
  loadStudents()
})
</script>

<style scoped>
.teacher-map-page { width:min(var(--page-width), calc(100% - var(--space-5))); margin:0 auto; padding:var(--space-4) 0 var(--space-8); }
.page-header { display:flex; justify-content:space-between; align-items:flex-end; gap:var(--space-2); border-bottom:calc(var(--stroke) * 2) solid var(--text-primary); padding-bottom:var(--space-2); margin-bottom:var(--space-2); }
.eyebrow { font-size:var(--text-caption); letter-spacing:.18em; text-transform:uppercase; color:var(--primary-color); font-weight: var(--weight-strong); }
h1 { font-family: var(--font-family); font-size:var(--text-page); line-height:1.1; }
.subtitle { color:var(--text-secondary); margin-top:var(--space-1); max-width:var(--search-width); }
.header-actions { display:flex; gap:var(--space-1); }
.btn { border:var(--stroke) solid var(--border-color); background:var(--bg-light); padding:var(--space-1) var(--space-1); font-weight: var(--weight-strong); cursor:pointer; color:var(--text-primary); }
.btn-primary { background:var(--text-primary); color:var(--bg-light); border-color:var(--text-primary); }
.toolbar { display:flex; flex-wrap:wrap; gap:var(--space-1); align-items:flex-end; background:var(--bg-light); border:var(--stroke) solid var(--border-color); padding:var(--space-2); margin-bottom:var(--space-2); }
.toolbar label { display:flex; flex-direction:column; gap:calc(var(--space-1) / 2); font-size:var(--text-caption); color:var(--text-muted); text-transform:uppercase; letter-spacing:.06em; }
.input { border:var(--stroke) solid var(--border-color); background:var(--bg-paper); padding:calc(var(--space-1) / 2) var(--space-1); min-width:var(--sidebar-width); color:var(--text-primary); }
.input-short { min-width:var(--row-label-width); }
.message { background:var(--surface-muted); border-left:var(--focus-width) solid var(--primary-color); padding:var(--space-1) var(--space-1); font-size:var(--text-caption); margin-bottom:var(--space-2); }
.notice-row { display:flex; flex-wrap:wrap; gap:var(--space-1); margin-bottom:var(--space-2); }
.notice { font-size:var(--text-caption); padding:calc(var(--space-1) / 2) var(--space-1); border:var(--stroke) solid var(--border-color); background:var(--bg-light); }
.notice-dark { background:var(--text-primary); color:var(--bg-light); }
.notice-ok { color:var(--success-color); border-color:var(--positive); }
.notice-warn { color:var(--warning-color); border-color:var(--warning); }
.panel { background:var(--bg-light); border:var(--stroke) solid var(--text-primary); padding:var(--space-2); margin-bottom:var(--space-2); box-shadow: var(--shadow-raised); }
.panel h2 { font-family: var(--font-family); font-size:var(--text-card); margin-bottom:var(--space-1); }
.panel-head { display:flex; justify-content:space-between; gap:var(--space-1); align-items:baseline; }
.muted { color:var(--text-muted); font-size:var(--text-caption); }
.small { font-size:var(--text-caption); }
.mono { font-family:ui-monospace, monospace; }
.missing-list { display:flex; flex-direction:column; gap:calc(var(--space-1) / 2); font-size:var(--text-caption); }
.missing-list li { display:flex; gap:var(--space-1); }
.code { font-family:ui-monospace, monospace; color:var(--warning-color); min-width:var(--row-value-width); }
.ok-block { color:var(--success-color); font-weight: var(--weight-strong); }
.two-col { display:grid; grid-template-columns:1fr 1fr; gap:var(--space-2); }
.cap-table { display:flex; flex-direction:column; max-height:var(--content-height); overflow:auto; }
.cap-row { display:grid; grid-template-columns:var(--space-8) 1.4fr 1.2fr var(--row-label-width) var(--row-label-width); gap:var(--space-1); padding:calc(var(--space-1) / 2) calc(var(--space-1) / 2); border-bottom:var(--stroke) solid var(--border-color); font-size:var(--text-caption); }
.cap-head { background:var(--bg-paper-2); font-size:var(--text-caption); text-transform:uppercase; letter-spacing:.06em; position:sticky; top:0; }
.adjust-form { display:grid; grid-template-columns:1fr 1fr; gap:var(--space-1); margin-top:var(--space-1); }
.adjust-form label { display:flex; flex-direction:column; gap:calc(var(--space-1) / 2); font-size:var(--text-caption); color:var(--text-muted); }
.adjust-form .full { grid-column:1 / -1; }
.student-head { display:flex; gap:var(--space-2); align-items:baseline; border-bottom:var(--stroke) solid var(--border-color); padding-bottom:var(--space-1); margin-bottom:var(--space-1); font-size:var(--text-caption); color:var(--text-secondary); }
.student-grid { display:grid; grid-template-columns:1.4fr 1fr; gap:var(--space-2); }
.student-map h3, .student-rec h3 { font-size:var(--text-caption); margin:var(--space-1) 0 calc(var(--space-1) / 2); }
.student-cap { display:grid; grid-template-columns:var(--space-8) 1fr var(--row-label-width) var(--row-label-width); gap:var(--space-1); font-size:var(--text-caption); padding:calc(var(--space-1) / 2) 0; border-bottom:var(--stroke) dotted var(--border-color); }
.state { font-weight: var(--weight-strong); font-size:var(--text-caption); }
.state-independent { color:var(--success-color); }
.state-needs_practice { color:var(--error-color); }
.state-assisted_pass, .state-retest_pending { color:var(--warning-color); }
.state-needs_diagnosis, .state-diagnosed, .state-not_attempted { color:var(--text-muted); }
.student-rec article { border-bottom:var(--stroke) solid var(--border-color); padding:var(--space-1) 0; }
.rec-cat { font-size:var(--text-caption); color:var(--primary-color); font-weight: var(--weight-strong); margin-right:calc(var(--space-1) / 2); }
.gaps { margin-top:var(--space-1); }
.gaps h4 { font-size:var(--text-caption); color:var(--warning-color); }
.changelog { margin-top:var(--space-2); border-top:var(--stroke) solid var(--border-color); padding-top:var(--space-1); scroll-margin-top: calc(var(--header-height) + var(--space-3)); }
.changelog summary { min-height: var(--control-height); cursor: pointer; font-weight: var(--weight-strong); }
.changelog summary:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.change-row { display:grid; grid-template-columns:var(--space-8) var(--row-label-width) 1fr var(--row-label-width); gap:var(--space-1); font-size:var(--text-caption); padding:var(--focus-width) 0; }
.evidence-row { display:grid; grid-template-columns:var(--row-label-width) 1.2fr 1fr; gap:var(--space-1); font-size:var(--text-caption); padding:calc(var(--space-1) / 2) 0; border-bottom:var(--stroke) dotted var(--border-color); }
.delivery-table { display:flex; flex-direction:column; overflow-x:auto; }
.delivery-row { display:grid; grid-template-columns:var(--row-label-width) 1.4fr var(--row-label-width) var(--row-label-width) var(--row-label-width) var(--row-value-width) 1fr; gap:var(--space-1); padding:calc(var(--space-1) / 2) calc(var(--space-1) / 2); border-bottom:var(--stroke) solid var(--border-color); font-size:var(--text-caption); min-width:var(--reading-width); }
.delivery-row.head { background:var(--bg-paper-2); font-size:var(--text-caption); text-transform:uppercase; letter-spacing:.06em; }
.state-box { background:var(--bg-light); border:var(--stroke) solid var(--border-color); padding:var(--space-5); text-align:center; color:var(--text-muted); }
@media (max-width: 1120px) {
  .two-col, .student-grid { grid-template-columns:1fr; }
  .page-header { flex-direction:column; align-items:flex-start; }
  .adjust-form { grid-template-columns:1fr; }
}
</style>
