<template>
  <div class="path-detail-page">
    <div class="page-header">
      <button type="button" class="back-button" @click="goBack">
        <icon-arrow-left aria-hidden="true" /> 返回{{ names.paths }}
      </button>
      <div class="header-copy">
        <p class="eyebrow">航线详情</p>
        <div class="badge-row">
          <span class="badge">{{ detail.difficultyLabel }}</span>
          <span v-if="detail.category" class="badge">{{ detail.category }}</span>
          <span v-if="detail.published" class="badge badge-positive">已发布</span>
        </div>
        <h1>{{ detail.title }}</h1>
        <p v-if="detail.description" class="subtitle">{{ detail.description }}</p>
        <dl class="path-facts">
          <div><dt>章节</dt><dd>{{ detail.chapterKnown ? `${detail.chapterCount} 章` : '未提供' }}</dd></div>
          <div><dt>实验</dt><dd>{{ detail.labCount === null ? '未提供' : `${detail.labCount} 个` }}</dd></div>
          <div><dt>预计时长</dt><dd>{{ detail.hoursLabel }}</dd></div>
        </dl>
      </div>
    </div>

    <div v-if="pathLoading" class="state-box" aria-live="polite">
      <div class="spinner"></div>
      <p>正在读取航线…</p>
    </div>

    <div v-else-if="pathError" class="state-box state-error" role="alert">
      <icon-exclamation-circle aria-hidden="true" />
      <h2>{{ pathNotFound ? '航线不存在或未开放' : '航线暂时无法读取' }}</h2>
      <p>{{ pathError }}</p>
      <button type="button" class="btn btn-secondary" @click="loadPath">重新加载</button>
    </div>

    <template v-else>
      <section class="join-panel" aria-labelledby="join-heading">
        <div class="join-copy">
          <h2 id="join-heading">学习进度</h2>
          <template v-if="progressState === 'loading'">
            <p>正在读取本人进度…</p>
          </template>
          <template v-else-if="progressState === 'failed'">
            <p class="is-error" role="alert">{{ progressError }}</p>
            <p class="hint">读取失败不代表尚未加入；在确认之前不会重复加入。</p>
            <button type="button" class="btn btn-secondary" :disabled="progressReloading" @click="loadProgress">
              {{ progressReloading ? '正在重试…' : '重新读取进度' }}
            </button>
          </template>
          <template v-else-if="progressState === 'notJoined'">
            <p>你还没有加入这条航线。加入后才会记录开始日期与章节进度。</p>
            <div class="join-actions">
              <button type="button" class="btn btn-primary" :disabled="starting" :aria-busy="starting" @click="startLearning">
                {{ starting ? '正在加入…' : '加入并开始学习' }}
              </button>
              <span class="hint">加入使用原有加入动作；不会替你标记任何章节完成。</span>
            </div>
            <p v-if="joinMessage" class="is-error" role="alert">{{ joinMessage }}</p>
          </template>
          <template v-else>
            <div class="progress-line">
              <div class="progress-circle" role="progressbar" aria-label="航线学习进度" :aria-valuenow="progress.percent ?? 0" aria-valuemin="0" aria-valuemax="100">
                <svg viewBox="0 0 36 36" aria-hidden="true">
                  <path class="progress-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                  <path class="progress-fill" :stroke-dasharray="`${progress.percent ?? 0}, 100`" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                </svg>
                <span class="progress-text">{{ progress.percent === null ? '—' : `${progress.percent}%` }}</span>
              </div>
              <div class="progress-copy">
                <p>{{ progress.countLabel }}</p>
                <p class="hint">
                  开始于 {{ progress.startedLabel }} · 当前章节：
                  {{ nextStep.chapterKnown ? nextStep.chapterTitle : '后台尚未返回，请按章节列表顺序选择' }}
                </p>
                <p class="hint">已完成实验：{{ progress.labLabel }}</p>
                <p v-if="progress.anomaly" class="anomaly" role="status">
                  数据异常：后台记录进度为 {{ progress.rawPercent }}%，已超过 100%。界面不裁剪成正常满进度，请联系教师核对进度数据。
                </p>
              </div>
            </div>
          </template>
        </div>
        <PathNextStep v-if="progressState === 'joined'" :step="nextStep" :pending="entering" @confirm="continueLearning" />
      </section>

      <div class="detail-grid">
        <section class="modules-panel" aria-labelledby="modules-heading">
          <header class="panel-head">
            <h2 id="modules-heading">学习章节</h2>
            <p class="panel-note">按后台返回的章节顺序排列；本页不据完成总数推测已完成或已解锁章节。</p>
          </header>

          <div v-if="modulesLoading" class="state-inline" aria-live="polite">
            <div class="spinner small"></div>
            <p>正在读取章节…</p>
          </div>
          <div v-else-if="modulesError" class="state-inline is-error" role="alert">
            <p>{{ modulesError }}</p>
            <button type="button" class="btn btn-secondary" @click="loadModules">重试</button>
          </div>
          <div v-else-if="!moduleList.length" class="state-inline">
            <p>这条航线暂未提供章节内容。</p>
          </div>
          <ol v-else class="module-list">
            <li v-for="module in moduleList" :key="module.id" class="module-row">
              <button type="button" class="module-main" :disabled="!module.to" @click="goToModule(module)">
                <span class="module-order" aria-hidden="true">{{ module.order }}</span>
                <span class="module-copy">
                  <span class="module-tags">
                    <span class="tag">{{ module.typeLabel }}</span>
                    <span v-if="module.required" class="tag">必修</span>
                    <span v-if="module.isCurrent" class="tag tag-current">当前章节</span>
                  </span>
                  <strong class="module-title">{{ module.title }}</strong>
                  <span v-if="module.description" class="module-description">{{ module.description }}</span>
                  <span class="module-meta">
                    <span>{{ module.minutesLabel }}</span>
                    <span>{{ module.labLabel }}</span>
                  </span>
                  <span v-if="module.requires.length" class="module-requires">先修：{{ module.requires.join('、') }}</span>
                  <span v-else-if="module.missingRequires" class="module-requires">
                    有 {{ module.missingRequires }} 项先修未能从章节目录读取名称；不以编号充当名称。
                  </span>
                </span>
                <icon-right class="module-arrow" aria-hidden="true" />
              </button>
            </li>
          </ol>
          <p class="panel-note">进入章节不会自动开始学习；请在章节页明确点击“开始学习”。</p>
        </section>

        <aside class="side-panel">
          <section class="side-card" aria-labelledby="stats-heading">
            <h2 id="stats-heading">学习统计</h2>
            <dl class="stats-list">
              <div><dt>开始时间</dt><dd>{{ progressState === 'joined' ? progress.startedLabel : '未加入或待读取' }}</dd></div>
              <div><dt>完成实验</dt><dd>{{ progressState === 'joined' ? progress.labLabel : '待读取' }}</dd></div>
              <div><dt>学习时长</dt><dd>接口未提供</dd></div>
            </dl>
            <p class="panel-note">学习时长字段不在现有进度接口中，显示“接口未提供”而不补造数值。</p>
          </section>

          <section class="side-card" aria-labelledby="graph-heading">
            <h2 id="graph-heading">航线知识点</h2>
            <p class="panel-note">航线节点与连线数据尚未提供；不以全部知识概念或固定条数冒充本航线图谱。</p>
            <button type="button" class="btn btn-secondary" @click="graphNoteVisible = true">查看完整图谱</button>
            <p v-if="graphNoteVisible" class="graph-note" role="status">
              完整航线图谱接口尚未提供，当前无法渲染。原入口保留，待接口就绪后再接入。
            </p>
          </section>
        </aside>
      </div>
    </template>

    <div v-if="message.visible" class="toast" :class="`toast-${message.type}`" role="status">
      <icon-check-circle v-if="message.type === 'success'" aria-hidden="true" />
      <icon-exclamation-circle v-else aria-hidden="true" />
      <span>{{ message.text }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { names } from '@/shared/navigation/names'
import { pathsApi } from '@/learning/paths/api.js'
import PathNextStep from '@/learning/paths/components/PathNextStep.vue'
import {
  isNotFound, moduleViews, nextStepView, pathDetailView, progressStateOf, progressView,
  safeError, startResult,
} from '@/learning/paths/presentation.js'

const route = useRoute()
const router = useRouter()
const pathId = computed(() => route.params.id)

const pathLoading = ref(true)
const pathError = ref('')
const pathNotFound = ref(false)
const path = ref({})
const detail = computed(() => pathDetailView(path.value))

const modulesLoading = ref(false)
const modulesError = ref('')
const modules = ref([])
const moduleList = computed(() => moduleViews(modules.value, { currentModuleId: record.value?.current_module, pathId: pathId.value, catalog: modules.value }))

const progressState = ref('loading')
const progressError = ref('')
const progressReloading = ref(false)
const record = ref(null)
const progress = computed(() => progressView(record.value))
const nextStep = computed(() => nextStepView(record.value, modules.value, pathId.value))
const currentChapter = nextStep

const starting = ref(false)
const entering = ref(false)
const joinMessage = ref('')
const graphNoteVisible = ref(false)
const message = reactive({ visible: false, type: 'info', text: '' })
let messageTimer = null

function showMessage(type, text) {
  message.visible = true
  message.type = type
  message.text = text
  clearTimeout(messageTimer)
  messageTimer = setTimeout(() => { message.visible = false }, 3200)
}

let loadVersion = 0

async function loadPath() {
  const version = ++loadVersion
  pathLoading.value = true
  pathError.value = ''
  pathNotFound.value = false
  // 切换航线时先清掉上一航线的章节与进度，避免旧数据短暂冒充新航线。
  record.value = null
  modules.value = []
  progressState.value = 'loading'
  try {
    const payload = await pathsApi.detail(pathId.value)
    if (version !== loadVersion) return
    path.value = payload
  } catch (failure) {
    if (version !== loadVersion) return
    pathNotFound.value = isNotFound(failure)
    pathError.value = pathNotFound.value
      ? '这条航线可能已下架，或链接有误。请返回航线列表重新选择。'
      : safeError(failure, '航线暂时未能读取，请稍后重试。')
    pathLoading.value = false
    return
  }
  pathLoading.value = false
  await Promise.all([loadProgress(version), loadModules(version)])
}

async function loadProgress(version = loadVersion) {
  if (!record.value) progressState.value = 'loading'
  else progressReloading.value = true
  progressError.value = ''
  let result
  try {
    const value = await pathsApi.progress(pathId.value)
    result = { status: 'fulfilled', value }
  } catch (reason) {
    result = { status: 'rejected', reason }
  }
  if (version !== loadVersion) return
  const state = progressStateOf(result)
  if (state === 'joined') {
    record.value = result.value
    progressState.value = 'joined'
  } else if (state === 'notJoined') {
    record.value = null
    progressState.value = 'notJoined'
  } else {
    progressError.value = safeError(result.reason, '本人进度暂时未能读取，请稍后重试。')
    progressState.value = 'failed'
  }
  progressReloading.value = false
}

async function loadModules(version = loadVersion) {
  modulesLoading.value = true
  modulesError.value = ''
  try {
    const payload = await pathsApi.modules({ learning_path: pathId.value })
    if (version !== loadVersion) return
    modules.value = payload
  } catch (failure) {
    if (version !== loadVersion) return
    modulesError.value = safeError(failure, '章节暂时未能读取，请稍后重试。')
    modules.value = []
  } finally {
    if (version === loadVersion) modulesLoading.value = false
  }
}

async function startLearning() {
  if (starting.value) return
  starting.value = true
  joinMessage.value = ''
  try {
    const payload = await pathsApi.start(pathId.value)
    const result = startResult(payload, pathId.value)
    if (!result.ok) {
      joinMessage.value = result.message
      return
    }
    record.value = result.record
    progressState.value = 'joined'
    showMessage('success', result.message)
  } catch (failure) {
    joinMessage.value = safeError(failure, '未能确认已加入学习航线。请重新加载进度后再试。')
  } finally {
    starting.value = false
  }
}

async function continueLearning() {
  if (!record.value) return
  const chapter = currentChapter.value
  // 只有后端记录且可核对的当前章节才进入；否则留在本页并说明，不按完成总数推测。
  if (chapter.chapterKnown && chapter.canEnter && chapter.to) {
    entering.value = true
    try {
      await router.push(chapter.to)
    } finally {
      entering.value = false
    }
    return
  }
  showMessage('warning', chapter.reason || '当前章节尚未读取，请稍后重试。')
}

function goToModule(module) {
  if (!module?.to) return
  router.push(module.to)
}

function goBack() {
  router.push('/learning-paths')
}

// 同一路由记录内切换 :id 时组件会被复用；按新航线重新读取，不沿用上一条航线的进度。
watch(pathId, (next, previous) => {
  if (next !== previous) loadPath()
})

onMounted(loadPath)
</script>

<style scoped>
.path-detail-page { display: grid; gap: var(--space-3); width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: var(--space-4) auto var(--space-8); }
.page-header { display: grid; gap: var(--space-2); }
.back-button { justify-self: start; display: inline-flex; align-items: center; gap: var(--space-1); min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink-secondary); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.back-button:hover { border-color: var(--line-strong); color: var(--action); }
.header-copy { display: grid; gap: var(--space-1); }
.eyebrow { margin: 0; color: var(--action); font-size: var(--text-caption); font-weight: var(--weight-medium); }
.badge-row { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.badge { padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); color: var(--ink-secondary); font-size: var(--text-caption); }
.badge-positive { border-color: var(--positive); color: var(--positive); }
h1 { margin: 0; font-size: var(--text-page); line-height: var(--leading-tight); overflow-wrap: anywhere; }
.subtitle { margin: 0; color: var(--ink-secondary); }
.path-facts { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-3); margin: 0; }
.path-facts div { display: flex; gap: var(--space-1); font-size: var(--text-caption); }
.path-facts dt { color: var(--ink-muted); }
.path-facts dd { margin: 0; color: var(--ink-secondary); }
.join-panel { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(var(--panel-width), .8fr); align-items: start; gap: var(--space-2); padding: var(--space-3); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-panel); background: var(--surface); }
.join-copy { display: grid; gap: var(--space-1); min-width: 0; }
.join-copy h2 { margin: 0; font-size: var(--text-section); }
.join-copy p { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.7; }
.join-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1) var(--space-2); margin-top: var(--space-1); }
.hint { color: var(--ink-muted); font-size: var(--text-caption); }
.is-error { padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--negative-soft); color: var(--negative); }
.progress-line { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); margin-top: var(--space-1); }
.progress-circle { position: relative; width: var(--space-10); height: var(--space-10); flex-shrink: 0; }
.progress-circle svg { width: 100%; height: 100%; }
.progress-circle .progress-bg { fill: none; stroke: var(--line); stroke-width: 3; }
.progress-circle .progress-fill { fill: none; stroke: var(--action); stroke-width: 3; stroke-linecap: round; transition: stroke-dasharray var(--motion-normal) var(--motion-ease); }
.progress-circle .progress-text { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: var(--text-caption); font-weight: var(--weight-strong); }
.progress-copy { display: grid; gap: calc(var(--space-1) / 2); min-width: 0; }
.anomaly { padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--warning-soft); color: var(--warning); }
.detail-grid { display: grid; grid-template-columns: minmax(0, 1fr) var(--menu-width); align-items: start; gap: var(--space-2); }
.modules-panel, .side-card { display: grid; gap: var(--space-2); min-width: 0; padding: var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.panel-head { display: grid; gap: var(--space-1); }
.panel-head h2, .side-card h2 { margin: 0; font-size: var(--text-card); }
.panel-note { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); line-height: 1.6; }
.module-list { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.module-row { min-width: 0; }
.module-main { display: flex; align-items: flex-start; gap: var(--space-2); width: 100%; padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; text-align: left; cursor: pointer; }
.module-main:hover:not(:disabled) { border-color: var(--action); background: var(--action-soft); }
.module-main:disabled { cursor: not-allowed; color: var(--ink-muted); }
.module-order { display: grid; place-items: center; width: var(--control-height); height: var(--control-height); flex-shrink: 0; border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-weight: var(--weight-strong); }
.module-copy { display: grid; gap: calc(var(--space-1) / 2); min-width: 0; flex: 1; }
.module-tags { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.tag { padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); color: var(--ink-muted); font-size: var(--text-caption); }
.tag-current { border-color: var(--action); color: var(--action); }
.module-title { font-size: var(--text-caption); overflow-wrap: anywhere; }
.module-description { color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.6; overflow-wrap: anywhere; }
.module-meta { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-2); color: var(--ink-muted); font-size: var(--text-caption); }
.module-requires { color: var(--ink-secondary); font-size: var(--text-caption); overflow-wrap: anywhere; }
.module-arrow { flex-shrink: 0; color: var(--ink-muted); }
.side-panel { display: grid; gap: var(--space-2); }
.stats-list { display: grid; gap: var(--space-1); margin: 0; }
.stats-list div { display: flex; justify-content: space-between; gap: var(--space-2); font-size: var(--text-caption); }
.stats-list dt { color: var(--ink-muted); }
.stats-list dd { margin: 0; color: var(--ink-secondary); text-align: right; overflow-wrap: anywhere; }
.graph-note { margin: var(--space-1) 0 0; padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1); min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn-success:disabled { border-color: var(--positive); background: var(--positive-soft); color: var(--positive); }
.btn:hover:not(:disabled) { border-color: var(--action); color: var(--action); }
.btn-primary:hover:not(:disabled) { background: var(--action-hover); border-color: var(--action-hover); color: var(--on-action); }
.btn:active:not(:disabled) { background: var(--surface-muted); }
.btn-primary:active:not(:disabled) { background: var(--action-pressed); border-color: var(--action-pressed); }
.btn:disabled { border-color: var(--line); background: var(--surface-muted); color: var(--ink-muted); cursor: not-allowed; }
.btn:focus-visible, .back-button:focus-visible, .module-main:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.state-box { display: grid; justify-items: center; gap: var(--space-1); padding: var(--space-6) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); text-align: center; color: var(--ink-secondary); }
.state-box p { margin: 0; }
.state-error { border-color: var(--negative); background: var(--negative-soft); color: var(--negative); }
.state-inline { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1) var(--space-2); color: var(--ink-secondary); font-size: var(--text-caption); }
.state-inline p { margin: 0; }
.state-inline.is-error { padding: var(--space-2); border-radius: var(--radius-control); background: var(--negative-soft); color: var(--negative); }
.spinner { width: var(--control-height); height: var(--control-height); border: var(--focus-width) solid var(--line); border-top-color: var(--action); border-radius: var(--radius-pill); animation: spin calc(var(--motion-slow) * 4) linear infinite; }
.spinner.small { width: var(--space-3); height: var(--space-3); }
@keyframes spin { to { transform: rotate(360deg); } }
.toast { position: fixed; top: calc(var(--header-height) + var(--space-2)); left: 50%; transform: translateX(-50%); z-index: var(--z-overlay); display: flex; align-items: center; gap: var(--space-1); max-width: calc(100% - var(--page-gutter) * 2); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font-size: var(--text-caption); box-shadow: var(--shadow-raised); }
.toast-success { background: var(--positive-soft); color: var(--positive); }
.toast-warning { background: var(--warning-soft); color: var(--warning); }
.toast-error { background: var(--negative-soft); color: var(--negative); }
.is-compact .path-detail-page :is(.join-panel, .detail-grid) { grid-template-columns: minmax(0, 1fr); }
.is-compact .path-detail-page :is(.join-panel, .modules-panel, .side-card) { padding: var(--space-2); }
.is-compact .path-detail-page .module-main { flex-wrap: wrap; }
.is-compact .path-detail-page .join-actions { flex-direction: column; align-items: stretch; }
@media (prefers-reduced-motion: reduce) {
  .spinner { animation: none; }
  .progress-circle .progress-fill { transition: none; }
}
</style>
