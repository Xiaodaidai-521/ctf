<template>
  <div class="teacher-review-page">
    <div class="page-header">
      <div>
        <span class="eyebrow">教学 · 验收待办</span>
        <h1>验收与抽查</h1>
        <p class="subtitle">
          开放题必评、常规抽查、评分争议分开处理；抽查不替代必评，也不阻塞已满足条件的结果。
        </p>
      </div>
      <button class="btn btn-secondary" @click="loadAll" :disabled="loading">刷新</button>
    </div>

    <p v-if="message" class="message">{{ message }}</p>
    <div v-if="loading" class="state-box">正在读取...</div>

    <p v-else-if="loadError" class="message" role="alert">{{ loadError }}</p>
    <template v-else>
      <div class="tabs">
        <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="selectTab(tab.key)">
          {{ tab.label }}<span v-if="counts[tab.countKey]" class="count">{{ counts[tab.countKey] }}</span>
        </button>
      </div>

      <!-- 开放题必评 -->
      <section v-if="activeTab === 'manual'" class="panel">
        <h2>开放题必评</h2>
        <div v-if="!manualTasks.length" class="muted">暂无待评。</div>
        <article v-for="task in manualTasks" :key="task.task_id" class="item">
          <div class="item-head">
            <div>
              <strong>{{ task.student.username }} · {{ task.submission.task.title }}</strong>
              <p class="muted small">
                {{ task.status_label }} · 提交 {{ formatDate(task.created_at) }} ·
                {{ task.submission.assistance.independence_label }}
              </p>
            </div>
            <button v-if="task.status === 'pending'" class="btn btn-small" @click="claimManual(task)">认领</button>
          </div>

          <details>
            <summary>查看提交与分项</summary>
            <div class="grid">
              <div><span class="label">程序核验</span>{{ task.submission.program_status_label }}</div>
              <div><span class="label">综合</span>{{ task.submission.overall_status_label }}</div>
              <div><span class="label">帮助层级</span>{{ task.submission.assistance.level_label || '无' }}</div>
              <div><span class="label">帮助来源</span>{{ task.submission.assistance.source_label }}</div>
            </div>
            <RecordView :value="task.submission.items" title="提交分项完整记录" />
            <RecordView :value="task.submission.program_result" title="程序核验完整记录" />
          </details>

          <div v-if="task.status !== 'reviewed' && task.status !== 'corrected'" class="review-form">
            <div v-for="entry in rubricRows" :key="entry.key" class="rubric-row">
              <span>{{ entry.label }}</span>
              <select v-model.number="reviewForms[task.task_id][entry.key].score">
                <option :value="0">0</option>
                <option :value="1">1</option>
                <option :value="2">2</option>
              </select>
              <input v-model="reviewForms[task.task_id][entry.key].evidence" placeholder="证据定位" />
              <input v-model="reviewForms[task.task_id][entry.key].reason" placeholder="理由" />
            </div>
            <div class="review-actions">
              <select v-model="reviewForms[task.task_id].decision">
                <option value="pass">通过</option>
                <option value="fail">未通过</option>
              </select>
              <input v-model="reviewForms[task.task_id].remarks" placeholder="评阅说明（必填）" />
              <button class="btn btn-primary btn-small" @click="submitManual(task)">提交评阅</button>
            </div>
          </div>
          <div v-else class="muted small">
            已评阅：{{ task.decision === 'pass' ? '通过' : '未通过' }} · 总分 {{ task.total_score }}
          </div>
        </article>
      </section>

      <!-- 常规抽查 -->
      <section v-if="activeTab === 'sampling'" class="panel">
        <h2>常规抽查</h2>
        <div class="batch-form">
          <input v-model="batchForm.title" placeholder="批次名称" />
          <input v-model="batchForm.basis" placeholder="抽样依据（必填）" />
          <input v-model.number="batchForm.sample_size" type="number" min="0" placeholder="随机样本数" />
          <input v-model.number="batchForm.high_risk_size" type="number" min="0" placeholder="高风险样本数" />
          <input v-model.number="batchForm.random_seed" type="number" placeholder="随机种子" />
          <input v-model.number="batchForm.days" type="number" min="1" placeholder="时间窗天数" />
          <button class="btn btn-primary btn-small" @click="createBatch">建立批次</button>
        </div>

        <div v-if="!samplingItems.length" class="muted">暂无抽查项。</div>
        <article v-for="item in samplingItems" :key="item.item_id" class="item">
          <div class="item-head">
            <div>
              <strong>{{ item.student }} · {{ item.task_title }}</strong>
              <p class="muted small">
                {{ item.batch_title }} · {{ selectionLabel(item.selection_reason) }}
                <template v-if="item.risk_reasons?.length"> · {{ item.risk_reasons.map(riskLabel).join('、') }}</template>
                <template v-if="item.overdue"> · 已超期</template>
              </p>
            </div>
            <div class="item-actions">
              <button v-if="item.status === 'pending'" class="btn btn-small" @click="claimSampling(item)">认领</button>
              <button v-if="item.status === 'claimed'" class="btn btn-primary btn-small" :disabled="samplingWriting[item.item_id]" @click="completeSampling(item)">完成复核</button>
            </div>
          </div>
          <div v-if="item.status === 'claimed'" class="review-form"><p>逐项确认你实际完成的核对；未核对项保持未选中。</p><label><input v-model="samplingForm(item).evidence_checked" type="checkbox" />已核对证据</label><label><input v-model="samplingForm(item).verifier_checked" type="checkbox" />已核对核验器</label><label><input v-model="samplingForm(item).rubric_checked" type="checkbox" />已核对量表</label><label><input v-model="samplingForm(item).help_checked" type="checkbox" />已核对帮助记录</label><label><input v-model="samplingForm(item).independence_checked" type="checkbox" />已核对独立性</label><label>实际结论<input v-model="samplingForm(item).conclusion" /></label><label>说明<input v-model="samplingForm(item).notes" /></label></div>
          <p v-if="item.status === 'completed'" class="muted small">已完成复核。</p>
        </article>
      </section>

      <!-- 争议 -->
      <section v-if="activeTab === 'disputes'" class="panel">
        <h2>评分争议</h2>
        <div v-if="!disputes.length" class="muted">暂无争议。</div>
        <article v-for="item in disputes" :key="item.dispute_id" class="item">
          <div class="item-head">
            <div>
              <strong>{{ item.student }} · {{ item.task_title }}</strong>
              <p class="muted small">{{ item.status_label }} · {{ formatDate(item.created_at) }}</p>
              <p>{{ item.reason }}</p>
            </div>
          </div>
          <div v-if="item.status !== 'resolved' && item.status !== 'rejected'" class="review-actions">
            <select v-model="disputeForms[item.dispute_id].status">
              <option value="resolved">已解决</option>
              <option value="rejected">驳回</option>
            </select>
            <input v-model="disputeForms[item.dispute_id].resolution" placeholder="处理结论（必填）" />
            <button class="btn btn-primary btn-small" @click="resolveDispute(item)">提交</button>
          </div>
          <p v-else class="muted small">处理结论：{{ item.resolution }}</p>
        </article>
      </section>

      <!-- 复测与统计 -->
      <section v-if="activeTab === 'retest'" class="panel">
        <h2>复测安排</h2>
        <div class="item-actions">
          <button class="btn btn-secondary btn-small" @click="processDue">按当前时间推进到期状态</button>
        </div>
        <p class="muted small">只推进日期状态，不代表学习保持效果。</p>
        <div v-if="!retests.length" class="muted">暂无复测安排。</div>
        <article v-for="item in retests" :key="item.assignment_id" class="item">
          <div class="item-head">
            <div>
              <strong>{{ item.student.username }} · {{ item.task ? item.task.title : '待补题' }}</strong>
              <p class="muted small">
                {{ item.status_label }} · 到期 {{ formatDate(item.due_at) }}
                <template v-if="item.outcome_label"> · {{ item.outcome_label }}</template>
              </p>
            </div>
            <span class="badge">{{ selectionLabel(item.selection_reason) }}</span>
          </div>
        </article>
      </section>

      <section v-if="activeTab === 'stats'" class="panel">
        <h2>统计口径</h2>
        <div class="grid">
          <div><span class="label">首次有效尝试</span>{{ stats?.first_effective_attempts?.total ?? '—' }}</div>
          <div><span class="label">待教师评阅</span>{{ stats?.first_effective_attempts?.pending_manual ?? '—' }}</div>
          <div><span class="label">独立性未知</span>{{ stats?.first_effective_attempts?.unknown_independence ?? '—' }}</div>
          <div><span class="label">独立通过率</span>{{ rateText(stats?.platform_independent_pass) }}</div>
          <div><span class="label">复测保持率</span>{{ rateText(stats?.retest?.retention) }}</div>
          <div><span class="label">待补题</span>{{ stats?.retest?.pending_item ?? '—' }}</div>
        </div>
        <p class="muted small">
          分母为 0 时显示“暂无数据”，不补成 0；执行能力首期未开展，不进入分子或分母。
        </p>
        <details>
          <summary>固定回归样例（交模块八）</summary>
          <RecordView :value="regression" title="固定回归样例完整记录" />
        </details>
      </section>
    </template>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { feedbackLabel, feedbackDate, feedbackError } from './feedbackPresentation.js'
import RecordView from '../shared/forms/RecordView.vue'
import service from '@/api'

const tabs = [
  { key: 'manual', label: '开放题必评', countKey: 'manual_pending' },
  { key: 'sampling', label: '常规抽查', countKey: 'sampling_pending' },
  { key: 'disputes', label: '评分争议', countKey: 'disputes_pending' },
  { key: 'retest', label: '复测安排', countKey: '' },
  { key: 'stats', label: '统计口径', countKey: '' },
]
const route = useRoute(), router = useRouter()
function tabPreset(value) { return typeof value === 'string' && tabs.some(tab => tab.key === value) ? value : 'manual' }
const activeTab = ref(tabPreset(route.query.tab))
function selectTab(key) { return router.replace({ path: route.path, query: { ...route.query, tab: tabPreset(key) }, hash: route.hash }) }
watch(() => route.query.tab, value => { activeTab.value = tabPreset(value) })
const loading = ref(true)
const message = ref('')
const counts = reactive({})
const loadError = ref('')
const samplingForms = reactive({})
const samplingWriting = reactive({})
let alive = true, loadRead = 0
onBeforeUnmount(() => { alive = false; ++loadRead })
const manualTasks = ref([])
const samplingItems = ref([])
const disputes = ref([])
const retests = ref([])
const stats = ref(null)
const regression = ref(null)
const reviewForms = reactive({})
const disputeForms = reactive({})
const batchForm = reactive({ title: '', basis: '', sample_size: 2, high_risk_size: 1, random_seed: 7, days: 7 })
const rubricRows = [
  { key: 'basis', label: '依据与范围' },
  { key: 'causal', label: '因果解释' },
  { key: 'evidence', label: '证据与不确定项' },
  { key: 'improvement', label: '改进与验证' },
]

function formatDate(value) { return feedbackDate(value) }
function riskLabel(value) { return ({ evidence_conflict: '证据冲突', verifier_failure: '核验未完成', unknown_independence: '独立性未知', scoring_dispute: '评分争议', missing_evidence: '证据缺失' })[value] || '已关联风险，完整记录可下载核对' }
function selectionLabel(value) { return feedbackLabel('sampling', value) }
function rateText(entry) { if (!entry || typeof entry.denominator !== 'number' || typeof entry.numerator !== 'number') return '未提供'; if (entry.denominator === 0) return '暂无数据'; return `${entry.numerator}/${entry.denominator}（${Math.round(entry.numerator / entry.denominator * 100)}%）` }
function extractError(err) { return feedbackError(err, '操作未完成，请核对填写内容或稍后重试。') }
function samplingForm(item) { return samplingForms[item.item_id] ||= { evidence_checked: false, verifier_checked: false, rubric_checked: false, help_checked: false, independence_checked: false, conclusion: '', notes: '' } }

function ensureReviewForm(task) {
  if (!reviewForms[task.task_id]) {
    const form = { decision: 'pass', remarks: '' }
    for (const row of rubricRows) {
      form[row.key] = { score: 0, evidence: '', reason: '' }
    }
    reviewForms[task.task_id] = form
  }
  return reviewForms[task.task_id]
}

async function loadAll() {
  if (!alive) return
  const read = ++loadRead
  loading.value = true; loadError.value = ''
  try {
    const [queue, manual, samplingPayload, disputesPayload, retestPayload, statsPayload, regressionPayload] = await Promise.all([service.skillReview.teacherQueue(), service.skillReview.manualTasks(), service.skillReview.samplingItems(), service.skillReview.teacherDisputes(), service.skillReview.teacherRetests(), service.skillReview.stats(), service.skillReview.regressionCases()])
    if (!alive || read !== loadRead) return
    if (![manual, samplingPayload, disputesPayload, retestPayload].every(value => Array.isArray(value.items))) throw new Error('Incomplete response')
    for (const key of Object.keys(counts)) delete counts[key]
    Object.assign(counts, queue.counts || {})
    manualTasks.value = manual.items; samplingItems.value = samplingPayload.items; disputes.value = disputesPayload.items; retests.value = retestPayload.items
    stats.value = statsPayload; regression.value = regressionPayload
    for (const task of manualTasks.value) ensureReviewForm(task)
    for (const item of samplingItems.value) samplingForm(item)
    for (const item of disputes.value) if (!disputeForms[item.dispute_id]) disputeForms[item.dispute_id] = { status: 'resolved', resolution: '' }
  } catch (err) { if (alive && read === loadRead) loadError.value = feedbackError(err, '验收待办未能完整读取，请重试。') }
  finally { if (alive && read === loadRead) loading.value = false }
}

async function claimManual(task) {
  try {
    await service.skillReview.claimManual(task.task_id)
    message.value = '已认领。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function submitManual(task) {
  const form = reviewForms[task.task_id]
  const scores = {}
  for (const row of rubricRows) {
    scores[row.key] = form[row.key]
  }
  try {
    await service.skillReview.reviewManual(task.task_id, {
      scores,
      decision: form.decision,
      remarks: form.remarks,
    })
    message.value = '评阅已保存；结果与模块一事实已更新。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function createBatch() {
  const now = new Date()
  const start = new Date(now.getTime() - batchForm.days * 86400000)
  const deadline = new Date(now.getTime() + 3 * 86400000)
  try {
    const payload = await service.skillReview.createSamplingBatch({
      catalog_version: stats.value?.catalog_version,
      title: batchForm.title || '常规抽查',
      window_start: start.toISOString(),
      window_end: now.toISOString(),
      basis: batchForm.basis || '首期常规抽查',
      deadline: deadline.toISOString(),
      sample_size: batchForm.sample_size,
      high_risk_size: batchForm.high_risk_size,
      random_seed: batchForm.random_seed,
    })
    message.value = `批次已建立，候选 ${payload.scope.candidate_count} 条，入选 ${payload.items} 条。`
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function claimSampling(item) {
  try {
    await service.skillReview.claimSampling(item.item_id)
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function completeSampling(item) {
  if (!alive || samplingWriting[item.item_id]) return
  const form = samplingForm(item)
  if (!form.conclusion.trim()) { message.value = '请填写实际复核结论，再提交已完成的核对项。'; return }
  const payload = { findings: { evidence_checked: form.evidence_checked, verifier_checked: form.verifier_checked, rubric_checked: form.rubric_checked, help_checked: form.help_checked, independence_checked: form.independence_checked, conclusion: form.conclusion }, notes: form.notes }
  samplingWriting[item.item_id] = true
  try { await service.skillReview.reviewSampling(item.item_id, payload); if (alive) { message.value = '实际复核内容已提交，请核对服务端结果。'; await loadAll() } }
  catch (err) { if (alive) message.value = extractError(err) }
  finally { if (alive) samplingWriting[item.item_id] = false }
}

async function resolveDispute(item) {
  const form = disputeForms[item.dispute_id]
  try {
    await service.skillReview.resolveDispute(item.dispute_id, form)
    message.value = '争议已处理；未直接修改成绩。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function processDue() {
  try {
    const result = await service.skillReview.processDueRetests({})
    message.value = `到期 ${result.due} 条，未完成 ${result.missed} 条。${result.note}`
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

onMounted(loadAll)
</script>

<style scoped>
.teacher-review-page { width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 36px 0 72px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; border-bottom: 2px solid var(--text-primary); padding-bottom: 20px; margin-bottom: 18px; }
.eyebrow { font-size: 12px; letter-spacing: .16em; text-transform: uppercase; color: var(--primary-color); font-weight: 700; }
h1 { font-family: "Songti SC", serif; font-size: 38px; line-height: 1.1; }
.subtitle { color: var(--text-secondary); margin-top: 8px; max-width: 760px; }
.btn { border: 1px solid var(--border-color); background: var(--bg-light); padding: 8px 12px; font-weight: 600; cursor: pointer; color: var(--text-primary); }
.btn-primary { background: var(--text-primary); color: var(--bg-light); }
.btn-small { padding: 5px 10px; font-size: 12px; }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
.tabs button { border: 1px solid var(--border-color); background: var(--bg-light); padding: 7px 12px; cursor: pointer; font-weight: 600; }
.tabs button.active { background: var(--text-primary); color: var(--bg-light); border-color: var(--text-primary); }
.count { margin-left: 6px; font-size: 11px; background: var(--primary-color); color: var(--on-action); padding: 0 6px; border-radius: 8px; }
.panel { background: var(--bg-light); border: 1px solid var(--border-color); padding: 18px; box-shadow: var(--shadow-md); }
.panel h2 { font-family: "Songti SC", serif; font-size: 20px; margin-bottom: 10px; }
.item { border-top: 1px solid var(--border-color); padding: 12px 0; }
.item-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.item-actions { display: flex; gap: 8px; align-items: center; }
.muted { color: var(--text-muted); font-size: 12px; }
.small { font-size: 12px; }
.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 8px 0; font-size: 12px; }
.label { display: block; font-size: 11px; color: var(--text-muted); }
.payload { background: var(--bg-paper-2); padding: 8px; font-size: 11px; overflow: auto; max-height: 220px; }
.review-form { margin-top: 10px; border: 1px dashed var(--border-color); padding: 10px; }
.rubric-row { display: grid; grid-template-columns: 130px 60px 1fr 1fr; gap: 8px; margin-bottom: 6px; font-size: 12px; align-items: center; }
.rubric-row input, .rubric-row select, .review-actions input, .review-actions select, .batch-form input, .batch-form select { border: 1px solid var(--border-color); padding: 5px 7px; font: inherit; background: var(--bg-paper); }
.review-actions { display: flex; gap: 8px; align-items: center; margin-top: 8px; flex-wrap: wrap; }
.batch-form { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.badge { font-size: 11px; padding: 2px 8px; border: 1px solid var(--border-color); }
.message { background: var(--warning-soft); border-left: 3px solid var(--primary-color); padding: 9px 12px; font-size: 13px; margin-bottom: 12px; }
.state-box { background: var(--bg-light); border: 1px solid var(--border-color); padding: 48px; text-align: center; color: var(--text-muted); }
@media (max-width: 900px) { .grid, .rubric-row { grid-template-columns: 1fr; } }
</style>
