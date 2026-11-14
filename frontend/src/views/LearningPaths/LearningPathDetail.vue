<template>
  <div class="path-detail-page">
    <header class="page-header">
      <button class="btn" @click="goBack"><icon-arrow-left aria-hidden="true" />返回{{ names.paths }}</button>
      <button class="btn" @click="loadPath" :disabled="pathLoading">刷新</button>
    </header>
    <div v-if="pathLoading" class="state-panel" role="status"><span class="spinner"></span>正在读取航线…</div>
    <div v-else-if="pathError" class="state-panel error" role="alert">{{ pathError }} <button class="btn" @click="loadPath">重新读取</button></div>
    <template v-else>
      <section class="join-panel">
        <div>
          <h1>{{ detail.title }}</h1><p>{{ detail.description }}</p>
          <dl class="facts"><div><dt>难度</dt><dd>{{ detail.difficultyLabel }}</dd></div><div><dt>章节</dt><dd>{{ detail.chapterKnown ? `${detail.chapterCount} 章` : '未提供' }}</dd></div><div><dt>实验</dt><dd>{{ detail.labCount === null ? '未提供' : `${detail.labCount} 个` }}</dd></div><div><dt>预计时长</dt><dd>{{ detail.hoursLabel }}</dd></div></dl>
        </div>
        <div class="join-actions">
          <p v-if="progressState === 'loading'">正在读取本人航线进度…</p>
          <template v-else-if="progressState === 'failed'"><p class="error" role="alert">{{ progressError }}</p><p>读取失败不代表尚未加入。</p><button class="btn" @click="loadProgress">重试进度</button></template>
          <button v-else-if="progressState === 'notJoined'" class="btn btn-primary" @click="startLearning" :disabled="starting" :aria-busy="starting">{{ starting ? '正在加入…' : '加入学习航线' }}</button>
          <p v-if="joinMessage" role="status">{{ joinMessage }}</p>
        </div>
      </section>
      <PathNextStep v-if="progressState === 'joined'" :step="currentChapter" @confirm="continueLearning" />
      <div class="detail-grid">
        <section class="modules-panel">
          <h2>章节目录</h2><p>进入章节不会自动开始学习；开始学习和标记完成由你在章节页操作。</p>
          <div v-if="modulesLoading" role="status">正在读取章节…</div>
          <div v-else-if="modulesError" class="error" role="alert">{{ modulesError }} <button class="btn" @click="loadModules">重试章节</button></div>
          <p v-else-if="!moduleList.length">本航线暂未提供章节。</p>
          <ol v-else class="module-list"><li v-for="module in moduleList" :key="module.id" class="module-main">
            <div><h3>{{ module.order }}. {{ module.title }} <span v-if="module.isCurrent" class="tag">当前章节</span></h3><p>{{ module.description }}</p><p>{{ module.typeLabel }} · {{ module.minutesLabel }} · {{ module.labLabel }}</p><p v-if="module.requires.length">先修：{{ module.requires.join('、') }}</p><p v-if="module.missingRequires">部分先修名称未读取，不以编号充当名称。</p></div>
            <button class="btn" :disabled="!module.to" @click="goToModule(module)">进入章节</button>
          </li></ol>
        </section>
        <aside class="summary-panel">
          <h2>本人航线进度</h2>
          <template v-if="progressState === 'joined'"><div v-if="progress.known" class="progress-circle"><progress max="100" :value="progress.percent"></progress><span class="progress-text">{{ progress.percent }}%</span></div><p>{{ progress.countLabel }}</p><p>开始时间：{{ progress.startedLabel }}</p><p>完成实验：{{ progress.labLabel }}</p><p v-if="progress.anomaly" class="error" role="alert">数据异常：后台记录进度为 {{ progress.rawPercent }}%</p></template>
          <p v-else>尚未读取到可确认的本人航线进度。</p>
          <h2>知识图谱</h2><button class="btn" @click="graphNoteVisible = true">查看完整图谱说明</button><p v-if="graphNoteVisible" role="status">完整航线图谱接口尚未提供，当前展示章节结构；本航线知识点、先修关系与掌握状态仍待接入。</p>
        </aside>
      </div>
    </template>
    <p v-if="message.visible" class="notice" role="status">{{ message.text }}</p>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { names } from '@/shared/navigation/names'
import { pathsApi } from '@/learning/paths/api.js'
import { pathDetailView, progressView, moduleViews, nextStepView, startResult, isNotFound, safeError } from '@/learning/paths/presentation.js'
import PathNextStep from '@/learning/paths/components/PathNextStep.vue'

const route = useRoute()
const router = useRouter()
const pathId = computed(() => route.params.id)
const pathLoading = ref(false), pathError = ref(''), pathNotFound = ref(false)
const path = ref(null), modules = ref([]), progressRecord = ref(null)
const modulesLoading = ref(false), modulesError = ref('')
const progressState = ref('loading'), progressError = ref('')
const starting = ref(false), joinMessage = ref(''), graphNoteVisible = ref(false)
const message = reactive({ visible: false, text: '' })
const detail = computed(() => pathDetailView(path.value))
const progress = computed(() => progressView(progressRecord.value))
const moduleList = computed(() => moduleViews(modules.value, { pathId: pathId.value, currentModuleId: progressRecord.value?.current_module }))
const currentChapter = computed(() => nextStepView(progressRecord.value, modules.value, pathId.value))
let pathGeneration = 0, moduleGeneration = 0, progressGeneration = 0

async function loadModules() {
  const generation = ++moduleGeneration, id = pathId.value
  modulesLoading.value = true
  modulesError.value = ''
  try {
    const result = await pathsApi.modules({ learning_path: id, top_level: 'true' })
    if (generation !== moduleGeneration || id !== pathId.value) return
    const rows = Array.isArray(result) ? result : result?.results
    if (!Array.isArray(rows)) throw Error('Incomplete modules')
    modules.value = rows
  } catch (error) {
    if (generation === moduleGeneration && id === pathId.value) { modules.value = []; modulesError.value = safeError(error, '章节暂时无法读取，请稍后重试。') }
  } finally { if (generation === moduleGeneration && id === pathId.value) modulesLoading.value = false }
}
async function loadProgress() {
  const generation = ++progressGeneration, id = pathId.value
  progressState.value = 'loading'
  progressError.value = ''
  progressRecord.value = null
  try {
    const result = await pathsApi.progress(id)
    if (generation !== progressGeneration || id !== pathId.value) return
    if (!result || String(result.learning_path) !== String(id)) throw Error('Unconfirmed progress')
    progressRecord.value = result
    progressState.value = 'joined'
  } catch (error) {
    if (generation !== progressGeneration || id !== pathId.value) return
    progressState.value = isNotFound(error) ? 'notJoined' : 'failed'
    progressError.value = isNotFound(error) ? '' : safeError(error, '本人进度暂时无法读取，请稍后重试。')
  }
}
async function loadPath() {
  const generation = ++pathGeneration, id = pathId.value
  pathLoading.value = true
  pathError.value = ''
  pathNotFound.value = false
  path.value = null
  modules.value = []
  joinMessage.value = ''
  const reads = [loadModules(), loadProgress()]
  try {
    const result = await pathsApi.detail(id)
    if (generation !== pathGeneration || id !== pathId.value) return
    if (!result || String(result.id) !== String(id)) throw Error('Unconfirmed path')
    path.value = result
  } catch (error) {
    if (generation === pathGeneration && id === pathId.value) { pathNotFound.value = isNotFound(error); pathError.value = isNotFound(error) ? '航线不存在或可能已下架，请返回列表重新选择。' : safeError(error, '航线暂时无法读取，请稍后重试。') }
  } finally {
    await Promise.allSettled(reads)
    if (generation === pathGeneration && id === pathId.value) pathLoading.value = false
  }
}
async function startLearning() {
  if (starting.value) return
  const id = pathId.value
  starting.value = true
  joinMessage.value = ''
  ++progressGeneration
  try {
    const result = startResult(await pathsApi.start(id), id)
    if (id !== pathId.value) return
    joinMessage.value = result.message
    if (result.ok) { progressRecord.value = result.record; progressState.value = 'joined'; progressError.value = '' }
  } catch (error) { if (id === pathId.value) joinMessage.value = safeError(error, '加入结果暂未确认，请重新读取本人进度后重试。') }
  finally { starting.value = false }
}
function continueLearning() {
  if (progressState.value === 'joined' && currentChapter.value.canEnter) return router.push(currentChapter.value.to)
  message.visible = true
  message.text = currentChapter.value.reason || '后台尚未返回当前章节；不按完成总数推测，请自行选择章节。'
}
function goToModule(module) { if (module.to) router.push(module.to) }
function goBack() { router.push('/learning-paths') }
watch(pathId, loadPath)
onMounted(loadPath)
</script>

<style scoped>
.path-detail-page { display: grid; gap: var(--space-3); padding: var(--page-gutter); color: var(--ink); }
.page-header, .module-main { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); }
.join-panel, .detail-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: var(--space-3); }
.join-panel, .modules-panel, .summary-panel, .state-panel { min-width: 0; padding: var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.join-actions { display: flex; flex-direction: column; justify-content: center; align-items: start; gap: var(--space-2); }
h1 { font-size: var(--text-page); } h2 { font-size: var(--text-section); } h3 { font-size: var(--text-card); }
p { color: var(--ink-secondary); line-height: var(--leading-body); overflow-wrap: anywhere; }
.facts { display: flex; flex-wrap: wrap; gap: var(--space-3); } dt { color: var(--ink-muted); } dd { margin: 0; }
.module-list { display: grid; gap: var(--space-2); padding: 0; list-style: none; } .module-main { padding: var(--space-2); border-bottom: var(--stroke) solid var(--line); } .module-main > div { min-width: 0; }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1); min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.btn-primary { background: var(--action); color: var(--on-action); border-color: var(--action); }
.btn:hover { border-color: var(--action); } .btn:active { background: var(--surface-hover); } .btn:disabled { color: var(--disabled-ink); background: var(--disabled); cursor: not-allowed; }
.btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.tag { font-size: var(--text-caption); color: var(--action); } .error { color: var(--negative); } .notice { padding: var(--space-2); background: var(--warning-soft); }
.progress-circle { position: relative; display: flex; align-items: center; min-height: var(--space-5); padding-right: var(--space-7); } .progress-circle .progress-text { position: absolute; right: 0; } progress { width: 100%; accent-color: var(--action); }
.spinner { display: inline-block; width: var(--icon-size); height: var(--icon-size); border: var(--stroke) solid var(--line); border-top-color: var(--action); border-radius: var(--radius-pill); animation: spin var(--motion-loop) linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }
.is-compact .path-detail-page :is(.join-panel, .detail-grid) { grid-template-columns: minmax(0, 1fr); }
.is-compact .path-detail-page .module-main { flex-wrap: wrap; }
.is-compact .path-detail-page .join-actions { flex-direction: column; }
@media (prefers-reduced-motion: reduce) { .spinner { animation: none; } }
</style>
