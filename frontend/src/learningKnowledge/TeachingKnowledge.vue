<template>
  <main v-if="managing" class="material-page">
    <header class="material-header">
      <div><h1>{{ user.userInfo?.role === 'admin' ? names.materialMaintenance : names.materials }}</h1><p>检查原文、段落和适用任务，再提交独立审阅与发布。这里只展示你有权管理的材料。</p></div>
      <div class="material-actions">
        <router-link :to="user.userInfo?.role === 'admin' ? '/admin/legal/kb' : '/teacher/knowledge'">返回{{ user.userInfo?.role === 'admin' ? names.foundation : names.knowledge }}</router-link>
        <button type="button" :disabled="busy" @click="resumeAndLoad">重新加载列表</button>
      </div>
    </header>
    <ContentAreaNav v-if="user.userInfo?.role === 'teacher'" />
    <!-- Native pickers may blur the window. Keep only these empty controls mounted;
         a new selection may resume, but never restores the previous target or form. -->
    <input ref="registerFileInput" class="material-file-input" type="file" accept=".json,application/json" aria-label="导入登记文件" @change="importFile($event, 'register')" />
    <input ref="revisionFileInput" class="material-file-input" type="file" accept=".json,application/json" aria-label="导入修订文件" @change="importFile($event, 'revise')" />
    <p class="material-notice">审阅与发布需要相应课程授权。请核实独立审阅人、当前版本、许可与发布范围；此处不提供学生预览。</p>
    <section v-if="paused" class="material-section" aria-live="polite">
      <h2>请重新加载材料</h2><p>为保护材料内容，未提交的表单已清空，请重新填写。</p>
      <p>操作中断后，请先重新加载核对结果，避免重复提交。</p>
      <button v-if="sessionChanged" type="button" @click="privacy.reload">登录状态已变化，刷新页面</button>
      <button v-else type="button" @click="resumeAndLoad">重新加载材料</button>
    </section>
    <p v-if="error" class="material-error" role="alert">{{ error }}</p>
    <p v-if="message" class="material-notice" role="status">{{ message }}</p>
    <p v-if="busy" role="status">正在加载，请稍候……</p>
    <p v-if="deletionState.message" class="material-notice" role="status">{{ deletionState.message }} <button v-if="deletionState.uncertain" @click="resumeAndLoad">重新加载</button></p>
    <MaterialDeleteDialog v-if="deletionState.target && !paused" :state="deletionState" @close="deletion.close" @confirm="deletion.confirm" @reload="resumeAndLoad" />
    <template v-if="!paused">
      <section class="material-section" aria-labelledby="material-list-title">
        <div class="material-list-heading">
          <h2 id="material-list-title">材料列表</h2>
          <button type="button" :disabled="busy" :aria-expanded="editorOpen" aria-controls="material-registration" @click="toggleEditor">{{ editorOpen ? '收起登记表单' : '登记材料' }}</button>
        </div>
        <p v-if="!materials.length && !busy">暂无可管理材料。登记或审阅新材料需要相应课程授权。</p>
        <ul class="material-list">
          <li v-for="row in materials" :key="row.material_id">
            <div><h3>{{ row.title }}</h3><p>{{ catalogName(row.catalog_version) }} · {{ classLabel(row.material_class) }} · 第 {{ row.revision }} 版 · {{ statusLabel(row.review_status) }}</p></div>
            <div class="material-actions"><button type="button" :disabled="busy || deletionState.busy" @click="inspect(row)">检查原文与段落</button><button type="button" :disabled="busy || deletionState.busy || deletionState.uncertain" @click="deletion.open(row)">删除材料</button></div>
          </li>
        </ul>
      </section>
      <section v-if="selectedId" class="material-section" aria-labelledby="inspection-title">
        <h2 id="inspection-title">原文与段落检查</h2>
        <form class="material-actions" @submit.prevent="inspectSelected">
          <label>材料版本（留空读取最新）<input v-model="revisionInput" type="number" min="1" step="1" :disabled="busy" /></label>
          <button type="submit" :disabled="busy">重新检查</button>
        </form>
        <template v-if="inspection">
          <MaterialInspection :inspection="inspection" :catalog-label="catalogName(selectedCatalog)" :task-names="taskNames" />
          <h3>审阅操作</h3>
          <p>批准必须由非所有者、非本次编写者的独立教师完成，并具备相应课程授权。</p>
          <p class="material-warning">撤回后将无法访问材料，受影响任务数见上方；操作后请重新加载核对状态。</p>
          <form class="material-review" @submit.prevent="runAction">
            <label>操作<select v-model="action" :disabled="busy"><option value="submit">提交审阅</option><option value="approve">独立批准</option><option value="publish">发布</option><option value="withdraw">撤回</option></select></label>
            <p>当前材料：第 {{ inspection.revision }} 版</p>
            <label>理由（必填，最多五百字）<textarea v-model="reason" required maxlength="500" rows="3" :disabled="busy" autocomplete="off" /></label>
            <button class="material-primary" type="submit" :disabled="busy || !reason.trim()">执行所选操作</button>
          </form>
        </template>
      </section>
      <section v-show="editorOpen" id="material-registration" class="material-section" aria-labelledby="material-form-title">
        <h2 id="material-form-title">登记材料 / 新修订</h2>
        <MaterialEditor :draft="draft" :mode="formMode" :busy="busy" :initial-step="editorInitialStep" :target-title="inspection?.title" :target-id="selectedId" :materials="materials" :target-catalog="catalogName(selectedCatalog)"
          :catalogs="catalogs" v-model:source-query="sourceQuery" :source-options="sourceOptions" :source-page="sourcePage"
          :source-previous="sourcePrevious" :source-next="sourceNext" :source-document="sourceDocument" :clause-options="clauses"
          @mode-change="changeMode" @save="saveMaterial" @source-type="changeSourceType" @source-search="loadSources" @source-select="selectSource"
          @choose-file="chooseFile" @download-template="downloadTemplate" @catalog-change="changeCatalog" @revision-target="chooseRevisionTarget" />
      </section>
    </template>
  </main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import MaterialDeleteDialog from '@/shared/knowledge/MaterialDeleteDialog.vue'
import { createMaterialDeletion, initialMaterialDeletion } from '@/shared/knowledge/materialDeletion.js'
import { names } from '@/shared/navigation/names'
import { useUserStore } from '@/store/user'
import { useRoute } from 'vue-router'
import ContentAreaNav from '@/shared/knowledge/ContentAreaNav.vue'
import { consumeTeachingTransfer, teachingIdentity } from '@/shared/knowledge/teachingTransfer.js'
import { staffKnowledgeApi as knowledgeApi } from '@/shared/knowledge/staffApi.js'
import { requestKey } from './requestGeneration.js'
import { usePrivatePage } from './usePrivatePage.js'
import { formatLocator } from './libraryController.js'
import { emptyMaterialDraft, importMaterialDraft, materialTemplate, materialPayload, reviewError, classLabel, statusLabel, sourceChoices, clauseChoices } from './materialEditor.js'
import { readMaterialCatalog, readMaterialTaskNames } from './materialEditorCatalog.js'
import MaterialEditor from './MaterialEditor.vue'
import MaterialInspection from './MaterialInspection.vue'

const user = useUserStore()
const route = useRoute()
const registerFileInput = ref(null)
const revisionFileInput = ref(null)
const managing = computed(() => ['teacher', 'admin'].includes(user.userInfo?.role))
const materials = ref([])
const inspection = ref(null)
const selectedId = ref('')
const selectedCatalog = ref('')
const revisionInput = ref('')
const action = ref('submit')
const reason = ref('')
const pendingAction = ref(null)
const formMode = ref('register')
const editorOpen = ref(false)
const editorInitialStep = ref(1)
const draft = ref(emptyMaterialDraft())
const catalogs = ref([])
const taskNames = ref([])
const sourceQuery = ref('')
const sourceOptions = ref([])
const clauses = ref([])
const sourceDocument = ref(null)
const sourcePage = ref(1)
const sourcePrevious = ref(false)
const sourceNext = ref(false)
const busy = ref(false)
const error = ref('')
const message = ref('')
const deletionState = reactive(initialMaterialDeletion())

function clearSources() {
  sourceOptions.value = []
  clauses.value = []
  sourceDocument.value = null
  sourcePrevious.value = false
  sourceNext.value = false
}
function resetDraft() {
  editorInitialStep.value = 1
  draft.value = emptyMaterialDraft()
  sourceQuery.value = ''
  sourcePage.value = 1
  clearSources()
}
function clearContent() {
  Object.assign(deletionState, initialMaterialDeletion())
  materials.value = []
  inspection.value = null
  selectedId.value = ''
  selectedCatalog.value = ''
  catalogs.value = []
  taskNames.value = []
  revisionInput.value = ''
  action.value = 'submit'
  reason.value = ''
  pendingAction.value = null
  formMode.value = 'register'
  editorOpen.value = false
  resetDraft()
  busy.value = false
  error.value = ''
  message.value = ''
}
const privacy = usePrivatePage(clearContent)
const { paused, sessionChanged } = privacy
const deletion = createMaterialDeletion({ state: deletionState, privacy, api: knowledgeApi, getRole: () => user.userInfo?.role,
  reload: async (ticket, id) => {
    inspection.value = null; selectedId.value = ''; selectedCatalog.value = ''; taskNames.value = []
    revisionInput.value = ''; pendingAction.value = null; reason.value = ''; resetDraft(); editorOpen.value = false
    const result = await knowledgeApi.materials(ticket.signal)
    if (!ticket.isCurrent()) return
    if (!Array.isArray(result.results) || result.results.some(row => row.material_id === id)) throw new Error('列表尚未更新')
    materials.value = result.results
  },
})
const catalogName = version => catalogs.value.find(item => item.value === version)?.label || '课程名称暂不可用'

function failure(err) {
  if ([401, 403, 404, 503].includes(err.response?.status)) clearContent()
  error.value = reviewError(err)
}
async function loadCatalogs(ticket) {
  const versions = [...new Set([undefined, ...materials.value.map(row => row.catalog_version)])]
  for (const version of versions) {
    if (!ticket.isCurrent()) return
    try {
      const option = await readMaterialCatalog(version, ticket.signal)
      if (ticket.isCurrent() && option && !catalogs.value.some(item => item.value === option.value)) catalogs.value.push(option)
    } catch (err) {
      // A readable catalog is not a CourseGrant. Its absence must not be guessed
      // from an internal version string or prevent review of authorized material.
      if (err.response?.status === 401) throw err
    }
  }
}
async function loadList() {
  if (!managing.value) return
  const ticket = privacy.begin()
  if (!ticket) return
  clearContent()
  busy.value = true
  try {
    const result = await knowledgeApi.materials(ticket.signal)
    if (!ticket.isCurrent()) return
    materials.value = result.results
    await loadCatalogs(ticket)
  } catch (err) { if (ticket.isCurrent()) failure(err) }
  finally { if (ticket.isCurrent()) busy.value = false; ticket.finish() }
}
function resumeAndLoad() { if (managing.value && privacy.resume()) return loadList() }
function toggleEditor() {
  if (!managing.value || busy.value || paused.value) return
  editorOpen.value = !editorOpen.value
}
function changeMode(mode) { if (!busy.value) { formMode.value = mode; resetDraft() } }
function changeCatalog(version) {
  if (busy.value || version === draft.value.catalog_version) return
  draft.value.catalog_version = version
  draft.value.task_ids = []
  message.value = '课程已更改，请重新导入该课程的适用任务。'
}
function chooseFile(mode) {
  if (!busy.value && !paused.value) (mode === 'revise' ? revisionFileInput.value : registerFileInput.value)?.click()
}
async function importFile(event, mode = formMode.value) {
  const file = event.target.files?.[0]
  event.target.value = '' // Never retain the local filename after import/clear.
  if (!file || busy.value || !managing.value) return
  if (file.size > 2 * 1024 * 1024) { error.value = '材料文件过大，请使用模板准备内容后重试。'; return }
  if (paused.value && !privacy.resume()) return
  const ticket = privacy.begin()
  if (!ticket) return
  busy.value = true
  error.value = ''
  message.value = ''
  let importedSuccessfully = false
  try {
    const text = await file.text()
    if (!ticket.isCurrent()) return
    const imported = importMaterialDraft(text, mode)
    resetDraft()
    formMode.value = mode
    draft.value = imported
    editorOpen.value = true
    importedSuccessfully = true
    message.value = '材料文件已导入，请检查完整内容；提交时仍需核验课程与任务权限。'
    if (mode === 'revise' && !materials.value.length) {
      const list = await knowledgeApi.materials(ticket.signal)
      if (!ticket.isCurrent()) return
      materials.value = list.results
      await loadCatalogs(ticket)
    }
    if (mode === 'register' && !catalogs.value.some(item => item.value === imported.catalog_version)) {
      try {
        const option = await readMaterialCatalog(imported.catalog_version, ticket.signal)
        if (ticket.isCurrent() && option) catalogs.value.push(option)
      } catch (err) { if (err.response?.status === 401) throw err }
    }
  } catch (err) {
    if (ticket.isCurrent()) {
      if (err.response) failure(err)
      else error.value = importedSuccessfully ? '文件已导入，但暂时无法读取课程或材料列表。重新加载后需再次导入。' : '材料文件无法导入，请检查所选表单类型、文件格式和必填内容。原表单未被替换。'
    }
  } finally { if (ticket.isCurrent()) busy.value = false; ticket.finish() }
}
function downloadTemplate() {
  if (!managing.value || busy.value) return
  const url = URL.createObjectURL(new Blob([materialTemplate(formMode.value)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = formMode.value === 'register' ? '材料登记模板.json' : '材料修订模板.json'
  link.click()
  URL.revokeObjectURL(url)
}
async function loadTaskNames(ticket, version) {
  taskNames.value = []
  if (!version) return
  try {
    const rows = await readMaterialTaskNames(version, ticket.signal)
    if (ticket.isCurrent()) taskNames.value = rows
  } catch (err) { if (err.response?.status === 401) throw err }
}

async function chooseRevisionTarget(id) {
  if (busy.value || formMode.value !== 'revise') return
  const row = materials.value.find(material => material.material_id === id)
  if (!row) return
  if (selectedCatalog.value && selectedCatalog.value !== row.catalog_version) draft.value.task_ids = []
  await inspect(row, row.revision, true)
}
async function inspect(row, revision = row.revision, preserveImportedDraft = false) {
  if (busy.value || !managing.value) return
  const ticket = privacy.begin()
  if (!ticket) return
  inspection.value = null
  taskNames.value = []
  if (!preserveImportedDraft) resetDraft()
  reason.value = ''
  pendingAction.value = null
  selectedId.value = row.material_id
  selectedCatalog.value = row.catalog_version || ''
  revisionInput.value = revision || ''
  error.value = ''
  message.value = ''
  busy.value = true
  try {
    const result = await knowledgeApi.inspect(row.material_id, revision, ticket.signal)
    if (!ticket.isCurrent()) return
    inspection.value = result
    await loadTaskNames(ticket, selectedCatalog.value)
  } catch (err) { if (ticket.isCurrent()) failure(err) }
  finally { if (ticket.isCurrent()) busy.value = false; ticket.finish() }
}
function inspectSelected() {
  const number = revisionInput.value === '' ? undefined : Number(revisionInput.value)
  if (number !== undefined && (!Number.isSafeInteger(number) || number < 1)) {
    error.value = '请选择有效的材料版本，或留空读取最新版本。'
    return
  }
  inspect({ material_id: selectedId.value, catalog_version: selectedCatalog.value }, number)
}
async function refreshAfterWrite(ticket, id, revision) {
  const [list, detail] = await Promise.all([
    knowledgeApi.materials(ticket.signal), knowledgeApi.inspect(id, revision, ticket.signal),
  ])
  if (!ticket.isCurrent()) return
  materials.value = list.results
  inspection.value = detail
  selectedId.value = id
  selectedCatalog.value = list.results.find(row => row.material_id === id)?.catalog_version || ''
  revisionInput.value = detail.revision
  await loadTaskNames(ticket, selectedCatalog.value)
}
async function runAction() {
  if (!managing.value || busy.value || !inspection.value || !reason.value.trim()) return
  const ticket = privacy.begin()
  if (!ticket) return
  const id = inspection.value.material_id
  const selectedAction = action.value
  const fields = { expected_revision: inspection.value.revision, reason: reason.value.trim() }
  const fingerprint = JSON.stringify([id, selectedAction, fields])
  if (pendingAction.value?.fingerprint !== fingerprint) {
    pendingAction.value = { fingerprint, body: { ...fields, idempotency_key: requestKey() } }
  }
  const body = { ...pendingAction.value.body }
  busy.value = true
  error.value = ''
  message.value = ''
  let confirmed = false
  try {
    await knowledgeApi.transition(id, selectedAction, body, ticket.signal)
    if (!ticket.isCurrent()) return
    confirmed = true
    pendingAction.value = null
    reason.value = ''
    inspection.value = null
    message.value = '操作已接受，正在重新核对状态。'
    await refreshAfterWrite(ticket, id, fields.expected_revision)
    if (ticket.isCurrent()) message.value = '操作已完成，材料列表与当前版本已更新。'
  } catch (err) {
    if (ticket.isCurrent()) {
      if (confirmed) inspection.value = null
      failure(err)
      if (confirmed) message.value = '操作已接受，但暂时无法核对最新状态；请重新加载，不要重复执行。'
    }
  } finally { if (ticket.isCurrent()) busy.value = false; ticket.finish() }
}
async function saveMaterial() {
  if (!managing.value || busy.value || (formMode.value === 'revise' && !selectedId.value)) return
  let body
  try { body = materialPayload(draft.value, formMode.value) } catch (err) { error.value = err.message; return }
  const ticket = privacy.begin()
  if (!ticket) return
  busy.value = true
  error.value = ''
  message.value = ''
  let confirmed = false
  try {
    const result = formMode.value === 'register'
      ? await knowledgeApi.register(body, ticket.signal)
      : await knowledgeApi.revise(selectedId.value, body, ticket.signal)
    if (!ticket.isCurrent()) return
    confirmed = true
    resetDraft()
    editorOpen.value = false
    reason.value = ''
    pendingAction.value = null
    inspection.value = null
    message.value = '材料已保存，正在读取段落。'
    await refreshAfterWrite(ticket, result.material_id, result.revision)
    if (ticket.isCurrent()) message.value = '材料已保存，请检查原文与段落，再提交审阅。'
  } catch (err) {
    if (ticket.isCurrent()) {
      failure(err)
      if (confirmed) message.value = '新版本已创建，但暂时无法读取；请重新加载列表，不要重复创建。'
    }
  } finally { if (ticket.isCurrent()) busy.value = false; ticket.finish() }
}
function changeSourceType(type) {
  if (busy.value) return
  draft.value.source_type = type
  draft.value.source_object_id = null
  draft.value.suppliedRegistrationFields = [...new Set([...(draft.value.suppliedRegistrationFields || []), 'source_type', 'source_object_id'])]
  sourceQuery.value = ''
  clearSources()
  if (type !== 'teacher_authored') loadSources(1)
}
async function loadSources(page = 1) {
  if (!managing.value || busy.value || formMode.value !== 'register' || draft.value.source_type === 'teacher_authored') return
  const ticket = privacy.begin()
  if (!ticket) return
  clearSources()
  sourcePage.value = page
  busy.value = true
  error.value = ''
  const type = draft.value.source_type === 'legal_clause' ? 'legal_document' : draft.value.source_type
  try {
    const result = await knowledgeApi.library({ group: type === 'legal_document' ? 'legal' : 'platform', source_type: type, q: sourceQuery.value, page }, ticket.signal)
    if (!ticket.isCurrent()) return
    sourceOptions.value = sourceChoices(result, type)
    sourcePrevious.value = Boolean(result.previous)
    sourceNext.value = Boolean(result.next)
  } catch (err) { if (ticket.isCurrent()) failure(err) }
  finally { if (ticket.isCurrent()) busy.value = false; ticket.finish() }
}
async function selectSource(id) {
  if (!managing.value || busy.value) return
  draft.value.source_object_id = null
  draft.value.suppliedRegistrationFields = [...new Set([...(draft.value.suppliedRegistrationFields || []), 'source_object_id'])]
  clauses.value = []
  sourceDocument.value = null
  if (!id || !sourceOptions.value.some(option => option.value === id)) return
  if (draft.value.source_type !== 'legal_clause') { draft.value.source_object_id = id; return }
  const ticket = privacy.begin()
  if (!ticket) return
  sourceDocument.value = id
  busy.value = true
  error.value = ''
  try {
    const detail = await knowledgeApi.libraryDetail('legal_document', id, ticket.signal)
    if (ticket.isCurrent()) clauses.value = clauseChoices(detail, formatLocator)
  } catch (err) { if (ticket.isCurrent()) failure(err) }
  finally { if (ticket.isCurrent()) busy.value = false; ticket.finish() }
}
onMounted(async () => {
  await resumeAndLoad()
  if (paused.value || sessionChanged.value) return
  const incoming = consumeTeachingTransfer(teachingIdentity(user.userInfo), 'material')
  if (incoming) {
    draft.value = emptyMaterialDraft()
    draft.value.material_class = incoming.materialClass
    Object.assign(draft.value.metadata, incoming.source, { source_snapshot: incoming.text })
    formMode.value = 'register'
    editorInitialStep.value = 2
    editorOpen.value = true
    message.value = `${incoming.excerpt ? '已读取段落以摘录形式加入材料草稿，不代表完整原文。' : '资料已加入材料草稿。'}请核对来源与许可，补齐课程、适用任务和教学安排后再提交审阅。`
    // Let the already queued Vue update reveal the form before scrolling to it.
    await Promise.resolve()
    document.getElementById('material-form-title')?.scrollIntoView({ block: 'start' })
  } else if (route.query.material) {
    const row = materials.value.find(item => String(item.material_id) === String(route.query.material))
    if (row) await inspect(row)
  }
})
</script>

<style scoped>
.material-file-input { display: none; }
.material-page { max-width: var(--page-width); margin: 0 auto; padding: var(--space-4) var(--page-gutter) var(--space-8); color: var(--ink); line-height: var(--leading-body); overflow-wrap: anywhere; }
h1 { font-size: var(--text-page); line-height: var(--leading-tight); margin: 0 0 var(--space-2); }
h2 { font-size: var(--text-section); margin: 0 0 var(--space-2); }
h3 { font-size: var(--text-card); margin: var(--space-2) 0; }
p { margin: var(--space-1) 0; }
.material-header, .material-actions, .material-list-heading { display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: end; }
.material-list-heading { justify-content: space-between; align-items: center; margin-bottom: var(--space-2); }
.material-list-heading h2 { margin: 0; }
.material-header { align-items: start; justify-content: space-between; margin-bottom: var(--space-3); }
.material-section { padding: var(--space-3) 0; border-top: var(--stroke) solid var(--line); }
.material-actions { margin: var(--space-2) 0; }
.material-list { list-style: none; padding: 0; margin: 0; }
.material-list li { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--space-2); border-bottom: var(--stroke) solid var(--line); padding: var(--space-2) 0; }
.material-list p { color: var(--ink-secondary); font-size: var(--text-caption); }
.material-review, label { display: grid; gap: var(--space-1); }
.material-review { gap: var(--space-2); margin-top: var(--space-2); }
input, textarea, select, button { font: inherit; color: var(--ink); background: var(--surface); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); padding: var(--space-1) var(--space-2); min-width: 0; max-width: 100%; min-height: var(--control-height); box-sizing: border-box; }
textarea { resize: vertical; }
button { cursor: pointer; width: fit-content; transition: background var(--motion-fast) var(--motion-ease); }
button:hover:not(:disabled) { background: var(--surface-hover); }
button:active:not(:disabled) { background: var(--action-soft); }
.material-primary { background: var(--action); color: var(--on-action); border-color: var(--action); }
.material-primary:hover:not(:disabled) { background: var(--action-hover); }
.material-primary:active:not(:disabled) { background: var(--action-pressed); }
:disabled { cursor: not-allowed; background: var(--disabled); color: var(--disabled-ink); }
a { color: var(--action); }
a:hover { color: var(--action-hover); }
:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.material-notice, .material-warning, .material-error { padding: var(--space-2); border-radius: var(--radius-control); }
.material-notice { background: var(--action-soft); }
.material-warning { background: var(--warning-soft); color: var(--warning); }
.material-error { background: var(--negative-soft); color: var(--negative); }
</style>
