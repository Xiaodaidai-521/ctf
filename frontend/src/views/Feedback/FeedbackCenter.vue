<template>
  <div class="fb-page">
    <div class="fb-header">
      <div>
        <span class="fb-eyebrow">模块七 · 学生反馈</span>
        <h1 class="fb-title">反馈中心</h1>
        <p class="fb-sub">
          针对识别、决策或教学问题提交具体争议与证据。反馈工单有独立状态，但不会直接修改学生成绩、学习事实或教学规则。
        </p>
      </div>
      <div class="fb-actions">
        <router-link to="/capability-map" class="fb-btn">能力地图</router-link>
        <router-link to="/feedback" class="fb-btn">刷新</router-link>
      </div>
    </div>

    <div class="fb-notice">
      <strong>教学演练：只看决策，不执行导出。</strong>
      首期反馈不触发执行、不预占生产配额、不修改生产策略。
      执行反馈入口等待独立里程碑 I；处理完成不等于教学效果已验证，也不等于新规则已生效。
    </div>

    <div v-if="statusInfo" class="fb-panel">
      <div class="fb-meta">
        <span class="fb-badge" :class="statusInfo.execution_feedback_open ? 'fb-badge-warn' : 'fb-badge-muted'">
          执行反馈：{{ statusInfo.execution_feedback_open ? '开放' : '未开放（里程碑 I）' }}
        </span>
        <span class="fb-badge fb-badge-info">核心流程不依赖模型</span>
        <span class="fb-badge fb-badge-muted">导出触发：否</span>
        <span class="fb-badge fb-badge-muted">配额预占：否</span>
        <span class="fb-badge fb-badge-muted">策略修改：否</span>
      </div>
    </div>

    <div class="fb-grid">
      <section class="fb-panel">
        <h2>提交反馈</h2>
        <p class="fb-muted">
          请先选择相关任务尝试；缺少任务/尝试关联时仍可保存，但会标为待补证/未映射，不能用于候选验收或能力提升统计。
        </p>

        <form @submit.prevent="submit">
          <div class="fb-form-grid">
            <label>
              反馈类别
              <select v-model="form.category" class="fb-select">
                <option v-for="item in options.categories" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label>
              具体问题
              <select v-model="form.issue_type" class="fb-select">
                <option v-for="item in issueTypes" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label class="fb-full">
              关联任务尝试（可选）
              <select v-if="!isTeacher" v-model="form.attempt_id" class="fb-select">
                <option value="">不关联尝试（将标为未映射/待补证）</option>
                <option v-for="attempt in attempts" :key="attempt.attempt_id" :value="attempt.attempt_id">
                  {{ attempt.task.title }} · {{ attempt.task.version }} · {{ attempt.status_label }}
                </option>
              </select>
              <input v-else v-model="form.attempt_uuid" class="fb-input" placeholder="尝试 UUID（教师代填，可留空）" />
            </label>
            <template v-if="isTeacher">
              <label>
                反馈所属学生 ID
                <input v-model="form.student_id" class="fb-input" placeholder="学生用户 ID" />
              </label>
              <label>
                目录版本
                <input v-model="form.catalog_version" class="fb-input" placeholder="如 v1-candidate" />
              </label>
              <label>
                任务键
                <input v-model="form.task_key" class="fb-input" placeholder="如 TASK-DS-..." />
              </label>
              <label>
                任务版本
                <input v-model="form.task_version" class="fb-input" placeholder="如 1.0.0" />
              </label>
            </template>
            <label class="fb-full">
              具体争议
              <textarea v-model="form.dispute" class="fb-textarea" rows="4" placeholder="写清楚哪一项判定、哪条证据或哪个处理结果与事实不一致"></textarea>
            </label>
            <label class="fb-full">
              期望结果
              <textarea v-model="form.expected_result" class="fb-textarea" rows="2" placeholder="希望如何更正或复核"></textarea>
            </label>
            <label class="fb-full">
              理由
              <textarea v-model="form.reason" class="fb-textarea" rows="2" placeholder="为什么你认为原判定需要复核"></textarea>
            </label>
            <label>
              原始判定引用
              <input v-model="form.original_decision_ref" class="fb-input" placeholder="如 recognition-profile / decision-id / fact-id" />
            </label>
            <label>
              原始判定版本
              <input v-model="form.original_decision_version" class="fb-input" placeholder="如 v1" />
            </label>
          </div>

          <h3>必需证据</h3>
          <p class="fb-muted">
            证据只保存引用、版本和必要摘要；不要粘贴完整答案、教师评分密钥、真实个人信息或凭证。附件请在保存后到详情页上传。
          </p>
          <div v-for="slot in requiredSlots" :key="slot.slot" class="fb-slot" style="margin-bottom: 10px;">
            <h4>{{ slot.label }}</h4>
            <div class="fb-form-grid">
              <label>
                证据引用
                <input :value="evidenceDraft[slot.slot]?.ref || ''" class="fb-input" @input="updateEvidence(slot.slot, 'ref', $event.target.value)" />
              </label>
              <label>
                版本
                <input :value="evidenceDraft[slot.slot]?.version || ''" class="fb-input" @input="updateEvidence(slot.slot, 'version', $event.target.value)" />
              </label>
              <label class="fb-full">
                必要摘要
                <textarea :value="evidenceDraft[slot.slot]?.summary || ''" class="fb-textarea" rows="2" @input="updateEvidence(slot.slot, 'summary', $event.target.value)"></textarea>
              </label>
            </div>
          </div>

          <div class="fb-missing">
            <label class="fb-check">
              <input type="checkbox" disabled />
              执行反馈（涉及实际导出/配额/交付；里程碑 I 后开放，当前不可提交）
            </label>
          </div>

          <div v-if="error" class="fb-error">{{ error }}</div>
          <div v-if="message" class="fb-success">
            {{ message }}
            <router-link v-if="lastCreatedId" :to="`/feedback/${lastCreatedId}`" class="fb-link">打开详情</router-link>
          </div>

          <div class="fb-actions">
            <button class="fb-btn fb-btn-primary" type="submit" :disabled="submitting">
              {{ submitting ? '保存中...' : (savePending ? '使用同一提交标识重试' : '提交反馈') }}
            </button>
            <button v-if="savePending" class="fb-btn" type="button" @click="submit">重试保存</button>
          </div>
        </form>
      </section>

      <section class="fb-panel">
        <h2>我的反馈</h2>
        <div class="fb-toolbar">
          <label>
            状态
            <select v-model="listFilters.status" class="fb-select" @change="loadList">
              <option value="">全部</option>
              <option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
          </label>
          <label>
            类别
            <select v-model="listFilters.category" class="fb-select" @change="loadList">
              <option value="">全部</option>
              <option v-for="item in options.categories" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
          </label>
          <button class="fb-btn" type="button" @click="loadList">刷新</button>
        </div>

        <div v-if="!tickets.length" class="fb-empty">暂无反馈记录。</div>
        <div v-else class="fb-list">
          <article v-for="ticket in tickets" :key="ticket.feedback_id" class="fb-card">
            <div class="fb-card-head">
              <div>
                <div class="fb-card-title">
                  <router-link :to="`/feedback/${ticket.feedback_id}`" class="fb-link">
                    {{ ticket.category_label }} · {{ ticket.issue_type_label }}
                  </router-link>
                </div>
                <div class="fb-meta">
                  <span class="fb-badge" :class="statusTone(ticket.status)">{{ ticket.status_label }}</span>
                  <span>{{ ticket.task_title || '未关联任务' }}</span>
                  <span>{{ formatDate(ticket.created_at) }}</span>
                  <span v-if="ticket.duplicate_of">重复于 {{ ticket.duplicate_of }}</span>
                </div>
              </div>
              <span class="fb-badge" :class="ticket.candidate_eligible ? 'fb-badge-ok' : 'fb-badge-muted'">
                {{ ticket.candidate_eligible ? '可作为候选依据' : '不可作为候选依据' }}
              </span>
            </div>
            <div v-if="ticket.missing_evidence_labels?.length" class="fb-missing">
              待补证：{{ ticket.missing_evidence_labels.join('、') }}
            </div>
            <div class="fb-meta">
              <span>处理去向：{{ ticket.handling_destination_label }}</span>
              <span>教学效果：{{ ticket.effect_status_label }}</span>
              <span v-if="ticket.owner_name">责任人：{{ ticket.owner_name }}</span>
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import service from '@/api'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const isTeacher = computed(() => ['teacher', 'admin'].includes(userStore.userInfo?.role))

const statusInfo = ref(null)
const options = reactive({ categories: [], conditional_slots: [], statuses: [], destinations: [] })
const attempts = ref([])
const tickets = ref([])
const counts = ref({})
const statuses = ref([])
const error = ref('')
const message = ref('')
const submitting = ref(false)
const savePending = ref(false)
const lastCreatedId = ref('')
const clientRequestId = ref(newClientRequestId())
const evidenceDraft = reactive({})

const form = reactive({
  category: 'recognition',
  issue_type: 'false_positive',
  attempt_id: '',
  attempt_uuid: '',
  student_id: '',
  catalog_version: '',
  task_key: '',
  task_version: '',
  dispute: '',
  expected_result: '',
  reason: '',
  original_decision_ref: '',
  original_decision_version: '',
})

const listFilters = reactive({ status: '', category: '' })

const issueTypes = computed(() => {
  const category = options.categories.find((item) => item.value === form.category)
  return category?.issue_types || []
})

const requiredSlots = computed(() => {
  const category = options.categories.find((item) => item.value === form.category)
  const slots = [...(category?.required_slots || [])]
  const conditional = options.conditional_slots.find(
    (item) => item.category === form.category && item.issue_type === form.issue_type,
  )
  if (conditional) {
    for (const slot of conditional.slots) {
      if (!slots.some((item) => item.slot === slot.slot)) slots.push(slot)
    }
  }
  return slots
})

function newClientRequestId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `fb-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function ensureEvidenceSlots() {
  for (const slot of requiredSlots.value) {
    if (!evidenceDraft[slot.slot]) {
      evidenceDraft[slot.slot] = { ref: '', version: '', summary: '' }
    }
  }
}

function updateEvidence(slot, field, value) {
  if (!evidenceDraft[slot]) evidenceDraft[slot] = { ref: '', version: '', summary: '' }
  evidenceDraft[slot][field] = value
}

function statusTone(status) {
  if (['confirmed', 'handled'].includes(status)) return 'fb-badge-ok'
  if (['pending_evidence', 'reopened', 'rejected'].includes(status)) return 'fb-badge-warn'
  if (status === 'duplicate') return 'fb-badge-muted'
  return 'fb-badge-info'
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

async function loadAll() {
  error.value = ''
  try {
    const [statusRes, optionsRes, listRes, attemptsRes] = await Promise.all([
      service.feedback.status(),
      service.feedback.options(),
      service.feedback.myList({}),
      service.learningMap.myAttempts(),
    ])
    statusInfo.value = statusRes
    Object.assign(options, optionsRes)
    statuses.value = optionsRes.statuses || []
    tickets.value = listRes.items || []
    counts.value = listRes.counts || {}
    attempts.value = attemptsRes.items || []
    if (issueTypes.value.length && !issueTypes.value.some((item) => item.value === form.issue_type)) {
      form.issue_type = issueTypes.value[0].value
    }
    ensureEvidenceSlots()
  } catch (err) {
    error.value = err.response?.data?.detail || '加载反馈中心失败。'
  }
}

async function loadList() {
  try {
    const res = await service.feedback.myList({
      status: listFilters.status || undefined,
      category: listFilters.category || undefined,
    })
    tickets.value = res.items || []
    counts.value = res.counts || {}
  } catch (err) {
    error.value = err.response?.data?.detail || '加载反馈列表失败。'
  }
}

async function submit() {
  error.value = ''
  message.value = ''
  if (!form.dispute.trim()) {
    error.value = '请填写具体争议。'
    return
  }
  submitting.value = true
  try {
    const evidence = requiredSlots.value
      .map((slot) => ({
        slot: slot.slot,
        ref: (evidenceDraft[slot.slot]?.ref || '').trim(),
        version: (evidenceDraft[slot.slot]?.version || '').trim(),
        summary: (evidenceDraft[slot.slot]?.summary || '').trim(),
      }))
      .filter((item) => item.ref || item.version || item.summary)
    const payload = {
      client_request_id: clientRequestId.value,
      category: form.category,
      issue_type: form.issue_type,
      dispute: form.dispute.trim(),
      expected_result: form.expected_result.trim(),
      reason: form.reason.trim(),
      original_decision_ref: form.original_decision_ref.trim(),
      original_decision_version: form.original_decision_version.trim(),
      evidence,
    }
    if (form.attempt_id) payload.attempt_id = form.attempt_id
    if (isTeacher.value) {
      if (form.attempt_uuid.trim()) payload.attempt_id = form.attempt_uuid.trim()
      if (form.student_id.trim()) {
        const studentId = Number(form.student_id.trim())
        if (!Number.isInteger(studentId) || studentId <= 0) {
          error.value = '学生 ID 必须为正整数。'
          submitting.value = false
          return
        }
        payload.student = studentId
      }
      if (form.catalog_version.trim()) payload.catalog_version = form.catalog_version.trim()
      if (form.task_key.trim()) payload.task_key = form.task_key.trim()
      if (form.task_version.trim()) payload.task_version = form.task_version.trim()
    }
    const res = await service.feedback.create(payload)
    savePending.value = false
    lastCreatedId.value = res.feedback_id
    message.value = res.idempotent_replay
      ? '该提交已处理，返回原反馈记录。'
      : `反馈已保存：${res.status_label}。${res.missing_evidence?.length ? '仍有待补证据。' : ''}`
    form.dispute = ''
    form.expected_result = ''
    form.reason = ''
    form.original_decision_ref = ''
    form.original_decision_version = ''
    form.attempt_id = ''
    form.attempt_uuid = ''
    form.student_id = ''
    form.catalog_version = ''
    form.task_key = ''
    form.task_version = ''
    for (const key of Object.keys(evidenceDraft)) delete evidenceDraft[key]
    clientRequestId.value = newClientRequestId()
    ensureEvidenceSlots()
    await loadList()
  } catch (err) {
    const data = err.response?.data
    if (err.response?.status === 503 && data?.retryable) {
      savePending.value = true
      error.value = `${data.detail}（客户端提交标识：${data.client_request_id}）`
    } else {
      error.value = data?.detail || data?.issue_type?.[0] || '保存失败，请检查输入后重试。'
    }
  } finally {
    submitting.value = false
  }
}

watch(requiredSlots, ensureEvidenceSlots, { immediate: true })
watch(() => form.category, () => {
  if (!issueTypes.value.some((item) => item.value === form.issue_type)) {
    form.issue_type = issueTypes.value[0]?.value || ''
  }
  ensureEvidenceSlots()
})

onMounted(loadAll)
</script>

<style src="@/assets/feedback.css"></style>
