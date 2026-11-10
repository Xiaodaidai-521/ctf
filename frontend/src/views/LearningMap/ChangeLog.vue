<template>
  <div class="changelog-page">
    <div class="page-header">
      <div>
        <span class="eyebrow">学习路径 · 变更记录</span>
        <h1>路径变更记录</h1>
        <p class="subtitle">每次能力状态变化都保留前后状态、原因和时间，不覆盖历史。</p>
      </div>
      <router-link to="/capability-map" class="btn btn-secondary">返回能力地图</router-link>
    </div>

    <div v-if="loading" class="state-box">正在读取...</div>
    <div v-else-if="error" class="state-box">{{ error }}</div>
    <div v-else-if="!items.length" class="state-box">暂无路径变更。完成核验后才会产生状态记录。</div>
    <table v-else class="log-table">
      <thead>
        <tr>
          <th>时间</th>
          <th>能力</th>
          <th>状态变化</th>
          <th>原因</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.created_at + item.capability_title + item.reason_label">
          <td>{{ formatDate(item.created_at) }}</td>
          <td>{{ item.capability_title }}</td>
          <td>{{ item.from_state_label || '—' }} → <strong>{{ item.to_state_label }}</strong></td>
          <td>{{ item.reason_label }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import service from '@/api'

const items = ref([])
const loading = ref(true)
const error = ref('')

function formatDate(value) {
  return new Date(value).toLocaleString('zh-CN')
}

onMounted(async () => {
  try {
    const payload = await service.learningMap.myChangelog()
    items.value = payload.items || []
  } catch (err) {
    error.value = err?.response?.data?.detail?.detail || err?.response?.data?.detail || '读取失败'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.changelog-page { width: min(1100px, calc(100% - 40px)); margin: 0 auto; padding: 40px 0 72px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; border-bottom: 2px solid var(--text-primary); padding-bottom: 20px; margin-bottom: 22px; }
.eyebrow { font-size: 12px; letter-spacing: .18em; text-transform: uppercase; color: var(--primary-color); font-weight: 700; }
h1 { font-family: "Songti SC", serif; font-size: 38px; }
.subtitle { color: var(--text-secondary); margin-top: 8px; }
.btn { border: 1px solid var(--border-color); padding: 8px 12px; background: var(--bg-light); color: var(--text-primary); font-weight: 600; }
.state-box { background: var(--bg-light); border: 1px solid var(--border-color); padding: 48px; text-align: center; color: var(--text-muted); }
.log-table { width: 100%; border-collapse: collapse; background: var(--bg-light); border: 1px solid var(--text-primary); }
.log-table th, .log-table td { text-align: left; padding: 11px 12px; border-bottom: 1px solid var(--border-color); font-size: 13px; }
.log-table th { background: var(--bg-paper-2); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
</style>
