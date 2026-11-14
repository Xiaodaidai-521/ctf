<template>
  <div class="fb-page">
    <header class="fb-header"><div><h1 class="fb-title">反馈事件核对</h1><p class="fb-sub">核对反馈动作与统一学习事件；内容不一致须人工核查。</p></div><div class="fb-actions"><router-link to="/teacher/feedback" class="fb-btn">返回反馈待办</router-link><button class="fb-btn" type="button" :disabled="loading" @click="load">刷新</button></div></header>
    <p class="fb-notice">事件核对结果与审批、发布分别记录。</p>
    <p v-if="error" class="fb-error" role="alert">{{ error }}</p><p v-if="message" class="fb-success" role="status">{{ message }}</p>
    <p v-if="loading" role="status">正在读取事件核对…</p>
    <section class="fb-panel"><div class="fb-meta"><span>已关联：{{ data.counts.linked ?? '未提供' }}</span><span>待重试：{{ data.counts.pending ?? '未提供' }}</span><span>不一致：{{ data.counts.mismatch ?? '未提供' }}</span><span>缺失：{{ data.counts.missing ?? '未提供' }}</span><span>扫描：{{ data.scanned ?? '未提供' }}</span></div><button class="fb-btn" type="button" :disabled="retrying" @click="retryAll">{{ retrying ? '重试中…' : '重试全部待同步事件' }}</button></section>
    <section class="fb-panel"><h2>需要关注的反馈</h2><p v-if="namesError" class="fb-error" role="alert">{{ namesError }} <button class="fb-btn" type="button" @click="loadNames">重试读取标题</button></p><p v-if="data.loaded && !data.items.length && !error && !loading" class="fb-empty">本次扫描未发现待处理差异。</p><article v-for="ticket in data.items" :key="ticket.feedback_id" class="fb-card"><div class="fb-card-head"><router-link :to="`/teacher/feedback/${ticket.feedback_id}`" class="fb-link">{{ feedbackTitle(ticketNames[ticket.feedback_id]) }}</router-link><button class="fb-btn" type="button" :disabled="retrying" @click="retryTicket(ticket.feedback_id)">重试该反馈</button></div><p>{{ feedbackLabel('status', ticket.status) }} · 反馈版本 {{ ticket.ticket_version ?? '未提供' }}</p><div class="fb-table-wrap"><table class="fb-table"><thead><tr><th>动作</th><th>事件类型</th><th>状态</th><th>尝试</th><th>核对说明</th></tr></thead><tbody><tr v-for="item in ticket.items" :key="item.action_id"><td>{{ feedbackLabel('action', item.action) }}</td><td>{{ feedbackLabel('event', item.event_type) }}</td><td>{{ feedbackLabel('eventStatus', item.status) }}</td><td>{{ item.attempts ?? '未提供' }}</td><td>{{ reconciliationNote(item) }}</td></tr></tbody></table></div></article></section>
  </div>
</template>
<script setup>
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import service from './feedback/api.js'
import { feedbackLabel, feedbackTitle, feedbackError, reconciliationNote } from './feedbackPresentation.js'
const data = reactive({ counts: {}, items: [], scanned: null, loaded: false })
const error = ref(''), message = ref(''), retrying = ref(false), loading = ref(true)
const ticketNames = reactive({}), namesError = ref('')
let alive = true, loadRead = 0, namesRead = 0
onBeforeUnmount(() => { alive = false; ++loadRead; ++namesRead })
async function loadNames() {
  if (!alive) return
  const read = ++namesRead, ids = [...new Set(data.items.map(item => item.feedback_id))]
  namesError.value = ''
  for (const id of ids) {
    try { const detail = await service.feedback.teacherDetail(id); if (!alive || read !== namesRead) return; ticketNames[id] = detail }
    catch (err) { if (!alive || read !== namesRead) return; namesError.value = feedbackError(err, '部分反馈标题读取失败，请重试。') }
  }
}
async function load() {
  if (!alive) return
  const read = ++loadRead; ++namesRead; loading.value = true; error.value = ''; data.loaded = false
  try { const res = await service.feedback.reconciliation(); if (!alive || read !== loadRead) return; if (!Array.isArray(res.items)) throw new Error('Incomplete response'); Object.assign(data, { counts: res.counts || {}, items: res.items, scanned: typeof res.scanned === 'number' ? res.scanned : null, loaded: true }); await loadNames() }
  catch (err) { if (alive && read === loadRead) { data.items = []; data.counts = {}; data.scanned = null; error.value = feedbackError(err, '加载事件核对失败，请重试。') } }
  finally { if (alive && read === loadRead) loading.value = false }
}
async function retry(payload, success) {
  if (!alive || retrying.value) return
  error.value = ''; message.value = ''; retrying.value = true
  try { await service.feedback.retryEvents(payload); if (alive) { message.value = success; await load() } }
  catch (err) { if (alive) error.value = feedbackError(err, '重试失败，请稍后核对事件结果。') }
  finally { if (alive) retrying.value = false }
}
function retryTicket(ticketId) { return retry({ ticket_id: ticketId }, '该反馈的待同步事件已重试，请核对读取结果。') }
function retryAll() { return retry({}, '待同步事件已重试，请核对读取结果。') }
onMounted(load)
</script>
<style scoped src="../shared/feedback/page.css"></style>
