<template>
  <LegalWorkspace
    title="违规记录"
    subtitle="跟踪疑似或确认违规事项、严重级别、处置状态与整改计划。"
    table-title="违规事项"
    aside-title="快速记录"
    :metrics="metrics"
    :columns="columns"
    :rows="records"
    :loading="loading"
    :actions="[{ key: 'create', label: '新增记录', primary: true }]"
    @refresh="loadData"
    @action="createRecord"
  >
    <template #aside>
      <div class="quick-form">
        <input v-model="form.title" class="form-input" placeholder="违规标题" />
        <select v-model="form.severity" class="form-input">
          <option value="low">低</option>
          <option value="medium">中</option>
          <option value="high">高</option>
          <option value="critical">严重</option>
        </select>
        <textarea v-model="form.description" class="form-textarea" rows="5" placeholder="事实描述"></textarea>
      </div>
    </template>
  </LegalWorkspace>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/api'
import LegalWorkspace from './LegalWorkspace.vue'

const loading = ref(false)
const records = ref([])
const form = ref({ title: '', description: '', severity: 'medium' })

const columns = [
  { key: 'title', label: '标题' },
  { key: 'severity', label: '等级', badge: true },
  { key: 'status', label: '状态', badge: true },
  { key: 'created_at', label: '创建时间', formatter: formatDate },
]

const metrics = computed(() => [
  { label: '记录数', value: records.value.length, hint: '当前页' },
  { label: '未关闭', value: records.value.filter((item) => item.status !== 'closed').length, hint: 'open' },
  { label: '高风险', value: records.value.filter((item) => ['high', 'critical'].includes(item.severity)).length, hint: 'high+' },
])

async function loadData() {
  loading.value = true
  try {
    records.value = normalizeList(await api.legal.violations({ page_size: 30 }))
  } finally {
    loading.value = false
  }
}

async function createRecord() {
  if (!form.value.title || !form.value.description) return
  await api.legal.createViolation(form.value)
  form.value = { title: '', description: '', severity: 'medium' }
  await loadData()
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
