<template>
  <div class="learning-history">
    <p>这里记录你本人的能力状态变化：时间、前后状态与原因都可以重看。展示最近最多两百条记录。</p>
    <button type="button" :disabled="loading" @click="load">刷新学习历史</button>
    <CapabilityHistoryTable :rows="rows" :loading="loading" :error="error" caption="本人能力状态变化记录" @retry="load" />
  </div>
</template>
<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'
import { capabilityApi } from '@/learning/capability/api.js'
import { changelogViews } from '@/learning/capability/presentation.js'
import CapabilityHistoryTable from '@/shared/learning/CapabilityHistoryTable.vue'

const route = useRoute()
const user = useUserStore()
const rows = ref([])
const loading = ref(false)
const error = ref('')
let generation = 0

async function load() {
  const token = ++generation
  rows.value = []
  loading.value = true
  error.value = ''
  try {
    // 本人接口不接受 query 中的学生身份；目录筛选沿用原授权接口。
    const version = typeof route.query.version === 'string' ? route.query.version : undefined
    const payload = await capabilityApi.changelog(version ? { version } : undefined)
    if (token === generation) rows.value = changelogViews(payload)
  } catch (err) {
    if (token !== generation) return
    const status = err?.response?.status
    error.value = status === 403 ? '当前账号无权查看这份学习历史。' : status === 404 ? '这份学习历史暂不可用，请核对目录后重试。' : '学习历史暂时无法读取，请稍后重试。'
  } finally {
    if (token === generation) loading.value = false
  }
}
watch(() => [user.userInfo?.id, user.userInfo?.role, route.query.version], load, { immediate: true })
onBeforeUnmount(() => { generation += 1; rows.value = []; error.value = ''; loading.value = false })
</script>
<style scoped>
.learning-history { color: var(--ink-secondary); }
button { min-height: var(--control-height); margin-bottom: var(--space-2); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
button:disabled { color: var(--disabled-ink); background: var(--disabled); cursor: not-allowed; }
button:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
