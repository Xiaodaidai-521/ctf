<template>
  <div class="learning-score-page">
    <div class="page-header-bar">
      <div>
        <h2>动态评分管理</h2>
        <p>评分必须使用实际测评日期；系统只把近 90 天内且间隔不少于 7 天的最新两次有效评分用于教学方案。</p>
      </div>
      <a-select v-model="selectedStudentId" placeholder="选择学生" allow-search style="width: 260px" @change="handleStudentChange">
        <a-option v-for="student in students" :key="student.id" :value="student.id">
          {{ student.username }}
        </a-option>
      </a-select>
    </div>

    <section class="panel composite-score-panel">
      <div class="composite-head">
        <div>
          <h3>综合总评</h3>
          <p>学生自评占 30%，管理员评分占 70%。</p>
        </div>
        <a-tag :color="scoreSummary?.status === 'ready' ? 'green' : 'orange'" size="small">
          {{ scoreSummary?.status === 'ready' ? '已生成总评' : '待补齐数据' }}
        </a-tag>
      </div>
      <div class="composite-grid">
        <div class="metric-card">
          <span class="metric-label">学生自评</span>
          <strong>{{ formatScore(scoreSummary?.self_assessment?.score) }}</strong>
          <small>六方向 1-5 星换算均值 {{ formatWeight(scoreSummary?.weights?.self_assessment) }}</small>
        </div>
        <div class="metric-card">
          <span class="metric-label">管理员评分</span>
          <strong>{{ formatScore(scoreSummary?.admin?.score) }}</strong>
          <small>{{ scoreSummary?.admin?.measured_at ? `最新有效评分：${scoreSummary.admin.measured_at}` : '暂无有效管理员评分' }} {{ formatWeight(scoreSummary?.weights?.admin) }}</small>
        </div>
        <div class="metric-card final">
          <span class="metric-label">计算后总评</span>
          <strong>{{ formatScore(scoreSummary?.final_score) }}</strong>
          <small>自评 * 30% + 管理员评分 * 70%</small>
        </div>
      </div>
    </section>

    <div class="work-grid">
      <section class="panel">
        <h3>录入评分</h3>
        <div class="form-grid">
          <label>
            <span>实际测评日期</span>
            <input v-model="scoreForm.measured_at" class="native-input" type="date" :max="today" />
          </label>
          <label>
            <span>总分</span>
            <a-input-number v-model="scoreForm.total_score" :min="0" :max="100" :precision="2" style="width: 100%" />
          </label>
        </div>

        <div class="dimension-grid">
          <label v-for="direction in directions" :key="direction.key">
            <span>{{ direction.label }}</span>
            <a-input-number v-model="scoreForm.dimension_scores[direction.key]" :min="0" :max="100" :precision="2" style="width: 100%" />
          </label>
        </div>

        <label class="full-field">
          <span>标签</span>
          <a-input v-model="scoreForm.tagsText" placeholder="用逗号分隔，例如：基础薄弱, Web 提升" />
        </label>
        <label class="full-field">
          <span>关键备注</span>
          <a-textarea v-model="scoreForm.remark" placeholder="记录本次测评暴露的关键问题、错误原因和建议方向" :auto-size="{ minRows: 3, maxRows: 5 }" />
        </label>

        <div class="submit-row">
          <a-button type="primary" :loading="saving" :disabled="!selectedStudentId" @click="submitScore">保存评分并生成方案</a-button>
        </div>
      </section>

      <section class="panel rules-panel">
        <h3>数据有效性</h3>
        <div class="rule-list">
          <div><strong>90 天</strong><span>仅保留近 90 天评分进入候选集</span></div>
          <div><strong>7 天</strong><span>两次有效评分间隔需不少于 7 天</span></div>
          <div><strong>{{ effectiveScoreIds.length }}</strong><span>当前有效评分数量</span></div>
        </div>
        <div v-if="teachingPlan" class="plan-preview">
          <div class="plan-label">{{ teachingPlan.validity_label || '暂无有效管理员评分，基于自评生成' }}</div>
          <h4>{{ teachingPlan.title }}</h4>
          <p>{{ teachingPlan.summary }}</p>
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="chart-head">
        <h3>历史评分趋势</h3>
        <a-select v-model="trendMode" style="width: 180px" @change="renderTrend">
          <a-option value="total">总分</a-option>
          <a-option v-for="direction in directions" :key="direction.key" :value="direction.key">{{ direction.label }}</a-option>
        </a-select>
      </div>
      <div ref="trendRef" class="trend-chart"></div>
    </section>

    <section class="panel">
      <h3>历史评分</h3>
      <a-table :data="scoreRows" :columns="columns" :loading="loadingScores" row-key="id" :pagination="{ pageSize: 8 }">
        <template #validity="{ record }">
          <a-tag :color="statusColor(record.validity_status)" size="small">{{ statusLabel(record.validity_status) }}</a-tag>
        </template>
        <template #tags="{ record }">
          <span class="tag-list">
            <a-tag v-for="tag in record.tags" :key="tag" size="small" color="arcoblue">{{ tag }}</a-tag>
          </span>
        </template>
        <template #remark="{ record }">
          <mark v-if="record.remark" class="remark-mark">{{ record.remark }}</mark>
          <span v-else class="muted">无</span>
        </template>
      </a-table>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import api from '@/api'

const directions = [
  { key: 'web', label: 'Web' },
  { key: 'crypto', label: 'Crypto' },
  { key: 'pwn', label: 'Pwn' },
  { key: 'reverse', label: 'Reverse' },
  { key: 'forensics', label: 'Forensics' },
  { key: 'misc', label: 'Misc' },
]

const today = new Date().toISOString().slice(0, 10)
const students = ref([])
const selectedStudentId = ref(null)
const scoreRows = ref([])
const effectiveScoreIds = ref([])
const scoreSummary = ref(null)
const teachingPlan = ref(null)
const loadingScores = ref(false)
const saving = ref(false)
const trendMode = ref('total')
const trendRef = ref(null)
let trendChart = null

const scoreForm = reactive({
  measured_at: today,
  total_score: 0,
  dimension_scores: Object.fromEntries(directions.map(item => [item.key, 0])),
  tagsText: '',
  remark: '',
})

const columns = [
  { title: '测评日期', dataIndex: 'measured_at', width: 120 },
  { title: '总分', dataIndex: 'total_score', width: 90 },
  { title: '有效性', slotName: 'validity', width: 100 },
  { title: '标签', slotName: 'tags', width: 180 },
  { title: '关键备注', slotName: 'remark' },
]

const selectedStudent = computed(() => students.value.find(item => item.id === selectedStudentId.value))

const formatScore = (value) => {
  const n = Number(value)
  return Number.isFinite(n) ? `${n.toFixed(2)} 分` : '暂无'
}

const formatWeight = (value) => {
  const n = Number(value)
  return Number.isFinite(n) ? `权重 ${Math.round(n * 100)}%` : ''
}

const statusLabel = (status) => ({
  effective: '有效',
  filtered: '频繁过滤',
  expired: '已过期',
  invalid: '无效日期',
  unknown: '未知',
}[status] || status)

const statusColor = (status) => ({
  effective: 'green',
  filtered: 'orange',
  expired: 'gray',
  invalid: 'red',
}[status] || 'gray')

const fetchStudents = async () => {
  students.value = await api.analytics.adminStudentReport() || []
  if (!selectedStudentId.value && students.value.length) {
    selectedStudentId.value = students.value[0].id
    await handleStudentChange()
  }
}

const fetchScores = async () => {
  if (!selectedStudentId.value) return
  loadingScores.value = true
  try {
    const data = await api.analytics.adminScores({ student_id: selectedStudentId.value })
    scoreRows.value = data?.results || []
    effectiveScoreIds.value = data?.effective_score_ids || []
    scoreSummary.value = data?.score_summary || null
    await nextTick()
    renderTrend()
  } finally {
    loadingScores.value = false
  }
}

const fetchPlan = async () => {
  if (!selectedStudentId.value) return
  teachingPlan.value = await api.analytics.adminTeachingPlan(selectedStudentId.value)
}

const handleStudentChange = async () => {
  await Promise.all([fetchScores(), fetchPlan()])
}

const submitScore = async () => {
  if (!selectedStudentId.value) return
  saving.value = true
  try {
    const dimensionScores = {}
    for (const direction of directions) {
      const value = Number(scoreForm.dimension_scores[direction.key])
      if (Number.isFinite(value)) dimensionScores[direction.key] = value
    }
    await api.analytics.createAdminScore({
      student: selectedStudentId.value,
      measured_at: scoreForm.measured_at,
      total_score: scoreForm.total_score,
      dimension_scores: dimensionScores,
      tags: scoreForm.tagsText.split(',').map(item => item.trim()).filter(Boolean),
      remark: scoreForm.remark,
    })
    scoreForm.remark = ''
    scoreForm.tagsText = ''
    await handleStudentChange()
  } finally {
    saving.value = false
  }
}

const renderTrend = () => {
  if (!trendRef.value) return
  if (!trendChart) trendChart = echarts.init(trendRef.value)
  const rows = [...scoreRows.value].sort((a, b) => new Date(a.measured_at) - new Date(b.measured_at))
  const labels = rows.map(item => item.measured_at)
  const values = rows.map(item => {
    if (trendMode.value === 'total') return Number(item.total_score || 0)
    return Number(item.dimension_scores?.[trendMode.value] || 0)
  })
  const effectiveSet = new Set(effectiveScoreIds.value)

  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 42, right: 20, top: 28, bottom: 40 },
    xAxis: { type: 'category', data: labels },
    yAxis: { type: 'value', min: 0, max: 100 },
    series: [{
      name: trendMode.value === 'total' ? '总分' : directions.find(item => item.key === trendMode.value)?.label,
      type: 'line',
      smooth: true,
      data: values,
      symbolSize: 9,
      itemStyle: {
        color: (params) => effectiveSet.has(rows[params.dataIndex]?.id) ? '#00b42a' : '#86909c',
      },
      lineStyle: { color: '#165dff', width: 3 },
      areaStyle: { color: 'rgba(22, 93, 255, 0.08)' },
    }],
  })
}

const resizeChart = () => trendChart?.resize()

onMounted(async () => {
  await fetchStudents()
  window.addEventListener('resize', resizeChart)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeChart)
  trendChart?.dispose()
})
</script>

<style scoped>
.page-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 18px;
}

.page-header-bar h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.page-header-bar p {
  margin: 6px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.composite-score-panel {
  background: #f8fbff;
  border-color: #dbeafe;
}

.composite-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 14px;
}

.composite-head h3 {
  margin-bottom: 4px;
}

.composite-head p {
  margin: 0;
  color: #6b7280;
  font-size: 13px;
}

.composite-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 104px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #e5eaf3;
  border-radius: 8px;
}

.metric-card strong {
  color: #111827;
  font-size: 26px;
  line-height: 1.15;
}

.metric-card small {
  color: #6b7280;
  font-size: 12px;
  line-height: 1.4;
}

.metric-card.final {
  border-color: #93c5fd;
  background: #eff6ff;
}

.metric-label {
  color: #4b5563;
  font-size: 13px;
  font-weight: 700;
}

.work-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.75fr);
  gap: 16px;
  margin-bottom: 16px;
}

.panel {
  background: #fff;
  border: 1px solid #edf1f7;
  border-radius: 8px;
  padding: 18px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, .04);
}

.panel h3 {
  margin: 0 0 14px;
  font-size: 16px;
  color: #1f2937;
}

.form-grid,
.dimension-grid {
  display: grid;
  gap: 12px;
}

.form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-bottom: 12px;
}

.dimension-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 12px;
}

label span {
  display: block;
  margin-bottom: 6px;
  color: #4b5563;
  font-size: 12px;
  font-weight: 600;
}

.native-input {
  width: 100%;
  height: 32px;
  padding: 4px 10px;
  border: 1px solid #d9dfe8;
  border-radius: 4px;
  color: #1f2937;
}

.full-field {
  display: block;
  margin-bottom: 12px;
}

.submit-row {
  display: flex;
  justify-content: flex-end;
}

.rule-list {
  display: grid;
  gap: 10px;
}

.rule-list div {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  border-radius: 6px;
  background: #f7f9fc;
}

.rule-list strong {
  min-width: 48px;
  color: #165dff;
  font-size: 20px;
}

.rule-list span {
  color: #4b5563;
  font-size: 13px;
}

.plan-preview {
  margin-top: 14px;
  padding: 12px;
  border-radius: 6px;
  background: #f2f8ff;
  border: 1px solid #dbeafe;
}

.plan-label {
  color: #165dff;
  font-size: 12px;
  font-weight: 700;
}

.plan-preview h4 {
  margin: 8px 0 6px;
}

.plan-preview p {
  margin: 0;
  color: #4b5563;
  line-height: 1.6;
}

.chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.trend-chart {
  width: 100%;
  height: 320px;
}

.tag-list {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.remark-mark {
  padding: 2px 6px;
  border-radius: 4px;
  background: #fff7e6;
  color: #7a4b00;
}

.muted {
  color: #9ca3af;
}

@media (max-width: 900px) {
  .page-header-bar,
  .work-grid,
  .composite-grid {
    display: grid;
    grid-template-columns: 1fr;
  }

  .form-grid,
  .dimension-grid {
    grid-template-columns: 1fr;
  }
}
</style>
