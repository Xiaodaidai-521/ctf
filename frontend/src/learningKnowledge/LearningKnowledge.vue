<template>
  <main class="lk-page">
    <header class="lk-header">
      <div>
        <p class="lk-eyebrow">模块三 · 学生证据</p>
        <h1>当前任务的学习证据</h1>
        <p class="lk-id">任务尝试：{{ attemptId }}</p>
      </div>
      <router-link class="lk-button" to="/feedback">模块七反馈中心</router-link>
    </header>
    <p class="lk-notice">只检索当前真实任务尝试的授权学习材料。证据不等于正确性或合规结论；本页不提供提示或答案解析的通用入口。</p>
    <p class="lk-muted">内容仅保存在本页内存中。切换用户 / 任务、离开页面、窗口失焦或后台会清除结果、详情、输入和未完成请求；返回后须重新检索。</p>

    <section v-if="paused" class="lk-panel" aria-live="polite">
      <h2>内容已清除</h2>
      <p>不会恢复之前的证据正文或继续旧请求。服务器会重新检查当前会话与任务权限。</p>
      <button v-if="sessionChanged" type="button" @click="privacy.reload">会话已在其他标签页变化，刷新页面</button>
      <button v-else type="button" @click="resumeAndSearch">为当前尝试重新检索</button>
    </section>

    <p v-if="error" class="lk-error" role="alert">{{ error }}</p>
    <p v-if="message" class="lk-notice" role="status">{{ message }}</p>
    <p v-if="busy" role="status">正在向服务器请求，请稍候……</p>

    <template v-if="!paused">
      <section class="lk-panel">
        <h2>检索学习材料</h2>
        <form class="lk-actions" @submit.prevent="search">
          <label class="lk-grow">检索词（留空读取当前任务的静态材料，最多 500 字）
            <input v-model="query" maxlength="500" autocomplete="off" :disabled="busy" />
          </label>
          <button type="submit" :disabled="busy">检索</button>
        </form>
        <p class="lk-muted">范围来自路由 attemptId，不能在此选择其他用户、课程权限或检索用途。</p>
      </section>

      <section v-if="searched" class="lk-panel" aria-labelledby="evidence-title">
        <h2 id="evidence-title">证据短卡片</h2>
        <p :class="evidenceStatus === 'sufficient' ? 'lk-notice' : 'lk-warning'" role="status">{{ statusNotice }}</p>
        <p>{{ serverNotice }}</p>
        <p class="lk-muted">检索方式：{{ mode === 'static' ? '静态任务材料' : mode === 'lexical' ? '关键词检索' : mode }}。仅显示服务器授权短摘录，不读取源文件。</p>
        <p v-if="!results.length">未返回可用证据。可以继续任务或通过下方模块七入口请求教师补查，不会自动编造证据。</p>
        <EvidenceCard v-for="card in results" :key="card.evidence_id" :evidence="card">
          <div class="lk-actions">
            <button type="button" :disabled="busy" @click="readDetail(card.evidence_id)">重新 GET 详情</button>
            <button type="button" :disabled="busy" @click="selectIssue(card.evidence_id)">对此证据反馈</button>
          </div>
        </EvidenceCard>
      </section>

      <section v-if="detail" class="lk-panel" aria-labelledby="detail-title">
        <h2 id="detail-title">证据详情（刚从服务器重新读取）</h2>
        <p>详情也只有短投影，不代表可以访问完整材料。下载会再次 GET 受控下载端点，可能因撤回、过期或授权变化被拒绝。</p>
        <EvidenceCard :evidence="detail" />
        <div class="lk-actions">
          <button type="button" :disabled="busy" @click="download(detail.evidence_id)">下载服务器短投影（JSON）</button>
          <button type="button" :disabled="busy" @click="detail = null">清除详情</button>
        </div>
        <p class="lk-muted">仅在主动点击后下载。下载文件是本机副本，离开页面不会删除，请按许可妥善处理。</p>
      </section>

      <section class="lk-panel" aria-labelledby="issue-title">
        <h2 id="issue-title">请求教师补查 · 模块七</h2>
        <p>缺证、过期、来源冲突、无定位或材料错误均可反馈。此操作创建或关联模块七工单，不自动修改成绩或来源。</p>
        <form class="lk-form" @submit.prevent="reportIssue">
          <label>问题类型
            <select v-model="issueReason" :disabled="busy">
              <option value="insufficient">证据不足</option><option value="stale">证据过期</option>
              <option value="conflict">来源冲突</option><option value="unlocated">定位待补齐</option>
              <option value="material_error">材料错误</option>
            </select>
          </label>
          <label>关联证据（可不选）
            <select v-model="issueEvidence" :disabled="busy">
              <option value="">当前任务缺证 / 无可用证据</option>
              <option v-for="card in results" :key="card.evidence_id" :value="card.evidence_id">{{ card.title }} · {{ card.evidence_id }}</option>
            </select>
          </label>
          <p class="lk-full lk-muted">证据若已不可读，请重新检索，或选择“当前任务缺证 / 无可用证据”提交任务级补查。</p>
          <button type="submit" :disabled="busy">提交补查请求</button>
        </form>
        <p v-if="feedbackId" role="status">
          {{ feedbackCreated ? '已创建补查工单。' : '已关联现有未关闭的补查工单。' }}
          <router-link :to="{ name: 'FeedbackDetail', params: { id: feedbackId } }">前往模块七查看处理</router-link>
        </p>
      </section>
    </template>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import EvidenceCard from './EvidenceCard.vue'
import { knowledgeApi, errorMessage } from './api.js'
import { requestKey } from './requestGeneration.js'
import { usePrivatePage } from './usePrivatePage.js'
import './learningKnowledge.css'

const route = useRoute()
const attemptId = computed(() => String(route.params.attemptId || ''))
const query = ref('')
const results = ref([])
const detail = ref(null)
const searched = ref(false)
const evidenceStatus = ref('')
const serverNotice = ref('')
const mode = ref('')
const busy = ref(false)
const error = ref('')
const message = ref('')
const issueReason = ref('insufficient')
const issueEvidence = ref('')
const pendingIssue = ref(null)
const feedbackId = ref('')
const feedbackCreated = ref(false)
const downloadUrls = new Set()

function clearEvidence() {
  results.value = []
  detail.value = null
  searched.value = false
  evidenceStatus.value = ''
  serverNotice.value = ''
  mode.value = ''
  issueEvidence.value = ''
  for (const url of downloadUrls) URL.revokeObjectURL(url)
  downloadUrls.clear()
}
function clearContent() {
  clearEvidence()
  query.value = ''
  busy.value = false
  error.value = ''
  message.value = ''
  issueReason.value = 'insufficient'
  pendingIssue.value = null
  feedbackId.value = ''
  feedbackCreated.value = false
}
const privacy = usePrivatePage(clearContent)
const { paused, sessionChanged } = privacy
const statusNotice = computed(() => ({
  sufficient: '已返回授权证据；请核对来源、定位、许可及适用范围，不应扩大结论。',
  insufficient: '缺证：当前授权材料不足，可继续提交任务或请求教师补查。',
  stale: '过期：材料已到复查期限，不展示过期正文。请请求教师更新来源。',
  conflict: '冲突：来源存在待核对冲突，不自动选择其中一个作为结论。请请求教师复核。',
  unlocated: '无定位：定位待人工补齐，不能把这些短摘录当作已定位证据。',
}[evidenceStatus.value] || '服务器未返回可识别的证据状态，请请求教师核查。'))

function validAttempt() {
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(attemptId.value)) return true
  error.value = '路由中的 attemptId 必须为真实任务尝试 UUID；请从任务页面取得正确地址。'
  return false
}
function failure(err) {
  // Never keep showing a previous response after a denied / failed revalidation.
  clearEvidence()
  error.value = errorMessage(err)
}

async function search() {
  if (busy.value || !validAttempt()) return
  const ticket = privacy.begin()
  if (!ticket) return
  const body = { attempt_id: attemptId.value, query: query.value, request_id: requestKey() }
  clearEvidence()
  pendingIssue.value = null
  feedbackId.value = ''
  error.value = ''
  message.value = ''
  busy.value = true
  try {
    const result = await knowledgeApi.search(body, ticket.signal)
    if (!ticket.isCurrent()) return
    results.value = result.results
    evidenceStatus.value = result.evidence_status
    serverNotice.value = result.notice
    mode.value = result.mode
    searched.value = true
    if (['insufficient', 'stale', 'conflict', 'unlocated'].includes(result.evidence_status)) {
      issueReason.value = result.evidence_status
    }
  } catch (err) {
    if (ticket.isCurrent()) failure(err)
  } finally {
    if (ticket.isCurrent()) busy.value = false
    ticket.finish()
  }
}
function resumeAndSearch() {
  if (privacy.resume()) search()
}

async function readDetail(id) {
  if (busy.value) return
  const ticket = privacy.begin()
  if (!ticket) return
  detail.value = null
  error.value = ''
  message.value = ''
  busy.value = true
  try {
    // Intentionally not results.find(): the server must reauthorize this evidence.
    const result = await knowledgeApi.evidence(id, ticket.signal)
    if (ticket.isCurrent()) detail.value = result
  } catch (err) {
    if (ticket.isCurrent()) failure(err)
  } finally {
    if (ticket.isCurrent()) busy.value = false
    ticket.finish()
  }
}

async function download(id) {
  if (busy.value) return
  const ticket = privacy.begin()
  if (!ticket) return
  error.value = ''
  message.value = ''
  busy.value = true
  try {
    const projection = await knowledgeApi.download(id, ticket.signal)
    if (!ticket.isCurrent()) return
    // Save only this fresh endpoint response, never cached cards, source URLs or raw materials.
    const blob = new Blob([JSON.stringify(projection, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    downloadUrls.add(url)
    const link = document.createElement('a')
    link.href = url
    link.download = 'learning-evidence.json'
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => { URL.revokeObjectURL(url); downloadUrls.delete(url) }, 0)
    // A native download dialog can blur the window and clear the page synchronously.
    if (ticket.isCurrent()) message.value = '已请求下载服务器本次授权的短投影，不含原始源文件。'
  } catch (err) {
    if (ticket.isCurrent()) failure(err)
  } finally {
    if (ticket.isCurrent()) busy.value = false
    ticket.finish()
  }
}

function selectIssue(id) {
  issueEvidence.value = id
  issueReason.value = evidenceStatus.value === 'sufficient' ? 'material_error' : evidenceStatus.value
  if (!['insufficient', 'stale', 'conflict', 'unlocated', 'material_error'].includes(issueReason.value)) {
    issueReason.value = 'material_error'
  }
  message.value = '已选择该证据，请在下方确认问题类型并提交补查。'
}
async function reportIssue() {
  if (busy.value || !validAttempt()) return
  const ticket = privacy.begin()
  if (!ticket) return
  const fields = { attempt_id: attemptId.value, reason: issueReason.value }
  if (issueEvidence.value) fields.evidence_id = issueEvidence.value
  const fingerprint = JSON.stringify(fields)
  if (pendingIssue.value?.fingerprint !== fingerprint) {
    pendingIssue.value = { fingerprint, body: { ...fields, request_id: requestKey() } }
  }
  const body = { ...pendingIssue.value.body }
  busy.value = true
  error.value = ''
  message.value = ''
  feedbackId.value = ''
  try {
    const result = await knowledgeApi.issue(body, ticket.signal)
    if (!ticket.isCurrent()) return
    feedbackId.value = result.feedback_id
    feedbackCreated.value = result.created
    pendingIssue.value = null
  } catch (err) {
    if (ticket.isCurrent()) failure(err)
  } finally {
    if (ticket.isCurrent()) busy.value = false
    ticket.finish()
  }
}

onMounted(resumeAndSearch)
</script>
