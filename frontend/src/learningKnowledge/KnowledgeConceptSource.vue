<template>
  <section class="concept-source" aria-labelledby="concept-source-title">
    <div class="concept-source-heading">
      <div>
        <h2 id="concept-source-title">知识点原文</h2>
      </div>
      <router-link :to="user.userInfo?.role === 'teacher' ? '/teacher/knowledge' : user.userInfo?.role === 'admin' ? '/admin/legal/kb' : '/knowledge'">返回知识资料库</router-link>
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
.concept-source { padding: 24px; margin-bottom: 24px; border: 1px solid var(--border-color, #d9cfbe); border-radius: 8px; background: var(--bg-card, #fffdf8); }
.concept-source-heading { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 16px; margin-bottom: 18px; }
.concept-source-heading p { margin: 0 0 6px; color: var(--primary-color, #b42318); font-size: 12px; }
.concept-source h2 { font-size: 19px; margin: 0; }.concept-source h3 { font-size: 17px; margin: 18px 0 10px; }
.concept-source-heading a { color: var(--primary-color, #b42318); font-size: 13px; }
.concept-source-meta { color: var(--text-secondary, #625a4d); font-size: 12px; overflow-wrap: anywhere; line-height: 1.7; }
.concept-source pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; font-size: 14px; line-height: 1.9; }
</style>
