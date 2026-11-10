<template>
  <div class="profile-setup-page">
    <main class="interview-shell">
      <header class="interview-head">
        <div>
          <p class="section-kicker">INITIAL LEARNING PROFILE</p>
          <h1>AI 初始学习画像访谈</h1>
          <p>请按真实情况回答。AI 会结合回答内容生成初始画像，后续再由学习数据持续校正。</p>
        </div>
        <div class="progress-copy">{{ completed ? '已完成' : `第 ${currentQuestionId} / ${questions.length || 8} 题` }}</div>
      </header>

      <div class="progress-track" aria-hidden="true">
        <span :style="{ width: `${progress}%` }"></span>
      </div>

      <section ref="conversationRef" class="conversation" aria-live="polite">
        <div class="message-row assistant">
          <div class="avatar">AI</div>
          <div class="message-bubble">
            <strong>学习画像助手</strong>
            <p>你好，我会通过 8 个自然问答了解你的基础、目标和学习习惯。这里没有标准答案，请描述真实经历和想法。</p>
          </div>
        </div>

        <template v-for="item in visibleQuestions" :key="item.id">
          <div class="message-row assistant">
            <div class="avatar">AI</div>
            <div class="message-bubble">
              <span class="question-label">{{ item.title }}</span>
              <p>{{ item.question }}</p>
            </div>
          </div>
          <div v-if="answers[String(item.id)]" class="message-row student">
            <div class="message-bubble"><p>{{ answers[String(item.id)] }}</p></div>
            <div class="avatar student-avatar">我</div>
          </div>
        </template>

        <div v-if="analyzing" class="message-row assistant">
          <div class="avatar">AI</div>
          <div class="message-bubble analyzing"><span></span><span></span><span></span> 正在分析回答并生成初始画像...</div>
        </div>

        <div v-if="completed" class="report-result">
          <div>
            <p class="section-kicker">PROFILE GENERATED</p>
            <h2>初始学习画像已生成并保存</h2>
            <p>{{ report?.summary || report?.report_data?.summary }}</p>
          </div>
          <a-button type="primary" size="large" @click="router.replace({ path: '/profile', query: { tab: 'persona' } })">查看学习画像</a-button>
        </div>
      </section>

      <footer v-if="!completed" class="answer-panel">
        <label :for="`answer-${currentQuestionId}`">你的回答</label>
        <a-textarea
          :id="`answer-${currentQuestionId}`"
          v-model="answerDraft"
          :max-length="4000"
          :auto-size="{ minRows: 4, maxRows: 8 }"
          show-word-limit
          placeholder="请结合你的真实经历和想法回答..."
          :disabled="loading || analyzing"
          @keydown.ctrl.enter.prevent="submitAnswer"
        />
        <div class="answer-actions">
          <span>回答会作为原始画像依据保存 · Ctrl + Enter 提交</span>
          <a-button type="primary" size="large" :loading="loading || analyzing" :disabled="answerDraft.trim().length < 2" @click="submitAnswer">
            {{ currentQuestionId === questions.length ? '提交并生成画像' : '提交回答' }}
          </a-button>
        </div>
      </footer>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import api from '@/api'

const router = useRouter()
const conversationRef = ref(null)
const questions = ref([])
const answers = ref({})
const currentQuestionId = ref(1)
const answerDraft = ref('')
const loading = ref(false)
const analyzing = ref(false)
const completed = ref(false)
const report = ref(null)

const visibleQuestions = computed(() => questions.value.filter((item) => item.id <= currentQuestionId.value))
const progress = computed(() => {
  if (completed.value) return 100
  return Math.max(4, Math.round(((currentQuestionId.value - 1) / (questions.value.length || 8)) * 100))
})

const scrollToBottom = async () => {
  await nextTick()
  if (conversationRef.value) conversationRef.value.scrollTop = conversationRef.value.scrollHeight
}

const loadInterview = async () => {
  loading.value = true
  try {
    const data = await api.studentProfile.onboardingInterview()
    questions.value = data.questions || []
    answers.value = data.answers || {}
    completed.value = data.status === 'completed'
    report.value = data.report
    currentQuestionId.value = completed.value ? questions.value.length : Math.min(data.current_question || 1, questions.value.length || 1)
    answerDraft.value = answers.value[String(currentQuestionId.value)] || ''
    await scrollToBottom()
  } catch (error) {
    Message.error(error?.response?.data?.detail || '加载画像访谈失败')
  } finally {
    loading.value = false
  }
}

const submitAnswer = async () => {
  const answer = answerDraft.value.trim()
  if (answer.length < 2 || loading.value || analyzing.value) return
  loading.value = true
  answers.value = { ...answers.value, [String(currentQuestionId.value)]: answer }
  await scrollToBottom()
  if (currentQuestionId.value === questions.value.length) analyzing.value = true
  try {
    const data = await api.studentProfile.answerOnboardingQuestion({
      question_id: currentQuestionId.value,
      answer,
    })
    if (data.completed) {
      completed.value = true
      report.value = data.report
      answerDraft.value = ''
      Message.success('初始学习画像与学生报表已保存')
      await router.replace({ path: '/profile', query: { tab: 'persona' } })
    } else {
      currentQuestionId.value = data.current_question
      answerDraft.value = answers.value[String(currentQuestionId.value)] || ''
    }
    await scrollToBottom()
  } catch (error) {
    Message.error(error?.response?.data?.answer?.[0] || error?.response?.data?.detail || '回答保存失败，请重试')
  } finally {
    loading.value = false
    analyzing.value = false
  }
}

onMounted(loadInterview)
</script>

<style scoped>
.profile-setup-page {
  min-height: calc(100vh - 64px);
  padding: 28px;
  background: #f4f1eb;
  color: #191814;
}

.interview-shell {
  width: min(980px, 100%);
  margin: 0 auto;
  overflow: hidden;
  border: 1px solid #d8d2c8;
  border-radius: 8px;
  background: #fffdf9;
  box-shadow: 0 14px 36px rgba(30, 27, 22, 0.08);
}

.interview-head {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 28px 32px 22px;
  border-bottom: 1px solid #e6e0d7;
}

.section-kicker { margin: 0 0 8px; color: #b8332b; font-size: 12px; font-weight: 800; }
.interview-head h1 { margin: 0; font-size: 25px; }
.interview-head p { max-width: 680px; margin: 9px 0 0; color: #6b655c; line-height: 1.7; }
.progress-copy { flex: none; color: #b8332b; font-weight: 700; }
.progress-track { height: 4px; background: #eee9e1; }
.progress-track span { display: block; height: 100%; background: #b8332b; transition: width 0.25s ease; }

.conversation {
  height: min(52vh, 540px);
  min-height: 360px;
  overflow-y: auto;
  padding: 28px 32px;
  background-image: linear-gradient(to right, rgba(75, 68, 58, 0.045) 1px, transparent 1px);
  background-size: 66px 100%;
}

.message-row { display: flex; align-items: flex-start; gap: 11px; margin-bottom: 20px; }
.message-row.student { justify-content: flex-end; }
.avatar { display: grid; width: 36px; height: 36px; flex: 0 0 36px; place-items: center; border-radius: 50%; background: #191814; color: #fff; font-size: 12px; font-weight: 800; }
.student-avatar { background: #b8332b; }
.message-bubble { max-width: 72%; padding: 14px 16px; border: 1px solid #ded8ce; border-radius: 4px; background: #fff; }
.student .message-bubble { border-color: #b8332b; background: #fbf0ed; }
.message-bubble strong, .question-label { display: block; margin-bottom: 7px; font-size: 13px; color: #b8332b; font-weight: 800; }
.message-bubble p { margin: 0; line-height: 1.75; white-space: pre-wrap; }
.analyzing span { display: inline-block; width: 6px; height: 6px; margin-right: 4px; border-radius: 50%; background: #b8332b; }

.report-result { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-top: 12px; padding: 24px; border: 1px solid #d7b06f; background: #fff5dc; }
.report-result h2 { margin: 0 0 8px; font-size: 20px; }
.report-result p { margin: 0; color: #6b655c; line-height: 1.7; }

.answer-panel { padding: 22px 32px 28px; border-top: 1px solid #e0dad0; background: #fff; }
.answer-panel label { display: block; margin-bottom: 10px; font-weight: 700; }
.answer-actions { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-top: 14px; }
.answer-actions span { color: #837c72; font-size: 12px; }

@media (max-width: 700px) {
  .profile-setup-page { padding: 12px; }
  .interview-head { display: block; padding: 22px 20px 18px; }
  .progress-copy { margin-top: 12px; }
  .conversation { height: 50vh; padding: 22px 18px; }
  .message-bubble { max-width: 82%; }
  .answer-panel { padding: 18px; }
  .answer-actions, .report-result { align-items: stretch; flex-direction: column; }
}
</style>
