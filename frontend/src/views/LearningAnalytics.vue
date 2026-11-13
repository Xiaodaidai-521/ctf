<template>
  <div class="analytics-page">
    <div class="container">
      <section class="page-hero">
        <div>

          <h1 class="page-title">{{ names.growth }} · 学习分析</h1>
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
import { names } from '@/shared/navigation/names'

import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import { tokenValue, tokenNumber } from '@/shared/design/chartTokens'
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
    textStyle: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption'), fontFamily: tokenValue('font-family') },
    color: [tokenValue('series-2'), tokenValue('series-1')],
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
      textStyle: { color: tokenValue('ink-secondary') },
      data: [previousScoreName.value, currentScoreName.value],
    },
    radar: {
      center: ['48%', '52%'],
      radius: '66%',
      splitNumber: 4,
      indicator: directionNames.value.map((name) => ({ name, max: 100 })),
      axisName: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption') },
      splitLine: { lineStyle: { color: tokenValue('line') } },
      splitArea: { areaStyle: { color: [tokenValue('surface-muted'), tokenValue('surface')] } },
      axisLine: { lineStyle: { color: tokenValue('line') } },
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: previousAbilityScores.value,
          name: previousScoreName.value,
          areaStyle: { color: tokenValue('series-2-soft') },
          lineStyle: { color: tokenValue('series-2'), width: 3 },
          itemStyle: { color: tokenValue('series-2') },
        },
        {
          value: currentAbilityScores.value,
          name: currentScoreName.value,
          areaStyle: { color: tokenValue('series-1-soft') },
          lineStyle: { color: tokenValue('series-1'), width: 3 },
          itemStyle: { color: tokenValue('series-1') },
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
    textStyle: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption'), fontFamily: tokenValue('font-family') },
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
      textStyle: { color: tokenValue('ink-muted') },
      pieces: [
        { min: 120, label: '高', color: tokenValue('sequence-high') },
        { min: 60, max: 119, label: '中', color: tokenValue('sequence-mid') },
        { min: 1, max: 59, label: '低', color: tokenValue('sequence-low') },
        { value: 0, label: '无', color: tokenValue('surface-muted') },
      ],
    },
    calendar: {
      top: 48,
      left: 72,
      right: 28,
      bottom: 76,
      range: [start, end],
      cellSize: ['auto', 24],
      splitLine: { lineStyle: { color: tokenValue('line'), width: 1 } },
      itemStyle: { borderWidth: 1, borderColor: tokenValue('surface') },
      yearLabel: { show: true, color: tokenValue('ink-muted'), fontWeight: 600 },
      monthLabel: { color: tokenValue('ink-muted') },
      dayLabel: { color: tokenValue('ink-muted') },
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
    textStyle: { color: tokenValue('ink-secondary'), fontSize: tokenNumber('text-caption'), fontFamily: tokenValue('font-family') },
    color: [tokenValue('series-1'), tokenValue('series-2'), tokenValue('series-3')],
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 18, top: 42, bottom: 54 },
    legend: { bottom: 0, icon: 'roundRect' },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: tokenNumber('text-caption'), color: tokenValue('ink-muted') },
      axisLine: { lineStyle: { color: tokenValue('line') } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      max: 100,
      axisLabel: { color: tokenValue('ink-muted') },
      splitLine: { lineStyle: { color: tokenValue('line') } },
    },
    series: [
      { name: 'Web', type: 'line', data: dates.map((_, i) => 56 + Math.round(Math.sin(i / 2) * 8) + i), smooth: true, symbolSize: 6, symbol: 'circle', lineStyle: { type: 'solid' } },
      { name: 'Crypto', type: 'line', data: dates.map((_, i) => 42 + Math.round(Math.cos(i / 2) * 6) + Math.floor(i / 3)), smooth: true, symbolSize: 6, symbol: 'rect', lineStyle: { type: 'dashed' } },
      { name: 'Reverse', type: 'line', data: dates.map((_, i) => 48 + Math.round(Math.sin(i / 3) * 7) + Math.floor(i / 4)), smooth: true, symbolSize: 6, symbol: 'triangle', lineStyle: { type: 'dotted' } },
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
  min-height:calc(100vh - var(--space-8));
  background:var(--surface-page);
  padding:var(--space-4) 0 var(--space-6);
}

.container {
  max-width:var(--page-width);
  margin:0 auto;
  padding:0 var(--space-2);
}

.page-hero {
  display:flex;
  align-items:flex-end;
  justify-content:space-between;
  gap:var(--space-3);
  margin-bottom:var(--space-3);
}

.eyebrow {
  margin:0 0 var(--space-1);
  color:var(--action);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  letter-spacing:0.08em;
  text-transform:uppercase;
}

.page-title {
  font-size:var(--text-page);
  font-weight: var(--weight-strong);
  color:var(--ink);
  margin:0;
}

.page-desc {
  margin:var(--space-1) 0 0;
  color:var(--ink-secondary);
  font-size:var(--text-caption);
  line-height:1.7;
}

.hero-summary {
  min-width:var(--row-value-width);
  padding:var(--space-2) var(--space-2);
  border-radius:var(--radius-panel);
  background:var(--surface);
  box-shadow: var(--shadow-raised);
  color:var(--ink-secondary);
}

.hero-summary strong {
  display:inline-block;
  margin:0 calc(var(--space-1) / 2);
  color:var(--action);
  font-size:var(--text-section);
}

.summary-label {
  display:block;
  margin-bottom:calc(var(--space-1) / 2);
  font-size:var(--text-caption);
}

.overview-grid {
  display:grid;
  grid-template-columns:repeat(4, minmax(0, 1fr));
  gap:var(--space-2);
  margin-bottom:var(--space-2);
}

.overview-card {
  min-height:var(--tile-short-height);
  padding:var(--space-2);
  border-radius:var(--radius-panel);
  background:var(--surface);
  box-shadow: var(--shadow-raised);
}

.overview-card.highlight {
  background: var(--surface-muted);
}

.overview-label,
.overview-unit {
  display:block;
  color:var(--ink-muted);
  font-size:var(--text-caption);
}

.overview-card strong {
  display:block;
  margin:var(--space-1) 0 calc(var(--space-1) / 2);
  color:var(--ink);
  font-size:var(--text-section);
  font-weight: var(--weight-strong);
}

.analytics-tabs {
  margin-top:calc(var(--space-1) / 2);
}

.chart-card,
.card {
  background:var(--surface);
  border-radius:var(--radius-panel);
  box-shadow: var(--shadow-raised);
}

.chart-card {
  padding:var(--space-3);
}

.chart-copy {
  margin-bottom:var(--space-2);
}

.section-kicker {
  margin:0 0 calc(var(--space-1) / 2);
  color:var(--action);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.chart-copy h2 {
  margin:0;
  color:var(--ink);
  font-size:var(--text-card);
}

.chart-copy p {
  margin:var(--space-1) 0 0;
  max-width:var(--search-width);
  color:var(--ink-secondary);
  line-height:1.7;
}

.chart-layout,
.heatmap-layout {
  display:grid;
  grid-template-columns:minmax(0, 1fr) var(--menu-width);
  gap:var(--space-2);
  align-items:stretch;
}

.chart-box {
  width:100%;
  height:var(--content-height);
}

.heatmap-card {
  min-width:0;
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-panel);
  background:var(--surface);
}

.heatmap-box {
  height:var(--content-height);
}

.insight-panel {
  padding:var(--space-2);
  border-radius:var(--radius-panel);
  background:var(--surface-muted);
  border:var(--stroke) solid var(--line);
}

.insight-panel h3 {
  margin:0 0 var(--space-2);
  color:var(--ink);
  font-size:var(--text-body);
}

.insight-item {
  padding:var(--space-2) 0;
  border-top:var(--stroke) solid var(--line);
}

.insight-item:first-of-type {
  border-top:0;
  padding-top:0;
}

.insight-item span,
.insight-item small {
  display:block;
  color:var(--ink-muted);
  font-size:var(--text-caption);
}

.insight-item strong {
  display:block;
  margin:calc(var(--space-1) / 2) 0;
  color:var(--action);
  font-size:var(--text-section);
}

.insight-note {
  margin:var(--space-2) 0 0;
  color:var(--ink-secondary);
  line-height:1.6;
}

.legend-row {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  margin-top:var(--space-2);
  color:var(--ink-muted);
  font-size:var(--text-caption);
}

.legend {
  width:var(--space-3);
  height:var(--space-1);
  border-radius:var(--radius-pill);
}

.legend.low { background:var(--sequence-low); }
.legend.mid { background:var(--sequence-mid); }
.legend.high { background:var(--sequence-high); }

.suggestion-list {
  display:grid;
  gap:var(--space-1);
}

.suggestion-item {
  padding:var(--space-1);
  border-radius:var(--radius-panel);
  background:var(--surface);
}

.suggestion-item strong,
.suggestion-item span {
  display:block;
}

.suggestion-item strong {
  color:var(--ink);
  margin-bottom:calc(var(--space-1) / 2);
}

.suggestion-item span {
  color:var(--ink-secondary);
  line-height:1.5;
}

.bottom-grid {
  display:grid;
  grid-template-columns:minmax(0, 1.4fr) minmax(var(--menu-width), 0.6fr);
  gap:var(--space-2);
  margin-top:var(--space-2);
}

.card {
  padding:var(--space-3);
}

.card-title {
  font-size:var(--text-body);
  font-weight: var(--weight-strong);
  color:var(--ink);
  margin:0 0 var(--space-2);
}

.weekly-grid {
  display:grid;
  grid-template-columns:repeat(3, 1fr);
  gap:var(--space-2);
  margin-bottom:var(--space-2);
}

.weekly-stat {
  padding:var(--space-2);
  text-align:center;
  border-radius:var(--radius-panel);
  background:var(--surface-muted);
}

.ws-value {
  font-size:var(--text-section);
  font-weight: var(--weight-strong);
  color:var(--action);
  display:block;
}

.ws-label {
  font-size:var(--text-caption);
  color:var(--ink-muted);
}

.weekly-summary-text {
  margin:0;
  font-size:var(--text-caption);
  color:var(--ink-secondary);
  line-height:1.7;
}

.action-list {
  display:grid;
  gap:var(--space-1);
}

.action-item {
  display:flex;
  align-items:flex-start;
  gap:var(--space-1);
  color:var(--ink-secondary);
  line-height:1.55;
}

.action-dot {
  width:var(--space-1);
  height:var(--space-1);
  margin-top:var(--space-1);
  flex:0 0 auto;
  border-radius:50%;
  background:var(--action);
}

@media (max-width: 1120px) {
  .page-hero,
  .chart-layout,
  .heatmap-layout,
  .bottom-grid {
    grid-template-columns:1fr;
  }

  .page-hero {
    display:grid;
  }

  .overview-grid {
    grid-template-columns:repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .overview-grid,
  .weekly-grid {
    grid-template-columns:1fr;
  }

  .chart-card,
  .card {
    padding:var(--space-2);
  }
}
</style>
