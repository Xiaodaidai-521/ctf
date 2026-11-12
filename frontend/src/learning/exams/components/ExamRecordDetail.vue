<template>
  <div class="exam-detail-page">
    <header class="page-header">
      <p class="page-eyebrow">{{ names.exams }} · 测评结果</p>
      <h1>{{ record?.exam_title || record?.title || '测评结果' }}</h1>
      <p class="page-subtitle">逐题记录只呈现后台已返回的题面、本人答案与得分；不向其他接口补取参考答案。</p>
    </header>

    <div v-if="loading" class="page-state" role="status">正在读取测评结果…</div>

    <div v-else-if="!record" class="page-state is-error" role="alert">
      <p>{{ error || '测评结果暂时未能读取，请重试。' }}</p>
      <button type="button" class="btn btn-primary" @click="loadResult">重新加载结果</button>
      <button type="button" class="btn" @click="backToRecords">返回测评记录</button>
    </div>

    <template v-else>
      <p v-if="error" class="page-state is-error" role="alert">
        {{ error }}<button type="button" class="text-action" @click="loadResult">重试</button>
      </p>

      <section class="result-overview" aria-labelledby="result-heading">
        <h2 id="result-heading" class="visually-hidden">测评总结果</h2>
        <div class="score-block">
          <p class="score-number">{{ record.score === null ? '—' : record.score }}</p>
          <p class="score-label">总分{{ record.totalPoints === null ? '' : ` / ${record.totalPoints}` }}</p>
          <p class="result-badge" :class="{ passed: record.is_passed === true, failed: record.is_passed === false }">{{ passCondition(record).text }}</p>
        </div>
        <dl class="info-grid">
          <div><dt>考试类型</dt><dd>{{ record.exam_type_display || examTypeLabel(record.exam_type) }}</dd></div>
          <div><dt>题数</dt><dd>{{ questionCount }}</dd></div>
          <div><dt>正确题数</dt><dd>{{ record.correct_count === null ? '—' : `${record.correct_count} / ${questionCount}` }}</dd></div>
          <div><dt>正确率</dt><dd>{{ accuracyText }}</dd></div>
          <div><dt>用时</dt><dd>{{ formatDuration(record.time_spent) }}</dd></div>
          <div><dt>开始时间</dt><dd>{{ formatDateTime(record.start_time || record.created_at) }}</dd></div>
          <div><dt>结束时间</dt><dd>{{ formatDateTime(record.end_time) }}</dd></div>
          <div><dt>通过条件</dt><dd>{{ passCondition(record).text }}</dd></div>
        </dl>
      </section>

      <section class="answers-section" aria-labelledby="answers-heading">
        <header class="section-heading">
          <h2 id="answers-heading">答题详情</h2>
          <p class="section-note">{{ answers.length }} 条答题记录</p>
          <ProtectionBadge :status="record.protection?.user_answer" label="你提交的考试答案加密保存" />
        </header>
        <p v-if="!answers.length" class="page-state">暂无答题明细。</p>
        <ol v-else class="answers-list">
          <li v-for="(answer, index) in answers" :key="answer.id ?? index" class="answer-item" :class="{ correct: answer.correct === true, wrong: answer.correct === false }">
            <div class="answer-header">
              <h3 class="answer-number">第 {{ index + 1 }} 题</h3>
              <span class="answer-status">
                <AppIcon v-if="answer.correct === true" name="bi-check-circle" />
                <AppIcon v-else-if="answer.correct === false" name="bi-x-lg" />
                {{ answer.correct === true ? '正确' : answer.correct === false ? '错误' : '待判定' }}
              </span>
              <span class="answer-points">{{ answer.score === null ? '—' : `${answer.score} 分` }}</span>
            </div>
            <p class="question-text">{{ answer.stem || '题面由后台返回后显示；本次未返回题面。' }}</p>
            <dl class="answer-comparison">
              <div>
                <dt>你的答案</dt>
                <dd>{{ answer.answer === null || answer.answer === '' ? '未作答' : answer.answer }} <ProtectionBadge :status="answer.protection?.user_answer" label="答案加密保存" /></dd>
              </div>
              <div v-if="answer.correctAnswer !== null">
                <dt>后台提供的答案</dt>
                <dd>{{ answer.correctAnswer }}</dd>
              </div>
              <div v-else-if="answer.correct === false">
                <dt>后台提供的答案</dt>
                <dd class="muted">本次结果未返回参考答案。</dd>
              </div>
            </dl>
          </li>
        </ol>
      </section>

      <div class="action-buttons">
        <button type="button" class="btn" @click="backToRecords"><AppIcon name="bi-arrow-left" />返回测评记录</button>
        <button v-if="record.practiceRecordId" type="button" class="btn btn-primary" @click="goToPracticeExam">
          进入实战考试<AppIcon name="bi-chevron-right" />
        </button>
        <button type="button" class="btn" :class="record.practiceRecordId ? '' : 'btn-primary'" @click="retakeExam">
          <AppIcon name="bi-arrow-clockwise" />再次挑战
        </button>
      </div>
    </template>
  </div>
</template>
<script setup>
import ProtectionBadge from '@/shared/privacy/ProtectionBadge.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/shared/design/AppIcon.vue'
import { names } from '@/shared/navigation/names'
import { RECORDS_PATH, accuracy, examTypeLabel, examsApi, formatDuration, passCondition, resultView } from '../api.js'

const route = useRoute()
const router = useRouter()
const recordId = computed(() => route.params.id)
const record = ref(null)
const loading = ref(true)
const error = ref('')
let requestVersion = 0

const answers = computed(() => record.value?.answers || [])
const questionCount = computed(() => {
  const total = Number(record.value?.total_questions)
  return Number.isFinite(total) ? total : answers.value.length
})
const accuracyText = computed(() => {
  const value = accuracy(record.value?.correct_count, questionCount.value)
  return value === null ? '—' : `${value}%`
})

function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
const backToRecords = () => router.push(RECORDS_PATH)
const retakeExam = () => router.push('/exam-center')
const goToPracticeExam = () => {
  if (record.value?.practiceRecordId) router.push(`/exam-taking/${record.value.practiceRecordId}`)
}

async function loadResult() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const data = resultView(await examsApi.result(recordId.value))
    if (version !== requestVersion) return
    record.value = data
  } catch {
    if (version !== requestVersion) return
    // 已有结果时保留已读取的总成绩与逐题记录，只提示明细读取失败。
    error.value = record.value
      ? '本次结果的部分明细暂时未能读取，已保留已读取的成绩。请重试。'
      : '测评结果暂时未能读取，请重试或返回测评记录。'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

watch(recordId, (next, previous) => {
  if (next === previous) return
  record.value = null
  loadResult()
})
onMounted(loadResult)
defineExpose({ record, loading, error, answers, questionCount, accuracyText, loadResult })
</script>
<style scoped>
.exam-detail-page { width: min(var(--reading-width), calc(100% - var(--page-gutter) * 2)); margin: 0 auto; padding: var(--space-3) 0 var(--space-6); color: var(--ink); }
.page-header { margin-bottom: var(--space-3); }
.page-eyebrow { margin: 0 0 2px; color: var(--ink-secondary); font-size: var(--text-caption); }
.page-header h1 { margin: 0 0 var(--space-1); font-size: var(--text-page); line-height: var(--leading-tight); overflow-wrap: anywhere; }
.page-subtitle { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.page-state { margin-bottom: var(--space-2); padding: var(--space-3); border-radius: var(--radius-panel); background: var(--surface-muted); color: var(--ink-secondary); }
.page-state.is-error { background: var(--negative-soft); color: var(--negative); }
.result-overview { display: grid; grid-template-columns: minmax(0, .8fr) minmax(0, 2fr); gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-panel); background: var(--surface); margin-bottom: var(--space-2); }
.score-block { display: grid; align-content: start; gap: var(--space-1); }
.score-number { margin: 0; font-size: var(--text-page); font-weight: var(--weight-strong); line-height: var(--leading-tight); }
.score-label { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.result-badge { justify-self: start; margin: 0; padding: var(--space-1) var(--space-2); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.result-badge.passed { background: var(--positive-soft); color: var(--positive); }
.result-badge.failed { background: var(--negative-soft); color: var(--negative); }
.info-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-2); margin: 0; }
.info-grid dt { color: var(--ink-secondary); font-size: var(--text-caption); }
.info-grid dd { margin: 0; font-size: var(--text-card); font-weight: var(--weight-medium); overflow-wrap: anywhere; }
.answers-section { padding: var(--space-3); border-radius: var(--radius-panel); background: var(--surface); }
.section-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--space-1) var(--space-2); margin-bottom: var(--space-2); }
.section-heading h2 { margin: 0; font-size: var(--text-section); }
.section-note { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.answers-list { display: grid; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }
.answer-item { padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); }
.answer-header { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.answer-number { margin: 0; font-size: var(--text-card); }
.answer-status { display: inline-flex; align-items: center; gap: var(--space-1); color: var(--ink-secondary); font-size: var(--text-caption); }
.answer-item.correct .answer-status { color: var(--positive); }
.answer-item.wrong .answer-status { color: var(--negative); }
.answer-points { margin-left: auto; color: var(--ink-secondary); font-size: var(--text-caption); }
.question-text { margin: var(--space-1) 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.answer-comparison { display: grid; gap: var(--space-1); margin: 0; }
.answer-comparison div { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--space-2); align-items: baseline; }
.answer-comparison dt { color: var(--ink-secondary); font-size: var(--text-caption); }
.answer-comparison dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.answer-comparison .muted { color: var(--ink-muted); }
.action-buttons { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-3); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1); min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.text-action { margin-left: var(--space-1); padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; cursor: pointer; }
.visually-hidden { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.is-compact .result-overview { grid-template-columns: minmax(0, 1fr); }
.is-compact .info-grid { grid-template-columns: minmax(0, 1fr); }
.is-compact .answer-comparison div { grid-template-columns: minmax(0, 1fr); gap: 2px; }
.is-compact .action-buttons { flex-direction: column; }
</style>
