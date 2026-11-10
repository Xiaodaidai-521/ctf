<template>
  <div class="exam-center-page">
    <div class="page-header">
      <h1 class="page-title">测试中心</h1>
      <p class="page-subtitle">参加理论考试和实战训练，检验你的学习成果</p>
    </div>

    <!-- 学习水平评级 -->
    <div class="level-section">
      <div class="level-card" :class="'level-' + level.grade.toLowerCase()">
        <div class="level-grade">{{ level.grade }}</div>
        <div class="level-info">
          <div class="level-title">{{ level.title }}</div>
          <div class="level-desc">{{ level.description }}</div>
        </div>
        <div class="level-progress">
          <div class="progress-label">
            <template v-if="level.isTopLevel">已达到最高等级</template>
            <template v-else>距离下一等级还需 {{ level.remainingScore }} 分</template>
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill"
              :style="{ width: level.progressPercent + '%' }"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 成绩趋势图 -->
    <div class="chart-section">
      <div class="section-header">
        <h2 class="section-title">成绩趋势</h2>
        <div class="section-subtitle">历次考试成绩变化</div>
      </div>
      <div class="chart-container">
        <div ref="chartRef" class="chart"></div>
        <div v-if="!hasExamHistory" class="no-data">
          <div class="no-data-icon"><i class="bi bi-graph-up"></i></div>
          <div class="no-data-text">暂无考试记录</div>
          <div class="no-data-desc">完成考试后将显示成绩趋势图</div>
        </div>
      </div>
    </div>

    <!-- 考试统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon">
          <i class="bi bi-journal-check"></i>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total_exams }}</div>
          <div class="stat-label">考试总数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">
          <i class="bi bi-check-circle"></i>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.passed_exams }}</div>
          <div class="stat-label">通过考试</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">
          <i class="bi bi-trophy"></i>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.average_score.toFixed(1) }}%</div>
          <div class="stat-label">平均成绩</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">
          <i class="bi bi-star"></i>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ Number(stats.best_score || 0).toFixed(1) }}%</div>
          <div class="stat-label">最高成绩</div>
        </div>
      </div>
    </div>

    <!-- 开始考试区域 -->
    <div class="start-exam-section">
      <div class="exam-info-card">
        <div class="exam-info-header">
          <h3 class="exam-info-title">综合测试</h3>
          <div class="exam-info-badge">推荐</div>
        </div>
        <div class="exam-info-content">
          <div class="exam-type">
            <div class="type-item">
              <div class="type-icon"><i class="bi bi-journal-text"></i></div>
              <div class="type-info">
                <div class="type-name">理论测试</div>
                <div class="type-desc">30单选 + 20多选 + 20判断</div>
              </div>
            </div>
            <div class="type-item">
              <div class="type-icon"><i class="bi bi-terminal"></i></div>
              <div class="type-info">
                <div class="type-name">实战测试</div>
                <div class="type-desc">3简单 + 2中等 + 1困难</div>
              </div>
            </div>
          </div>
          <div class="exam-tips">
            <div class="tip-item"><i class="bi bi-clock"></i> 理论测试限时 180 分钟</div>
            <div class="tip-item"><i class="bi bi-clock-history"></i> 实战测试限时 180 分钟</div>
            <div class="tip-item"><i class="bi bi-arrow-right-square"></i> 完成理论测试后自动进入实战测试</div>
          </div>
        </div>
        <div v-if="hasOngoingExam && ongoingExamId" class="ongoing-exam-actions">
          <button
            class="btn btn-primary btn-large btn-block"
            @click="continueExam"
          >
            继续进行中的考试
          </button>
          <button
            class="btn btn-outline btn-large btn-block"
            @click="abandonAndStartNew"
          >
            放弃当前考试并开始新考试
          </button>
          <div class="ongoing-warning">
            <i class="bi bi-exclamation-triangle"></i>
            放弃当前考试将无法恢复
          </div>
        </div>
        <button
          v-else
          class="btn btn-primary btn-large btn-block"
          @click="startExam"
          :disabled="loading"
        >
          <span v-if="loading">正在准备考试...</span>
          <span v-else>开始测试</span>
        </button>
      </div>
    </div>

    <!-- 最近考试记录 -->
    <div class="history-section">
      <div class="section-header">
        <h2 class="section-title">最近考试记录</h2>
        <router-link to="/exam-history" class="view-all-link">查看全部 →</router-link>
      </div>
      <div class="history-list">
        <div v-if="recentRecords.length === 0" class="no-history">
          <div class="no-history-icon"><i class="bi bi-clipboard2-check"></i></div>
          <div class="no-history-text">暂无考试记录</div>
          <div class="no-history-desc">开始测试后，考试记录将显示在这里</div>
        </div>
        <div
          v-for="record in recentRecords"
          :key="record.id"
          class="history-item"
          @click="viewResult(record.id)"
        >
          <div class="history-left">
            <div class="history-type">{{ getExamTypeText(record.exam_type) }}</div>
            <div class="history-title">{{ record.exam_title || '未命名考试' }}</div>
            <div class="history-time">{{ formatTime(record.created_at) }}</div>
          </div>
          <div class="history-right">
            <div class="history-score" :class="{ 'passed': record.is_passed, 'failed': !record.is_passed }">
              {{ record.score }}分
            </div>
            <div class="history-status">
              {{ record.is_passed ? '通过' : '未通过' }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import api from '@/api'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()

const chartRef = ref(null)
let scoreChart = null
const loading = ref(false)
const stats = ref({
  total_exams: 0,
  theory_exams: 0,
  practice_exams: 0,
  passed_exams: 0,
  average_score: 0,
  best_score: 0,
})

const level = ref({
  grade: 'D',
  title: '初学者',
  description: '继续努力，多加练习',
  currentScore: 0,
  nextLevelScore: 60,
  progressPercent: 0,
})

const scoreTrend = ref({
  dates: [],
  scores: [],
  theory_scores: [],
  practice_scores: [],
})

const recentRecords = ref([])
const hasExamHistory = ref(false)
const ongoingExamId = ref(null)
const hasOngoingExam = computed(() => !!ongoingExamId.value)

// 学习等级定义
const defaultLevelDefinitions = [
  { grade: 'S', title: '大师', description: 'CTF 界的传奇人物', minScore: 90 },
  { grade: 'A', title: '专家', description: 'CTF 领域的顶尖高手', minScore: 80 },
  { grade: 'B', title: '高手', description: '经验丰富的安全专家', minScore: 70 },
  { grade: 'C', title: '进阶', description: '具备一定的安全技能', minScore: 60 },
  { grade: 'D', title: '初学者', description: '继续努力，多加练习', minScore: 0 },
]
const levelDefinitions = ref(defaultLevelDefinitions)

const normalizePercent = (value) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(100, n))
}

// 计算学习等级
const calculateLevel = (averageScore) => {
  const score = normalizePercent(averageScore)
  const definitions = [...levelDefinitions.value].sort((a, b) => Number(b.minScore || 0) - Number(a.minScore || 0))
  for (const levelDef of definitions) {
    const minScore = normalizePercent(levelDef.minScore)
    if (score >= minScore) {
      const nextLevelIndex = definitions.indexOf(levelDef) - 1
      const nextLevel = nextLevelIndex >= 0 ? definitions[nextLevelIndex] : null
      const nextLevelScore = nextLevel ? normalizePercent(nextLevel.minScore) : 100
      const rawProgress = nextLevel
        ? ((score - minScore) / Math.max(1, nextLevelScore - minScore)) * 100
        : 100

      return {
        ...levelDef,
        currentScore: score,
        nextLevelScore,
        remainingScore: nextLevel ? Math.max(0, Math.ceil(nextLevelScore - score)) : 0,
        isTopLevel: !nextLevel,
        progressPercent: normalizePercent(rawProgress),
      }
    }
  }
  const fallback = definitions[definitions.length - 1] || defaultLevelDefinitions[defaultLevelDefinitions.length - 1]
  return {
    ...fallback,
    currentScore: score,
    nextLevelScore: 60,
    remainingScore: Math.max(0, Math.ceil(60 - score)),
    isTopLevel: false,
    progressPercent: normalizePercent(score),
  }
}

// 初始化图表
const loadLevelDefinitions = async () => {
  try {
    const data = await api.exams.levelRules()
    if (Array.isArray(data) && data.length > 0) {
      levelDefinitions.value = data
    }
  } catch (error) {
    console.error('Failed to load exam level rules:', error)
  }
}

const initChart = () => {
  if (!chartRef.value || !hasExamHistory.value) return

  if (!scoreChart) scoreChart = echarts.init(chartRef.value)
  const option = {
    color: ['#b7352d', '#4f7c52', '#d58b25'],
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255, 250, 242, 0.96)',
      borderColor: '#e4d8c8',
      borderWidth: 1,
      textStyle: { color: '#181713' },
      valueFormatter: (value) => (value === null || value === undefined ? '-' : `${value}%`),
    },
    legend: {
      data: ['总分', '理论', '实战'],
      bottom: 0,
      icon: 'roundRect',
      itemWidth: 18,
      itemHeight: 10,
      textStyle: { color: '#6f665d' },
    },
    grid: {
      left: 42,
      right: 24,
      top: 28,
      bottom: 56,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: scoreTrend.value.dates,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#e4d8c8' } },
      axisLabel: {
        color: '#8a8178',
        fontSize: 11,
        hideOverlap: true,
        formatter: (value) => (value && value.length > 5 ? value.slice(5) : value),
      },
    },
    yAxis: {
      type: 'value',
      name: '成绩',
      min: 0,
      max: 100,
      axisLabel: {
        color: '#8a8178',
        formatter: '{value}%',
      },
      splitLine: { lineStyle: { color: '#ece2d6' } },
    },
    series: [
      {
        name: '总分',
        type: 'line',
        data: scoreTrend.value.scores,
        smooth: true,
        symbolSize: 7,
        lineStyle: { width: 3 },
        areaStyle: { color: 'rgba(183, 53, 45, 0.10)' },
      },
      {
        name: '理论',
        type: 'line',
        data: scoreTrend.value.theory_scores,
        smooth: true,
        symbolSize: 7,
        lineStyle: { width: 2 },
        connectNulls: false,
      },
      {
        name: '实战',
        type: 'line',
        data: scoreTrend.value.practice_scores,
        smooth: true,
        symbolSize: 7,
        lineStyle: { width: 2 },
        connectNulls: false,
      },
    ],
  }
  scoreChart.setOption(option, true)
}

const resizeChart = () => scoreChart?.resize()

const fillMissingTrendSeries = (values, length) => {
  const series = Array.isArray(values) ? values.slice(0, length) : []
  while (series.length < length) series.push(null)

  const firstValue = series.find((value) => value !== null && value !== undefined)
  let lastValue = firstValue ?? 0

  return series.map((value) => {
    if (value !== null && value !== undefined) {
      lastValue = value
      return value
    }
    return lastValue
  })
}

const normalizeTrend = (trend) => {
  const dates = Array.isArray(trend?.dates) ? trend.dates : []
  return {
    dates,
    scores: Array.isArray(trend?.scores) ? trend.scores : [],
    theory_scores: Array.isArray(trend?.theory_scores) ? trend.theory_scores : [],
    practice_scores: fillMissingTrendSeries(trend?.practice_scores, dates.length),
  }
}

// 加载数据
const loadData = async () => {
  try {
    // 加载统计数据
    await loadLevelDefinitions()

    const statsRes = await api.exams.statistics()
    stats.value = statsRes

    // 计算学习等级
    level.value = calculateLevel(stats.value.average_score)

    // 加载成绩趋势
    const trendRes = await api.exams.scoreTrend()
    scoreTrend.value = normalizeTrend(trendRes)
    hasExamHistory.value = scoreTrend.value.dates.length > 0

    // 先渲染趋势图，避免后续历史记录/进行中考试接口失败时留下空白图表区域
    await nextTick()
    initChart()

    // 加载最近考试记录
    const historyRes = await api.exams.myHistory()
    recentRecords.value = historyRes.records.slice(0, 5) // 只显示最近5条

    // 检查是否有进行中的考试
    const recordsRes = await api.exams.records({ status: 'in_progress' })
    if (recordsRes.results && recordsRes.results.length > 0) {
      ongoingExamId.value = recordsRes.results[0].id
    }
  } catch (error) {
    console.error('加载数据失败:', error)
  }
}

// 继续进行中的考试
const continueExam = () => {
  if (ongoingExamId.value) {
    router.push(`/exam-taking/${ongoingExamId.value}`)
  }
}

// 放弃当前考试并开始新考试
const abandonAndStartNew = async () => {
  if (!confirm('确定要放弃当前考试吗？此操作无法撤销！')) {
    return
  }

  loading.value = true
  try {
    // 调用放弃考试 API
    await api.exams.startComprehensiveExam({ abandon: true })

    // 清空进行中考试 ID
    ongoingExamId.value = null
    hasOngoingExam.value = false

    // 开始新考试
    await startExam()
  } catch (error) {
    console.error('放弃考试失败:', error)
    alert(error.response?.data?.error || '操作失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

// 开始考试
const startExam = async () => {
  loading.value = true
  try {
    const res = await api.exams.startComprehensiveExam()
    if (res.theory_record) {
      router.push(`/exam-taking/${res.theory_record.id}`)
    }
  } catch (error) {
    console.error('创建考试失败:', error)
    alert(error.response?.data?.error || '创建考试失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

// 查看结果
const viewResult = (recordId) => {
  router.push(`/exam-result/${recordId}`)
}

// 格式化时间
const formatTime = (timeString) => {
  const date = new Date(timeString)
  const now = new Date()
  const diff = now - date

  if (diff < 60000) {
    return '刚刚'
  } else if (diff < 3600000) {
    return `${Math.floor(diff / 60000)}分钟前`
  } else if (diff < 86400000) {
    return `${Math.floor(diff / 3600000)}小时前`
  } else if (diff < 604800000) {
    return `${Math.floor(diff / 86400000)}天前`
  } else {
    return date.toLocaleDateString('zh-CN')
  }
}

// 获取考试类型文本
const getExamTypeText = (type) => {
  const map = {
    'theory': '理论考试',
    'practice': '实战考试',
  }
  return map[type] || '考试'
}

onMounted(() => {
  loadData()
  window.addEventListener('resize', resizeChart)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeChart)
  scoreChart?.dispose()
})
</script>

<style scoped>
.exam-center-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 44px 24px 32px;
}

.page-header {
  text-align: center;
  margin-bottom: 40px;
}

.page-title {
  font-size: 44px;
  line-height: 1;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.page-subtitle {
  font-size: 16px;
  color: var(--text-secondary);
}

/* 学习等级卡片 */
.level-section {
  margin-bottom: 32px;
}

.level-card {
  background: var(--bg-paper-2);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 28px;
  box-shadow: 10px 10px 0 rgba(24, 23, 19, 0.06);
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) minmax(240px, 360px);
  align-items: center;
  gap: 24px;
  overflow: hidden;
}

.level-grade {
  width: 88px;
  height: 88px;
  border-radius: 8px;
  background: var(--bg-dark);
  color: var(--secondary-color);
  border: 1px solid rgba(24, 23, 19, 0.2);
  font-size: 42px;
  font-weight: 950;
  display: flex;
  align-items: center;
  justify-content: center;
}

.level-info {
  min-width: 0;
}

.level-title {
  font-size: 24px;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.level-desc {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.level-progress {
  min-width: 0;
}

.progress-label {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 8px;
  text-align: right;
  white-space: nowrap;
}

.progress-bar {
  height: 10px;
  background: #fffaf2;
  border: 1px solid rgba(24, 23, 19, 0.12);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--primary-color);
  border-radius: 0;
  transition: width 0.3s;
}

/* 图表区域 */
.chart-section {
  background: #fffaf2bd;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 28px;
  box-shadow: 10px 10px 0 rgba(24, 23, 19, 0.04);
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 24px;
}

.section-title {
  font-size: 20px;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.section-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
}

.chart-container {
  min-height: 320px;
  position: relative;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: #fffaf2a8;
  padding: 12px 12px 4px;
}

.chart {
  width: 100%;
  height: 340px;
}

.no-data {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}

.no-data-icon,
.no-history-icon {
  width: 72px;
  height: 72px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(24, 23, 19, 0.16);
  border-radius: 8px;
  background: #fffaf2bd;
  color: var(--primary-color);
  font-size: 30px;
  margin-bottom: 16px;
}

.no-data-text {
  font-size: 16px;
  margin-bottom: 8px;
}

.no-data-desc {
  font-size: 14px;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 20px;
  margin-bottom: 32px;
}

.stat-card {
  background: #fffaf2bd;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 24px;
  box-shadow: 8px 8px 0 rgba(24, 23, 19, 0.04);
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 8px;
  border: 1px solid rgba(24, 23, 19, 0.16);
  background: #fffaf2bd;
  color: var(--primary-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: var(--text-secondary);
}

/* 开始考试区域 */
.start-exam-section {
  margin-bottom: 32px;
}

.exam-info-card {
  background: #fffaf2bd;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 32px;
  box-shadow: 10px 10px 0 rgba(24, 23, 19, 0.05);
}

.exam-info-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.exam-info-title {
  font-size: 24px;
  font-weight: 950;
  color: var(--text-primary);
}

.exam-info-badge {
  background: var(--bg-dark);
  color: #fbf7ef;
  padding: 6px 14px;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 850;
}

.exam-type {
  display: flex;
  gap: 24px;
  margin-bottom: 24px;
}

.type-item {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  background: #fffaf294;
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.type-icon {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(24, 23, 19, 0.16);
  border-radius: 6px;
  background: #fffaf2bd;
  color: var(--primary-color);
  font-size: 20px;
  flex-shrink: 0;
}

.type-name {
  font-size: 16px;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.type-desc {
  font-size: 14px;
  color: var(--text-secondary);
}

.exam-tips {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 24px;
  padding: 16px;
  background: rgba(239, 196, 107, 0.16);
  border: 1px solid rgba(239, 196, 107, 0.35);
  border-radius: 6px;
}

.tip-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #785313;
  font-weight: 700;
}

.ongoing-tip {
  margin-top: 12px;
  padding: 12px;
  background: rgba(183, 53, 45, 0.08);
  color: var(--primary-color);
  border: 1px solid rgba(183, 53, 45, 0.18);
  border-radius: 6px;
  text-align: center;
  font-size: 14px;
}

.ongoing-exam-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ongoing-warning {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  background: rgba(183, 53, 45, 0.08);
  color: var(--primary-color);
  border: 1px solid rgba(183, 53, 45, 0.18);
  border-radius: 6px;
  text-align: center;
  font-size: 14px;
  font-weight: 500;
}

.btn-large {
  padding: 16px 32px;
  font-size: 18px;
  font-weight: bold;
}

/* 历史记录 */
.history-section {
  background: #fffaf2bd;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 32px;
  box-shadow: 10px 10px 0 rgba(24, 23, 19, 0.04);
}

.view-all-link {
  color: var(--primary-color);
  text-decoration: none;
  font-size: 14px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.no-history {
  padding: 48px;
  text-align: center;
  color: var(--text-muted);
}

.no-history-text {
  font-size: 16px;
  margin-bottom: 8px;
}

.no-history-desc {
  font-size: 14px;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  background: #fffaf294;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s;
}

.history-item:hover {
  background: var(--bg-paper-2);
  transform: translateX(4px);
}

.history-left {
  flex: 1;
}

.history-type {
  display: inline-block;
  padding: 4px 12px;
  background: var(--bg-dark);
  color: #fbf7ef;
  border-radius: 4px;
  font-size: 12px;
  margin-bottom: 8px;
}

.history-title {
  font-size: 16px;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.history-time {
  font-size: 14px;
  color: var(--text-secondary);
}

.history-right {
  text-align: right;
}

.history-score {
  font-size: 24px;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.history-score.passed {
  color: var(--success-color);
}

.history-score.failed {
  color: var(--primary-color);
}

.history-status {
  font-size: 14px;
  color: var(--text-secondary);
}

@media (max-width: 820px) {
  .exam-center-page {
    padding: 18px;
  }

  .level-card {
    grid-template-columns: auto minmax(0, 1fr);
    align-items: start;
  }

  .level-progress {
    grid-column: 1 / -1;
    width: 100%;
  }

  .progress-label {
    text-align: left;
  }

  .chart-section,
  .history-section,
  .exam-info-card {
    padding: 20px;
  }
}

@media (max-width: 560px) {
  .level-card {
    grid-template-columns: 1fr;
    justify-items: start;
  }

  .level-grade {
    width: 72px;
    height: 72px;
    font-size: 34px;
  }

  .exam-type {
    flex-direction: column;
  }
}
</style>
