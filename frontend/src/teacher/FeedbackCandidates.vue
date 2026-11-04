<template>
  <div class="candidate-page" :class="{ 'candidate-embedded': embedded }">
    <div class="page-header">
      <div v-if="!embedded">
        <span class="eyebrow">教学 · 候选改进</span>
        <h1>问题组与候选管理</h1>
        <p class="subtitle">
          问题组须人工确认成员；候选只能引用已确认、无缺证的问题组。审批依据相应教学配置与评测报告，发布只影响后续任务。
        </p>
      </div>
      <button class="btn btn-secondary" @click="loadAll" :disabled="loading">刷新</button>
    </div>

    <div class="gates">
      <span :class="['gate', gates.phase3_write_enabled ? 'on' : 'off']">
        候选写入：{{ gates.phase3_write_enabled ? '已启用' : '默认关闭' }}
      </span>
      <span :class="['gate', gates.release_enabled ? 'on' : 'off']">
        生效与回退：{{ gates.release_enabled ? '已启用' : '默认关闭' }}
      </span>
    </div>

    <p v-if="message" class="message">{{ message }}</p>
    <div v-if="loading" class="state-box" role="status">正在读取...</div>

    <div v-else-if="loadError" class="message" role="alert">{{ loadError }} <button class="btn" @click="loadAll">重新读取</button></div>
    <template v-else-if="loaded">
      <section class="panel">
        <div class="panel-head">
          <h2>跨尝试问题组</h2>
          <span class="muted">同一尝试、同类型、同争议只计一个实例。</span>
        </div>

        <div class="form-row">
          <input v-model="groupForm.title" placeholder="问题组名称" />
          <select v-model="groupForm.category">
            <option value="recognition">识别反馈</option>
            <option value="decision">决策反馈</option>
            <option value="teaching">教学反馈</option>
          </select>
          <select v-model="groupForm.issue_type" aria-label="问题类型">
            <option v-for="item in issueTypeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
          <input v-model.number="groupForm.days" type="number" min="1" placeholder="时间窗天数" />
          <button class="btn btn-secondary btn-small" @click="createGroup">生成候选成员</button>
        </div>

        <div v-if="!groups.length" class="muted">暂无问题组。</div>
        <article v-for="group in groups" :key="group.group_id" class="item">
          <div class="item-head">
            <div>
              <strong>{{ group.title }}</strong>
              <span class="badge" :class="group.status">{{ group.status_label }}</span>
              <p class="muted small">
                {{ group.category_label }} · {{ group.issue_type_label }}
                <template v-if="group.task_key"> · {{ taskTitle(group.task_key) }}</template>
              </p>
              <p class="counts">
                原始 {{ group.counts?.raw_feedback ?? '未提供' }} ·
                纳入 {{ group.counts?.included_feedback ?? '未提供' }} ·
                去重实例 {{ group.counts?.deduplicated_instances ?? '未提供' }} ·
                不同学生 {{ group.counts?.distinct_students ?? '未提供' }} ·
                缺证 {{ group.counts?.missing_evidence ?? '未提供' }}
              </p>
            </div>
            <div class="item-actions">
              <button
                v-if="group.status === 'pending_confirmation' || group.status === 'draft'"
                class="btn btn-small"
                @click="confirmGroup(group)"
              >确认</button>
            </div>
          </div>
        </article>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>教学配置候选</h2>
          <span class="muted">草稿 → 待评测 → 评测中 → 待审批 → 已批准待发布 → 观察中 → 已稳定 / 已回退</span>
        </div>

        <div class="form-row">
          <input v-model="candidateForm.title" placeholder="候选名称" />
          <select v-model="candidateForm.issue_group_ids" multiple size="4" aria-label="关联问题组">
            <option v-for="group in groups" :key="group.group_id" :value="group.group_id">
              {{ group.title }} · {{ group.status_label }}
            </option>
          </select>
          <p class="muted">基准、候选及回退版本由配置文件提供，提交时核对。</p>
          <ReferenceImport title="改动因素" :fields="factorFields" :model-value="{ single_changed_factor: candidateForm.single_changed_factor }" @update:model-value="Object.assign(candidateForm, $event)" />
          <label class="btn">导入真实候选配置
            <input type="file" accept=".json,application/json" aria-label="导入真实候选配置" @change="importConfiguration" />
          </label>
          <button class="btn btn-primary btn-small" :disabled="creatingCandidate" @click="createCandidate">登记草稿</button>
          <p class="muted">请由配置负责人提供包含基准与候选配置、改动因素、回退版本和适用任务的文件；可同时包含名称、问题组、排除范围与预期风险。导入仅准备草稿，提交前仍需核对。</p>
          <RecordView v-if="configurationImported" :value="candidateForm" title="导入的候选配置" />
        </div>

        <div v-if="!candidates.length" class="muted">暂无候选。</div>
        <article v-for="candidate in candidates" :key="candidate.candidate_id" class="item">
          <div class="item-head">
            <div>
              <strong>{{ candidate.title }}</strong>
              <span class="badge" :class="candidate.state">{{ candidate.state_label }}</span>
              <p class="muted small">
                {{ configurationVersionLabel(candidate.baseline_config_version) }} → {{ configurationVersionLabel(candidate.candidate_config_version) }}
                · 改动 {{ changedFactorLabel(candidate.single_changed_factor) }}
              </p>
              <p class="muted small">
                <template v-if="candidate.evaluation_report_ref?.report_id">
                  评测报告：第 {{ candidate.evaluation_report_ref?.report_version }} 版 ·
                  {{ reportRecommendationLabel(candidate.evaluation_report_ref?.recommendation) }}
                </template>
                <template v-else>尚未登记评测报告</template>
              </p>
              <p v-if="!candidate.approval_valid && candidate.state === 'approved_pending_release'" class="warn small">
                审批已失效：{{ approvalReasonLabel(candidate.approval_invalid_reason) }}
              </p>
              <RecordView :value="candidate" title="候选配置与审批依据" />
            </div>
            <div class="item-actions">
              <button v-if="candidate.state === 'draft'" class="btn btn-small" @click="submitCandidate(candidate)">提交评测</button>
              <template v-if="candidate.state === 'pending_eval'">
                <label class="btn">导入真实评测报告引用
                  <input type="file" accept=".json,application/json" :aria-label="`导入${candidate.title}评测报告引用`" @change="importReport(candidate, $event)" />
                </label>
                <p class="muted">请由评测负责人提供实际报告引用文件，保留原报告的版本、建议、完成情况和缺失案例数。导入不代表评测通过，提交后仍需核对来源与放行条件。</p>
                <RecordView v-if="reportImports[candidate.candidate_id]" :value="reportImports[candidate.candidate_id]" title="待登记的报告引用" />
                <button class="btn btn-small" :disabled="!reportImports[candidate.candidate_id] || attachingReports[candidate.candidate_id]" @click="attachReport(candidate)">登记报告</button>
              </template>
              <button v-if="candidate.state === 'evaluating'" class="btn btn-small" @click="completeEvaluation(candidate)">完成评测</button>
              <button v-if="candidate.state === 'pending_approval'" class="btn btn-small" @click="approve(candidate)">审批</button>
              <button v-if="candidate.state === 'approved_pending_release'" class="btn btn-secondary btn-small" @click="activate(candidate)">生效</button>
              <button v-if="candidate.state === 'observing'" class="btn btn-small" @click="markStable(candidate)">标记稳定</button>
              <button
                v-if="candidate.state === 'observing' || candidate.state === 'stable'"
                class="btn btn-small danger"
                @click="rollback(candidate)"
              >回退</button>
            </div>
          </div>
        </article>
      </section>
    </template>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import service from './feedback/api.js'
import ReferenceImport from '@/shared/forms/ReferenceImport.vue'
import RecordView from '@/shared/forms/RecordView.vue'
import { feedbackError } from './feedbackPresentation.js'
import { configurationVersionLabel, changedFactorLabel, approvalReasonLabel } from './candidatePresentation.js'
import { parseCandidateConfiguration, parseCandidateReport, validateCandidateConfiguration, validateCandidateReport } from './feedback/candidateImport.js'

const { embedded } = defineProps({ embedded: { type: Boolean, default: false } })
const emit = defineEmits(['ready'])
const loaded = ref(false)
const loadError = ref('')
let loadRead = 0
let alive = true
onBeforeUnmount(() => { alive = false; ++loadRead })

const factorFields = [{ key: 'single_changed_factor', label: '改动因素' }]

const loading = ref(true)
const message = ref('')
const groups = ref([])
const candidates = ref([])
const gates = reactive({ phase3_write_enabled: false, release_enabled: false })
const groupForm = reactive({ title: '', category: 'teaching', issue_type: 'scoring_dispute', days: 7 })
const issueTypeOptions = [
  { value: 'scoring_dispute', label: '评分争议' },
  { value: 'false_positive', label: '误报' }, { value: 'false_negative', label: '漏报' },
  { value: 'classification_correction', label: '分类修正' },
  { value: 'hint_ineffective', label: '提示无效' }, { value: 'wrong_attribution', label: '错误归因' },
  { value: 'assistance_misrecorded', label: '受助误记' }, { value: 'retest_not_maintained', label: '复测未保持' },
  { value: 'catalog_or_recommendation', label: '目录或推荐问题' },
  { value: 'material_issue', label: '材料问题' }, { value: 'other', label: '其他问题' },
]
const taskTitles = ref({})
function taskTitle(key) {
  return taskTitles.value[key] || '任务名称暂不可用'
}
const candidateForm = reactive({
  title: '',
  issue_group_ids: [],
  baseline_config_version: '',
  candidate_config_version: '',
  single_changed_factor: '',
  rollback_version: '',
  target_task_versions: null,
  baseline_config: null,
  candidate_config: null,
})
const configurationImported = ref(false)
const creatingCandidate = ref(false)
const reportImports = reactive({})
const attachingReports = reactive({})
let configurationRead = 0
const reportReads = new Map()
async function readImport(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return null
  if (file.size > 1024 * 1024) throw new Error('文件过大，请导入不超过 1 MB 的 JSON 资料。')
  try { return await file.text() } catch { throw new Error('文件未能读取，请重试。') }
}
async function importConfiguration(event) {
  if (!event.target.files?.[0] || creatingCandidate.value) return
  const current = ++configurationRead
  configurationImported.value = false
  candidateForm.baseline_config = null
  candidateForm.candidate_config = null
  candidateForm.target_task_versions = null
  try {
    const text = await readImport(event)
    if (!alive || current !== configurationRead || text === null) return
    const payload = parseCandidateConfiguration(text)
    // Optional values from an earlier import must not leak into its replacement.
    delete candidateForm.excluded_scope
    delete candidateForm.expected_risk
    Object.assign(candidateForm, payload)
    configurationImported.value = true
    message.value = '真实候选配置已导入，请核对问题组与全部字段后登记。'
  } catch (err) {
    if (alive && current === configurationRead) message.value = err.message
  }
}
async function importReport(candidate, event) {
  const id = candidate.candidate_id
  if (!event.target.files?.[0] || attachingReports[id]) return
  const current = (reportReads.get(id) || 0) + 1
  reportReads.set(id, current)
  delete reportImports[id]
  try {
    const text = await readImport(event)
    if (!alive || reportReads.get(id) !== current || text === null) return
    reportImports[id] = parseCandidateReport(text)
    message.value = '报告引用已导入，尚未登记或核验；请核对原报告。'
  } catch (err) {
    if (alive && reportReads.get(id) === current) message.value = err.message
  }
}

const reportRecommendationLabels = { pass: '建议通过', fail: '建议不通过', insufficient_evidence: '证据不足', revise: '建议修订', pending: '待评测' }
const reportRecommendationLabel = value => reportRecommendationLabels[value] || '结论待确认'

function extractError(err) {
  const data = err?.response?.data
  if (data?.code === 'phase3_write_disabled') return '候选登记暂未开放，请联系管理员确认开放安排。'
  if (data?.code === 'phase3_release_disabled') return '生效与回退暂未开放，请联系管理员确认开放安排。'
  return feedbackError(err, '操作未完成，请核对候选资料与审批条件后重试。')
}

async function loadAll() {
  const current = ++loadRead
  loading.value = true
  loadError.value = ''
  try {
    const [groupPayload, candidatePayload, catalog] = await Promise.all([
      service.feedbackPhase3.issueGroups(),
      service.feedbackPhase3.candidates(),
      service.learningMap.catalog().catch(() => null),
    ])
    if (!alive || current !== loadRead) return
    if (!Array.isArray(groupPayload?.items) || !Array.isArray(candidatePayload?.items)) throw new Error('Incomplete candidates')
    groups.value = groupPayload.items
    candidates.value = candidatePayload.items
    loaded.value = true
    const titles = {}
    for (const capability of catalog?.capabilities || []) {
      for (const task of capability.tasks || []) {
        if (task?.task_key) titles[task.task_key] = task.title
      }
    }
    taskTitles.value = titles
    gates.phase3_write_enabled = Boolean(groupPayload.phase3_write_enabled)
    gates.release_enabled = Boolean(groupPayload.release_enabled)
  } catch (err) {
    if (alive && current === loadRead) loadError.value = extractError(err)
  } finally {
    if (alive && current === loadRead) loading.value = false
  }
}

async function createGroup() {
  const now = new Date()
  try {
    await service.feedbackPhase3.createIssueGroup({
      title: groupForm.title || '教学问题组',
      category: groupForm.category,
      issue_type: groupForm.issue_type,
      window_start: new Date(now.getTime() - groupForm.days * 86400000).toISOString(),
      window_end: now.toISOString(),
    })
    message.value = '问题组已生成候选成员，需人工确认。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function confirmGroup(group) {
  try {
    await service.feedbackPhase3.confirmIssueGroup(group.group_id, {})
    message.value = '问题组已确认；计数已快照。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function createCandidate() {
  if (creatingCandidate.value) return
  const groupIds = [...candidateForm.issue_group_ids]
  if (!groupIds.length) {
    message.value = '请至少选择一个已确认的问题组。'
    return
  }
  let payload
  try {
    validateCandidateConfiguration(candidateForm)
    payload = JSON.parse(JSON.stringify({ ...candidateForm, issue_group_ids: groupIds }))
  } catch (err) {
    message.value = err.message
    return
  }
  creatingCandidate.value = true
  try {
    await service.feedbackPhase3.createCandidate(payload)
    if (!alive) return
    candidateForm.issue_group_ids = []
    message.value = '候选草稿已登记。'
    await loadAll()
  } catch (err) {
    if (alive) message.value = extractError(err)
  } finally {
    if (alive) creatingCandidate.value = false
  }
}

async function submitCandidate(candidate) {
  try {
    await service.feedbackPhase3.submitCandidate(candidate.candidate_id)
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function attachReport(candidate) {
  const id = candidate.candidate_id
  if (attachingReports[id]) return
  let report
  try {
    report = JSON.parse(JSON.stringify(validateCandidateReport(reportImports[id])))
  } catch (err) {
    message.value = err.message
    return
  }
  attachingReports[id] = true
  try {
    await service.feedbackPhase3.attachCandidateReport(id, report)
    if (!alive) return
    message.value = '报告引用已登记，请在评测完成后继续核对。'
    await loadAll()
  } catch (err) {
    if (alive) message.value = extractError(err)
  } finally {
    if (alive) attachingReports[id] = false
  }
}

async function completeEvaluation(candidate) {
  try {
    await service.feedbackPhase3.completeCandidateEvaluation(candidate.candidate_id, {})
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function approve(candidate) {
  try {
    await service.feedbackPhase3.approveCandidate(candidate.candidate_id, {
      scope: '合成案例教学回放',
      observation_window: '14 天',
      rollback_condition: '关键授权反例失败即回退',
    })
    message.value = '已审批；候选作者不能独自审批。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function activate(candidate) {
  try {
    await service.feedbackPhase3.activateCandidate(candidate.candidate_id, {
      applicable_future_tasks: candidate.target_task_versions,
    })
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function markStable(candidate) {
  try {
    await service.feedbackPhase3.markCandidateStable(candidate.candidate_id, { note: '观察期无未解释退化' })
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function rollback(candidate) {
  try {
    await service.feedbackPhase3.rollbackCandidate(candidate.candidate_id, {
      reason: '人工确认关键反例失败',
      result: 'success',
    })
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

onMounted(async () => {
  await loadAll()
  if (alive) emit('ready')
})
</script>

<style scoped>
.candidate-page { width: 100%; max-width: var(--table-width); margin: 0 auto; padding: var(--density-gap); box-sizing: border-box; color: var(--ink); }
.candidate-embedded { max-width: none; padding: 0; }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: var(--density-gap); margin-bottom: var(--space-2); }
.eyebrow, .muted, .small, .counts { font-size: var(--text-caption); color: var(--ink-secondary); }
h1 { font-family: var(--font-family); font-size: var(--text-page); line-height: var(--leading-tight); }
.subtitle { color: var(--ink-secondary); margin-top: var(--space-1); max-width: var(--reading-width); }
.btn { border: var(--stroke) solid var(--line); background: var(--surface); color: var(--ink); border-radius: var(--radius-pill); padding: var(--space-1) var(--space-2); font: inherit; min-height: var(--control-height); cursor: pointer; }
.btn-primary { background: var(--button-primary); color: var(--on-action); }
.btn:hover:not(:disabled) { background: var(--surface-hover); }
.btn-primary:hover:not(:disabled) { background: var(--button-primary-hover); }
.btn-primary:active:not(:disabled) { background: var(--button-primary-pressed); }
.btn-small { font-size: var(--text-caption); }
.btn.danger { color: var(--negative); }
.btn:disabled { background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
.gates { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-bottom: var(--space-2); }
.gate, .badge { font-size: var(--text-caption); padding: var(--space-1); background: var(--surface-muted); border-radius: var(--radius-pill); color: var(--ink-secondary); }
.gate.on, .badge.confirmed, .badge.stable { color: var(--positive); background: var(--positive-soft); }
.gate.off, .warn, .badge.pending_confirmation, .badge.pending_approval, .badge.approved_pending_release { color: var(--warning); background: var(--warning-soft); }
.badge.rolled_back, .badge.withdrawn, .badge.rejected { color: var(--negative); background: var(--negative-soft); }
.panel { background: var(--surface); border-radius: var(--radius-panel); padding: var(--density-gap); margin-bottom: var(--space-2); }
.candidate-embedded .panel { padding: var(--density-gap) 0; border-radius: 0; }
.panel h2 { font-family: var(--font-family); font-size: var(--text-card); }
.panel-head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: var(--space-1); margin-bottom: var(--space-2); }
.form-row { display: flex; gap: var(--space-1); flex-wrap: wrap; margin-bottom: var(--space-2); }
.form-row input, .form-row select { border: var(--stroke) solid var(--line); padding: var(--space-1); background: var(--surface); color: var(--ink); border-radius: var(--radius-control); font: inherit; min-height: var(--control-height); min-width: 0; max-width: 100%; box-sizing: border-box; }
.item { border-top: var(--stroke) solid var(--line); padding: var(--space-2) 0; overflow-wrap: anywhere; }
.item-head { display: flex; justify-content: space-between; gap: var(--space-2); align-items: flex-start; }
.item-actions { display: flex; gap: var(--space-1); flex-wrap: wrap; justify-content: flex-end; }
.message { background: var(--surface-muted); padding: var(--space-2); font-size: var(--text-caption); margin-bottom: var(--space-2); border-radius: var(--radius-control); }
.state-box { background: var(--surface); padding: var(--space-6); text-align: center; color: var(--ink-secondary); }
.candidate-page :is(button, input, select):focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
@media (max-width: 768px) { .item-head { flex-direction: column; } .form-row > input, .form-row > select { width: 100%; } .item-actions { justify-content: flex-start; } }
</style>
