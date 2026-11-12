<template>
  <div class="tutor-host" :class="{ 'is-page': mode === 'page', 'is-drawer': mode === 'drawer', 'with-dock': dockOpen }">
    <div data-retain-scroll class="host-main">
    <header class="host-heading">
      <div class="host-title">
        <span class="host-mark" aria-hidden="true"><AppIcon name="bi-cpu" /></span>
        <div><h2>{{ mode === 'drawer' ? '题内辅导' : '和智航一起学' }}</h2><p>先给思路与分级提示，再一起练习。</p></div>
      </div>
      <div class="host-actions">
        <button v-if="mode === 'page'" type="button" class="dock-toggle" :aria-pressed="dockOpen" @click="toggleDock">
          <AppIcon name="bi-journal-check" />教学产出
        </button>
        <ConversationActions
          :messages="messages" :conversation-id="conversationId" :disabled="sending"
          @export="exportRecord" @restart="restart" @delete="deleteHistory"
        />
      </div>
    </header>

    <div v-if="contextLabel" class="context-chip">
      <span><AppIcon name="bi-link-45deg" />{{ contextLabel }}</span>
      <button type="button" class="clear-context" aria-label="清除当前学习上下文" @click="dropContext">清除</button>
    </div>

    <p v-if="switchNote" class="switch-note" role="status">{{ switchNote }}</p>
    <ProtectionBadge :status="sending ? undefined : protection?.content" label="对话内容加密保存" explanation="服务器保存的对话正文采用加密方式保存；尚未提交的输入和本机导出的协作记录需另行保管。" />
    <ChallengeTutoringGuide v-if="challengeContext" :policy="policy" />
    <TeachingProgress class="host-progress" :messages="messages" />

    <ConversationStream ref="streamRef" :messages="messages" :restoring="restoring">
      <template #tail>
        <ResourceReferences v-if="resources.length || resourceError" :resources="resources" :error="resourceError" />
      </template>
    </ConversationStream>

    <ExecutionStatus :phase="phase" :error="error" @stop="stopWaiting" />

    <TutorComposer
      ref="composerRef"
      class="host-composer"
      :draft-key="draftKey"
      :busy="sending"
      :disabled="!authenticated || restoring"
      :placeholder="mode === 'drawer' ? '哪里卡住了？先说说你的尝试' : '说说目标或卡住的地方'"
      :quick-actions="quickActions"
      @submit="submit"
      @quick="quickPrompt"
    />
    <p v-if="!authenticated" class="login-note"><router-link to="/login">登录</router-link>后继续学习，历史会话按账号隔离。</p>
    </div>
    <TeachingArtifactDock
      v-if="dockOpen"
      :artifacts="artifacts"
      :failures="artifactFailures"
      :loading="artifactLoading"
      @refresh="loadArtifacts"
      @close="dockOpen = false"
    />
  </div>
</template>
<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import ProtectionBadge from '@/shared/privacy/ProtectionBadge.vue'
import { createAccountGuard } from '@/shared/state/accountScope.js'
import { useRouter } from 'vue-router'
import AppIcon from '@/shared/design/AppIcon.vue'
import { useUserStore } from '@/store/user'
import { takeDraft, subscribeDraft } from '../draft.js'
import { agentSession, syncAgentAccount } from '../runtime.js'
import { contextLabel as labelFor, sameContext } from '../context.js'
import { collaborationRecord } from '../presentation.js'
import { currentPageContext, subscribePageContext } from '../host.js'
import { challengeSwitchNote, tutoringPolicy } from '../tutoring.js'
import ChallengeTutoringGuide from './ChallengeTutoringGuide.vue'
import ConversationActions from './ConversationActions.vue'
import ConversationStream from './ConversationStream.vue'
import ExecutionStatus from './ExecutionStatus.vue'
import ResourceReferences from './ResourceReferences.vue'
import TeachingProgress from './TeachingProgress.vue'
import TeachingArtifactDock from './TeachingArtifactDock.vue'
import TutorComposer from './TutorComposer.vue'
import { readArtifacts, shouldRefresh } from '../artifacts.js'
import { guideApi } from '@/learning/guide/api.js'
import { pathsApi } from '@/learning/paths/api.js'
import { growthApi } from '@/learning/growth/api.js'

const props = defineProps({ mode: { type: String, default: 'page' } })
const emit = defineEmits(['exported'])
const router = useRouter()
const user = useUserStore()
const account = createAccountGuard()
let active = true
const authenticated = computed(() => user.isAuthenticated)
const session = agentSession
const messages = ref([])
const resources = ref([])
const resourceError = ref('')
const conversationId = ref(null)
const phase = ref('idle')
const restoring = ref(false)
const sending = ref(false)
const error = ref('')
const context = ref(null)
const metadata = ref(null)
const protection = ref(null)
const switchNote = ref('')
const streamRef = ref(null)
const composerRef = ref(null)
const dockOpen = ref(false)
const artifacts = ref(null)
const artifactFailures = ref([])
const artifactLoading = ref(false)
let artifactsRequest = 0

// 停靠产出只读真实接口；对话完成后若产出标识变化才刷新，避免无谓重读。
async function loadArtifacts() {
  const version = ++artifactsRequest
  artifactLoading.value = true
  const next = await readArtifacts({
    plan: () => growthApi.teachingPlan(),
    paths: () => pathsApi.my(),
    reviews: () => guideApi.reviews(),
  })
  if (!account.current() || version !== artifactsRequest) return
  artifacts.value = next
  artifactFailures.value = next.failures
  artifactLoading.value = false
  return next
}
function toggleDock() {
  dockOpen.value = !dockOpen.value
  if (dockOpen.value && !artifacts.value) loadArtifacts()
}

const draftKey = computed(() => context.value ? `${context.value.kind}:${context.value.ref ?? 'general'}` : 'general')
const contextLabel = computed(() => labelFor(context.value))
const challengeContext = computed(() => context.value?.kind === 'challenge')
// 只呈现后台真实 metadata；没有关联 attempt/run 时层级显示“未返回”。
const policy = computed(() => tutoringPolicy({ context: context.value, metadata: metadata.value, authorHint: context.value?.authorHint === true }))
const quickActions = computed(() => challengeContext.value
  ? [{ value: '请给一点提示：只给思路，不要给答案或完整解法。', label: '请给一点提示' }]
  : [])

function applySnapshot(snapshot) {
  if (!account.current() || !active) return
  messages.value = [...snapshot.messages]
  resources.value = [...snapshot.resources]
  conversationId.value = snapshot.conversationId
  phase.value = snapshot.phase
  restoring.value = snapshot.restoring
  sending.value = snapshot.sending
  error.value = snapshot.error
  context.value = snapshot.context
  metadata.value = snapshot.metadata
  protection.value = snapshot.protection || null || null
}
const unsubscribeSession = session.subscribe(applySnapshot)
syncAgentAccount(user.userInfo?.id || null)
applySnapshot(session.state)

async function submit(text) {
  if (!authenticated.value) { router.push('/login'); return }
  if (!account.current() || !active) return
  const previous = artifacts.value
  const result = await session.send({ message: text, agentIds: ['tutor'] })
  if (!account.current()) return
  // 回复完成后只重读真实产出；没有结构化新计划就保留来源说明，不把建议写成已加入。
  if (result?.ok && dockOpen.value) {
    const next = await loadArtifacts()
    if (next && !shouldRefresh(previous, next) && previous) artifacts.value = previous
  }
}
function quickPrompt(value) {
  submit(value)
}
function stopWaiting() { session.cancelWaiting() }
function dropContext() { session.setContext(null) }
function restart() {
  session.reset()
  resources.value = []
  resourceError.value = ''
  composerRef.value?.focus()
}
async function deleteHistory() {
  await session.reset({ deleteServer: true })
  if (!account.current()) return
  resources.value = []
  resourceError.value = ''
}
function exportRecord() {
  const record = collaborationRecord({ transcript: messages.value })
  const blob = new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = '智航协作记录.json'
  anchor.click()
  URL.revokeObjectURL(url)
  emit('exported', record)
}

// 页面/抽屉共享同一控制器；草稿按账号交接，不重复投递首条问题。
function takePendingDraft() {
  if (!active || !account.current() || session.state.restoring || session.state.sending) return
  const draft = takeDraft(user.userInfo?.id)
  if (draft) submit(draft)
}
const unsubscribeDraft = subscribeDraft(takePendingDraft)
watch([restoring, sending], () => takePendingDraft())
watch(() => user.userInfo?.id, id => { syncAgentAccount(id); applySnapshot(session.state) })

// 当前页对象变化时：同题保留对话；换题则先划清边界（不再沿用上一题的会话），并说明切换。
function syncPageContext(page) {
  if (!active || !account.current()) return
  if (!page || page.kind !== 'challenge') return
  // 以控制器里的上下文为准（首次挂载时组件本地副本尚未应用快照）。
  const previous = session.state.context
  if (!previous) { switchNote.value = ''; session.setContext(page); return }
  if (sameContext(previous, page)) {
    if (previous.authorHint !== page.authorHint) session.setContext(page)
    return
  }
  switchNote.value = challengeSwitchNote(previous, page)
  session.reset()
  session.setContext(page)
}
const unsubscribePage = subscribePageContext(syncPageContext)

onMounted(() => {
  // 抽屉里打开时，把题内上下文同步给同一会话；只做引用，不抓题面答案，也不自动发问。
  applySnapshot(session.state)
  if (props.mode === 'page') takePendingDraft()
  composerRef.value?.focus()
})
onActivated(() => { active = true; syncPageContext(currentPageContext()); applySnapshot(session.state); if (props.mode === 'page') takePendingDraft() })
onDeactivated(() => { active = false })
onBeforeUnmount(() => { account.dispose(); artifactsRequest++; artifacts.value = null; unsubscribeDraft(); unsubscribeSession(); unsubscribePage() })
defineExpose({ focus: () => composerRef.value?.focus(), submit })
</script>
<style scoped>
.tutor-host { min-height: 0; }
/* 固定行数会在新增说明块时错位：改为纵向排布，只有对话流可伸缩滚动。 */
.host-main { display: flex; flex-direction: column; gap: var(--space-2); min-height: 0; height: 100%; }
.host-main > .conversation-stream { flex: 1 1 auto; min-height: 0; }
.with-dock { display: grid; grid-template-columns: minmax(0, 1fr) minmax(240px, 320px); gap: var(--space-2); align-items: stretch; }
/* 抽屉高度有限：说明展开时整列可滚动，输入坞仍贴在底部。 */
.is-drawer .host-main { overflow-y: auto; }
.is-drawer .host-main > .conversation-stream { flex: 1 0 auto; overflow: visible; }
.host-actions { display: flex; align-items: center; gap: var(--space-1); }
.dock-toggle { display: flex; align-items: center; gap: 2px; padding: var(--space-1); border: 0; background: transparent; color: var(--ink-secondary); cursor: pointer; font-size: var(--text-caption); }
.dock-toggle[aria-pressed="true"] { color: var(--agent-accent); }
.host-heading { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--space-2); }
.host-actions { flex: none; }
.host-title { display: flex; align-items: center; gap: var(--space-2); }
.host-title h2 { margin: 0; font-size: var(--text-card); }
.host-title p { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.host-mark { display: grid; place-items: center; width: var(--space-6); height: var(--space-6); border-radius: var(--radius-panel); background: var(--agent-soft); color: var(--agent-accent); font-size: var(--text-page); }
.switch-note { margin: 0; padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--action-soft); color: var(--action); font-size: var(--text-caption); }
.context-chip { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.context-chip > span { display: flex; align-items: center; gap: var(--space-1); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.clear-context { flex: none; white-space: nowrap; border: 0; background: transparent; color: var(--ink-secondary); text-decoration: underline; cursor: pointer; font-size: var(--text-caption); }
.host-progress { padding-bottom: var(--space-1); }
.host-composer { position: sticky; bottom: 0; box-shadow: var(--shadow-raised); }
.login-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.is-page { width: min(var(--reading-width), 100%); margin-inline: auto; height: 100%; }
.is-drawer { height: 100%; padding: var(--space-2); }
.is-drawer .host-main { height: 100%; }
@media (max-width: 1000px) {
  .with-dock { grid-template-columns: minmax(0, 1fr); }
}
</style>
