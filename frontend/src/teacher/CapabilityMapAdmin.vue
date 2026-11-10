<template>
  <div class="teacher-map-page">
    <div class="page-header">
      <div>
        <span class="eyebrow">能力目录 · 教师视图</span>
        <h1>能力目录审核与个人路径</h1>
        <p class="subtitle">
          查看候选目录、审核门禁、学生状态与证据，并记录教师调整。候选目录未签收前不能冻结或发布。
        </p>
      </div>
      <div class="header-actions">
        <router-link to="/capability-map" class="btn btn-secondary">学生视图</router-link>
        <button class="btn btn-secondary" @click="loadCatalog">刷新目录</button>
      </div>
    </div>

    <div class="toolbar">
      <label>
        目录版本
        <input v-model="catalogVersion" class="input" @keyup.enter="loadCatalog" />
      </label>
      <label>
        学生 ID
        <input v-model="studentId" class="input input-short" placeholder="例如 3" />
      </label>
      <button class="btn btn-primary" @click="loadStudent">加载学生</button>
      <button class="btn btn-secondary" @click="exportCase">导出 CASE v1.1</button>
      <button v-if="isAdmin" class="btn btn-secondary" @click="freezeCatalog">冻结</button>
      <button v-if="isAdmin" class="btn btn-secondary" @click="publishCatalog">发布</button>
    </div>

    <p v-if="message" class="message">{{ message }}</p>

    <div v-if="loadingCatalog" class="state-box">正在读取候选目录...</div>
    <template v-else-if="catalog">
      <div class="notice-row">
        <span class="notice" :class="catalog.status === 'published' ? 'notice-ok' : 'notice-warn'">
          {{ catalog.version }} · {{ catalog.status_label }}
        </span>
        <span class="notice notice-dark">规则 {{ catalog.rule_version }}</span>
        <span class="notice" :class="catalog.readiness.ready ? 'notice-ok' : 'notice-warn'">
          发布门禁：{{ catalog.readiness.ready ? '已满足' : '未满足（' + catalog.readiness.missing.length + ' 项缺失）' }}
        </span>
        <span class="notice">能力 {{ catalog.readiness.counts.capabilities }} · 开放 {{ catalog.readiness.counts.open_capabilities }} · 任务 {{ catalog.readiness.counts.tasks }}</span>
      </div>

      <section class="panel">
        <div class="panel-head">
          <h2>审核门禁缺失项</h2>
          <span class="muted">签收必须有真实复核人、附件位置和时间；不得代填。</span>
        </div>
        <div v-if="!catalog.readiness.missing.length" class="ok-block">全部检查通过。</div>
        <ul v-else class="missing-list">
          <li v-for="(item, index) in catalog.readiness.missing.slice(0, 18)" :key="index">
            <span class="code">{{ item.code }}</span>
            <span>{{ item.detail }}</span>
          </li>
        </ul>
        <p v-if="catalog.readiness.missing.length > 18" class="muted">
          另有 {{ catalog.readiness.missing.length - 18 }} 项，见接口完整响应。
        </p>
      </section>

      <div class="two-col">
        <section class="panel">
          <h2>能力目录</h2>
          <div class="cap-table">
            <div class="cap-row cap-head">
              <span>ID</span><span>能力</span><span>主线/维度</span><span>状态</span><span>先修</span>
            </div>
            <div v-for="capability in catalog.capabilities" :key="capability.capability_id" class="cap-row">
              <span class="mono">{{ capability.capability_id }}</span>
              <span>{{ capability.title }}</span>
              <span>{{ trackLabel(capability.track) }} / {{ dimensionLabel(capability.dimension) }}</span>
              <span>{{ capability.status_label }}</span>
              <span class="mono small">{{ capability.prerequisite_ids.join(', ') || '—' }}</span>
            </div>
          </div>
        </section>

        <section class="panel">
          <h2>教师调整</h2>
          <p class="muted">指定任务必须记录理由；任务环境不可用或尚未开放的任务不能指定。</p>
          <form class="adjust-form" @submit.prevent="submitAdjustment">
            <label>学生 ID
              <input v-model="adjustment.student" class="input" />
            </label>
            <label>能力 ID
              <input v-model="adjustment.capability_id" class="input" placeholder="DS-005" />
            </label>
            <label>动作
              <select v-model="adjustment.action" class="input">
                <option value="assign_task">指定任务</option>
                <option value="request_retest">安排复测</option>
                <option value="add_note">补充说明</option>
                <option value="refer_review">转交复核</option>
              </select>
            </label>
            <label>任务键
              <input v-model="adjustment.task_key" class="input" placeholder="TASK-DS-CUSTOMER-TABLE-001" />
            </label>
            <label>任务版本
              <input v-model="adjustment.task_version" class="input" placeholder="1.0.0-candidate" />
            </label>
            <label class="full">理由
              <textarea v-model="adjustment.rationale" class="input" rows="3" placeholder="写清楚证据、卡点和调整目的"></textarea>
            </label>
            <button class="btn btn-primary" type="submit" :disabled="submittingAdjustment">
              {{ submittingAdjustment ? '提交中...' : '记录调整' }}
            </button>
          </form>
        </section>
      </div>

      <section class="panel">
        <h2>学生证据与推荐</h2>
        <div v-if="!studentMap" class="muted">输入学生 ID 后加载。</div>
        <template v-else>
          <div class="student-head">
            <strong>{{ studentMap.student.username }}</strong>
            <span>目录 {{ studentMap.catalog.version }}</span>
            <span>规则 {{ studentMap.catalog.rule_version }}</span>
          </div>
          <div class="student-grid">
            <div class="student-map">
              <div v-for="track in studentMap.tracks" :key="track.track">
                <h3>{{ track.label }}</h3>
                <div v-for="capability in track.capabilities" :key="capability.capability_id" class="student-cap">
                  <span class="mono">{{ capability.capability_id }}</span>
                  <span>{{ capability.title }}</span>
                  <span class="state" :class="'state-' + capability.state">{{ capability.state_label }}</span>
                  <span class="muted small">
                    {{ capability.evidence.fact_count }} 条证据
                    <template v-if="capability.evidence.latest"> · {{ capability.evidence.latest.outcome }}</template>
                  </span>
                </div>
              </div>
            </div>
            <div class="student-rec">
              <h3>当前推荐</h3>
              <p v-if="!studentRecommendations" class="muted">暂无推荐数据。</p>
              <template v-else>
                <div v-if="!studentRecommendations.items.length" class="muted">没有可推荐任务。</div>
                <article v-for="item in studentRecommendations.items" :key="item.priority + '-' + item.category">
                  <span class="rec-cat">{{ item.category_label }}</span>
                  <strong>{{ item.task ? item.task.title : item.track_label + '基础诊断' }}</strong>
                  <p class="muted small">{{ item.reason.text }}</p>
                </article>
                <div v-if="studentRecommendations.gaps.length" class="gaps">
                  <h4>缺口</h4>
                  <p v-for="gap in studentRecommendations.gaps" :key="gap.code + gap.capability_id">
                    <span class="mono">{{ gap.code }}</span> {{ gap.detail }}
                  </p>
                </div>
              </template>
            </div>
          </div>
          <div class="changelog">
            <h3>最近路径变更</h3>
            <p v-if="!changelog.length" class="muted">暂无变更。</p>
            <div v-for="item in changelog" :key="item.created_at + item.reason" class="change-row">
              <span class="mono">{{ item.capability_id || '—' }}</span>
              <span>{{ item.from_state || '—' }} → {{ item.to_state }}</span>
              <span class="mono small">{{ item.reason }}</span>
              <span class="muted small">{{ formatDate(item.created_at) }}</span>
            </div>
          </div>
        </template>
      </section>

      <div class="two-col">
        <section class="panel">
          <h2>WSTG 转译（候选）</h2>
          <div v-for="mapping in catalog.wstg_mappings" :key="mapping.scenario_id" class="evidence-row">
            <span class="mono">{{ mapping.scenario_id }}</span>
            <span>{{ mapping.scenario_title }}</span>
            <span class="muted small">{{ mapping.capability_id }} · {{ mapping.status }} · 复核人 {{ mapping.reviewer_name || '未指定' }}</span>
          </div>
        </section>
        <section class="panel">
          <h2>数据依据卡（候选）</h2>
          <div v-for="card in catalog.basis_cards" :key="card.card_id" class="evidence-row">
            <span class="mono">{{ card.card_id }}</span>
            <span>{{ card.source_title }}</span>
            <span class="muted small">{{ card.capability_id }} · {{ card.status }} · 核验日期 {{ card.verified_date || '未核验' }}</span>
          </div>
        </section>
      </div>

      <section class="panel">
        <h2>首期交付登记（3.1）</h2>
        <p class="muted">状态必须由真实编制、复核和附件支撑；缺失时不能签收。</p>
        <div class="delivery-table">
          <div class="delivery-row head">
            <span>编号</span><span>交付项</span><span>版本</span><span>状态</span><span>复核人</span><span>附件</span><span>未决问题</span>
          </div>
          <div v-for="item in deliveryItems" :key="item.delivery_no" class="delivery-row">
            <span class="mono">{{ item.delivery_no }}</span>
            <span>{{ item.title }}</span>
            <span class="mono small">{{ item.version }}</span>
            <span>{{ item.status_label }}</span>
            <span>{{ item.reviewer_name || '—' }}</span>
            <span class="mono small">{{ item.attachment_path || '—' }}</span>
            <span class="small">{{ item.open_issues || '—' }}</span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import service from '@/api'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.userInfo?.role === 'admin')
const canManageCatalog = computed(() => Boolean(userStore.userInfo?.can_manage_catalog))
const catalogVersion = ref('v1-candidate')
const studentId = ref('')
const catalog = ref(null)
const deliveryItems = ref([])
const studentMap = ref(null)
const studentRecommendations = ref(null)
const changelog = ref([])
const loadingCatalog = ref(false)
const message = ref('')
const submittingAdjustment = ref(false)
const adjustment = reactive({
  student: '',
  capability_id: '',
  action: 'assign_task',
  task_key: '',
  task_version: '',
  rationale: '',
})

const trackLabels = { data: '数据安全', network: '网络安全' }
const dimensionLabels = { explain: '能解释', identify: '能识别', operate: '能操作', repair: '能修复' }

function trackLabel(value) { return trackLabels[value] || value }
function dimensionLabel(value) { return dimensionLabels[value] || value }
function formatDate(value) { return new Date(value).toLocaleString('zh-CN') }
function extractError(err) {
  const data = err?.response?.data
  if (!data) return '网络或服务异常。'
  if (typeof data === 'string') return data
  if (data.detail) {
    if (typeof data.detail === 'string') return data.detail
    if (data.detail.detail) return data.detail.detail
    if (data.detail.missing) return JSON.stringify(data.detail.missing.slice(0, 5))
    return JSON.stringify(data.detail)
  }
  return JSON.stringify(data)
}

async function loadCatalog() {
  loadingCatalog.value = true
  message.value = ''
  try {
    catalog.value = await service.learningMap.teacherCatalog({ version: catalogVersion.value })
    const register = await service.learningMap.deliveryRegister({ version: catalogVersion.value })
    deliveryItems.value = register.items || []
  } catch (err) {
    catalog.value = null
    deliveryItems.value = []
    message.value = extractError(err)
  } finally {
    loadingCatalog.value = false
  }
}

async function loadStudent() {
  message.value = ''
  const id = Number(studentId.value)
  if (!id) {
    message.value = '请先填写学生 ID。'
    return
  }
  try {
    const params = { version: catalogVersion.value }
    const [map, recommendations, logs] = await Promise.all([
      service.learningMap.studentMap(id, params),
      service.learningMap.studentRecommendations(id, params),
      service.learningMap.studentChangelog(id, params),
    ])
    studentMap.value = map
    studentRecommendations.value = recommendations
    changelog.value = logs.items || []
  } catch (err) {
    message.value = extractError(err)
  }
}

async function submitAdjustment() {
  submittingAdjustment.value = true
  message.value = ''
  try {
    await service.learningMap.createAdjustment({
      catalog_version: catalogVersion.value,
      student: Number(adjustment.student || studentId.value),
      capability_id: adjustment.capability_id || null,
      task_key: adjustment.task_key || null,
      task_version: adjustment.task_version || null,
      action: adjustment.action,
      rationale: adjustment.rationale,
    })
    message.value = '教师调整已记录；下一次推荐会引用该调整。'
    adjustment.rationale = ''
    if (studentId.value) await loadStudent()
  } catch (err) {
    message.value = extractError(err)
  } finally {
    submittingAdjustment.value = false
  }
}

async function freezeCatalog() {
  message.value = ''
  try {
    const payload = await service.learningMap.freezeCatalog(catalogVersion.value)
    message.value = `目录已冻结：${payload.version}`
    await loadCatalog()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function publishCatalog() {
  message.value = ''
  try {
    const payload = await service.learningMap.publishCatalog(catalogVersion.value)
    message.value = `目录已发布：${payload.version}`
    await loadCatalog()
  } catch (err) {
    message.value = extractError(err)
  }
}

async function exportCase() {
  message.value = ''
  try {
    const payload = await service.learningMap.exportCatalog(catalogVersion.value, { format: 'case' })
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `case-${catalogVersion.value}.json`
    link.click()
    URL.revokeObjectURL(url)
    message.value = 'CASE v1.1 包已导出，已通过官方 schema 校验（测试环境）。'
  } catch (err) {
    message.value = extractError(err)
  }
}

onMounted(loadCatalog)
</script>

<style scoped>
.teacher-map-page { width: min(1320px, calc(100% - 40px)); margin: 0 auto; padding: 36px 0 72px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 20px; border-bottom: 2px solid var(--text-primary); padding-bottom: 20px; margin-bottom: 18px; }
.eyebrow { font-size: 12px; letter-spacing: .18em; text-transform: uppercase; color: var(--primary-color); font-weight: 700; }
h1 { font-family: "Songti SC", serif; font-size: 38px; line-height: 1.1; }
.subtitle { color: var(--text-secondary); margin-top: 8px; max-width: 760px; }
.header-actions { display: flex; gap: 8px; }
.btn { border: 1px solid var(--border-color); background: var(--bg-light); padding: 8px 12px; font-weight: 600; cursor: pointer; color: var(--text-primary); }
.btn-primary { background: var(--text-primary); color: var(--bg-light); border-color: var(--text-primary); }
.toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; background: var(--bg-light); border: 1px solid var(--border-color); padding: 14px; margin-bottom: 16px; }
.toolbar label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .06em; }
.input { border: 1px solid var(--border-color); background: var(--bg-paper); padding: 7px 9px; min-width: 220px; color: var(--text-primary); }
.input-short { min-width: 110px; }
.message { background: rgba(183,53,45,.06); border-left: 3px solid var(--primary-color); padding: 9px 12px; font-size: 13px; margin-bottom: 14px; }
.notice-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.notice { font-size: 12px; padding: 5px 9px; border: 1px solid var(--border-color); background: var(--bg-light); }
.notice-dark { background: var(--text-primary); color: var(--bg-light); }
.notice-ok { color: var(--success-color); border-color: rgba(79,124,82,.4); }
.notice-warn { color: var(--warning-color); border-color: rgba(201,135,33,.4); }
.panel { background: var(--bg-light); border: 1px solid var(--text-primary); padding: 18px; margin-bottom: 16px; box-shadow: var(--shadow-md); }
.panel h2 { font-family: "Songti SC", serif; font-size: 20px; margin-bottom: 10px; }
.panel-head { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }
.muted { color: var(--text-muted); font-size: 12px; }
.small { font-size: 12px; }
.mono { font-family: ui-monospace, monospace; }
.missing-list { display: flex; flex-direction: column; gap: 5px; font-size: 12px; }
.missing-list li { display: flex; gap: 8px; }
.code { font-family: ui-monospace, monospace; color: var(--warning-color); min-width: 190px; }
.ok-block { color: var(--success-color); font-weight: 700; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.cap-table { display: flex; flex-direction: column; max-height: 420px; overflow: auto; }
.cap-row { display: grid; grid-template-columns: 70px 1.4fr 1.2fr 100px 110px; gap: 8px; padding: 7px 6px; border-bottom: 1px solid var(--border-color); font-size: 12px; }
.cap-head { background: var(--bg-paper-2); font-size: 10px; text-transform: uppercase; letter-spacing: .06em; position: sticky; top: 0; }
.adjust-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
.adjust-form label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--text-muted); }
.adjust-form .full { grid-column: 1 / -1; }
.student-head { display: flex; gap: 14px; align-items: baseline; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; margin-bottom: 10px; font-size: 12px; color: var(--text-secondary); }
.student-grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; }
.student-map h3, .student-rec h3 { font-size: 14px; margin: 10px 0 6px; }
.student-cap { display: grid; grid-template-columns: 64px 1fr 90px 130px; gap: 8px; font-size: 12px; padding: 4px 0; border-bottom: 1px dotted var(--border-color); }
.state { font-weight: 700; font-size: 11px; }
.state-independent { color: var(--success-color); }
.state-needs_practice { color: var(--error-color); }
.state-assisted_pass, .state-retest_pending { color: var(--warning-color); }
.state-needs_diagnosis, .state-diagnosed, .state-not_attempted { color: var(--text-muted); }
.student-rec article { border-bottom: 1px solid var(--border-color); padding: 8px 0; }
.rec-cat { font-size: 10px; color: var(--primary-color); font-weight: 700; margin-right: 6px; }
.gaps { margin-top: 10px; }
.gaps h4 { font-size: 12px; color: var(--warning-color); }
.changelog { margin-top: 18px; border-top: 1px solid var(--border-color); padding-top: 12px; }
.change-row { display: grid; grid-template-columns: 70px 150px 1fr 150px; gap: 8px; font-size: 12px; padding: 3px 0; }
.evidence-row { display: grid; grid-template-columns: 110px 1.2fr 1fr; gap: 8px; font-size: 12px; padding: 5px 0; border-bottom: 1px dotted var(--border-color); }
.delivery-table { display: flex; flex-direction: column; overflow-x: auto; }
.delivery-row { display: grid; grid-template-columns: 150px 1.4fr 110px 100px 90px 180px 1fr; gap: 8px; padding: 7px 6px; border-bottom: 1px solid var(--border-color); font-size: 12px; min-width: 980px; }
.delivery-row.head { background: var(--bg-paper-2); font-size: 10px; text-transform: uppercase; letter-spacing: .06em; }
.state-box { background: var(--bg-light); border: 1px solid var(--border-color); padding: 40px; text-align: center; color: var(--text-muted); }
@media (max-width: 980px) {
  .two-col, .student-grid { grid-template-columns: 1fr; }
  .page-header { flex-direction: column; align-items: flex-start; }
  .adjust-form { grid-template-columns: 1fr; }
}
</style>
