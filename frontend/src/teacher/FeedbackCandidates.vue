<template>
  <div class="candidate-page">
    <div class="page-header">
      <div>
        <span class="eyebrow">教学 · 候选改进</span>
        <h1 v-if="!embedded">问题组与候选管理</h1>
        <p class="subtitle">
          问题组必须人工确认成员；候选只能引用已确认、无缺证的问题组。审批绑定确切配置摘要与模块八报告，发布只影响后续任务。
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
    <div v-if="loading" class="state-box">正在读取...</div>

    <p v-if="loadError" class="message" role="alert">{{ loadError }}</p>
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
          <input v-model="groupForm.issue_type" placeholder="问题类型，如 scoring_dispute" />
          <input v-model.number="groupForm.days" type="number" min="1" placeholder="时间窗天数" />
          <button class="btn btn-primary btn-small" :disabled="!gates.phase3_write_enabled || writing" @click="createGroup">生成候选成员</button>
        </div>

        <div v-if="!groups.length" class="muted">暂无问题组。</div>
        <article v-for="group in groups" :key="group.group_id" class="item">
          <div class="item-head">
            <div>
              <strong>{{ group.title }}</strong>
              <span class="badge" :class="group.status">{{ group.status_label }}</span>
              <p class="muted small">
                {{ group.category_label }} · {{ group.issue_type_label }}
                <template v-if="group.task_key"> · {{ group.task_title || '已关联任务' }} · {{ configurationVersionLabel(group.task_version) }}</template>
              </p>
              <p class="counts">
                原始 {{ group.counts.raw_feedback ?? 0 }} ·
                纳入 {{ group.counts.included_feedback ?? 0 }} ·
                去重实例 {{ group.counts.deduplicated_instances ?? 0 }} ·
                不同学生 {{ group.counts.distinct_students ?? 0 }} ·
                缺证 {{ group.counts.missing_evidence ?? 0 }}
              </p>
            </div>
            <div class="item-actions">
              <button
                v-if="group.status === 'pending_confirmation' || group.status === 'draft'"
                class="btn btn-small"
                :disabled="!gates.phase3_write_enabled || writing" @click="confirmGroup(group)"
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
          <label>导入候选配置 JSON<input type="file" accept="application/json,.json" :disabled="creatingCandidate" @change="importConfiguration" /></label>
          <label>关联问题组<select v-model="candidateForm.issue_group_ids" multiple><option v-for="id in candidateForm.issue_group_ids.filter(id => !groups.some(group => group.group_id === id))" :key="id" :value="id">已导入关联问题组</option><option v-for="group in groups" :key="group.group_id" :value="group.group_id">{{ group.title }}</option></select></label>
          <input v-model="candidateForm.baseline_config_version" placeholder="基准配置版本" />
          <input v-model="candidateForm.candidate_config_version" placeholder="候选配置版本" />
          <input v-model="candidateForm.single_changed_factor" placeholder="唯一改动因素" />
          <input v-model="candidateForm.rollback_version" placeholder="回退版本" />
          <button class="btn btn-primary btn-small" :disabled="!gates.phase3_write_enabled || creatingCandidate || !configurationImported" @click="createCandidate">登记草稿</button>
        </div>

        <p class="muted">请导入不超过 1 MB 的真实配置。替换文件失败后须重新导入；文件只校验格式，来源与适用范围由服务端核查。</p>
        <RecordView v-if="configurationImported" :value="candidateForm" title="待登记配置完整记录" />
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
              <p v-if="!candidate.approval_valid && candidate.state === 'approved_pending_release'" class="warn small">
                审批已失效：{{ approvalReasonLabel(candidate.approval_invalid_reason) }}
              </p>
            </div>
            <div class="item-actions">
              <button v-if="candidate.state === 'draft'" class="btn btn-small" :disabled="!gates.phase3_write_enabled || writing" @click="submitCandidate(candidate)">提交评测</button>
              <template v-if="candidate.state === 'pending_eval'"><label>导入真实评测报告引用<input type="file" accept="application/json,.json" :disabled="attachingReports[candidate.candidate_id]" @change="importReport(candidate, $event)" /></label><button class="btn btn-small" :disabled="!gates.phase3_write_enabled || attachingReports[candidate.candidate_id] || !reportImports[candidate.candidate_id]" @click="attachReport(candidate)">登记报告</button><RecordView v-if="reportImports[candidate.candidate_id]" :value="reportImports[candidate.candidate_id]" title="待登记报告完整记录" /></template>
              <button v-if="candidate.state === 'evaluating'" class="btn btn-small" :disabled="!gates.phase3_write_enabled || writing" @click="completeEvaluation(candidate)">完成评测</button>
              <template v-if="candidate.state === 'pending_approval'"><label>审批范围<input v-model="actionDraft(candidate).scope" /></label><label>观察窗口<input v-model="actionDraft(candidate).observation_window" /></label><label>回退条件<input v-model="actionDraft(candidate).rollback_condition" /></label><button class="btn btn-small" :disabled="!gates.phase3_write_enabled || writing" @click="approve(candidate)">审批</button></template>
              <button v-if="candidate.state === 'approved_pending_release'" class="btn btn-primary btn-small" :disabled="!gates.release_enabled || writing" @click="activate(candidate)">生效</button>
              <template v-if="candidate.state === 'observing'"><label>实际观察结论<input v-model="actionDraft(candidate).note" /></label><button class="btn btn-small" :disabled="!gates.phase3_write_enabled || writing" @click="markStable(candidate)">登记稳定结论</button></template>
              <label v-if="['observing', 'stable'].includes(candidate.state)">实际回退原因<input v-model="actionDraft(candidate).reason" /></label><label v-if="['observing', 'stable'].includes(candidate.state)">实际回退结果<select v-model="actionDraft(candidate).result"><option value="">请选择实际结果</option><option value="success">已成功</option><option value="failure">失败</option></select></label>
              <button
                v-if="candidate.state === 'observing' || candidate.state === 'stable'"
                :disabled="!gates.release_enabled || writing"
                class="btn btn-small danger"
                @click="rollback(candidate)"
              >回退</button>
            </div>
          </div>
          <RecordView :value="candidate" title="候选完整记录" />
        </article>
      </section>
    </template>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import service from './feedback/api.js'
import { parseCandidateConfiguration, parseCandidateReport, validateCandidateConfiguration, validateCandidateReport } from './feedback/candidateImport.js'
import { feedbackError, feedbackLabel } from './feedbackPresentation.js'
import { configurationVersionLabel, changedFactorLabel, approvalReasonLabel } from './candidatePresentation.js'
import RecordView from '../shared/forms/RecordView.vue'

const props = defineProps({ embedded: Boolean })
const embedded = props.embedded
const emit = defineEmits(['ready'])
const loading = ref(true), loaded = ref(false), loadError = ref(''), message = ref('')
const groups = ref([]), candidates = ref([])
const gates = reactive({ phase3_write_enabled: false, release_enabled: false })
const groupForm = reactive({ title: '', category: 'teaching', issue_type: 'scoring_dispute', days: 7 })
const candidateForm = reactive({ title: '', issue_group_ids: [], baseline_config_version: '', candidate_config_version: '', single_changed_factor: '', rollback_version: '' })
const configurationImported = ref(false), creatingCandidate = ref(false), writing = ref(false)
const reportImports = reactive({}), attachingReports = reactive({}), actionDrafts = reactive({})
const factorFields = ['single_changed_factor']
let alive = true, loadRead = 0, configurationRead = 0
const reportReads = new Map()
onBeforeUnmount(() => { alive = false; ++loadRead; ++configurationRead; reportReads.clear() })
const clone = value => JSON.parse(JSON.stringify(value))
function extractError(err) {
  if (err?.response?.data?.code === 'phase3_write_disabled') return '候选管理暂未开放，请在完成评测与审批后由负责人决定开启。'
  if (err?.response?.data?.code === 'phase3_release_disabled') return '生效与回退暂未开放，请由负责人核对开放条件。'
  return feedbackError(err, '操作未完成，请核对资料或稍后重试。')
}
function actionDraft(candidate) {
  return actionDrafts[candidate.candidate_id] ||= { scope: '', observation_window: '', rollback_condition: '', note: '', reason: '', result: '' }
}
async function loadAll() {
  if (!alive) return
  const read = ++loadRead
  loading.value = true; loaded.value = false; loadError.value = ''
  try {
    const [groupPayload, candidatePayload] = await Promise.all([service.feedbackPhase3.issueGroups(), service.feedbackPhase3.candidates()])
    if (!alive || read !== loadRead) return
    if (!Array.isArray(groupPayload.items) || !Array.isArray(candidatePayload.items)) throw new Error('Incomplete response')
    groups.value = groupPayload.items; candidates.value = candidatePayload.items
    gates.phase3_write_enabled = groupPayload.phase3_write_enabled === true
    gates.release_enabled = groupPayload.release_enabled === true
    loaded.value = true
  } catch (err) {
    if (alive && read === loadRead) { groups.value = []; candidates.value = []; gates.phase3_write_enabled = false; gates.release_enabled = false; loadError.value = extractError(err) }
  } finally {
    if (alive && read === loadRead) { loading.value = false; emit('ready') }
  }
}
async function importConfiguration(event) {
  if (!alive || creatingCandidate.value) return
  const read = ++configurationRead
  configurationImported.value = false
  const file = event?.target?.files?.[0]
  if (!file) return
  let text
  try { if (file.size > 1024 * 1024) throw new Error('large'); text = await file.text() }
  catch { if (alive && read === configurationRead) message.value = file.size > 1024 * 1024 ? '文件过大，请导入不超过 1 MB 的 JSON 资料。' : '文件未能读取，请重新选择真实资料。'; return }
  if (!alive || read !== configurationRead) return
  try {
    const imported = parseCandidateConfiguration(text)
    for (const key of Object.keys(candidateForm)) if (!['title', 'issue_group_ids'].includes(key)) delete candidateForm[key]
    Object.assign(candidateForm, imported)
    configurationImported.value = true; message.value = '配置已导入，请核对原始内容后登记。'
  } catch (err) { message.value = err.message }
  finally { if (event?.target) event.target.value = '' }
}
async function importReport(candidate, event) {
  if (!alive || attachingReports[candidate.candidate_id]) return
  const id = candidate.candidate_id, read = (reportReads.get(id) || 0) + 1
  reportReads.set(id, read); delete reportImports[id]
  const file = event?.target?.files?.[0]
  if (!file) return
  let text
  try { if (file.size > 1024 * 1024) throw new Error('large'); text = await file.text() }
  catch { if (alive && reportReads.get(id) === read) message.value = file.size > 1024 * 1024 ? '文件过大，请导入不超过 1 MB 的 JSON 资料。' : '文件未能读取，请重新选择真实报告。'; return }
  if (!alive || reportReads.get(id) !== read) return
  try { reportImports[id] = parseCandidateReport(text); message.value = '报告引用已导入；其来源与结论由服务端核查。' }
  catch (err) { message.value = err.message }
  finally { if (event?.target) event.target.value = '' }
}
async function createCandidate() {
  if (!alive || creatingCandidate.value) return
  if (!configurationImported.value) { message.value = '请先导入真实候选配置。'; return }
  let payload
  try { payload = clone(validateCandidateConfiguration({ ...candidateForm, single_changed_factor: candidateForm.single_changed_factor })); if (!payload.title?.trim() || !payload.issue_group_ids?.length) throw new Error('请填写候选名称并选择关联问题组。') }
  catch (err) { message.value = err.message; return }
  creatingCandidate.value = true
  try { await service.feedbackPhase3.createCandidate(payload); if (alive) { message.value = '候选草稿已登记。'; await loadAll() } }
  catch (err) { if (alive) message.value = extractError(err) }
  finally { if (alive) creatingCandidate.value = false }
}
async function attachReport(candidate) {
  const id = candidate.candidate_id
  if (!alive || attachingReports[id]) return
  let payload
  try { payload = clone(validateCandidateReport(reportImports[id])) }
  catch (err) { message.value = err.message; return }
  attachingReports[id] = true
  try { await service.feedbackPhase3.attachCandidateReport(id, payload); if (alive) { message.value = '报告引用已登记，尚须核对服务端评测结果。'; await loadAll() } }
  catch (err) { if (alive) message.value = extractError(err) }
  finally { if (alive) attachingReports[id] = false }
}
async function write(action, success) {
  if (!alive || writing.value) return
  writing.value = true; message.value = ''
  try { await action(); if (alive) { message.value = success; await loadAll() } }
  catch (err) { if (alive) message.value = extractError(err) }
  finally { if (alive) writing.value = false }
}
function createGroup() {
  if (!groupForm.title.trim() || !Number.isSafeInteger(groupForm.days) || groupForm.days < 1) { message.value = '请填写问题组名称和有效时间窗。'; return }
  const now = new Date()
  return write(() => service.feedbackPhase3.createIssueGroup({ title: groupForm.title, category: groupForm.category, issue_type: groupForm.issue_type, window_start: new Date(now.getTime() - groupForm.days * 86400000).toISOString(), window_end: now.toISOString() }), '问题组已生成，须人工确认成员。')
}
function confirmGroup(group) { return write(() => service.feedbackPhase3.confirmIssueGroup(group.group_id, {}), '问题组已确认。') }
function submitCandidate(candidate) { return write(() => service.feedbackPhase3.submitCandidate(candidate.candidate_id), '候选已提交评测。') }
function completeEvaluation(candidate) { return write(() => service.feedbackPhase3.completeCandidateEvaluation(candidate.candidate_id, {}), '服务端已处理评测完成请求。') }
function approve(candidate) { const { scope, observation_window, rollback_condition } = actionDraft(candidate); if (![scope, observation_window, rollback_condition].every(value => value.trim())) { message.value = '请填写实际审批范围、观察窗口和回退条件。'; return }; return write(() => service.feedbackPhase3.approveCandidate(candidate.candidate_id, { scope, observation_window, rollback_condition }), '审批已登记，请核对服务端审批状态。') }
function activate(candidate) { return write(() => service.feedbackPhase3.activateCandidate(candidate.candidate_id, { applicable_future_tasks: clone(candidate.target_task_versions) }), '服务端已处理生效请求。') }
function markStable(candidate) { const { note } = actionDraft(candidate); if (!note.trim()) { message.value = '请填写实际观察结论。'; return }; return write(() => service.feedbackPhase3.markCandidateStable(candidate.candidate_id, { note }), '观察结论已登记。') }
function rollback(candidate) { const { reason, result } = actionDraft(candidate); if (!reason.trim() || !result) { message.value = '请填写实际回退原因与结果。'; return }; return write(() => service.feedbackPhase3.rollbackCandidate(candidate.candidate_id, { reason, result }), '回退结果已登记，请核对实际状态。') }
onMounted(loadAll)
</script>

<style scoped>
.candidate-page { width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 36px 0 72px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; border-bottom: 2px solid var(--ink); padding-bottom: 20px; margin-bottom: 16px; }
.eyebrow { font-size: 12px; letter-spacing: .16em; text-transform: uppercase; color: var(--action); font-weight: 700; }
h1 { font-family: "Songti SC", serif; font-size: 38px; line-height: 1.1; }
.subtitle { color: var(--ink-secondary); margin-top: 8px; max-width: 780px; }
.btn { border: 1px solid var(--line); background: var(--surface); padding: 8px 12px; font-weight: 600; cursor: pointer; }
.btn-primary { background: var(--ink); color: var(--surface); }
.btn-small { padding: 5px 10px; font-size: 12px; }
.btn.danger { color: var(--negative); border-color: var(--negative); }
.gates { display: flex; gap: 8px; margin-bottom: 14px; }
.gate { font-size: 12px; padding: 4px 9px; border: 1px solid var(--line); }
.gate.on { color: var(--positive); border-color: var(--positive); }
.gate.off { color: var(--warning); border-color: var(--warning); }
.panel { background: var(--surface); border: 1px solid var(--line); padding: 18px; box-shadow: var(--shadow-raised); margin-bottom: 16px; }
.panel h2 { font-family: "Songti SC", serif; font-size: 20px; }
.panel-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
.form-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.form-row input, .form-row select { border: 1px solid var(--line); padding: 6px 8px; background: var(--surface); font: inherit; }
.item { border-top: 1px solid var(--line); padding: 12px 0; }
.item-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.item-actions { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.muted { color: var(--ink-secondary); font-size: 12px; }
.small { font-size: 12px; }
.mono { font-family: ui-monospace, monospace; font-size: 11px; }
.counts { font-size: 12px; color: var(--ink-secondary); margin-top: 4px; }
.warn { color: var(--warning); }
.badge { font-size: 11px; padding: 1px 7px; border: 1px solid var(--line); margin-left: 6px; }
.badge.confirmed, .badge.stable { color: var(--positive); border-color: var(--positive); }
.badge.pending_confirmation, .badge.pending_approval, .badge.approved_pending_release { color: var(--warning); border-color: var(--warning); }
.badge.rolled_back, .badge.withdrawn, .badge.rejected { color: var(--negative); border-color: var(--negative); }
.message { background: var(--warning-soft); border-left: 3px solid var(--action); padding: 9px 12px; font-size: 13px; margin-bottom: 12px; }
.state-box { background: var(--surface); border: 1px solid var(--line); padding: 48px; text-align: center; color: var(--ink-secondary); }
input:focus-visible, select:focus-visible, button:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.btn:disabled { background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
label { display: grid; gap: var(--space-1); min-width: 0; }
.form-row input, .form-row select { max-width: 100%; box-sizing: border-box; }
</style>
