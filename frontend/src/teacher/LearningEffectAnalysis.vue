<template>
  <section class="analysis-page">
    <header class="heading">
      <p class="eyebrow">学习画像 / 数据快照</p>
      <h1>学习效果分析</h1>
      <p>基于已生成的学习快照，展示学生近 90 天的学习表现与变化。</p>
    </header>

    <label class="student-picker">
      <span>查看学生</span>
      <select v-model="studentId" @change="load">
        <option value="">选择学生</option>
        <option v-for="student in students" :key="student.id" :value="student.id">{{ student.username }}</option>
      </select>
    </label>

    <div v-if="loading" class="metric-grid" aria-label="正在加载学习分析">
      <div v-for="item in 8" :key="item" class="metric-card skeleton" />
    </div>
    <div v-else class="analysis-content">
      <p v-if="errorMessage" class="state-message error-message">{{ errorMessage }}</p>
      <div class="metric-grid">
        <article v-for="metric in metrics" :key="metric.key" class="metric-card">
          <div class="metric-head"><span>{{ metric.label }}</span><span class="metric-icon" aria-hidden="true">{{ metric.icon }}</span></div>
          <div class="metric-value">{{ metric.display }}<small v-if="metric.unit">{{ metric.unit }}</small></div>
          <div class="trend" :class="metric.trend.tone"><span aria-hidden="true">{{ metric.trend.symbol }}</span>{{ metric.trend.text }}</div>
          <p>{{ metric.status }}</p>
        </article>
      </div>
      <section class="analysis-panel">
        <div>
          <p class="panel-label">综合学习效果</p>
          <strong>{{ formatNumber(snapshot.total_effect_score) }} 分</strong>
          <span>{{ effectLevelLabel }}</span>
        </div>
        <div class="recommendations">
          <p class="panel-label">学习建议</p>
          <p v-for="item in recommendations" :key="item.id">{{ item.title }}：{{ item.content }}</p>
          <p v-if="!recommendations.length">当前暂无新的学习建议。</p>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/api'
import {
  getDemoLearningEffect,
  getDemoStudentKey,
  withDemoTeacherStudents,
} from '@/teacher/mockTeacherAnalytics'

const students = ref([])
const studentId = ref('')
const snapshot = ref({ total_effect_score: 0, effect_level: 'at_risk', sample_description: { effective_learning_seconds: 0 }, dimensions: {} })
const previousSnapshot = ref(null)
const recommendations = ref([])
const loading = ref(false)
const errorMessage = ref('')

const metricConfigs = [
  { key: 'study_time', label: '学习时长', icon: '◷', type: 'duration', scoreKey: 'time_score' },
  { key: 'completion_score', label: '课程完成率', icon: '✓', type: 'percent' },
  { key: 'mastery_score', label: '知识掌握度', icon: '◇', type: 'score' },
  { key: 'retention_score', label: '记忆保持度', icon: '↺', type: 'percent' },
  { key: 'consistency_score', label: '学习连续性', icon: '≋', type: 'percent' },
  { key: 'efficiency_score', label: '学习效率', icon: '↗', type: 'score' },
  { key: 'engagement_score', label: '学习参与度', icon: '◎', type: 'percent' },
  { key: 'focus_score', label: '学习专注度', icon: '◉', type: 'score' },
]

const toNumber = value => Number.isFinite(Number(value)) ? Number(value) : null
const formatNumber = value => value == null ? '--' : value.toFixed(2)
const formatDuration = seconds => {
  const value = toNumber(seconds)
  if (value == null) return { value: '--', unit: '' }
  if (value <= 0) return { value: formatNumber(0), unit: '小时' }
  return value >= 3600 ? { value: formatNumber(value / 3600), unit: '小时' } : { value: formatNumber(value / 60), unit: '分钟' }
}
const getStatus = score => {
  if (score == null) return '暂无足够数据'
  if (score >= 80) return '表现优秀'
  if (score >= 60) return '状态良好'
  if (score >= 40) return '基本稳定，建议关注'
  return '建议重点提升'
}
const getValue = config => {
  if (config.type === 'duration') return toNumber(snapshot.value?.sample_description?.effective_learning_seconds)
  return toNumber(snapshot.value?.dimensions?.[config.key])
}
const getPreviousValue = config => {
  if (config.type === 'duration') return toNumber(previousSnapshot.value?.sample_description?.effective_learning_seconds)
  return toNumber(previousSnapshot.value?.dimensions?.[config.key])
}
const getTrend = (config, value, previous) => {
  if (value == null || previous == null) return { tone: 'neutral', symbol: '•', text: '暂无上一周期数据' }
  const delta = value - previous
  if (Math.abs(delta) < 0.1) return { tone: 'neutral', symbol: '•', text: '与上一周期基本持平' }
  const positive = delta > 0
  const unit = config.type === 'duration' ? '小时' : config.type === 'percent' ? '%' : '分'
  const displayDelta = config.type === 'duration' ? delta / 3600 : delta
  return { tone: positive ? 'positive' : 'negative', symbol: positive ? '↑' : '↓', text: `较上一周期 ${positive ? '+' : ''}${formatNumber(displayDelta)} ${unit}` }
}
const metrics = computed(() => metricConfigs.map(config => {
  const value = getValue(config)
  const score = config.type === 'duration' ? toNumber(snapshot.value?.dimensions?.[config.scoreKey]) : value
  const duration = config.type === 'duration' ? formatDuration(value) : null
  return {
    ...config,
    display: duration ? duration.value : formatNumber(value),
    unit: duration ? duration.unit : config.type === 'percent' ? '%' : '分',
    status: getStatus(score),
    trend: getTrend(config, value, getPreviousValue(config)),
  }
}))
const effectLevelLabel = computed(() => ({ excellent: '优秀', good: '良好', developing: '需要关注', at_risk: '预警' })[snapshot.value?.effect_level] || '暂无评级')
const emptySnapshot = () => ({
  total_effect_score: 0,
  effect_level: 'at_risk',
  sample_description: { effective_learning_seconds: 0 },
  dimensions: Object.fromEntries(metricConfigs.map(item => [item.scoreKey || item.key, 0])),
})

const selectedStudent = computed(() => students.value.find(item => String(item.id) === String(studentId.value)))
const applyDemoAnalytics = studentKey => {
  const demoKey = studentKey || getDemoStudentKey(studentId.value, students.value)
  const demo = getDemoLearningEffect(demoKey)
  if (!demo) return false
  snapshot.value = demo.snapshot
  previousSnapshot.value = demo.previousSnapshot
  recommendations.value = demo.recommendations
  return true
}

async function load() {
  snapshot.value = emptySnapshot()
  previousSnapshot.value = null
  recommendations.value = []
  errorMessage.value = ''
  if (!studentId.value) {
    students.value = students.value.length ? students.value : withDemoTeacherStudents([])
    studentId.value = students.value[0]?.id || ''
  }
  if (!studentId.value) {
    errorMessage.value = '暂无可查看的学生。'
    return
  }
  const demoKey = getDemoStudentKey(studentId.value, students.value)
  if (demoKey && applyDemoAnalytics(demoKey)) return

  loading.value = true
  try {
    const response = await api.analytics.learningEffectSummary(studentId.value, 90)
    if (response?.snapshot) {
      snapshot.value = response.snapshot
      previousSnapshot.value = response.previous_snapshot || null
      recommendations.value = response.recommendations || []
    } else if (!applyDemoAnalytics(demoKey)) {
      errorMessage.value = '暂无学习效果快照，正在显示默认指标。'
    }
  } catch (error) {
    console.error(error)
    if (!applyDemoAnalytics(demoKey)) {
      errorMessage.value = '学习效果加载失败，正在显示默认指标。'
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const loadedStudents = await api.analytics.teacherStudentReport() || []
    students.value = withDemoTeacherStudents(loadedStudents)
  } catch (error) {
    console.error(error)
    students.value = withDemoTeacherStudents([])
  }
  const demoStudent = students.value.find(student => String(student.username) === '123')
  studentId.value = demoStudent?.id || students.value[0]?.id || ''
  await load()
})
</script>

<style scoped>
.analysis-page{min-height:100vh;padding:42px 36px;background-color:#faf7f0;background-image:linear-gradient(#e9e1d4 1px,transparent 1px),linear-gradient(90deg,#e9e1d4 1px,transparent 1px);background-size:38px 38px;color:#1e1c18}.heading{margin-bottom:24px}.eyebrow{margin:0 0 7px;color:#b42318;font-size:12px;font-weight:800;letter-spacing:.04em}.heading h1{margin:0;font-size:42px;letter-spacing:-.05em}.heading p:not(.eyebrow){margin:8px 0 0;color:#6b6256}.student-picker{display:grid;gap:7px;width:min(260px,100%);margin:22px 0 28px;font-size:13px;font-weight:800}.student-picker select{height:43px;padding:0 12px;border:1px solid #a78b63;border-radius:5px;background:#fffaf2;color:#1e1c18;font:inherit}.analysis-content{display:grid;gap:18px}.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.metric-card{min-height:174px;padding:18px;border:1px solid #d9cfbe;border-radius:8px;background:rgba(255,250,242,.92);display:flex;flex-direction:column;gap:10px}.metric-head{display:flex;justify-content:space-between;align-items:center;color:#6b6256;font-weight:800}.metric-icon{color:#b42318;font-size:18px}.metric-value{font-size:34px;line-height:1;font-weight:900;letter-spacing:-.04em}.metric-value small{margin-left:4px;color:#6b6256;font-size:14px;font-weight:700;letter-spacing:0}.trend{font-size:13px;font-weight:800}.positive{color:#2f7d4a}.negative{color:#b42318}.neutral{color:#6b6256}.metric-card p{margin:auto 0 0;color:#6b6256;font-size:13px}.analysis-panel{display:grid;grid-template-columns:minmax(180px,.4fr) 1fr;gap:18px;padding:18px;border:1px solid #d9cfbe;border-radius:8px;background:rgba(255,250,242,.92)}.analysis-panel strong{display:block;margin:6px 0;font-size:30px}.analysis-panel span{color:#6b6256;font-weight:700}.panel-label{margin:0;color:#6b6256;font-size:13px;font-weight:800}.recommendations p:not(.panel-label){margin:8px 0 0;color:#4b453b;font-size:13px;line-height:1.55}.state-message{margin:32px 0;color:#6b6256}.error-message{color:#b42318}.skeleton{min-height:174px;border-color:transparent;background:linear-gradient(90deg,#f3eee5,#fffaf2,#f3eee5);background-size:200% 100%;animation:shine 1.2s infinite}@keyframes shine{to{background-position:-200% 0}}@media(max-width:1000px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:640px){.analysis-page{padding:28px 16px}.heading h1{font-size:32px}.metric-grid{grid-template-columns:1fr}.analysis-panel{grid-template-columns:1fr}}
</style>










