<template>
  <div class="fb-page">
    <div class="fb-header">
      <div>
        <span class="fb-eyebrow">模块七 · 教师待办</span>
        <h1 class="fb-title">反馈待办与随机抽查</h1>
        <p class="fb-sub">
          默认按证据冲突、影响、新颖性和等待时间处理。重复投诉数量不参与正确性判断，也不能作为独立证据。
        </p>
      </div>
      <div class="fb-actions">
        <router-link to="/teacher/feedback/reconciliation" class="fb-btn">事件核对</router-link>
        <router-link to="/teacher/feedback" class="fb-btn">刷新</router-link>
      </div>
    </div>

    <div class="fb-notice">
      <strong>首期只做人工处理。</strong>
      已处理 ≠ 教学效果已验证 ≠ 新规则已生效。候选管理、审批发布和回退属于第三阶段，本轮未启用。
    </div>

    <div v-if="error" class="fb-error">{{ error }}</div>

    <section class="fb-panel">
      <div class="fb-toolbar">
        <label>
          状态
          <select v-model="filters.status" class="fb-select" @change="loadQueue">
            <option value="">全部（不含重复）</option>
            <option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label>
          类别
          <select v-model="filters.category" class="fb-select" @change="loadQueue">
            <option value="">全部</option>
            <option v-for="item in categories" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label>
          责任人
          <select v-model="filters.owner" class="fb-select" @change="loadQueue">
            <option value="">全部</option>
            <option value="me">我的</option>
            <option value="unassigned">未分配</option>
          </select>
        </label>
        <label>
          排序
          <select v-model="filters.sort" class="fb-select" @change="loadQueue">
            <option value="priority">冲突/影响/新颖性/等待</option>
            <option value="waiting">等待最久</option>
            <option value="newest">最新</option>
          </select>
        </label>
        <button class="fb-btn" type="button" @click="loadQueue">刷新</button>
      </div>

      <div class="fb-meta">
        <span v-for="(count, key) in queue.counts" :key="key" class="fb-badge" :class="count ? 'fb-badge-info' : 'fb-badge-muted'">
          {{ statusLabel(key) }}：{{ count }}
        </span>
        <span class="fb-badge fb-badge-muted">共 {{ queue.total }} 条</span>
      </div>

      <div v-if="!queue.items.length" class="fb-empty" style="margin-top: 14px;">当前没有待处理反馈。</div>
      <div v-else class="fb-list" style="margin-top: 14px;">
        <article v-for="item in queue.items" :key="item.feedback_id" class="fb-card">
          <div class="fb-card-head">
            <div>
              <div class="fb-card-title">
                <router-link :to="`/teacher/feedback/${item.feedback_id}`" class="fb-link">
                  {{ item.category_label }} · {{ item.issue_type_label }}
                </router-link>
              </div>
              <div class="fb-meta">
                <span>{{ item.student_name }}</span>
                <span>{{ item.task_title || '未关联任务' }}</span>
                <span>等待 {{ item.waiting_days }} 天</span>
                <span v-if="item.duplicate_count">重复 {{ item.duplicate_count }} 条（不增加独立证据）</span>
              </div>
            </div>
            <span class="fb-badge" :class="statusTone(item.status)">{{ item.status_label }}</span>
          </div>
          <div class="fb-meta">
            <span class="fb-badge" :class="item.conflict_flag ? 'fb-badge-danger' : 'fb-badge-muted'">
              冲突：{{ item.conflict_flag ? '有' : '无' }}
            </span>
            <span class="fb-badge" :class="item.impact_level === 'high' ? 'fb-badge-danger' : 'fb-badge-muted'">
              影响：{{ item.impact_label }}
            </span>
            <span class="fb-badge" :class="item.novelty === 'new' ? 'fb-badge-warn' : 'fb-badge-muted'">
              新颖性：{{ item.novelty_label }}
            </span>
            <span class="fb-badge fb-badge-muted">去向：{{ item.handling_destination_label }}</span>
            <span class="fb-badge fb-badge-muted">责任人：{{ item.owner_name || '未分配' }}</span>
            <span class="fb-badge" :class="item.candidate_eligible ? 'fb-badge-ok' : 'fb-badge-muted'">
              {{ item.candidate_eligible ? '可作候选依据' : '不可作候选依据' }}
            </span>
          </div>
          <p class="fb-muted" style="margin: 8px 0 0;">优先级：{{ item.priority_reason }}</p>
          <div v-if="item.missing_evidence_labels?.length" class="fb-missing">
            待补证：{{ item.missing_evidence_labels.join('、') }}
          </div>
          <div class="fb-actions">
            <router-link :to="`/teacher/feedback/${item.feedback_id}`" class="fb-btn fb-btn-primary">打开处理</router-link>
          </div>
        </article>
      </div>
    </section>

    <section class="fb-panel">
      <h2>随机抽查登记</h2>
      <p class="fb-muted">
        每批保存范围、总体摘要、随机种子、样本数量和入选原因。高风险样本单列，不作为总体错误率的随机估计。
        相同总体、范围和种子应产生相同随机样本；不足目标数量时全部查看。
      </p>
      <div class="fb-form-grid">
        <label>
          抽查状态
          <select v-model="batchForm.status" class="fb-select">
            <option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label>
          样本数量
          <input v-model.number="batchForm.sample_size" class="fb-input" type="number" min="1" />
        </label>
        <label>
          随机种子（可留空由服务端生成）
          <input v-model="batchForm.random_seed" class="fb-input" placeholder="如 20261025" />
        </label>
        <label class="fb-check" style="align-self: end;">
          <input v-model="batchForm.exclude_prior" type="checkbox" />
          排除既往样本
        </label>
        <label class="fb-full">
          高风险样本 ID（可选，逗号分隔）
          <input v-model="batchForm.risk_ticket_ids" class="fb-input" placeholder="反馈 UUID" />
        </label>
        <label class="fb-full">
          抽样依据/说明
          <textarea v-model="batchForm.notes" class="fb-textarea" rows="2"></textarea>
        </label>
      </div>
      <div class="fb-actions">
        <button class="fb-btn fb-btn-primary" type="button" :disabled="creatingBatch" @click="createBatch">
          {{ creatingBatch ? '生成中...' : '生成抽查批次' }}
        </button>
      </div>

      <div v-if="selectedBatch" class="fb-card" style="margin-top: 14px;">
        <div class="fb-card-head">
          <strong>批次 {{ selectedBatch.batch_id }}</strong>
          <span class="fb-badge fb-badge-info">{{ selectedBatch.method }}</span>
        </div>
        <div class="fb-meta">
          <span>种子：{{ selectedBatch.random_seed }}</span>
          <span>总体：{{ selectedBatch.population_count }}</span>
          <span>目标样本：{{ selectedBatch.sample_size }}</span>
          <span>实际：{{ selectedBatch.items?.length || 0 }}</span>
          <span>排除既往：{{ selectedBatch.exclude_prior ? '是' : '否' }}</span>
        </div>
        <div class="fb-table-wrap">
          <table class="fb-table">
            <thead><tr><th>反馈</th><th>入选原因</th><th>状态</th><th>优先级</th></tr></thead>
            <tbody>
              <tr v-for="item in selectedBatch.items" :key="item.ticket_id">
                <td><router-link :to="`/teacher/feedback/${item.ticket_id}`" class="fb-link">{{ item.ticket_id }}</router-link></td>
                <td>{{ item.selected_reason_label }}</td>
                <td>{{ item.status_label }}</td>
                <td>{{ item.priority_reason }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <h3>最近批次</h3>
      <div v-if="!batches.length" class="fb-empty">暂无抽查批次。</div>
      <div v-else class="fb-list">
        <article v-for="batch in batches" :key="batch.batch_id" class="fb-card">
          <div class="fb-card-head">
            <strong>{{ batch.batch_id }}</strong>
            <button class="fb-btn" type="button" @click="loadBatch(batch.batch_id)">查看明细</button>
          </div>
          <div class="fb-meta">
            <span>种子：{{ batch.random_seed }}</span>
            <span>总体：{{ batch.population_count }}</span>
            <span>目标：{{ batch.sample_size }}</span>
            <span>方法：{{ batch.method }}</span>
            <span>{{ formatDate(batch.created_at) }}</span>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import service from '@/api'

const queue = reactive({ items: [], counts: {}, total: 0 })
const statuses = ref([])
const categories = ref([])
const batches = ref([])
const selectedBatch = ref(null)
const error = ref('')
const creatingBatch = ref(false)

const filters = reactive({ status: '', category: '', owner: '', sort: 'priority' })
const batchForm = reactive({
  status: 'pending_fact_review',
  sample_size: 5,
  random_seed: '',
  exclude_prior: true,
  risk_ticket_ids: '',
  notes: '教师按冲突、影响、新颖性和等待时间处理后的随机抽查。',
})

function statusLabel(value) {
  return statuses.value.find((item) => item.value === value)?.label || value
}

function statusTone(status) {
  if (['confirmed', 'handled'].includes(status)) return 'fb-badge-ok'
  if (['pending_evidence', 'reopened', 'rejected'].includes(status)) return 'fb-badge-warn'
  return 'fb-badge-info'
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

async function loadQueue() {
  error.value = ''
  try {
    const res = await service.feedback.teacherQueue({
      status: filters.status || undefined,
      category: filters.category || undefined,
      owner: filters.owner || undefined,
      sort: filters.sort,
      page_size: 50,
    })
    Object.assign(queue, { items: res.items || [], counts: res.counts || {}, total: res.total || 0 })
  } catch (err) {
    error.value = err.response?.data?.detail || '加载教师待办失败。'
  }
}

async function loadOptions() {
  try {
    const res = await service.feedback.options()
    statuses.value = res.statuses || []
    categories.value = res.categories || []
  } catch (err) {
    error.value = err.response?.data?.detail || '加载选项失败。'
  }
}

async function loadBatches() {
  try {
    const res = await service.feedback.samplingBatches()
    batches.value = res.items || []
  } catch (err) {
    error.value = err.response?.data?.detail || '加载抽查批次失败。'
  }
}

async function loadBatch(batchId) {
  try {
    selectedBatch.value = await service.feedback.samplingBatch(batchId)
  } catch (err) {
    error.value = err.response?.data?.detail || '加载抽查批次详情失败。'
  }
}

async function createBatch() {
  error.value = ''
  creatingBatch.value = true
  try {
    const riskIds = batchForm.risk_ticket_ids
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    const payload = {
      scope: { statuses: [batchForm.status] },
      sample_size: batchForm.sample_size,
      exclude_prior: batchForm.exclude_prior,
      notes: batchForm.notes,
      risk_ticket_ids: riskIds,
    }
    if (batchForm.random_seed !== '' && batchForm.random_seed !== null) {
      payload.random_seed = Number(batchForm.random_seed)
    }
    selectedBatch.value = await service.feedback.createSamplingBatch(payload)
    await loadBatches()
    await loadQueue()
  } catch (err) {
    error.value = err.response?.data?.detail || '生成抽查批次失败。'
  } finally {
    creatingBatch.value = false
  }
}

onMounted(async () => {
  await loadOptions()
  await Promise.all([loadQueue(), loadBatches()])
})
</script>

<style src="@/assets/feedback.css"></style>
