<template>
  <a-button type="text" class="message-trigger" :aria-label="unread ? `消息，${unread} 条未读` : '消息'" @click="open = true">
    <icon-notification /><span v-if="unread" class="unread-count">{{ unread }}</span><span v-else>消息</span>
  </a-button>
  <a-drawer v-model:visible="open" title="消息" :width="drawerWidth" :footer="false">
    <p class="message-intro">平台公告与学习提醒</p>
    <a-spin v-if="loading" tip="正在加载公告…" />
    <a-alert v-else-if="error" type="error">公告暂时无法加载。<a-button type="text" @click="load">重试</a-button></a-alert>
    <a-empty v-else-if="!rows.length" description="暂时没有新公告" />
    <div v-else class="announcement-list">
      <button v-for="row in rows" :key="row.id" class="announcement-row" @click="showDetail(row)">
        <span class="announcement-meta"><span>{{ priority(row.priority) }}</span><span>{{ readIds.includes(row.id) ? '已读' : '未读' }}</span></span>
        <strong>{{ row.title }}</strong><span>{{ row.summary }}</span><time>{{ date(row.created_at) }}</time>
      </button>
    </div>
    <section v-if="selected" class="announcement-detail" aria-live="polite">
      <h2>{{ selected.title }}</h2>
      <a-spin v-if="detailLoading" tip="正在加载正文…" />
      <a-alert v-else-if="detailError" type="error">正文暂时无法加载。<a-button type="text" @click="showDetail(selected)">重试</a-button></a-alert>
      <template v-else><p class="announcement-meta">{{ selected.author_name }} · {{ date(selected.published_at || selected.created_at) }}</p><p class="announcement-content">{{ selected.content }}</p></template>
    </section>
  </a-drawer>
</template>
<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import api from '@/api'
import { useUserStore } from '@/store/user'
const user = useUserStore()
const key = `announcement-read:${user.userInfo?.id || 'guest'}`
function loadReadIds() { try { const ids = JSON.parse(localStorage.getItem(key) || '[]'); return Array.isArray(ids) ? ids : [] } catch { return [] } }
const readIds = ref(loadReadIds())
const rows = ref([])
const loading = ref(false)
const error = ref(false)
const open = ref(false)
const selected = ref(null)
const detailLoading = ref(false)
const detailError = ref(false)
let request = 0
let alive = true
const drawerWidth = 'min(100vw, var(--message-width))'
const unread = computed(() => rows.value.filter(row => !readIds.value.includes(row.id)).length)
const list = response => Array.isArray(response) ? response : response?.results || []
const priority = value => ({ high: '重要公告', medium: '提醒', low: '公告' }[value] || '公告')
const date = value => value ? new Date(value).toLocaleDateString('zh-CN') : ''
async function load() {
  loading.value = true
  error.value = false
  try {
    const response = await api.announcement.pinned()
    const pinned = list(response)
    const latest = list(await api.announcement.latest())
    if (alive) rows.value = [...new Map([...pinned, ...latest].map(row => [row.id, row])).values()]
  } catch { if (alive) error.value = true }
  finally { if (alive) loading.value = false }
}
async function showDetail(row) {
  const version = ++request
  selected.value = row
  detailLoading.value = true
  detailError.value = false
  try {
    const detail = await api.announcement.detail(row.id)
    if (!alive || version !== request) return
    selected.value = detail
    if (!readIds.value.includes(row.id)) readIds.value.push(row.id)
    try { localStorage.setItem(key, JSON.stringify(readIds.value)) } catch { /* 阅读状态不影响公告正文。 */ }
  } catch { if (alive && version === request) detailError.value = true }
  finally { if (alive && version === request) detailLoading.value = false }
}
onMounted(load)
onBeforeUnmount(() => { alive = false; request++ })
</script>
<style scoped>
.message-trigger { color: var(--ink-secondary); }
.unread-count { margin-left: var(--space-1); font-weight: var(--weight-strong); }
.message-intro, .announcement-meta, time { color: var(--ink-secondary); font-size: var(--text-caption); }
.announcement-list { display: grid; }
.announcement-row { display: grid; gap: var(--space-1); width: 100%; text-align: left; border: 0; border-bottom: var(--stroke) solid var(--line); background: var(--surface); padding: var(--space-2); color: var(--ink); cursor: pointer; }
.announcement-row:hover { background: var(--surface-muted); }
.announcement-meta { display: flex; justify-content: space-between; }
.announcement-detail { margin-top: var(--space-4); }
.announcement-detail h2 { font-size: var(--text-section); }
.announcement-content { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
