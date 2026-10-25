<template>
  <div class="fb-page">
    <div class="fb-header">
      <div>
        <span class="fb-eyebrow">模块七 · 教师处理</span>
        <h1 class="fb-title">{{ detail ? `${detail.category_label} · ${detail.issue_type_label}` : '反馈处理' }}</h1>
        <p class="fb-sub" v-if="detail">
          反馈 ID：<span class="fb-badge fb-badge-muted">{{ detail.feedback_id }}</span>
          学生：{{ detail.student_name }} · 工单版本：{{ detail.version }} · 状态：{{ detail.status_label }}
        </p>
      </div>
      <div class="fb-actions">
        <router-link to="/teacher/feedback" class="fb-btn">返回待办</router-link>
        <button class="fb-btn" type="button" @click="load">刷新</button>
      </div>
    </div>

    <div class="fb-notice">
      <strong>处理完成不等于教学效果已验证，也不等于新规则已生效。</strong>
      本页只记录人工处理、证据和转交；不会修改学生成绩、模块六核验事实或生产策略。
      评分争议交模块六，目录/推荐问题交模块一，技术故障交平台维护。
    </div>

    <div v-if="error" class="fb-error">{{ error }}</div>
    <div v-if="message" class="fb-success">{{ message }}</div>
    <div v-if="!detail" class="fb-empty">正在读取反馈详情...</div>

    <template v-else>
      <div class="fb-grid">
        <section class="fb-panel">
          <h2>工单摘要</h2>
          <div class="fb-row"><span>状态</span><strong>{{ detail.status_label }}</strong></div>
          <div class="fb-row"><span>学生/提交人</span><strong>{{ detail.student_name }} / {{ detail.submitter_name }}（{{ detail.submitter_role }}）</strong></div>
          <div class="fb-row"><span>目录/任务</span><strong>{{ detail.catalog_version || '—' }} · {{ detail.task_key || '—' }}@{{ detail.task_version || '—' }}</strong></div>
          <div class="fb-row"><span>尝试</span><strong>{{ detail.attempt_id || detail.attempt_ref || '未映射' }}</strong></div>
          <div class="fb-row"><span>能力/知识点</span><strong>{{ detail.capability_id || '—' }} / {{ detail.knowledge_point_id || '—' }}</strong></div>
          <div class="fb-row"><span>处理去向</span><strong>{{ detail.handling_destination_label }}</strong></div>
          <div class="fb-row"><span>责任人</span><strong>{{ detail.owner_name || '未分配' }}（{{ detail.owner_role_label }}）</strong></div>
          <div class="fb-row"><span>证据/映射</span><strong>{{ detail.evidence_complete ? '完整' : '缺证' }} / {{ detail.mapping_complete ? '完整' : '未映射' }}</strong></div>
          <div class="fb-row"><span>候选依据</span><strong>{{ detail.candidate_eligible ? '满足' : '不满足' }}</strong></div>
          <div class="fb-row"><span>教学效果</span><strong>{{ detail.effect_status_label }}</strong></div>
          <div class="fb-row"><span>重复记录</span><strong>{{ detail.duplicate_of || '否' }}（{{ detail.duplicate_count }} 条重复）</strong></div>

          <h3>具体争议</h3>
          <p class="fb-pre">{{ detail.dispute }}</p>
          <h3>期望结果 / 理由</h3>
          <p class="fb-pre">{{ detail.expected_result || '—' }}
{{ detail.reason || '—' }}</p>

          <div v-if="detail.missing_evidence_labels?.length" class="fb-missing">
            <strong>缺失证据</strong>
            <ul>
              <li v-for="label in detail.missing_evidence_labels" :key="label">{{ label }}</li>
            </ul>
          </div>
          <div v-if="detail.missing_mapping?.length" class="fb-missing">
            <strong>未映射字段</strong>
            <ul><li v-for="field in detail.missing_mapping" :key="field">{{ field }}</li></ul>
          </div>
        </section>

        <section class="fb-panel">
          <h2>证据与附件</h2>
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
                <span>引用：{{ item.ref || '—' }}</span>
                <span>版本：{{ item.version || '—' }}</span>
                <span>来源：{{ item.source_label }}</span>
                <span>可见：{{ item.visibility_label }}</span>
              </div>
              <div v-if="item.attachment" class="fb-actions">
                <button class="fb-btn" type="button" @click="download(item.attachment)">下载 {{ item.attachment.original_name }}</button>
              </div>
            </article>
          </div>

          <h3>原始判定摘要</h3>
          <pre class="fb-pre">{{ pretty(detail.original_decision_snapshot) }}</pre>
          <h3>提交时上下文</h3>
          <pre class="fb-pre">{{ pretty(detail.context_snapshot) }}</pre>
        </section>
      </div>

      <section class="fb-panel">
        <h2>人工处理动作</h2>
        <p class="fb-muted">每个动作都需要当前工单版本，服务端会拒绝并发覆盖。理由、证据和责任人会写入追加动作记录。</p>

        <details class="fb-card" style="margin-bottom: 10px;">
          <summary><strong>认领 / 分配</strong></summary>
          <div class="fb-actions">
            <button class="fb-btn fb-btn-primary" type="button" @click="run('claim', { reason: '负责人认领待办。' })">认领给自己</button>
          </div>
          <div class="fb-form-grid" style="margin-top: 10px;">
            <label>管理员分配给用户 ID<input v-model="actionForms.assign.owner_id" class="fb-input" /></label>
            <label>责任角色
              <select v-model="actionForms.assign.owner_role" class="fb-select">
                <option v-for="item in options.owner_roles" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="fb-full">理由<textarea v-model="actionForms.assign.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="run('assign', actionForms.assign)">分配</button>
          </div>
        </details>

        <details class="fb-card" style="margin-bottom: 10px;">
          <summary><strong>登记冲突 / 影响 / 新颖性</strong></summary>
          <div class="fb-form-grid">
            <label>影响
              <select v-model="actionForms.triage.impact_level" class="fb-select">
                <option v-for="item in options.impact_levels" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label>新颖性
              <select v-model="actionForms.triage.novelty" class="fb-select">
                <option v-for="item in options.novelty" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="fb-check"><input v-model="actionForms.triage.conflict_flag" type="checkbox" /> 存在证据冲突</label>
            <label class="fb-full">理由<textarea v-model="actionForms.triage.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions"><button class="fb-btn" type="button" @click="run('triage', actionForms.triage)">保存优先级</button></div>
        </details>

        <details class="fb-card" style="margin-bottom: 10px;">
          <summary><strong>要求补证</strong></summary>
          <p class="fb-muted">只选择确实缺失的必需证据；补证责任人、期限和理由会保留。</p>
          <div class="fb-missing" v-if="detail.missing_evidence?.length">
            <label v-for="slot in detail.missing_evidence" :key="slot" class="fb-check" style="display:flex; margin: 4px 0;">
              <input v-model="selectedMissing" type="checkbox" :value="slot" />
              {{ slotLabel(slot) }}
            </label>
          </div>
          <div v-else class="fb-muted">当前没有缺失证据槽。</div>
          <div class="fb-form-grid">
            <label>补证责任人 ID<input v-model="actionForms.request.owner_id" class="fb-input" /></label>
            <label>期限<input v-model="actionForms.request.due_at" class="fb-input" placeholder="2026-11-01T18:00:00+08:00" /></label>
            <label class="fb-full">理由<textarea v-model="actionForms.request.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="requestEvidence">要求补证</button>
          </div>
        </details>

        <details class="fb-card" style="margin-bottom: 10px;">
          <summary><strong>确认 / 驳回</strong></summary>
          <div class="fb-form-grid">
            <label>处理去向
              <select v-model="actionForms.confirm.handling_destination" class="fb-select">
                <option v-for="item in options.destinations" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label>责任角色
              <select v-model="actionForms.confirm.owner_role" class="fb-select">
                <option v-for="item in options.owner_roles" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="fb-full">引用证据（逗号分隔）<input v-model="actionForms.confirm.evidence_refs" class="fb-input" /></label>
            <label class="fb-full">确认理由<textarea v-model="actionForms.confirm.reason" class="fb-textarea" rows="2"></textarea></label>
            <label class="fb-full">驳回理由<textarea v-model="actionForms.reject.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn fb-btn-primary" type="button" @click="confirmTicket">确认</button>
            <button class="fb-btn fb-btn-danger" type="button" @click="run('reject', { reason: actionForms.reject.reason, evidence_refs: splitRefs(actionForms.confirm.evidence_refs) })">驳回</button>
          </div>
        </details>

        <details class="fb-card" style="margin-bottom: 10px;">
          <summary><strong>追加复核更正</strong></summary>
          <p class="fb-muted">只追加新结论，原复核人、理由、时间和原始判定保留。</p>
          <div class="fb-form-grid">
            <label>新结论
              <select v-model="actionForms.revise.conclusion" class="fb-select">
                <option value="confirmed">已确认</option>
                <option value="rejected">已驳回</option>
              </select>
            </label>
            <label class="fb-full">引用证据<input v-model="actionForms.revise.evidence_refs" class="fb-input" /></label>
            <label class="fb-full">更正理由<textarea v-model="actionForms.revise.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="run('revise_review', { conclusion: actionForms.revise.conclusion, reason: actionForms.revise.reason, evidence_refs: splitRefs(actionForms.revise.evidence_refs) })">追加更正</button>
          </div>
        </details>

        <details class="fb-card" style="margin-bottom: 10px;">
          <summary><strong>开始人工处理</strong></summary>
          <div class="fb-form-grid">
            <label>处理动作<input v-model="actionForms.handling.handling_action" class="fb-input" placeholder="补充解释 / 安排审核任务 / 转交" /></label>
            <label>处理去向
              <select v-model="actionForms.handling.handling_destination" class="fb-select">
                <option v-for="item in options.destinations" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="fb-full">处理说明<textarea v-model="actionForms.handling.handling_note" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn fb-btn-primary" type="button" @click="run('start_handling', actionForms.handling)">开始处理</button>
          </div>
        </details>

        <details class="fb-card" style="margin-bottom: 10px;">
          <summary><strong>转交 / 接收确认</strong></summary>
          <p class="fb-muted">评分争议必须转模块六；目录/推荐问题转模块一；技术故障转平台维护。接收方确认前不能标记已处理。</p>
          <div class="fb-form-grid">
            <label>转交去向
              <select v-model="actionForms.refer.destination" class="fb-select">
                <option value="module6">模块六</option>
                <option value="module1">模块一</option>
                <option value="course_material">课程材料</option>
                <option value="platform">平台维护</option>
              </select>
            </label>
            <label>接收方引用<input v-model="actionForms.refer.external_ref" class="fb-input" /></label>
            <label class="fb-full">转交说明<textarea v-model="actionForms.refer.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="run('refer', { destination: actionForms.refer.destination, reason: actionForms.refer.reason, external_ref: actionForms.refer.external_ref })">登记转交</button>
          </div>
          <div v-if="pendingReferrals.length" class="fb-form-grid" style="margin-top: 10px;">
            <label>待确认转交
              <select v-model="actionForms.ack.referral_id" class="fb-select">
                <option value="">请选择</option>
                <option v-for="referral in pendingReferrals" :key="referral.referral_id" :value="referral.referral_id">
                  {{ referral.destination_label }} · {{ referral.referral_id }}
                </option>
              </select>
            </label>
            <label>接收方引用<input v-model="actionForms.ack.external_ref" class="fb-input" /></label>
            <label class="fb-full">确认说明<textarea v-model="actionForms.ack.ack_note" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="run('ack_referral', { referral_id: actionForms.ack.referral_id, referral_status: 'acknowledged', ack_note: actionForms.ack.ack_note, external_ref: actionForms.ack.external_ref })">确认接收</button>
            <button class="fb-btn fb-btn-danger" type="button" @click="run('ack_referral', { referral_id: actionForms.ack.referral_id, referral_status: 'declined', ack_note: actionForms.ack.ack_note || '接收方退回。', external_ref: actionForms.ack.external_ref })">退回转交</button>
          </div>
        </details>

        <details class="fb-card" style="margin-bottom: 10px;">
          <summary><strong>标记已处理 / 登记教学效果</strong></summary>
          <p class="fb-muted">所有转交必须已确认接收才能标记已处理。教学效果单独登记，不随工单关闭自动变成“已验证”。</p>
          <div class="fb-form-grid">
            <label class="fb-full">处理说明<textarea v-model="actionForms.handle.handling_note" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn fb-btn-primary" type="button" @click="run('handle', { handling_note: actionForms.handle.handling_note })">标记已处理</button>
          </div>
          <div class="fb-form-grid" style="margin-top: 10px;">
            <label>教学效果
              <select v-model="actionForms.effect.effect_status" class="fb-select">
                <option v-for="item in options.effect_statuses" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label>复测事实 ID<input v-model="actionForms.effect.retest_fact_ref" class="fb-input" /></label>
            <label>复测尝试 ID<input v-model="actionForms.effect.retest_attempt_ref" class="fb-input" /></label>
            <label class="fb-full">效果说明<textarea v-model="actionForms.effect.effect_note" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="run('set_effect', actionForms.effect)">登记教学效果</button>
          </div>
        </details>

        <details class="fb-card" style="margin-bottom: 10px;">
          <summary><strong>重开 / 内部备注 / 重复处理</strong></summary>
          <div class="fb-form-grid">
            <label class="fb-full">重开理由<textarea v-model="actionForms.reopen.reason" class="fb-textarea" rows="2"></textarea></label>
            <label class="fb-full">内部备注（仅教师可见）<textarea v-model="actionForms.note.reason" class="fb-textarea" rows="2"></textarea></label>
            <label>主记录反馈 ID<input v-model="actionForms.duplicate.main_ticket_id" class="fb-input" /></label>
            <label class="fb-full">重复处理理由<textarea v-model="actionForms.duplicate.reason" class="fb-textarea" rows="2"></textarea></label>
          </div>
          <div class="fb-actions">
            <button class="fb-btn" type="button" @click="run('reopen', { reason: actionForms.reopen.reason })">重开</button>
            <button class="fb-btn" type="button" @click="run('note', { reason: actionForms.note.reason })">保存内部备注</button>
            <button class="fb-btn" type="button" @click="run('confirm_duplicate', { main_ticket_id: actionForms.duplicate.main_ticket_id, reason: actionForms.duplicate.reason })">确认重复</button>
            <button class="fb-btn" type="button" @click="run('split_duplicate', { reason: actionForms.duplicate.reason || '拆分重复记录。' })">拆分重复</button>
          </div>
        </details>
      </section>

      <section class="fb-panel">
        <h2>复核与转交记录</h2>
        <h3>复核结论</h3>
        <div v-if="!detail.reviews?.length" class="fb-empty">暂无复核结论。</div>
        <div v-else class="fb-list">
          <article v-for="review in detail.reviews" :key="review.review_id" class="fb-card">
            <div class="fb-card-head">
              <strong>{{ review.conclusion_label }}</strong>
              <span class="fb-badge" :class="review.is_current ? 'fb-badge-info' : 'fb-badge-muted'">{{ review.is_current ? '当前' : '历史' }}</span>
            </div>
            <p class="fb-muted">{{ review.reason }}</p>
            <div class="fb-meta">
              <span>复核人：{{ review.reviewer_name }}</span>
              <span>版本：{{ review.ticket_version }}</span>
              <span>{{ formatDate(review.created_at) }}</span>
            </div>
          </article>
        </div>
        <h3>转交</h3>
        <div v-if="!detail.referrals?.length" class="fb-empty">暂无转交记录。</div>
        <div v-else class="fb-list">
          <article v-for="referral in detail.referrals" :key="referral.referral_id" class="fb-card">
            <div class="fb-card-head">
              <strong>{{ referral.destination_label }}</strong>
              <span class="fb-badge" :class="referral.status === 'acknowledged' ? 'fb-badge-ok' : 'fb-badge-warn'">{{ referral.status_label }}</span>
            </div>
            <p class="fb-muted">{{ referral.note || '—' }}</p>
            <div class="fb-meta">
              <span>接收引用：{{ referral.external_ref || '—' }}</span>
              <span>{{ formatDate(referral.created_at) }}</span>
            </div>
          </article>
        </div>
        <h3>事件核对</h3>
        <p class="fb-muted">状态变更必须对应统一学习事件；待重试链接可重试，内容不一致需人工核对。</p>
        <div class="fb-actions">
          <button class="fb-btn" type="button" @click="retryEvents">重试待同步事件</button>
        </div>
        <pre class="fb-pre">{{ pretty(detail.reconciliation) }}</pre>
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
const error = ref('')
const message = ref('')
const selectedMissing = ref([])
const options = reactive({
  categories: [],
  conditional_slots: [],
  destinations: [],
  owner_roles: [],
  impact_levels: [],
  novelty: [],
  effect_statuses: [],
})

const actionForms = reactive({
  assign: { owner_id: '', owner_role: 'teacher', reason: '' },
  triage: { impact_level: 'unknown', novelty: 'unknown', conflict_flag: false, reason: '' },
  request: { owner_id: '', due_at: '', reason: '' },
  confirm: { handling_destination: '', owner_role: '', evidence_refs: '', reason: '' },
  reject: { reason: '' },
  revise: { conclusion: 'confirmed', evidence_refs: '', reason: '' },
  handling: { handling_action: '', handling_note: '', handling_destination: '' },
  refer: { destination: 'module6', reason: '', external_ref: '' },
  ack: { referral_id: '', ack_note: '', external_ref: '' },
  handle: { handling_note: '' },
  effect: { effect_status: 'awaiting_retest', effect_note: '', retest_fact_ref: '', retest_attempt_ref: '' },
  reopen: { reason: '' },
  note: { reason: '' },
  duplicate: { main_ticket_id: '', reason: '' },
})

const pendingReferrals = computed(() => (detail.value?.referrals || []).filter((item) => item.status === 'pending_ack'))

function slotLabel(slot) {
  const category = options.categories.find((item) => item.value === detail.value?.category)
  const all = [...(category?.required_slots || [])]
  const conditional = options.conditional_slots.find(
    (item) => item.category === detail.value?.category && item.issue_type === detail.value?.issue_type,
  )
  if (conditional) all.push(...conditional.slots)
  return all.find((item) => item.slot === slot)?.label || slot
}

function splitRefs(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function pretty(value) {
  if (value === undefined || value === null) return '—'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

async function load() {
  error.value = ''
  try {
    const [detailRes, optionsRes] = await Promise.all([
      service.feedback.teacherDetail(route.params.id),
      service.feedback.options(),
    ])
    detail.value = detailRes
    Object.assign(options, optionsRes)
    selectedMissing.value = [...(detailRes.missing_evidence || [])]
    if (!actionForms.confirm.handling_destination) {
      actionForms.confirm.handling_destination = detailRes.handling_destination || 'unassigned'
    }
    if (!actionForms.handling.handling_destination) {
      actionForms.handling.handling_destination = detailRes.handling_destination || 'unassigned'
    }
    if (!actionForms.confirm.owner_role) actionForms.confirm.owner_role = detailRes.owner_role || 'teacher'
    if (!actionForms.ack.referral_id && pendingReferrals.value.length) {
      actionForms.ack.referral_id = pendingReferrals.value[0].referral_id
    }
  } catch (err) {
    error.value = err.response?.data?.detail || '加载反馈详情失败。'
  }
}

async function run(action, payload = {}) {
  error.value = ''
  message.value = ''
  try {
    const res = await service.feedback.teacherAction(detail.value.feedback_id, {
      action,
      expected_version: detail.value.version,
      ...payload,
    })
    detail.value = res
    message.value = `动作已记录：${action}；当前状态：${res.status_label}。`
    selectedMissing.value = [...(res.missing_evidence || [])]
    await load()
  } catch (err) {
    const data = err.response?.data
    error.value = data?.detail
      || (data && typeof data === 'object' ? JSON.stringify(data) : '处理动作失败。')
  }
}

function requestEvidence() {
  if (!selectedMissing.value.length) {
    error.value = '请选择需要补充的证据槽。'
    return
  }
  run('request_evidence', {
    missing_slots: selectedMissing.value,
    due_at: actionForms.request.due_at || null,
    owner_id: actionForms.request.owner_id || null,
    reason: actionForms.request.reason,
  })
}

function confirmTicket() {
  run('confirm', {
    reason: actionForms.confirm.reason,
    handling_destination: actionForms.confirm.handling_destination,
    owner_role: actionForms.confirm.owner_role,
    evidence_refs: splitRefs(actionForms.confirm.evidence_refs),
  })
}

async function retryEvents() {
  error.value = ''
  message.value = ''
  try {
    await service.feedback.retryEvents({ ticket_id: detail.value.feedback_id })
    message.value = '事件同步重试完成；请查看核对结果。'
    await load()
  } catch (err) {
    error.value = err.response?.data?.detail || '事件同步重试失败。'
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
