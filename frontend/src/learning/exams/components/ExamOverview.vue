<template>
  <section class="exam-overview" aria-label="测评成长">
    <header class="overview-heading">
      <div>
        <p class="overview-eyebrow">{{ names.exams }} · 测评成长</p>
        <h2>等级、统计与成绩趋势</h2>
      </div>
      <p class="overview-note">统计只计已完成记录；趋势为百分比分口径。</p>
    </header>

    <p v-if="overviewLoading" class="overview-state" role="status">正在读取测评成长数据…</p>

    <div class="growth-grid">
      <section class="level-card" aria-labelledby="level-heading">
        <h3 id="level-heading" class="card-title">学习等级</h3>
        <p v-if="levelError" class="card-note is-error" role="alert">{{ levelError }}</p>
        <p v-else-if="statsError" class="card-note">等级依据平均成绩计算；统计暂未读取，暂不显示等级。</p>
        <p v-else-if="statsReady && stats.total_exams === 0" class="card-note">完成测评后，将根据真实成绩显示学习等级。</p>
        <div v-else-if="level.known" class="level-body">
          <div class="level-grade" aria-hidden="true">{{ level.current?.grade || '—' }}</div>
          <div class="level-info">
            <p class="level-title">{{ level.current?.title || '等级规则已读取' }}</p>
            <p class="level-desc">{{ level.current?.description || '' }}</p>
            <p class="level-next">
              <template v-if="level.top">已达到最高等级</template>
              <template v-else-if="level.next">距离下一等级还需 {{ level.remaining }} 分</template>
              <template v-else>等级规则暂未读取</template>
            </p>
            <div v-if="level.percent !== null" class="level-progress" role="progressbar" aria-label="当前等级进度" :aria-valuenow="level.percent" aria-valuemin="0" aria-valuemax="100">
              <span class="level-progress-fill" :style="{ width: level.percent + '%' }"></span>
            </div>
          </div>
        </div>
      </section>

      <section class="stats-card" aria-labelledby="stats-heading">
        <h3 id="stats-heading" class="card-title">测评统计</h3>
        <p v-if="statsError" class="card-note is-error" role="alert">{{ statsError }}<button type="button" class="text-action" @click="loadStats">重试</button></p>
        <dl v-else class="stats-grid">
          <div><dt>考试总数</dt><dd>{{ statValue(stats.total_exams) }}</dd></div>
          <div><dt>通过考试</dt><dd>{{ statValue(stats.passed_exams) }}</dd></div>
          <div><dt>平均成绩</dt><dd>{{ percentValue(stats.average_score) }}</dd></div>
          <div><dt>最高成绩</dt><dd>{{ percentValue(stats.best_score) }}</dd></div>
        </dl>
      </section>
    </div>

    <section class="trend-card" aria-labelledby="trend-heading">
      <header class="trend-heading">
        <h3 id="trend-heading" class="card-title">成绩趋势</h3>
        <p class="card-note">总分、理论、实战分别按已完成的同类型记录取当日平均。</p>
      </header>
      <div class="chart-wrap">
        <div ref="chartRef" class="trend-chart" role="img" aria-label="历次考试成绩趋势图"></div>
        <p v-if="trendError" class="card-note is-error" role="alert">{{ trendError }}<button type="button" class="text-action" @click="loadTrend">重试</button></p>
        <p v-else-if="trendLoading" class="card-note" role="status">正在读取成绩趋势…</p>
        <p v-else-if="!trend.dates.length" class="card-note">暂无可绘制成绩趋势的已完成记录。</p>
      </div>
      <details v-if="trend.dates.length" class="trend-table">
        <summary>查看成绩数据表</summary>
        <div class="table-scroll">
          <table>
            <caption>历次测评成绩（百分比分），未记录的成绩以“—”表示</caption>
            <thead><tr><th scope="col">日期</th><th scope="col">总分</th><th scope="col">理论</th><th scope="col">实战</th></tr></thead>
            <tbody>
              <tr v-for="(date, index) in trend.dates" :key="`${date}-${index}`">
                <th scope="row">{{ date }}</th>
                <td v-for="key in ['scores', 'theory_scores', 'practice_scores']" :key="key">{{ trend[key][index] === null ? '—' : trend[key][index] + '%' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </section>

    <section class="recent-card" aria-labelledby="recent-heading">
      <header class="trend-heading">
        <h3 id="recent-heading" class="card-title">最近五条</h3>
        <router-link :to="recordsPath" class="view-all">查看全部记录 →</router-link>
      </header>
      <p v-if="!recentViews.length" class="card-note">还没有测评记录；最近五条只是摘要，完整历史在记录区。</p>
      <ul v-else class="recent-list">
        <li v-for="record in recentViews" :key="record.id">
          <router-link v-if="record.href" :to="record.href" class="recent-item">
            <span class="recent-main">
              <span class="recent-type">{{ record.typeLabel }}</span>
              <span class="recent-title">{{ record.title }}</span>
              <span class="recent-date">{{ formatDateTime(record.date) }}</span>
            </span>
            <span class="recent-side">
              <span class="recent-score" :class="{ passed: record.status === 'completed' && record.passed === true, failed: record.status === 'completed' && record.passed === false }">{{ record.score === null ? '—' : record.score + '分' }}</span>
              <span class="recent-status">{{ record.statusLabel }}</span>
            </span>
          </router-link>
          <span v-else class="recent-item">{{ record.title }}</span>
        </li>
      </ul>
    </section>
  </section>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { names } from '@/shared/navigation/names'
import { normalizeTrend, scoreTrendOption } from '../trend.js'
import { RECORDS_PATH, examsApi, levelView, recordView, statPercent } from '../api.js'

const props = defineProps({
  // 记录区已读取的全部记录；概览只呈现最近五条，不替代完整历史。
  records: { type: Array, default: () => [] },
})

const recordsPath = RECORDS_PATH
const overviewLoading = ref(true)
const levelRules = ref([])
const levelError = ref('')
const statsReady = ref(false)
const statsError = ref('')
const stats = ref({ total_exams: null, passed_exams: null, average_score: null, best_score: null })
const trend = ref(normalizeTrend(null))
const trendLoading = ref(true)
const trendError = ref('')
const chartRef = ref(null)
let chart = null

const level = computed(() => levelView(levelRules.value, stats.value.average_score))
const recentViews = computed(() => props.records.slice(0, 5).map(recordView))
const statValue = value => (value === null || value === undefined ? '—' : value)
const percentValue = value => statPercent(value, stats.value.total_exams)
function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function loadStats() {
  statsError.value = ''
  if (!levelRules.value.length) {
    try {
      levelRules.value = await examsApi.levelRules()
      levelError.value = ''
    } catch {
      levelRules.value = []
      levelError.value = '等级规则暂时未能读取；这里不会用默认等级代替后台规则。'
    }
  }
  try {
    const data = await examsApi.statistics()
    stats.value = {
      total_exams: data?.total_exams ?? null,
      passed_exams: data?.passed_exams ?? null,
      average_score: typeof data?.average_score === 'number' ? data.average_score : null,
      best_score: typeof data?.best_score === 'number' ? data.best_score : null,
    }
    statsReady.value = true
    statsError.value = ''
  } catch {
    statsReady.value = false
    statsError.value = '测评统计暂时未能读取，数据不会记作零分。'
  }
  await nextTick()
  drawChart()
}

async function loadTrend() {
  trendLoading.value = true
  trendError.value = ''
  try {
    trend.value = normalizeTrend(await examsApi.scoreTrend())
    await nextTick()
    drawChart()
  } catch {
    trend.value = normalizeTrend(null)
    trendError.value = '成绩趋势暂时未能读取，请重试。'
  } finally {
    trendLoading.value = false
  }
}

function drawChart() {
  if (!chartRef.value || !trend.value.dates.length) {
    chart?.dispose()
    chart = null
    return
  }
  if (!chart) chart = echarts.init(chartRef.value)
  const styles = getComputedStyle(document.documentElement)
  chart.setOption(scoreTrendOption(trend.value, name => styles.getPropertyValue(name)), true)
}
const resize = () => chart?.resize()

onMounted(async () => {
  window.addEventListener('resize', resize)
  await Promise.all([loadStats(), loadTrend()])
  overviewLoading.value = false
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
defineExpose({ loadStats, loadTrend, level, trend, stats })
</script>
<style scoped>
.exam-overview { display: grid; gap: var(--space-2); }
.overview-heading { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.overview-heading h2 { margin: 0; font-size: var(--text-section); line-height: var(--leading-tight); }
.overview-eyebrow { margin: 0 0 2px; color: var(--ink-secondary); font-size: var(--text-caption); }
.overview-note { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.overview-state { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); }
.growth-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--space-2); }
.level-card, .stats-card, .trend-card, .recent-card { min-width: 0; padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); }
.card-title { margin: 0 0 var(--space-1); font-size: var(--text-card); }
.card-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.card-note.is-error { color: var(--negative); }
.text-action { margin-left: var(--space-1); padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; cursor: pointer; }
.level-body { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--space-2); align-items: center; }
.level-grade { display: grid; place-items: center; width: var(--space-8); height: var(--space-8); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink); font-size: var(--text-page); font-weight: var(--weight-strong); }
.level-info { min-width: 0; }
.level-title { margin: 0; font-size: var(--text-card); font-weight: var(--weight-strong); }
.level-desc, .level-next { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.level-progress { position: relative; height: var(--space-1); margin-top: var(--space-1); overflow: hidden; border-radius: var(--radius-pill); background: var(--surface-muted); }
.level-progress-fill { display: block; height: 100%; background: var(--action); transition: width var(--motion-normal); }
.stats-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-1); margin: 0; }
.stats-grid dt { color: var(--ink-secondary); font-size: var(--text-caption); }
.stats-grid dd { margin: 0; font-size: var(--text-section); font-weight: var(--weight-strong); overflow-wrap: anywhere; }
.trend-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.chart-wrap { position: relative; }
.trend-chart { width: 100%; height: var(--chart-height); }
.chart-wrap .card-note { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; }
.trend-table { margin-top: var(--space-1); }
.trend-table summary { min-height: var(--control-height); padding: var(--space-1) 0; cursor: pointer; }
.table-scroll { overflow-x: auto; }
.trend-table table { width: 100%; border-collapse: collapse; font-size: var(--text-caption); text-align: left; }
.trend-table caption { padding: var(--space-1) 0; color: var(--ink-secondary); text-align: left; }
.trend-table th, .trend-table td { padding: var(--space-1); border-bottom: var(--stroke) solid var(--line); }
.view-all { color: var(--action); font-size: var(--text-caption); }
.recent-list { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.recent-item { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); padding: var(--space-1) 0; border-top: var(--stroke) solid var(--line); color: var(--ink); text-decoration: none; }
.recent-list li:first-child .recent-item { border-top: 0; }
.recent-main { display: grid; gap: 2px; min-width: 0; }
.recent-type { justify-self: start; padding: 0 var(--space-1); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.recent-title { font-weight: var(--weight-medium); overflow-wrap: anywhere; }
.recent-date { color: var(--ink-secondary); font-size: var(--text-caption); }
.recent-side { display: grid; justify-items: end; flex: none; }
.recent-score { font-size: var(--text-card); font-weight: var(--weight-strong); }
.recent-score.passed { color: var(--positive); }
.recent-score.failed { color: var(--negative); }
.recent-status { color: var(--ink-secondary); font-size: var(--text-caption); }
.recent-item:focus-visible, .text-action:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.is-compact .growth-grid { grid-template-columns: minmax(0, 1fr); }
.is-compact .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
@media (prefers-reduced-motion: reduce) { .level-progress-fill { transition: none; } }
</style>
