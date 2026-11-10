<template>
  <LegalWorkspace
    title="审计日志"
    subtitle="查看合规事件、AI 调用日志和哈希链校验结果。"
    table-title="审计事件"
    aside-title="哈希链"
    :metrics="metrics"
    :columns="columns"
    :rows="events"
    :loading="loading"
    :actions="[{ key: 'verify', label: '校验哈希链', primary: true }]"
    @refresh="loadData"
    @action="verifyLedger"
  >
    <template #aside>
      <div class="ledger-box">
        <strong>{{ ledgerResult?.is_valid === false ? '链路异常' : '链路有效' }}</strong>
        <span>区块数：{{ ledgerResult?.total_entries ?? '-' }}</span>
        <span>错误数：{{ ledgerResult?.errors?.length ?? 0 }}</span>
      </div>
    </template>
  </LegalWorkspace>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/api'
import LegalWorkspace from './LegalWorkspace.vue'

const loading = ref(false)
const events = ref([])
const aiLogs = ref([])
const ledger = ref([])
const ledgerResult = ref(null)

const columns = [
  { key: 'category', label: '类别', badge: true },
  { key: 'summary', label: '摘要' },
  { key: 'username', label: '用户' },
  { key: 'ip_address', label: 'IP' },
  { key: 'created_at', label: '时间', formatter: formatDate },
]

const metrics = computed(() => [
  { label: '审计事件', value: events.value.length, hint: '当前页' },
  { label: 'AI 日志', value: aiLogs.value.length, hint: '当前页' },
  { label: '链条记录', value: ledger.value.length, hint: '当前页' },
  { label: '链路状态', value: ledgerResult.value?.is_valid === false ? '异常' : '正常', hint: 'verify' },
])

async function loadData() {
  loading.value = true
  try {
    const [eventRes, aiRes, ledgerRes, verifyRes] = await Promise.all([
      api.audit.events({ page_size: 30 }),
      api.audit.aiLogs({ page_size: 10 }).catch(() => []),
      api.audit.ledger({ page_size: 30 }),
      api.audit.verifyLedger().catch(() => null),
    ])
    events.value = normalizeList(eventRes)
    aiLogs.value = normalizeList(aiRes)
    ledger.value = normalizeList(ledgerRes)
    ledgerResult.value = verifyRes
  } finally {
    loading.value = false
  }
}

async function verifyLedger() {
  ledgerResult.value = await api.audit.verifyLedger()
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
.ledger-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: #334155;
}
</style>
