<template>
  <div class="review-page">
    <div class="page-header">
      <div>
        <span class="eyebrow">我的学习 · 验收与复盘</span>
        <h1>结果与复盘</h1>
        <p class="subtitle">
          程序核验和教师评阅分别显示；提交前实际使用过帮助会记为受助，不会因重交变成独立。
        </p>
      </div>
      <button class="btn btn-secondary" @click="loadAll" :disabled="loading">刷新</button>
    </div>

    <div v-if="loading" class="state-box">正在读取...</div>
    <div v-else-if="error" class="state-box">{{ error }}</div>

    <template v-else>
      <section class="panel">
        <div class="panel-head">
          <h2>待复测</h2>
          <span class="muted">无提示完成；到期未参加不记为知识错误。</span>
        </div>
        <div v-if="!retests.length" class="muted">暂无复测安排。</div>
        <article v-for="item in retests" :key="item.assignment_id" class="retest-card">
          <div>
            <strong>{{ item.task ? item.task.title : '等待补充新场景' }}</strong>
            <p class="muted small">
              {{ item.status_label }} · 建议 {{ formatDate(item.due_at) }}
              <template v-if="item.task"> · 版本 {{ item.task.version_label }}</template>
            </p>
            <p v-if="item.outcome_label" class="small">结果：{{ item.outcome_label }}</p>
          </div>
          <button
            v-if="item.status === 'due' || item.status === 'scheduled'"
            class="btn btn-primary btn-small"
            :disabled="claiming === item.assignment_id"
            @click="claimRetest(item)"
          >{{ claiming === item.assignment_id ? '领取中...' : '领取复测' }}</button>
          <span v-else-if="item.status === 'pending_item'" class="badge">待补题</span>
        </article>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>我的提交</h2>
          <span class="muted">只显示本人记录。</span>
        </div>
        <div v-if="!submissions.length" class="muted">暂无提交记录。</div>
        <article v-for="item in submissions" :key="item.submission_id" class="submission-card">
          <div class="submission-head">
            <div>
              <strong>{{ item.task.title }}</strong>
              <span class="muted small"> · {{ item.task.track_label }} · {{ formatDate(item.submitted_at) }}</span>
            </div>
            <span class="badge" :class="badgeClass(item.overall_status)">{{ item.overall_status_label }}</span>
          </div>

          <div class="status-grid">
            <div><span class="label">程序核验</span><strong>{{ item.program_status_label }}</strong></div>
            <div><span class="label">教师评阅</span><strong>{{ item.manual_status_label }}</strong></div>
            <div><span class="label">本次帮助</span><strong>{{ item.assistance.independence_label }}</strong></div>
            <div><span class="label">保存</span><strong>{{ item.save_status_label }}</strong></div>
          </div>

          <p v-if="item.verification_note" class="note">{{ item.verification_note }}</p>
          <p v-if="item.assistance.answer_exposure" class="note warn">
            已查看过同题解析，重做不计为首次独立完成。
          </p>

          <details>
            <summary>分项结果</summary>
            <ul class="items">
              <li v-for="entry in item.items" :key="entry.label">
                <span>{{ entry.label }}</span>
                <span class="muted small">{{ entry.kind_label }}</span>
                <strong :class="entry.status === 'failed' ? 'danger' : ''">{{ entry.status_label }}</strong>
                <span v-if="entry.max_points" class="muted small">
                  {{ entry.score === null ? '—' : entry.score }}/{{ entry.max_points }}
                </span>
              </li>
            </ul>
          </details>

          <details v-if="item.total_score !== null && item.total_score !== undefined">
            <summary>解释题量表</summary>
            <p>总分 {{ item.total_score }} / {{ item.max_total_score }}</p>
            <p v-if="item.review_remarks" class="muted">{{ item.review_remarks }}</p>
          </details>

          <div class="actions">
            <button class="btn btn-small" @click="openCard(item)">写复盘</button>
            <button class="btn btn-small" @click="openDispute(item)">提出复核</button>
          </div>

          <div v-if="activeSubmission === item.submission_id" class="card-form">
            <h3>复盘卡</h3>
            <label v-for="field in cardFields" :key="field.key">
              {{ field.label }}
              <textarea v-model="cardForm[field.key]" rows="2"></textarea>
            </label>
            <div class="actions">
              <button class="btn btn-secondary btn-small" @click="activeSubmission = null">取消</button>
              <button class="btn btn-secondary btn-small" @click="saveCard(false)">保存草稿</button>
              <button class="btn btn-primary btn-small" @click="saveCard(true)">完成复盘并安排复测</button>
            </div>
            <p v-if="cardMessage" class="note">{{ cardMessage }}</p>
          </div>

          <div v-if="disputeSubmission === item.submission_id" class="card-form">
            <h3>提出复核</h3>
            <textarea v-model="disputeReason" rows="3" placeholder="写清楚争议点和依据"></textarea>
            <div class="actions">
              <button class="btn btn-secondary btn-small" @click="disputeSubmission = null">取消</button>
              <button class="btn btn-primary btn-small" @click="submitDispute(item)">提交</button>
            </div>
            <p class="muted small">处理争议不直接改分；需要改分须由教师建立更正版本。</p>
          </div>
        </article>
      </section>
    </template>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import service from '@/api'

const loading = ref(true)
const error = ref('')
const submissions = ref([])
const retests = ref([])
const activeSubmission = ref(null)
const disputeSubmission = ref(null)
const disputeReason = ref('')
const cardMessage = ref('')
const claiming = ref(null)
const cardForm = reactive({
  original_task_summary: '',
  error_evidence: '',
  judgment_at_time: '',
  correct_basis: '',
  next_verification: '',
  student_reflection: '',
})
const cardFields = [
  { key: 'error_evidence', label: '错误证据' },
  { key: 'judgment_at_time', label: '当时的判断' },
  { key: 'correct_basis', label: '正确依据或方法' },
  { key: 'next_verification', label: '下一次如何验证' },
  { key: 'student_reflection', label: '我的反思' },
]

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function badgeClass(status) {
  if (status === 'passed') return 'ok'
  if (status === 'failed') return 'bad'
  if (status === 'pending_manual') return 'wait'
  return ''
}

function extractError(err) {
  const data = err?.response?.data
  if (!data) return '网络或服务异常。'
  if (typeof data === 'string') return data
  if (typeof data.detail === 'string') return data.detail
  if (data.detail?.detail) return data.detail.detail
  return '操作未完成。'
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [subs, retestsPayload] = await Promise.all([
      service.skillReview.mySubmissions(),
      service.skillReview.myRetests(),
    ])
    submissions.value = subs.items || []
    retests.value = retestsPayload.items || []
  } catch (err) {
    error.value = extractError(err)
  } finally {
    loading.value = false
  }
}

function openCard(item) {
  activeSubmission.value = item.submission_id
  cardMessage.value = ''
  cardForm.original_task_summary = `${item.task.title} · ${item.task.version_label}`
  cardForm.error_evidence = ''
  cardForm.judgment_at_time = ''
  cardForm.correct_basis = ''
  cardForm.next_verification = ''
  cardForm.student_reflection = ''
}

async function saveCard(complete) {
  cardMessage.value = ''
  try {
    const payload = await service.skillReview.saveReviewCard(activeSubmission.value, {
      ...cardForm,
      complete,
    })
    cardMessage.value = complete
      ? `复盘已保存。${payload.retest ? '已安排复测：' + (payload.retest.task ? payload.retest.task.title : '等待补题') : ''}`
      : '草稿已保存。'
    if (complete) {
      activeSubmission.value = null
      await loadAll()
    }
  } catch (err) {
    cardMessage.value = extractError(err)
  }
}

function openDispute(item) {
  disputeSubmission.value = item.submission_id
  disputeReason.value = ''
}

async function submitDispute(item) {
  try {
    await service.skillReview.createDispute(item.submission_id, {
      client_dispute_id: `d-${item.submission_id}-${Date.now()}`,
      reason: disputeReason.value,
    })
    disputeSubmission.value = null
    cardMessage.value = '复核申请已提交。'
  } catch (err) {
    cardMessage.value = extractError(err)
  }
}

async function claimRetest(item) {
  claiming.value = item.assignment_id
  try {
    await service.skillReview.claimRetest(item.assignment_id)
    await loadAll()
  } catch (err) {
    error.value = extractError(err)
  } finally {
    claiming.value = null
  }
}

onMounted(loadAll)
</script>

<style scoped>
.review-page { width: min(1100px, calc(100% - 40px)); margin: 0 auto; padding: 40px 0 72px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; border-bottom: 2px solid var(--text-primary); padding-bottom: 20px; margin-bottom: 20px; }
.eyebrow { font-size: 12px; letter-spacing: .16em; text-transform: uppercase; color: var(--primary-color); font-weight: 700; }
h1 { font-family: "Songti SC", serif; font-size: 40px; line-height: 1.1; }
.subtitle { color: var(--text-secondary); margin-top: 8px; max-width: 720px; }
.btn { border: 1px solid var(--border-color); background: var(--bg-light); padding: 8px 12px; font-weight: 600; cursor: pointer; color: var(--text-primary); }
.btn-primary { background: var(--text-primary); color: var(--bg-light); }
.btn-small { padding: 5px 10px; font-size: 12px; }
.panel { background: var(--bg-light); border: 1px solid var(--border-color); padding: 18px; margin-bottom: 18px; box-shadow: var(--shadow-md); }
.panel h2 { font-family: "Songti SC", serif; font-size: 20px; }
.panel-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
.muted { color: var(--text-muted); font-size: 12px; }
.small { font-size: 12px; }
.retest-card { display: flex; justify-content: space-between; gap: 16px; align-items: center; border-top: 1px solid var(--border-color); padding: 12px 0; }
.submission-card { border-top: 1px solid var(--border-color); padding: 14px 0; }
.submission-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.badge { font-size: 11px; padding: 2px 8px; border: 1px solid var(--border-color); }
.badge.ok { color: var(--success-color); border-color: var(--success-color); }
.badge.bad { color: var(--error-color); border-color: var(--error-color); }
.badge.wait { color: var(--warning-color); border-color: var(--warning-color); }
.status-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 10px 0; }
.status-grid .label { display: block; font-size: 11px; color: var(--text-muted); }
.note { font-size: 12px; color: var(--text-secondary); margin-top: 6px; }
.note.warn { color: var(--warning-color); }
.items { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; font-size: 12px; }
.items li { display: grid; grid-template-columns: 1.4fr .8fr 80px 60px; gap: 8px; }
.danger { color: var(--error-color); }
.actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.card-form { margin-top: 12px; border: 1px dashed var(--border-color); padding: 12px; }
.card-form h3 { font-size: 14px; margin-bottom: 8px; }
.card-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; margin-bottom: 8px; color: var(--text-secondary); }
.card-form textarea { border: 1px solid var(--border-color); padding: 6px 8px; font: inherit; }
.state-box { background: var(--bg-light); border: 1px solid var(--border-color); padding: 48px; text-align: center; color: var(--text-muted); }
@media (max-width: 800px) { .status-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
