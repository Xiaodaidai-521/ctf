<template>
  <div class="fb-page">
    <div class="fb-header">
      <div>
        <span class="fb-eyebrow">事件核对</span>
        <h1 class="fb-title">反馈事件核对</h1>
        <p class="fb-sub">
          检查反馈处理记录是否完整。未同步的记录可以重试；内容不一致时需要人工核对，不会自动覆盖。
        </p>
      </div>
      <div class="fb-actions">
        <router-link to="/teacher/feedback" class="fb-btn">返回反馈处理</router-link>
        <button class="fb-btn" type="button" @click="load">刷新</button>
      </div>
    </div>

    <div class="fb-notice">
      <strong>事件核对不等于审批或发布。</strong>
      这里只检查反馈处理记录，不会修改学生成绩、核验结论或课程规则。
    </div>

    <div v-if="error" class="fb-error" role="alert">{{ error }}</div>
    <div v-if="message" class="fb-success" role="status">{{ message }}</div>

    <section class="fb-panel">
      <div class="fb-meta">
        <span class="fb-badge fb-badge-ok">已关联：{{ data.counts.linked }}</span>
        <span class="fb-badge fb-badge-warn">待重试：{{ data.counts.pending }}</span>
        <span class="fb-badge fb-badge-danger">内容不一致：{{ data.counts.mismatch }}</span>
        <span class="fb-badge fb-badge-muted">事件缺失：{{ data.counts.missing }}</span>
        <span class="fb-badge fb-badge-muted">已检查反馈：{{ data.scanned }}</span>
      </div>
      <p class="fb-muted">重试只补齐未同步的记录，内容差异仍需人工核对。</p>
      <div class="fb-actions">
        <button class="fb-btn fb-btn-primary" type="button" :disabled="retrying" @click="retryAll">
          {{ retrying ? '重试中...' : '重试全部待同步事件' }}
        </button>
      </div>
    </section>

    <section class="fb-panel">
      <h2>需要关注的反馈</h2>
      <div v-if="namesError" class="fb-error" role="alert">
        {{ namesError }}
        <button class="fb-btn" type="button" @click="loadNames">重试读取标题</button>
      </div>
      <div v-if="loading" class="fb-empty" role="status">正在核对反馈记录…</div>
      <div v-else-if="!data.items.length && !error" class="fb-empty">本次检查的反馈中没有待处理差异。</div>
      <div v-else class="fb-list">
        <article v-for="ticket in data.items" :key="ticket.feedback_id" class="fb-card">
          <div class="fb-card-head">
            <div>
              <div class="fb-card-title">
                <router-link :to="`/teacher/feedback/${ticket.feedback_id}`" class="fb-link">{{ feedbackTitle(ticketNames[ticket.feedback_id]) }}</router-link>
              </div>
              <div class="fb-meta">
                <span>{{ feedbackLabel('status', ticket.status) }}</span>
                <span class="fb-badge fb-badge-warn">待重试 {{ ticket.counts.pending }}</span>
                <span class="fb-badge fb-badge-danger">不一致 {{ ticket.counts.mismatch }}</span>
                <span class="fb-badge fb-badge-muted">缺失 {{ ticket.counts.missing }}</span>
              </div>
            </div>
            <button class="fb-btn" type="button" @click="retryTicket(ticket.feedback_id)">重试该反馈</button>
          </div>
          <div class="fb-table-wrap">
            <table class="fb-table">
              <thead><tr><th>处理动作</th><th>记录内容</th><th>核对状态</th><th>重试次数</th><th>最近核对</th><th>处理建议</th></tr></thead>
              <tbody>
                <tr v-for="item in ticket.items" :key="item.action_id">
                  <td>{{ feedbackLabel('action', item.action) }}</td>
                  <td>{{ feedbackLabel('event', item.event_type) }}</td>
                  <td>
                    <span class="fb-badge" :class="item.status === 'linked' ? 'fb-badge-ok' : item.status === 'mismatch' ? 'fb-badge-danger' : 'fb-badge-warn'">
                      {{ feedbackLabel('eventStatus', item.status) }}
                    </span>
                  </td>
                  <td>{{ item.attempts }}</td>
                  <td>{{ formatDate(item.checked_at) }}</td>
                  <td>{{ reconciliationNote(item) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import service from './feedback/api.js'
import { feedbackDate as formatDate, feedbackError, feedbackLabel, feedbackTitle, reconciliationNote } from './feedbackPresentation.js'

const data = reactive({ counts: { linked: 0, pending: 0, mismatch: 0, missing: 0 }, items: [], scanned: 0 })
const error = ref('')
const message = ref('')
const retrying = ref(false)
const loading = ref(false)
const ticketNames = reactive({})
const namesError = ref('')
let loadGeneration = 0
let namesGeneration = 0

async function loadNames() {
  const generation = ++namesGeneration
  namesError.value = ''
  // Resolve one at a time, without blocking the existing retry operations.
  for (const ticket of data.items) {
    if (generation !== namesGeneration) return
    if (ticketNames[ticket.feedback_id]) continue
    try {
      const detail = await service.feedback.teacherDetail(ticket.feedback_id)
      if (generation !== namesGeneration) return
      ticketNames[ticket.feedback_id] = detail
    } catch (err) {
      if (generation !== namesGeneration) return
      namesError.value = feedbackError(err, '部分反馈标题未能读取，仍可打开反馈或重试核对。')
      break
    }
  }
}

async function load() {
  const generation = ++loadGeneration
  ++namesGeneration
  error.value = ''
  loading.value = true
  try {
    const res = await service.feedback.reconciliation()
    if (generation !== loadGeneration) return
    Object.assign(data, res)
    loading.value = false
    void loadNames()
  } catch (err) {
    if (generation !== loadGeneration) return
    error.value = feedbackError(err, '加载事件核对失败，请重试。')
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

async function retryTicket(ticketId) {
  error.value = ''
  message.value = ''
  try {
    await service.feedback.retryEvents({ ticket_id: ticketId })
    message.value = '该反馈的待同步事件已重试。'
    await load()
  } catch (err) {
    error.value = feedbackError(err, '重试失败，请稍后再试。')
  }
}

async function retryAll() {
  error.value = ''
  message.value = ''
  retrying.value = true
  try {
    await service.feedback.retryEvents({})
    message.value = '全部待同步事件已重试。'
    await load()
  } catch (err) {
    error.value = feedbackError(err, '批量重试失败，请稍后再试。')
  } finally {
    retrying.value = false
  }
}

onMounted(load)
</script>

<style src="@/assets/feedback.css"></style>
