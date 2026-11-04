<template>
  <div class="learning-trend">
    <div v-if="rows.length" ref="chartRef" class="chart" role="img" :aria-label="`${title}，完整数值见${showTable ? '下方' : '本分区每日学习分钟'}表格`"></div>
    <p v-else>暂无可绘制记录。</p>
    <div v-if="showTable && rows.length" class="table-scroll"><table><caption>{{ title }} · 数据表</caption><thead><tr><th scope="col">日期</th><th scope="col">{{ unit }}</th><th v-if="hasValidity" scope="col">有效性</th></tr></thead><tbody><tr v-for="(row, index) in rows" :key="index"><th scope="row">{{ row.date }}</th><td>{{ row.value === null ? '—' : row.value }}</td><td v-if="hasValidity">{{ row.validity }}</td></tr></tbody></table></div>
  </div>
</template>
<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { tokenValue, tokenNumber } from '@/shared/design/chartTokens'
const props = defineProps({ rows: { type: Array, default: () => [] }, title: String, unit: { type: String, default: '分' }, max: { type: Number, default: undefined }, showTable: { type: Boolean, default: true } })
const hasValidity = computed(() => props.rows.some(row => row.validity))
const chartRef = ref(null)
let chart = null, chartElement = null, observer = null, dead = false
function clearChart() {
  observer?.disconnect(); observer = null
  chart?.dispose(); chart = null; chartElement = null
}
async function draw() {
  await nextTick()
  if (dead) return
  if (!chartRef.value || !props.rows.length) { clearChart(); return }
  if (chartElement !== chartRef.value) {
    clearChart(); chartElement = chartRef.value; chart = echarts.init(chartElement)
    if (globalThis.ResizeObserver) { observer = new ResizeObserver(resize); observer.observe(chartElement) }
  }
  chart.setOption({
    animation: !globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
    textStyle: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption'), fontFamily: tokenValue('font-family') },
    tooltip: { trigger: 'axis', renderMode: 'richText', axisPointer: { type: 'line' }, valueFormatter: value => `${value ?? '—'} ${props.unit}` },
    grid: { left: 0, right: 0, top: 32, bottom: 0, containLabel: true },
    xAxis: { type: 'category', data: props.rows.map(row => row.date), axisLabel: { color: tokenValue('ink-muted'), hideOverlap: true }, axisTick: { show: false }, axisLine: { lineStyle: { color: tokenValue('line') } } },
    yAxis: { type: 'value', name: props.unit, min: 0, max: props.max, nameTextStyle: { color: tokenValue('ink-muted') }, axisLabel: { color: tokenValue('ink-muted') }, splitLine: { lineStyle: { color: tokenValue('line'), width: 1 } } },
    series: [{ name: props.title, type: 'line', data: props.rows.map(row => row.value), connectNulls: false, symbolSize: 8, lineStyle: { width: 2, color: tokenValue('series-1') }, itemStyle: { color: tokenValue('series-1'), borderColor: tokenValue('surface'), borderWidth: 2 } }],
  }, true)
}
const resize = () => chart?.resize()
watch(() => [props.rows, props.title, props.unit, props.max], draw, { deep: true })
onMounted(() => { draw(); window.addEventListener('resize', resize) })
onBeforeUnmount(() => { dead = true; window.removeEventListener('resize', resize); clearChart() })
</script>
<style scoped>
.chart { height: var(--chart-height); width: 100%; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: var(--text-caption); font-variant-numeric: tabular-nums; }
th, td { padding: var(--space-1); border-bottom: var(--stroke) solid var(--line); }
caption { text-align: left; color: var(--ink-secondary); padding: var(--space-1) 0; }
@media print, (forced-colors: active) { .chart { display: none; } }
</style>
