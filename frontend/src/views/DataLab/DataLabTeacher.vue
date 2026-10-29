<script setup>
import { onMounted, reactive, ref } from 'vue'
import { teacherLabApi } from './api'
import { readableError } from './errors'

const cases = ref([]), taskKey = ref(''), detail = ref(null), attempts = ref([])
const busy = ref(false), error = ref(''), notice = ref('')
const helpAttempt = ref(''), helpReceipt = ref('')
const helpForm = reactive({ summary: '', level: 1 })
const pending = new Map()

async function run(action) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() }
  catch (e) { error.value = readableError(e) }
  finally { busy.value = false }
}
function clearHelp() {
  helpAttempt.value = ''; helpForm.summary = ''; helpForm.level = 1; helpReceipt.value = ''
}
async function loadCase() {
  detail.value = null; attempts.value = []; clearHelp(); pending.clear()
  if (!taskKey.value) return
  const data = await teacherLabApi.caseDetail(taskKey.value)
  // Deliberately select only management fields; never render a raw teacher response.
  detail.value = {
    title: data.material?.title || cases.value.find(c => c.task_key === taskKey.value)?.title,
    status: data.status, paused: data.paused, withdrawn: data.withdrawn,
  }
  attempts.value = (data.attempts || []).map(attempt => ({
    attempt_id: attempt.attempt_id, student_id: attempt.student_id,
    submissions: (attempt.submissions || []).map(submission => ({
      submission_id: submission.submission_id, status: submission.status,
      failure_code: submission.failure_code, module6_id: submission.module6_id,
    })),
  }))
}
async function loadCases() {
  detail.value = null; attempts.value = []; clearHelp()
  const data = await teacherLabApi.cases()
  cases.value = data.cases
  if (!cases.value.some(c => c.task_key === taskKey.value)) taskKey.value = cases.value[0]?.task_key || ''
  await loadCase()
}
async function setStatus(field) {
  const current = detail.value?.[field]
  if (typeof current !== 'boolean') throw new Error('状态未知，请先刷新案例，不能推测当前状态')
  const next = !current
  if (field === 'withdrawn' && next && !window.confirm('确认撤回此案例？学生将无法继续使用该材料。')) return
  const saved = await teacherLabApi.setStatus(taskKey.value, { [field]: next })
  detail.value.paused = saved.paused; detail.value.withdrawn = saved.withdrawn
  notice.value = '案例状态已由服务端确认'
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
  const saved = await teacherLabApi.help(taskKey.value, helpAttempt.value, { ...body, idempotency_key: pending.get(fingerprint) })
  pending.delete(fingerprint)
  helpReceipt.value = saved.record_id
  helpForm.summary = ''
  notice.value = '实际教师帮助已登记；不代表核验或评分通过'
}
onMounted(() => run(loadCases))
</script>

<template>
  <main class="teacher-lab" :aria-busy="busy">
    <header>
      <h1>数据安全案例教学管理</h1>
      <p>仅管理已获授权的案例；角色与案例对象权限均由服务端校验。</p>
      <p>本页不加载受控附件。教学演练只看决策，执行未开展，实际保护未评估。</p>
      <router-link to="/data-lab">学生实验台入口</router-link>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="busy" role="status">正在处理，请稍候…</p>
    <section aria-label="案例选择">
      <button :disabled="busy" @click="run(loadCases)">刷新授权案例列表</button>
      <label>案例
        <select v-model="taskKey" :disabled="busy || !cases.length" @change="run(loadCase)">
          <option v-for="item in cases" :key="item.task_key" :value="item.task_key">{{ item.title }} · {{ item.task_key }}</option>
        </select>
      </label>
      <p v-if="!busy && !cases.length && !error">暂无可管理案例。请联系管理员核对案例归属。</p>
    </section>
    <template v-if="detail">
      <section aria-label="案例状态">
        <h2>{{ detail.title }}</h2>
        <p>材料状态：{{ detail.status }} · 暂停：{{ typeof detail.paused === 'boolean' ? (detail.paused ? '是' : '否') : '未知' }} · 撤回：{{ typeof detail.withdrawn === 'boolean' ? (detail.withdrawn ? '是' : '否') : '未知' }}</p>
        <p>恢复暂停或撤回不会替代材料签收、发布和其他后端校验。</p>
        <button :disabled="busy || typeof detail.paused !== 'boolean'" @click="run(() => setStatus('paused'))">{{ detail.paused ? '解除暂停' : '暂停案例' }}</button>
        <button :disabled="busy || typeof detail.withdrawn !== 'boolean'" @click="run(() => setStatus('withdrawn'))">{{ detail.withdrawn ? '取消撤回' : '撤回案例' }}</button>
      </section>
      <section aria-label="学生尝试">
        <h2>学生尝试与提交状态</h2>
        <p v-if="!attempts.length">该案例尚无尝试记录。</p>
        <article v-for="attempt in attempts" :key="attempt.attempt_id">
          <h3>学生 {{ attempt.student_id }}</h3>
          <p>尝试 <code>{{ attempt.attempt_id }}</code></p>
          <p v-if="!attempt.submissions.length">尚未保存证据提交。</p>
          <ul v-else>
            <li v-for="submission in attempt.submissions" :key="submission.submission_id">
              提交 <code>{{ submission.submission_id }}</code> · 交接 {{ submission.status }}
              <span v-if="submission.failure_code"> · 原因 {{ submission.failure_code }}</span>
              <span v-if="submission.module6_id"> · 模块六 <code>{{ submission.module6_id }}</code></span>
            </li>
          </ul>
          <button :disabled="busy" @click="selectHelp(attempt.attempt_id)">登记该尝试的实际教师帮助</button>
        </article>
      </section>
      <section v-if="helpAttempt" aria-label="教师帮助登记">
        <h2>实际教师帮助</h2>
        <p>目标尝试 <code>{{ helpAttempt }}</code>。仅登记已实际提供的帮助；登记后记为受助，不会自动展示预置提示。</p>
        <form @submit.prevent="run(recordHelp)">
          <label>实际帮助层级
            <select v-model.number="helpForm.level" :disabled="busy"><option v-for="level in 4" :key="level" :value="level">{{ level }}</option></select>
          </label>
          <label>帮助摘要<textarea v-model="helpForm.summary" :disabled="busy" maxlength="1500" required /></label>
          <button type="submit" :disabled="busy || !helpForm.summary.trim()">登记实际帮助</button>
          <button type="button" :disabled="busy" @click="clearHelp">取消</button>
        </form>
        <p v-if="helpReceipt" role="status">服务端记录 <code>{{ helpReceipt }}</code></p>
      </section>
    </template>
  </main>
</template>

<style scoped>
.teacher-lab { max-width: 1100px; margin: 0 auto; padding: 24px; color: var(--color-text-1, #17212b); }
h1 { font-size: 24px; } p, li { line-height: 1.65; } code { overflow-wrap: anywhere; }
section, article { margin: 20px 0; padding: 16px; border: 1px solid var(--color-border-2, #c7cdd3); border-radius: 6px; }
label { display: block; margin: 12px 0; } button, select, textarea { font: inherit; }
button { margin: 4px; padding: 8px 12px; cursor: pointer; } button:disabled { opacity: .6; cursor: not-allowed; }
select { max-width: 100%; } textarea { display: block; box-sizing: border-box; width: 100%; min-height: 100px; }
.error { border-left: 4px solid #a82b2b; padding: 12px; }
@media(max-width: 800px) { .teacher-lab { padding: 12px; } }
</style>
