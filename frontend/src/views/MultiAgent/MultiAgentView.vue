<template>
  <section class="multi-agent-page" aria-labelledby="multi-agent-heading">
    <div v-if="!isStudent" class="conversation-views" aria-label="对话工作面">
      <button type="button" :aria-pressed="!collaboration" @click="collaboration = false">教学对话</button>
      <button type="button" :aria-pressed="collaboration" @click="collaboration = true">多智能体协作</button>
    </div>
    <h1 id="multi-agent-heading" class="visually-hidden">{{ names.guide }} · {{ collaboration && !isStudent ? '多智能体协作' : '导学对话' }}</h1>
    <KeepAlive>
      <template v-if="isStudent || !collaboration">
        <TutorHost mode="page" />
      </template>
      <LegacyMultiAgentView v-else />
    </KeepAlive>
  </section>
</template>
<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { names } from '@/shared/navigation/names.js'
import TutorHost from '@/learning/agent/components/TutorHost.vue'
import LegacyMultiAgentView from './legacy/LegacyMultiAgentView.vue'
import { clearPageContext, setPageContext } from '@/learning/agent/host.js'
import { agentSession } from '@/learning/agent/runtime.js'
import { practiceApi } from '@/learning/practice/api.js'
import { captureAccount } from '@/shared/state/accountScope.js'

// 学生进入多智能体页即是一条可直接提问的居中对话流；教师保留原协作视图。
const user = useUserStore()
const route = useRoute()
const router = useRouter()
const collaboration = computed({
  get: () => route.query.view === 'collaboration',
  set: value => router.replace({ path: route.path, query: { ...route.query, view: value ? 'collaboration' : undefined } }),
})
const isStudent = computed(() => (user.userInfo?.role || 'student') === 'student')
let generation = 0
let active = true

async function applyChallengeContext() {
  const version = ++generation
  const id = route.params.challengeId
  if (!active) return
  if (!id || !user.isAuthenticated || !isStudent.value) { clearPageContext(); return }
  const account = captureAccount()
  const current = () => active && account.current() && version === generation
  try {
    const challenge = await practiceApi.detail(id)
    if (!current()) return
    setPageContext({ kind: 'challenge', ref: id, title: challenge?.title || '' })
    agentSession.setContext({ kind: 'challenge', ref: id, title: challenge?.title || '' })
  } catch {
    if (current()) setPageContext(null)
  }
}

onMounted(applyChallengeContext)
watch(() => route.params.challengeId, applyChallengeContext)
onActivated(() => { if (!active) { active = true; return applyChallengeContext() } })
onDeactivated(() => { active = false; generation++; clearPageContext() })
onBeforeUnmount(() => { active = false; generation++; clearPageContext() })
</script>
<style scoped>
.conversation-views { display: flex; gap: var(--space-1); margin-bottom: var(--space-2); }
.conversation-views button { padding: var(--space-1) var(--space-2); min-height: var(--control-height); color: var(--ink-secondary); background: var(--surface); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); cursor: pointer; }
.conversation-views button[aria-pressed='true'] { color: var(--action); background: var(--action-soft); border-color: var(--action); }
.multi-agent-page { width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: var(--space-4) auto 0; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.multi-agent-page :deep(.tutor-host) { min-height: calc(100vh - var(--header-height) - var(--nav-height) - var(--space-8)); }
</style>
