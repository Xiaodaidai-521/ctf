<template>
  <LegalWorkspace
    title="合规大屏"
    subtitle="汇总分析任务、风险发现、报告和审计链状态，用于日常合规值守。"
    table-title="最近分析任务"
    aside-title="风险概览"
    :metrics="metrics"
    :columns="columns"
    :rows="tasks"
    :loading="loading"
    :actions="[{ key: 'newTask', label: '新建分析任务', primary: true }]"
    :row-actions="[{ key: 'run', label: '运行分析', disabled: (row) => row.status === 'running' }]"
    @refresh="loadData"
    @action="handleAction"
    @row-action="handleRowAction"
  >
    <template #aside>
      <div ref="chartRef" class="risk-chart"></div>
      <div class="aside-list">
        <div v-for="item in riskBreakdown" :key="item.name" class="aside-row">
          <span>{{ item.name }}</span>
          <strong>{{ item.value }}</strong>
        </div>
      </div>
    </template>
  </LegalWorkspace>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import * as echarts from 'echarts'
import api from '@/api'
import LegalWorkspace from './LegalWorkspace.vue'

const loading = ref(false)
const tasks = ref([])
const findings = ref([])
const reports = ref([])
const ledgerStatus = ref(null)
const chartRef = ref(null)
let chart = null

const columns = [
  { key: 'title', label: '任务' },
  { key: 'source_type', label: '来源' },
  { key: 'status', label: '状态', badge: true },
  { key: 'result_summary', label: '摘要', formatter: (value) => value ? String(value).slice(0, 42) : '-' },
  { key: 'created_at', label: '创建时间', formatter: formatDate },
]

const riskBreakdown = computed(() => {
  const count = { critical: 0, high: 0, medium: 0, low: 0 }
  findings.value.forEach((item) => { count[item.severity] = (count[item.severity] || 0) + 1 })
  return [
    { name: '严重', value: count.critical },
    { name: '高危', value: count.high },
    { name: '中危', value: count.medium },
    { name: '低危', value: count.low },
  ]
})

const metrics = computed(() => [
  { label: '分析任务', value: tasks.value.length, hint: '当前页任务数' },
  { label: '风险发现', value: findings.value.length, hint: '当前页发现数' },
  { label: '合规报告', value: reports.value.length, hint: '当前页报告数' },
  { label: '审计链', value: ledgerStatus.value?.is_valid === false ? '异常' : '正常', hint: 'Hash chain verify' },
])

async function loadData() {
  loading.value = true
  try {
    const [taskRes, findingRes, reportRes, ledgerRes] = await Promise.all([
      api.legal.analysisTasks({ page_size: 20 }),
      api.legal.findings({ page_size: 50 }),
      api.legal.reports({ page_size: 20 }),
      api.audit.verifyLedger().catch(() => null),
    ])
    tasks.value = normalizeList(taskRes)
    findings.value = normalizeList(findingRes)
    reports.value = normalizeList(reportRes)
    ledgerStatus.value = ledgerRes
    await nextTick()
    renderChart()
  } finally {
    loading.value = false
  }
}

function renderChart() {
  if (!chartRef.value) return
  if (!chart) chart = echarts.init(chartRef.value)
  chart.setOption({
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: ['48%', '72%'],
      data: riskBreakdown.value,
      label: { formatter: '{b}: {c}' },
    }],
    color: ['#b91c1c', '#dc2626', '#f59e0b', '#10b981'],
  })
}

function handleAction(key) {
  if (key === 'newTask') window.location.href = '/admin/legal/reports'
}

async function handleRowAction(key, row) {
  if (key === 'run') {
    await api.legal.runAnalysis(row.id)
    await loadData()
  }
}

function normalizeList(response) {
  return response?.results || response || []
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(loadData)
onUnmounted(() => {
  if (chart) chart.dispose()
})
</script>

<style scoped>
.risk-chart {
  width: 100%;
  height: 240px;
}

.aside-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.aside-row {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 8px;
}
</style>
