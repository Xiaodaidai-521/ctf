<template>
  <section class="learning-report" aria-labelledby="report-heading">
    <header class="section-head">
      <div>
        <h2 id="report-heading">学习结论与报告</h2>
        <p class="section-note">周报根据已记录的学习情况生成，缺少的数据保留为空；若不是本周的记录，会标为“最近一期周报”。</p>
      </div>
    </header>

    <p v-if="loading" class="state-note" role="status">正在读取周报…</p>
    <p v-else-if="error" class="state-note is-error" role="alert">{{ error }}<button type="button" class="text-action" @click="load">重试</button></p>
    <div v-else-if="!report" class="state-note">暂无已生成的周报，这里不展示模拟周报。</div>

    <article v-else class="report-card">
      <header class="report-card-head">
        <div>
          <span class="report-label">{{ report.label }}</span>
          <h3>{{ formatDate(report.week_start) }} 起</h3>
        </div>
        <span class="generated-at">生成时间 {{ report.generated_at ? formatDateTime(report.generated_at) : '—' }}</span>
      </header>
      <dl class="report-grid">
        <div><dt>学习时长</dt><dd>{{ report.total_study_minutes === null ? '—' : `${report.total_study_minutes} 分钟` }}</dd></div>
        <div><dt>完成模块</dt><dd>{{ valueText(report.modules_completed) }}</dd></div>
        <div><dt>完成练习</dt><dd>{{ valueText(report.exercises_completed) }}</dd></div>
        <div><dt>掌握概念</dt><dd>{{ valueText(report.concepts_mastered) }}</dd></div>
        <div><dt>智能体互动</dt><dd>{{ valueText(report.ai_interactions) }}</dd></div>
        <div><dt>沙箱执行</dt><dd>{{ valueText(report.sandbox_executions) }}</dd></div>
      </dl>
    </article>

    <section class="teaching-card" aria-labelledby="teaching-heading">
      <h3 id="teaching-heading" class="panel-title">个性化教学方案</h3>
      <p v-if="teachingLoading" class="state-note" role="status">正在读取教学方案…</p>
      <p v-else-if="teachingError" class="state-note is-error" role="alert">{{ teachingError }}</p>
      <p v-else-if="!teachingPlan" class="state-note">暂无教学方案。</p>
      <template v-else>
        <p class="plan-validity">{{ teachingPlan.validity_label || '依据：本人自评与教师评分' }}</p>
        <p class="plan-summary">{{ teachingPlan.summary || '方案摘要暂未返回。' }}</p>
        <ol class="plan-steps">
          <li v-for="item in planItems" :key="item.phase">
            <strong>{{ item.phase }} · {{ item.title }}</strong>
            <span class="plan-duration">{{ item.duration || '时长待定' }}</span>
            <ul>
              <li v-for="action in item.actions || []" :key="action">{{ action }}</li>
            </ul>
          </li>
        </ol>
      </template>
    </section>
  </section>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/api'
import { formatDate, weeklyReport } from '../presentation.js'

const props = defineProps({
  // 教学方案由总览统一请求一次后下发；本组件不再重复 GET（该接口每次 GET 都会重算方案）。
  teachingPlan: { type: Object, default: null },
  teachingLoading: { type: Boolean, default: false },
  teachingError: { type: String, default: '' },
})

const report = ref(null)
const loading = ref(true)
const error = ref('')

const planItems = computed(() => (Array.isArray(props.teachingPlan?.plan_items) ? props.teachingPlan.plan_items : []))
const valueText = value => (value === null || value === undefined ? '—' : value)
const formatDateTime = value => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const payload = await api.analytics.weeklySummary()
    report.value = weeklyReport(payload)
  } catch {
    report.value = null
    error.value = '周报暂时未能读取，请重试。'
  } finally {
    loading.value = false
  }
}

onMounted(load)
defineExpose({ load, report, loading })
</script>
<style scoped>
.learning-report { display: grid; gap: var(--space-2); }
.section-head h2 { margin: 0 0 var(--space-1); font-size: var(--text-section); }
.section-note { margin: 0; max-width: var(--reading-width); color: var(--ink-secondary); font-size: var(--text-caption); }
.state-note { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); }
.state-note.is-error { background: var(--negative-soft); color: var(--negative); }
.text-action { margin-left: var(--space-1); padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; cursor: pointer; }
.report-card, .teaching-card { min-width: 0; padding: var(--space-3); border-radius: var(--radius-panel); background: var(--surface); }
.report-card-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--space-2); margin-bottom: var(--space-2); }
.report-label { display: inline-flex; padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--action-soft); color: var(--action); font-size: var(--text-caption); }
.report-card-head h3 { margin: var(--space-1) 0 0; font-size: var(--text-card); }
.generated-at { color: var(--ink-muted); font-size: var(--text-caption); }
.report-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-2); margin: 0; }
.report-grid dt { color: var(--ink-secondary); font-size: var(--text-caption); }
.report-grid dd { margin: var(--space-1) 0 0; font-size: var(--text-section); font-weight: var(--weight-strong); }
.panel-title { margin: 0 0 var(--space-2); font-size: var(--text-card); }
.plan-validity { display: inline-flex; padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.plan-summary { margin: var(--space-1) 0; color: var(--ink-secondary); }
.plan-steps { display: grid; gap: var(--space-2); margin: 0; padding-left: var(--space-3); }
.plan-steps li { display: grid; gap: var(--space-1); }
.plan-duration { color: var(--ink-muted); font-size: var(--text-caption); }
.plan-steps ul { margin: 0; padding-left: var(--space-3); color: var(--ink-secondary); font-size: var(--text-caption); }
.is-compact .report-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
@media (max-width: 640px) { .is-compact .report-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
