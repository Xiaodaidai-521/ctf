<template>
  <section class="review-reminders" aria-labelledby="review-heading">
    <header class="section-head">
      <div>
        <h2 id="review-heading">待复习</h2>
        <p class="section-note">记忆概率与复习日期以已记录的复习情况为准；“完成复习”是本人自报，不等于通过无提示复测或已独立掌握。</p>
      </div>
      <span class="count-badge">{{ rows.length }} 项</span>
    </header>

    <p v-if="loading" class="state-note" role="status">正在读取复习提醒…</p>
    <p v-else-if="error" class="state-note is-error" role="alert">{{ error }}<button type="button" class="text-action" @click="load">重试</button></p>
    <p v-else-if="!rows.length" class="state-note">暂无待复习项；目前不能在这里添加复习任务。</p>

    <ul v-else class="review-list">
      <li v-for="item in rows" :key="item.id" class="review-item">
        <div class="review-main">
          <strong>{{ item.concept }}</strong>
          <div class="review-meta">
            <span>记忆率 {{ item.memoryRate }}</span>
            <span>建议复习 {{ item.dueLabel }}</span>
            <span v-if="item.challengeTitle">关联练习：{{ item.challengeTitle }}</span>
          </div>
          <p v-if="item.reason" class="review-reason">依据：{{ item.reason }}</p>
          <p v-if="feedback.id === item.id" class="review-feedback" :class="{ 'is-error': feedback.error }" role="status">{{ feedback.text }}</p>
        </div>
        <div class="review-actions">
          <button type="button" class="btn" @click="goPractice(item)" :disabled="!item.challengeId && !item.actionLink">去练习</button>
          <button type="button" class="btn btn-primary" :disabled="completingId === item.id" @click="complete(item)">{{ completingId === item.id ? '正在记录…' : '完成复习' }}</button>
          <router-link to="/my-results" class="text-link">写复盘 →</router-link>
        </div>
      </li>
    </ul>
  </section>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'
import { reviewRows } from '../presentation.js'

const router = useRouter()
const rows = ref([])
const loading = ref(true)
const error = ref('')
const completingId = ref(null)
const feedback = ref({ id: null, text: '', error: false })

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = reviewRows(await api.learningPaths.reviewReminders())
  } catch {
    rows.value = []
    error.value = '复习提醒暂时未能读取，请重试。'
  } finally {
    loading.value = false
  }
}

function goPractice(item) {
  if (item.challengeId) {
    router.push({ name: 'ChallengeDetail', params: { id: item.challengeId } })
    return
  }
  if (item.actionLink) router.push(item.actionLink)
}

async function complete(item) {
  if (completingId.value) return
  completingId.value = item.id
  feedback.value = { id: null, text: '', error: false }
  try {
    await api.learningPaths.completeReview({ state_id: item.id, success: true })
    await load()
    feedback.value = { id: null, text: '已记录本人完成复习；这不会自动写成掌握或复测通过。', error: false }
  } catch {
    feedback.value = { id: item.id, text: '完成记录尚未保存；复习项仍保留，请重试。', error: true }
  } finally {
    completingId.value = null
  }
}

onMounted(load)
defineExpose({ load, rows, loading, error, goPractice, complete, completingId })
</script>
<style scoped>
.review-reminders { display: grid; gap: var(--space-2); }
.section-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.section-head h2 { margin: 0 0 var(--space-1); font-size: var(--text-section); }
.section-note { margin: 0; max-width: var(--reading-width); color: var(--ink-secondary); font-size: var(--text-caption); }
.count-badge { padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.state-note { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); }
.state-note.is-error { background: var(--negative-soft); color: var(--negative); }
.text-action { margin-left: var(--space-1); padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; cursor: pointer; }
.review-list { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.review-item { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--space-2); padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); }
.review-main { display: grid; gap: var(--space-1); min-width: 0; }
.review-meta { display: flex; flex-wrap: wrap; gap: var(--space-2); color: var(--ink-secondary); font-size: var(--text-caption); }
.review-reason { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.review-feedback { margin: 0; color: var(--positive); font-size: var(--text-caption); }
.review-feedback.is-error { color: var(--negative); }
.review-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); }
.btn { display: inline-flex; align-items: center; gap: var(--space-1); min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn:disabled { border-color: var(--line); background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
.text-link { display: inline-flex; align-items: center; min-height: var(--control-height); color: var(--action); font-size: var(--text-caption); text-decoration: none; }
.is-compact .review-item { flex-direction: column; }
.btn:focus-visible, .text-link:focus-visible, .text-action:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
