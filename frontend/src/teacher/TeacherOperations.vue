<template>
  <section class="operations">
    <h1>教学布置与协作</h1><p>正式教学待办 · 当前授权范围</p>
    <p>协作记录不代替评阅、抽查与争议处理。处理后须由实际新场景、无提示复测验证，不提供“标记已改善”。</p>
    <button :disabled="busy" @click="run(refresh)">刷新待办</button>
    <button :disabled="busy" @click="run(sync)">同步源队列</button>
    <button :disabled="busy" @click="run(receive)">接收更正并重算</button>
    <p v-if="message" role="status">{{ message }}</p>
    <form @submit.prevent="run(create)">
      <label>建立协作待办
        <span class="inline-picker">
          <select v-model="createStudent" :disabled="busy">
            <option value="">选择学生</option>
            <option v-for="student in students" :key="student.id" :value="String(student.id)">{{ student.username }}</option>
          </select>
          <select v-model="attemptId" :disabled="busy" required>
            <option value="">选择该学生的练习记录</option>
            <option v-for="attempt in studentAttempts" :key="attempt.attempt_id" :value="attempt.attempt_id">
              {{ attempt.task_title }} · {{ attempt.status_label }} · {{ attempt.claimed_at }}
            </option>
          </select>
        </span>
      </label>
      <button :disabled="busy || !attemptId">建立协作待办</button>
    </form>
    <section v-for="(items, kind) in groups" :key="kind">
      <h3>{{ kinds[kind] || '其他待办' }}</h3><p v-if="!items.length">暂无待办。</p>
      <article v-for="item in items" :key="item.todo_id">
        <p>学生 {{ studentName(item.student_id) }} · 负责人 {{ ownerName(item.owner_id) }} · {{ states[item.status] || '状态待确认' }} · 第 {{ item.revision }} 版</p>
        <p>练习：{{ attemptLabel(item.attempt_id) }} · 原结果：{{ item.original_result_id ? '已关联原结果' : '暂无' }}</p>
        <p>源队列当前状态：{{ sourceStates[item.source_current_status] || (item.source_current_status ? '状态待确认' : '手工待办，无源队列') }}</p>
        <p>{{ item.summary }}</p>
        <button v-if="!item.owner_id" :disabled="busy" @click="run(() => change(item, 'claim'))">认领</button>
        <template v-else-if="canEdit(item)">
          <label>处理摘要 / 转交原因<input v-model.trim="draft(item).summary" maxlength="1000" :disabled="busy" /></label>
          <button :disabled="busy || !draft(item).summary.trim()" @click="run(() => change(item, 'handle'))">记录处理</button>
          <fieldset class="transfer-import" :disabled="busy">
            <ReferenceImport title="接手负责人" :fields="assigneeFields" :model-value="{ assignee_id: draft(item).assigneeId }" @update:model-value="importAssignee(item, $event)" />
          </fieldset>
          <p>{{ draft(item).assigneeId ? '已导入待核对负责人 · 1 人' : '尚未导入接手负责人' }}。当前接口未提供授权教师姓名目录；请用原关联文件导入实际负责人，接手资格由服务端核验，不根据同名或既有负责人猜测。</p>
          <button :disabled="busy || !draft(item).assigneeId || !draft(item).summary.trim()" @click="run(() => resolveTransfer(item))">转交</button>
          <label>复测记录
            <select v-model="draft(item).retest" :disabled="busy">
              <option value="">不关联复测记录（沿用原记录）</option>
              <option v-for="retest in retestsFor(item)" :key="retest.assignment_id" :value="retest.assignment_id">
                {{ retest.task_title }} · {{ retest.status_label }} · {{ retest.due_at }}
              </option>
            </select>
          </label>
          <button :disabled="busy" @click="run(() => change(item, 'verify'))">核对实际复测</button>
        </template>
        <p v-else>仅负责人可处理、转交和核对复测。</p>
        <details>
          <summary>源快照、复测证据和操作审计</summary>
          <p class="muted">原始记录用于核查，不在界面展开技术字段；如需逐项核对，请打开对应练习与复测记录。操作审计共 {{ item.actions?.length || 0 }} 条，保留在服务端。</p>
          <ul v-if="item.actions?.length">
            <li v-for="action in item.actions" :key="action.revision">{{ actionAction(action.action) }} · {{ formatDate(action.created_at) }}{{ action.summary ? ` · ${action.summary}` : '' }}</li>
          </ul>
        </details>
      </article>
    </section>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import evaluation from './insights/api.js'
import { useUserStore } from '@/store/user'
import ReferenceImport from '@/shared/forms/ReferenceImport.vue'

const user = useUserStore()
let generation = 0, dead = false
const account = computed(() => user.userInfo?.role === 'teacher' && user.userInfo?.id ? `teacher:${user.userInfo.id}` : null)
const current = token => !dead && Boolean(account.value) && token === generation
const groups = ref({})
const drafts = reactive({})
const busy = ref(false)
const needsRefresh = ref(false)
const message = ref('')
const attemptId = ref('')
const createStudent = ref('')
const students = ref([])
const attempts = ref([])
const retests = ref([])
const ownerNames = ref({})
const assigneeFields = [{ key: 'assignee_id', label: '接手负责人', type: 'number' }]
const kinds = { help: '主动求助', manual_review: '开放题必评', sampling: '常规抽查', dispute: '争议复核', evidence: '证据异常' }
const states = { unclaimed: '未认领', in_progress: '处理中', pending_verification: '待验证', verified: '复测已验证' }
const sourceStates = { pending: '待认领', open: '开放', claimed: '处理中', completed: '已完成', needs_correction: '需更正', submitted: '已提交', under_review: '复核中', reviewed: '已评阅', resolved: '已解决', helped: '已协助' }
const actionLabels = {
  claim: '认领', handle: '记录处理', transfer: '转交', verify: '核对复测', correction_reopened: '更正后重开',
  create: '建立待办', sync: '同步', receive: '接收更正',
}
function draft(item) {
  return drafts[item.todo_id] || (drafts[item.todo_id] = { summary: '', assigneeId: '', retest: item.retest_id || '' })
}
function studentName(id) {
  return students.value.find(item => String(item.id) === String(id))?.username || '学生姓名暂不可用'
}
function ownerName(id) {
  if (!id) return '未认领'
  return ownerNames.value[String(id)] || '负责人姓名暂不可用'
}
function attemptLabel(id) {
  const attempt = attempts.value.find(item => item.attempt_id === id)
  return attempt ? `${attempt.task_title} · ${attempt.student_name}` : '练习记录暂不可用'
}
function retestsFor(item) {
  return retests.value.filter(retest => String(retest.student_id) === String(item.student_id) && String(retest.original_attempt_id) === String(item.attempt_id))
}
function actionAction(value) { return actionLabels[value] || '处理动作' }
function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN') : '时间待确认' }
const studentAttempts = computed(() => attempts.value.filter(item => String(item.student_id) === String(createStudent.value)))
const todoRows = () => Object.values(groups.value).flat()
const canEdit = item => Boolean(account.value) && String(item.owner_id) === String(user.userInfo?.id)
function latestTodo(item) {
  const latest = todoRows().find(row => row.todo_id === item.todo_id)
  if (!latest || latest.revision !== item.revision) throw { response: { status: 409 } }
  return latest
}
async function load() {
  const token = generation
  const response = await evaluation.todos()
  if (!current(token)) return
  if (!response?.groups || typeof response.groups !== 'object' || Array.isArray(response.groups) || Object.values(response.groups).some(items => !Array.isArray(items) || items.some(item => !item?.todo_id || !item.attempt_id || !item.student_id || !Number.isInteger(item.revision)))) throw new Error('Invalid todo readback')
  groups.value = response.groups; needsRefresh.value = false
  const names = {}
  for (const group of Object.values(groups.value || {})) {
    for (const todo of group || []) {
      if (todo.owner_id && todo.owner_name) names[String(todo.owner_id)] = todo.owner_name
    }
  }
  ownerNames.value = names
}
async function loadOptions() {
  const token = generation
  try {
    const [report, retestResult] = await Promise.all([
      evaluation.students(),
      evaluation.retests(),
    ])
    if (!current(token)) return
    if (!Array.isArray(report) || !Array.isArray(retestResult?.items)) throw new Error('Invalid options')
    students.value = report.filter(item => item?.id && (!item.role || item.role === 'student')).map(item => ({ id: item.id, username: item.username || '学生名称暂不可用' }))
    retests.value = retestResult.items.map(item => ({
      assignment_id: item.assignment_id,
      student_id: item.student?.id,
      original_attempt_id: item.original_attempt_id,
      task_title: item.task?.title || item.original_task_title || '复测任务',
      status_label: item.status_label,
      due_at: item.due_at ? new Date(item.due_at).toLocaleString('zh-CN') : '未定',
    }))
    const loaded = await loadAttempts()
    if (current(token)) attempts.value = loaded
  } catch {
    if (!current(token)) return
    message.value = '待办选项未能全部读取，请重新读取；未补造练习或复测记录。'
    students.value = []
    retests.value = []; attempts.value = []
  }
}
async function loadAttempts() {
  const token = generation
  const items = []
  for (const student of [...students.value]) {
    if (!current(token)) return []
    try {
      const payload = await evaluation.learning({ mode: 'formal', student_id: student.id, limit: 100 })
      if (!current(token)) return []
      if (payload?.source !== 'formal' || !Array.isArray(payload.rows) || payload.rows.some(row => !row?.attempt_id || row.source !== 'formal' || String(row.student_id) !== String(student.id))) throw new Error('Wrong attempt scope')
      for (const row of payload.rows) {
        items.push({
          attempt_id: row.attempt_id,
          student_id: student.id,
          student_name: student.username,
          task_title: row.task_title,
          status_label: row.attempt_status === 'submitted' ? '已提交' : '进行中',
          claimed_at: row.claimed_at ? new Date(row.claimed_at).toLocaleString('zh-CN') : '时间待确认',
        })
      }
    } catch {
      if (current(token)) message.value = '部分学生的练习记录未能读取；可以刷新重试，不以空记录代替读取成功。'
    }
  }
  return items
}
async function refresh() { const token = generation; await load(); if (current(token)) await loadOptions() }
async function persist(work, confirm, token) {
  if (!current(token) || needsRefresh.value) return null
  let response
  try { response = await work() } catch (error) {
    if (current(token) && ![400, 401, 403, 404, 409, 422].includes(error.response?.status)) needsRefresh.value = true
    throw error
  }
  if (!current(token)) return null
  if (!confirm(response)) {
    needsRefresh.value = true
    message.value = '未能确认写入结果；请先刷新待办核对，不要重复提交。'
    return null
  }
  return response
}
async function readAfterWrite(token, expected) {
  try {
    await load()
    if (!current(token)) return false
    if (expected && !todoRows().some(row => row.todo_id === expected.todo_id && row.revision >= expected.revision && row.attempt_id === expected.attempt_id && String(row.student_id) === String(expected.student_id))) throw new Error('Write not in readback')
    return true
  } catch {
    if (current(token)) {
      needsRefresh.value = true
      message.value = '写入已确认，但最新待办未能读回；请刷新，不要重复提交。'
    }
    return false
  }
}
async function sync() {
  const token = generation
  const response = await persist(() => evaluation.syncTodos(), value => Array.isArray(value?.todo_ids), token)
  if (response && await readAfterWrite(token)) message.value = '源队列已同步，最新待办已读回；不代表源任务已处理。'
}
async function receive() {
  const token = generation
  const response = await persist(() => evaluation.consumeReceipts(), value => Array.isArray(value?.receipts), token)
  if (response && await readAfterWrite(token)) message.value = `已读取 ${response.receipts.length} 条处理回执并读回待办；未改写源成绩。`
}
async function create() {
  const id = attemptId.value
  const selected = studentAttempts.value.find(item => item.attempt_id === id)
  if (!selected) throw new Error('Invalid attempt')
  const token = generation
  const response = await persist(() => evaluation.createTodo({ attempt_id: id }), value => Boolean(value?.todo_id) && Number.isInteger(value.revision) && value.attempt_id === id && String(value.student_id) === String(selected.student_id), token)
  if (!response) return
  if (await readAfterWrite(token, response)) {
    if (attemptId.value === id) attemptId.value = ''
    message.value = '协作待办已建立，记录已读回；不代表问题已改善。'
  }
}
function importAssignee(item, values) {
  if (busy.value || !canEdit(item) || !todoRows().includes(item)) return
  draft(item).assigneeId = values.assignee_id
}
async function resolveTransfer(item) {
  const id = draft(item).assigneeId
  if (!/^[1-9]\d*$/.test(String(id)) || !Number.isSafeInteger(Number(id))) {
    message.value = '请导入并核对有效接手负责人关联；未根据姓名猜测负责人。'
    return
  }
  await change(item, 'transfer', { assignee_id: Number(id) })
}
async function change(item, action, extra = {}) {
  item = latestTodo(item)
  if (action === 'claim' ? Boolean(item.owner_id) : !canEdit(item)) throw { response: { status: 403 } }
  const token = generation, edit = draft(item)
  if (['handle', 'transfer'].includes(action) && !edit.summary.trim()) throw new Error('Summary required')
  if (action === 'verify' && edit.retest && !retestsFor(item).some(row => row.assignment_id === edit.retest)) throw new Error('Wrong retest binding')
  const response = await persist(() => evaluation.changeTodo(item.todo_id, { revision: item.revision, action,
    ...(action === 'handle' || action === 'transfer' ? { summary: edit.summary } : {}),
    ...(action === 'transfer' ? { assignee_id: extra.assignee_id } : {}),
    ...(action === 'verify' && edit.retest ? { retest_id: edit.retest } : {}),
  }), value => value?.todo_id === item.todo_id && value.revision === item.revision + 1 && value.attempt_id === item.attempt_id && String(value.student_id) === String(item.student_id), token)
  if (!response || !await readAfterWrite(token, response)) return
  delete drafts[item.todo_id]
  const latest = todoRows().find(row => row.todo_id === item.todo_id)
  message.value = action === 'verify' ? latest.status === 'verified' && latest.proof?.verified === true ? '实际复测已由服务端核对通过，记录已读回。' : '核对记录已读回；复测证据不足，仍待验证，不计为改善。' : '操作已保存，最新待办已读回。'
}
async function run(work) {
  if (busy.value || !account.value || dead) return
  if (needsRefresh.value && work !== refresh) { message.value = '请先刷新待办核对上次写入，不要重复提交。'; return }
  const token = generation
  busy.value = true
  message.value = ''
  try { await work() } catch (error) {
    if (!current(token)) return
    message.value = error.response?.status === 409 ? '待办已变化，请刷新后按最新版本操作。' : needsRefresh.value ? '未能确认写入结果；请先刷新待办核对，不要重复提交。' : '操作失败；请核对权限、摘要与关联记录后重试。'
  } finally { if (current(token)) busy.value = false }
}
watch(createStudent, () => { attemptId.value = '' }, { flush: 'sync' })
watch(account, value => {
  generation++
  groups.value = {}; students.value = []; attempts.value = []; retests.value = []; ownerNames.value = {}
  for (const key of Object.keys(drafts)) delete drafts[key]
  attemptId.value = createStudent.value = message.value = ''; busy.value = false; needsRefresh.value = false
  if (value) run(async () => { const token = generation; await load(); if (current(token)) await loadOptions() })
}, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { dead = true; generation++ })
</script>

<style scoped>
.operations { padding: var(--space-2); background: var(--surface-page); color: var(--ink); }
.operations h1 { font-size: var(--text-section); margin-bottom: var(--space-2); }
.operations h3 { font-size: var(--text-card); margin: var(--space-3) 0 var(--space-1); }
.operations article { padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); margin: var(--space-2) 0; background: var(--surface); }
.operations .transfer-import { border: 0; padding: 0; margin: var(--space-1) 0; min-width: 0; }
.operations label { display: grid; gap: var(--space-1); margin: var(--space-1) 0; font-size: var(--text-caption); color: var(--ink-secondary); }
.operations .inline-picker { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.operations button, .operations input, .operations select { font: inherit; min-height: var(--control-height); padding: var(--space-1) var(--space-2); background: var(--surface); color: var(--ink); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); }
.operations button { cursor: pointer; margin: var(--space-1) var(--space-1) 0 0; }
.operations button:disabled { cursor: not-allowed; color: var(--disabled-ink); background: var(--disabled); border-color: var(--line); }
.operations button:focus-visible, .operations input:focus-visible, .operations select:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.operations .muted { color: var(--ink-secondary); font-size: var(--text-caption); }
.operations ul { margin: var(--space-1) 0; padding-left: var(--space-3); font-size: var(--text-caption); }
</style>
