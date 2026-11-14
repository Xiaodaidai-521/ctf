<template>
  <div class="fb-page">
    <header class="fb-header" v-if="!embedded"><div><h1 class="fb-title">反馈待办与随机抽查</h1><p class="fb-sub">按证据冲突、影响、新颖性和等待时间处理；重复数量不能作为独立证据。</p></div><div class="fb-actions"><router-link to="/teacher/feedback/reconciliation" class="fb-btn">事件核对</router-link><button class="fb-btn" type="button" @click="loadQueue">刷新</button></div></header>
    <div class="fb-notice">已处理、教学效果已验证和新规则生效分别记录；候选写入与生效须通过各自开放条件。</div>
    <p v-if="error" class="fb-error" role="alert">{{ error }}</p>
    <section class="fb-panel">
      <div class="fb-toolbar"><label>状态<select v-model="filters.status" class="fb-select" @change="loadQueue"><option value="">全部（不含重复）</option><option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label>类别<select v-model="filters.category" class="fb-select" @change="loadQueue"><option value="">全部</option><option v-for="item in categories" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label>责任人<select v-model="filters.owner" class="fb-select" @change="loadQueue"><option value="">全部</option><option value="me">我的</option><option value="unassigned">未分配</option></select></label><label>排序<select v-model="filters.sort" class="fb-select" @change="loadQueue"><option value="priority">冲突/影响/新颖性/等待</option><option value="waiting">等待最久</option><option value="newest">最新</option></select></label><button class="fb-btn" type="button" @click="loadQueue">刷新</button></div>
      <p v-if="optionsError" class="fb-error" role="alert">{{ optionsError }} <button class="fb-btn" type="button" @click="loadOptions">重试读取选项</button></p>
      <p v-if="loading" role="status">正在读取反馈待办…</p><p v-else-if="queueError" class="fb-error" role="alert">{{ queueError }}</p>
      <template v-else-if="queueLoaded"><div class="fb-meta"><span v-for="(count, key) in queue.counts" :key="key" class="fb-badge">{{ feedbackLabel('status', key) }}：{{ count }}</span><span>共 {{ queue.total ?? '未提供' }} 条</span></div><p v-if="!queue.items.length" class="fb-empty">当前筛选下没有反馈。</p><div v-else class="fb-list"><article v-for="item in queue.items" :key="item.feedback_id" class="fb-card"><div class="fb-card-head"><router-link :to="`/teacher/feedback/${item.feedback_id}`" class="fb-link">{{ feedbackTitle(item) }}</router-link><span class="fb-badge" :class="statusTone(item.status)">{{ feedbackLabel('status', item.status) }}</span></div><p class="fb-muted">{{ feedbackPriority(item) }}</p><p>处理去向：{{ feedbackLabel('destination', item.handling_destination) }} · 责任人：{{ item.owner_name || '未分配' }}</p><p v-if="item.duplicate_count">重复 {{ item.duplicate_count }} 条（不增加独立证据）</p><p v-if="item.missing_evidence?.length">待补证：{{ item.missing_evidence.map(slot => feedbackLabel('slot', slot)).join('、') }}</p><router-link :to="`/teacher/feedback/${item.feedback_id}`" class="fb-btn">打开处理</router-link></article></div><div class="fb-actions"><button v-if="queue.page > 1" class="fb-btn" type="button" @click="loadQueue(queue.page - 1)">上一页</button><button v-if="queueNext" class="fb-btn" type="button" @click="loadQueue(queueNext)">下一页</button></div></template>
    </section>
    <details id="feedback-sampling" class="length-disclosure fb-panel">
      <summary class="length-disclosure__summary"><h2>随机抽查登记</h2></summary>
      <div class="length-disclosure__body"><p class="fb-muted">范围、随机种子、样本数量及入选原因由服务端保存；高风险样本单列，不作为总体错误率的随机估计。</p>
        <div class="fb-form-grid"><label>抽查状态<select v-model="batchForm.status" class="fb-select"><option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label>样本数量<input v-model.number="batchForm.sample_size" class="fb-input" type="number" min="1" /></label><label>随机种子（可留空由服务端生成）<input v-model="batchForm.random_seed" class="fb-input" /></label><label class="fb-check"><input v-model="batchForm.exclude_prior" type="checkbox" />排除既往样本</label><label class="fb-full">高风险反馈（可多选）<select v-model="batchForm.risk_ticket_ids" multiple class="fb-select"><option v-for="item in riskTickets" :key="item.feedback_id" :value="item.feedback_id">{{ feedbackTitle(item) }}</option></select></label><label class="fb-full">抽样依据/说明<textarea v-model="batchForm.notes" class="fb-textarea" rows="2"></textarea></label></div>
        <p v-if="riskLoading" role="status">正在读取高风险反馈选择…</p><p v-if="riskError" class="fb-error" role="alert">{{ riskError }}</p><div class="fb-actions"><button class="fb-btn" type="button" :disabled="riskLoading" @click="loadRiskTickets">{{ riskLoaded ? '刷新高风险选择' : '读取高风险选择' }}</button><button class="fb-btn fb-btn-primary" type="button" :disabled="creatingBatch" @click="createBatch">{{ creatingBatch ? '生成中…' : '生成抽查批次' }}</button></div>
        <p v-if="batchLoading" role="status">正在读取批次明细…</p><p v-if="batchNamesError" class="fb-error" role="alert">{{ batchNamesError }} <button class="fb-btn" type="button" @click="loadBatchNames">重试读取标题</button></p>
        <article v-if="selectedBatch" class="fb-card"><h3>抽查批次 · {{ feedbackDate(selectedBatch.created_at) }}</h3><p>{{ feedbackLabel('sampling', selectedBatch.method) }} · 总体 {{ selectedBatch.population_count ?? '未提供' }} · 目标 {{ selectedBatch.sample_size ?? '未提供' }} · 实际 {{ selectedBatch.items?.length ?? '未提供' }}</p><div class="fb-table-wrap"><table class="fb-table"><thead><tr><th>反馈</th><th>入选原因</th><th>状态</th><th>优先级</th></tr></thead><tbody><tr v-for="item in selectedBatch.items" :key="item.ticket_id"><td><router-link :to="`/teacher/feedback/${item.ticket_id}`" class="fb-link">{{ feedbackTitle(batchNames[item.ticket_id]) }}</router-link></td><td>{{ feedbackLabel('sampling', item.selected_reason) }}</td><td>{{ feedbackLabel('status', item.status) }}</td><td>{{ batchNames[item.ticket_id] ? feedbackPriority(batchNames[item.ticket_id]) : '待核对' }}</td></tr></tbody></table></div></article>
        <h3>最近批次</h3><button class="fb-btn" type="button" @click="loadBatches">刷新批次</button><p v-if="batchesLoading" role="status">正在读取抽查批次…</p><p v-else-if="batchesError" class="fb-error" role="alert">{{ batchesError }}</p><template v-else-if="batchesLoaded"><p v-if="!batches.length" class="fb-empty">暂无抽查批次。</p><div v-else class="fb-list"><article v-for="batch in batches" :key="batch.batch_id" class="fb-card"><strong>抽查批次 · {{ feedbackDate(batch.created_at) }}</strong><p>{{ feedbackLabel('sampling', batch.method) }} · 总体 {{ batch.population_count ?? '未提供' }} · 目标 {{ batch.sample_size ?? '未提供' }}</p><button class="fb-btn" type="button" @click="loadBatch(batch.batch_id)">查看明细</button></article></div></template>
      </div>
    </details>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import service from './feedback/api.js'
import { feedbackLabel, feedbackOptions, feedbackDate, feedbackTitle, feedbackPriority, feedbackError, nextFeedbackPage, mergeFeedbackItems } from './feedbackPresentation.js'
import { queueStatusPreset } from './feedback/queueState.js'
import '../shared/layout/disclosure.css'
const props = defineProps({ embedded: Boolean })
const embedded = props.embedded
const emit = defineEmits(['ready'])
const route = useRoute()
const queue = reactive({ items: [], counts: {}, total: null, page: 1, page_size: null })
const loading = ref(true), queueLoaded = ref(false), queueError = ref(''), optionsError = ref('')
const statuses = ref([]), categories = ref([]), batches = ref([]), selectedBatch = ref(null), error = ref(''), creatingBatch = ref(false)
const batchesLoading = ref(true), batchesLoaded = ref(false), batchesError = ref(''), batchLoading = ref(false)
const riskTickets = ref([]), riskLoading = ref(false), riskLoaded = ref(false), riskError = ref('')
const batchNames = reactive({}), batchNamesError = ref('')
const filters = reactive({ status: queueStatusPreset(route.query.status), category: '', owner: '', sort: 'priority' })
const batchForm = reactive({ status: 'pending_fact_review', sample_size: 5, random_seed: '', exclude_prior: true, risk_ticket_ids: [], notes: '' })
let alive = true, queueRead = 0, optionsRead = 0, batchesRead = 0, batchRead = 0, riskRead = 0, namesRead = 0
onBeforeUnmount(() => { alive = false; ++queueRead; ++optionsRead; ++batchesRead; ++batchRead; ++riskRead; ++namesRead })
const queueNext = computed(() => { try { return nextFeedbackPage(queue) } catch { return null } })
function statusTone(status) { return ['confirmed', 'handled'].includes(status) ? 'fb-badge-ok' : ['pending_evidence', 'reopened', 'rejected'].includes(status) ? 'fb-badge-warn' : 'fb-badge-info' }
async function loadQueue(requestPage = 1) {
  if (!alive) return
  const read = ++queueRead, page = Number.isSafeInteger(requestPage) && requestPage > 0 ? requestPage : 1
  loading.value = true; queueError.value = ''; queueLoaded.value = false
  try {
    const res = await service.feedback.teacherQueue({ status: filters.status || undefined, category: filters.category || undefined, owner: filters.owner || undefined, sort: filters.sort, page, page_size: 50 })
    if (!alive || read !== queueRead) return
    if (!Array.isArray(res.items)) throw new Error('Incomplete response')
    Object.assign(queue, { items: res.items, counts: res.counts || {}, total: typeof res.total === 'number' && Number.isFinite(res.total) && res.total >= 0 ? res.total : null, page: res.page || page, page_size: res.page_size || null })
    queueLoaded.value = true
  } catch (err) { if (alive && read === queueRead) queueError.value = feedbackError(err, '加载教师待办失败，请重试。') }
  finally { if (alive && read === queueRead) loading.value = false }
}
async function loadOptions() {
  if (!alive) return
  const read = ++optionsRead; optionsError.value = ''
  try { const res = await service.feedback.options(); if (alive && read === optionsRead) { statuses.value = feedbackOptions(res.statuses || [], 'status'); categories.value = feedbackOptions(res.categories || [], 'category') } }
  catch (err) { if (alive && read === optionsRead) optionsError.value = feedbackError(err, '加载选项失败，请重试。') }
}
async function loadBatches() {
  if (!alive) return
  const read = ++batchesRead; batchesLoading.value = true; batchesLoaded.value = false; batchesError.value = ''
  try { const res = await service.feedback.samplingBatches(); if (alive && read === batchesRead) { if (!Array.isArray(res.items)) throw new Error('Incomplete response'); batches.value = res.items; batchesLoaded.value = true } }
  catch (err) { if (alive && read === batchesRead) batchesError.value = feedbackError(err, '加载抽查批次失败，请重试。') }
  finally { if (alive && read === batchesRead) batchesLoading.value = false }
}
async function loadRiskTickets() {
  if (!alive || riskLoading.value) return
  const read = ++riskRead; riskLoading.value = true; riskLoaded.value = false; riskError.value = ''
  try {
    let page = 1, rows = []
    while (page !== null) { if (page > 10000) throw new Error('Too many pages'); const res = await service.feedback.teacherQueue({ page, page_size: 100 }); if (!alive || read !== riskRead) return; if (!Array.isArray(res.items)) throw new Error('Incomplete response'); rows = mergeFeedbackItems(rows, res.items); const next = nextFeedbackPage(res); if (next !== null && next <= page) throw new Error('Invalid pagination'); page = next }
    riskTickets.value = rows; riskLoaded.value = true
  } catch (err) { if (alive && read === riskRead) riskError.value = feedbackError(err, '高风险反馈尚未全部读取，请重试；已选反馈仍保留。') }
  finally { if (alive && read === riskRead) riskLoading.value = false }
}
async function loadBatchNames() {
  if (!alive || !selectedBatch.value) return
  const read = ++namesRead, ids = [...new Set((selectedBatch.value.items || []).map(item => item.ticket_id))]
  batchNamesError.value = ''
  for (const id of ids) {
    try { const detail = await service.feedback.teacherDetail(id); if (!alive || read !== namesRead) return; batchNames[id] = detail }
    catch (err) { if (!alive || read !== namesRead) return; batchNamesError.value = feedbackError(err, '部分反馈标题未能读取，请重试。') }
  }
}
async function loadBatch(batchId) {
  if (!alive) return
  const read = ++batchRead; ++namesRead; batchLoading.value = true; error.value = ''
  try { const res = await service.feedback.samplingBatch(batchId); if (alive && read === batchRead) { selectedBatch.value = res; await loadBatchNames() } }
  catch (err) { if (alive && read === batchRead) error.value = feedbackError(err, '加载批次明细失败，请重试。') }
  finally { if (alive && read === batchRead) batchLoading.value = false }
}
async function createBatch() {
  if (!alive || creatingBatch.value) return
  const payload = { scope: { statuses: [batchForm.status] }, sample_size: batchForm.sample_size, exclude_prior: batchForm.exclude_prior, notes: batchForm.notes, risk_ticket_ids: [...batchForm.risk_ticket_ids] }
  if (batchForm.random_seed !== '' && batchForm.random_seed !== null) payload.random_seed = Number(batchForm.random_seed)
  error.value = ''; creatingBatch.value = true
  try { const res = await service.feedback.createSamplingBatch(payload); if (!alive) return; selectedBatch.value = res; await Promise.all([loadBatches(), loadQueue(), loadBatchNames()]) }
  catch (err) { if (alive) error.value = feedbackError(err, '生成抽查批次失败，请重试。') }
  finally { if (alive) creatingBatch.value = false }
}
watch(() => route.query.status, value => { filters.status = queueStatusPreset(value); void loadQueue() })
onMounted(async () => { await Promise.allSettled([loadOptions(), loadQueue(), loadBatches()]); if (alive) emit('ready') })
</script>

<style scoped src="../shared/feedback/page.css"></style>
