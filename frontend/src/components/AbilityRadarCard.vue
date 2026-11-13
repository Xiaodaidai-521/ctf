<template>
  <section class="ability-radar-card">
    <div class="radar-head">
      <div><p class="section-kicker">ABILITY PROGRESS</p><h3>能力成长折线对比</h3></div>
      <span class="radar-note">{{ sourceNote }}</span>
    </div>
    <div class="radar-content">
      <div ref="chartEl" class="radar-chart"></div>
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
import { abilityModel } from './abilityRadarModel.js'
import { tokenValue, tokenNumber } from '@/shared/design/chartTokens.js'

const props = defineProps({
  initialScores: { type: Object, default: () => ({}) },
  dynamicScores: { type: Object, default: () => ({}) },
  eligibleForAi: { type: Boolean, default: false },
})

const chartEl = ref(null)
let chart = null
const model = computed(() => abilityModel(props))
const labels = model.value.labels
const hasInitial = computed(() => model.value.hasInitial)
const hasDynamic = computed(() => model.value.hasDynamic)
const initial = computed(() => model.value.initial)
const current = computed(() => model.value.dynamic)
const scoreText = value => value === null ? '暂未评分' : `${value} 分`
const sourceNote = computed(() => {
  if (hasInitial.value && hasDynamic.value) return '初始问答与真实学习数据形成的成长对比'
  if (hasDynamic.value) return '当前有效学习数据形成的能力评分，暂无初始基线'
  if (hasInitial.value) return '初始画像已生成，等待有效学习数据形成成长对比'
  return '完成初始画像问答后将显示能力基线'
})
const strongest = computed(() => model.value.strongest)
const weakest = computed(() => model.value.weakest)
const improved = computed(() => model.value.improved)
const render = () => {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  chart.setOption({
    color: [tokenValue('series-1'), tokenValue('series-3')],
    grid: { top: 52, right: 22, bottom: 38, left: 48, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'line' }, valueFormatter: (value) => String(value) + ' 分' },
    legend: { top: 0, right: 4, icon: 'roundRect', itemWidth: 16, itemHeight: 9, textStyle: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption') }, data: ['初始画像', '动态成长画像'] },
    xAxis: { type: 'category', boundaryGap: false, data: labels, axisLine: { lineStyle: { color: tokenValue('line') } }, axisTick: { show: false }, axisLabel: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption') } },
    yAxis: { type: 'value', min: 0, max: 100, interval: 20, name: '能力得分', nameTextStyle: { color: tokenValue('ink-muted'), fontSize: tokenNumber('text-caption') }, axisLabel: { color: tokenValue('ink-muted'), formatter: '{value}' }, splitLine: { lineStyle: { color: tokenValue('line'), type: 'dashed' } } },
    series: [
      { name: '初始画像', type: 'line', data: initial.value, smooth: 0.25, symbol: 'circle', symbolSize: 7, lineStyle: { color: tokenValue('series-1'), width: 3 }, itemStyle: { color: tokenValue('series-1'), borderColor: tokenValue('surface'), borderWidth: 2 } },
      { name: '动态成长画像', type: 'line', data: hasDynamic.value ? current.value : labels.map(() => null), smooth: 0.25, symbol: 'rect', symbolSize: 7, lineStyle: { color: tokenValue('series-3'), width: 3, type: 'dashed' }, itemStyle: { color: tokenValue('series-3'), borderColor: tokenValue('surface'), borderWidth: 2 } },
    ],
  })
}
const resizeChart = () => chart?.resize()
watch([initial, current], async () => { await nextTick(); render() })
onMounted(async () => { await nextTick(); render(); window.addEventListener('resize', resizeChart) })
onUnmounted(() => { window.removeEventListener('resize', resizeChart); chart?.dispose() })
</script>

<style scoped>
.ability-radar-card { border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); padding: var(--space-3); box-shadow: var(--shadow-raised); }
.radar-head { display:flex; justify-content:space-between; gap:var(--space-2); align-items:flex-start; margin-bottom:var(--space-2); }
.section-kicker { margin:0 0 var(--space-1); color:var(--action); font-size:var(--text-caption); font-weight:var(--weight-strong); }
.radar-head h3 { margin:0; color:var(--ink); font-size:var(--text-card); }
.radar-note { max-width:var(--message-width); color:var(--ink-secondary); font-size:var(--text-caption); line-height:var(--leading-body); text-align:right; }
.radar-content { display:grid; grid-template-columns:minmax(0,1fr) var(--row-value-width); gap:var(--space-2); align-items:center; }
.radar-chart { width:100%; height:var(--chart-height); min-width:0; }
.radar-insights { display:grid; gap:var(--space-1); }
.insight-item { border:var(--stroke) solid var(--line); border-radius:var(--radius-control); padding:var(--space-2); background:var(--surface-muted); }
.insight-item span,.insight-item small { display:block; color:var(--ink-secondary); font-size:var(--text-caption); }
.insight-item strong { display:block; margin:var(--space-1) 0; color:var(--ink); font-size:var(--text-body); }
@media (max-width:900px) { .radar-head { display:block; }.radar-note { max-width:none; margin-top:var(--space-1); text-align:left; }.radar-content { grid-template-columns:1fr; }.radar-insights { grid-template-columns:repeat(3,minmax(0,1fr)); } }
@media (max-width:640px) { .ability-radar-card { padding:var(--space-2); }.radar-insights { grid-template-columns:1fr; } }
</style>
