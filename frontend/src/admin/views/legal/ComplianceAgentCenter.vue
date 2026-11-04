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
          <span>执行角色</span>
          <strong>{{ latestRun.role_label || '合规审查智能体' }}</strong>
        </div>
        <div class="trace-row">
          <span>模型</span>
          <strong>{{ modelLabel }}</strong>
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
  { key: 'source_type', label: '来源', labelKey: 'source' },
  { key: 'status', label: '状态', labelKey: 'taskStatus', badge: true },
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
  { label: '智能体运行', value: agentRuns.value.length, hint: '编排器调用记录' },
])

const latestRun = computed(() => agentRuns.value[0] || null)
const providerLabels = { local: '本地规则', openai: '云端智能体', anthropic: '云端智能体', deepseek: '云端智能体', moonshot: '云端智能体', qwen: '云端智能体' }
const modelLabel = computed(() => {
  const run = latestRun.value
  if (!run) return '未记录'
  return providerLabels[run.provider] || (run.provider ? '智能体服务' : '未记录')
})

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
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.agent-form label {
  color:var(--ink);
  display:flex;
  flex-direction:column;
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  gap:calc(var(--space-1) / 2);
}

.agent-trace {
  border-top:var(--stroke) solid var(--line);
  margin-top:var(--space-2);
  padding-top:var(--space-2);
}

.agent-trace h4 {
  color:var(--action);
  font-size:var(--text-caption);
  margin:0 0 var(--space-1);
}

.trace-row {
  align-items:center;
  display:flex;
  justify-content:space-between;
  padding:calc(var(--space-1) / 2) 0;
}

.trace-row span {
  color:var(--ink-secondary);
}

.trace-row strong {
  color:var(--action);
  font-size:var(--text-caption);
}

.agent-trace p {
  background:var(--surface);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  color:var(--ink);
  line-height:1.6;
  margin:var(--space-1) 0 0;
  max-height:var(--content-short-height);
  overflow:auto;
  padding:var(--space-1);
  white-space:pre-wrap;
}
</style>
