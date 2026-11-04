<template>
  <div class="exam-taking-page">
    <header class="exam-header">
      <div class="header-left">
        <p class="page-context">{{ names.exams }} · 正式答题</p>
        <h1 class="exam-title">{{ examInfo.title || '正式测评' }}</h1>
        <div v-if="!loading && !loadError" class="exam-meta">
          <span class="exam-type-badge">{{ examType === 'theory' ? '理论考试' : '实战考试' }}</span>
          <span v-if="questions.length">第 {{ currentQuestionIndex + 1 }} 题 / 共 {{ questions.length }} 题</span>
        </div>
      </div>
      <div class="header-right">
        <div v-if="!loading && !loadError" class="timer" :class="{ warning: timeRemaining < 300, danger: timeRemaining < 60 }">
          <icon-clock-circle aria-hidden="true" />
          <div>
            <span class="timer-label">剩余时间</span>
            <span class="timer-value" role="timer" aria-live="off">{{ formatTime(timeRemaining) }}</span>
          </div>
          <span class="timer-warning" role="status">{{ timeRemaining < 60 ? '不足 1 分钟' : timeRemaining < 300 ? '不足 5 分钟' : '' }}</span>
        </div>
        <button type="button" class="btn btn-outline" @click="exitExam">退出考试</button>
      </div>
    </header>

    <!-- 保存/交卷失败必须页面可见；不能只留在内部状态或依赖弹窗提示。 -->
    <p v-if="submitError" class="exam-notice is-error" role="alert">{{ submitError }}</p>
    <div v-if="loading" class="page-state" role="status" aria-busy="true">
      <icon-loading aria-hidden="true" /> 正在读取考试题目与已提交答案…
    </div>
    <div v-else-if="loadError" class="page-state load-error" role="alert">{{ loadError }}</div>
    <p v-if="timeoutNotice" class="exam-notice is-error" role="alert">{{ timeoutNotice }}</p>
    <div v-else-if="!questions.length" class="page-state" role="status">本场考试暂无题目，请联系教师或退出考试。</div>

    <div v-else class="exam-content">
      <section class="question-section" aria-labelledby="question-heading">
        <div v-if="currentQuestion" class="question-card">
          <div class="question-heading">
            <h2 id="question-heading" class="question-title">第 {{ currentQuestionIndex + 1 }} 题</h2>
            <span class="question-type-badge">{{ examType === 'practice' ? '实战题' : getQuestionTypeText(currentQuestion.question_detail?.question_type || 'single_choice') }}</span>
            <span v-if="currentQuestion.points" class="question-score">{{ currentQuestion.points }} 分</span>
          </div>
          <div class="question-detail" v-html="formatQuestion(currentQuestion)"></div>

          <div class="answer-section">
            <fieldset v-if="examType === 'theory' && currentQuestion.question_detail" class="options-list">
              <legend class="answer-hint">{{ currentQuestion.question_detail.question_type === 'multiple_choice' ? '请选择所有符合题意的选项' : '请选择一个选项' }}</legend>
              <button
                v-for="(option, index) in currentQuestion.question_detail.options"
                :key="index"
                type="button"
                class="option-item"
                :class="{ selected: isOptionSelected(option) }"
                :aria-pressed="isOptionSelected(option)"
                @click="selectOption(option)"
              >
                <span class="option-marker">{{ getOptionLabel(index) }}</span>
                <span class="option-text">{{ option }}</span>
                <icon-check-circle v-if="isOptionSelected(option)" class="option-check" aria-hidden="true" />
              </button>
            </fieldset>

            <div v-else-if="examType === 'practice' && currentQuestion.challenge" class="practice-answer">
              <div class="practice-info">
                <span>难度 <strong>{{ getDifficultyText(currentQuestion.challenge_difficulty) }}</strong></span>
                <span>分值 <strong>{{ currentQuestion.challenge_points || 0 }} 分</strong></span>
              </div>
              <label class="input-label" for="exam-flag">Flag 答案</label>
              <div class="flag-input">
                <input
                  id="exam-flag"
                  v-model="currentAnswer"
                  type="text"
                  class="input"
                  :disabled="submittingAnswer"
                  placeholder="请输入 flag，例如 flag{...}"
                  @keyup.enter="submitAnswer"
                />
                <button type="button" class="btn btn-primary" @click="submitAnswer" :disabled="!currentAnswer.trim() || submittingAnswer" :aria-busy="submittingAnswer">{{ submittingAnswer ? '正在提交答案…' : '提交答案' }}</button>
              </div>
              <div v-if="submissionResult" class="submission-result" :class="{ success: submissionResult.is_correct, error: !submissionResult.is_correct }" role="status">
                <icon-check-circle v-if="submissionResult.is_correct" aria-hidden="true" />
                <icon-close-circle v-else aria-hidden="true" />
                <span>{{ submissionResult.is_correct ? '答案正确！' : '答案错误，请重试' }}</span>
              </div>
            </div>
          </div>

          <nav class="navigation-buttons" aria-label="切换题目">
            <button type="button" class="btn btn-outline" @click="prevQuestion" :disabled="currentQuestionIndex === 0">
              <icon-left aria-hidden="true" /> 上一题
            </button>
            <button type="button" class="btn btn-outline" @click="nextQuestion" :disabled="currentQuestionIndex === questions.length - 1">
              下一题 <icon-right aria-hidden="true" />
            </button>
          </nav>
        </div>
      </section>

      <aside class="question-nav-section" aria-labelledby="question-nav-heading">
        <div class="nav-card">
          <h2 id="question-nav-heading" class="nav-title">题目导航</h2>
          <div class="nav-legend" aria-hidden="true">
            <span>描边为当前题</span>
            <span><icon-check aria-hidden="true" /> 已答</span>
            <span>空圈为未答</span>
          </div>
          <nav class="nav-grid" aria-label="按题号跳转">
            <button
              v-for="(question, index) in questions"
              :key="index"
              type="button"
              class="nav-item"
              :class="{ current: index === currentQuestionIndex, answered: isAnswered(index) }"
              :aria-current="index === currentQuestionIndex ? 'step' : undefined"
              :aria-label="`第 ${index + 1} 题，${isAnswered(index) ? '已答' : '未答'}${index === currentQuestionIndex ? '，当前题' : ''}`"
              @click="goToQuestion(index)"
            >
              <span>{{ index + 1 }}</span>
              <icon-check v-if="isAnswered(index)" aria-hidden="true" />
              <span v-else class="unanswered-marker" aria-hidden="true"></span>
            </button>
          </nav>
          <dl class="progress-stats">
            <div><dt>已答题目</dt><dd>{{ answeredCount }} / {{ questions.length }}</dd></div>
            <div><dt>正确率</dt><dd>{{ accuracyRate }}%</dd></div>
          </dl>
          <div class="quick-nav">
            <button type="button" class="btn btn-outline" @click="goToFirstUnanswered" :disabled="!hasUnanswered">跳转未答</button>
            <button type="button" class="btn" :class="examType === 'theory' ? 'btn-primary' : 'btn-outline'" @click="submitExam" :disabled="!canSubmit || preparingSubmit" :aria-busy="preparingSubmit">{{ preparingSubmit ? '正在提交答案…' : '提交考试' }}</button>
          </div>
        </div>
      </aside>
    </div>

    <ExamTakingDialog :open="showSubmitDialog" title="提交考试" title-id="exam-submit-heading" @close="closeSubmitDialog">
      <dl class="submit-info">
        <div><dt>已答题目</dt><dd>{{ answeredCount }} / {{ questions.length }}</dd></div>
        <div><dt>已用时间</dt><dd>{{ formatTime(elapsedTime) }}</dd></div>
      </dl>
      <p v-if="answeredCount < questions.length" class="warning-text">
        <icon-exclamation-circle aria-hidden="true" />
        还有 {{ questions.length - answeredCount }} 道题未答，确认提交吗？
      </p>
      <template #footer>
        <button type="button" class="btn btn-outline" autofocus @click="closeSubmitDialog">取消</button>
        <button type="button" class="btn btn-primary" @click="confirmSubmit" :disabled="submittingExam" :aria-busy="submittingExam">{{ submittingExam ? '正在交卷…' : '确认提交' }}</button>
      </template>
    </ExamTakingDialog>

    <ExamTakingDialog :open="showExitDialog" title="退出考试" title-id="exam-exit-heading" @close="closeExitDialog">
      <p>请选择退出方式。</p>
      <div class="exit-options">
        <button type="button" class="exit-option" @click="exitWithoutAbandon">
          <span class="option-title"><icon-save aria-hidden="true" /> 退出并保留</span>
          <span class="option-desc">仅保留已提交的答案，尚未提交的选择不会保存</span>
        </button>
        <button type="button" class="exit-option danger" @click="abandonAndExit" :disabled="abandoning" :aria-busy="abandoning">
          <span class="option-title"><icon-exclamation-circle aria-hidden="true" /> {{ abandoning ? '正在放弃考试…' : '放弃考试' }}</span>
          <span class="option-desc">放弃当前考试，无法恢复</span>
        </button>
      </div>
      <template #footer>
        <button type="button" class="btn btn-outline" autofocus @click="closeExitDialog">取消</button>
      </template>
    </ExamTakingDialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '@/api'
import { sanitizeHtml } from '@/utils/sanitize'
import { names } from '@/shared/navigation/names'
import { RESULT_PATH, practiceQuestionRef, savedAnswerRef, theoryExamId, theoryQuestionRef } from '@/learning/exams/api.js'
import ExamTakingDialog from './ExamTakingDialog.vue'

const router = useRouter()
const route = useRoute()

// recordId 必须随路由变化重新读卷；仍以原服务器考试时间计时，不自造新的开始时间。
const recordId = computed(() => route.params.id)
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
const loading = ref(true)
const loadError = ref('')
const submitError = ref('')
const timeoutNotice = ref('')
const submittingAnswer = ref(false)
const preparingSubmit = ref(false)
const submittingExam = ref(false)
const abandoning = ref(false)
let loadVersion = 0

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

// 仅转换展示文案，不更改难度或评分口径。
const getDifficultyText = (difficulty) => {
  const labels = { easy: '简单', medium: '中等', hard: '困难', 简单: '简单', 中等: '中等', 困难: '困难' }
  return labels[String(difficulty || '').toLowerCase()] || '未知'
}

// 格式化题目内容
const formatQuestion = (question) => {
  // 理论题
  if (question.question_detail) {
    return sanitizeHtml(question.question_detail.question_text)
  }
  // 实战题
  if (question.challenge) {
    return sanitizeHtml(question.challenge.description || question.challenge_title)
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
    submitError.value = ''
  }
}

// 下一题
const nextQuestion = () => {
  if (currentQuestionIndex.value < questions.value.length - 1) {
    currentQuestionIndex.value++
    currentAnswer.value = ''
    submissionResult.value = null
    submitError.value = ''
  }
}

// 跳转到指定题目
const goToQuestion = (index) => {
  currentQuestionIndex.value = index
  currentAnswer.value = ''
  submissionResult.value = null
  submitError.value = ''
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

// 逐题保存理论题的核心字段是试卷题目关联 id（practice）或原题目 id（theory），
// 结果接口返回的 theory_question/practice_question 是同一口径，不能与关联 id 混用。
async function saveTheoryAnswers({ onlyUnsaved = false } = {}) {
  let failures = 0
  for (const question of questions.value) {
    const selected = answers.value[question.id]
    if (!selected) continue
    if (onlyUnsaved && selected.saved) continue
    const questionRef = theoryQuestionRef(question)
    if (questionRef === null) { failures++; continue }
    try {
      const result = await api.exams.submitAnswer(recordId.value, {
        theory_question_id: questionRef,
        user_answer: selected.user_answer,
        time_spent: Math.floor(elapsedTime.value),
      })
      const next = { ...selected, saved: true }
      if (result && typeof result.is_correct === 'boolean') next.is_correct = result.is_correct
      if (result && result.points_earned !== null && result.points_earned !== undefined) next.points_earned = result.points_earned
      answers.value[question.id] = next
    } catch {
      failures++
    }
  }
  return failures
}

// 提交答案（实战题）
const submitAnswer = async () => {
  if (!currentQuestion.value || !currentAnswer.value.trim() || submittingAnswer.value) return
  const questionRef = practiceQuestionRef(currentQuestion.value)
  if (questionRef === null) {
    submitError.value = '本题缺少可保存的题目标识，暂时不能提交；请返回试炼场重新进入。'
    return
  }

  submittingAnswer.value = true
  submitError.value = ''
  try {
    const result = await api.exams.submitAnswer(recordId.value, {
      practice_question_id: questionRef,
      user_answer: currentAnswer.value.trim(),
      time_spent: Math.floor(elapsedTime.value),
    })

    submissionResult.value = result
    answers.value[currentQuestion.value.id] = {
      user_answer: currentAnswer.value.trim(),
      is_correct: result.is_correct,
      points_earned: result.points_earned,
      saved: true,
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
    // 保留输入与未答状态：失败的保存不会被当作已保存。
    submitError.value = '答案尚未保存成功，输入已保留。请检查网络后重试。'
    alert('提交失败，请重试')
  } finally {
    submittingAnswer.value = false
  }
}

// 提交考试
const submitExam = () => {
  if (examType.value === 'theory') {
    // 理论题：先逐题保存所有选择，保存失败不进入交卷确认。
    submitAllTheoryAnswers()
  } else {
    // 实战题：已提交的 Flag 答案在服务端；直接显示确认对话框。
    showSubmitDialog.value = true
  }
}

// 提交所有理论题答案
const submitAllTheoryAnswers = async () => {
  if (preparingSubmit.value) return
  preparingSubmit.value = true
  submitError.value = ''
  try {
    const failures = await saveTheoryAnswers()
    if (failures > 0) {
      submitError.value = `有 ${failures} 道题的选择尚未保存成功，暂不进入交卷。输入已保留，请检查网络后在本题重新选择并提交。`
      return
    }
    showSubmitDialog.value = true
  } finally {
    preparingSubmit.value = false
  }
}

// 最终交卷：防重复；失败保留对话框与当前答案，不假装已交卷。
async function finalizeSubmission() {
  if (submittingExam.value) return
  submittingExam.value = true
  submitError.value = ''
  try {
    await api.exams.submitExam(recordId.value)

    // 理论考试交卷后由后台开启配对的实战记录。
    if (examType.value === 'theory') {
      const record = await api.exams.getExamResult(recordId.value)
      if (record?.practice_record_id) {
        router.push(`/exam-taking/${record.practice_record_id}`)
        return
      }
    }
    router.push(RESULT_PATH(recordId.value))
  } catch (error) {
    console.error('提交考试失败:', error)
    submitError.value = '交卷尚未成功，答案仍保留在本页。请检查网络后再次提交。'
    alert('提交失败，请重试')
  } finally {
    submittingExam.value = false
  }
}

// 确认提交
const confirmSubmit = async () => {
  if (submittingExam.value || preparingSubmit.value) return
  // 理论题在确认前再核对一遍未保存的选择，避免“确认了但没保存”。
  if (examType.value === 'theory') {
    preparingSubmit.value = true
    let failures = 0
    try { failures = await saveTheoryAnswers({ onlyUnsaved: true }) } finally { preparingSubmit.value = false }
    if (failures > 0) {
      submitError.value = `有 ${failures} 道题的选择尚未保存成功，暂不交卷。请恢复网络后重试。`
      return
    }
  }
  await finalizeSubmission()
}

// 关闭提交对话框
const closeSubmitDialog = () => {
  showSubmitDialog.value = false
}

// 退出考试
const exitExam = () => {
  showExitDialog.value = true
}

// 退出但不放弃考试：不写入任何答案，已保存的答案由服务端保留。
const exitWithoutAbandon = () => {
  closeExitDialog()
  router.push('/exam-center')
}

// 放弃考试并退出：先确认，再按真实响应重读记录；不把失败当作已放弃。
const abandonAndExit = async () => {
  if (abandoning.value) return
  abandoning.value = true
  submitError.value = ''
  try {
    await api.exams.startComprehensiveExam({ abandon: true })
    let status = null
    try { status = (await api.exams.getExamResult(recordId.value))?.status ?? null } catch { status = null }
    if (status === 'in_progress') {
      submitError.value = '后台仍显示本场考试进行中，放弃可能未生效。请重试或返回试炼场确认。'
      return
    }
    closeExitDialog()
    router.push('/exam-center')
  } catch (error) {
    console.error('放弃考试失败:', error)
    alert('放弃考试失败')
  } finally {
    abandoning.value = false
  }
}

// 关闭退出对话框；取消确认不写入任何状态。
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

function resetExamState() {
  if (timer.value) { clearInterval(timer.value); timer.value = null }
  examType.value = 'theory'
  examInfo.value = {}
  questions.value = []
  currentQuestionIndex.value = 0
  answers.value = {}
  currentAnswer.value = ''
  timeRemaining.value = 0
  elapsedTime.value = 0
  submissionResult.value = null
  submitError.value = ''
  timeoutNotice.value = ''
  loadError.value = ''
  showSubmitDialog.value = false
  showExitDialog.value = false
  loading.value = true
}

// 加载本场题目、时限与服务端已保存的答案；旧 recordId 的响应不得写入新卷。
const loadExamInfo = async () => {
  const version = ++loadVersion
  const id = recordId.value
  loading.value = true
  loadError.value = ''
  try {
    const record = await api.exams.getExamResult(id)
    if (version !== loadVersion) return
    if (record.status && record.status !== 'in_progress') {
      router.push(RESULT_PATH(id))
      return
    }
    const theory = record.theory_exam !== null && record.theory_exam !== undefined && record.theory_exam !== ''
    const examId = theory ? theoryExamId(record) : (typeof record.practice_exam === 'object' ? record.practice_exam?.id : record.practice_exam)
    if (examId === null || examId === undefined) throw new Error('考试记录无效')
    const [exam, items] = await Promise.all([
      theory ? api.exams.getTheoryExam(examId) : api.exams.getPracticeExam(examId),
      theory ? api.exams.getTheoryQuestions(examId) : api.exams.getPracticeQuestions(examId),
    ])
    if (version !== loadVersion) return
    const duration = Number(exam.duration)
    const started = Date.parse(record.start_time)
    if (!Number.isFinite(duration) || duration <= 0 || !Number.isFinite(started)) {
      throw new Error('考试时限暂不可用')
    }
    examType.value = theory ? 'theory' : 'practice'
    examInfo.value = { ...exam, title: record.exam_title || exam.title }
    questions.value = Array.isArray(items) ? items : []
    elapsedTime.value = Math.max(0, Math.floor((Date.now() - started) / 1000))
    timeRemaining.value = Math.max(0, duration * 60 - elapsedTime.value)
    answers.value = {}
    for (const answer of record.answers || []) {
      const questionId = theory
        ? questions.value.find(q => String(theoryQuestionRef(q)) === String(savedAnswerRef(theory, answer)))?.id
        : savedAnswerRef(theory, answer)
      if (questionId !== null && questionId !== undefined && questions.value.some(q => q.id === questionId)) {
        answers.value[questionId] = {
          user_answer: answer.user_answer,
          is_correct: answer.is_correct,
          points_earned: answer.points_earned,
          saved: true,
        }
      }
    }
  } catch (error) {
    if (version !== loadVersion) return
    loadError.value = '考试信息暂时未能读取，请返回试炼场重试或联系教师。'
    alert(loadError.value)
    router.push('/exam-center')
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

function startTimer() {
  if (timer.value) clearInterval(timer.value)
  if (!loadError.value && questions.value.length) timer.value = setInterval(updateTimer, 1000)
}

// 到时交卷：先处理尚未保存的选择；保存失败时不假交卷，保留输入并明确提示。
async function handleTimeUp() {
  if (submittingExam.value || preparingSubmit.value) return
  if (examType.value === 'theory') {
    const failures = await saveTheoryAnswers({ onlyUnsaved: true })
    if (failures > 0) {
      timeoutNotice.value = `已到时限，但有 ${failures} 道已选答案未能保存。系统不会把未保存的答案当作已交卷；请恢复网络后手动提交。`
      return
    }
  }
  timeoutNotice.value = '已到时限，正在按服务端已保存的答案交卷。'
  await finalizeSubmission()
}

// 更新计时器
const updateTimer = () => {
  if (timeRemaining.value > 0) {
    timeRemaining.value--
    elapsedTime.value++
  } else {
    // 时间到，按真实保存状态交卷（只触发一次）。
    clearInterval(timer.value)
    timer.value = null
    handleTimeUp()
  }
}

watch(recordId, (next, previous) => {
  if (next === previous) return
  // 换记录必须重新读卷并丢弃旧响应，不能只靠 mounted 一次加载。
  loadVersion++
  resetExamState()
  loadExamInfo().then(startTimer)
})

onMounted(async () => {
  await loadExamInfo()
  startTimer()
})

onUnmounted(() => {
  if (timer.value) {
    clearInterval(timer.value)
    timer.value = null
  }
})
</script>

<style scoped src="./examTaking.css"></style>
