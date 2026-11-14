<template>
  <main class="exam-taking-page">
    <header class="exam-header">
      <div class="header-left"><p class="page-context">{{ names.exams }} · 正式测评</p><h1 class="exam-title">{{ examInfo.title || '正式测评' }}</h1><div class="exam-meta"><span>{{ examType === 'theory' ? '理论测试' : '实战测试' }}</span><span>{{ questions.length ? currentQuestionIndex + 1 : 0 }} / {{ questions.length }}</span></div></div>
      <div class="header-right">
        <div class="timer" :class="{ warning: timeRemaining < 300, danger: timeRemaining < 60 }" role="timer" aria-live="off"><span class="timer-label">剩余时间</span><strong class="timer-value">{{ formatTime(timeRemaining) }}</strong><span class="timer-warning">{{ timeRemaining < 60 ? '不足 1 分钟' : timeRemaining < 300 ? '不足 5 分钟' : '' }}</span></div>
        <button class="btn" :class="examType === 'theory' ? 'btn-primary' : 'btn-outline'" :disabled="!canSubmit || preparingSubmit || submittingExam" @click="submitExam">提交考试</button>
        <button class="btn btn-outline" @click="exitExam">退出</button>
      </div>
    </header>
    <p v-if="loading" class="page-state" role="status" aria-busy="true">正在读取考试信息…</p>
    <p v-else-if="loadError" class="page-state load-error" role="alert">{{ loadError }} <button class="btn btn-outline" @click="restartExam">重新读取</button><router-link to="/exam-center">返回试炼场</router-link></p>
    <p v-else-if="!questions.length" class="page-state">本场考试暂无题目</p>
    <div v-else class="exam-content">
      <section class="question-section">
        <article v-if="currentQuestion" class="question-card">
          <div class="question-heading"><span class="question-type-badge">{{ getQuestionTypeText(currentQuestion.question_detail?.question_type) }}</span><h2 class="question-title">第 {{ currentQuestionIndex + 1 }} 题</h2><span v-if="currentQuestion.points" class="question-score">{{ currentQuestion.points }}分</span></div>
          <div class="question-detail" v-html="formatQuestion(currentQuestion)"></div>
          <div v-if="examType === 'theory' && currentQuestion.question_detail" class="options-list">
            <button v-for="(option, index) in currentQuestion.question_detail.options" :key="index" type="button" class="option-item" :class="{ selected: isOptionSelected(option) }" :aria-pressed="isOptionSelected(option)" @click="selectOption(option)"><span class="option-marker">{{ getOptionLabel(index) }}</span><span class="option-text">{{ option }}</span><icon-check-circle v-if="isOptionSelected(option)" class="option-check" /></button>
          </div>
          <div v-else-if="examType === 'practice' && currentQuestion.challenge" class="practice-answer">
            <div class="practice-info"><span>难度：{{ difficultyText(currentQuestion.challenge_difficulty) }}</span><span>分值：{{ currentQuestion.challenge_points ?? '—' }}</span></div>
            <label class="input-label" for="exam-flag">请提交 Flag</label>
            <div class="flag-input"><input id="exam-flag" v-model="currentAnswer" type="text" class="input" placeholder="请输入 flag" @keyup.enter="submitAnswer" /><button class="btn btn-primary" @click="submitAnswer" :disabled="!currentAnswer.trim() || submittingAnswer" :aria-busy="submittingAnswer">{{ submittingAnswer ? '正在提交答案' : '提交答案' }}</button></div>
            <div v-if="submissionResult" class="submission-result" :class="submissionResult.is_correct ? 'success' : 'error'" role="status">{{ submissionResult.is_correct ? '答案正确！' : '答案错误，请重试' }}</div>
          </div>
          <div class="navigation-buttons"><button class="btn btn-outline" @click="prevQuestion" :disabled="currentQuestionIndex === 0">上一题</button><button class="btn btn-outline" @click="nextQuestion" :disabled="currentQuestionIndex === questions.length - 1">下一题</button></div>
        </article>
      </section>
      <aside class="question-nav-section"><div class="nav-card"><h2 class="nav-title">题目导航</h2><p class="nav-legend">当前 / 已答 / 未答</p>
        <div class="nav-grid"><button v-for="(question, index) in questions" :key="question.id" type="button" class="nav-item" :class="{ current: index === currentQuestionIndex, answered: isAnswered(index) }" :aria-label="`第 ${index + 1} 题，${isAnswered(index) ? '已答' : '未答'}${index === currentQuestionIndex ? '，当前题' : ''}`" :aria-current="index === currentQuestionIndex ? 'step' : undefined" @click="goToQuestion(index)">{{ index + 1 }}<icon-check v-if="isAnswered(index)" /></button></div>
        <p>已答题：{{ answeredCount }} / {{ questions.length }}</p><p v-if="examType === 'practice'">已记录正确率：{{ accuracyRate }}%</p>
        <div class="quick-nav"><button class="btn btn-outline" @click="goToFirstUnanswered" :disabled="!hasUnanswered">跳转未答</button></div>
      </div></aside>
    </div>
    <p v-if="examType === 'theory' && !loading && !loadError" class="exam-notice" role="status">{{ savingTheoryAnswers ? '答案保存中…' : answerSaveError ? '答案尚未保存，请重试。' : '答案已保存' }} <button v-if="answerSaveError && timeRemaining > 0" class="btn btn-outline" @click="saveTheoryAnswers">重试保存</button></p>
    <p v-if="timeoutNotice" class="exam-notice is-error" role="alert">{{ timeoutNotice }}</p><p v-if="submitError" class="exam-notice is-error" role="alert">{{ submitError }}</p>
    <ExamTakingDialog :open="showSubmitDialog" title="提交考试" title-id="exam-submit-heading" @close="closeSubmitDialog">
      <p>已答题目：{{ answeredCount }} / {{ questions.length }}</p><p>已用时间：{{ formatTime(elapsedTime) }}</p><p v-if="answeredCount < questions.length">还有 {{ questions.length - answeredCount }} 道题未答，确认提交吗？</p>
      <template #footer><button class="btn btn-outline" autofocus @click="closeSubmitDialog">取消</button><button class="btn btn-primary" @click="confirmSubmit" :disabled="submittingExam">{{ submittingExam ? '正在交卷…' : '确认提交' }}</button></template>
    </ExamTakingDialog>
    <ExamTakingDialog :open="showExitDialog" title="退出考试" title-id="exam-exit-heading" @close="closeExitDialog">
      <p>退出前会保存当前答案；网络异常时请先重试保存。</p><div class="exit-options"><button class="btn btn-outline" @click="exitWithoutAbandon">退出并保留</button><button class="btn btn-outline" :disabled="abandoning" @click="abandonAndExit">放弃考试并退出</button></div>
      <template #footer><button class="btn btn-outline" autofocus @click="closeExitDialog">取消</button></template>
    </ExamTakingDialog>
  </main>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '@/api'
import { sanitizeHtml } from '@/utils/sanitize'
import ExamTakingDialog from './ExamTakingDialog.vue'
import { names } from '@/shared/navigation/names'
import { savedAnswerRef, theoryExamId } from '@/learning/exams/api.js'

const router = useRouter()
const route = useRoute()

const recordId = computed(() => route.params.id)
const loading = ref(true)
const loadError = ref('')
const submittingAnswer = ref(false), preparingSubmit = ref(false), submittingExam = ref(false), abandoning = ref(false)
const timeoutNotice = ref(''), submitError = ref('')
let pageAlive = true
let examReadGeneration = 0
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
const savingTheoryAnswers = ref(false), answerSaveError = ref('')
const examDeadline = ref(0)
let theoryDirty = new Set(), savedTheoryAnswers = new Map(), theorySavePromise = null

const currentQuestion = computed(() => questions.value[currentQuestionIndex.value])
const answeredCount = computed(() => Object.keys(answers.value).length)
const accuracyRate = computed(() => {
  const correct = Object.values(answers.value).filter(a => a.is_correct).length
  return answeredCount.value > 0 ? Math.round((correct / answeredCount.value) * 100) : 0
})
const canSubmit = computed(() => !loading.value && !loadError.value && questions.value.length > 0)
const hasUnanswered = computed(() => answeredCount.value < questions.value.length)

// 获取选项标签
const difficultyText = value => ({ easy: '简单', medium: '中等', hard: '困难', expert: '专家' }[value?.toLowerCase()] || '难度待确认')
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
    return sanitizeHtml(question.question_detail.question_text)
  }
  // 实战题
  if (question.challenge) {
    return sanitizeHtml(question.challenge_description || question.challenge?.description || question.challenge_title || '')
  }
  return ''
}

// 是否选中选项
const isOptionSelected = (option) => {
  if (!currentQuestion.value || !answers.value[currentQuestion.value.id]) {
    return false
  }
  const userAnswer = answers.value[currentQuestion.value.id].user_answer
  const questionType = currentQuestion.value.question_detail?.question_type || (currentQuestion.value.challenge ? 'practice' : 'single_choice')

  if (questionType === 'multiple_choice') {
    return userAnswer.split(',').includes(option)
  }
  return userAnswer === option
}

// 选择选项
const selectOption = (option) => {
  if (!currentQuestion.value || timeRemaining.value <= 0 || submittingExam.value) return

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

    if (answerArray.length === 0) {
      delete answers.value[questionId]
    } else {
      answers.value[questionId] = {
        user_answer: answerArray.join(','),
      }
    }
  } else {
    // 单选/判断：直接设置
    answers.value[questionId] = {
      user_answer: option,
    }
  }
  theoryDirty.add(questionId)
  void saveTheoryAnswers()
}

// One writer per record prevents an older response from restoring a cleared
// choice. Changes made while a request is in flight stay in the queue.
const saveTheoryAnswers = () => {
  if (theorySavePromise) return theorySavePromise
  const id = recordId.value, reading = examReadGeneration
  const dirty = theoryDirty, saved = savedTheoryAnswers
  const belongsToPage = () => pageAlive && id === recordId.value && reading === examReadGeneration
  savingTheoryAnswers.value = true
  answerSaveError.value = ''
  const task = Promise.resolve().then(async () => {
    try {
      for (const question of questions.value) {
        const value = answers.value[question.id]?.user_answer || ''
        if (value !== (saved.get(question.id) || '')) dirty.add(question.id)
      }
      while (dirty.size) {
        if (!belongsToPage()) return false
        const questionId = dirty.values().next().value
        const question = questions.value.find(item => item.id === questionId)
        if (!question?.question) { dirty.delete(questionId); continue }
        const value = answers.value[questionId]?.user_answer || ''
        await api.exams.submitAnswer(id, {
          theory_question_id: question.question,
          user_answer: value,
          time_spent: Math.floor(elapsedTime.value),
        })
        if (!belongsToPage()) return false
        saved.set(questionId, value)
        if ((answers.value[questionId]?.user_answer || '') === value) dirty.delete(questionId)
      }
      return true
    } catch (error) {
      if (belongsToPage()) answerSaveError.value = '答案保存失败，请检查网络后重试。'
      return false
    } finally {
      if (belongsToPage()) savingTheoryAnswers.value = false
    }
  })
  theorySavePromise = task
  void task.finally(() => { if (theorySavePromise === task) theorySavePromise = null })
  return task
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
  if (!currentQuestion.value || !currentAnswer.value.trim() || submittingAnswer.value) return
  const questionId = currentQuestion.value.id, answer = currentAnswer.value.trim()
  const id = recordId.value, reading = examReadGeneration
  submittingAnswer.value = true
  try {
    const result = await api.exams.submitAnswer(id, {
      practice_question_id: questionId,
      user_answer: answer,
      time_spent: Math.floor(elapsedTime.value),
    })

    if (!pageAlive || id !== recordId.value || reading !== examReadGeneration) return
    if (currentQuestion.value?.id === questionId) submissionResult.value = result
    answers.value[questionId] = {
      user_answer: answer,
      is_correct: result.is_correct,
      points_earned: result.points_earned,
    }

    if (result.is_correct) {
      // 答对了，延迟后跳转下一题
      setTimeout(() => {
        if (!pageAlive || id !== recordId.value || reading !== examReadGeneration || currentQuestion.value?.id !== questionId) return
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
  } finally {
    submittingAnswer.value = false
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
  if (preparingSubmit.value) return false
  const id = recordId.value, reading = examReadGeneration
  preparingSubmit.value = true
  try {
    if (!(await saveTheoryAnswers())) return false
    if (!pageAlive || id !== recordId.value || reading !== examReadGeneration) return false
    showSubmitDialog.value = true
    return true
  } catch (error) {
    console.error('提交答案失败:', error)
    alert('提交失败，请重试')
    return false
  } finally {
    preparingSubmit.value = false
  }
}

// 确认提交
const confirmSubmit = async (automatic = false) => {
  if (submittingExam.value) return
  const id = recordId.value, reading = examReadGeneration
  submittingExam.value = true
  try {
    if (automatic !== true && examType.value === 'theory' && !(await saveTheoryAnswers())) return
    await api.exams.submitExam(id)
    if (!pageAlive || id !== recordId.value || reading !== examReadGeneration) return
    if (automatic === true && examType.value === 'theory' && theoryDirty.size) {
      router.push(`/exam-center/result/${id}?unsaved=1`)
      return
    }

    // 检查是否是理论考试，如果是则进入实战考试
    if (examType.value === 'theory') {
      const record = await api.exams.getExamResult(id)
      if (!pageAlive || id !== recordId.value || reading !== examReadGeneration) return
      if (record.practice_record_id) {
        // 进入实战考试
        router.push(`/exam-taking/${record.practice_record_id}`)
        return
      }
    }

    // 跳转到结果页
    router.push(`/exam-center/result/${id}`)
  } catch (error) {
    console.error('提交考试失败:', error)
    alert('提交失败，请重试')
  } finally {
    submittingExam.value = false
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
const exitWithoutAbandon = async () => {
  if (examType.value === 'theory' && !(await saveTheoryAnswers())) return
  closeExitDialog()
  router.push('/exam-center')
}

// 放弃考试并退出
const abandonAndExit = async () => {
  if (abandoning.value) return
  abandoning.value = true
  submitError.value = ''
  try {
    await api.exams.startComprehensiveExam({ abandon: true })
    const confirmed = await api.exams.getExamResult(recordId.value)
    if (confirmed.status !== 'abandoned') { submitError.value = '放弃可能未生效，请重新读取考试记录核对。'; return }
    closeExitDialog()
    router.push('/exam-center')
  } catch (error) {
    console.error('放弃考试失败:', error)
    alert('放弃考试失败')
  } finally {
    abandoning.value = false
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
  const reading = ++examReadGeneration, id = recordId.value
  loading.value = true
  loadError.value = ''
  examInfo.value = {}
  questions.value = []
  answers.value = {}
  theoryDirty = new Set()
  savedTheoryAnswers = new Map()
  theorySavePromise = null
  savingTheoryAnswers.value = false
  answerSaveError.value = ''
  examDeadline.value = 0
  currentQuestionIndex.value = 0
  currentAnswer.value = ''
  submissionResult.value = null
  showSubmitDialog.value = false
  showExitDialog.value = false
  timeoutNotice.value = ''
  submitError.value = ''
  try {
    const record = await api.exams.getExamResult(id)
    if (!pageAlive || reading !== examReadGeneration || id !== recordId.value) return false
    if (record.status && record.status !== 'in_progress') {
      router.push(`/exam-center/result/${id}`)
      return false
    }
    let details, loadedQuestions
    const theoryId = theoryExamId(record)
    const practiceId = typeof record.practice_exam === 'object' ? record.practice_exam?.id : record.practice_exam
    if (theoryId) {
      details = await api.exams.getTheoryExam(theoryId)
      if (!pageAlive || reading !== examReadGeneration || id !== recordId.value) return false
      loadedQuestions = await api.exams.getTheoryQuestions(theoryId)
    } else if (practiceId) {
      details = await api.exams.getPracticeExam(practiceId)
      if (!pageAlive || reading !== examReadGeneration || id !== recordId.value) return false
      loadedQuestions = await api.exams.getPracticeQuestions(practiceId)
    } else {
      throw new Error('考试记录无效')
    }
    if (!pageAlive || reading !== examReadGeneration || id !== recordId.value) return false
    examType.value = theoryId ? 'theory' : 'practice'
    examInfo.value = { id: theoryId || practiceId, title: record.exam_title, duration: details.duration }
    questions.value = Array.isArray(loadedQuestions) ? loadedQuestions : loadedQuestions?.results || []
    const duration = Number(details.duration)
    const startedAt = Date.parse(record.start_time)
    if (!Number.isFinite(duration) || duration <= 0 || !Number.isFinite(startedAt)) throw new Error('考试时间无法确认')
    elapsedTime.value = Math.max(0, Math.floor((Date.now() - startedAt) / 1000))
    timeRemaining.value = Math.max(0, Math.floor(duration * 60) - elapsedTime.value)
    examDeadline.value = startedAt + duration * 60000
    answers.value = {}
    if (Array.isArray(record.answers)) {
      for (const answer of record.answers) {
        let questionId = null
        const answerRef = savedAnswerRef(examType.value === 'theory', answer)
        if (examType.value === 'theory') {
          const examQuestion = questions.value.find(q => String(q.question) === String(answerRef))
          if (examQuestion) {
            questionId = examQuestion.id
          }
        } else {
          questionId = answerRef
        }
        if (questionId && typeof answer.user_answer === 'string' && answer.user_answer !== '[REDACTED]' && answer.user_answer.trim()) {
          answers.value[questionId] = {
            user_answer: answer.user_answer,
            is_correct: answer.is_correct,
            points_earned: answer.points_earned,
          }
          savedTheoryAnswers.set(questionId, answer.user_answer)
        }
      }
    }

    return true
  } catch (error) {
    if (pageAlive && reading === examReadGeneration) loadError.value = '考试信息暂时无法读取，请重新进入考试或联系教师核对。'
    return false
  } finally {
    if (reading === examReadGeneration) loading.value = false
  }
}

// 更新计时器
const updateTimer = () => {
  if (examDeadline.value) {
    timeRemaining.value = Math.max(0, Math.ceil((examDeadline.value - Date.now()) / 1000))
    elapsedTime.value = Math.max(0, Math.floor(Number(examInfo.value.duration) * 60 - (examDeadline.value - Date.now()) / 1000))
  }
  if (timeRemaining.value > 0) {
    if (!examDeadline.value) { timeRemaining.value--; elapsedTime.value++ }
    if (examType.value === 'theory' && theoryDirty.size) void saveTheoryAnswers()
  } else {
    // 时间到，自动提交
    handleTimeUp()
  }
}

const handleTimeUp = async () => {
  clearInterval(timer.value)
  timeoutNotice.value = ''
  if (examType.value === 'theory') {
    // Await requests already sent before expiry; the server remains the
    // authority for the deadline. Do not resend saved answers after expiry.
    if (theorySavePromise) await theorySavePromise
    if (theoryDirty.size) timeoutNotice.value = '考试时间已到，仅结算截止前保存成功的答案；未保存的选择未计入成绩，请联系教师核对。'
  }
  await confirmSubmit(true)
}

async function restartExam() {
  clearInterval(timer.value)
  if (await loadExamInfo() && pageAlive) timer.value = setInterval(updateTimer, 1000)
}
watch(recordId, restartExam)
onMounted(restartExam)

onUnmounted(() => {
  pageAlive = false
  ++examReadGeneration
  if (timer.value) {
    clearInterval(timer.value)
  }
})
</script>


<style scoped src="./examTaking.css"></style>
