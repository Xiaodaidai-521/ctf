<template>
  <div class="module-learning-page">
    <header class="module-header"><div class="breadcrumb"><button class="btn" @click="goBack"><icon-arrow-left aria-hidden="true" />返回{{ names.paths }}</button><router-link :to="`/learning-paths/${pathId}`">{{ path?.title || '航线详情' }}</router-link><span>{{ view.title }}</span></div><div class="header-actions"><button class="btn" @click="refreshData" :disabled="loading || starting || completing">刷新</button><button v-if="status.canStart" class="btn btn-primary" @click="startModule" :disabled="loading || !!error || starting || completing">{{ starting ? '正在开始…' : '开始学习' }}</button><button v-if="status.canComplete" class="btn" @click="markComplete" :disabled="loading || !!error || starting || completing">{{ completing ? '正在提交…' : '标记完成' }}</button></div></header>
    <div v-if="loading" class="state-panel" role="status"><span class="spinner"></span>正在读取章节…</div>
    <div v-else-if="error" class="state-panel error" role="alert">{{ error }} <button class="btn" @click="loadData">重新读取</button></div>
    <template v-else>
      <section class="chapter-summary"><h1>{{ view.title }}</h1><p>{{ view.description }}</p><p>{{ view.typeLabel }} · {{ view.minutesLabel }} · {{ position.label }}</p><p>{{ requires.label }}</p><p>{{ status.label }} · 开始：{{ status.startedLabel }} · 完成：{{ status.completedLabel }}</p><p>{{ status.note }} 标记完成不称已独立掌握。</p><p v-if="catalogError" class="error" role="status">{{ catalogError }}</p></section>
      <div class="learning-columns" :class="{ 'has-labs': labs.length }"><div class="content-column"><ModuleContent :view="view" :html="renderedContent" /><ModuleNotes v-model="notes" :status="notesStatus" @save-local="saveLocal" @copy="copyNotes" @download="downloadNotes" /></div><ModuleLabs :labs="labs" :capability="capability" /></div>
      <PathConceptPreview :path-id="pathId" />
      <nav class="module-nav" aria-label="章节导航"><router-link v-if="position.previous" :to="position.previous.to" class="btn">上一章：{{ position.previous.title }}</router-link><router-link v-if="position.next" :to="position.next.to" class="btn">下一章：{{ position.next.title }}</router-link><p v-if="!position.known">章节目录暂未读取，无法显示上一章/下一章。</p></nav>
    </template>
    <p v-if="message.visible" class="notice" :class="message.type" role="status">{{ message.text }}</p>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { useUserStore } from '@/store/user'
import { marked } from 'marked'
import { sanitizeHtml } from '@/utils/sanitize.js'
import { names } from '@/shared/navigation/names'
import { pathsApi } from '@/learning/paths/api.js'
import { asList } from '@/learning/contracts.js'
import { moduleView, moduleStatusView, labViews, labCapability, requiresView, modulePosition, notesView, completeResult, completeFailure, loadFailure, startFailure } from '@/learning/paths/moduleLearning.js'
import ModuleContent from '@/learning/paths/components/ModuleContent.vue'
import ModuleNotes from '@/learning/paths/components/ModuleNotes.vue'
import ModuleLabs from '@/learning/paths/components/ModuleLabs.vue'
import PathConceptPreview from '@/learning/paths/components/PathConceptPreview.vue'

const route = useRoute(), router = useRouter(), userStore = useUserStore()
const pathId = computed(() => route.params.pathId), moduleId = computed(() => route.params.moduleId)
const path = ref(null), module = ref(null), catalog = ref([]), moduleProgress = ref(null)
const loading = ref(false), error = ref(''), catalogError = ref(''), starting = ref(false), completing = ref(false)
const notes = ref(''), savedNotes = ref('')
const view = computed(() => moduleView(module.value))
const status = computed(() => moduleStatusView(moduleProgress.value))
const requires = computed(() => requiresView(view.value.requires, catalog.value))
const position = computed(() => modulePosition(moduleId.value, catalog.value, pathId.value))
const labs = computed(() => labViews(module.value?.labs))
const capability = labCapability()
const notesStatus = computed(() => notesView({ content: notes.value, saved: savedNotes.value }))
const renderedContent = computed(() => view.value.hasContent ? sanitizeHtml(marked(view.value.content)) : '')
const message = reactive({ visible: false, type: 'info', text: '' })
let generation = 0, alive = true
const notesKey = () => `ctf-module-notes:${userStore.userInfo?.id || 'guest'}:${pathId.value}:${moduleId.value}`
function notify(type, text) { Object.assign(message, { visible: true, type, text }) }
async function loadData() {
  const request = ++generation, id = moduleId.value, pathRef = pathId.value
  loading.value = true
  error.value = ''
  catalogError.value = ''
  module.value = null
  moduleProgress.value = null
  catalog.value = []
  message.visible = false
  try { notes.value = savedNotes.value = localStorage.getItem(notesKey()) || '' } catch { notes.value = savedNotes.value = '' }
  const results = await Promise.allSettled([pathsApi.detail(pathRef), pathsApi.module(id), pathsApi.modules({ learning_path: pathRef })])
  if (!alive || request !== generation || id !== moduleId.value || pathRef !== pathId.value) return
  const [pathResult, moduleResult, catalogResult] = results
  path.value = pathResult.status === 'fulfilled' ? pathResult.value : null
  if (moduleResult.status === 'rejected') error.value = loadFailure(moduleResult.reason).message
  else if (!moduleResult.value || String(moduleResult.value.id) !== String(id)) error.value = '章节资料暂时无法确认，请稍后重试。'
  else module.value = moduleResult.value
  if (catalogResult.status === 'fulfilled') catalog.value = asList(catalogResult.value)
  else catalogError.value = '章节目录暂时无法读取，请稍后重试。'
  loading.value = false
}
async function startModule() {
  if (starting.value || completing.value) return
  const request = generation, id = moduleId.value
  starting.value = true
  try {
    const result = await pathsApi.startModule(moduleId.value)
    if (!alive || request !== generation || id !== moduleId.value) return
    if (!result || String(result.module) !== String(id) || !['IN_PROGRESS', 'COMPLETED'].includes(result.status)) { notify('warning', '开始结果尚未确认，请重新读取后核对。'); return }
    moduleProgress.value = result
    notify('success', '学习状态已读取；以平台记录为准。')
  } catch (error) { if (alive && request === generation) { const failure = startFailure(error); notify(failure.blocked ? 'warning' : 'error', failure.message) } }
  finally { starting.value = false }
}
async function markComplete() {
  if (starting.value || completing.value) return
  const request = generation, id = moduleId.value
  completing.value = true
  try {
    const result = await pathsApi.completeModule(moduleId.value)
    if (!alive || request !== generation || id !== moduleId.value) return
    const checked = completeResult(result, id)
    if (checked.ok) moduleProgress.value = result
    notify(checked.ok ? 'success' : 'warning', checked.message)
  } catch (error) { if (alive && request === generation) { const failure = completeFailure(error); notify(failure.needsStart ? 'warning' : 'error', failure.message) } }
  finally { completing.value = false }
}
function saveLocal() {
  try { localStorage.setItem(notesKey(), notes.value); savedNotes.value = notes.value; notify('success', '笔记已保存到本机浏览器。') }
  catch { notify('error', '本机保存失败，请复制或下载笔记保全。') }
}
async function copyNotes() {
  try { await navigator.clipboard.writeText(notes.value); notify('success', '笔记已复制。') }
  catch { notify('error', '复制失败，请手动选择笔记或下载文件。') }
}
function downloadNotes() {
  const url = URL.createObjectURL(new Blob([notes.value], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `章节${moduleId.value}-笔记.txt`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function confirmLeave() { return !notesStatus.value.dirty || window.confirm('笔记尚未保存到本机，确定离开当前章节吗？') }
function refreshData() { if (confirmLeave()) loadData() }
function beforeUnload(event) { if (notesStatus.value.dirty) { event.preventDefault(); event.returnValue = '' } }
function goBack() { router.push(`/learning-paths/${pathId.value}`) }
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate(to => {
  if (!confirmLeave()) return false
  ++generation
  // Wait until Vue Router has installed the new parameters before loading.
  setTimeout(loadData, 0)
})
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { alive = false; ++generation; window.removeEventListener('beforeunload', beforeUnload) })
onMounted(loadData)
</script>

<style scoped>
.module-learning-page { display: grid; gap: var(--space-3); padding: var(--page-gutter); color: var(--ink); }
.module-header, .breadcrumb, .header-actions, .module-nav { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-2); }
.breadcrumb a { color: var(--action); } .breadcrumb span { color: var(--ink-muted); }
.chapter-summary, .state-panel { min-width: 0; padding: var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
h1 { font-size: var(--text-page); } p { color: var(--ink-secondary); line-height: var(--leading-body); overflow-wrap: anywhere; }
.learning-columns { display: grid; gap: var(--space-3); } .learning-columns.has-labs { grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); } .content-column { display: grid; gap: var(--space-3); min-width: 0; }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1); min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.btn-primary { background: var(--action); color: var(--on-action); border-color: var(--action); }
.btn:hover { border-color: var(--action); } .btn:active { background: var(--surface-hover); } .btn:disabled { color: var(--disabled-ink); background: var(--disabled); cursor: not-allowed; }
.btn:focus-visible, a:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.error { color: var(--negative); } .notice { padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); } .notice.error { background: var(--negative-soft); } .notice.warning { background: var(--warning-soft); }
.spinner { display: inline-block; width: var(--icon-size); height: var(--icon-size); border: var(--stroke) solid var(--line); border-top-color: var(--action); border-radius: var(--radius-pill); animation: spin var(--motion-loop) linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }
.is-compact .module-learning-page :is(.learning-columns.has-labs) { grid-template-columns: minmax(0, 1fr); }
.is-compact .module-learning-page .module-nav { flex-direction: column; }
.is-compact .module-learning-page .header-actions .btn { flex: 1; }
@media (prefers-reduced-motion: reduce) { .spinner { animation: none; } }
</style>
