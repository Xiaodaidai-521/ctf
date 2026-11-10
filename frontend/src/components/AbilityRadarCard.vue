<template>
  <section class="ability-radar-card">
    <div class="radar-head">
      <div><p class="section-kicker">ABILITY PROGRESS</p><h3>能力成长折线对比</h3></div>
      <span class="radar-note">{{ sourceNote }}</span>
    </div>
    <div class="radar-content">
      <div ref="chartEl" class="radar-chart"></div>
      <aside class="radar-insights">
        <div class="insight-item"><span>优势方向</span><strong>{{ strongest.name }}</strong><small>{{ strongest.score }} 分</small></div>
        <div class="insight-item"><span>待加强</span><strong>{{ weakest.name }}</strong><small>{{ weakest.score }} 分</small></div>
        <div class="insight-item"><span>提升最大</span><strong>{{ improved.name }}</strong><small>{{ improved.text }}</small></div>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  initialScores: { type: Object, default: () => ({}) },
  dynamicScores: { type: Object, default: () => ({}) },
  eligibleForAi: { type: Boolean, default: false },
})

const directions = [
  { key: 'web', label: 'Web' }, { key: 'crypto', label: 'Crypto' },
  { key: 'pwn', label: 'Pwn' }, { key: 'reverse', label: 'Reverse' },
  { key: 'forensics', label: 'Forensics' }, { key: 'misc', label: 'Misc' },
]
const chartEl = ref(null)
let chart = null
const clamp = (value) => Math.max(0, Math.min(100, Number(value) || 0))
const scoreFor = (scores, key) => clamp(scores?.[key])
const hasInitial = computed(() => Object.keys(props.initialScores).length > 0)
const hasDynamic = computed(() => props.eligibleForAi && Object.keys(props.dynamicScores).length > 0)
const labels = directions.map((item) => item.label)
const initial = computed(() => directions.map((item) => scoreFor(props.initialScores, item.key)))
const current = computed(() => directions.map((item) => hasDynamic.value ? scoreFor(props.dynamicScores, item.key) : scoreFor(props.initialScores, item.key)))
const sourceNote = computed(() => {
  if (hasInitial.value && hasDynamic.value) return '初始问答与真实学习数据形成的成长对比'
  if (hasInitial.value) return '初始画像已生成，等待有效学习数据形成成长对比'
  return '完成初始画像问答后将显示能力基线'
})
const indexOfMax = (values) => values.indexOf(Math.max(...values, 0))
const indexOfMin = (values) => values.indexOf(Math.min(...values, 0))
const strongest = computed(() => {
  if (!hasInitial.value) return { name: '-', score: 0 }
  const index = indexOfMax(current.value)
  return { name: labels[index] || '-', score: current.value[index] || 0 }
})
const weakest = computed(() => {
  if (!hasInitial.value) return { name: '-', score: 0 }
  const index = indexOfMin(current.value)
  return { name: labels[index] || '-', score: current.value[index] || 0 }
})
const improved = computed(() => {
  if (!hasDynamic.value) return { name: '-', text: '待积累' }
  const deltas = current.value.map((score, index) => score - initial.value[index])
  const index = indexOfMax(deltas)
  const delta = deltas[index] || 0
  return { name: labels[index] || '-', text: (delta >= 0 ? '+' : '') + delta + ' 分' }
})
const render = () => {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  chart.setOption({
    color: ['#b8332b', '#4f7d59'],
    grid: { top: 52, right: 22, bottom: 38, left: 48, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'line' }, valueFormatter: (value) => String(value) + ' 分' },
    legend: { top: 0, right: 4, icon: 'roundRect', itemWidth: 16, itemHeight: 9, textStyle: { color: '#5d6677', fontSize: 11 }, data: ['初始画像', '动态成长画像'] },
    xAxis: { type: 'category', boundaryGap: false, data: labels, axisLine: { lineStyle: { color: '#d8d2c8' } }, axisTick: { show: false }, axisLabel: { color: '#4f5663', fontSize: 11 } },
    yAxis: { type: 'value', min: 0, max: 100, interval: 20, name: '能力得分', nameTextStyle: { color: '#6b7280', fontSize: 11 }, axisLabel: { color: '#6b7280', formatter: '{value}' }, splitLine: { lineStyle: { color: '#ebe7df', type: 'dashed' } } },
    series: [
      { name: '初始画像', type: 'line', data: initial.value, smooth: 0.25, symbol: 'circle', symbolSize: 7, lineStyle: { color: '#b8332b', width: 3 }, itemStyle: { color: '#b8332b', borderColor: '#fff', borderWidth: 2 } },
      { name: '动态成长画像', type: 'line', data: current.value, smooth: 0.25, symbol: 'circle', symbolSize: 7, lineStyle: { color: '#4f7d59', width: 3 }, itemStyle: { color: '#4f7d59', borderColor: '#fff', borderWidth: 2 } },
    ],
  })
}
const resizeChart = () => chart?.resize()
watch([initial, current], async () => { await nextTick(); render() })
onMounted(async () => { await nextTick(); render(); window.addEventListener('resize', resizeChart) })
onUnmounted(() => { window.removeEventListener('resize', resizeChart); chart?.dispose() })
</script>

<style scoped>
.ability-radar-card { border: 1px solid rgba(226,232,240,.95); border-radius: 8px; background: #fff; padding: 20px; box-shadow: 0 10px 28px rgba(15,23,42,.06); }
.radar-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:14px; }.section-kicker { margin:0 0 6px; color:#5b7cfa; font-size:12px; font-weight:800; }.radar-head h3 { margin:0; color:#1f2937; font-size:18px; }.radar-note { max-width:360px; color:#6b7280; font-size:12px; line-height:1.6; text-align:right; }
.radar-content { display:grid; grid-template-columns:minmax(0,1fr) 180px; gap:18px; align-items:center; }.radar-chart { width:100%; height:320px; min-width:0; }.radar-insights { display:grid; gap:10px; }.insight-item { border:1px solid #e6eaf2; border-radius:8px; padding:12px; background:#f8faff; }.insight-item span,.insight-item small { display:block; color:#6b7280; font-size:12px; }.insight-item strong { display:block; margin:5px 0; color:#111827; font-size:16px; }
@media (max-width:900px) { .radar-head { display:block; }.radar-note { max-width:none; margin-top:8px; text-align:left; }.radar-content { grid-template-columns:1fr; }.radar-chart { height:300px; }.radar-insights { grid-template-columns:repeat(3,minmax(0,1fr)); } }
@media (max-width:640px) { .ability-radar-card { padding:16px; }.radar-chart { height:280px; }.radar-insights { grid-template-columns:1fr; } }
</style>
