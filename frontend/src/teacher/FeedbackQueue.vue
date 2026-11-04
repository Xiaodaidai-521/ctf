<template>
  <div class="fb-page" :class="{ 'feedback-embedded': embedded }">
    <div v-if="!embedded" class="fb-header">
      <div>
        <span class="fb-eyebrow">教师待办</span>
        <h1 class="fb-title">反馈待办与随机抽查</h1>
        <p class="fb-sub">
          默认按证据冲突、影响、新颖性和等待时间处理。重复投诉数量不参与正确性判断，也不能作为独立证据。
        </p>
      </div>
      <div class="fb-actions">
        <router-link to="/teacher/feedback/reconciliation" class="fb-btn">事件核对</router-link>
        <button class="fb-btn" type="button" :disabled="loading" @click="loadQueue">刷新</button>
      </div>
    </div>

    <div class="fb-notice">
      <strong>反馈由教师人工核查。</strong>
      处理完成不代表学习效果已验证，也不会自动更新课程规则；请结合后续练习继续跟踪。
    </div>

    <div v-if="error" class="fb-error" role="alert">{{ error }}</div>

    <div v-if="optionsError" class="fb-error" role="alert">{{ optionsError }} <button class="fb-btn" @click="loadOptions">重试读取选项</button></div>
    <section class="fb-panel">
      <div class="fb-toolbar">
        <label>
          状态
          <select v-model="filters.status" class="fb-select" @change="loadQueue">
            <option value="">全部（不含重复）</option>
            <option v-if="filters.status && !statuses.some(item => item.value === filters.status)" :value="filters.status">{{ feedbackLabel('status', filters.status) }}</option>
            <option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label>
          类别
          <select v-model="filters.category" class="fb-select" @change="loadQueue">
            <option value="">全部</option>
            <option v-for="item in categories" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label>
          责任人
          <select v-model="filters.owner" class="fb-select" @change="loadQueue">
            <option value="">全部</option>
            <option value="me">我的</option>
            <option value="unassigned">未分配</option>
          </select>
        </label>
        <label>
          排序
          <select v-model="filters.sort" class="fb-select" @change="loadQueue">
            <option value="priority">冲突/影响/新颖性/等待</option>
            <option value="waiting">等待最久</option>
            <option value="newest">最新</option>
          </select>
        </label>
        <button class="fb-btn" type="button" :disabled="loading" @click="loadQueue">刷新</button>
      </div>

      <div v-if="queueLoaded && !loading && !queueError" class="fb-meta">
        <span v-for="(count, key) in queue.counts" :key="key" class="fb-badge" :class="count ? 'fb-badge-info' : 'fb-badge-muted'">
          {{ feedbackLabel('status', key) }}：{{ count }}
        </span>
        <span class="fb-badge fb-badge-muted">共 {{ queue.total ?? '未提供' }} 条</span>
      </div>

      <p v-if="loading" class="fb-empty" role="status">正在读取反馈待办…</p>
      <div v-else-if="queueError" class="fb-error" role="alert">{{ queueError }} <button class="fb-btn" @click="loadQueue">重新读取</button></div>
      <div v-else-if="queueLoaded && !queue.items.length" class="fb-empty fb-mt">当前筛选下没有反馈。</div>
      <div v-else-if="queueLoaded" class="fb-list fb-mt">
        <article v-for="item in queue.items" :key="item.feedback_id" class="fb-card">
          <div class="fb-card-head">
            <div>
              <div class="fb-card-title">
                <router-link :to="`/teacher/feedback/${item.feedback_id}`" class="fb-link">
                  {{ feedbackLabel('category', item.category) }} · {{ feedbackLabel('issue', item.issue_type) }}
                </router-link>
              </div>
              <div class="fb-meta">
                <span>{{ item.student_name }}</span>
                <span>{{ item.task_title || '未关联任务' }}</span>
                <span>等待 {{ item.waiting_days ?? '未提供' }} 天</span>
                <span v-if="item.duplicate_count">重复 {{ item.duplicate_count }} 条（不增加独立证据）</span>
              </div>
            </div>
            <span class="fb-badge" :class="statusTone(item.status)">{{ feedbackLabel('status', item.status) }}</span>
          </div>
          <div class="fb-meta">
            <span class="fb-badge" :class="item.conflict_flag ? 'fb-badge-danger' : 'fb-badge-muted'">
              冲突：{{ item.conflict_flag ? '有' : '无' }}
            </span>
            <span class="fb-badge" :class="item.impact_level === 'high' ? 'fb-badge-danger' : 'fb-badge-muted'">
              影响：{{ feedbackLabel('impact', item.impact_level) }}
            </span>
            <span class="fb-badge" :class="item.novelty === 'new' ? 'fb-badge-warn' : 'fb-badge-muted'">
              新颖性：{{ feedbackLabel('novelty', item.novelty) }}
            </span>
            <span class="fb-badge fb-badge-muted">去向：{{ feedbackLabel('destination', item.handling_destination) }}</span>
            <span class="fb-badge fb-badge-muted">责任人：{{ item.owner_name || '未分配' }}</span>
            <span class="fb-badge" :class="item.candidate_eligible ? 'fb-badge-ok' : 'fb-badge-muted'">
              {{ item.candidate_eligible ? '可作候选依据' : '不可作候选依据' }}
            </span>
          </div>
          <p class="fb-muted">优先级：{{ feedbackPriority(item) }}</p>
          <div v-if="item.missing_evidence?.length" class="fb-missing">
            待补证：{{ item.missing_evidence.map(slot => feedbackLabel('slot', slot)).join('、') }}
          </div>
          <div class="fb-actions">
            <router-link :to="`/teacher/feedback/${item.feedback_id}`" class="fb-btn">打开处理</router-link>
          </div>
        </article>
      </div>
      <div v-if="queueLoaded && !loading && !queueError" class="fb-actions">
        <span class="fb-muted">本页 {{ queue.items.length }} 条</span>
        <button v-if="queue.page > 1" class="fb-btn" @click="loadQueue(queue.page - 1)">上一页</button>
        <button v-if="queueNext" class="fb-btn" @click="loadQueue(queueNext)">下一页</button>
      </div>
    </section>

    <details id="feedback-sampling" class="fb-panel length-disclosure">
      <summary class="length-disclosure__summary"><h2>随机抽查登记</h2></summary>
      <div class="length-disclosure__body">
      <p class="fb-muted">
        每次抽查保存范围、样本数量和入选原因。高风险样本单列，不作为总体错误率的随机估计。
        同一范围和总体使用相同的可复现随机值，可得到相同随机样本；不足目标数量时全部查看。
      </p>
      <div class="fb-form-grid">
        <label>
          抽查状态
          <select v-model="batchForm.status" class="fb-select">
            <option v-if="!statuses.some(item => item.value === batchForm.status)" :value="batchForm.status">{{ feedbackLabel('status', batchForm.status) }}</option>
            <option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label>
          样本数量
          <input v-model.number="batchForm.sample_size" class="fb-input" type="number" min="1" />
        </label>
        <label>
          可复现随机值（留空自动生成）
          <input v-model="batchForm.random_seed" class="fb-input" placeholder="如 20261025" />
        </label>
        <label class="fb-check fb-align-end">
          <input v-model="batchForm.exclude_prior" type="checkbox" />
          排除既往样本
        </label>
        <div class="fb-full">
          <h3>高风险样本（可选）</h3>
          <p class="fb-muted">从有权查看的反馈中多选，不限于上方待办列表。生成时会检查抽查状态与既往抽查记录。</p>
          <div class="fb-actions">
            <button class="fb-btn" type="button" :disabled="riskLoading" @click="loadRiskTickets">
              {{ riskLoading ? '正在读取反馈…' : riskLoaded ? '刷新可选反馈' : '读取可选反馈' }}
            </button>
            <span class="fb-muted">已选 {{ batchForm.risk_ticket_ids.length }} 条</span>
          </div>
          <div v-if="riskError" class="fb-error" role="alert">{{ riskError }}</div>
          <p v-if="riskLoading" class="fb-muted" role="status">已读取 {{ riskTickets.length }} 条，正在继续读取其余反馈。</p>
          <p v-else-if="riskLoaded && !riskTickets.length" class="fb-empty">暂无可选反馈。</p>
          <label v-if="riskTickets.length" class="fb-mt">
            选择反馈（可多选）
            <select v-model="batchForm.risk_ticket_ids" class="fb-select" multiple size="8">
              <option v-for="ticket in riskTickets" :key="ticket.feedback_id" :value="ticket.feedback_id">
                {{ feedbackTitle(ticket) }} · {{ feedbackLabel('status', ticket.status) }}
              </option>
            </select>
          </label>
        </div>
        <label class="fb-full">
          抽样依据/说明
          <textarea v-model="batchForm.notes" class="fb-textarea" rows="2"></textarea>
        </label>
      </div>
      <div class="fb-actions">
        <button class="fb-btn" type="button" :disabled="creatingBatch" @click="createBatch">
          {{ creatingBatch ? '生成中...' : '生成抽查批次' }}
        </button>
      </div>

      <p v-if="batchLoading" class="fb-muted" role="status">正在读取抽查明细…</p>
      <div v-if="selectedBatch" class="fb-card fb-mt">
        <div class="fb-card-head">
          <strong>{{ formatDate(selectedBatch.created_at) }}的抽查</strong>
          <span class="fb-badge fb-badge-info">{{ feedbackLabel('sampling', selectedBatch.method) }}</span>
        </div>
        <div v-if="batchNamesError" class="fb-error" role="alert">
          {{ batchNamesError }}
          <button class="fb-btn" type="button" @click="loadBatchNames">重试读取标题</button>
        </div>
        <div class="fb-meta">
          <span>可复现随机值：{{ selectedBatch.random_seed }}</span>
          <span>总体：{{ selectedBatch.population_count }}</span>
          <span>目标样本：{{ selectedBatch.sample_size }}</span>
          <span>实际：{{ selectedBatch.items?.length || 0 }}</span>
          <span>排除既往：{{ selectedBatch.exclude_prior ? '是' : '否' }}</span>
        </div>
        <div class="fb-table-wrap">
          <table class="fb-table">
            <thead><tr><th>反馈</th><th>入选原因</th><th>状态</th><th>优先级</th></tr></thead>
            <tbody>
              <tr v-for="item in selectedBatch.items" :key="item.ticket_id">
                <td><router-link :to="`/teacher/feedback/${item.ticket_id}`" class="fb-link">{{ feedbackTitle(batchNames[item.ticket_id]) }}</router-link></td>
                <td>{{ feedbackLabel('sampling', item.selected_reason) }}</td>
                <td>{{ feedbackLabel('status', item.status) }}</td>
                <td>{{ batchNames[item.ticket_id] ? feedbackPriority(batchNames[item.ticket_id]) : '详情暂不可用，请打开反馈查看' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <h3>最近批次</h3>
      <p v-if="batchesLoading" class="fb-empty" role="status">正在读取最近批次…</p>
      <div v-else-if="batchesError" class="fb-error" role="alert">{{ batchesError }} <button class="fb-btn" @click="loadBatches">重新读取批次</button></div>
      <div v-else-if="batchesLoaded && !batches.length" class="fb-empty">暂无抽查批次。</div>
      <div v-else-if="batchesLoaded" class="fb-list">
        <article v-for="batch in batches" :key="batch.batch_id" class="fb-card">
          <div class="fb-card-head">
            <strong>{{ formatDate(batch.created_at) }}的抽查</strong>
            <button class="fb-btn" type="button" @click="loadBatch(batch.batch_id)">查看明细</button>
          </div>
          <div class="fb-meta">
            <span>可复现随机值：{{ batch.random_seed }}</span>
            <span>总体：{{ batch.population_count }}</span>
            <span>目标：{{ batch.sample_size }}</span>
            <span>方法：{{ feedbackLabel('sampling', batch.method) }}</span>
            <span>{{ formatDate(batch.created_at) }}</span>
          </div>
        </article>
      </div>
      </div>
    </details>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, reactive, ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { queueStatusPreset } from './feedback/queueState.js'
import '@/shared/layout/disclosure.css'
import service from './feedback/api.js'
import { feedbackDate as formatDate, feedbackError, feedbackLabel, feedbackOptions, feedbackPriority, feedbackTitle, mergeFeedbackItems, nextFeedbackPage } from './feedbackPresentation.js'

const { embedded } = defineProps({ embedded: { type: Boolean, default: false } })
const emit = defineEmits(['ready'])
const route = useRoute()
const queue = reactive({ items: [], counts: {}, total: null, page: 1, page_size: null })
const loading = ref(true)
const queueLoaded = ref(false)
const queueError = ref('')
const optionsError = ref('')
const batchesLoading = ref(true)
const batchesLoaded = ref(false)
const batchesError = ref('')
let queueRead = 0
let optionsRead = 0
let batchesRead = 0
let alive = true
const queueNext = computed(() => Number.isInteger(queue.total) && Number.isInteger(queue.page_size) && queue.page_size > 0 && queue.page * queue.page_size < queue.total ? queue.page + 1 : null)
const statuses = ref([])
const categories = ref([])
const batches = ref([])
const selectedBatch = ref(null)
const error = ref('')
const creatingBatch = ref(false)
const riskTickets = ref([])
const riskLoading = ref(false)
const riskLoaded = ref(false)
const riskError = ref('')
const batchNames = reactive({})
const batchNamesError = ref('')
let batchRead = 0
let batchNamesRead = 0
const batchLoading = ref(false)

const filters = reactive({ status: queueStatusPreset(route.query?.status), category: '', owner: '', sort: 'priority' })
watch(() => route.query?.status, value => { filters.status = queueStatusPreset(value); void loadQueue() })
onBeforeUnmount(() => { alive = false; ++queueRead; ++optionsRead; ++batchesRead; ++batchRead; ++batchNamesRead })
const batchForm = reactive({
  status: 'pending_fact_review',
  sample_size: 5,
  random_seed: '',
  exclude_prior: true,
  risk_ticket_ids: [],
  notes: '教师按冲突、影响、新颖性和等待时间处理后的随机抽查。',
})

function statusTone(status) {
  if (['confirmed', 'handled'].includes(status)) return 'fb-badge-ok'
  if (['pending_evidence', 'reopened', 'rejected'].includes(status)) return 'fb-badge-warn'
  return 'fb-badge-info'
}

async function loadQueue(requestedPage = 1) {
  const current = ++queueRead
  const page = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  queueError.value = ''
  loading.value = true
  try {
    const res = await service.feedback.teacherQueue({
      status: filters.status || undefined, category: filters.category || undefined,
      owner: filters.owner || undefined, sort: filters.sort, page, page_size: 50,
    })
    if (!alive || current !== queueRead) return
    if (!Array.isArray(res?.items)) throw new Error('Incomplete queue')
    Object.assign(queue, {
      items: res.items, counts: res.counts || {},
      total: Number.isInteger(res.total) && res.total >= 0 ? res.total : null,
      page: Number.isInteger(res.page) && res.page > 0 ? res.page : page,
      page_size: Number.isInteger(res.page_size) && res.page_size > 0 ? res.page_size : null,
    })
    queueLoaded.value = true
  } catch (err) {
    if (alive && current === queueRead) queueError.value = feedbackError(err, '加载教师待办失败，请重试。')
  } finally {
    if (alive && current === queueRead) loading.value = false
  }
}

async function loadOptions() {
  const current = ++optionsRead
  optionsError.value = ''
  try {
    const res = await service.feedback.options()
    if (!alive || current !== optionsRead) return
    statuses.value = feedbackOptions(res.statuses, 'status')
    categories.value = feedbackOptions(res.categories, 'category')
  } catch (err) {
    if (alive && current === optionsRead) optionsError.value = feedbackError(err, '加载选项失败，请重试读取选项。')
  }
}

async function loadRiskTickets() {
  if (riskLoading.value) return
  riskLoading.value = true
  riskError.value = ''
  riskLoaded.value = false
  // All non-duplicate feedback is available here, regardless of the queue's
  // filters or page. Sampling scope/prior-sample eligibility stays server-owned.
  let page = 1
  let items = []
  try {
    do {
      const res = await service.feedback.teacherQueue({ page, page_size: 100, sort: 'newest' })
      if (!alive) return
      items = mergeFeedbackItems(items, res.items || [])
      riskTickets.value = mergeFeedbackItems(
        riskTickets.value.filter(item => batchForm.risk_ticket_ids.includes(item.feedback_id)), items,
      )
      page = nextFeedbackPage(res)
    } while (page !== null)
    riskLoaded.value = true
  } catch (err) {
    if (!alive) return
    riskError.value = feedbackError(err, '可选反馈尚未全部读取，已选项仍保留。请重试读取其余反馈。')
  } finally {
    riskLoading.value = false
  }
}

async function loadBatches() {
  const current = ++batchesRead
  batchesLoading.value = true
  batchesError.value = ''
  try {
    const res = await service.feedback.samplingBatches()
    if (!alive || current !== batchesRead) return
    if (!Array.isArray(res?.items)) throw new Error('Incomplete batches')
    batches.value = res.items
    batchesLoaded.value = true
  } catch (err) {
    if (alive && current === batchesRead) batchesError.value = feedbackError(err, '加载抽查批次失败，请重试。')
  } finally {
    if (alive && current === batchesRead) batchesLoading.value = false
  }
}

async function loadBatchNames() {
  const current = ++batchNamesRead
  batchNamesError.value = ''
  // Sequential reads avoid flooding the service for larger samples. Reuse
  // available titles; batch status and selection reasons remain original.
  for (const item of selectedBatch.value?.items || []) {
    if (!alive || current !== batchNamesRead) return
    if (batchNames[item.ticket_id]) continue
    const known = [...queue.items, ...riskTickets.value].find(row => row.feedback_id === item.ticket_id)
    if (known) {
      batchNames[item.ticket_id] = known
      continue
    }
    try {
      const detail = await service.feedback.teacherDetail(item.ticket_id)
      if (!alive || current !== batchNamesRead) return
      batchNames[item.ticket_id] = detail
    } catch (err) {
      if (!alive || current !== batchNamesRead) return
      batchNamesError.value = feedbackError(err, '部分反馈标题未能读取，仍可打开反馈；可重试加载标题。')
      break
    }
  }
}

async function loadBatch(batchId) {
  const current = ++batchRead
  ++batchNamesRead
  batchLoading.value = true
  batchNamesError.value = ''
  try {
    const batch = await service.feedback.samplingBatch(batchId)
    if (!alive || current !== batchRead) return
    selectedBatch.value = batch
    batchLoading.value = false
    void loadBatchNames()
  } catch (err) {
    if (!alive || current !== batchRead) return
    error.value = feedbackError(err, '加载抽查批次详情失败，请重试。')
    batchLoading.value = false
  }
}

async function createBatch() {
  if (creatingBatch.value) return
  error.value = ''
  creatingBatch.value = true
  try {
    const payload = {
      scope: { statuses: [batchForm.status] },
      sample_size: batchForm.sample_size,
      exclude_prior: batchForm.exclude_prior,
      notes: batchForm.notes,
      risk_ticket_ids: [...batchForm.risk_ticket_ids],
    }
    if (batchForm.random_seed !== '' && batchForm.random_seed !== null) {
      payload.random_seed = Number(batchForm.random_seed)
    }
    const batch = await service.feedback.createSamplingBatch(payload)
    if (!alive) return
    ++batchRead
    ++batchNamesRead
    batchLoading.value = false
    selectedBatch.value = batch
    void loadBatchNames()
    await loadBatches()
    await loadQueue()
  } catch (err) {
    error.value = feedbackError(err, '生成抽查批次失败，请重试。')
  } finally {
    creatingBatch.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadOptions(), loadQueue(), loadBatches()])
  if (alive) emit('ready')
})
</script>

<style src="@/assets/feedback.css"></style>
<style scoped>
.feedback-embedded { max-width: none; margin: 0; padding: 0; background: var(--surface); }
.feedback-embedded .fb-panel { box-shadow: none; border: none; border-radius: 0; padding: var(--density-gap) 0; }
.feedback-embedded .fb-card { box-shadow: none; }
</style>
