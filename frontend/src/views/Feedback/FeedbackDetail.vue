<template>
  <div class="fb-page">
    <div class="fb-header">
      <div>
        <span class="fb-eyebrow">模块七 · 反馈详情</span>
        <h1 class="fb-title">{{ detail ? `${detail.category_label} · ${detail.issue_type_label}` : '反馈详情' }}</h1>
        <p class="fb-sub" v-if="detail">
          反馈 ID：<span class="fb-badge fb-badge-muted">{{ detail.feedback_id }}</span>
          提交于 {{ formatDate(detail.created_at) }}
        </p>
      </div>
      <div class="fb-actions">
        <router-link to="/feedback" class="fb-btn">返回反馈中心</router-link>
      </div>
    </div>

    <div v-if="error" class="fb-error">{{ error }}</div>
    <div v-if="message" class="fb-success">{{ message }}</div>

    <div v-if="!detail" class="fb-empty">正在读取反馈详情...</div>
    <template v-else>
      <div class="fb-notice">
        <strong>处理状态与规则生效分开。</strong>
        当前工单状态：{{ detail.status_label }}；教学效果：{{ detail.effect_status_label }}。
        处理完成不等于教学效果已验证，也不等于新规则已生效。原始判定与历史结论保留。
      </div>

      <div class="fb-grid">
        <section class="fb-panel">
          <h2>工单摘要</h2>
          <div class="fb-row"><span>状态</span><strong>{{ detail.status_label }}</strong></div>
          <div class="fb-row"><span>任务</span><strong>{{ detail.task_title || '未关联' }} · {{ detail.task_version || '—' }}</strong></div>
          <div class="fb-row"><span>尝试</span><strong>{{ detail.attempt_status || '未关联' }}</strong></div>
          <div class="fb-row"><span>能力/知识点</span><strong>{{ detail.capability_title || detail.knowledge_point_name || '未映射' }}</strong></div>
          <div class="fb-row"><span>处理去向</span><strong>{{ detail.handling_destination_label }}</strong></div>
          <div class="fb-row"><span>责任人</span><strong>{{ detail.owner_name || '未分配' }}（{{ detail.owner_role_label }}）</strong></div>
          <div class="fb-row"><span>候选依据</span><strong>{{ detail.candidate_eligible ? '满足' : '不满足' }}</strong></div>
          <div class="fb-row"><span>重复记录</span><strong>{{ detail.duplicate_of || '否' }}</strong></div>

          <h3>具体争议</h3>
          <p class="fb-pre">{{ detail.dispute }}</p>
          <h3>期望结果</h3>
          <p class="fb-pre">{{ detail.expected_result || '—' }}</p>
          <h3>理由</h3>
          <p class="fb-pre">{{ detail.reason || '—' }}</p>

          <div v-if="detail.missing_evidence_labels?.length" class="fb-missing">
            <strong>待补证</strong>
            <ul>
              <li v-for="label in detail.missing_evidence_labels" :key="label">{{ label }}</li>
            </ul>
          </div>
          <div v-if="detail.missing_mapping?.length" class="fb-missing">
            <strong>未映射字段</strong>
            <ul>
              <li v-for="field in detail.missing_mapping" :key="field">{{ field }}</li>
            </ul>
          </div>
        </section>

        <section class="fb-panel">
          <h2>证据</h2>
          <p class="fb-muted">只显示你有权查看的证据；教师专用附件和内部备注不会展示。</p>
          <div v-if="!detail.evidence?.length" class="fb-empty">暂无证据。</div>
          <div v-else class="fb-list">
            <article v-for="item in detail.evidence" :key="item.evidence_id" class="fb-card">
              <div class="fb-card-head">
                <strong>{{ item.slot_label }}</strong>
                <span class="fb-badge" :class="item.status === 'provided' ? 'fb-badge-ok' : 'fb-badge-warn'">
                  {{ item.status_label }}
                </span>
              </div>
              <p class="fb-muted">{{ item.summary || '—' }}</p>
              <div class="fb-meta">
                <span>版本：{{ item.version || '—' }}</span>
                <span>来源：{{ item.source_label }}</span>
                <span v-if="item.ref">引用：{{ item.ref }}</span>
              </div>
              <div v-if="item.attachment" class="fb-actions">
                <button class="fb-btn" type="button" @click="download(item.attachment)">
                  下载 {{ item.attachment.original_name }}
                </button>
              </div>
            </article>
          </div>
        </section>
      </div>

      <section class="fb-panel">
        <h2>补充证据</h2>
        <p class="fb-muted">
          新证据会追加为当前版本，原证据保留；若工单已驳回或已处理，会重新进入待复核。
          重复记录请到主记录补充。
        </p>
        <div class="fb-form-grid">
          <label>
            证据槽
            <select v-model="evidenceForm.slot" class="fb-select">
              <option v-for="slot in slotOptions" :key="slot.slot" :value="slot.slot">
                {{ slot.label }}{{ detail.missing_evidence?.includes(slot.slot) ? '（缺失）' : '' }}
              </option>
            </select>
          </label>
          <label>
            版本
            <input v-model="evidenceForm.version" class="fb-input" placeholder="如 v2" />
          </label>
          <label class="fb-full">
            证据引用
            <input v-model="evidenceForm.ref" class="fb-input" placeholder="受控证据引用，不要粘贴答案正文" />
          </label>
          <label class="fb-full">
            必要摘要
            <textarea v-model="evidenceForm.summary" class="fb-textarea" rows="3"></textarea>
          </label>
          <label class="fb-full">
            附件（可选）
            <select v-model="evidenceForm.attachment_id" class="fb-select">
              <option value="">不关联附件</option>
              <option v-for="attachment in detail.attachments" :key="attachment.attachment_id" :value="attachment.attachment_id">
                {{ attachment.original_name }}
              </option>
            </select>
          </label>
        </div>
        <div class="fb-actions">
          <button class="fb-btn fb-btn-primary" type="button" :disabled="submitting" @click="addEvidence">
            {{ submitting ? '保存中...' : '追加证据并申请复核' }}
          </button>
        </div>

        <h3>上传受控附件</h3>
        <p class="fb-muted">
          支持 PDF、PNG、JPG、TXT、CSV、JSON、Markdown，单文件不超过 10 MB。附件只通过鉴权下载接口访问。
        </p>
        <div class="fb-form-grid">
          <label class="fb-full">
            文件
            <input class="fb-input" type="file" @change="onFileChange" />
          </label>
          <label>
            可见范围
            <select v-model="uploadVisibility" class="fb-select">
              <option value="student">学生可见</option>
            </select>
          </label>
        </div>
        <div class="fb-actions">
          <button class="fb-btn" type="button" :disabled="uploading || !uploadFile" @click="upload">
            {{ uploading ? '上传中...' : '上传附件' }}
          </button>
        </div>
      </section>

      <section class="fb-panel">
        <h2>处理记录</h2>
        <div v-if="!detail.actions?.length" class="fb-empty">暂无处理记录。</div>
        <div v-else class="fb-timeline">
          <div v-for="action in detail.actions" :key="action.action_id" class="fb-timeline-item" :class="{ 'is-current': action.to_status === detail.status }">
            <div class="fb-inline">
              <strong>{{ action.action_label }}</strong>
              <span class="fb-badge fb-badge-muted">{{ action.from_status_label || '—' }} → {{ action.to_status_label || '—' }}</span>
              <span class="fb-muted">{{ formatDate(action.created_at) }} · {{ action.actor_name }}</span>
            </div>
            <p class="fb-muted" v-if="action.reason">{{ action.reason }}</p>
          </div>
        </div>
      </section>

      <section class="fb-panel">
        <h2>复核结论</h2>
        <div v-if="!detail.reviews?.length" class="fb-empty">尚无复核结论。</div>
        <div v-else class="fb-list">
          <article v-for="review in detail.reviews" :key="review.review_id" class="fb-card">
            <div class="fb-card-head">
              <strong>{{ review.conclusion_label }}</strong>
              <span class="fb-badge" :class="review.is_current ? 'fb-badge-info' : 'fb-badge-muted'">
                {{ review.is_current ? '当前结论' : '历史结论' }}
              </span>
            </div>
            <p class="fb-muted">{{ review.reason }}</p>
            <div class="fb-meta">
              <span>复核人：{{ review.reviewer_name }}</span>
              <span>工单版本：{{ review.ticket_version }}</span>
              <span>{{ formatDate(review.created_at) }}</span>
            </div>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import service from '@/api'

const route = useRoute()
const detail = ref(null)
const options = reactive({ categories: [], conditional_slots: [] })
const error = ref('')
const message = ref('')
const submitting = ref(false)
const uploading = ref(false)
const uploadFile = ref(null)
const uploadVisibility = ref('student')
const evidenceForm = reactive({
  slot: '',
  ref: '',
  version: '',
  summary: '',
  attachment_id: '',
})

const slotOptions = computed(() => {
  if (!detail.value) return []
  const category = options.categories.find((item) => item.value === detail.value.category)
  const slots = [...(category?.required_slots || [])]
  const conditional = options.conditional_slots.find(
    (item) => item.category === detail.value.category && item.issue_type === detail.value.issue_type,
  )
  if (conditional) {
    for (const slot of conditional.slots) {
      if (!slots.some((item) => item.slot === slot.slot)) slots.push(slot)
    }
  }
  return slots
})

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

async function load() {
  error.value = ''
  try {
    const [detailRes, optionsRes] = await Promise.all([
      service.feedback.detail(route.params.id),
      service.feedback.options(),
    ])
    detail.value = detailRes
    Object.assign(options, optionsRes)
    if (!evidenceForm.slot) {
      evidenceForm.slot = detailRes.missing_evidence?.[0] || slotOptions.value[0]?.slot || ''
    }
  } catch (err) {
    error.value = err.response?.data?.detail || '加载反馈详情失败。'
  }
}

async function addEvidence() {
  error.value = ''
  message.value = ''
  if (!evidenceForm.slot) {
    error.value = '请选择证据槽。'
    return
  }
  submitting.value = true
  try {
    const item = {
      slot: evidenceForm.slot,
      ref: evidenceForm.ref.trim(),
      version: evidenceForm.version.trim(),
      summary: evidenceForm.summary.trim(),
    }
    if (evidenceForm.attachment_id) item.attachment_id = evidenceForm.attachment_id
    const res = await service.feedback.addEvidence(detail.value.feedback_id, { items: [item] })
    detail.value = res
    message.value = '证据已追加；原证据与原始判定保留。'
    evidenceForm.ref = ''
    evidenceForm.version = ''
    evidenceForm.summary = ''
    evidenceForm.attachment_id = ''
  } catch (err) {
    error.value = err.response?.data?.detail || '补充证据失败。'
  } finally {
    submitting.value = false
  }
}

function onFileChange(event) {
  uploadFile.value = event.target.files?.[0] || null
}

async function upload() {
  error.value = ''
  message.value = ''
  if (!uploadFile.value) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value)
    formData.append('visibility', uploadVisibility.value)
    await service.feedback.uploadAttachment(detail.value.feedback_id, formData)
    message.value = '附件已上传；可在“补充证据”中关联。'
    uploadFile.value = null
    await load()
  } catch (err) {
    error.value = err.response?.data?.detail || '上传附件失败。'
  } finally {
    uploading.value = false
  }
}

async function download(attachment) {
  try {
    const response = await service.feedback.downloadAttachment(detail.value.feedback_id, attachment.attachment_id)
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = attachment.original_name
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    error.value = err.response?.data?.detail || '下载附件失败。'
  }
}

onMounted(load)
</script>

<style src="@/assets/feedback.css"></style>
