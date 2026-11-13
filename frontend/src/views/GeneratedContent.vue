<template>
  <main class="generated-content-page">
    <p v-if="loading" role="status">正在读取生成内容…</p>
    <section v-else-if="failure" class="content-card" role="alert">
      <h1>{{ failure.title }}</h1><p>{{ failure.message }}</p>
      <a-button @click="fetchContent">重新读取</a-button>
    </section>
    <template v-else-if="content">
      <header class="content-header"><h1>{{ view.title }}</h1><a-tag :color="view.typeColor">{{ view.typeLabel }}</a-tag></header>
      <section v-if="view.type === 'quiz' && view.hasQuestions" class="quiz-area">
        <p>本地练习，不计入正式测评。</p>
        <article v-for="(q, qi) in view.questions" :key="qi" class="content-card quiz-card">
          <h2>{{ qi + 1 }}. {{ q.question }}</h2>
          <a-radio-group v-model="answers[qi]" direction="vertical" :disabled="submitted">
            <a-radio v-for="(opt, oi) in q.options" :key="oi" :value="oi">{{ opt }}</a-radio>
          </a-radio-group>
          <div v-if="submitted" class="quiz-feedback">
            <p v-if="q.answerIndex === null">本题未提供可判定答案，不计分。</p>
            <p v-else-if="answers[qi] === q.answerIndex">回答正确！</p>
            <p v-else>正确答案：{{ q.options[q.answerIndex] }}</p>
            <p v-if="q.explanation">{{ q.explanation }}</p>
          </div>
        </article>
        <a-button type="primary" @click="submitQuiz" :disabled="submitted">提交本地练习</a-button>
        <p v-if="submitted" role="status">{{ result.label }}</p>
      </section>
      <section v-else-if="view.type === 'diagram' && view.mermaidCode" class="content-card">
        <MermaidDiagram :mermaid-code="view.mermaidCode" />
      </section>
      <section v-else-if="view.type === 'exercise'" class="content-card">
        <p>代码阅读练习，不自动判题，不计入正式测评。</p>
        <p v-if="view.exercise.language">{{ view.exercise.language }}</p>
        <pre v-if="view.exercise.starterCode"><code>{{ view.exercise.starterCode }}</code></pre>
        <div v-else-if="view.hasBody" v-html="renderedMarkdown"></div>
        <p v-else>暂未提供起始代码或练习正文。</p>
        <details v-for="(hint, hi) in view.exercise.hints" :key="hi"><summary>提示 {{ hi + 1 }}</summary><p>{{ hint }}</p></details>
      </section>
      <section v-else class="content-card"><div v-if="view.hasBody" v-html="renderedMarkdown"></div><p v-else>暂未提供可阅读的正文或题目。</p></section>
      <div class="regenerate-area"><a-button :loading="regenerating" @click="handleRegenerate">重新生成</a-button></div>
    </template>
  </main>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { marked } from 'marked'
import api from '@/api'
import MermaidDiagram from '@/components/MermaidDiagram.vue'
import { sanitizeHtml } from '@/utils/sanitize'
import { contentView, contentFailure, quizResult, regeneratedTarget } from './generatedContent.js'
import { createAccountGuard } from '@/shared/state/accountScope.js'

const route = useRoute(), router = useRouter(), guard = createAccountGuard()
const content = ref(null), loading = ref(true), regenerating = ref(false), failure = ref(null)
const answers = ref({}), submitted = ref(false)
let generation = 0
const view = computed(() => contentView(content.value))
const result = computed(() => quizResult(view.value.questions, answers.value))
const renderedMarkdown = computed(() => sanitizeHtml(marked(view.value.rawContent)))
const resetPractice = () => { answers.value = {}; submitted.value = false }
const fetchContent = async () => {
  const reading = ++generation, id = route.params.id, contentType = route.query.content_type
  loading.value = true; content.value = null; failure.value = null; resetPractice()
  try {
    const response = await api.content.getDetail(id, { content_type: contentType })
    if (!guard.current() || reading !== generation || id !== route.params.id) return
    content.value = response
  } catch (error) {
    if (guard.current() && reading === generation) failure.value = contentFailure(error)
  } finally {
    if (guard.current() && reading === generation) loading.value = false
  }
}
const handleRegenerate = async () => {
  if (regenerating.value || loading.value) return
  const id = route.params.id, reading = generation
  regenerating.value = true
  try {
    const response = await api.content.regenerate(id, { content_type: content.value?.content_type || route.query.content_type })
    if (!guard.current() || reading !== generation || id !== route.params.id) return
    const target = regeneratedTarget(id, response)
    if (!target.ok) { Message.error('服务未返回可打开的生成内容，请重新读取。'); return }
    if (target.changed) await router.replace(target.to)
    else { content.value = response; resetPractice() }
    Message.success('重新生成已完成')
  } catch {
    if (guard.current() && reading === generation) Message.error('重新生成失败，请稍后重试。')
  } finally {
    if (guard.current()) regenerating.value = false
  }
}
const submitQuiz = () => { submitted.value = true }
watch(() => [route.params.id, route.query.content_type], fetchContent)
onMounted(fetchContent)
onBeforeUnmount(guard.dispose)
</script>

<style scoped>
.generated-content-page { width: min(var(--reading-width), calc(100% - var(--page-gutter) * 2)); margin: auto; padding: var(--space-3) 0; color: var(--ink); }
.content-header { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-2); }
h1 { font-size: var(--text-page); } h2 { font-size: var(--text-card); }
.content-card { padding: var(--space-3); border-radius: var(--radius-panel); background: var(--surface); overflow-wrap: anywhere; }
.quiz-card, .regenerate-area { margin-top: var(--space-2); }
.quiz-feedback { color: var(--ink-secondary); }
pre { max-width: 100%; overflow: auto; padding: var(--space-2); background: var(--surface-muted); }
.content-card :deep(img), .content-card :deep(svg) { max-width: 100%; height: auto; }
.content-card :deep(table) { display: block; max-width: 100%; overflow: auto; }
summary { cursor: pointer; } summary:focus-visible { outline: var(--focus-width) solid var(--action); }
</style>
