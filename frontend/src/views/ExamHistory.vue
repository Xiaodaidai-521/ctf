<template>
  <div class="exam-history-page">
    <div class="page-header">
      <h1 class="page-title">考试历史</h1>
      <p class="page-subtitle">查看您的所有考试记录</p>
    </div>

    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div class="loading-text">加载中...</div>
    </div>

    <div v-else-if="history.length > 0" class="history-content">
      <!-- 筛选器 -->
      <div class="filter-bar">
        <select v-model="filterType" class="filter-select">
          <option value="all">全部类型</option>
          <option value="theory">理论考试</option>
          <option value="practice">实战考试</option>
        </select>
        <select v-model="filterStatus" class="filter-select">
          <option value="all">全部状态</option>
          <option value="completed">已完成</option>
          <option value="in_progress">进行中</option>
          <option value="abandoned">已放弃</option>
        </select>
      </div>

      <!-- 考试列表 -->
      <div class="history-list">
        <div
          v-for="record in filteredHistory"
          :key="record.id"
          class="history-item"
          @click="viewResult(record.id)"
        >
          <div class="history-left">
            <div class="history-type" :class="'type-' + record.exam_type">
              {{ getExamTypeText(record.exam_type) }}
            </div>
            <div class="history-title">{{ record.exam_title || '未命名考试' }}</div>
            <div class="history-time">{{ formatDateTime(record.created_at) }}</div>
            <div class="history-meta">
              <span v-if="record.total_questions">共 {{ record.total_questions }} 题</span>
              <span v-if="record.time_spent">用时 {{ formatTime(record.time_spent) }}</span>
            </div>
          </div>
          <div class="history-right">
            <div class="history-score" :class="{ 'passed': record.is_passed, 'failed': !record.is_passed }">
              {{ record.score !== null ? record.score : '-' }}分
            </div>
            <div class="history-status" :class="'status-' + record.status">
              {{ getStatusText(record.status) }}
            </div>
            <div v-if="record.is_passed !== null" class="history-passed">
              {{ record.is_passed ? '通过' : '未通过' }}
            </div>
          </div>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="action-buttons">
        <button class="btn btn-outline" @click="backToCenter">
          <i class="bi bi-arrow-left"></i>
          返回测试中心
        </button>
      </div>
    </div>

    <div v-else class="empty-state">
      <div class="empty-icon">📋</div>
      <div class="empty-text">暂无考试记录</div>
      <div class="empty-desc">开始测试后，考试记录将显示在这里</div>
      <button class="btn btn-primary" @click="goToExamCenter">
        开始测试
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'

const router = useRouter()

const history = ref([])
const loading = ref(true)
const filterType = ref('all')
const filterStatus = ref('all')

// 筛选后的历史记录
const filteredHistory = computed(() => {
  return history.value.filter(record => {
    const typeMatch = filterType.value === 'all' || record.exam_type === filterType.value
    const statusMatch = filterStatus.value === 'all' || record.status === filterStatus.value
    return typeMatch && statusMatch
  })
})

// 获取考试类型文本
const getExamTypeText = (type) => {
  const map = {
    'theory': '理论考试',
    'practice': '实战考试',
  }
  return map[type] || '考试'
}

// 获取状态文本
const getStatusText = (status) => {
  const map = {
    'completed': '已完成',
    'in_progress': '进行中',
    'pending': '待开始',
    'abandoned': '已放弃',
  }
  return map[status] || status
}

// 格式化时间
const formatTime = (seconds) => {
  if (!seconds) return '-'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60

  if (hours > 0) {
    return `${hours}小时${minutes}分`
  } else if (minutes > 0) {
    return `${minutes}分${secs}秒`
  }
  return `${secs}秒`
}

// 格式化日期时间
const formatDateTime = (dateTimeStr) => {
  if (!dateTimeStr) return '-'
  const date = new Date(dateTimeStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// 查看结果
const viewResult = (recordId) => {
  router.push(`/exam-result/${recordId}`)
}

// 返回测试中心
const backToCenter = () => {
  router.push('/exam-center')
}

// 前往测试中心
const goToExamCenter = () => {
  router.push('/exam-center')
}

// 加载历史记录
const loadHistory = async () => {
  loading.value = true
  try {
    const response = await api.exams.myHistory()
    history.value = response.records || []
  } catch (error) {
    console.error('加载考试历史失败:', error)
    alert('加载考试历史失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.exam-history-page {
  min-height: 100vh;
  background: #f5f5f5;
  padding: 32px;
}

.page-header {
  text-align: center;
  margin-bottom: 40px;
}

.page-title {
  font-size: 32px;
  font-weight: bold;
  color: #1a1a1a;
  margin: 0 0 8px 0;
}

.page-subtitle {
  font-size: 16px;
  color: #666;
  margin: 0;
}

.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f0f0f0;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  margin-top: 16px;
  color: #666;
}

.filter-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.filter-select {
  padding: 8px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 14px;
  background: white;
  cursor: pointer;
}

.history-list {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: all 0.2s;
}

.history-item:last-child {
  border-bottom: none;
}

.history-item:hover {
  background: #f8f9fa;
}

.history-left {
  flex: 1;
}

.history-type {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 8px;
}

.type-theory {
  background: #e6f7ff;
  color: #1890ff;
}

.type-practice {
  background: #fff7e6;
  color: #faad14;
}

.history-title {
  font-size: 16px;
  font-weight: 500;
  color: #1a1a1a;
  margin-bottom: 4px;
}

.history-time {
  font-size: 14px;
  color: #999;
  margin-bottom: 8px;
}

.history-meta {
  font-size: 14px;
  color: #666;
}

.history-meta span {
  margin-right: 16px;
}

.history-right {
  text-align: right;
}

.history-score {
  font-size: 24px;
  font-weight: bold;
  margin-bottom: 4px;
}

.history-score.passed {
  color: #52c41a;
}

.history-score.failed {
  color: #ff4d4f;
}

.history-status {
  font-size: 14px;
  margin-bottom: 4px;
}

.status-completed {
  color: #52c41a;
}

.status-in_progress {
  color: #1890ff;
}

.status-pending {
  color: #faad14;
}

.status-abandoned {
  color: #999;
}

.history-passed {
  font-size: 12px;
  color: #666;
}

.action-buttons {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 32px;
}

.empty-state {
  text-align: center;
  padding: 80px 0;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.empty-text {
  font-size: 18px;
  font-weight: 500;
  color: #1a1a1a;
  margin-bottom: 8px;
}

.empty-desc {
  font-size: 14px;
  color: #666;
  margin-bottom: 24px;
}
</style>
