<template>
  <section class="evaluation-page">
    <header>
      <h1>学情与教学证据</h1>
      <p>按原任务与目录版本查看核验、帮助和复测；不合并为总分。</p>
    </header>
    <form class="filters" @submit.prevent="load">
      <label>数据模式<select v-model="mode" @change="resetMode"><option value="formal">正式</option><option value="demo">合成演示</option></select></label>
      <label v-if="mode === 'formal'">学生<select v-model="studentId"><option value="">全部学生</option><option v-for="student in students" :key="student.id" :value="student.id">{{ student.username }}</option></select></label>
      <label>任务 ID<input v-model.trim="taskKey" placeholder="全部任务" /></label>
      <label>知识点 ID<input v-model.trim="knowledgePoint" placeholder="稳定 ID" /></label>
      <label>目录版本<input v-model.trim="catalogVersion" placeholder="分版本展示" /></label>
      <button :disabled="loading">查询</button>
    </form>
    <p v-if="mode === 'demo'" role="status">演示模式：合成案例，与正式学生和统计完全分离；不代表实际教学效果。</p>
    <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
    <p v-if="loading" role="status">正在读取证据…</p>
    <template v-else-if="data">
      <p>来源：{{ label(data.source) }} · 更新时间：{{ data.updated_at }} · 窗口：{{ data.window?.start || '全部历史' }} — {{ data.window?.end || '当前' }}</p>
      <p v-if="!data.rows.length">暂无数据。不会自动补入演示学生或成绩。</p>
      <div class="table-scroll" v-else>
        <table><caption>任务尝试（最多展示 100 条；指标按完整筛选范围计算）</caption>
          <thead><tr><th>学生内部 ID</th><th>任务 / 版本</th><th>目录版本</th><th>核验</th><th>帮助状态</th><th>证据</th></tr></thead>
          <tbody><tr v-for="row in data.rows" :key="row.attempt_id">
            <td>{{ row.student_id }}</td><td>{{ row.task_title }} / {{ row.versions.task_version }}</td><td>{{ row.versions.catalog_version }}</td>
            <td>{{ label(row.overall_status) }}</td><td>{{ label(row.independence) }}</td>
            <td><button v-if="mode === 'formal'" @click="showDetail(row.attempt_id)">展开尝试与事实</button><span v-else>合成示例</span></td>
          </tr></tbody>
        </table>
      </div>
      <section v-for="group in data.version_groups" :key="JSON.stringify(group.versions)">
        <h2>学生学习 · {{ group.versions.task_key }} / {{ group.versions.task_version }} / {{ group.versions.catalog_version }}</h2>
        <div class="table-scroll"><table><thead><tr><th>指标</th><th>分子</th><th>分母</th><th>缺失量</th><th>状态</th></tr></thead>
          <tbody><tr v-for="(metric, name) in group.metrics" :key="name"><th>{{ label(name) }}</th><td>{{ metric.numerator ?? '未知' }}</td><td>{{ metric.denominator }}</td><td>{{ metric.missing }}</td><td>{{ label(metric.status) }}</td></tr></tbody>
        </table></div>
      </section>
      <section><h2>数据保护与证据接通</h2><p>教学演练：只看决策，不执行导出。实际保护：未评估。</p>
        <ul><li v-for="(status, source) in data.source_status" :key="source">{{ label(source) }}：{{ label(status) }}</li></ul>
      </section>
      <section><h2>智能体运行记录</h2><p>请求成功不等于任务通过；未知费用/token 不补零。</p><button @click="loadRuntime">读取本范围运行摘要</button>
        <p v-if="runtime?.status === 'no_data'">暂无运行数据。</p><pre v-else-if="runtime">{{ JSON.stringify(runtime, null, 2) }}</pre>
      </section>
      <section v-if="detail"><h2>尝试、事实、版本与事件对账</h2><button @click="detail = null">收起</button><pre>{{ JSON.stringify(detail, null, 2) }}</pre></section>
    </template>
    <TeacherOperations v-if="mode === 'formal'" />
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import evaluation from '@/api/evaluation'
import TeacherOperations from './TeacherOperations.vue'

const mode = ref('formal')
const students = ref([])
const studentId = ref('')
const taskKey = ref('')
const knowledgePoint = ref('')
const catalogVersion = ref('')
const data = ref(null)
const detail = ref(null)
const runtime = ref(null)
const loading = ref(false)
const errorMessage = ref('')
let generation = 0
const labels = {
  formal: '正式', demo: '演示', offline: '离线评测', passed: '通过', failed: '未通过',
  independent: '平台内独立', assisted: '受助', unknown: '未知', pending_manual: '待教师评阅',
  verification_failed: '核验失败', environment_affected: '受环境影响', not_submitted: '未提交',
  no_data: '暂无数据', not_connected: '未接通', not_started: '未开展', not_evaluated: '未评估',
  available: '可核对', partial: '部分缺失', module3: '模块三', module4: '模块四', module5: '模块五',
  execution: '执行', actual_protection: '实际保护', independent_completion: '平台内独立完成率',
  determinate_coverage: '可判定覆盖率', core_pass: '程序/必需项通过', first_effective_attempts: '首次有效尝试',
  independent_retest_pass: '无提示复测通过', unmapped: '未映射', retests_due: '应复测',
  retests_not_tested: '未复测', retests_assisted: '受助复测', retests_pending_manual: '复测待评',
  retests_verification_failed: '复测核验失败',
}
const label = value => labels[value] || value
const params = () => ({ mode: mode.value,
  ...(mode.value === 'formal' && studentId.value ? { student_id: studentId.value } : {}),
  ...(taskKey.value ? { task_key: taskKey.value } : {}),
  ...(knowledgePoint.value ? { knowledge_point_id: knowledgePoint.value } : {}),
  ...(catalogVersion.value ? { catalog_version: catalogVersion.value } : {}),
})
async function load() {
  const token = ++generation
  loading.value = true
  data.value = detail.value = runtime.value = null
  errorMessage.value = ''
  try {
    const response = await evaluation.learning(params())
    if (token === generation) data.value = response
  } catch {
    if (token === generation) errorMessage.value = '读取失败，请检查权限或重试；未使用演示数据替代。'
  } finally {
    if (token === generation) loading.value = false
  }
}
async function resetMode() {
  const token = ++generation
  studentId.value = ''
  students.value = []
  data.value = detail.value = runtime.value = null
  errorMessage.value = ''
  loading.value = true
  try {
    const response = await evaluation.students({ mode: mode.value })
    if (token !== generation) return
    students.value = response.students
    await load()
  } catch {
    if (token === generation) {
      errorMessage.value = '学生列表加载失败；未生成演示学生。'
      loading.value = false
    }
  }
}
async function showDetail(id) {
  const token = generation
  try {
    const response = await evaluation.attempt(id)
    if (token === generation) detail.value = response
  } catch { if (token === generation) errorMessage.value = '明细读取失败或无权限。' }
}
async function loadRuntime() {
  const token = generation
  try {
    const response = await evaluation.runtime(params())
    if (token === generation) runtime.value = response
  } catch { if (token === generation) errorMessage.value = '运行摘要读取失败或无权限。' }
}
onMounted(resetMode)
</script>

<style scoped>
.evaluation-page{padding:28px;color:#242424;background:#fafafa;min-height:100vh}.evaluation-page h1{font-size:28px}.evaluation-page h2{font-size:19px;margin-top:30px}.filters{display:flex;gap:14px;flex-wrap:wrap;align-items:end}.filters label{display:grid;gap:6px}input,select,button{font:inherit;padding:8px;border:1px solid #777;border-radius:4px}button{cursor:pointer;background:#fff;color:inherit}button:disabled{cursor:wait}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;margin:18px 0;background:#fff}caption{text-align:left;margin-bottom:8px}th,td{padding:10px;border:1px solid #ccc;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#fff;border:1px solid #ccc;padding:16px;max-height:600px;overflow:auto}[role=alert]{font-weight:bold}@media(prefers-color-scheme:dark){.evaluation-page{background:#181818;color:#eee}table,pre,button,input,select{background:#262626;color:#eee}th,td,pre{border-color:#666}}@media(max-width:600px){.evaluation-page{padding:16px}.filters label{width:100%}}
</style>
