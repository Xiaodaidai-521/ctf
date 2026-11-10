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

    <template v-else>
      <div class="tabs">
        <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
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
            <pre class="payload">{{ JSON.stringify(task.submission.items, null, 2) }}</pre>
            <p class="muted small">程序核验明细：{{ JSON.stringify(task.submission.program_result) }}</p>
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
                {{ item.batch_title }} · {{ item.selection_reason === 'high_risk' ? '高风险' : '随机' }}
                <template v-if="item.risk_reasons.length"> · {{ item.risk_reasons.join('、') }}</template>
                <template v-if="item.overdue"> · 已超期</template>
              </p>
            </div>
            <div class="item-actions">
              <button v-if="item.status === 'pending'" class="btn btn-small" @click="claimSampling(item)">认领</button>
              <button v-if="item.status === 'claimed'" class="btn btn-primary btn-small" @click="completeSampling(item)">完成复核</button>
            </div>
          </div>
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
            <span class="badge">{{ item.selection_reason }}</span>
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
          <pre class="payload">{{ JSON.stringify(regression, null, 2) }}</pre>
        </details>
      </section>
    </template>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import service from '@/api'

const tabs = [
  { key: 'manual', label: '开放题必评', countKey: 'manual_pending' },
  { key: 'sampling', label: '常规抽查', countKey: 'sampling_pending' },
  { key: 'disputes', label: '评分争议', countKey: 'disputes_pending' },
  { key: 'retest', label: '复测安排', countKey: '' },
  { key: 'stats', label: '统计口径', countKey: '' },
]
const activeTab = ref('manual')
const loading = ref(true)
const message = ref('')
const counts = reactive({ manual_pending: 0, sampling_pending: 0, disputes_pending: 0 })
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

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function rateText(entry) {
  if (!entry) return '—'
  if (!entry.denominator) return '暂无数据'
  return `${entry.numerator}/${entry.denominator}（${Math.round(entry.rate * 100)}%）`
}

function extractError(err) {
  const data = err?.response?.data
  if (!data) return '网络或服务异常。'
  if (typeof data === 'string') return data
  if (typeof data.detail === 'string') return data.detail
  if (data.detail?.detail) return data.detail.detail
  return '操作未完成。'
}

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
  loading.value = true
  message.value = ''
  try {
    const queue = await service.skillReview.teacherQueue()
    Object.assign(counts, queue.counts)
    const [manual, samplingPayload, disputesPayload, retestPayload, statsPayload, regressionPayload] = await Promise.all([
      service.skillReview.manualTasks(),
      service.skillReview.samplingItems(),
      service.skillReview.teacherDisputes(),
      service.skillReview.teacherRetests(),
      service.skillReview.stats(),
      service.skillReview.regressionCases(),
    ])
    manualTasks.value = manual.items || []
    samplingItems.value = samplingPayload.items || []
    disputes.value = disputesPayload.items || []
    retests.value = retestPayload.items || []
    stats.value = statsPayload
    regression.value = regressionPayload
    for (const task of manualTasks.value) {
      ensureReviewForm(task)
    }
    for (const item of disputes.value) {
      if (!disputeForms[item.dispute_id]) {
        disputeForms[item.dispute_id] = { status: 'resolved', resolution: '' }
      }
    }
  } catch (err) {
    message.value = extractError(err)
  } finally {
    loading.value = false
  }
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
  try {
    await service.skillReview.reviewSampling(item.item_id, {
      findings: {
        evidence_checked: true,
        verifier_checked: true,
        rubric_checked: true,
        help_checked: true,
        independence_checked: true,
        conclusion: '已复核，维持原判',
      },
      notes: '界面复核',
    })
    message.value = '抽查项已完成。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
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
.count { margin-left: 6px; font-size: 11px; background: var(--primary-color); color: #fff; padding: 0 6px; border-radius: 8px; }
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
.message { background: rgba(183,53,45,.06); border-left: 3px solid var(--primary-color); padding: 9px 12px; font-size: 13px; margin-bottom: 12px; }
.state-box { background: var(--bg-light); border: 1px solid var(--border-color); padding: 48px; text-align: center; color: var(--text-muted); }
@media (max-width: 900px) { .grid, .rubric-row { grid-template-columns: 1fr; } }
</style>
