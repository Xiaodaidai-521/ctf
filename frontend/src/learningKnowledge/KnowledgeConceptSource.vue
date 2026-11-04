<template>
  <section class="concept-source" aria-labelledby="concept-source-title">
    <div class="concept-source-heading">
      <div>
        <h2 id="concept-source-title">知识点原文</h2>
      </div>
      <router-link :to="user.userInfo?.role === 'teacher' ? '/teacher/knowledge' : user.userInfo?.role === 'admin' ? '/admin/legal/kb' : '/knowledge'">返回{{ user.userInfo?.role === 'teacher' ? names.knowledge : names.foundation }}</router-link>
    </div>
    <a-alert v-if="!managing" type="warning">此资料仅供教师和管理员查看。</a-alert>
    <template v-else>
      <a-alert v-if="paused" type="warning">
        请重新加载资料。
        <a-button v-if="sessionChanged" size="small" @click="privacy.reload">刷新页面</a-button>
        <a-button v-else size="small" @click="load">重新加载</a-button>
      </a-alert>
      <a-alert v-if="error" type="error" role="alert">{{ libraryError(error) }}</a-alert>
      <p v-if="busy" role="status">正在加载知识点…</p>
      <article v-if="source && !paused">
        <h3>{{ source.name }}</h3>
        <pre>{{ source.description || '暂无知识点说明。' }}</pre>
      </article>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'
import { names } from '@/shared/navigation/names.js'
import { errorMessage, knowledgeApi } from './api.js'
import { canManageLibrary, libraryError } from './libraryController.js'
import { usePrivatePage } from './usePrivatePage.js'

const route = useRoute()
const user = useUserStore()
const managing = computed(() => canManageLibrary(user.userInfo?.role))
const source = ref(null)
const busy = ref(false)
const error = ref('')
const privacy = usePrivatePage(() => { source.value = null; error.value = ''; busy.value = false })
const { paused, sessionChanged } = privacy
async function load() {
  if (!managing.value || busy.value || !privacy.resume()) return
  const id = route.query.concept
  if (typeof id !== 'string' || !/^[1-9]\d*$/.test(id) || !Number.isSafeInteger(Number(id))) {
    error.value = '知识点链接无效，请返回资料库重新打开。'
    return
  }
  const ticket = privacy.begin()
  if (!ticket) return
  busy.value = true
  try {
    const result = await knowledgeApi.conceptSource(id, ticket.signal)
    if (ticket.isCurrent()) source.value = result
  } catch (err) {
    if (ticket.isCurrent()) {
      source.value = null
      error.value = errorMessage(err)
    }
  } finally {
    if (ticket.isCurrent()) busy.value = false
    ticket.finish()
  }
}
onMounted(load)
</script>

<style scoped>
.concept-source { padding:var(--space-3); margin-bottom:var(--space-3); border:var(--stroke) solid var(--border-color, var(--line)); border-radius:var(--radius-control); background:var(--bg-card, var(--surface)); }
.concept-source-heading { display:flex; justify-content:space-between; flex-wrap:wrap; gap:var(--space-2); margin-bottom:var(--space-2); }
.concept-source-heading p { margin:0 0 calc(var(--space-1) / 2); color:var(--primary-color, var(--ink-secondary)); font-size:var(--text-caption); }
.concept-source h2 { font-size:var(--text-card); margin:0; }.concept-source h3 { font-size:var(--text-body); margin:var(--space-2) 0 var(--space-1); }
.concept-source-heading a { color:var(--primary-color, var(--ink-secondary)); font-size:var(--text-caption); }
.concept-source-meta { color:var(--text-secondary, var(--ink-secondary)); font-size:var(--text-caption); overflow-wrap:anywhere; line-height:1.7; }
.concept-source pre { white-space:pre-wrap; overflow-wrap:anywhere; font:inherit; font-size:var(--text-caption); line-height:1.9; }
</style>
