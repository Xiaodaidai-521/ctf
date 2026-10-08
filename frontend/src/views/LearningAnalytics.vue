<template>
  <div class="analytics-page">
    <div class="container">
      <section class="page-hero">
        <div>
          <p class="eyebrow">Learning Analytics</p>
          <h1 class="page-title">学习分析</h1>
          <p class="page-desc">把能力、投入和掌握趋势放在一起看，方便你判断下一步该补哪里。</p>
        </div>
        <div class="hero-summary">
          <span class="summary-label">本周学习</span>
          <strong>{{ totalStudyMinutes }}</strong>
          <span>分钟</span>
        </div>
      </section>

      <div class="overview-grid">
        <div class="overview-card">
          <span class="overview-label">连续活跃</span>
          <strong>{{ currentStreak }}</strong>
          <span class="overview-unit">天</span>
        </div>
        <div class="overview-card">
          <span class="overview-label">完成任务</span>
          <strong>{{ completedCount }}</strong>
          <span class="overview-unit">个</span>
        </div>
        <div class="overview-card">
          <span class="overview-label">平均正确率</span>
          <strong>{{ accuracyText }}</strong>
          <span class="overview-unit">近 7 天</span>
        </div>
        <div class="overview-card highlight">
          <span class="overview-label">建议重点</span>
          <strong>{{ focusArea }}</strong>
          <span class="overview-unit">优先补齐短板</span>
        </div>
      </div>

      <a-tabs v-model:active-key="activeTab" class="analytics-tabs">
        <a-tab-pane key="radar" title="能力雷达图">
          <div class="chart-card">
            <div class="chart-copy">
              <p class="section-kicker">能力结构</p>
              <h2>看清强项和短板</h2>
              <p>雷达图优先绑定个人后台有效评分，蓝色为最新评分，橙色为上次评分；暂无足够评分时参考后台评分模拟数据。</p>
            </div>
            <div class="chart-layout">
              <div ref="radarRef" class="chart-box"></div>
              <aside class="insight-panel">
                <h3>能力提示</h3>
                <div class="insight-item">
                  <span>优势方向</span>
                  <strong>{{ strongestDirection.name }}</strong>
                  <small>{{ strongestDirection.value }} 分</small>
                </div>
                <div class="insight-item">
                  <span>待加强</span>
                  <strong>{{ weakestDirection.name }}</strong>
                  <small>{{ weakestDirection.value }} 分</small>
                </div>
                <div class="insight-item">
                  <span>提升最大</span>
                  <strong>{{ mostImprovedDirection.name }}</strong>
                  <small>{{ mostImprovedDirection.deltaText }}</small>
                </div>
                <p class="insight-note">{{ radarSourceNote }}</p>
              </aside>
            </div>
          </div>
        </a-tab-pane>

        <a-tab-pane key="heatmap" title="学习热力图">
          <div class="chart-card">
            <div class="chart-copy">
              <p class="section-kicker">学习投入</p>
              <h2>近 6 个月学习热度</h2>
              <p>颜色越深代表当天投入越多。保持低波动，比偶尔冲刺更容易稳定进步。</p>
            </div>
            <div class="heatmap-layout">
              <div class="heatmap-card">
                <div ref="heatmapRef" class="chart-box heatmap-box"></div>
              </div>
              <aside class="insight-panel compact">
                <h3>热度概览</h3>
                <div class="insight-item">
                  <span>活跃天数</span>
                  <strong>{{ activeDays }}</strong>
                  <small>近 6 个月</small>
                </div>
                <div class="insight-item">
                  <span>最高投入</span>
                  <strong>{{ hottestDay.minutes }}</strong>
                  <small>{{ hottestDay.date }}</small>
                </div>
                <div class="legend-row">
                  <span>少</span>
                  <i class="legend low"></i>
                  <i class="legend mid"></i>
                  <i class="legend high"></i>
                  <span>多</span>
                </div>
              </aside>
            </div>
          </div>
        </a-tab-pane>

        <a-tab-pane key="trend" title="掌握度趋势">
          <div class="chart-card">
            <div class="chart-copy">
              <p class="section-kicker">掌握趋势</p>
              <h2>近 14 天方向变化</h2>
              <p>用趋势判断学习是否真正沉淀，曲线下降时优先复盘错题和概念卡片。</p>
            </div>
            <div class="chart-layout">
              <div ref="trendRef" class="chart-box"></div>
              <aside class="insight-panel">
                <h3>趋势建议</h3>
                <div class="suggestion-list">
                  <div v-for="item in suggestions" :key="item.title" class="suggestion-item">
                    <strong>{{ item.title }}</strong>
                    <span>{{ item.text }}</span>
                  </div>
                </div>
              </aside>
            </div>
          </div>
        </a-tab-pane>
      </a-tabs>

      <div class="bottom-grid">
        <div class="card weekly-card">
          <h3 class="card-title">周报摘要</h3>
          <div class="weekly-grid">
            <div class="weekly-stat">
              <span class="ws-value">{{ totalStudyMinutes }}</span>
              <span class="ws-label">本周学习分钟</span>
            </div>
            <div class="weekly-stat">
              <span class="ws-value">{{ completedCount }}</span>
              <span class="ws-label">完成任务</span>
            </div>
            <div class="weekly-stat">
              <span class="ws-value">{{ accuracyText }}</span>
              <span class="ws-label">正确率</span>
            </div>
          </div>
          <p class="weekly-summary-text">{{ weeklySummaryText }}</p>
        </div>

        <div class="card action-card">
          <h3 class="card-title">下一步行动</h3>
          <div class="action-list">
            <div v-for="action in nextActions" :key="action" class="action-item">
              <span class="action-dot"></span>
              <span>{{ action }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import api from '@/api'

const activeTab = ref('radar')
const radarRef = ref(null)
const heatmapRef = ref(null)
const trendRef = ref(null)
const weeklySummary = ref(null)
const profile = ref(null)
const teachingPlan = ref(null)

let radarChart = null
let heatmapChart = null
let trendChart = null

const defaultDirections = [
  { key: 'web', label: 'Web' },
  { key: 'crypto', label: 'Crypto' },
  { key: 'pwn', label: 'Pwn' },
  { key: 'reverse', label: 'Reverse' },
  { key: 'forensics', label: 'Forensics' },
  { key: 'misc', label: 'Misc' },
]
const directions = ref(defaultDirections)
const directionNames = computed(() => directions.value.map((direction) => direction.label))
const adminScoreMockPair = {
  previous: {
    measured_at: '2026-05-10',
    total_score: 43,
    dimension_scores: {
      web: 62,
      crypto: 48,
      pwn: 20,
      reverse: 35,
      forensics: 38,
      forensic: 38,
      misc: 52,
    },
  },
  current: {
    measured_at: '2026-05-25',
    total_score: 55,
    dimension_scores: {
      web: 80,
      crypto: 58,
      pwn: 20,
      reverse: 44,
      forensics: 45,
      forensic: 45,
      misc: 61,
    },
  },
}
const normalizeAbilityValue = (value) => Math.max(0, Math.min(100, Number(value) || 0))
const directionScoreAliases = {
  web: ['Web', 'web_security'],
  crypto: ['Crypto', 'cryptography'],
  pwn: ['Pwn', 'binary', 'binary_security'],
  reverse: ['Reverse', 're'],
  forensics: ['Forensics', 'forensic', 'digital_forensics'],
  forensic: ['Forensics', 'forensics', 'digital_forensics'],
  misc: ['Misc'],
}

const effectiveAdminScores = computed(() => {
  const scores = teachingPlan.value?.input_snapshot?.effective_scores
  return Array.isArray(scores) ? scores.filter(Boolean) : []
})

const buildReferenceBaseline = (score) => {
  const dimensions = score?.dimension_scores || {}
  return {
    ...adminScoreMockPair.previous,
    measured_at: score?.measured_at || adminScoreMockPair.previous.measured_at,
    total_score: Math.max(0, Number(score?.total_score || 0) - 8),
    dimension_scores: Object.fromEntries(
      Object.entries(dimensions).map(([key, value]) => [key, Math.max(0, normalizeAbilityValue(value) - (key === 'pwn' ? 0 : 8))]),
    ),
  }
}

const radarScorePair = computed(() => {
  const [latest, previous] = effectiveAdminScores.value
  if (latest && previous) {
    return {
      source: 'backend',
      previous,
      current: latest,
      note: teachingPlan.value?.validity_label || '基于个人后台最新两次有效评分数据',
    }
  }
  if (latest) {
    return {
      source: 'single-backend',
      previous: buildReferenceBaseline(latest),
      current: latest,
      note: `${teachingPlan.value?.validity_label || '基于个人后台最新有效评分数据'}，上一组为后台评分参考基线`,
    }
  }
  return {
    source: 'mock',
    previous: adminScoreMockPair.previous,
    current: adminScoreMockPair.current,
    note: '暂无个人有效后台评分，当前参考后台评分模拟数据',
  }
})

const previousScoreName = computed(() => (radarScorePair.value.source === 'backend' ? '上次后台评分' : '上次参考评分'))
const currentScoreName = computed(() => (radarScorePair.value.source === 'mock' ? '本次参考评分' : '最新后台评分'))
const radarSourceNote = computed(() => radarScorePair.value.note)
const getDirectionScore = (direction, score) => {
  const dataset = score?.dimension_scores || score || {}
  const aliases = [direction.key, ...(direction.aliases || []), ...(directionScoreAliases[direction.key] || [])]
  for (const key of aliases) {
    if (Object.prototype.hasOwnProperty.call(dataset, key)) {
      return normalizeAbilityValue(dataset[key])
    }
  }
  return 0
}
const previousAbilityScores = computed(() => directions.value.map((direction) => getDirectionScore(direction, radarScorePair.value.previous)))
const currentAbilityScores = computed(() => directions.value.map((direction) => getDirectionScore(direction, radarScorePair.value.current)))
const abilityScores = currentAbilityScores

const heatmapDays = 183

const activityData = Array.from({ length: heatmapDays }, (_, index) => {
  const now = new Date()
  const date = new Date(now.getTime() - (heatmapDays - 1 - index) * 86400000)
  const seasonal = Math.abs(Math.sin(index * 0.21)) * 78
  const weekly = index % 7 === 0 ? 0 : 18
  const burst = index % 17 === 0 ? 46 : 0
  const minutes = Math.round(weekly + seasonal + burst + (index % 5) * 10)
  return [date.toISOString().slice(0, 10), Math.min(minutes, 180)]
})

const strongestDirection = computed(() => {
  const scores = abilityScores.value
  const max = Math.max(...scores)
  const index = scores.indexOf(max)
  return { name: directionNames.value[index] || '-', value: max }
})

const weakestDirection = computed(() => {
  const scores = abilityScores.value
  const min = Math.min(...scores)
  const index = scores.indexOf(min)
  return { name: directionNames.value[index] || '-', value: min }
})

const mostImprovedDirection = computed(() => {
  const deltas = currentAbilityScores.value.map((score, index) => score - previousAbilityScores.value[index])
  const max = Math.max(...deltas)
  const index = deltas.indexOf(max)
  return {
    name: directionNames.value[index] || '-',
    value: max,
    deltaText: `${max >= 0 ? '+' : ''}${max} 分`,
  }
})

const totalStudyMinutes = computed(() => weeklySummary.value?.total_study_minutes || 320)
const completedCount = computed(() => weeklySummary.value?.completed_count || 8)
const accuracyText = computed(() => weeklySummary.value?.accuracy ? `${weeklySummary.value.accuracy}%` : '76%')
const focusArea = computed(() => weakestDirection.value.name)
const activeDays = computed(() => activityData.filter((item) => item[1] > 0).length)
const currentStreak = computed(() => {
  let streak = 0
  for (let index = activityData.length - 1; index >= 0; index--) {
    if (activityData[index][1] <= 0) break
    streak++
  }
  return streak
})
const hottestDay = computed(() => {
  const item = [...activityData].sort((a, b) => b[1] - a[1])[0]
  return { date: item?.[0] || '-', minutes: item?.[1] || 0 }
})
const weeklySummaryText = computed(() => (
  weeklySummary.value?.summary ||
  `本周学习节奏整体稳定，建议继续保持每日短时练习，并把重点放在 ${focusArea.value} 方向。`
))

const suggestions = computed(() => [
  { title: '先补基础', text: `${focusArea.value} 当前分数最低，建议安排 2 组基础题。` },
  { title: '保持节奏', text: `最近 30 天活跃 ${activeDays.value} 天，继续维持固定学习时间。` },
  { title: '做一次复盘', text: '把错题按知识点归类，优先处理重复出错的概念。' },
])

const nextActions = computed(() => [
  `完成 1 套 ${focusArea.value} 方向专项练习`,
  '整理今天遇到的 3 个关键概念',
  '使用教学辅导师复盘一道错题',
  '明天继续保持 30 分钟以上学习',
])

const initRadar = () => {
  if (!radarRef.value) return
  if (!radarChart) radarChart = echarts.init(radarRef.value)
  radarChart.setOption({
    color: ['#f59e0b', '#5b7cfa'],
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const rows = directionNames.value.map((name, index) => {
          const current = currentAbilityScores.value[index]
          const previous = previousAbilityScores.value[index]
          const delta = current - previous
          const value = params.name === currentScoreName.value ? current : previous
          return `${name}: ${value} 分（变化 ${delta >= 0 ? '+' : ''}${delta}）`
        })
        return `<strong>${params.name}</strong><br/>${rows.join('<br/>')}`
      },
    },
    legend: {
      top: 4,
      right: 12,
      icon: 'roundRect',
      itemWidth: 18,
      itemHeight: 10,
      textStyle: { color: '#5d6677' },
      data: [previousScoreName.value, currentScoreName.value],
    },
    radar: {
      center: ['48%', '52%'],
      radius: '66%',
      splitNumber: 4,
      indicator: directionNames.value.map((name) => ({ name, max: 100 })),
      axisName: { color: '#4f5663', fontSize: 12 },
      splitLine: { lineStyle: { color: '#e6eaf2' } },
      splitArea: { areaStyle: { color: ['#f8faff', '#ffffff'] } },
      axisLine: { lineStyle: { color: '#e6eaf2' } },
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: previousAbilityScores.value,
          name: previousScoreName.value,
          areaStyle: { color: 'rgba(245, 158, 11, 0.12)' },
          lineStyle: { color: '#f59e0b', width: 3 },
          itemStyle: { color: '#f59e0b' },
        },
        {
          value: currentAbilityScores.value,
          name: currentScoreName.value,
          areaStyle: { color: 'rgba(91, 124, 250, 0.20)' },
          lineStyle: { color: '#5b7cfa', width: 3 },
          itemStyle: { color: '#5b7cfa' },
        },
      ],
      symbolSize: 6,
    }],
  })
}

const initHeatmap = () => {
  if (!heatmapRef.value) return
  if (!heatmapChart) heatmapChart = echarts.init(heatmapRef.value)
  const start = activityData[0][0]
  const end = activityData[activityData.length - 1][0]
  heatmapChart.setOption({
    tooltip: {
      formatter: (params) => `${params.value[0]}<br/>学习 ${params.value[1]} 分钟`,
    },
    visualMap: {
      min: 0,
      max: 180,
      type: 'piecewise',
      orient: 'horizontal',
      left: 'center',
      bottom: 10,
      itemWidth: 18,
      itemHeight: 12,
      textStyle: { color: '#6b7280' },
      pieces: [
        { min: 120, label: '高', color: '#4e6fe8' },
        { min: 60, max: 119, label: '中', color: '#89a2f3' },
        { min: 1, max: 59, label: '低', color: '#c5d1fb' },
        { value: 0, label: '无', color: '#eef2ff' },
      ],
    },
    calendar: {
      top: 48,
      left: 72,
      right: 28,
      bottom: 76,
      range: [start, end],
      cellSize: ['auto', 24],
      splitLine: { lineStyle: { color: '#d8deea', width: 1 } },
      itemStyle: { borderWidth: 1, borderColor: '#f7f9fc' },
      yearLabel: { show: true, color: '#747b88', fontWeight: 600 },
      monthLabel: { color: '#747b88' },
      dayLabel: { color: '#747b88' },
    },
    series: [{
      type: 'heatmap',
      coordinateSystem: 'calendar',
      data: activityData,
    }],
  })
}

const initTrend = () => {
  if (!trendRef.value) return
  if (!trendChart) trendChart = echarts.init(trendRef.value)
  const dates = Array.from({ length: 14 }, (_, index) => {
    const now = new Date()
    return new Date(now.getTime() - (13 - index) * 86400000).toISOString().slice(5, 10)
  })

  trendChart.setOption({
    color: ['#5b7cfa', '#14b8a6', '#f59e0b'],
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 18, top: 42, bottom: 54 },
    legend: { bottom: 0, icon: 'roundRect' },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 11, color: '#6b7280' },
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: { color: '#6b7280' },
      splitLine: { lineStyle: { color: '#eef2f7' } },
    },
    series: [
      { name: 'Web', type: 'line', data: dates.map((_, i) => 56 + Math.round(Math.sin(i / 2) * 8) + i), smooth: true, symbolSize: 6 },
      { name: 'Crypto', type: 'line', data: dates.map((_, i) => 42 + Math.round(Math.cos(i / 2) * 6) + Math.floor(i / 3)), smooth: true, symbolSize: 6 },
      { name: 'Reverse', type: 'line', data: dates.map((_, i) => 48 + Math.round(Math.sin(i / 3) * 7) + Math.floor(i / 4)), smooth: true, symbolSize: 6 },
    ],
  })
}

const fetchWeeklySummary = async () => {
  try {
    weeklySummary.value = await api.analytics.weeklySummary()
  } catch {
    weeklySummary.value = null
  }
}

const fetchLearningDirections = async () => {
  try {
    const data = await api.studentProfile.learningDirections()
    if (Array.isArray(data) && data.length > 0) {
      directions.value = data
    }
  } catch (error) {
    console.error('Failed to load learning directions:', error)
  }
}

const fetchProfile = async () => {
  try {
    profile.value = await api.studentProfile.get()
  } catch (error) {
    console.error('Failed to load student profile:', error)
  }
}

const fetchTeachingPlan = async () => {
  try {
    teachingPlan.value = await api.analytics.teachingPlan()
  } catch (error) {
    console.error('Failed to load teaching plan score snapshot:', error)
    teachingPlan.value = null
  }
}

const resizeAll = () => {
  radarChart?.resize()
  heatmapChart?.resize()
  trendChart?.resize()
}

watch(activeTab, async (key) => {
  await nextTick()
  if (key === 'radar') {
    initRadar()
    radarChart?.resize()
  } else if (key === 'heatmap') {
    initHeatmap()
    heatmapChart?.resize()
  } else if (key === 'trend') {
    initTrend()
    trendChart?.resize()
  }
})

watch([directionNames, previousAbilityScores, currentAbilityScores], async () => {
  if (activeTab.value !== 'radar') return
  await nextTick()
  initRadar()
})

onMounted(async () => {
  await Promise.all([fetchLearningDirections(), fetchProfile(), fetchTeachingPlan()])
  await nextTick()
  initRadar()
  fetchWeeklySummary()
  window.addEventListener('resize', resizeAll)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeAll)
  radarChart?.dispose()
  heatmapChart?.dispose()
  trendChart?.dispose()
})
</script>

<style scoped>
.analytics-page {
  min-height: calc(100vh - 64px);
  background: #f5f7fb;
  padding: 32px 0 48px;
}

.container {
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 18px;
}

.page-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 22px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #5b7cfa;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.page-title {
  font-size: 32px;
  font-weight: 750;
  color: #181c25;
  margin: 0;
}

.page-desc {
  margin: 10px 0 0;
  color: #697182;
  font-size: 15px;
  line-height: 1.7;
}

.hero-summary {
  min-width: 164px;
  padding: 16px 18px;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 14px 34px rgba(66, 91, 166, 0.10);
  color: #697182;
}

.hero-summary strong {
  display: inline-block;
  margin: 0 6px;
  color: #3158e8;
  font-size: 30px;
}

.summary-label {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}

.overview-card {
  min-height: 104px;
  padding: 18px;
  border-radius: 18px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(66, 91, 166, 0.08);
}

.overview-card.highlight {
  background: linear-gradient(135deg, #eef3ff 0%, #ffffff 70%);
}

.overview-label,
.overview-unit {
  display: block;
  color: #7a8291;
  font-size: 13px;
}

.overview-card strong {
  display: block;
  margin: 8px 0 4px;
  color: #1d2430;
  font-size: 28px;
  font-weight: 760;
}

.analytics-tabs {
  margin-top: 4px;
}

.chart-card,
.card {
  background: #ffffff;
  border-radius: 20px;
  box-shadow: 0 12px 32px rgba(66, 91, 166, 0.08);
}

.chart-card {
  padding: 24px;
}

.chart-copy {
  margin-bottom: 18px;
}

.section-kicker {
  margin: 0 0 6px;
  color: #5b7cfa;
  font-size: 12px;
  font-weight: 700;
}

.chart-copy h2 {
  margin: 0;
  color: #1d2430;
  font-size: 22px;
}

.chart-copy p {
  margin: 8px 0 0;
  max-width: 720px;
  color: #6d7584;
  line-height: 1.7;
}

.chart-layout,
.heatmap-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 20px;
  align-items: stretch;
}

.chart-box {
  width: 100%;
  height: 420px;
}

.heatmap-card {
  min-width: 0;
  border: 1px solid #edf1f7;
  border-radius: 16px;
  background: #fbfcff;
}

.heatmap-box {
  height: 420px;
}

.insight-panel {
  padding: 18px;
  border-radius: 16px;
  background: #f8faff;
  border: 1px solid #edf1f7;
}

.insight-panel h3 {
  margin: 0 0 14px;
  color: #1d2430;
  font-size: 16px;
}

.insight-item {
  padding: 14px 0;
  border-top: 1px solid #e7ecf6;
}

.insight-item:first-of-type {
  border-top: 0;
  padding-top: 0;
}

.insight-item span,
.insight-item small {
  display: block;
  color: #798292;
  font-size: 12px;
}

.insight-item strong {
  display: block;
  margin: 4px 0;
  color: #3158e8;
  font-size: 24px;
}

.insight-note {
  margin: 14px 0 0;
  color: #5d6677;
  line-height: 1.6;
}

.legend-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 18px;
  color: #7a8291;
  font-size: 12px;
}

.legend {
  width: 28px;
  height: 12px;
  border-radius: 999px;
}

.legend.low { background: #c5d1fb; }
.legend.mid { background: #89a2f3; }
.legend.high { background: #4e6fe8; }

.suggestion-list {
  display: grid;
  gap: 12px;
}

.suggestion-item {
  padding: 12px;
  border-radius: 12px;
  background: #ffffff;
}

.suggestion-item strong,
.suggestion-item span {
  display: block;
}

.suggestion-item strong {
  color: #1d2430;
  margin-bottom: 4px;
}

.suggestion-item span {
  color: #6d7584;
  line-height: 1.5;
}

.bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(300px, 0.6fr);
  gap: 20px;
  margin-top: 20px;
}

.card {
  padding: 22px;
}

.card-title {
  font-size: 17px;
  font-weight: 700;
  color: #1d2430;
  margin: 0 0 16px;
}

.weekly-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}

.weekly-stat {
  padding: 16px;
  text-align: center;
  border-radius: 14px;
  background: #f8faff;
}

.ws-value {
  font-size: 28px;
  font-weight: 760;
  color: #3158e8;
  display: block;
}

.ws-label {
  font-size: 13px;
  color: #7a8291;
}

.weekly-summary-text {
  margin: 0;
  font-size: 14px;
  color: #5d6677;
  line-height: 1.7;
}

.action-list {
  display: grid;
  gap: 12px;
}

.action-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  color: #4f5868;
  line-height: 1.55;
}

.action-dot {
  width: 8px;
  height: 8px;
  margin-top: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #5b7cfa;
}

@media (max-width: 980px) {
  .page-hero,
  .chart-layout,
  .heatmap-layout,
  .bottom-grid {
    grid-template-columns: 1fr;
  }

  .page-hero {
    display: grid;
  }

  .overview-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .overview-grid,
  .weekly-grid {
    grid-template-columns: 1fr;
  }

  .chart-card,
  .card {
    padding: 18px;
  }
}
</style>
