<template>
  <section class="evaluation-page">
    <header>
      <h2>任务评估统计</h2>
      <p>按原任务与目录版本查看核验、帮助和复测；不合并为总分。</p>
    </header>
    <form class="filters" @submit.prevent="load">
      <label>数据范围<select v-model="mode"><option value="formal">正式教学数据</option><option value="demo">合成演示</option></select></label>
      <label v-if="mode === 'formal'">学生<select v-model="studentId"><option value="">全部学生</option><option v-if="studentId && !students.some(student => String(student.id) === String(studentId))" :value="studentId">已导入学生关联（名称暂不可用）</option><option v-for="student in students" :key="student.id" :value="student.id">{{ student.username }}</option></select></label>
      <label>任务<select v-model="taskKey"><option value="">全部任务</option><option v-if="taskKey && !taskOptions.some(task => task.key === taskKey)" :value="taskKey">已导入任务关联（名称暂不可用）</option><option v-for="task in taskOptions" :key="task.key" :value="task.key">{{ task.title }}</option></select></label>
      <label>知识点<select v-model="knowledgePoint"><option value="">全部知识点</option><option v-if="knowledgePoint && !knowledgeOptions.some(point => point.id === knowledgePoint)" :value="knowledgePoint">已导入知识点关联（名称暂不可用）</option><option v-for="point in knowledgeOptions" :key="point.id" :value="point.id">{{ point.name }}</option></select></label>
      <label>目录版本<select v-model="catalogVersion"><option value="">全部版本</option><option v-if="catalogVersion && !catalogVersions.includes(catalogVersion)" :value="catalogVersion">已导入目录版本</option><option v-for="version in catalogVersions" :key="version" :value="version">{{ configurationVersionLabel(version) }}</option></select></label>
      <button :disabled="loading">查询</button>
    </form>
    <ReferenceImport title="其他查询条件" :fields="filterFields" :model-value="{ student_id: studentId, task_key: taskKey, knowledge_point_id: knowledgePoint, catalog_version: catalogVersion }" @update:model-value="applyFilters" />
    <p v-if="mode === 'demo'" role="status">演示模式：合成案例，与正式学生和统计完全分离；不代表实际教学效果。</p>
    <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
    <p v-if="loading" role="status">正在读取证据…</p>
    <template v-else-if="data">
      <p>来源：{{ label(data.source) }} · 更新时间：{{ data.updated_at }} · 窗口：{{ data.window?.start || '全部历史' }} — {{ data.window?.end || '当前' }}</p>
      <RecordView :value="data" title="学习统计原始记录" />
      <p v-if="!data.rows.length">暂无数据。不会自动补入演示学生或成绩。</p>
      <div class="table-scroll" v-else>
        <table><caption>任务尝试（最多展示 100 条；指标按完整筛选范围计算）</caption>
          <thead><tr><th>学生</th><th>任务 / 版本</th><th>目录版本</th><th>核验</th><th>帮助状态</th><th>证据</th></tr></thead>
          <tbody><tr v-for="row in data.rows" :key="row.attempt_id">
            <td>{{ students.find(student => String(student.id) === String(row.student_id))?.username || (mode === 'demo' ? '演示学生' : '学生姓名暂不可用') }}</td><td>{{ row.task_title }} / {{ row.versions.task_version }}</td><td>{{ configurationVersionLabel(row.versions.catalog_version) }}</td>
            <td>{{ label(row.overall_status) }}</td><td>{{ label(row.independence) }}</td>
            <td><button v-if="mode === 'formal'" @click="showDetail(row.attempt_id)">展开尝试与事实</button><span v-else>合成示例</span></td>
          </tr></tbody>
        </table>
      </div>
      <section v-for="group in data.version_groups" :key="JSON.stringify(group.versions)">
        <h2>学生学习 · {{ taskTitle(group.versions.task_key) }} · {{ configurationVersionLabel(group.versions.catalog_version) }}</h2>
        <div class="table-scroll"><table><thead><tr><th>指标</th><th>分子</th><th>分母</th><th>缺失量</th><th>状态</th></tr></thead>
          <tbody><tr v-for="(metric, name) in group.metrics" :key="name"><th>{{ label(name) }}</th><td>{{ metric.numerator ?? '未知' }}</td><td>{{ metric.denominator }}</td><td>{{ metric.missing }}</td><td>{{ label(metric.status) }}</td></tr></tbody>
        </table></div>
      </section>
      <section><h2>数据保护与证据接通</h2><p>教学演练：只看决策，不执行导出。实际保护：未评估。</p>
        <ul><li v-for="(status, source) in data.source_status" :key="source">{{ label(source) }}：{{ label(status) }}</li></ul>
      </section>
      <section><h2>智能体运行记录</h2><p>请求成功不等于任务通过；未知费用和用量不补零。</p><button @click="loadRuntime">读取本范围运行摘要</button>
        <p v-if="runtime?.status === 'no_data'">暂无运行数据。</p>
        <div v-else-if="runtime" class="runtime-summary">
          <p>本范围共 {{ runtime.records?.length || 0 }} 次教学运行；请求成功不等于任务通过，费用与用量未知时不补零。</p>
          <div class="table-scroll" v-if="runtime.records?.length">
            <table><caption>运行摘要</caption><thead><tr><th>学生</th><th>任务 / 版本</th><th>目录版本</th><th>状态</th><th>开始时间</th></tr></thead>
              <tbody><tr v-for="run in runtime.records" :key="run.run_id"><td>{{ studentName(run.student_id) }}</td><td>{{ taskTitle(run.versions?.task_key) }} / {{ run.versions?.task_version || '未提供' }}</td><td>{{ configurationVersionLabel(run.versions?.catalog_version) }}</td><td>{{ runStateLabel(run.state) }}</td><td>{{ formatDate(run.created_at) }}</td></tr></tbody>
            </table>
          </div>
          <RecordView :value="runtime" title="教学运行记录" />
        </div>
      </section>
      <section v-if="detail"><h2>练习、学习事实与事件核对</h2><button @click="detail = null">收起</button>
        <div class="table-scroll"><table><caption>尝试明细</caption><thead><tr><th>项目</th><th>内容</th></tr></thead>
          <tbody>
            <tr><td>任务</td><td>{{ detail.task_title || '未提供' }}</td></tr>
            <tr><td>学生</td><td>{{ detailStudentName }}</td></tr>
            <tr><td>提交与核验</td><td>{{ label(detail.overall_status) }} · {{ label(detail.independence) }}</td></tr>
            <tr><td>目录与任务版本</td><td>{{ configurationVersionLabel(detail.versions?.catalog_version) }} / {{ detail.versions?.task_version || '未提供' }}</td></tr>
            <tr><td>提交次数</td><td>{{ detail.submission_count ?? '未提供' }}</td></tr>
            <tr><td>开始与生效时间</td><td>{{ formatDate(detail.claimed_at) }} · {{ formatDate(detail.effective_at) }}</td></tr>
            <tr><td>能力</td><td>{{ (detail.capability_ids || []).map(capabilityTitle).join('、') || '未关联能力' }}</td></tr>
            <tr><td>知识点</td><td>{{ (detail.knowledge_point_ids || []).map(knowledgeTitle).join('、') || '未关联知识点' }}</td></tr>
          </tbody>
        </table></div>
        <RecordView :value="detail" title="学习证据与事件" />
      </section>
    </template>
  </section>
</template>

<script setup>
import { names } from '@/shared/navigation/names'

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useUserStore } from '@/store/user'
import evaluation from './api.js'
import ReferenceImport from '@/shared/forms/ReferenceImport.vue'
import RecordView from '@/shared/forms/RecordView.vue'
import { configurationVersionLabel } from '../candidatePresentation.js'

const mode = ref('formal')
const students = ref([])
const studentId = ref('')
const taskKey = ref('')
const knowledgePoint = ref('')
const catalogVersion = ref('')
const taskCatalog = ref([])
const conceptCatalog = ref([])
const capabilityCatalog = ref([])
const filterFields = [
  { key: 'student_id', label: '学生', type: 'number' }, { key: 'task_key', label: '任务' },
  { key: 'knowledge_point_id', label: '知识点' }, { key: 'catalog_version', label: '目录版本' },
]
function applyFilters(values) {
  studentId.value = values.student_id
  taskKey.value = values.task_key
  knowledgePoint.value = values.knowledge_point_id
  catalogVersion.value = values.catalog_version
}
const capabilityTitle = id => capabilityCatalog.value.find(item => item.capability_id === id)?.title || '能力名称暂不可用'
const knowledgeTitle = id => conceptCatalog.value.find(item => item.stable_id === id)?.name || '知识点名称暂不可用'
const catalogVersions = ref([])
const data = ref(null)
const detail = ref(null)
const runtime = ref(null)
const loading = ref(false)
const errorMessage = ref('')
let generation = 0, rosterGeneration = 0, detailGeneration = 0, runtimeGeneration = 0, catalogGeneration = 0, dead = false
const user = useUserStore()
const account = computed(() => user.userInfo?.role === 'teacher' && user.userInfo?.id ? `teacher:${user.userInfo.id}` : null)
const labels = {
  formal: '正式', demo: '演示', offline: '离线评测', passed: '通过', failed: '未通过',
  independent: '平台内独立', assisted: '受助', unknown: '未知', pending_manual: '待教师评阅',
  verification_failed: '核验失败', environment_affected: '受环境影响', not_submitted: '未提交',
  no_data: '暂无数据', not_connected: '未接通', not_started: '未开展', not_evaluated: '未评估',
  available: '可核对', partial: '部分缺失', module3: '学习材料', module4: '识别与复核', module5: '决策回放',
  execution: '执行', actual_protection: '实际保护', independent_completion: '平台内独立完成率',
  determinate_coverage: '可判定覆盖率', core_pass: '程序/必需项通过', first_effective_attempts: '首次有效尝试',
  independent_retest_pass: '无提示复测通过', unmapped: '未映射', retests_due: '应复测',
  retests_not_tested: '未复测', retests_assisted: '受助复测', retests_pending_manual: '复测待评',
  retests_verification_failed: '复测核验失败',
}
const label = value => labels[value] || '状态待确认'
const formatDate = value => value ? new Date(value).toLocaleString('zh-CN') : '—'
const taskOptions = computed(() => taskCatalog.value.map(task => ({ key: task.task_key, title: task.title })))
const knowledgeOptions = computed(() => conceptCatalog.value.map(point => ({ id: point.stable_id, name: point.name })))
const detailStudentName = computed(() => studentName(detail.value?.student_id))
function taskTitle(key) {
  return taskCatalog.value.find(task => task.task_key === key)?.title || '任务名称暂不可用'
}
function studentName(id) {
  return students.value.find(student => String(student.id) === String(id))?.username || '学生姓名暂不可用'
}
const runStateLabels = {
  ready: '就绪', waiting_ai: '等待智能体', showing_help: '展示帮助', paused: '已暂停',
  waiting_teacher: '等待教师', degraded: '已降级', ended: '已结束',
}
const runStateLabel = value => runStateLabels[value] || '状态待确认'
const params = () => ({ mode: mode.value,
  ...(mode.value === 'formal' && studentId.value ? { student_id: studentId.value } : {}),
  ...(taskKey.value ? { task_key: taskKey.value } : {}),
  ...(knowledgePoint.value ? { knowledge_point_id: knowledgePoint.value } : {}),
  ...(catalogVersion.value ? { catalog_version: catalogVersion.value } : {}),
})
async function loadFilterCatalog() {
  if (!account.value || dead) return
  const token = ++catalogGeneration
  taskCatalog.value = []; conceptCatalog.value = []; capabilityCatalog.value = []; catalogVersions.value = []
  try {
    const version = catalogVersion.value
    const catalog = await evaluation.catalog({ version: version || undefined })
    if (dead || token !== catalogGeneration) return
    if (!catalog || !Array.isArray(catalog.capabilities) || (version && catalog.version !== version)) throw new Error('Wrong catalog version')
    catalogVersions.value = catalog.version ? [catalog.version] : []
    capabilityCatalog.value = catalog.capabilities || []
    const tasks = new Map()
    const points = new Map()
    for (const capability of catalog.capabilities || []) {
      for (const task of capability.tasks || []) {
        if (task?.task_key && !tasks.has(task.task_key)) tasks.set(task.task_key, task)
      }
      for (const point of capability.knowledge_points || []) {
        if (point?.knowledge_point_id && !points.has(point.knowledge_point_id)) points.set(point.knowledge_point_id, point)
      }
    }
    taskCatalog.value = [...tasks.values()]
    conceptCatalog.value = [...points.values()].map(point => ({ stable_id: point.knowledge_point_id, name: point.name }))
  } catch {
    if (dead || token !== catalogGeneration) return
    taskCatalog.value = []
    conceptCatalog.value = []
    catalogVersions.value = []
  }
}
async function load() {
  if (!account.value || dead) return
  const token = ++generation
  loading.value = true
  data.value = detail.value = runtime.value = null
  errorMessage.value = ''
  try {
    const query = params()
    const response = await evaluation.learning(query)
    if (response?.source !== query.mode || !Array.isArray(response?.rows) || !Array.isArray(response.version_groups) || response.rows.some(row => !row?.attempt_id || row.source !== query.mode || (query.student_id && String(row.student_id) !== String(query.student_id)))) throw new Error('Wrong data scope')
    if (!dead && token === generation) data.value = response
  } catch {
    if (!dead && token === generation) errorMessage.value = '读取失败，请检查权限或重试；未使用演示数据替代。'
  } finally {
    if (!dead && token === generation) loading.value = false
  }
}
async function resetMode() {
  if (!account.value || dead) return
  studentId.value = ''
  const token = ++rosterGeneration
  generation++; detailGeneration++; runtimeGeneration++
  students.value = []
  data.value = detail.value = runtime.value = null
  errorMessage.value = ''
  loading.value = true
  try {
    const scope = mode.value
    const response = await evaluation.evaluationStudents({ mode: scope })
    if (dead || token !== rosterGeneration) return
    if (response?.source !== scope || !Array.isArray(response?.students)) throw new Error('Wrong roster scope')
    students.value = response.students
    await load()
  } catch {
    if (!dead && token === rosterGeneration) {
      errorMessage.value = '学生列表加载失败；未生成演示学生。'
      loading.value = false
    }
  }
}
async function showDetail(id) {
  if (mode.value !== 'formal' || !account.value || !data.value?.rows.some(row => row.attempt_id === id)) return
  const selected = data.value.rows.find(row => row.attempt_id === id)
  const request = ++detailGeneration
  detail.value = null
  const token = generation
  try {
    const response = await evaluation.attempt(id)
    if (response?.attempt_id !== id || response.source !== 'formal' || String(response.student_id) !== String(selected.student_id)) throw new Error('Wrong attempt detail')
    if (!dead && token === generation && request === detailGeneration) detail.value = response
  } catch { if (!dead && token === generation && request === detailGeneration) errorMessage.value = '明细读取失败或无权限。' }
}
async function loadRuntime() {
  if (!account.value || !data.value || dead) return
  const request = ++runtimeGeneration
  runtime.value = null
  const token = generation
  try {
    const query = params()
    const response = await evaluation.runtime(query)
    if (response?.source !== query.mode || !Array.isArray(response.records) || response.records.some(row => !row?.run_id || (query.student_id && String(row.student_id) !== String(query.student_id)))) throw new Error('Wrong runtime scope')
    if (!dead && token === generation && request === runtimeGeneration) runtime.value = response
  } catch { if (!dead && token === generation && request === runtimeGeneration) errorMessage.value = '运行摘要读取失败或无权限。' }
}
watch(mode, () => {
  generation++; rosterGeneration++; detailGeneration++; runtimeGeneration++
  students.value = []; data.value = detail.value = runtime.value = null
  loading.value = false; errorMessage.value = ''
  resetMode()
}, { flush: 'sync' })
watch(catalogVersion, loadFilterCatalog, { flush: 'sync' })
watch([studentId, taskKey, knowledgePoint, catalogVersion], () => {
  generation++; detailGeneration++; runtimeGeneration++
  data.value = detail.value = runtime.value = null
  loading.value = false
}, { flush: 'sync' })
watch(account, value => {
  generation++; rosterGeneration++; catalogGeneration++; detailGeneration++; runtimeGeneration++
  students.value = []; data.value = detail.value = runtime.value = null
  taskCatalog.value = []; conceptCatalog.value = []; capabilityCatalog.value = []; catalogVersions.value = []
  studentId.value = taskKey.value = knowledgePoint.value = catalogVersion.value = ''
  loading.value = false; errorMessage.value = ''
  if (value) { loadFilterCatalog(); resetMode() }
}, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { dead = true; generation++; rosterGeneration++; catalogGeneration++; detailGeneration++; runtimeGeneration++ })
</script>

<style scoped>
.evaluation-page{padding:var(--space-3);color:var(--ink);background:var(--surface);min-height:100vh}.evaluation-page h1{font-size:var(--text-section)}.evaluation-page h2{font-size:var(--text-card);margin-top:var(--space-4)}.filters{display:flex;gap:var(--space-2);flex-wrap:wrap;align-items:end}.filters label{display:grid;gap:calc(var(--space-1) / 2)}input,select,button{font:inherit;padding:var(--space-1);border:var(--stroke) solid var(--line);border-radius:var(--radius-control)}button{cursor:pointer;background:var(--surface);color:inherit}button:disabled{cursor:wait}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;margin:var(--space-2) 0;background:var(--surface)}caption{text-align:left;margin-bottom:var(--space-1)}th,td{padding:var(--space-1);border:var(--stroke) solid var(--line);text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--surface);border:var(--stroke) solid var(--line);padding:var(--space-2);max-height:var(--content-height);overflow:auto}[role=alert]{font-weight:bold}@media (max-width: 768px){.evaluation-page{padding:var(--space-2)}.filters label{width:100%}}
</style>
