<template>
  <div class="module-learning-page">
    <div class="page-header">
      <div class="header-content">
        <button type="button" class="back-button" @click="goBack">
          <icon-arrow-left aria-hidden="true" />
          返回{{ names.paths }}
        </button>
        <nav class="module-breadcrumb" aria-label="章节位置">
          <router-link :to="`/learning-paths/${pathId}`">{{ path.title || '航线详情' }}</router-link>
          <icon-arrow-right aria-hidden="true" />
          <span>{{ view.title }}</span>
        </nav>
        <div class="module-meta">
          <span class="difficulty-badge">{{ difficultyLabel(path.difficulty) }}</span>
          <span class="type-badge">{{ view.typeLabel }}</span>
          <span v-if="view.required" class="type-badge">必修</span>
          <span class="type-badge">{{ view.minutesLabel }}</span>
          <span class="type-badge">{{ position.label }}</span>
        </div>
        <h1 class="module-title">{{ view.title }}</h1>
        <p v-if="view.description" class="module-description">{{ view.description }}</p>
        <p class="module-requires">{{ requires.label }}</p>
        <p class="status-line">
          章节状态：<strong>{{ status.label }}</strong>
          <span v-if="status.startedLabel !== '—'"> · 开始于 {{ status.startedLabel }}</span>
          <span v-if="status.completedLabel !== '—'"> · 完成于 {{ status.completedLabel }}</span>
        </p>
      </div>

      <div class="header-actions">
        <button v-if="status.canStart" type="button" class="btn btn-primary" :disabled="starting" :aria-busy="starting" @click="startModule">
          <icon-play-arrow aria-hidden="true" />
          {{ starting ? '正在记录…' : '开始学习' }}
        </button>
        <button v-if="status.canComplete" type="button" class="btn" :disabled="completing" :aria-busy="completing" @click="markComplete">
          <icon-check-circle aria-hidden="true" />
          {{ completing ? '正在记录…' : '标记完成' }}
        </button>
        <span v-else class="btn btn-success" aria-disabled="true">
          <icon-check-circle aria-hidden="true" />
          已完成
        </span>
      </div>
    </div>

    <p class="page-note">{{ status.note }} 完成只表示已学完章节，不称已独立掌握。</p>

    <div v-if="loading" class="state-box" role="status">
      <div class="spinner" aria-hidden="true"></div>
      <p>正在读取章节…</p>
    </div>

    <div v-else-if="error" class="state-box state-error" role="alert">
      <icon-exclamation-circle aria-hidden="true" />
      <h2>{{ notFound ? '章节不存在或已下架' : '章节暂时无法读取' }}</h2>
      <p>{{ error }}</p>
      <button type="button" class="btn" @click="loadData">重试</button>
    </div>

    <template v-else>
      <div class="learning-columns" :class="{ 'has-labs': labs.length }">
        <div class="content-column">
          <ModuleContent :view="view" :html="renderedContent" />
          <ModuleNotes
            v-model="notes"
            :status="notesStatus"
            @save-local="saveLocal"
            @copy="copyNotes"
            @download="downloadNotes"
          />
        </div>
        <ModuleLabs :labs="labs" :capability="capability" />
      </div>

      <PathConceptPreview :path-id="pathId" />

      <nav class="module-nav" aria-label="章节切换">
        <router-link v-if="position.previous" :to="position.previous.to" class="btn">
          <icon-arrow-left aria-hidden="true" /> 上一章：{{ position.previous.title }}
        </router-link>
        <router-link v-if="position.next" :to="position.next.to" class="btn">
          下一章：{{ position.next.title }} <icon-arrow-right aria-hidden="true" />
        </router-link>
        <p v-if="!position.known" class="page-note">章节目录暂未读取，无法显示上一章/下一章；不按编号推测相邻章节。</p>
      </nav>
    </template>

    <div v-if="message.visible" class="toast" :class="`toast-${message.type}`" role="status">{{ message.text }}</div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { names } from '@/shared/navigation/names'
import { pathsApi } from '@/learning/paths/api.js'
import { difficultyLabel } from '@/learning/paths/presentation.js'
import {
  completeFailure, completeResult, labCapability, labViews, loadFailure, modulePosition,
  moduleStatusView, moduleView, notesView, requiresView, startFailure,
} from '@/learning/paths/moduleLearning.js'
import { asList } from '@/learning/contracts.js'
import { marked } from 'marked'
import { sanitizeHtml } from '@/utils/sanitize'
import ModuleContent from '@/learning/paths/components/ModuleContent.vue'
import ModuleNotes from '@/learning/paths/components/ModuleNotes.vue'
import ModuleLabs from '@/learning/paths/components/ModuleLabs.vue'
import PathConceptPreview from '@/learning/paths/components/PathConceptPreview.vue'

const route = useRoute()
const router = useRouter()
const user = useUserStore()
const pathId = computed(() => route.params.pathId)
const moduleId = computed(() => route.params.moduleId)

const loading = ref(true)
const error = ref('')
const notFound = ref(false)
const path = ref({})
const moduleRaw = ref({})
const catalog = ref([])
const view = computed(() => moduleView(moduleRaw.value))
const requires = computed(() => requiresView(view.value.requires, catalog.value))
const position = computed(() => modulePosition(moduleId.value, catalog.value, pathId.value))
const labs = computed(() => labViews(moduleRaw.value.labs))
const capability = labCapability()

// 章节进度只来自 start/complete 的真响应；GET 详情不会创建学习记录。
const progressRecord = ref(null)
const status = computed(() => moduleStatusView(progressRecord.value))
const starting = ref(false)
const completing = ref(false)

const notes = ref('')
const savedNotes = ref('')
const notesStatus = computed(() => notesView({ content: notes.value, saved: savedNotes.value }))
const notesKey = computed(() => `ctf:module-notes:${user.userInfo?.id ?? 'guest'}:${pathId.value}:${moduleId.value}`)

const renderedContent = computed(() => view.value.hasContent ? sanitizeHtml(marked(view.value.content)) : '')
const message = reactive({ visible: false, type: 'info', text: '' })
let messageTimer = null

function showMessage(type, text) {
  message.visible = true
  message.type = type
  message.text = text
  clearTimeout(messageTimer)
  messageTimer = setTimeout(() => { message.visible = false }, 3600)
}

function readLocalDraft() {
  try {
    return localStorage.getItem(notesKey.value) || ''
  } catch {
    return ''
  }
}

let loadVersion = 0

async function loadData() {
  const version = ++loadVersion
  loading.value = true
  error.value = ''
  notFound.value = false
  progressRecord.value = null
  const [pathResult, moduleResult, catalogResult] = await Promise.allSettled([
    pathsApi.detail(pathId.value),
    pathsApi.module(moduleId.value),
    pathsApi.modules({ learning_path: pathId.value }),
  ])
  // 连续切换章节时只采用最后一次请求，避免上一章响应覆盖当前页。
  if (version !== loadVersion) return
  path.value = pathResult.status === 'fulfilled' ? (pathResult.value || {}) : {}
  catalog.value = catalogResult.status === 'fulfilled' ? asList(catalogResult.value) : []
  if (moduleResult.status === 'rejected') {
    // 章节不存在/已下架与网络失败分开说明，不把后端英文原文直接展示给学生。
    const failure = loadFailure(moduleResult.reason)
    notFound.value = failure.notFound
    error.value = failure.message
    loading.value = false
    return
  }
  moduleRaw.value = moduleResult.value || {}
  notes.value = readLocalDraft()
  savedNotes.value = notes.value
  loading.value = false
}

async function startModule() {
  if (starting.value) return
  starting.value = true
  try {
    const record = await pathsApi.startModule(moduleId.value)
    progressRecord.value = record
    showMessage('success', '已记录本章节开始；进度以平台记录为准。')
  } catch (failure) {
    const result = startFailure(failure)
    showMessage(result.blocked ? 'warning' : 'error', result.message)
  } finally {
    starting.value = false
  }
}

async function markComplete() {
  if (completing.value) return
  completing.value = true
  try {
    const payload = await pathsApi.completeModule(moduleId.value)
    const result = completeResult(payload, moduleId.value)
    if (result.ok) progressRecord.value = payload
    showMessage(result.ok ? 'success' : 'warning', result.message)
  } catch (failure) {
    const result = completeFailure(failure)
    if (result.needsStart) progressRecord.value = null
    showMessage(result.needsStart ? 'warning' : 'error', result.message)
  } finally {
    completing.value = false
  }
}

function saveLocal() {
  try {
    localStorage.setItem(notesKey.value, notes.value)
    savedNotes.value = notes.value
    showMessage('success', '已保存到本机浏览器；服务器暂不接收章节笔记。')
  } catch {
    showMessage('error', '本机保存失败，请复制或下载笔记保全内容。')
  }
}

async function copyNotes() {
  try {
    await navigator.clipboard.writeText(notes.value)
    showMessage('success', '笔记已复制到剪贴板。')
  } catch {
    showMessage('warning', '浏览器未允许自动复制，请手动选中复制，或下载为文件。')
  }
}

function downloadNotes() {
  const blob = new Blob([notes.value], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `章节笔记-${moduleId.value}.md`
  link.click()
  URL.revokeObjectURL(url)
  showMessage('success', '已生成本地笔记文件；不会上传到服务器。')
}

function beforeUnload(event) {
  if (!notesStatus.value.dirty) return
  event.preventDefault()
  event.returnValue = ''
}

function goBack() {
  router.push(`/learning-paths/${pathId.value}`)
}

const unsavedNotesGuard = () => {
  if (!notesStatus.value.dirty) return true
  return window.confirm('笔记还没有保存到本机，也没有服务器笔记接口。离开会丢失当前输入，确定离开吗？')
}

onBeforeRouteLeave(unsavedNotesGuard)
// 上一章/下一章复用同一路由记录，离开守卫不会触发；参数变化同样先询问未保存笔记。
onBeforeRouteUpdate(unsavedNotesGuard)

// 站内切换章节时复用组件：按真实路径/章节参数重新读取，不沿用上一章的进度与内容。
watch([pathId, moduleId], ([nextPath, nextModule], [previousPath, previousModule]) => {
  if (nextPath === previousPath && nextModule === previousModule) return
  message.visible = false
  loadData()
})

watch(notesStatus, value => {
  if (value.dirty) window.addEventListener('beforeunload', beforeUnload)
  else window.removeEventListener('beforeunload', beforeUnload)
})

onMounted(loadData)
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  clearTimeout(messageTimer)
})
</script>

<style scoped>
.module-learning-page { display: grid; gap: var(--space-3); width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: var(--space-4) auto var(--space-8); color: var(--ink); }
.page-header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: var(--space-3); padding-bottom: var(--space-3); border-bottom: var(--stroke) solid var(--line); }
.header-content { display: grid; gap: var(--space-1); min-width: 0; flex: 1; }
.back-button { justify-self: start; display: inline-flex; align-items: center; gap: var(--space-1); min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink-secondary); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.module-breadcrumb { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); color: var(--ink-secondary); font-size: var(--text-caption); }
.module-breadcrumb a { color: var(--action); }
.module-meta { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.difficulty-badge, .type-badge { padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.module-title { margin: 0; font-size: var(--text-page); line-height: var(--leading-tight); overflow-wrap: anywhere; }
.module-description { margin: 0; color: var(--ink-secondary); }
.module-requires, .status-line, .page-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.6; }
.header-actions { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.learning-columns { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-3); align-items: start; }
.learning-columns.has-labs { grid-template-columns: minmax(0, 1fr) var(--menu-width); }
.content-column { display: grid; gap: var(--space-3); min-width: 0; }
.module-nav { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-1); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1); min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn:hover:not(:disabled) { border-color: var(--action); color: var(--action); }
.btn-primary:hover:not(:disabled) { background: var(--action-hover); border-color: var(--action-hover); color: var(--on-action); }
.btn:active:not(:disabled) { background: var(--surface-muted); }
.btn-primary:active:not(:disabled) { background: var(--action-pressed); border-color: var(--action-pressed); }
.btn:disabled, .btn.btn-success { cursor: not-allowed; }
.btn:disabled { border-color: var(--line); background: var(--surface-muted); color: var(--ink-muted); }
.btn-success { border-color: var(--positive); background: var(--positive-soft); color: var(--positive); }
.back-button:hover, .btn:focus-visible, .back-button:focus-visible, .module-breadcrumb a:focus-visible { border-color: var(--action); }
:is(.btn, .back-button, .module-breadcrumb a):focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.state-box { display: grid; justify-items: center; gap: var(--space-1); padding: var(--space-6) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); color: var(--ink-secondary); text-align: center; }
.state-box p { margin: 0; }
.state-error { border-color: var(--negative); background: var(--negative-soft); color: var(--negative); }
.spinner { width: var(--control-height); height: var(--control-height); border: var(--focus-width) solid var(--line); border-top-color: var(--action); border-radius: var(--radius-pill); animation: spin calc(var(--motion-slow) * 4) linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.toast { position: fixed; top: calc(var(--header-height) + var(--space-2)); left: 50%; transform: translateX(-50%); z-index: var(--z-overlay); max-width: calc(100% - var(--page-gutter) * 2); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font-size: var(--text-caption); box-shadow: var(--shadow-raised); }
.toast-success { background: var(--positive-soft); color: var(--positive); }
.toast-warning { background: var(--warning-soft); color: var(--warning); }
.toast-error { background: var(--negative-soft); color: var(--negative); }
.is-compact .module-learning-page .page-header { flex-direction: column; align-items: stretch; }
.is-compact .module-learning-page .header-actions .btn { flex: 1; }
.is-compact .module-learning-page :is(.learning-columns.has-labs) { grid-template-columns: minmax(0, 1fr); }
.is-compact .module-learning-page .module-nav { flex-direction: column; align-items: stretch; }
@media (prefers-reduced-motion: reduce) {
  .spinner { animation: none; }
}
</style>
