<template>
  <div class="learning-score-page">
    <div class="page-header-bar">
      <div><h2>动态评分管理</h2><p>评分使用实际测评日期；系统仅将近 90 天内且间隔不少于 7 天的两次最新有效评分用于教学方案。</p></div>
      <a-select v-model="selectedStudentId" placeholder="选择学生" allow-search style="width: 260px" @change="handleStudentChange"><a-option v-for="student in students" :key="student.id" :value="student.id">{{ student.username }}</a-option></a-select>
    </div>
    <section class="panel composite-score-panel">
      <div class="composite-head"><div><h3>综合总评</h3><p>学生自评占 30%，教师评分占 70%。</p></div><a-tag :color="scoreSummary?.status === 'ready' ? 'green' : 'orange'" size="small">{{ scoreSummary?.status === 'ready' ? '已生成总评' : '待补齐数据' }}</a-tag></div>
      <div class="composite-grid">
        <div class="metric-card"><span class="metric-label">学生自评</span><strong>{{ formatScore(scoreSummary?.self_assessment?.score) }}</strong><small>六个方向 1-5 星换算均值 {{ formatWeight(scoreSummary?.weights?.self_assessment) }}</small></div>
        <div class="metric-card"><span class="metric-label">教师评分</span><strong>{{ formatScore(scoreSummary?.admin?.score) }}</strong><small>{{ scoreSummary?.admin?.measured_at ? `最新有效评分：${scoreSummary.admin.measured_at}` : '暂无有效教师评分' }} {{ formatWeight(scoreSummary?.weights?.admin) }}</small></div>
        <div class="metric-card final"><span class="metric-label">计算后总评</span><strong>{{ formatScore(scoreSummary?.final_score) }}</strong><small>自评 × 30% + 教师评分 × 70%</small></div>
      </div>
    </section>
    <div class="work-grid">
      <section class="panel">
        <h3>录入评分</h3>
        <div class="form-grid"><label><span>实际测评日期</span><input v-model="scoreForm.measured_at" class="native-input" type="date" :max="today" /></label><label><span>总分</span><a-input-number v-model="scoreForm.total_score" :min="0" :max="100" :precision="2" style="width: 100%" /></label></div>
        <div class="dimension-grid"><label v-for="direction in directions" :key="direction.key"><span>{{ direction.label }}</span><a-input-number v-model="scoreForm.dimension_scores[direction.key]" :min="0" :max="100" :precision="2" style="width: 100%" /></label></div>
        <label class="full-field"><span>标签</span><a-input v-model="scoreForm.tagsText" placeholder="用逗号分隔，例如：基础薄弱, Web 提升" /></label>
        <label class="full-field"><span>关键备注</span><a-textarea v-model="scoreForm.remark" placeholder="记录本次测评暴露的关键问题、错误原因和建议方向" :auto-size="{ minRows: 3, maxRows: 5 }" /></label>
        <div class="submit-row"><a-button type="primary" :loading="saving" :disabled="!selectedStudentId" @click="submitScore">保存评分并生成方案</a-button></div>
      </section>
      <section class="panel rules-panel"><h3>数据有效性</h3><div class="rule-list"><div><strong>90 天</strong><span>仅保留近 90 天评分进入候选集</span></div><div><strong>7 天</strong><span>两次有效评分间隔需不少于 7 天</span></div><div><strong>{{ effectiveScoreIds.length }}</strong><span>当前有效评分数量</span></div></div><div v-if="teachingPlan" class="plan-preview"><div class="plan-label">{{ teachingPlan.validity_label || '暂无有效教师评分，基于自评生成' }}</div><h4>{{ teachingPlan.title }}</h4><p>{{ teachingPlan.summary }}</p></div></section>
    </div>
    <section class="panel"><div class="chart-head"><h3>历史评分趋势</h3><a-select v-model="trendMode" style="width: 180px" @change="renderTrend"><a-option value="total">总分</a-option><a-option v-for="direction in directions" :key="direction.key" :value="direction.key">{{ direction.label }}</a-option></a-select></div><div ref="trendRef" class="trend-chart"></div></section>
    <section class="panel"><h3>历史评分</h3><a-table :data="scoreRows" :columns="columns" :loading="loadingScores" row-key="id" :pagination="{ pageSize: 8 }"><template #validity="{ record }"><a-tag :color="statusColor(record.validity_status)" size="small">{{ statusLabel(record.validity_status) }}</a-tag></template><template #tags="{ record }"><span class="tag-list"><a-tag v-for="tag in record.tags" :key="tag" size="small" color="arcoblue">{{ tag }}</a-tag></span></template><template #remark="{ record }"><mark v-if="record.remark" class="remark-mark">{{ record.remark }}</mark><span v-else class="muted">无</span></template></a-table></section>
  </div>
</template>
<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import * as echarts from 'echarts'
import api from '@/api'
import { useUserStore } from '@/store/user'
import {
  getDemoScorePayload,
  getDemoStudentKey,
  getDemoTeachingPlan,
  withDemoTeacherStudents,
} from '@/teacher/mockTeacherAnalytics'

const userStore = useUserStore()
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
const isTeacherView = computed(() => userStore.userInfo?.role === 'teacher')

const getSelectedDemoKey = () => isTeacherView.value ? getDemoStudentKey(selectedStudentId.value, students.value) : null

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
const selectedStudent = computed(() => students.value.find(item => String(item.id) === String(selectedStudentId.value)))
const formatScore = value => {
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(2)} 分` : '暂无'
}
const formatWeight = value => {
  const number = Number(value)
  return Number.isFinite(number) ? `权重 ${Math.round(number * 100)}%` : ''
}
const statusLabel = status => ({
  effective: '有效', filtered: '频繁过滤', expired: '已过期', invalid: '无效日期', unknown: '未知',
}[status] || status)
const statusColor = status => ({
  effective: 'green', filtered: 'orange', expired: 'gray', invalid: 'red',
}[status] || 'gray')

const applyDemoScores = async studentKey => {
  const data = getDemoScorePayload(studentKey)
  if (!data) return false
  scoreRows.value = data.results || []
  effectiveScoreIds.value = data.effective_score_ids || []
  scoreSummary.value = data.score_summary || null
  await nextTick()
  renderTrend()
  return true
}

const fetchStudents = async () => {
  const loadReport = isTeacherView.value ? api.analytics.teacherStudentReport : api.analytics.adminStudentReport
  try {
    const loadedStudents = await loadReport() || []
    students.value = isTeacherView.value ? withDemoTeacherStudents(loadedStudents) : loadedStudents
  } catch (error) {
    console.error(error)
    students.value = isTeacherView.value ? withDemoTeacherStudents([]) : []
  }
  if (!selectedStudentId.value && students.value.length) {
    const demoStudent = isTeacherView.value ? students.value.find(student => String(student.username) === '123') : null
    const scoredStudent = students.value.find(student => student.latest_admin_score != null)
    selectedStudentId.value = demoStudent?.id || scoredStudent?.id || students.value[0].id
    await handleStudentChange()
  }
}
const fetchScores = async () => {
  if (!selectedStudentId.value) return
  loadingScores.value = true
  try {
    const demoKey = getSelectedDemoKey()
    if (demoKey && await applyDemoScores(demoKey)) return
    const loadScores = isTeacherView.value ? api.analytics.teacherScores : api.analytics.adminScores
    const data = await loadScores({ student_id: selectedStudentId.value })
    scoreRows.value = data?.results || []
    effectiveScoreIds.value = data?.effective_score_ids || []
    scoreSummary.value = data?.score_summary || null
    await nextTick()
    renderTrend()
  } catch (error) {
    console.error(error)
    const demoKey = getSelectedDemoKey()
    if (demoKey) await applyDemoScores(demoKey)
  } finally {
    loadingScores.value = false
  }
}
const fetchPlan = async () => {
  if (!selectedStudentId.value) return
  const demoKey = getSelectedDemoKey()
  if (demoKey) {
    teachingPlan.value = getDemoTeachingPlan(demoKey)
    return
  }
  try {
    teachingPlan.value = isTeacherView.value
      ? await api.analytics.teacherTeachingPlan(selectedStudentId.value)
      : await api.analytics.adminTeachingPlan(selectedStudentId.value)
  } catch (error) {
    console.error(error)
    teachingPlan.value = null
  }
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
    const tags = scoreForm.tagsText.split(',').map(item => item.trim()).filter(Boolean)
    const demoKey = getSelectedDemoKey()
    if (demoKey) {
      const newRow = {
        id: `mock-${demoKey}-${Date.now()}`,
        measured_at: scoreForm.measured_at || today,
        total_score: Number(scoreForm.total_score || 0),
        dimension_scores: dimensionScores,
        validity_status: 'effective',
        tags,
        remark: scoreForm.remark,
      }
      scoreRows.value = [newRow, ...scoreRows.value]
      effectiveScoreIds.value = [...scoreRows.value]
        .filter(row => row.validity_status === 'effective')
        .sort((left, right) => new Date(right.measured_at) - new Date(left.measured_at))
        .slice(0, 2)
        .map(row => row.id)
      const selfScore = Number(scoreSummary.value?.self_assessment?.score)
      const adminScore = Number(newRow.total_score)
      const safeSelfScore = Number.isFinite(selfScore) ? selfScore : adminScore
      scoreSummary.value = {
        status: 'ready',
        self_assessment: { score: safeSelfScore },
        admin: { score: adminScore, measured_at: newRow.measured_at },
        final_score: Math.round((safeSelfScore * 0.3 + adminScore * 0.7) * 100) / 100,
        weights: { self_assessment: 0.3, admin: 0.7 },
      }
      const basePlan = getDemoTeachingPlan(demoKey) || {}
      teachingPlan.value = {
        ...basePlan,
        validity_label: '本地演示评分已更新',
        title: `${selectedStudent.value?.username || '学生'} 的阶段提升方案`,
        summary: `已记录 ${newRow.measured_at} 的演示评分，可结合最新总分 ${newRow.total_score} 分调整下一阶段练习。`,
      }
      scoreForm.remark = ''
      scoreForm.tagsText = ''
      await nextTick()
      renderTrend()
      return
    }
    const createScore = isTeacherView.value ? api.analytics.createTeacherScore : api.analytics.createAdminScore
    await createScore({
      student: selectedStudentId.value,
      measured_at: scoreForm.measured_at,
      total_score: scoreForm.total_score,
      dimension_scores: dimensionScores,
      tags,
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
  const rows = [...scoreRows.value].sort((left, right) => new Date(left.measured_at) - new Date(right.measured_at))
  const effectiveSet = new Set(effectiveScoreIds.value)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 42, right: 20, top: 28, bottom: 40 },
    xAxis: { type: 'category', data: rows.map(item => item.measured_at) },
    yAxis: { type: 'value', min: 0, max: 100 },
    series: [{
      name: trendMode.value === 'total' ? '总分' : directions.find(item => item.key === trendMode.value)?.label,
      type: 'line', smooth: true,
      data: rows.map(item => trendMode.value === 'total' ? Number(item.total_score || 0) : Number(item.dimension_scores?.[trendMode.value] || 0)),
      symbolSize: 9,
      itemStyle: { color: params => effectiveSet.has(rows[params.dataIndex]?.id) ? '#00b42a' : '#86909c' },
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

/* 教师评分页：统一为教师工作台的纸张式信息层级，评分逻辑保持不变 */
.learning-score-page {
  max-width: 1260px;
  margin: 0 auto;
  padding: 46px 36px 72px;
  color: #1e1c18;
}

.page-header-bar {
  min-height: 112px;
  box-sizing: border-box;
  margin-bottom: 26px;
  padding: 24px 28px;
  align-items: center;
  border: 1px solid #d9cfbe;
  border-radius: 8px;
  background: rgba(255, 250, 242, .94);
}

.page-header-bar h2 {
  color: #1e1c18;
  font-size: 32px;
  font-weight: 900;
  letter-spacing: -.04em;
}

.page-header-bar p { max-width: 720px; color: #6b6256; line-height: 1.6; }

.panel {
  margin-bottom: 20px;
  padding: 24px;
  border: 1px solid #d9cfbe;
  border-radius: 8px;
  background: rgba(255, 250, 242, .94);
  box-shadow: none;
}

.panel h3 { color: #1e1c18; font-size: 18px; font-weight: 900; }

.composite-score-panel {
  border-color: #d9cfbe;
  background: rgba(255, 250, 242, .94);
}

.composite-head { margin-bottom: 18px; }
.composite-head p { color: #6b6256; }

.composite-grid { gap: 16px; }
.metric-card {
  min-height: 118px;
  padding: 18px;
  border-color: #e1d7c7;
  border-radius: 6px;
  background: #fffdf8;
}

.metric-card strong { color: #1e1c18; font-size: 30px; font-weight: 900; }
.metric-card small,
.metric-label { color: #6b6256; }
.metric-card.final { border-color: #b42318; background: #fff6ef; }

.work-grid { gap: 20px; margin-bottom: 20px; }
.form-grid,
.dimension-grid { gap: 16px; }

label span { color: #4b453b; font-weight: 800; }
.native-input {
  height: 40px;
  box-sizing: border-box;
  border-color: #cfc3b2;
  border-radius: 5px;
  background: #fffdf8;
}

.native-input:focus {
  outline: none;
  border-color: #b42318;
  box-shadow: 0 0 0 3px rgba(180, 35, 24, .1);
}

.submit-row { margin-top: 20px; }

.rules-panel { border-left: 4px solid #b42318; }
.rule-list { gap: 12px; }
.rule-list div { padding: 13px; border-radius: 5px; background: #f7f1e7; }
.rule-list strong { color: #b42318; font-weight: 900; }
.rule-list span { color: #5d5549; }

.plan-preview { padding: 16px; border-color: #ddc7a5; border-radius: 5px; background: #fff8ec; }
.plan-label { color: #a06412; }
.plan-preview h4 { color: #1e1c18; }
.plan-preview p { color: #5d5549; }

.chart-head { margin-bottom: 16px; }
.trend-chart { height: 340px; }

:deep(.arco-select-view),
:deep(.arco-input),
:deep(.arco-input-number),
:deep(.arco-textarea) {
  border-color: #cfc3b2;
  border-radius: 5px;
  background: #fffdf8;
}

:deep(.arco-select-view:hover),
:deep(.arco-input:hover),
:deep(.arco-input-number:hover),
:deep(.arco-textarea:hover) { border-color: #a28f77; }

:deep(.arco-select-view:focus-within),
:deep(.arco-input:focus-within),
:deep(.arco-input-number:focus-within),
:deep(.arco-textarea:focus-within) {
  border-color: #b42318;
  box-shadow: 0 0 0 3px rgba(180, 35, 24, .1);
}

:deep(.arco-btn-primary) { border-color: #1e1c18; background: #1e1c18; font-weight: 800; }
:deep(.arco-btn-primary:hover) { border-color: #b42318; background: #b42318; }
:deep(.arco-table) { border-color: #ded3c2; }
:deep(.arco-table th) { color: #4b453b; background: #f5eee2; }

@media (max-width: 900px) {
  .learning-score-page { padding: 30px 20px 56px; }
  .page-header-bar { align-items: flex-start; }
}

@media (max-width: 600px) {
  .learning-score-page { padding: 24px 16px 44px; }
  .page-header-bar { padding: 20px; }
  .page-header-bar h2 { font-size: 28px; }
  .panel { padding: 18px; }
}
</style>






