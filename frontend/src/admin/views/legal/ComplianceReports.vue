<template>
  <LegalWorkspace
    title="合规报告"
    subtitle="创建分析任务、运行数智合规官编排，并管理报告生成与导出状态。"
    table-title="报告列表"
    aside-title="新建分析任务"
    :metrics="metrics"
    :columns="columns"
    :rows="reports"
    :loading="loading"
    :row-actions="[{ key: 'export', label: '导出', disabled: (row) => row.status === 'exported' }]"
    :actions="[{ key: 'createTask', label: '创建并运行', primary: true }]"
    @refresh="loadData"
    @action="createAndRun"
    @row-action="handleRowAction"
  >
    <template #aside>
      <div class="quick-form">
        <input v-model="taskForm.title" class="form-input" placeholder="分析任务标题" />
        <select v-model="taskForm.source_type" class="form-input">
          <option value="manual">手工输入</option>
          <option value="challenge">题目</option>
          <option value="article">文章</option>
          <option value="resource">资源</option>
          <option value="data_processing">数据处理活动</option>
          <option value="protocol">协议</option>
        </select>
        <textarea v-model="taskForm.input_text" class="form-textarea" rows="7" placeholder="待分析内容"></textarea>
      </div>
    </template>
  </LegalWorkspace>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/api'
import LegalWorkspace from './LegalWorkspace.vue'

const loading = ref(false)
const reports = ref([])
const taskForm = ref({ title: '', source_type: 'manual', input_text: '' })

const columns = [
  { key: 'title', label: '报告' },
  { key: 'report_type', label: '类型' },
  { key: 'status', label: '状态', badge: true },
  { key: 'summary', label: '摘要', formatter: (value) => value ? String(value).slice(0, 48) : '-' },
  { key: 'generated_at', label: '生成时间', formatter: formatDate },
]

const metrics = computed(() => [
  { label: '报告数', value: reports.value.length, hint: '当前页' },
  { label: '草稿', value: reports.value.filter((item) => item.status === 'draft').length, hint: 'draft' },
  { label: '已导出', value: reports.value.filter((item) => item.status === 'exported').length, hint: 'exported' },
])

async function loadData() {
  loading.value = true
  try {
    reports.value = normalizeList(await api.legal.reports({ page_size: 30 }))
  } finally {
    loading.value = false
  }
}

async function createAndRun() {
  if (!taskForm.value.title || !taskForm.value.input_text) return
  const task = await api.legal.createAnalysisTask(taskForm.value)
  await api.legal.runAnalysis(task.id)
  taskForm.value = { title: '', source_type: 'manual', input_text: '' }
  await loadData()
}

async function handleRowAction(key, row) {
  if (key === 'export') {
    await api.legal.exportReport(row.id)
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
</script>

<style scoped>
.quick-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
