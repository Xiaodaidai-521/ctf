<template>
  <section class="learning-activity" aria-labelledby="activity-heading">
    <header class="section-head">
      <div>
        <h2 id="activity-heading">学习活动</h2>
        <p class="section-note">按已记录的学习活动查看趋势；暂无记录的日期不补曲线、热度或累计天数。</p>
      </div>
      <div class="window-switch" role="group" aria-label="学习活动窗口">
        <button v-for="days in windows" :key="days" type="button" :class="{ active: days === currentDays }" :aria-pressed="days === currentDays" @click="selectWindow(days)">
          近 {{ days }} 天
        </button>
      </div>
    </header>

    <p v-if="loading" class="state-note" role="status">正在读取近 {{ currentDays }} 天学习活动…</p>
    <p v-else-if="error" class="state-note is-error" role="alert">{{ error }}<button type="button" class="text-action" @click="load(currentDays)">重试</button></p>
    <p v-else-if="!effect" class="state-note">学习活动暂未读取；不会以参考数据补齐。</p>

    <template v-else>
      <ActivityFacts :effect="effect" :show-table="false" />

      <div class="chart-wrap">
        <div v-if="effect.hasDaily" ref="chartRef" class="activity-chart" role="img" aria-label="每日学习分钟趋势图"></div>
        <p v-else class="state-note">{{ emptyNote }}</p>
      </div>

      <ActivityFacts :effect="effect" :show-facts="false" />

      <div v-if="effect.recommendations.length" class="effect-advice">
        <h3 class="panel-title">活动建议</h3>
        <ul>
          <li v-for="(item, index) in effect.recommendations" :key="index">
            <strong>{{ item.action_text || item.title || '学习建议' }}</strong>
            <span v-if="item.reason">{{ item.reason }}</span>
            <RecordView v-if="item.evidence" :value="item.evidence" title="活动建议依据" />
          </li>
        </ul>
      </div>
    </template>

    <details class="reference-block">
      <summary>{{ REFERENCE_LABEL }}：半年热图与 14 天方向趋势</summary>
      <p class="reference-note">以下为参考样例，可查看提示、图例和建议；不计入本人的学习汇总，也不作为优势、短板或推荐的依据。完整学习历史暂未提供。</p>
      <div class="reference-grid">
        <div class="reference-card">
          <h3>近 6 个月学习热度</h3>
          <div ref="heatmapRef" class="reference-chart" role="img" aria-label="参考学习热力图"></div>
          <div class="legend-row" aria-label="热度图例">
            <span>少</span><i class="legend low"></i><i class="legend mid"></i><i class="legend high"></i><span>多</span>
          </div>
        </div>
        <div class="reference-card">
          <h3>近 14 天方向趋势</h3>
          <div ref="trendRef" class="reference-chart" role="img" aria-label="参考方向趋势图"></div>
          <ul class="reference-advice">
            <li><strong>先补基础</strong><span>选择能力图中证据不足的方向做基础练习。</span></li>
            <li><strong>保持节奏</strong><span>固定每日短时练习，比偶尔冲刺更稳定。</span></li>
            <li><strong>做一次复盘</strong><span>把错题按知识点归类，优先处理重复出错的概念。</span></li>
          </ul>
        </div>
      </div>
    </details>
  </section>
</template>
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { tokenValue, tokenNumber } from '@/shared/design/chartTokens'
import api from '@/api'
import { ACTIVITY_WINDOWS, REFERENCE_LABEL, normalizeEffect } from '../presentation.js'
import ActivityFacts from '@/shared/learning/ActivityFacts.vue'
import RecordView from '@/shared/forms/RecordView.vue'

const props = defineProps({
  initialDays: { type: Number, default: 7 },
})
const emit = defineEmits(['window-change'])
const windows = ACTIVITY_WINDOWS
const allowedDays = value => (ACTIVITY_WINDOWS.includes(Number(value)) ? Number(value) : 7)
const currentDays = ref(allowedDays(props.initialDays))
const effect = ref(null)
const loading = ref(true)
const error = ref('')
const chartRef = ref(null)
const heatmapRef = ref(null)
const trendRef = ref(null)
let chart = null
let heatmap = null
let trend = null
let requestVersion = 0

// 后台缺快照时返回英文工程说明；界面只用自己的中文状态，不把后端原文抛给学生。
const emptyNote = computed(() => (effect.value?.hasSnapshot
  ? '本期快照没有可绘制的按日数据；不补曲线或参考数据。'
  : '这一时间窗还没有可绘制的学习日数据，暂不显示曲线、热度或累计天数。'))

const formatDateTime = value => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function load(days) {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const payload = await api.analytics.learningEffectSummary(undefined, days)
    if (version !== requestVersion || days !== currentDays.value) return
    effect.value = normalizeEffect(payload, days)
    await nextTick()
    drawChart()
  } catch {
    if (version !== requestVersion) return
    effect.value = null
    error.value = `近 ${days} 天学习活动暂时未能读取，请重试。`
    chart?.dispose()
    chart = null
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

function selectWindow(days) {
  if (!windows.includes(days)) return
  currentDays.value = days
  emit('window-change', days)
  load(days)
}

// 外部（兼容链接或浏览历史）切换窗口时同步，不重复请求同一窗口。
watch(() => props.initialDays, value => {
  const days = allowedDays(value)
  if (days !== currentDays.value) selectWindow(days)
})

function drawChart() {
  if (!chartRef.value || !effect.value?.hasDaily) {
    chart?.dispose()
    chart = null
    return
  }
  if (!chart) chart = echarts.init(chartRef.value)
  const dates = effect.value.dailyStats.map(item => item.date.slice(5))
  const minutes = effect.value.dailyStats.map(item => item.minutes)
  chart.setOption({
    textStyle: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption'), fontFamily: tokenValue('font-family') },
    color: [tokenValue('series-1')],
    tooltip: { trigger: 'axis', valueFormatter: value => `${value ?? '—'} 分钟` },
    grid: { left: 44, right: 18, top: 24, bottom: 36, containLabel: true },
    xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: tokenValue('line') } }, axisTick: { show: false }, axisLabel: { color: tokenValue('ink-muted') } },
    yAxis: { type: 'value', name: '分钟', nameTextStyle: { color: tokenValue('ink-muted') }, axisLabel: { color: tokenValue('ink-muted') }, splitLine: { lineStyle: { color: tokenValue('line') } } },
    series: [{ name: '学习分钟', type: 'bar', data: minutes, barMaxWidth: 24, itemStyle: { color: tokenValue('series-1'), borderRadius: [2, 2, 0, 0] } }],
  }, true)
}

const referenceActivity = Array.from({ length: 183 }, (_, index) => {
  const date = new Date(Date.now() - (182 - index) * 86400000)
  const seasonal = Math.abs(Math.sin(index * 0.21)) * 78
  const weekly = index % 7 === 0 ? 0 : 18
  const burst = index % 17 === 0 ? 46 : 0
  return [date.toISOString().slice(0, 10), Math.min(Math.round(weekly + seasonal + burst + (index % 5) * 10), 180)]
})

function drawReference() {
  if (heatmapRef.value) {
    if (!heatmap) heatmap = echarts.init(heatmapRef.value)
    heatmap.setOption({
      textStyle: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption'), fontFamily: tokenValue('font-family') },
      tooltip: { formatter: params => `${params.value[0]}<br/>参考学习 ${params.value[1]} 分钟（不计入本人学情）` },
      visualMap: {
        min: 0, max: 180, type: 'piecewise', orient: 'horizontal', left: 'center', bottom: 4, itemWidth: 16, itemHeight: 10,
        textStyle: { color: tokenValue('ink-muted') },
        pieces: [
          { min: 120, label: '高', color: tokenValue('sequence-high') },
          { min: 60, max: 119, label: '中', color: tokenValue('sequence-mid') },
          { min: 1, max: 59, label: '低', color: tokenValue('sequence-low') },
          { value: 0, label: '无', color: tokenValue('surface-muted') },
        ],
      },
      calendar: {
        top: 36, left: 52, right: 16, bottom: 62, range: [referenceActivity[0][0], referenceActivity[182][0]], cellSize: ['auto', 18],
        splitLine: { lineStyle: { color: tokenValue('line'), width: 1 } }, itemStyle: { borderWidth: 1, borderColor: tokenValue('surface') },
        yearLabel: { show: true, color: tokenValue('ink-muted') }, monthLabel: { color: tokenValue('ink-muted') }, dayLabel: { color: tokenValue('ink-muted') },
      },
      series: [{ type: 'heatmap', coordinateSystem: 'calendar', data: referenceActivity }],
    })
  }
  if (trendRef.value) {
    if (!trend) trend = echarts.init(trendRef.value)
    const dates = Array.from({ length: 14 }, (_, index) => new Date(Date.now() - (13 - index) * 86400000).toISOString().slice(5, 10))
    trend.setOption({
      textStyle: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption'), fontFamily: tokenValue('font-family') },
      color: [tokenValue('series-1'), tokenValue('series-2'), tokenValue('series-3')],
      tooltip: { trigger: 'axis', valueFormatter: value => `${value} 分（参考）` },
      grid: { left: 34, right: 12, top: 32, bottom: 44, containLabel: true },
      legend: { bottom: 0, icon: 'roundRect', itemWidth: 14, itemHeight: 8, textStyle: { color: tokenValue('ink-secondary') } },
      xAxis: { type: 'category', data: dates, axisLine: { lineStyle: { color: tokenValue('line') } }, axisTick: { show: false }, axisLabel: { color: tokenValue('ink-muted') } },
      yAxis: { type: 'value', max: 100, axisLabel: { color: tokenValue('ink-muted') }, splitLine: { lineStyle: { color: tokenValue('line') } } },
      series: [
        { name: 'Web（参考）', type: 'line', data: dates.map((_, i) => 56 + Math.round(Math.sin(i / 2) * 8) + i), smooth: true, symbolSize: 5 },
        { name: 'Crypto（参考）', type: 'line', data: dates.map((_, i) => 42 + Math.round(Math.cos(i / 2) * 6) + Math.floor(i / 3)), smooth: true, symbolSize: 5, lineStyle: { type: 'dashed' } },
        { name: 'Reverse（参考）', type: 'line', data: dates.map((_, i) => 48 + Math.round(Math.sin(i / 3) * 7) + Math.floor(i / 4)), smooth: true, symbolSize: 5, lineStyle: { type: 'dotted' } },
      ],
    })
  }
}

const resize = () => { chart?.resize(); heatmap?.resize(); trend?.resize() }
onMounted(async () => {
  window.addEventListener('resize', resize)
  await load(currentDays.value)
  await nextTick()
  drawReference()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose(); heatmap?.dispose(); trend?.dispose()
  chart = null; heatmap = null; trend = null
})
defineExpose({ selectWindow, load, currentDays, effect, loading, error })
</script>
<style scoped>
.learning-activity { display: grid; gap: var(--space-2); }
.section-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.section-head h2 { margin: 0 0 var(--space-1); font-size: var(--text-section); }
.section-note { margin: 0; max-width: var(--reading-width); color: var(--ink-secondary); font-size: var(--text-caption); }
.window-switch { display: inline-flex; gap: 2px; padding: 2px; border-radius: var(--radius-control); background: var(--surface-muted); }
.window-switch button { min-height: var(--control-height); padding: 0 var(--space-2); border: 0; border-radius: var(--radius-control); background: transparent; color: var(--ink-secondary); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.window-switch button.active { background: var(--surface); color: var(--ink); box-shadow: var(--shadow-raised); }
.state-note { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); }
.state-note.is-error { background: var(--negative-soft); color: var(--negative); }
.text-action { margin-left: var(--space-1); padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; cursor: pointer; }
.period-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-1); margin: 0; }
.period-facts div { padding: var(--space-1); border-radius: var(--radius-control); background: var(--surface); }
.period-facts dt { color: var(--ink-secondary); font-size: var(--text-caption); }
.period-facts dd { margin: 2px 0 0; font-size: var(--text-caption); overflow-wrap: anywhere; }
.chart-wrap { min-height: var(--chart-height); padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); }
.activity-chart { width: 100%; height: var(--chart-height); }
.activity-table { width: 100%; border-collapse: collapse; font-size: var(--text-caption); text-align: left; }
.activity-table caption { padding: var(--space-1) 0; color: var(--ink-secondary); text-align: left; }
.activity-table th, .activity-table td { padding: var(--space-1); border-bottom: var(--stroke) solid var(--line); }
.effect-advice { padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); }
.panel-title { margin: 0 0 var(--space-1); font-size: var(--text-card); }
.effect-advice ul { display: grid; gap: var(--space-1); margin: 0; padding-left: var(--space-3); }
.effect-advice li { display: grid; gap: 2px; }
.effect-advice span, .effect-advice small { color: var(--ink-secondary); font-size: var(--text-caption); }
.reference-block { padding: var(--space-2); border: var(--stroke) dashed var(--line-strong); border-radius: var(--radius-panel); background: var(--surface-muted); }
.reference-block summary { min-height: var(--control-height); cursor: pointer; font-weight: var(--weight-strong); }
.reference-note { margin: 0 0 var(--space-2); color: var(--ink-secondary); font-size: var(--text-caption); }
.reference-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-2); }
.reference-card { min-width: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface); }
.reference-card h3 { margin: 0 0 var(--space-1); font-size: var(--text-card); }
.reference-chart { width: 100%; height: var(--chart-height); }
.legend-row { display: flex; align-items: center; gap: var(--space-1); color: var(--ink-muted); font-size: var(--text-caption); }
.legend { width: var(--space-2); height: var(--space-1); border-radius: var(--radius-control); }
.legend.low { background: var(--sequence-low); }
.legend.mid { background: var(--sequence-mid); }
.legend.high { background: var(--sequence-high); }
.reference-advice { display: grid; gap: var(--space-1); margin: var(--space-2) 0 0; padding-left: var(--space-3); }
.reference-advice li { display: grid; gap: 2px; }
.reference-advice span { color: var(--ink-secondary); font-size: var(--text-caption); }
.is-compact .period-facts, .is-compact .reference-grid { grid-template-columns: minmax(0, 1fr); }
.window-switch button:focus-visible, .reference-block summary:focus-visible, .text-action:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
