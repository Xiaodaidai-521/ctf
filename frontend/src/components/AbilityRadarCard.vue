<template>
  <section class="ability-radar-card">
    <div class="radar-head">
      <div><h3>能力成长折线对比</h3></div>
      <span class="radar-note">{{ sourceNote }}</span>
    </div>
    <div class="radar-content">
      <div v-if="hasAnyScore" ref="chartEl" class="radar-chart"></div>
      <p v-else class="radar-empty">暂无可比较的方向评分；完成画像自评或积累学习证据后再看优势与短板。</p>
      <aside class="radar-insights">
        <div class="insight-item"><span>优势方向</span><strong>{{ strongest.name }}</strong><small>{{ scoreText(strongest.score) }}</small></div>
        <div class="insight-item"><span>待加强</span><strong>{{ weakest.name }}</strong><small>{{ scoreText(weakest.score) }}</small></div>
        <div class="insight-item"><span>提升最大</span><strong>{{ improved.name }}</strong><small>{{ improved.text }}</small></div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { tokenValue, tokenNumber } from '@/shared/design/chartTokens'
import { abilityModel } from './abilityRadarModel.js'

const props = defineProps({
  initialScores: { type: Object, default: () => ({}) },
  dynamicScores: { type: Object, default: () => ({}) },
  eligibleForAi: { type: Boolean, default: false },
})

const model = computed(() => abilityModel({
  initialScores: props.initialScores,
  dynamicScores: props.dynamicScores,
  eligibleForAi: props.eligibleForAi,
}))
const chartEl = ref(null)
let chart = null
const labels = model.value.labels
const initial = computed(() => model.value.initial)
const dynamic = computed(() => model.value.dynamic)
const hasInitial = computed(() => model.value.hasInitial)
const hasDynamic = computed(() => model.value.hasDynamic)
const hasAnyScore = computed(() => model.value.hasAnyScore)
const strongest = computed(() => model.value.strongest)
const weakest = computed(() => model.value.weakest)
const improved = computed(() => model.value.improved)
const sourceNote = computed(() => {
  if (hasInitial.value && hasDynamic.value) return '初始问答与真实学习数据形成的成长对比'
  if (hasInitial.value) return '初始画像已生成，等待有效学习数据形成成长对比'
  if (hasDynamic.value) return '仅有真实学习数据，初始基线尚未生成'
  return '完成初始画像问答后将显示能力基线'
})
const scoreText = (value) => (value === null || value === undefined ? '待积累' : `${value} 分`)
const render = () => {
  if (!chartEl.value || !hasAnyScore.value) {
    chart?.dispose()
    chart = null
    return
  }
  if (!chart) chart = echarts.init(chartEl.value)
  const series = []
  if (hasInitial.value) {
    series.push({ name: '初始画像', type: 'line', data: initial.value, smooth: 0.25, symbol: 'circle', symbolSize: 7, connectNulls: false, lineStyle: { color: tokenValue('series-2'), width: 3 }, itemStyle: { color: tokenValue('series-2'), borderColor: tokenValue('surface'), borderWidth: 2 } })
  }
  if (hasDynamic.value) {
    series.push({ name: '动态成长画像', type: 'line', data: dynamic.value, smooth: 0.25, symbol: 'circle', symbolSize: 7, connectNulls: false, lineStyle: { color: tokenValue('series-1'), width: 3 }, itemStyle: { color: tokenValue('series-1'), borderColor: tokenValue('surface'), borderWidth: 2 } })
  }
  chart.setOption({
    textStyle: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption'), fontFamily: tokenValue('font-family') },
    color: [tokenValue('series-2'), tokenValue('series-1')],
    grid: { top: 52, right: 22, bottom: 38, left: 48, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'line' }, valueFormatter: (value) => (value === null || value === undefined ? '待积累' : String(value) + ' 分') },
    legend: { top: 0, right: 4, icon: 'roundRect', itemWidth: 16, itemHeight: 9, textStyle: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption') }, data: series.map((item) => item.name) },
    xAxis: { type: 'category', boundaryGap: false, data: labels, axisLine: { lineStyle: { color: tokenValue('line') } }, axisTick: { show: false }, axisLabel: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption') } },
    yAxis: { type: 'value', min: 0, max: 100, interval: 20, name: '能力得分', nameTextStyle: { color: tokenValue('ink-muted'), fontSize: tokenNumber('text-caption') }, axisLabel: { color: tokenValue('ink-muted'), formatter: '{value}' }, splitLine: { lineStyle: { color: tokenValue('line'), type: 'dashed' } } },
    series,
  }, true)
}
const resizeChart = () => chart?.resize()
watch(model, async () => { await nextTick(); render() })
onMounted(async () => { await nextTick(); render(); window.addEventListener('resize', resizeChart) })
onUnmounted(() => { window.removeEventListener('resize', resizeChart); chart?.dispose() })
</script>

<style scoped>
.ability-radar-card { border:var(--stroke) solid var(--line); border-radius:var(--radius-control); background:var(--surface); padding:var(--space-2); box-shadow: var(--shadow-raised); }
.radar-head { display:flex; justify-content:space-between; gap:var(--space-2); align-items:flex-start; margin-bottom:var(--space-2); }.section-kicker { margin:0 0 calc(var(--space-1) / 2); color:var(--action); font-size:var(--text-caption); font-weight: var(--weight-strong); }.radar-head h3 { margin:0; color:var(--action); font-size:var(--text-card); }.radar-note { max-width:var(--panel-width); color:var(--ink-secondary); font-size:var(--text-caption); line-height:1.6; text-align:right; }
.radar-content { display:grid; grid-template-columns:minmax(0,1fr) var(--row-value-width); gap:var(--space-2); align-items:center; }.radar-chart { width:100%; height:var(--chart-height); min-width:0; }.radar-empty { margin:0; padding:var(--space-2); border-radius:var(--radius-control); background:var(--surface-muted); color:var(--ink-secondary); font-size:var(--text-caption); }.radar-insights { display:grid; gap:var(--space-1); }.insight-item { border:var(--stroke) solid var(--line); border-radius:var(--radius-control); padding:var(--space-1); background:var(--surface); }.insight-item span,.insight-item small { display:block; color:var(--ink-secondary); font-size:var(--text-caption); }.insight-item strong { display:block; margin:calc(var(--space-1) / 2) 0; color:var(--action); font-size:var(--text-body); }
@media (max-width: 768px) { .radar-head { display:block; }.radar-note { max-width:none; margin-top:var(--space-1); text-align:left; }.radar-content { grid-template-columns:1fr; }.radar-chart { height:var(--chart-height); }.radar-insights { grid-template-columns:repeat(3,minmax(0,1fr)); } }
@media (max-width: 768px) { .ability-radar-card { padding:var(--space-2); }.radar-chart { height:var(--chart-height); }.radar-insights { grid-template-columns:1fr; } }
</style>
