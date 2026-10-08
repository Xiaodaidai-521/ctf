<template>
  <LegalWorkspace
    title="协议签署"
    subtitle="查看协议版本、用户同意记录和签署证据链。"
    table-title="用户同意记录"
    aside-title="协议版本"
    :metrics="metrics"
    :columns="columns"
    :rows="consents"
    :loading="loading"
    :actions="[{ key: 'refresh', label: '同步协议', primary: true }]"
    @refresh="loadData"
    @action="loadData"
  >
    <template #aside>
      <div class="version-list">
        <div v-for="version in versions" :key="version.id" class="version-row">
          <strong>{{ version.title }}</strong>
          <span>{{ version.protocol_key }} v{{ version.version }}</span>
          <small>{{ version.is_published ? '已发布' : '草稿' }}</small>
        </div>
      </div>
    </template>
  </LegalWorkspace>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/api'
import LegalWorkspace from './LegalWorkspace.vue'

const loading = ref(false)
const consents = ref([])
const versions = ref([])

const columns = [
  { key: 'user', label: '用户ID' },
  { key: 'protocol_name', label: '协议' },
  { key: 'version', label: '版本' },
  { key: 'consent_method', label: '方式', badge: true },
  { key: 'signed_at', label: '签署时间', formatter: formatDate },
]

const metrics = computed(() => [
  { label: '签署记录', value: consents.value.length, hint: '当前页' },
  { label: '协议版本', value: versions.value.length, hint: '当前页' },
  { label: '已发布', value: versions.value.filter((item) => item.is_published).length, hint: 'published' },
])

async function loadData() {
  loading.value = true
  try {
    const [consentRes, versionRes] = await Promise.all([
      api.legal.consents({ page_size: 30 }),
      api.legal.protocolVersions({ page_size: 30 }),
    ])
    consents.value = normalizeList(consentRes)
    versions.value = normalizeList(versionRes)
  } finally {
    loading.value = false
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
.version-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.version-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e2e8f0;
}
</style>
