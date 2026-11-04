<template>
  <div class="profile-setup-page">
    <main class="interview-shell">
      <header class="interview-head">
        <div>

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
  color: var(--ink);
  font-family: var(--font-family);
  font-size: var(--text-body);
  line-height: var(--leading-body);
  background: var(--surface-page);
  box-sizing: border-box;
  min-height: calc(100vh - var(--header-height));
  padding: var(--space-4) var(--page-gutter);
}

.interview-shell {
  margin: 0 auto;
  overflow: hidden;
  border: var(--stroke) solid var(--line);
  background: var(--surface);
  box-shadow: none;
  width: 100%;
  max-width: var(--reading-width);
  border-radius: var(--radius-panel);
}

.interview-head {
  display: flex;
  justify-content: space-between;
  border-bottom: var(--stroke) solid var(--line);
  padding: var(--space-3) var(--space-4);
  gap: var(--space-3);
}
.interview-head h1 { margin: 0; font-size: var(--text-page); line-height: var(--leading-tight); font-weight: var(--weight-strong); }
.interview-head p { margin: var(--space-1) 0 0; color: var(--ink-secondary); line-height: var(--leading-body); max-width: var(--reading-width); }
.progress-copy { flex: none; font-weight: var(--weight-strong); font-size: var(--text-caption); color: var(--ink-secondary); }
.progress-track { height: 4px; background: var(--surface-muted); }
.progress-track span { display: block; height: 100%; background: var(--action); transition: width var(--motion-normal) var(--motion-ease); }

.conversation {
  height: min(52vh, 540px);
  min-height: 360px;
  overflow-y: auto;
  padding: var(--space-3) var(--space-4);
}

.message-row { display: flex; align-items: flex-start; margin-bottom: var(--space-3); gap: var(--space-2); }
.message-row.student { justify-content: flex-end; }
.avatar { display: grid; place-items: center; border-radius: var(--radius-pill); font-size: var(--text-caption); font-weight: var(--weight-strong); width: var(--avatar-size); height: var(--avatar-size); flex: 0 0 var(--avatar-size); background: var(--agent-soft); color: var(--agent-accent); }
.student-avatar {
  background: var(--action-soft);
  color: var(--action); }
.message-bubble { max-width: 72%; border: none; background: transparent; border-radius: var(--radius-panel); padding: var(--space-2); min-width: 0; overflow-wrap: anywhere; }
.student .message-bubble {
  background: var(--action-soft); }
.message-bubble strong, .question-label { display: block; margin-bottom: var(--space-1); font-size: var(--text-caption); font-weight: var(--weight-strong); color: var(--ink-secondary); }
.message-bubble p { margin: 0; line-height: var(--leading-body); white-space: pre-wrap; }
.analyzing span { display: inline-block; margin-right: var(--space-1); border-radius: var(--radius-pill); background: var(--agent-accent); width: var(--space-1); height: var(--space-1); }

.report-result { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); margin-top: var(--space-1); padding: var(--space-3); border: none; border-radius: var(--radius-panel); background: var(--positive-soft); }
.report-result h2 { margin: 0 0 var(--space-1); font-size: var(--text-section); font-weight: var(--weight-strong); }
.report-result p { margin: 0; color: var(--ink-secondary); line-height: var(--leading-body); }

.answer-panel { border-top: var(--stroke) solid var(--line); background: var(--surface); padding: var(--space-3) var(--space-4); }
.answer-panel label { display: block; margin-bottom: var(--space-1); font-weight: var(--weight-strong); }
.answer-actions { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); margin-top: var(--space-2); }
.answer-actions span { color: var(--ink-muted); font-size: var(--text-caption); }

@media (max-width: 768px) {
  .profile-setup-page { padding: var(--space-1); }
  .interview-head { display: block; padding: var(--space-3) var(--space-2) var(--space-2); }
  .progress-copy { margin-top: var(--space-1); }
  .conversation { height: 50vh; padding: var(--space-3) var(--space-2); }
  .message-bubble { max-width: 82%; }
  .answer-panel { padding: var(--space-2); }
  .answer-actions, .report-result { align-items: stretch; flex-direction: column; }
}

.answer-panel :deep(.arco-textarea) { font-family: var(--font-family); font-size: var(--text-body); line-height: var(--leading-body); }

.profile-setup-page :is(button, input, select, textarea, a):focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }

.profile-setup-page :is(input, textarea)::placeholder { color: var(--ink-muted); }

.profile-setup-page :is(input, select, textarea):disabled { background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }

.profile-setup-page button:disabled { background: var(--disabled); color: var(--disabled-ink); border-color: var(--line); cursor: not-allowed; opacity: 1; }
</style>
