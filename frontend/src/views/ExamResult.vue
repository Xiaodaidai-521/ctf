<template>
  <div class="exam-result-page">
    <div class="page-header">
      <h1 class="page-title">考试结果</h1>
      <p class="page-subtitle">查看您的考试表现</p>
    </div>

    <div v-if="loading" class="loading">
      <div class="loading-spinner"></div>
      <div class="loading-text">加载中...</div>
    </div>

    <div v-else-if="result" class="result-content">
      <!-- 结果概览卡片 -->
      <div class="overview-card">
        <div class="overview-left">
          <div class="score-display" :class="{ 'passed': result.is_passed, 'failed': !result.is_passed }">
            <div class="score-number">{{ result.score }}</div>
            <div class="score-label">总分</div>
          </div>
          <div class="result-badge" :class="result.is_passed ? 'passed' : 'failed'">
            {{ result.is_passed ? '🎉 通过' : '❌ 未通过' }}
          </div>
        </div>
        <div class="overview-right">
          <div class="info-grid">
            <div class="info-item">
              <div class="info-label">考试类型</div>
              <div class="info-value">{{ getExamTypeText(result.exam_type) }}</div>
            </div>
            <div class="info-item">
              <div class="info-label">正确题数</div>
              <div class="info-value">{{ result.correct_count }} / {{ result.total_questions || '-' }}</div>
            </div>
            <div class="info-item">
              <div class="info-label">正确率</div>
              <div class="info-value">{{ calculateAccuracy(result) }}%</div>
            </div>
            <div class="info-item">
              <div class="info-label">用时</div>
              <div class="info-value">{{ formatTime(result.time_spent) }}</div>
            </div>
            <div class="info-item">
              <div class="info-label">考试时间</div>
              <div class="info-value">{{ formatDateTime(result.created_at) }}</div>
            </div>
            <div class="info-item" v-if="result.theory_exam">
              <div class="info-label">及格分数</div>
              <div class="info-value">{{ result.theory_exam.pass_score }}分</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 答题详情 -->
      <div class="answers-section">
        <div class="section-header">
          <h2 class="section-title">答题详情</h2>
        </div>
        <div class="answers-list">
          <div
            v-for="(answer, index) in result.answers"
            :key="index"
            class="answer-item"
            :class="{ 'correct': answer.is_correct, 'wrong': !answer.is_correct }"
          >
            <div class="answer-header">
              <div class="answer-number">第 {{ index + 1 }} 题</div>
              <div class="answer-status">
                <i v-if="answer.is_correct" class="bi bi-check-circle-fill text-success"></i>
                <i v-else class="bi bi-x-circle-fill text-danger"></i>
                <span>{{ answer.is_correct ? '正确' : '错误' }}</span>
              </div>
              <div class="answer-points">+{{ answer.points_earned }}分</div>
            </div>
            <div class="answer-content">
              <div class="question-text">
                {{ answer.question_text || '题目内容' }}
              </div>
              <div class="answer-comparison">
                <div class="comparison-item">
                  <div class="comparison-label user-label">您的答案:</div>
                  <div class="comparison-value user-value">{{ answer.user_answer || '未作答' }}</div>
                </div>
                <div class="comparison-item" v-if="!answer.is_correct && answer.correct_answer">
                  <div class="comparison-label correct-label">正确答案:</div>
                  <div class="comparison-value correct-value">{{ answer.correct_answer }}</div>
                </div>
              </div>
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
        <button v-if="result.practice_record_id" class="btn btn-primary" @click="goToPracticeExam">
          进入实战考试 <i class="bi bi-arrow-right"></i>
        </button>
        <button class="btn btn-primary" @click="retakeExam">
          <i class="bi bi-arrow-repeat"></i>
          再次挑战
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '@/api'

const router = useRouter()
const route = useRoute()

const recordId = route.params.id
const result = ref(null)
const loading = ref(true)

// 获取考试类型文本
const getExamTypeText = (type) => {
  const map = {
    'theory': '理论考试',
    'practice': '实战考试',
  }
  return map[type] || '考试'
}

// 计算正确率
const calculateAccuracy = (record) => {
  if (!record.total_questions || record.total_questions === 0) return 0
  return Math.round((record.correct_count / record.total_questions) * 100)
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

// 返回测试中心
const backToCenter = () => {
  router.push('/exam-center')
}

// 进入实战考试
const goToPracticeExam = () => {
  if (result.value && result.value.practice_record_id) {
    router.push(`/exam-taking/${result.value.practice_record_id}`)
  }
}

// 再次挑战
const retakeExam = () => {
  router.push('/exam-center')
}

// 加载考试结果
const loadResult = async () => {
  try {
    const data = await api.exams.getExamResult(recordId)
    result.value = data

    console.log('=== ExamResult 加载数据 ===')
    console.log('data:', data)
    console.log('data.theory_exam:', data.theory_exam)
    console.log('data.theory_exam type:', typeof data.theory_exam)
    console.log('data.practice_exam:', data.practice_exam)
    console.log('data.exam_type:', data.exam_type)

    // 如果是理论考试，加载答案详情
    if (data.theory_exam) {
      const examId = typeof data.theory_exam === 'object' ? data.theory_exam.id : data.theory_exam
      console.log('加载理论题目, examId:', examId)
      const questions = await api.exams.getTheoryQuestions(examId)
      // 将答案与题目匹配
      if (data.answers && questions) {
        data.answers.forEach(answer => {
          const question = questions.find(q => q.id === answer.theory_question_id)
          if (question) {
            answer.question_text = question.question_text
            answer.correct_answer = question.correct_answer
          }
        })
      }
    } else if (data.practice_exam) {
      const examId = typeof data.practice_exam === 'object' ? data.practice_exam.id : data.practice_exam
      console.log('加载实战题目, examId:', examId)
      const questions = await api.exams.getPracticeQuestions(examId)
      if (data.answers && questions) {
        data.answers.forEach(answer => {
          const question = questions.find(q => q.id === answer.practice_question_id)
          if (question && question.challenge) {
            answer.question_text = question.challenge.title || question.challenge.description
          }
        })
      }
    }
  } catch (error) {
    console.error('加载考试结果失败:', error)
    alert('加载考试结果失败')
    router.push('/exam-center')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadResult()
})
</script>

<style scoped>
.exam-result-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 24px;
}

.page-header {
  text-align: center;
  margin-bottom: 40px;
}

.page-title {
  font-size: 32px;
  font-weight: bold;
  color: #1a1a1a;
  margin-bottom: 8px;
}

.page-subtitle {
  font-size: 16px;
  color: #666;
}

/* 加载中 */
.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 100px 0;
  color: #999;
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #f3f3f3;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-text {
  font-size: 16px;
}

/* 结果概览 */
.overview-card {
  background: white;
  border-radius: 16px;
  padding: 40px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  margin-bottom: 32px;
  display: flex;
  gap: 48px;
}

.overview-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.score-display {
  width: 160px;
  height: 160px;
  border-radius: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  transition: all 0.3s;
}

.score-display.passed {
  background: linear-gradient(135deg, #52c41a 0%, #73d13d 100%);
  color: white;
}

.score-display.failed {
  background: linear-gradient(135deg, #ff4d4f 0%, #ff7875 100%);
  color: white;
}

.score-number {
  font-size: 56px;
  font-weight: bold;
  line-height: 1;
}

.score-label {
  font-size: 16px;
  opacity: 0.9;
}

.result-badge {
  padding: 8px 24px;
  border-radius: 20px;
  font-size: 16px;
  font-weight: bold;
}

.result-badge.passed {
  background: #f6ffed;
  color: #52c41a;
}

.result-badge.failed {
  background: #fff2f0;
  color: #ff4d4f;
}

.overview-right {
  flex: 1;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.info-item {
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
}

.info-label {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

.info-value {
  font-size: 18px;
  font-weight: bold;
  color: #1a1a1a;
}

/* 答题详情 */
.answers-section {
  background: white;
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 24px;
}

.section-title {
  font-size: 20px;
  font-weight: bold;
  color: #1a1a1a;
  margin: 0;
}

.answers-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.answer-item {
  padding: 20px;
  border-radius: 12px;
  border: 2px solid #e9ecef;
  transition: all 0.3s;
}

.answer-item.correct {
  background: #f6ffed;
  border-color: #52c41a;
}

.answer-item.wrong {
  background: #fff2f0;
  border-color: #ff4d4f;
}

.answer-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}

.answer-number {
  font-size: 16px;
  font-weight: bold;
  color: #1a1a1a;
}

.answer-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
}

.answer-item.correct .answer-status {
  color: #52c41a;
}

.answer-item.wrong .answer-status {
  color: #ff4d4f;
}

.answer-points {
  margin-left: auto;
  font-size: 14px;
  font-weight: bold;
  color: #52c41a;
}

.answer-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.question-text {
  font-size: 16px;
  color: #333;
  line-height: 1.6;
  white-space: pre-wrap;
}

.answer-comparison {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.comparison-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
}

.comparison-label {
  min-width: 80px;
  font-weight: 500;
}

.user-label {
  color: #1890ff;
}

.correct-label {
  color: #52c41a;
}

.comparison-value {
  flex: 1;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
  word-break: break-all;
}

.user-value {
  border-left: 4px solid #1890ff;
}

.correct-value {
  border-left: 4px solid #52c41a;
  font-weight: 500;
}

/* 操作按钮 */
.action-buttons {
  display: flex;
  gap: 16px;
  justify-content: center;
}

.text-success {
  color: #52c41a;
}

.text-danger {
  color: #ff4d4f;
}
</style>
