<template>
  <div class="exam-taking-page">
    <!-- 顶部导航栏 -->
    <div class="exam-header">
      <div class="header-left">
        <h1 class="exam-title">{{ examInfo.title }}</h1>
        <div class="exam-meta">
          <span v-if="examType === 'theory'" class="exam-type-badge type-theory">理论测试</span>
          <span v-else class="exam-type-badge type-practice">实战测试</span>
          <span class="exam-progress">{{ currentQuestionIndex + 1 }} / {{ questions.length }}</span>
        </div>
      </div>
      <div class="header-right">
        <div class="timer" :class="{ 'warning': timeRemaining < 300, 'danger': timeRemaining < 60 }">
          <i class="bi bi-clock"></i>
          <span>{{ formatTime(timeRemaining) }}</span>
        </div>
        <button
          v-if="canSubmit"
          class="btn btn-success"
          @click="submitExam"
        >
          提交考试
        </button>
        <button
          class="btn btn-outline"
          @click="exitExam"
        >
          退出
        </button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="exam-content">
      <!-- 左侧题目区 -->
      <div class="question-section">
        <div v-if="currentQuestion" class="question-card">
          <!-- 题目类型标签 -->
          <div class="question-type-badge">
            {{ getQuestionTypeText(currentQuestion.question_detail?.question_type || 'single_choice') }}
          </div>

          <!-- 题目内容 -->
          <div class="question-content">
            <h2 class="question-text">
              <span class="question-number">第 {{ currentQuestionIndex + 1 }} 题</span>
              <span class="question-score" v-if="currentQuestion.points">({{ currentQuestion.points }}分)</span>
            </h2>
            <div class="question-detail" v-html="formatQuestion(currentQuestion)"></div>
          </div>

          <!-- 答案选项/输入区 -->
          <div class="answer-section">
            <!-- 理论题选项 -->
            <div v-if="examType === 'theory' && currentQuestion.question_detail" class="options-list">
              <div
                v-for="(option, index) in currentQuestion.question_detail.options"
                :key="index"
                class="option-item"
                :class="{ 'selected': isOptionSelected(option) }"
                @click="selectOption(option)"
              >
                <div class="option-marker">{{ getOptionLabel(index) }}</div>
                <div class="option-text">{{ option }}</div>
                <div class="option-check">
                  <i v-if="isOptionSelected(option)" class="bi bi-check-circle-fill"></i>
                </div>
              </div>
            </div>

            <!-- 实战题输入 -->
            <div v-else-if="examType === 'practice' && currentQuestion.challenge" class="practice-answer">
              <div class="practice-info">
                <div class="info-item">
                  <span class="info-label">难度:</span>
                  <span class="info-value" :class="'difficulty-' + (currentQuestion.challenge_difficulty?.toLowerCase() || 'unknown')">
                    {{ currentQuestion.challenge_difficulty || '未知' }}
                  </span>
                </div>
                <div class="info-item">
                  <span class="info-label">分值:</span>
                  <span class="info-value">{{ currentQuestion.challenge_points || 0 }} 分</span>
                </div>
              </div>
              <div class="flag-input">
                <label class="input-label">请提交 Flag:</label>
                <input
                  v-model="currentAnswer"
                  type="text"
                  class="input input-large"
                  placeholder="请输入 flag，例如: flag{...}"
                  @keyup.enter="submitAnswer"
                />
                <button
                  class="btn btn-primary btn-submit"
                  @click="submitAnswer"
                  :disabled="!currentAnswer.trim()"
                >
                  提交答案
                </button>
              </div>
              <div v-if="submissionResult" class="submission-result" :class="{ 'success': submissionResult.is_correct, 'error': !submissionResult.is_correct }">
                <i :class="submissionResult.is_correct ? 'bi bi-check-circle-fill' : 'bi bi-x-circle-fill'"></i>
                <span>{{ submissionResult.is_correct ? '答案正确！' : '答案错误，请重试' }}</span>
              </div>
            </div>
          </div>

          <!-- 导航按钮 -->
          <div class="navigation-buttons">
            <button
              class="btn btn-outline"
              @click="prevQuestion"
              :disabled="currentQuestionIndex === 0"
            >
              <i class="bi bi-chevron-left"></i>
              上一题
            </button>
            <button
              class="btn btn-primary"
              @click="nextQuestion"
              :disabled="currentQuestionIndex === questions.length - 1"
            >
              下一题
              <i class="bi bi-chevron-right"></i>
            </button>
          </div>
        </div>
      </div>

      <!-- 右侧题目导航 -->
      <div class="question-nav-section">
        <div class="nav-card">
          <div class="nav-header">
            <h3>题目导航</h3>
            <div class="nav-legend">
              <span class="legend-item current">当前</span>
              <span class="legend-item answered">已答</span>
              <span class="legend-item unanswered">未答</span>
            </div>
          </div>
          <div class="nav-grid">
            <div
              v-for="(question, index) in questions"
              :key="index"
              class="nav-item"
              :class="{
                'current': index === currentQuestionIndex,
                'answered': isAnswered(index),
                'unanswered': !isAnswered(index) && index !== currentQuestionIndex
              }"
              @click="goToQuestion(index)"
            >
              <span class="nav-number">{{ index + 1 }}</span>
              <span v-if="isAnswered(index)" class="nav-icon">✓</span>
            </div>
          </div>

          <!-- 进度统计 -->
          <div class="progress-stats">
            <div class="stat-row">
              <span class="stat-label">已答题:</span>
              <span class="stat-value">{{ answeredCount }}/{{ questions.length }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label">正确率:</span>
              <span class="stat-value">{{ accuracyRate }}%</span>
            </div>
          </div>

          <!-- 快速跳转 -->
          <div class="quick-nav">
            <button
              class="btn btn-small btn-outline"
              @click="goToFirstUnanswered"
              :disabled="!hasUnanswered"
            >
              跳转未答
            </button>
            <button
              class="btn btn-small btn-primary"
              @click="submitExam"
              :disabled="!canSubmit"
            >
              提交考试
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 提交确认对话框 -->
    <div v-if="showSubmitDialog" class="modal-overlay" @click="closeSubmitDialog">
      <div class="modal-content" @click.stop>
        <h3 class="modal-title">提交考试</h3>
        <div class="modal-body">
          <div class="submit-info">
            <div class="info-row">
              <span class="info-label">已答题目:</span>
              <span class="info-value">{{ answeredCount }} / {{ questions.length }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">预计用时:</span>
              <span class="info-value">{{ formatTime(elapsedTime) }}</span>
            </div>
          </div>
          <div v-if="answeredCount < questions.length" class="warning-text">
            ⚠️ 还有 {{ questions.length - answeredCount }} 道题未答，确认提交吗？
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="closeSubmitDialog">取消</button>
          <button class="btn btn-primary" @click="confirmSubmit">确认提交</button>
        </div>
      </div>
    </div>

    <!-- 退出确认对话框 -->
    <div v-if="showExitDialog" class="modal-overlay" @click="closeExitDialog">
      <div class="modal-content" @click.stop>
        <h3 class="modal-title">退出考试</h3>
        <div class="modal-body">
          <p>选择退出方式：</p>
          <div class="exit-options">
            <div class="exit-option" @click="exitWithoutAbandon">
              <div class="option-title">📝 退出并保留</div>
              <div class="option-desc">退出考试，稍后可以继续答题</div>
            </div>
            <div class="exit-option danger" @click="abandonAndExit">
              <div class="option-title">⚠️ 放弃考试</div>
              <div class="option-desc">放弃当前考试，无法恢复</div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="closeExitDialog">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '@/api'

const router = useRouter()
const route = useRoute()

const recordId = route.params.id
const examType = ref('theory')
const examInfo = ref({})
const questions = ref([])
const currentQuestionIndex = ref(0)
const answers = ref({})
const currentAnswer = ref('')
const timeRemaining = ref(0)
const elapsedTime = ref(0)
const showSubmitDialog = ref(false)
const showExitDialog = ref(false)
const submissionResult = ref(null)
const timer = ref(null)

const currentQuestion = computed(() => questions.value[currentQuestionIndex.value])
const answeredCount = computed(() => Object.keys(answers.value).length)
const accuracyRate = computed(() => {
  const correct = Object.values(answers.value).filter(a => a.is_correct).length
  return answeredCount.value > 0 ? Math.round((correct / answeredCount.value) * 100) : 0
})
const canSubmit = computed(() => answeredCount.value > 0)
const hasUnanswered = computed(() => answeredCount.value < questions.value.length)

// 获取选项标签
const getOptionLabel = (index) => {
  return String.fromCharCode(65 + index)
}

// 获取题目类型文本
const getQuestionTypeText = (type) => {
  const map = {
    'single_choice': '单选题',
    'multiple_choice': '多选题',
    'true_false': '判断题',
  }
  return map[type] || '题目'
}

// 格式化题目内容
const formatQuestion = (question) => {
  // 理论题
  if (question.question_detail) {
    return question.question_detail.question_text
  }
  // 实战题
  if (question.challenge) {
    return question.challenge.description || question.challenge_title
  }
  return ''
}

// 是否选中选项
const isOptionSelected = (option) => {
  if (!currentQuestion.value || !answers.value[currentQuestion.value.id]) {
    return false
  }
  const userAnswer = answers.value[currentQuestion.value.id].user_answer
  const questionType = currentQuestion.value.question_detail?.question_type || currentQuestion.value.challenge ? 'practice' : 'single_choice'

  if (questionType === 'multiple_choice') {
    return userAnswer.includes(option)
  }
  return userAnswer === option
}

// 选择选项
const selectOption = (option) => {
  if (!currentQuestion.value) return

  const questionId = currentQuestion.value.id
  const questionType = currentQuestion.value.question_detail?.question_type

  if (questionType === 'multiple_choice') {
    // 多选：添加或移除选项
    const currentAnswers = answers.value[questionId]?.user_answer || ''
    const answerArray = currentAnswers ? currentAnswers.split(',') : []

    if (answerArray.includes(option)) {
      // 移除选项
      const index = answerArray.indexOf(option)
      answerArray.splice(index, 1)
    } else {
      // 添加选项
      answerArray.push(option)
    }

    answers.value[questionId] = {
      user_answer: answerArray.join(','),
      is_correct: false,
      points_earned: 0,
    }
  } else {
    // 单选/判断：直接设置
    answers.value[questionId] = {
      user_answer: option,
      is_correct: false,
      points_earned: 0,
    }
  }
}

// 判断是否已答
const isAnswered = (index) => {
  const question = questions.value[index]
  if (!question) return false
  return !!answers.value[question.id]
}

// 上一题
const prevQuestion = () => {
  if (currentQuestionIndex.value > 0) {
    currentQuestionIndex.value--
    currentAnswer.value = ''
    submissionResult.value = null
  }
}

// 下一题
const nextQuestion = () => {
  if (currentQuestionIndex.value < questions.value.length - 1) {
    currentQuestionIndex.value++
    currentAnswer.value = ''
    submissionResult.value = null
  }
}

// 跳转到指定题目
const goToQuestion = (index) => {
  currentQuestionIndex.value = index
  currentAnswer.value = ''
  submissionResult.value = null
}

// 跳转到第一题未答题
const goToFirstUnanswered = () => {
  for (let i = 0; i < questions.value.length; i++) {
    if (!isAnswered(i)) {
      goToQuestion(i)
      return
    }
  }
}

// 提交答案（实战题）
const submitAnswer = async () => {
  if (!currentQuestion.value || !currentAnswer.value.trim()) return

  try {
    const result = await api.exams.submitAnswer(recordId, {
      practice_question_id: currentQuestion.value.id,
      user_answer: currentAnswer.value.trim(),
      time_spent: Math.floor(elapsedTime.value),
    })

    submissionResult.value = result
    answers.value[currentQuestion.value.id] = {
      user_answer: currentAnswer.value.trim(),
      is_correct: result.is_correct,
      points_earned: result.points_earned,
    }

    if (result.is_correct) {
      // 答对了，延迟后跳转下一题
      setTimeout(() => {
        if (currentQuestionIndex.value < questions.value.length - 1) {
          nextQuestion()
        } else {
          // 最后一题答对，提交考试
          showSubmitDialog.value = true
        }
      }, 1500)
    }
  } catch (error) {
    console.error('提交答案失败:', error)
    alert('提交失败，请重试')
  }
}

// 提交考试
const submitExam = () => {
  if (examType.value === 'theory') {
    // 理论题：先提交所有答案，再提交考试
    submitAllTheoryAnswers()
  } else {
    // 实战题：直接显示确认对话框
    showSubmitDialog.value = true
  }
}

// 提交所有理论题答案
const submitAllTheoryAnswers = async () => {
  try {
    for (const question of questions.value) {
      if (question.question && answers.value[question.id]) {
        await api.exams.submitAnswer(recordId, {
          theory_question_id: question.question,  // 使用实际的题目 ID
          user_answer: answers.value[question.id].user_answer,
          time_spent: Math.floor(elapsedTime.value),
        })
      }
    }
    showSubmitDialog.value = true
  } catch (error) {
    console.error('提交答案失败:', error)
    alert('提交失败，请重试')
  }
}

// 确认提交
const confirmSubmit = async () => {
  try {
    await api.exams.submitExam(recordId)

    // 检查是否是理论考试，如果是则进入实战考试
    if (examType.value === 'theory') {
      const record = await api.exams.getExamResult(recordId)
      if (record.practice_record_id) {
        // 进入实战考试
        router.push(`/exam-taking/${record.practice_record_id}`)
        return
      }
    }

    // 跳转到结果页
    router.push(`/exam-result/${recordId}`)
  } catch (error) {
    console.error('提交考试失败:', error)
    alert('提交失败，请重试')
  }
}

// 关闭提交对话框
const closeSubmitDialog = () => {
  showSubmitDialog.value = false
}

// 退出考试
const exitExam = () => {
  showExitDialog.value = true
}

// 退出但不放弃考试
const exitWithoutAbandon = () => {
  closeExitDialog()
  router.push('/exam-center')
}

// 放弃考试并退出
const abandonAndExit = async () => {
  try {
    await api.exams.startComprehensiveExam({ abandon: true })
    closeExitDialog()
    router.push('/exam-center')
  } catch (error) {
    console.error('放弃考试失败:', error)
    alert('放弃考试失败')
  }
}

// 关闭退出对话框
const closeExitDialog = () => {
  showExitDialog.value = false
}

// 格式化时间
const formatTime = (seconds) => {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }
  return `${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

// 加载考试信息
const loadExamInfo = async () => {
  console.log('开始加载考试信息, recordId:', recordId)
  console.log('当前 token:', localStorage.getItem('token'))

  try {
    // 添加原始响应日志
    const response = await fetch(`/api/exams/records/${recordId}/result/`, {
      headers: {
        'Authorization': `Token ${localStorage.getItem('token')}`
      }
    })
    const rawRecord = await response.json()
    console.log('=== 原始 API 响应 ===')
    console.log('原始响应数据:', rawRecord)
    console.log('原始响应 theory_exam:', rawRecord.theory_exam)
    console.log('原始响应 practice_exam:', rawRecord.practice_exam)

    const record = await api.exams.getExamResult(recordId)
    console.log('=== axios 拦截器返回的数据 ===')
    console.log('axios 返回的 record:', record)
    console.log('record 类型:', typeof record)
    console.log('record 键值:', Object.keys(record))
    console.log('record.theory_exam:', record.theory_exam)
    console.log('record.theory_exam 类型:', typeof record.theory_exam)
    console.log('record.practice_exam:', record.practice_exam)
    console.log('record.practice_exam 类型:', typeof record.practice_exam)
    console.log('record.exam_title:', record.exam_title)
    console.log('record.exam_type:', record.exam_type)

    if (record.theory_exam) {
      console.log('✅ 检测到 theory_exam，准备加载理论题目')
      examType.value = 'theory'
      examInfo.value = {
        id: record.theory_exam,
        title: record.exam_title,
        duration: 180
      }
      console.log('加载理论题目, examId:', record.theory_exam, '类型:', typeof record.theory_exam)
      questions.value = await api.exams.getTheoryQuestions(record.theory_exam)
      console.log('理论题目加载成功, 数量:', questions.value.length)
    } else if (record.practice_exam) {
      console.log('✅ 检测到 practice_exam，准备加载实战题目')
      examType.value = 'practice'
      examInfo.value = {
        id: record.practice_exam,
        title: record.exam_title,
        duration: 180
      }
      console.log('加载实战题目, examId:', record.practice_exam, '类型:', typeof record.practice_exam)
      questions.value = await api.exams.getPracticeQuestions(record.practice_exam)
      console.log('实战题目加载成功, 数量:', questions.value.length)
    } else {
      console.error('❌ 考试记录中没有 theory_exam 或 practice_exam')
      console.error('record.theory_exam:', record.theory_exam)
      console.error('record.practice_exam:', record.practice_exam)
      throw new Error('考试记录无效')
    }

    timeRemaining.value = record.theory_exam ? 180 * 60 : (record.practice_exam ? 180 * 60 : 3600)

    // 加载已提交的答案
    const answersRes = await api.exams.records({ id: recordId })
    console.log('获取答案记录成功:', answersRes)
    if (answersRes.results && answersRes.results[0] && answersRes.results[0].answers) {
      for (const answer of answersRes.results[0].answers) {
        let questionId = null
        if (answer.theory_question_id) {
          const examQuestion = questions.value.find(q => q.question === answer.theory_question_id)
          if (examQuestion) {
            questionId = examQuestion.id
          }
        } else if (answer.practice_question_id) {
          questionId = answer.practice_question_id
        }

        if (questionId) {
          answers.value[questionId] = {
            user_answer: answer.user_answer,
            is_correct: answer.is_correct,
            points_earned: answer.points_earned,
          }
        }
      }
    }

    console.log('考试信息加载完成, 题目数量:', questions.value.length)
  } catch (error) {
    console.error('=== 加载考试信息失败 ===')
    console.error('recordId:', recordId)
    console.error('Error:', error)
    console.error('Error response:', error.response)
    console.error('Error status:', error.response?.status)
    console.error('Error data:', error.response?.data)
    console.error('Error message:', error.message)
    console.error('Error stack:', error.stack)

    // 显示具体错误信息
    const errorMsg = error.response?.data?.error || error.message || '未知错误'
    alert(`加载考试信息失败！\n\n错误：${errorMsg}\n\n请重试或联系管理员`)
    router.push('/exam-center')
  }
}

// 更新计时器
const updateTimer = () => {
  if (timeRemaining.value > 0) {
    timeRemaining.value--
    elapsedTime.value++
  } else {
    // 时间到，自动提交
    clearInterval(timer.value)
    confirmSubmit()
  }
}

onMounted(async () => {
  await loadExamInfo()
  timer.value = setInterval(updateTimer, 1000)
})

onUnmounted(() => {
  if (timer.value) {
    clearInterval(timer.value)
  }
})
</script>

<style scoped>
.exam-taking-page {
  min-height: 100vh;
  background: #f5f5f5;
}

/* 顶部导航 */
.exam-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 72px;
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  z-index: 1000;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.exam-title {
  font-size: 20px;
  font-weight: bold;
  color: #1a1a1a;
  margin: 0;
}

.exam-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.exam-type-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.type-theory {
  background: #e6f7ff;
  color: #1890ff;
}

.type-practice {
  background: #fff7e6;
  color: #faad14;
}

.exam-progress {
  font-size: 14px;
  color: #666;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.timer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #f8f9fa;
  border-radius: 8px;
  font-size: 18px;
  font-weight: bold;
  color: #52c41a;
}

.timer.warning {
  color: #faad14;
  animation: pulse 1s infinite;
}

.timer.danger {
  color: #ff4d4f;
  animation: pulse 0.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 主内容区 */
.exam-content {
  display: flex;
  gap: 24px;
  padding: 96px 32px 32px;
  max-width: 1400px;
  margin: 0 auto;
}

.question-section {
  flex: 1;
  min-width: 0;
}

.question-nav-section {
  width: 320px;
  flex-shrink: 0;
}

/* 题目卡片 */
.question-card {
  background: white;
  border-radius: 16px;
  padding: 32px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.question-type-badge {
  display: inline-block;
  padding: 4px 12px;
  background: #1890ff;
  color: white;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  margin-bottom: 24px;
}

.question-content {
  margin-bottom: 32px;
}

.question-text {
  font-size: 18px;
  font-weight: bold;
  color: #1a1a1a;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.question-number {
  color: #1890ff;
}

.question-score {
  color: #999;
  font-size: 14px;
  font-weight: normal;
}

.question-detail {
  font-size: 16px;
  color: #333;
  line-height: 1.8;
  white-space: pre-wrap;
}

/* 选项列表 */
.options-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: #f8f9fa;
  border: 2px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s;
}

.option-item:hover {
  background: #e9ecef;
}

.option-item.selected {
  background: #e6f7ff;
  border-color: #1890ff;
}

.option-marker {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #1890ff;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 14px;
}

.option-text {
  flex: 1;
  font-size: 16px;
  color: #1a1a1a;
}

.option-check {
  font-size: 20px;
  color: #1890ff;
}

/* 实战题答题区 */
.practice-answer {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.practice-info {
  display: flex;
  gap: 24px;
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
}

.info-item {
  display: flex;
  gap: 8px;
  font-size: 14px;
}

.info-label {
  color: #666;
}

.info-value {
  font-weight: 500;
}

.difficulty-easy { color: #52c41a; }
.difficulty-medium { color: #faad14; }
.difficulty-hard { color: #ff4d4f; }

.flag-input {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.input-label {
  font-size: 14px;
  font-weight: 500;
  color: #1a1a1a;
}

.input-large {
  font-size: 16px;
  padding: 14px 20px;
}

.btn-submit {
  align-self: flex-start;
}

.submission-result {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 500;
  animation: fadeIn 0.3s;
}

.submission-result.success {
  background: #f6ffed;
  color: #52c41a;
}

.submission-result.error {
  background: #fff2f0;
  color: #ff4d4f;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 导航按钮 */
.navigation-buttons {
  display: flex;
  justify-content: space-between;
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid #e9ecef;
}

/* 题目导航卡片 */
.nav-card {
  position: sticky;
  top: 96px;
  background: white;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.nav-header {
  margin-bottom: 20px;
}

.nav-header h3 {
  font-size: 18px;
  font-weight: bold;
  color: #1a1a1a;
  margin: 0 0 12px 0;
}

.nav-legend {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #666;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-item::before {
  content: '';
  width: 12px;
  height: 12px;
  border-radius: 4px;
}

.legend-item.current::before {
  background: #1890ff;
}

.legend-item.answered::before {
  background: #52c41a;
}

.legend-item.unanswered::before {
  background: #d9d9d9;
}

.nav-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 8px;
  margin-bottom: 24px;
}

.nav-item {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8f9fa;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
  font-size: 14px;
  color: #666;
  transition: all 0.3s;
  position: relative;
}

.nav-item:hover {
  transform: scale(1.05);
}

.nav-item.current {
  background: #1890ff;
  color: white;
}

.nav-item.answered {
  background: #52c41a;
  color: white;
}

.nav-item.unanswered {
  background: #f8f9fa;
  color: #666;
}

.nav-icon {
  position: absolute;
  bottom: 2px;
  right: 2px;
  font-size: 10px;
}

.progress-stats {
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
  margin-bottom: 20px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
}

.stat-row:last-child {
  margin-bottom: 0;
}

.stat-label {
  color: #666;
}

.stat-value {
  font-weight: bold;
  color: #1a1a1a;
}

.quick-nav {
  display: flex;
  gap: 12px;
}

.btn-small {
  flex: 1;
  padding: 10px 16px;
  font-size: 14px;
}

/* 模态框 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-content {
  background: white;
  border-radius: 16px;
  padding: 32px;
  width: 90%;
  max-width: 480px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
}

.modal-title {
  font-size: 20px;
  font-weight: bold;
  color: #1a1a1a;
  margin: 0 0 24px 0;
}

.modal-body {
  margin-bottom: 24px;
}

.exit-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.exit-option {
  padding: 16px;
  background: #f8f9fa;
  border: 2px solid #e9ecef;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.exit-option:hover {
  background: #e9ecef;
  border-color: #1890ff;
}

.exit-option.danger {
  background: #fff2f0;
  border-color: #ffccc7;
}

.exit-option.danger:hover {
  background: #ffccc7;
  border-color: #ff4d4f;
}

.option-title {
  font-weight: bold;
  color: #1a1a1a;
  margin-bottom: 4px;
}

.option-desc {
  font-size: 14px;
  color: #666;
}

.submit-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  font-size: 14px;
}

.warning-text {
  padding: 12px;
  background: #fff7e6;
  color: #d46b08;
  border-radius: 8px;
  font-size: 14px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
