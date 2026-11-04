<template>
  <div class="challenge-workspace" :class="`is-${mode}`">
    <p v-if="loading" class="workspace-state" role="status">正在读取题目…</p>
    <div v-else-if="error" class="workspace-state error" role="alert">
      <p>{{ error }}</p>
      <div class="state-actions">
        <button type="button" class="btn" @click="load">重新读取</button>
        <button type="button" class="btn" @click="$emit('close')">返回靶场</button>
      </div>
    </div>
    <p v-else-if="!session.challenge.value" class="workspace-state">
      暂时无法读取这道题目。<button type="button" class="btn" @click="$emit('close')">返回靶场</button>
    </p>

    <div v-else class="workspace-grid">
      <button type="button" class="btn mobile-submit-jump" @click="goSubmit">前往提交 Flag</button>
      <div class="workspace-main">
        <ChallengeBody :challenge="session.challenge.value" @ask-tutor="askTutor" />
        <EnvironmentPanel
          v-if="hasEnvironment"
          :state="session.environment.value"
          :status="session.environmentStatus.value"
          :countdown-text="session.countdownText.value"
          :authenticated="authenticated"
          :message="envMessage"
          :message-type="envMessageType"
          @start="startEnvironment"
          @stop="stopEnvironment"
          @copy="copyAccess"
          @refresh="session.refreshEnvironment()"
        />
      </div>

      <aside ref="submissionPanel" class="workspace-side" aria-label="提交与记录">
        <FlagSubmission
          :challenge="session.challenge.value"
          :authenticated="authenticated"
          :flag="session.flag.value"
          :submitting="session.submitting.value"
          :message="session.message.value"
          :message-type="session.messageType.value"
          @update:flag="session.setFlag"
          @submit="submit"
          @ask-tutor="askTutor"
        />
        <SubmissionHistory
          :authenticated="authenticated"
          :items="session.submissions.value.items"
          :info="session.submissions.value"
          :has-next="session.submissions.value.hasNext"
          :loading="session.submissionsLoading.value"
          :error="session.submissionsError.value"
          @more="session.loadSubmissions({ more: true })"
          @retry="session.loadSubmissions()"
        />
        <RelatedLearning :challenge="session.challenge.value" :same-category="session.related.value.sameCategory" />
        <div v-if="mode === 'modal'" class="full-page-entry">
          <router-link :to="`/challenge/${challengeId}`" class="btn btn-primary btn-block">在完整题目页打开</router-link>
        </div>
      </aside>
    </div>
  </div>
</template>
<script setup>
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { accountScope } from '@/shared/state/accountScope.js'
import ChallengeBody from './components/ChallengeBody.vue'
import FlagSubmission from './components/FlagSubmission.vue'
import SubmissionHistory from './components/SubmissionHistory.vue'
import RelatedLearning from './components/RelatedLearning.vue'
import EnvironmentPanel from './components/EnvironmentPanel.vue'
import { createWorkspaceSession } from './workspaceSession.js'
import { practiceApi } from './api.js'
import { requestTutorDrawer, setPageContext, clearPageContext } from '@/learning/agent/host.js'
import { useUserStore } from '@/store/user'

const props = defineProps({
  challengeId: { type: Number, required: true },
  // page = 直达页宿主；modal = 靶场弹层宿主，两者共用同一套工作台动作。
  mode: { type: String, default: 'page' },
})
const emit = defineEmits(['close', 'solved', 'loaded'])
const userStore = useUserStore()
const authenticated = computed(() => Boolean(userStore.isAuthenticated))

const apiClient = {
  ...practiceApi,
  clipboard: typeof navigator === 'undefined' ? { writeText: async () => {} } : navigator.clipboard,
}
const makeSession = () => createWorkspaceSession({
  apiClient, challengeId: props.challengeId,
  userId: userStore.userInfo?.id ?? (userStore.isAuthenticated ? 'account' : null),
})
const currentSession = shallowRef(makeSession())
// Keep refs intact for both the template and the modal host's exposed contract.
const session = new Proxy({}, { get: (_, key) => currentSession.value[key] })
const loading = computed(() => session.loading.value)
const error = computed(() => session.error.value)
const submissionPanel = ref(null)
let active = true, alive = true
function goSubmit() { submissionPanel.value?.scrollIntoView?.({ block: 'start', behavior: 'smooth' }) }
// 环境动作的反馈留在环境面板内，不混进 Flag 提交区的消息。
const envMessage = ref('')
const envMessageType = ref('')
const hasEnvironment = computed(() => Boolean(
  session.challenge.value?.docker_image
  || session.environment.value.info
  || session.environment.value.phase !== 'idle'
  || session.challenge.value?.submission_mode === 'practice',
))

function publishContext() {
  const value = session.challenge.value
  if (!alive || !active || !value) return
  const next = {
    kind: 'challenge', ref: value.id ?? props.challengeId,
    title: value.title || '', reason: '当前正在练习的题目',
    // 只标记作者是否给出公开提示，不把提示正文带进对话上下文。
    authorHint: Boolean(value.hint),
  }
  setPageContext(next)
}
async function load() {
  const target = currentSession.value
  await target.load()
  if (!alive || target !== currentSession.value || !active) return
  publishContext()
  if (session.challenge.value) emit('loaded', { title: session.challenge.value.title || '题目详情' })
  if (authenticated.value) {
    await Promise.allSettled([session.loadSubmissions(), session.refreshEnvironment()])
  }
}
async function submit() {
  const target = currentSession.value
  const result = await target.submit()
  if (!alive || target !== currentSession.value || result?.cancelled) return
  if (result?.ok) {
    emit('solved', { challengeId: props.challengeId })
    if (userStore.fetchProfile) await userStore.fetchProfile().catch(() => {})
  }
}
function sayEnvironment(message, type) {
  envMessage.value = message || ''
  envMessageType.value = type
}
async function startEnvironment() {
  sayEnvironment('', '')
  const target = currentSession.value
  const result = await target.startEnvironment()
  if (!alive || !active || target !== currentSession.value || result?.cancelled) return
  if (result?.message) sayEnvironment(result.message, result.ok ? 'info' : 'error')
}
async function stopEnvironment() {
  const target = currentSession.value
  const result = await target.stopEnvironment()
  if (!alive || !active || target !== currentSession.value || result?.cancelled) return
  if (result?.message) sayEnvironment(result.message, result.ok ? 'success' : 'error')
}
async function copyAccess() {
  const target = currentSession.value
  const result = await target.copyAccess()
  if (!alive || !active || target !== currentSession.value || result?.cancelled) return
  if (result?.message) sayEnvironment(result.message, result.ok ? 'success' : 'error')
}
function askTutor() {
  publishContext()
  requestTutorDrawer()
}

onMounted(load)
watch(() => [props.challengeId, accountScope.value.epoch], () => {
  clearPageContext(); session.destroy(); currentSession.value = makeSession()
  envMessage.value = ''; envMessageType.value = ''
  if (active) load()
})
onActivated(() => { active = true; publishContext(); if (session.challenge.value) session.resume() })
onDeactivated(() => { active = false; clearPageContext(props.challengeId); session.suspend() })
onUnmounted(() => { alive = false; clearPageContext(props.challengeId); session.destroy() })
defineExpose({ session, load })
</script>
<style scoped>
.challenge-workspace { min-width: 0; }
.mobile-submit-jump { display: flex; grid-column: 1 / -1; justify-self: start; }
.workspace-side { scroll-margin-top: var(--space-4); }
.workspace-state { margin: 0; padding: var(--space-6) var(--space-3); text-align: center; color: var(--ink-secondary); }
.workspace-state.error { color: var(--negative); }
.state-actions { display: flex; justify-content: center; gap: var(--space-1); margin-top: var(--space-2); }
.workspace-grid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: var(--density-gap); align-items: start; min-width: 0; }
.workspace-main { display: grid; gap: var(--density-gap); min-width: 0; }
.workspace-side { display: grid; gap: var(--density-gap); min-width: 0; }
.full-page-entry { padding-top: var(--space-1); }
.btn { display: inline-flex; align-items: center; justify-content: center; min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; text-decoration: none; cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn-block { width: 100%; }
.btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
@media (max-width: 1120px) {
  .workspace-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 768px) {
  .workspace-grid, .workspace-main, .workspace-side { gap: var(--space-2); }
  .mobile-submit-jump { display: flex; width: 100%; min-height: var(--space-6); }
  .state-actions { flex-direction: column; }
}
</style>
