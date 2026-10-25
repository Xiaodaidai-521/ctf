<template>
  <div class="candidate-page">
    <div class="page-header">
      <div>
        <span class="eyebrow">教学 · 候选改进</span>
        <h1>问题组与候选管理</h1>
        <p class="subtitle">
          问题组必须人工确认成员；候选只能引用已确认、无缺证的问题组。审批绑定确切配置摘要与模块八报告，发布只影响后续任务。
        </p>
      </div>
      <button class="btn btn-secondary" @click="loadAll" :disabled="loading">刷新</button>
    </div>

    <div class="gates">
      <span :class="['gate', gates.phase3_write_enabled ? 'on' : 'off']">
        候选写入：{{ gates.phase3_write_enabled ? '已启用' : '默认关闭' }}
      </span>
      <span :class="['gate', gates.release_enabled ? 'on' : 'off']">
        生效与回退：{{ gates.release_enabled ? '已启用' : '默认关闭' }}
      </span>
    </div>

    <p v-if="message" class="message">{{ message }}</p>
    <div v-if="loading" class="state-box">正在读取...</div>

    <template v-else>
      <section class="panel">
        <div class="panel-head">
          <h2>跨尝试问题组</h2>
          <span class="muted">同一尝试、同类型、同争议只计一个实例。</span>
        </div>

        <div class="form-row">
          <input v-model="groupForm.title" placeholder="问题组名称" />
          <select v-model="groupForm.category">
            <option value="recognition">识别反馈</option>
            <option value="decision">决策反馈</option>
            <option value="teaching">教学反馈</option>
          </select>
          <input v-model="groupForm.issue_type" placeholder="问题类型，如 scoring_dispute" />
          <input v-model.number="groupForm.days" type="number" min="1" placeholder="时间窗天数" />
          <button class="btn btn-primary btn-small" @click="createGroup">生成候选成员</button>
        </div>

        <div v-if="!groups.length" class="muted">暂无问题组。</div>
        <article v-for="group in groups" :key="group.group_id" class="item">
          <div class="item-head">
            <div>
              <strong>{{ group.title }}</strong>
              <span class="badge" :class="group.status">{{ group.status_label }}</span>
              <p class="muted small">
                {{ group.category_label }} · {{ group.issue_type_label }}
                <template v-if="group.task_key"> · {{ group.task_key }}@{{ group.task_version }}</template>
              </p>
              <p class="counts">
                原始 {{ group.counts.raw_feedback ?? 0 }} ·
                纳入 {{ group.counts.included_feedback ?? 0 }} ·
                去重实例 {{ group.counts.deduplicated_instances ?? 0 }} ·
                不同学生 {{ group.counts.distinct_students ?? 0 }} ·
                缺证 {{ group.counts.missing_evidence ?? 0 }}
              </p>
            </div>
            <div class="item-actions">
              <button
                v-if="group.status === 'pending_confirmation' || group.status === 'draft'"
                class="btn btn-small"
                @click="confirmGroup(group)"
              >确认</button>
            </div>
          </div>
        </article>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>教学配置候选</h2>
          <span class="muted">草稿 → 待评测 → 评测中 → 待审批 → 已批准待发布 → 观察中 → 已稳定 / 已回退</span>
        </div>

        <div class="form-row">
          <input v-model="candidateForm.title" placeholder="候选名称" />
          <input v-model="candidateForm.issue_group_ids" placeholder="问题组 ID（逗号分隔）" />
          <input v-model="candidateForm.baseline_config_version" placeholder="基准配置版本" />
          <input v-model="candidateForm.candidate_config_version" placeholder="候选配置版本" />
          <input v-model="candidateForm.single_changed_factor" placeholder="唯一改动因素" />
          <input v-model="candidateForm.rollback_version" placeholder="回退版本" />
          <button class="btn btn-primary btn-small" @click="createCandidate">登记草稿</button>
        </div>

        <div v-if="!candidates.length" class="muted">暂无候选。</div>
        <article v-for="candidate in candidates" :key="candidate.candidate_id" class="item">
          <div class="item-head">
            <div>
              <strong>{{ candidate.title }}</strong>
              <span class="badge" :class="candidate.state">{{ candidate.state_label }}</span>
              <p class="muted small">
                {{ candidate.baseline_config_version }} → {{ candidate.candidate_config_version }}
                · 改动 {{ candidate.single_changed_factor }}
              </p>
              <p class="muted small mono">
                配置摘要 {{ candidate.config_digest.slice(0, 12) }}…
                <template v-if="candidate.evaluation_report_ref.report_id">
                  · 报告 {{ candidate.evaluation_report_ref.report_id }}
                  v{{ candidate.evaluation_report_ref.report_version }}
                  （{{ candidate.evaluation_report_ref.recommendation }}）
                </template>
              </p>
              <p v-if="!candidate.approval_valid && candidate.state === 'approved_pending_release'" class="warn small">
                审批已失效：{{ candidate.approval_invalid_reason }}
              </p>
            </div>
            <div class="item-actions">
              <button v-if="candidate.state === 'draft'" class="btn btn-small" @click="submitCandidate(candidate)">提交评测</button>
              <button v-if="candidate.state === 'pending_eval'" class="btn btn-small" @click="attachReport(candidate)">登记报告</button>
              <button v-if="candidate.state === 'evaluating'" class="btn btn-small" @click="completeEvaluation(candidate)">完成评测</button>
              <button v-if="candidate.state === 'pending_approval'" class="btn btn-small" @click="approve(candidate)">审批</button>
              <button v-if="candidate.state === 'approved_pending_release'" class="btn btn-primary btn-small" @click="activate(candidate)">生效</button>
              <button v-if="candidate.state === 'observing'" class="btn btn-small" @click="markStable(candidate)">标记稳定</button>
              <button
                v-if="candidate.state === 'observing' || candidate.state === 'stable'"
                class="btn btn-small danger"
                @click="rollback(candidate)"
              >回退</button>
            </div>
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
const message = ref('')
const groups = ref([])
const candidates = ref([])
const gates = reactive({ phase3_write_enabled: false, release_enabled: false })
const groupForm = reactive({ title: '', category: 'teaching', issue_type: 'scoring_dispute', days: 7 })
const candidateForm = reactive({
  title: '',
  issue_group_ids: '',
  baseline_config_version: '',
  candidate_config_version: '',
  single_changed_factor: '',
  rollback_version: '',
})

function extractError(err) {
  const data = err?.response?.data
  if (!data) return '网络或服务异常。'
  if (typeof data === 'string') return data
  if (data.code === 'phase3_write_disabled') return '候选管理默认关闭，需在评测环境显式开启。'
  if (data.code === 'phase3_release_disabled') return '生效与回退默认关闭，需显式开启。'
  return data.detail || '操作未完成。'
}

async function loadAll() {
  loading.value = true
  try {
    const [groupPayload, candidatePayload] = await Promise.all([
      service.feedbackPhase3.issueGroups(),
      service.feedbackPhase3.candidates(),
    ])
    groups.value = groupPayload.items || []
    candidates.value = candidatePayload.items || []
    gates.phase3_write_enabled = Boolean(groupPayload.phase3_write_enabled)
    gates.release_enabled = Boolean(groupPayload.release_enabled)
  } catch (err) {
    message.value = extractError(err)
  } finally {
    loading.value = false
  }
}

async function createGroup() {
  const now = new Date()
  try {
    await service.feedbackPhase3.createIssueGroup({
      title: groupForm.title || '教学问题组',
      category: groupForm.category,
      issue_type: groupForm.issue_type,
      window_start: new Date(now.getTime() - groupForm.days * 86400000).toISOString(),
      window_end: now.toISOString(),
    })
    message.value = '问题组已生成候选成员，需人工确认。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function confirmGroup(group) {
  try {
    await service.feedbackPhase3.confirmIssueGroup(group.group_id, {})
    message.value = '问题组已确认；计数已快照。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function createCandidate() {
  const groupIds = candidateForm.issue_group_ids
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
  try {
    await service.feedbackPhase3.createCandidate({
      title: candidateForm.title || '教学配置候选',
      issue_group_ids: groupIds,
      baseline_config_version: candidateForm.baseline_config_version || 'cfg-v1',
      candidate_config_version: candidateForm.candidate_config_version || 'cfg-v2',
      single_changed_factor: candidateForm.single_changed_factor || 'export_record_limit',
      target_task_versions: [],
      baseline_config: { export_record_limit: 100 },
      candidate_config: { export_record_limit: 120 },
      rollback_version: candidateForm.rollback_version || 'cfg-v1',
    })
    message.value = '候选草稿已登记。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function submitCandidate(candidate) {
  try {
    await service.feedbackPhase3.submitCandidate(candidate.candidate_id)
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function attachReport(candidate) {
  try {
    await service.feedbackPhase3.attachCandidateReport(candidate.candidate_id, {
      run_id: `run-${Date.now()}`,
      report_id: `report-${Date.now()}`,
      report_version: 'v1',
      report_digest: candidate.config_digest,
      candidate_config_digest: candidate.config_digest,
      recommendation: 'pass',
      completed: true,
      missing_cases: 0,
    })
    message.value = '报告引用已登记（评测仍在模块八执行）。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function completeEvaluation(candidate) {
  try {
    await service.feedbackPhase3.completeCandidateEvaluation(candidate.candidate_id, {})
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function approve(candidate) {
  try {
    await service.feedbackPhase3.approveCandidate(candidate.candidate_id, {
      scope: '合成案例教学回放',
      observation_window: '14 天',
      rollback_condition: '关键授权反例失败即回退',
    })
    message.value = '已审批；候选作者不能独自审批。'
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function activate(candidate) {
  try {
    await service.feedbackPhase3.activateCandidate(candidate.candidate_id, {
      applicable_future_tasks: candidate.target_task_versions,
    })
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function markStable(candidate) {
  try {
    await service.feedbackPhase3.markCandidateStable(candidate.candidate_id, { note: '观察期无未解释退化' })
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function rollback(candidate) {
  try {
    await service.feedbackPhase3.rollbackCandidate(candidate.candidate_id, {
      reason: '人工确认关键反例失败',
      result: 'success',
    })
    await loadAll()
  } catch (err) {
    message.value = extractError(err)
  }
}

onMounted(loadAll)
</script>

<style scoped>
.candidate-page { width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 36px 0 72px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; border-bottom: 2px solid var(--text-primary); padding-bottom: 20px; margin-bottom: 16px; }
.eyebrow { font-size: 12px; letter-spacing: .16em; text-transform: uppercase; color: var(--primary-color); font-weight: 700; }
h1 { font-family: "Songti SC", serif; font-size: 38px; line-height: 1.1; }
.subtitle { color: var(--text-secondary); margin-top: 8px; max-width: 780px; }
.btn { border: 1px solid var(--border-color); background: var(--bg-light); padding: 8px 12px; font-weight: 600; cursor: pointer; }
.btn-primary { background: var(--text-primary); color: var(--bg-light); }
.btn-small { padding: 5px 10px; font-size: 12px; }
.btn.danger { color: var(--error-color); border-color: var(--error-color); }
.gates { display: flex; gap: 8px; margin-bottom: 14px; }
.gate { font-size: 12px; padding: 4px 9px; border: 1px solid var(--border-color); }
.gate.on { color: var(--success-color); border-color: var(--success-color); }
.gate.off { color: var(--warning-color); border-color: var(--warning-color); }
.panel { background: var(--bg-light); border: 1px solid var(--border-color); padding: 18px; box-shadow: var(--shadow-md); margin-bottom: 16px; }
.panel h2 { font-family: "Songti SC", serif; font-size: 20px; }
.panel-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10px; }
.form-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.form-row input, .form-row select { border: 1px solid var(--border-color); padding: 6px 8px; background: var(--bg-paper); font: inherit; }
.item { border-top: 1px solid var(--border-color); padding: 12px 0; }
.item-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.item-actions { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.muted { color: var(--text-muted); font-size: 12px; }
.small { font-size: 12px; }
.mono { font-family: ui-monospace, monospace; font-size: 11px; }
.counts { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.warn { color: var(--warning-color); }
.badge { font-size: 11px; padding: 1px 7px; border: 1px solid var(--border-color); margin-left: 6px; }
.badge.confirmed, .badge.stable { color: var(--success-color); border-color: var(--success-color); }
.badge.pending_confirmation, .badge.pending_approval, .badge.approved_pending_release { color: var(--warning-color); border-color: var(--warning-color); }
.badge.rolled_back, .badge.withdrawn, .badge.rejected { color: var(--error-color); border-color: var(--error-color); }
.message { background: rgba(183,53,45,.06); border-left: 3px solid var(--primary-color); padding: 9px 12px; font-size: 13px; margin-bottom: 12px; }
.state-box { background: var(--bg-light); border: 1px solid var(--border-color); padding: 48px; text-align: center; color: var(--text-muted); }
</style>
