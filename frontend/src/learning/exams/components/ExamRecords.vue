<template>
  <div class="exam-records-page">
    <header class="page-header">
      <p class="page-eyebrow">{{ names.exams }} · 测评记录</p>
      <h1>{{ names.exams }} · 测评记录</h1>
      <p class="page-subtitle">测评成长与全部历史；筛选结果会保留在地址栏，刷新或分享后一致。</p>
    </header>

    <ExamOverview :records="history" />

    <section class="records-section" aria-labelledby="records-heading">
      <header class="section-heading">
        <h2 id="records-heading">全部记录</h2>
        <p class="section-note">最近五条只是摘要；这里保留全部历史与五类状态。</p>
      </header>

      <div class="filter-bar" role="group" aria-label="筛选测评记录">
        <label>
          考试类型
          <select v-model="filterType">
            <option v-for="option in typeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
        <label>
          考试状态
          <select v-model="filterStatus">
            <option v-for="option in statusOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
      </div>

      <div v-if="loading" class="page-state" role="status">正在读取测评记录…</div>
      <div v-else-if="error" class="page-state is-error" role="alert">
        <p>{{ error }}</p>
        <button type="button" class="btn btn-primary" @click="loadHistory">重试</button>
      </div>
      <div v-else-if="!history.length" class="page-state empty-state">
        <AppIcon name="bi-clock" />
        <h3>暂无考试记录</h3>
        <p>开始测试后，考试记录将显示在这里。</p>
        <button type="button" class="btn btn-primary" @click="goToExamCenter">开始测试</button>
      </div>
      <div v-else-if="!filteredHistory.length" class="page-state" role="status">
        没有符合当前筛选的记录，请调整考试类型或状态。
      </div>
      <div v-else class="history-list">
        <button v-for="record in filteredHistory" :key="record.id" type="button" class="history-item" @click="viewResult(record.id)">
          <span class="history-left">
            <span class="history-type">{{ record.typeLabel }}</span>
            <span class="history-title">{{ record.title }}</span>
            <span class="history-time">{{ formatDateTime(record.date) }}</span>
            <ProtectionBadge :status="record.protection?.user_answer" label="考试答案加密保存" compact />
            <span class="history-meta">
              <span v-if="record.questionCount !== null && record.questionCount !== undefined">共 {{ record.questionCount }} 题</span>
              <span>用时 {{ formatTime(record.durationSeconds) }}</span>
            </span>
          </span>
          <span class="history-right">
            <span class="history-score" :class="{ passed: record.status === 'completed' && record.passed === true, failed: record.status === 'completed' && record.passed === false }">
              {{ record.score === null ? '—' : record.score + '分' }}
            </span>
            <span class="history-status">{{ record.statusLabel }}</span>
            <span v-if="record.status === 'completed'" class="history-passed">
              {{ record.passed === true ? '通过' : record.passed === false ? '未通过' : '待判定' }}
            </span>
          </span>
        </button>
      </div>
    </section>

    <div class="action-buttons">
      <button type="button" class="btn" @click="backToCenter">
        <AppIcon name="bi-arrow-left" />返回{{ names.exams }}
      </button>
    </div>
  </div>
</template>
<script setup>
import ProtectionBadge from '@/shared/privacy/ProtectionBadge.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/shared/design/AppIcon.vue'
import { names } from '@/shared/navigation/names'
import {
  EXAM_STATUS_FILTERS, EXAM_TYPE_FILTERS, RECORDS_PATH, RESULT_PATH, examsApi,
  filterRecords, formatDuration, parseRecordQuery, recordView,
} from '../api.js'
import ExamOverview from './ExamOverview.vue'

const route = useRoute()
const router = useRouter()
const initial = parseRecordQuery(route?.query)
const history = ref([])
const loading = ref(true)
const error = ref('')
const filterType = ref(initial.type)
const filterStatus = ref(initial.status)
const typeOptions = EXAM_TYPE_FILTERS
const statusOptions = EXAM_STATUS_FILTERS

const filteredHistory = computed(() => filterRecords(history.value, { type: filterType.value, status: filterStatus.value }).map(recordView))

// 筛选写回地址栏；replace 不额外增加历史栈，浏览器返回仍回到进入记录区前的页面。
watch([filterType, filterStatus], ([type, status]) => {
  const current = parseRecordQuery(route?.query)
  if (current.type === type && current.status === status) return
  const query = {}
  if (type) query.type = type
  if (status) query.status = status
  router.replace({ path: RECORDS_PATH, query })
})

const formatTime = formatDuration
function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
const viewResult = recordId => router.push(RESULT_PATH(recordId))
const backToCenter = () => router.push('/exam-center')
const goToExamCenter = () => router.push('/exam-center')

async function loadHistory() {
  loading.value = true
  error.value = ''
  try {
    const response = await examsApi.myHistory()
    history.value = Array.isArray(response?.records) ? response.records : []
  } catch {
    // 失败不冒充空列表；保留筛选条件供重试后继续。
    error.value = '测评记录暂时未能读取，请重试。'
  } finally {
    loading.value = false
  }
}

onMounted(loadHistory)
defineExpose({ history, loading, error, filterType, filterStatus, filteredHistory, loadHistory, viewResult, backToCenter, goToExamCenter })
</script>
<style scoped>
.exam-records-page { width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: 0 auto; padding: var(--space-3) 0 var(--space-6); color: var(--ink); }
.page-header { margin-bottom: var(--space-3); }
.page-eyebrow { margin: 0 0 2px; color: var(--ink-secondary); font-size: var(--text-caption); }
.page-header h1 { margin: 0 0 var(--space-1); font-size: var(--text-page); line-height: var(--leading-tight); }
.page-subtitle { margin: 0; color: var(--ink-secondary); }
.records-section { margin-top: var(--space-3); padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); }
.section-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--space-1) var(--space-2); margin-bottom: var(--space-2); }
.section-heading h2 { margin: 0; font-size: var(--text-section); }
.section-note { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.filter-bar { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--space-2); }
.filter-bar label { display: grid; gap: var(--space-1); color: var(--ink-secondary); font-size: var(--text-caption); }
.filter-bar select { min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.page-state { margin-bottom: var(--space-2); padding: var(--space-3); border-radius: var(--radius-panel); background: var(--surface-muted); color: var(--ink-secondary); }
.page-state.is-error { background: var(--negative-soft); color: var(--negative); }
.empty-state { display: grid; justify-items: start; gap: var(--space-1); }
.empty-state h3 { margin: 0; font-size: var(--text-card); }
.empty-state p { margin: 0; }
.history-list { display: grid; }
.history-item { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); width: 100%; padding: var(--space-2); border: 0; border-top: var(--stroke) solid var(--line); background: transparent; color: var(--ink); font: inherit; text-align: left; cursor: pointer; transition: background var(--motion-fast) var(--motion-ease); }
.history-item:hover { background: var(--surface-hover); }
.history-item:focus-visible, .filter-bar select:focus-visible, .btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.history-left { display: grid; gap: var(--space-1); min-width: 0; overflow-wrap: anywhere; }
.history-type { justify-self: start; padding: 0 var(--space-1); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.history-title { font-size: var(--text-card); font-weight: var(--weight-strong); }
.history-time, .history-meta, .history-status, .history-passed { color: var(--ink-secondary); font-size: var(--text-caption); }
.history-meta { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.history-right { display: grid; gap: var(--space-1); flex: none; text-align: right; }
.history-score { font-size: var(--text-section); font-weight: var(--weight-strong); }
.history-score.passed { color: var(--positive); }
.history-score.failed { color: var(--negative); }
.action-buttons { margin-top: var(--space-2); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1); min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.is-compact .filter-bar { flex-direction: column; }
.is-compact .history-item { align-items: flex-start; flex-direction: column; }
.is-compact .history-right { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); text-align: left; }
@media (prefers-reduced-motion: reduce) { .history-item { transition: none; } }
</style>
