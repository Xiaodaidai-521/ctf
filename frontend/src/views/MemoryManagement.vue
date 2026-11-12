<template>
  <main class="memory-page">
    <h1>我的 AI 记忆</h1><p>查看 AI 保存的长期记忆，或删除不再需要的记录。</p>
    <div class="memory-actions"><button type="button" :disabled="loading || deleting !== null" @click="load(null)">刷新</button><router-link to="/privacy">隐私与数据保护</router-link></div>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="loading" role="status">正在读取记忆…</p><p v-else-if="!items.length && !error">暂无已保存的 AI 记忆。</p>
    <article v-for="item in items" :key="item.id" class="memory-item">
      <h2>{{ typeLabel(item.memory_type) }}</h2><ProtectionBadge :status="combinedStatus(item)" label="记忆内容加密保存" />
      <p>更新时间：{{ new Date(item.updated_at).toLocaleString() }}</p>
      <pre v-if="item.memory_value !== null">{{ JSON.stringify(item.memory_value, null, 2) }}</pre><p v-else>内容暂时无法读取。</p>
      <button type="button" :disabled="deleting !== null || loading" @click="selected = item">删除这条记忆</button>
    </article>
    <button v-if="next" type="button" :disabled="loading || deleting !== null" @click="load(next)">下一页</button>
    <a-modal :visible="Boolean(selected)" title="删除 AI 记忆" :ok-loading="deleting !== null" :closable="deleting === null" :mask-closable="deleting === null" :cancel-button-props="{ disabled: deleting !== null }" @cancel="selected = null" @ok="remove">
      <p>删除后，这条记忆将不再供 AI 使用。已有对话记录会分别保留。</p>
    </a-modal>
  </main>
</template>
<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { captureAccount } from '@/shared/state/accountScope.js'
import { useUserStore } from '@/store/user'
import api from '@/api'
import ProtectionBadge from '@/shared/privacy/ProtectionBadge.vue'
const user = useUserStore()
const items = ref([]), next = ref(null), loading = ref(false), error = ref(''), notice = ref(''), selected = ref(null), deleting = ref(null)
let generation = 0, alive = true
function combinedStatus(item) {
  const values = item.protection || {}
  if (values.memory_value?.storage === 'encrypted' && ['encrypted', 'empty'].includes(values.metadata?.storage)) return values.memory_value
  return values.memory_value?.storage === 'empty' ? values.memory_value : { storage: 'unknown' }
}
const typeLabel = type => ({ preference: '学习偏好', learning_insight: '学习观察', interaction_pattern: '交流习惯', fact: '个人记忆', temporary: '临时记忆' })[type] || 'AI 记忆'
async function load(cursor = null) {
  const account = captureAccount(), version = ++generation
  items.value = []; next.value = null; loading.value = true; error.value = ''
  try {
    const data = await api.memory.list(cursor)
    if (!alive || version !== generation || !account.current()) return
    items.value = Array.isArray(data) ? data : data.results || []; next.value = data.next || null
  } catch { if (alive && version === generation && account.current()) error.value = '记忆暂时无法读取，请重试。' }
  finally { if (alive && version === generation && account.current()) loading.value = false }
}
async function remove() {
  if (!selected.value || deleting.value !== null) return
  const account = captureAccount(), id = selected.value.id
  deleting.value = id; error.value = ''
  try { await api.memory.remove(id); if (!alive || !account.current()) return; selected.value = null; notice.value = '这条记忆已删除。'; await load(null) }
  catch { if (alive && account.current()) error.value = '记忆删除失败，请重试。' }
  finally { if (alive && account.current()) deleting.value = null }
}
watch(() => `${user.userInfo?.id}:${user.userInfo?.role}`, () => { generation++; items.value = []; selected.value = null; notice.value = ''; error.value = ''; deleting.value = null; load(null) })
onMounted(() => load(null)); onBeforeUnmount(() => { alive = false; generation++ })
</script>
<style scoped>
.memory-page { max-width: 900px; margin: 30px auto; padding: 24px; } .memory-actions { display: flex; gap: 18px; align-items: center; } .memory-item { padding: 20px; margin-block: 16px; border: 1px solid var(--line, #ddd); border-radius: 10px; } .memory-item h2 { font-size: 18px; } pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
</style>
