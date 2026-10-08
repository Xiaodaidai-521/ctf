<template>
  <LegalWorkspace
    title="数智合规官"
    subtitle="创建分析任务，调用合规编排器、知识检索器、风险评估器和报告生成器完成证据化审查。"
    table-title="分析任务"
    aside-title="发起审查"
    :metrics="metrics"
    :columns="columns"
    :rows="tasks"
    :loading="loading || running"
    :actions="[{ key: 'refresh', label: '刷新' }]"
    :row-actions="rowActions"
    @refresh="loadData"
    @action="loadData"
    @row-action="handleRowAction"
  >
    <template #aside>
      <form class="agent-form" @submit.prevent="createAndRun">
        <label>
          <span>任务标题</span>
          <input v-model="form.title" class="form-input" type="text" required />
        </label>
        <label>
          <span>来源类型</span>
          <select v-model="form.source_type" class="form-input">
            <option value="manual">手动输入</option>
            <option value="challenge">题目演练</option>
            <option value="data_processing">数据处理活动</option>
            <option value="report">报告复核</option>
          </select>
        </label>
        <label>
          <span>待审查内容</span>
          <textarea
            v-model="form.input_text"
            class="form-textarea"
            rows="8"
            required
            placeholder="输入业务场景、数据处理流程、题目材料或待复核文本"
          ></textarea>
        </label>
        <button class="action-btn btn-primary" type="submit" :disabled="running || !form.title || !form.input_text">
          {{ running ? '分析中...' : '调用数智合规官' }}
        </button>
      </form>

      <div v-if="latestRun" class="agent-trace">
        <h4>最近运行轨迹</h4>
        <div class="trace-row">
          <span>Agent</span>
          <strong>{{ latestRun.agent_id }}</strong>
        </div>
        <div class="trace-row">
          <span>模型</span>
          <strong>{{ latestRun.provider }} / {{ latestRun.model }}</strong>
        </div>
        <div class="trace-row">
          <span>耗时</span>
          <strong>{{ latestRun.duration_ms }} ms</strong>
        </div>
        <p>{{ latestRun.output_payload?.content }}</p>
      </div>
    </template>
  </LegalWorkspace>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/api'
import LegalWorkspace from './LegalWorkspace.vue'

const loading = ref(false)
const running = ref(false)
const tasks = ref([])
const findings = ref([])
const reports = ref([])
const agentRuns = ref([])

const form = ref({
  title: '平台合规风险快速审查',
  source_type: 'manual',
  input_text: '',
})

const columns = [
  { key: 'title', label: '任务' },
  { key: 'source_type', label: '来源' },
  { key: 'status', label: '状态', badge: true },
  { key: 'result_summary', label: '结论摘要', formatter: (value) => value ? String(value).slice(0, 56) : '-' },
  { key: 'created_at', label: '创建时间', formatter: formatDate },
]

const rowActions = [
  { key: 'run', label: '重新分析', disabled: (row) => row.status === 'running' },
  { key: 'trace', label: '查看轨迹' },
]

const metrics = computed(() => [
  { label: '分析任务', value: tasks.value.length, hint: '当前任务页' },
  { label: '风险发现', value: findings.value.length, hint: '当前发现页' },
  { label: '合规报告', value: reports.value.length, hint: '自动生成报告' },
  { label: 'Agent 运行', value: agentRuns.value.length, hint: '编排器调用记录' },
])

const latestRun = computed(() => agentRuns.value[0] || null)

async function loadData() {
  loading.value = true
  try {
    const [taskRes, findingRes, reportRes, runRes] = await Promise.all([
      api.legal.analysisTasks({ page_size: 30 }),
      api.legal.findings({ page_size: 50 }),
      api.legal.reports({ page_size: 30 }),
      api.legal.agentRuns({ page_size: 10 }),
    ])
    tasks.value = normalizeList(taskRes)
    findings.value = normalizeList(findingRes)
    reports.value = normalizeList(reportRes)
    agentRuns.value = normalizeList(runRes)
  } finally {
    loading.value = false
  }
}

async function createAndRun() {
  running.value = true
  try {
    const task = await api.legal.createAnalysisTask({
      title: form.value.title,
      source_type: form.value.source_type,
      input_text: form.value.input_text,
      metadata: { entry: 'admin_compliance_agent_center' },
    })
    await api.legal.runAnalysis(task.id)
    form.value.input_text = ''
    await loadData()
  } finally {
    running.value = false
  }
}

async function handleRowAction(key, row) {
  if (key === 'run') {
    running.value = true
    try {
      await api.legal.runAnalysis(row.id)
      await loadData()
    } finally {
      running.value = false
    }
  }
  if (key === 'trace') {
    const response = await api.legal.agentRuns({ task: row.id, page_size: 1 })
    agentRuns.value = normalizeList(response)
  }
}

function normalizeList(response) {
  return response?.results || response || []
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(loadData)
</script>

<style scoped>
.agent-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.agent-form label {
  color: #334155;
  display: flex;
  flex-direction: column;
  font-size: 13px;
  font-weight: 600;
  gap: 6px;
}

.agent-trace {
  border-top: 1px solid #e2e8f0;
  margin-top: 16px;
  padding-top: 14px;
}

.agent-trace h4 {
  color: #0f172a;
  font-size: 14px;
  margin: 0 0 10px;
}

.trace-row {
  align-items: center;
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
}

.trace-row span {
  color: #64748b;
}

.trace-row strong {
  color: #0f172a;
  font-size: 13px;
}

.agent-trace p {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  color: #334155;
  line-height: 1.6;
  margin: 10px 0 0;
  max-height: 220px;
  overflow: auto;
  padding: 10px;
  white-space: pre-wrap;
}
</style>
