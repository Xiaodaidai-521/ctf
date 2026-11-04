<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'
import { teacherLabApi } from './api'
import { readableError } from './errors'
import api from '@/api'

const cases = ref([]), taskKey = ref(''), detail = ref(null), attempts = ref([])
const studentNames = ref({})
const busy = ref(false), error = ref(''), notice = ref('')
const helpAttempt = ref(''), helpReceipt = ref('')
const helpForm = reactive({ summary: '', level: 1 })
const pending = new Map()
const route = useRoute(), user = useUserStore()
const isAdmin = computed(() => user.userInfo?.role === 'admin')
let generation = 0
let alive = true
function clearPrivateState() {
  generation += 1
  cases.value = []; taskKey.value = ''; detail.value = null; attempts.value = []
  studentNames.value = {}; busy.value = false; error.value = ''; notice.value = ''
  clearHelp(); pending.clear()
}

const statusLabels = { published: '已发布', draft: '草稿', signed_off: '已签收', withdrawn: '已撤回', paused: '已暂停', active: '可用' }
const handoffLabels = { pending: '待交接', synced: '已交接', failed: '交接未完成', not_required: '无需交接' }
const failureLabels = {
  module6_unavailable: '核验服务暂不可用', validation_failed: '提交内容未通过核验',
  timeout: '核验超时', unknown: '原因待确认',
}
const levelLabels = { 1: '思路提示', 2: '关键点提示', 3: '局部示例', 4: '完整讲解' }
const statusLabel = value => statusLabels[value] || (value ? '状态待确认' : '未提供')

async function run(action) {
  if (!alive || busy.value) return
  const token = generation
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() }
  catch (e) { if (token === generation) error.value = readableError(e) }
  finally { if (token === generation) busy.value = false }
}
function clearHelp() {
  helpAttempt.value = ''; helpForm.summary = ''; helpForm.level = 1; helpReceipt.value = ''
}
function studentLabel(studentId) {
  if (!studentId) return '未关联学生'
  return studentNames.value[String(studentId)] || '学生姓名暂不可用'
}
async function loadStudentNames() {
  const token = generation
  try {
    const report = await api.analytics.teacherStudentReport()
    if (token === generation) studentNames.value = Object.fromEntries((report || []).map(item => [String(item.id), item.username]))
  } catch {
    if (token === generation) studentNames.value = {}
  }
}
async function loadCase() {
  const token = generation, key = taskKey.value
  detail.value = null; attempts.value = []; clearHelp(); pending.clear()
  if (!key || !alive) return
  const data = await teacherLabApi.caseDetail(key)
  if (token !== generation || key !== taskKey.value) return
  // Deliberately select only management fields; never render a raw teacher response.
  detail.value = {
    title: data.material?.title || cases.value.find(c => c.task_key === taskKey.value)?.title,
    status: data.status, paused: data.paused, withdrawn: data.withdrawn,
  }
  attempts.value = (data.attempts || []).map(attempt => ({
    attempt_id: attempt.attempt_id, student_id: attempt.student_id,
    submissions: (attempt.submissions || []).map(submission => ({
      submission_id: submission.submission_id, status: submission.status,
      failure_code: submission.failure_code,
    })),
  }))
}
async function loadCases() {
  if (!alive) return
  const token = generation
  detail.value = null; attempts.value = []; clearHelp()
  const data = await teacherLabApi.cases()
  if (token !== generation) return
  cases.value = data.cases
  const linkedCase = typeof route.query.case === 'string' ? route.query.case : ''
  if (linkedCase && cases.value.some(c => c.task_key === linkedCase)) taskKey.value = linkedCase
  else if (!cases.value.some(c => c.task_key === taskKey.value)) taskKey.value = cases.value[0]?.task_key || ''
  if (linkedCase && !cases.value.some(c => c.task_key === linkedCase)) error.value = '链接中的案例暂不可用，或当前账号尚未获授权。可从授权列表重新选择。'
  await loadCase()
}
async function setStatus(field) {
  const current = detail.value?.[field]
  if (typeof current !== 'boolean') throw new Error('状态未知，请先刷新案例，不能推测当前状态')
  const next = !current
  if (field === 'withdrawn' && next && !window.confirm('确认撤回此案例？学生将无法继续使用该材料。')) return
  const token = generation, key = taskKey.value
  const saved = await teacherLabApi.setStatus(key, { [field]: next })
  if (token !== generation || key !== taskKey.value || !detail.value) return
  detail.value.paused = saved.paused; detail.value.withdrawn = saved.withdrawn
  notice.value = '案例状态已确认'
}
function selectHelp(attemptId) {
  clearHelp(); error.value = ''; notice.value = ''
  helpAttempt.value = attemptId
}
async function recordHelp() {
  if (!helpAttempt.value || !helpForm.summary.trim()) throw new Error('请选择尝试并填写实际提供的帮助摘要')
  const body = { summary: helpForm.summary.trim(), level: helpForm.level }
  const fingerprint = JSON.stringify([taskKey.value, helpAttempt.value, body])
  if (!pending.has(fingerprint)) pending.set(fingerprint, crypto.randomUUID())
  const token = generation
  const saved = await teacherLabApi.help(taskKey.value, helpAttempt.value, { ...body, idempotency_key: pending.get(fingerprint) })
  if (token !== generation) return
  pending.delete(fingerprint)
  helpReceipt.value = saved.record_id
  helpForm.summary = ''
  notice.value = '实际教师帮助已登记；不代表核验或评分通过'
}
watch(() => [user.userInfo?.id, user.userInfo?.role], () => {
  clearPrivateState()
  void run(async () => { const token = generation; await loadStudentNames(); if (token === generation) await loadCases() })
}, { flush: 'sync' })
watch(() => route.query.case, () => {
  clearPrivateState()
  void run(async () => { const token = generation; await loadStudentNames(); if (token === generation) await loadCases() })
}, { flush: 'sync' })
onBeforeUnmount(() => { alive = false; clearPrivateState() })
onMounted(() => run(async () => { const token = generation; await loadStudentNames(); if (token === generation) await loadCases() }))
</script>

<template>
  <main class="teacher-lab" :aria-busy="busy">
    <header>
      <h1>{{ isAdmin ? '数据安全案例监督' : '数据安全案例管理' }}</h1>
      <p>仅管理已获授权的案例；操作时会核验账号与案例访问权限。</p>
      <p>本页不加载受控附件。教学演练只看决策，执行未开展，实际保护未评估。</p>
      <router-link to="/resources/topics/data-security">查看智库数据安全专题</router-link>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="busy" role="status">正在处理，请稍候…</p>
    <section aria-label="案例选择">
      <button :disabled="busy" @click="run(loadCases)">刷新授权案例列表</button>
      <label>案例
        <select v-model="taskKey" :disabled="busy || !cases.length" @change="run(loadCase)">
          <option v-for="item in cases" :key="item.task_key" :value="item.task_key">{{ item.title }}</option>
        </select>
      </label>
      <p v-if="!busy && !cases.length && !error">暂无可管理案例。请联系管理员核对案例归属。</p>
    </section>
    <template v-if="detail">
      <section aria-label="案例状态">
        <h2>{{ detail.title }}</h2>
        <p>材料状态：{{ statusLabel(detail.status) }} · 暂停：{{ typeof detail.paused === 'boolean' ? (detail.paused ? '是' : '否') : '未知' }} · 撤回：{{ typeof detail.withdrawn === 'boolean' ? (detail.withdrawn ? '是' : '否') : '未知' }}</p>
        <p>恢复使用仍需满足材料签收、发布和访问权限要求。</p>
        <button :disabled="busy || typeof detail.paused !== 'boolean'" @click="run(() => setStatus('paused'))">{{ detail.paused ? '解除暂停' : '暂停案例' }}</button>
        <button :disabled="busy || typeof detail.withdrawn !== 'boolean'" @click="run(() => setStatus('withdrawn'))">{{ detail.withdrawn ? '取消撤回' : '撤回案例' }}</button>
      </section>
      <section aria-label="学生尝试">
        <h2>学生尝试与提交状态</h2>
        <p v-if="!attempts.length">该案例尚无尝试记录。</p>
        <article v-for="attempt in attempts" :key="attempt.attempt_id">
          <h3>学生 {{ studentLabel(attempt.student_id) }}</h3>
          <p>练习记录：{{ attempt.student_id ? '已关联学生' : '未关联学生' }}</p>
          <p v-if="!attempt.submissions.length">尚未保存证据提交。</p>
          <ul v-else>
            <li v-for="submission in attempt.submissions" :key="submission.submission_id">
              提交状态：{{ handoffLabels[submission.status] || '状态待确认' }}
              <span v-if="submission.failure_code"> · 原因：{{ failureLabels[submission.failure_code] || '原因待确认' }}</span>
            </li>
          </ul>
          <button :disabled="busy" @click="selectHelp(attempt.attempt_id)">登记该尝试的实际教师帮助</button>
        </article>
      </section>
      <section v-if="helpAttempt" aria-label="教师帮助登记">
        <h2>实际教师帮助</h2>
        <p>仅登记已实际提供的帮助；登记后记为受助，不会自动展示预置提示。</p>
        <form @submit.prevent="run(recordHelp)">
          <label>实际帮助层级
            <select v-model.number="helpForm.level" :disabled="busy">
              <option v-for="level in 4" :key="level" :value="level">{{ level }} · {{ levelLabels[level] }}</option>
            </select>
          </label>
          <label>帮助摘要<textarea v-model="helpForm.summary" :disabled="busy" maxlength="1500" required /></label>
          <button type="submit" :disabled="busy || !helpForm.summary.trim()">登记实际帮助</button>
          <button type="button" :disabled="busy" @click="clearHelp">取消</button>
        </form>
        <p v-if="helpReceipt" role="status">帮助登记已由服务端确认。</p>
      </section>
    </template>
  </main>
</template>

<style scoped>
.teacher-lab { width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: 0 auto; padding: var(--space-3) 0 var(--space-6); color: var(--ink); font-size: var(--text-body); line-height: var(--leading-body); }
h1 { font-size: var(--text-page); line-height: var(--leading-tight); } h2 { font-size: var(--text-section); } h3 { font-size: var(--text-card); } p, li { line-height: var(--leading-body); }
section, article { margin: var(--space-3) 0; padding: var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
label { display: grid; gap: var(--space-1); margin: var(--space-2) 0; font-size: var(--text-caption); color: var(--ink-secondary); }
button, select, textarea { font: inherit; }
button { margin: var(--space-1) var(--space-1) 0 0; min-height: var(--control-height); padding: var(--space-1) var(--space-2); cursor: pointer; border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); }
button:hover:not(:disabled) { background: var(--surface-hover); }
button:disabled { cursor: not-allowed; color: var(--disabled-ink); background: var(--disabled); border-color: var(--line); }
button:focus-visible, select:focus-visible, textarea:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
select { max-width: 100%; min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); }
textarea { display: block; box-sizing: border-box; width: 100%; min-height: 100px; padding: var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); }
.error { border-left: var(--focus-width) solid var(--negative); padding: var(--space-2); background: var(--negative-soft); color: var(--negative); }
[role='status'] { color: var(--ink-secondary); }
@media (max-width: 768px) { .teacher-lab { padding-inline: var(--space-2); } }
</style>
