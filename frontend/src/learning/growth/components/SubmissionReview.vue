<template>
  <section class="submission-review" aria-labelledby="submission-heading">
    <header class="block-head">
      <div>
        <h3 id="submission-heading">我的提交与复盘</h3>
        <p class="block-note">系统检查结果和老师评阅分开显示；做题时用过提示或讲解会如实记录，重交也不会变成独立完成。这里只显示你自己的记录。</p>
      </div>
      <button type="button" class="text-action" :disabled="loading" @click="load">刷新</button>
    </header>

    <p v-if="loading" class="state-note" role="status">正在读取本人提交…</p>
    <p v-else-if="error" class="state-note is-error" role="alert">{{ error }}<button type="button" class="text-action" @click="load">重试</button></p>
    <p v-else-if="!rows.length" class="state-note">还没有提交记录。完成一次任务提交后，可按提交逐条写复盘或提出复核。</p>

    <ul v-else class="submission-items">
      <li v-for="item in rows" :key="item.id" class="submission-item">
        <header class="submission-head">
          <div class="submission-title">
            <strong>{{ item.taskTitle }}</strong>
            <span class="meta">{{ [item.trackLabel, item.versionLabel, item.submittedLabel].filter(Boolean).join(' · ') }}</span>
          </div>
          <span class="status-chip" :class="badgeClass(item.overallStatus)">{{ item.overallLabel }}</span>
        </header>

        <div class="status-grid">
          <div><span class="label">程序核验</span><strong>{{ item.programLabel }}</strong></div>
          <div><span class="label">教师评阅</span><strong>{{ item.manualLabel }}</strong></div>
          <div><span class="label">本次帮助</span><strong>{{ item.independenceLabel }}<template v-if="item.assistanceLevelLabel"> · {{ item.assistanceLevelLabel }}</template></strong></div>
          <div><span class="label">保存</span><strong>{{ item.saveLabel }}</strong></div>
        </div>

        <p v-if="item.note" class="note">{{ item.note }}</p>
        <p v-if="item.answerExposure" class="note is-warn">已查看过同题解析，重做不计为首次独立完成。</p>
        <p v-if="item.corrected" class="note">本次结果来自更正版本（v{{ item.resultVersion }}）；原结果仍按版本保留。</p>

        <details class="items-block">
          <summary>分项结果（{{ item.items.length }} 项）</summary>
          <ul v-if="item.items.length" class="items">
            <li v-for="entry in item.items" :key="`${entry.label}-${entry.kindLabel}`">
              <span class="item-label">{{ entry.label }}</span>
              <span class="meta">{{ entry.kindLabel }}</span>
              <strong :class="{ 'is-failed': entry.status === 'failed' }">{{ entry.statusLabel }}</strong>
              <span class="meta">{{ entry.score === null ? '—' : entry.score }}{{ entry.maxPoints ? ` / ${entry.maxPoints}` : '' }}</span>
            </li>
          </ul>
          <p v-else class="note">暂未提供分项结果，请以已有总评与教师评语为准。</p>
        </details>

        <details v-if="item.totalScore !== null || item.remarks" class="items-block">
          <summary>量表与教师评语</summary>
          <p class="note">总分 {{ item.totalScore === null ? '—' : item.totalScore }} / {{ item.maxTotalScore === null ? '—' : item.maxTotalScore }}</p>
          <p v-if="item.remarks" class="note">{{ item.remarks }}</p>
        </details>

        <div class="submission-actions">
          <button v-if="!completedCards[item.id]" type="button" class="btn" @click="toggleCard(item)">{{ activeCard === item.id ? '收起复盘卡' : '复盘卡' }}</button>
          <span v-else class="status-chip is-completed">复盘已完成</span>
          <button type="button" class="btn" @click="toggleDispute(item)">{{ activeDispute === item.id ? '收起复核' : '提出复核' }}</button>
        </div>
        <p v-if="actionFeedback[item.id]" class="form-message" :class="{ 'is-error': actionFeedback[item.id].error }" role="status">{{ actionFeedback[item.id].text }}</p>

        <ReviewCardEditor
          v-if="activeCard === item.id"
          :submission="item"
          @close="activeCard = null"
          @saved="onCardSaved(item, $event)"
        />
        <DisputeForm
          v-if="activeDispute === item.id"
          :submission="item"
          @close="activeDispute = null"
          @saved="onDisputeSaved(item, $event)"
        />
      </li>
    </ul>

    <section v-if="disputes.length || disputesError" class="dispute-history" aria-labelledby="dispute-history-heading">
      <h4 id="dispute-history-heading">本人复核记录</h4>
      <p v-if="disputesError" class="state-note is-error" role="alert">{{ disputesError }}<button type="button" class="text-action" @click="loadDisputes">重试</button></p>
      <ul v-else class="dispute-items">
        <li v-for="dispute in disputes" :key="dispute.id">
          <div class="dispute-head">
            <strong>{{ dispute.taskTitle }}</strong>
            <span class="status-chip" :class="`is-${dispute.status}`">{{ dispute.statusLabel }}</span>
          </div>
          <p class="note">依据：{{ dispute.reason }}</p>
          <p class="note meta">提交 {{ dispute.createdLabel }}<template v-if="dispute.resolvedLabel"> · 处理 {{ dispute.resolvedLabel }}</template></p>
          <p v-if="dispute.resolution" class="note">处理结果：{{ dispute.resolution }}</p>
        </li>
      </ul>
      <p class="note meta">复核处理不直接改分；如需改分，教师会建立更正版本，并在提交结果中标注。</p>
    </section>
  </section>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import api from '@/api'
import { disputeViews, errorText, submissionViews } from '../reviewActions.js'
import ReviewCardEditor from './ReviewCardEditor.vue'
import DisputeForm from './DisputeForm.vue'

const emit = defineEmits(['saved', 'card-saved'])

const rows = ref([])
const loading = ref(true)
const error = ref('')
const activeCard = ref(null)
const activeDispute = ref(null)
const completedCards = reactive({})
const actionFeedback = reactive({})
const disputes = ref([])
const disputesError = ref('')

const badgeClass = status => ({ passed: 'is-completed', failed: 'is-missed', pending_manual: 'is-due' }[status] || '')

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = submissionViews(await api.skillReview.mySubmissions())
  } catch (err) {
    rows.value = []
    error.value = `本人提交暂时未能读取：${errorText(err)}`
  } finally {
    loading.value = false
  }
}

async function loadDisputes() {
  disputesError.value = ''
  try {
    disputes.value = disputeViews(await api.skillReview.myDisputes())
  } catch (err) {
    disputes.value = []
    disputesError.value = `复核记录暂时未能读取：${errorText(err)}`
  }
}

function toggleCard(item) {
  activeCard.value = activeCard.value === item.id ? null : item.id
  if (activeCard.value) activeDispute.value = null
  delete actionFeedback[item.id]
}

function toggleDispute(item) {
  activeDispute.value = activeDispute.value === item.id ? null : item.id
  if (activeDispute.value) activeCard.value = null
  delete actionFeedback[item.id]
}

function onCardSaved(item, result) {
  actionFeedback[item.id] = { text: result.message, error: Boolean(result.failed) }
  if (result.completed && !result.failed) {
    completedCards[item.id] = true
    activeCard.value = null
  }
  emit('card-saved', { item, ...result })
  emit('saved', { kind: 'card', ...result })
}

function onDisputeSaved(item, result) {
  actionFeedback[item.id] = { text: result.message, error: Boolean(result.failed) }
  if (!result.failed) {
    activeDispute.value = null
    loadDisputes()
  }
  emit('saved', { kind: 'dispute', ...result })
}

onMounted(() => { load(); loadDisputes() })
defineExpose({ load, loadDisputes, rows, loading, error, disputes, disputesError, toggleCard, toggleDispute, activeCard, activeDispute })
</script>
<style scoped>
.submission-review { display: grid; gap: var(--space-2); }
.block-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.block-head h3 { margin: 0 0 var(--space-1); font-size: var(--text-card); }
.block-note { margin: 0; max-width: var(--reading-width); color: var(--ink-secondary); font-size: var(--text-caption); }
.state-note { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); }
.state-note.is-error { background: var(--negative-soft); color: var(--negative); }
.text-action { padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.submission-items { display: grid; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }
.submission-item { padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); overflow-wrap: anywhere; }
.submission-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.submission-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-1); min-width: 0; }
.submission-title strong { overflow-wrap: anywhere; }
.meta { color: var(--ink-secondary); font-size: var(--text-caption); }
.status-chip { padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.status-chip.is-completed { background: var(--positive-soft); color: var(--positive); }
.status-chip.is-missed { background: var(--negative-soft); color: var(--negative); }
.status-chip.is-due { background: var(--warning-soft); color: var(--warning); }
.status-chip.is-resolved { background: var(--positive-soft); color: var(--positive); }
.status-chip.is-rejected { background: var(--negative-soft); color: var(--negative); }
.status-chip.is-under_review { background: var(--action-soft); color: var(--action); }
.status-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-2); margin: var(--space-2) 0; }
.status-grid .label { display: block; color: var(--ink-secondary); font-size: var(--text-caption); }
.note { margin: var(--space-1) 0 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.note.is-warn { color: var(--warning); }
.items-block { margin-top: var(--space-1); }
.items-block summary { min-height: var(--control-height); cursor: pointer; font-size: var(--text-caption); }
.items { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; font-size: var(--text-caption); }
.items li { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, .8fr) auto auto; gap: var(--space-1); align-items: baseline; }
.item-label { overflow-wrap: anywhere; }
.is-failed { color: var(--negative); }
.submission-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); margin-top: var(--space-2); }
.form-message { margin: var(--space-1) 0 0; color: var(--positive); font-size: var(--text-caption); }
.form-message.is-error { color: var(--negative); }
.btn { display: inline-flex; align-items: center; min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.dispute-history { display: grid; gap: var(--space-1); padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); }
.dispute-history h4 { margin: 0; font-size: var(--text-card); }
.dispute-items { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.dispute-items li { padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); }
.dispute-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-1); }
.btn:focus-visible, .text-action:focus-visible, .items-block summary:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.is-compact .status-grid, .is-compact .items li { grid-template-columns: repeat(2, minmax(0, 1fr)); }
@media (max-width: 640px) { .is-compact .status-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
