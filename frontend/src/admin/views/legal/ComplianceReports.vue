<template>
  <LegalWorkspace
    title="合规报告"
    subtitle="创建合规审查任务，查看分析结论并管理报告。"
    table-title="报告列表"
    aside-title="新建分析任务"
    :metrics="metrics"
    :columns="columns"
    :rows="reports"
    :loading="loading"
    :row-actions="[{ key: 'export', label: '脱敏导出', disabled: (row) => !row.export_available || exporting !== null }]"
    :actions="[{ key: 'createTask', label: creating ? '正在分析…' : '创建并运行', primary: true, disabled: creating }]"
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
        <ProtectionBadge :status="taskProtection?.input_text" label="已提交的分析原文加密保存" />
        <p v-if="exportError" role="alert">{{ exportError }}</p>
        <p v-if="exportNotice" role="status">{{ exportNotice }}</p>
      </div>
    </template>
  </LegalWorkspace>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import api from '@/api'
import { captureAccount, onAccountClear } from '@/shared/state/accountScope.js'
import LegalWorkspace from './LegalWorkspace.vue'
import ProtectionBadge from '@/shared/privacy/ProtectionBadge.vue'

const loading = ref(false)
const reports = ref([])
const taskProtection = ref(null)
const taskForm = ref({ title: '', source_type: 'manual', input_text: '' })
const creating = ref(false), exporting = ref(null), exportError = ref(''), exportNotice = ref('')
let alive = true, loadGeneration = 0
const clearAccount = onAccountClear(() => {
  loadGeneration++
  reports.value = []; taskProtection.value = null; taskForm.value = { title: '', source_type: 'manual', input_text: '' }
  loading.value = false; creating.value = false; exporting.value = null; exportError.value = ''; exportNotice.value = ''
})

const columns = [
  { key: 'title', label: '报告' },
  { key: 'report_type', label: '类型', labelKey: 'reportType' },
  { key: 'status', label: '状态', labelKey: 'taskStatus', badge: true },
  { key: 'summary', label: '摘要', formatter: (value) => value ? String(value).slice(0, 48) : '-' },
  { key: 'generated_at', label: '生成时间', formatter: formatDate },
]

const metrics = computed(() => [
  { label: '报告数', value: reports.value.length, hint: '当前页' },
  { label: '草稿', value: reports.value.filter((item) => item.status === 'draft').length, hint: '尚未定稿' },
  { label: '已导出', value: reports.value.filter((item) => item.status === 'exported').length, hint: '已留档' },
])

async function loadData() {
  const account = captureAccount(), generation = ++loadGeneration
  loading.value = true
  try {
    const response = await api.legal.reports({ page_size: 30 })
    if (!alive || !account.current() || generation !== loadGeneration) return
    reports.value = normalizeList(response)
  } catch {
    if (alive && account.current() && generation === loadGeneration) exportError.value = '报告列表暂时无法读取，请重试。'
  } finally {
    if (alive && account.current() && generation === loadGeneration) loading.value = false
  }
}

async function createAndRun() {
  if (creating.value || !taskForm.value.title || !taskForm.value.input_text) return
  const account = captureAccount()
  creating.value = true; taskProtection.value = null; exportError.value = ''
  try {
    const task = await api.legal.createAnalysisTask({ ...taskForm.value })
    if (!alive || !account.current()) return
    taskProtection.value = task.protection || null
    await api.legal.runAnalysis(task.id)
    if (!alive || !account.current()) return
    taskForm.value = { title: '', source_type: 'manual', input_text: '' }
    await loadData()
  } catch {
    if (alive && account.current()) exportError.value = '分析未完成，请检查任务状态后重试。'
  } finally {
    if (alive && account.current()) creating.value = false
  }
}

async function handleRowAction(key, row) {
  if (key !== 'export' || !row.export_available || exporting.value !== null) return
  const account = captureAccount()
  exporting.value = row.id; exportError.value = ''; exportNotice.value = ''
  try {
    const response = await api.legal.exportReport(row.id)
    if (!alive || !account.current()) return
    const url = URL.createObjectURL(response.data), link = document.createElement('a')
    link.href = url; link.download = `report-${row.id}.txt`
    document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    exportNotice.value = '脱敏报告已生成并开始下载。'
    await loadData()
  } catch { if (alive && account.current()) exportError.value = '报告导出失败或权限已失效，请刷新后重试。' }
  finally { if (alive && account.current()) exporting.value = null }
}

function normalizeList(response) {
  return response?.results || response || []
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '-'
}

onMounted(loadData)
onBeforeUnmount(() => { alive = false; clearAccount() })
</script>

<style scoped>
.quick-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
