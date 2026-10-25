<template>
  <div class="fb-page">
    <div class="fb-header">
      <div>
        <span class="fb-eyebrow">模块七 · 事件核对</span>
        <h1 class="fb-title">反馈事件核对</h1>
        <p class="fb-sub">
          检查每个反馈状态变更是否写入统一学习事件。待重试链接可以安全重试；内容不一致不会自动覆盖，需要人工核对。
        </p>
      </div>
      <div class="fb-actions">
        <router-link to="/teacher/feedback" class="fb-btn">返回反馈待办</router-link>
        <button class="fb-btn" type="button" @click="load">刷新</button>
      </div>
    </div>

    <div class="fb-notice">
      <strong>事件核对不等于审批或发布。</strong>
      这里只核对反馈动作与统一事件的一致性；不会修改成绩、核验事实、教学配置或生产策略。
    </div>

    <div v-if="error" class="fb-error">{{ error }}</div>
    <div v-if="message" class="fb-success">{{ message }}</div>

    <section class="fb-panel">
      <div class="fb-meta">
        <span class="fb-badge fb-badge-ok">已关联：{{ data.counts.linked }}</span>
        <span class="fb-badge fb-badge-warn">待重试：{{ data.counts.pending }}</span>
        <span class="fb-badge fb-badge-danger">内容不一致：{{ data.counts.mismatch }}</span>
        <span class="fb-badge fb-badge-muted">事件缺失：{{ data.counts.missing }}</span>
        <span class="fb-badge fb-badge-muted">扫描：{{ data.scanned }}</span>
      </div>
      <p class="fb-muted">{{ data.note }}</p>
      <div class="fb-actions">
        <button class="fb-btn fb-btn-primary" type="button" :disabled="retrying" @click="retryAll">
          {{ retrying ? '重试中...' : '重试全部待同步事件' }}
        </button>
      </div>
    </section>

    <section class="fb-panel">
      <h2>需要关注的工单</h2>
      <div v-if="!data.items.length" class="fb-empty">全部事件已关联，没有待处理差异。</div>
      <div v-else class="fb-list">
        <article v-for="ticket in data.items" :key="ticket.feedback_id" class="fb-card">
          <div class="fb-card-head">
            <div>
              <div class="fb-card-title">
                <router-link :to="`/teacher/feedback/${ticket.feedback_id}`" class="fb-link">{{ ticket.feedback_id }}</router-link>
              </div>
              <div class="fb-meta">
                <span>{{ ticket.status_label }}</span>
                <span>工单版本：{{ ticket.ticket_version }}</span>
                <span class="fb-badge fb-badge-warn">待重试 {{ ticket.counts.pending }}</span>
                <span class="fb-badge fb-badge-danger">不一致 {{ ticket.counts.mismatch }}</span>
                <span class="fb-badge fb-badge-muted">缺失 {{ ticket.counts.missing }}</span>
              </div>
            </div>
            <button class="fb-btn" type="button" @click="retryTicket(ticket.feedback_id)">重试该工单</button>
          </div>
          <table class="fb-table">
            <thead><tr><th>动作</th><th>事件类型</th><th>事件 ID</th><th>状态</th><th>尝试</th><th>最后错误</th></tr></thead>
            <tbody>
              <tr v-for="item in ticket.items" :key="item.action_id">
                <td>{{ item.action }}</td>
                <td>{{ item.event_type }}</td>
                <td class="fb-mono">{{ item.event_id || '—' }}</td>
                <td>
                  <span class="fb-badge" :class="item.status === 'linked' ? 'fb-badge-ok' : item.status === 'mismatch' ? 'fb-badge-danger' : 'fb-badge-warn'">
                    {{ item.status_label }}
                  </span>
                </td>
                <td>{{ item.attempts }}</td>
                <td>{{ item.last_error || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import service from '@/api'

const data = reactive({ counts: { linked: 0, pending: 0, mismatch: 0, missing: 0 }, items: [], scanned: 0, note: '' })
const error = ref('')
const message = ref('')
const retrying = ref(false)

async function load() {
  error.value = ''
  try {
    const res = await service.feedback.reconciliation()
    Object.assign(data, res)
  } catch (err) {
    error.value = err.response?.data?.detail || '加载事件核对失败。'
  }
}

async function retryTicket(ticketId) {
  error.value = ''
  message.value = ''
  try {
    await service.feedback.retryEvents({ ticket_id: ticketId })
    message.value = '该工单的待同步事件已重试。'
    await load()
  } catch (err) {
    error.value = err.response?.data?.detail || '重试失败。'
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
    error.value = err.response?.data?.detail || '批量重试失败。'
  } finally {
    retrying.value = false
  }
}

onMounted(load)
</script>

<style src="@/assets/feedback.css"></style>
