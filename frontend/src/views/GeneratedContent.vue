<template>
  <div class="generated-content-page">
    <div class="container">
      <a-spin :loading="loading">
        <template v-if="view">
          <header class="content-header">
            <div class="title-group">
              <p class="eyebrow">生成内容</p>
              <h1 class="content-title">{{ view.title }}</h1>
              <div class="meta-row">
                <a-tag :color="view.typeColor">{{ view.typeLabel }}</a-tag>
                <span v-if="view.type === 'quiz'" class="meta-note">本地练习，不计入正式测评</span>
                <span v-else-if="view.type === 'exercise'" class="meta-note">不自动判题，提示按需展开</span>
              </div>
            </div>
            <a-button type="primary" :loading="regenerating" :disabled="regenerating" @click="handleRegenerate">
              {{ regenerating ? '正在生成…' : '重新生成' }}
            </a-button>
          </header>

          <p v-if="view.type === 'quiz'" class="page-note">
            这是生成内容的本地练习：提交后只在本页判分，不写入正式测评记录，也不改变能力掌握结论。
          </p>

          <section v-if="view.type === 'tutorial'" class="content-card card-markdown" aria-label="教程正文">
            <div v-if="view.hasBody" v-html="renderedMarkdown"></div>
            <p v-else class="state-note">本教程暂未提供正文内容；不代填讲解，可稍后重新生成。</p>
          </section>

          <section v-else-if="view.type === 'quiz'" class="quiz-area" aria-label="测验">
            <template v-if="view.hasQuestions">
              <article v-for="(q, qi) in view.questions" :key="qi" class="quiz-card">
                <h3 class="quiz-question">{{ qi + 1 }}. {{ q.question }}</h3>
                <a-radio-group v-model="answers[qi]" direction="vertical">
                  <a-radio v-for="(opt, oi) in q.options" :key="oi" :value="oi">{{ opt }}</a-radio>
                </a-radio-group>
                <div v-if="submitted" class="quiz-feedback" :class="feedbackClass(q, qi)">
                  <template v-if="q.answerIndex === null">本题未提供可判定答案，暂不计分。</template>
                  <template v-else-if="answers[qi] === undefined">本题尚未选择。</template>
                  <template v-else-if="answers[qi] === q.answerIndex">回答正确。</template>
                  <template v-else>本题未选对；正确答案：{{ q.options[q.answerIndex] }}</template>
                  <p v-if="q.explanation" class="quiz-explanation">{{ q.explanation }}</p>
                </div>
              </article>
              <div class="quiz-actions">
                <a-button type="primary" :disabled="submitted" @click="submitQuiz">提交答案</a-button>
                <p class="quiz-summary" role="status">{{ submitted ? summary : '选择后提交，仅在本页判分。' }}</p>
              </div>
            </template>
            <p v-else class="state-note">本测验暂未提供题目；不代填题目，也不记为已完成。</p>
          </section>

          <section v-else-if="view.type === 'diagram'" class="content-card" aria-label="图表">
            <MermaidDiagram v-if="view.mermaidCode" :mermaid-code="view.mermaidCode" />
            <p v-else class="state-note">本图表暂未提供 Mermaid 定义；不显示占位图冒充已生成。</p>
          </section>

          <section v-else-if="view.type === 'exercise'" class="exercise-area" aria-label="代码练习">
            <div v-if="view.exercise.starterCode" class="code-card">
              <div class="code-header">
                <span class="code-lang">{{ view.exercise.language || '编程语言未提供' }}</span>
              </div>
              <pre class="code-block"><code>{{ view.exercise.starterCode }}</code></pre>
            </div>
            <p v-else class="state-note">本练习暂未提供初始代码；不代写代码或答案。</p>
            <div v-if="view.exercise.hints.length" class="hints-section">
              <a-collapse>
                <a-collapse-item v-for="(hint, hi) in view.exercise.hints" :key="hi" :header="`提示 ${hi + 1}`">
                  <p>{{ hint }}</p>
                </a-collapse-item>
              </a-collapse>
            </div>
            <p class="page-note">本练习不自动判题；答案与测试用例不在页面展示，请按提示自行验证。</p>
          </section>

          <section v-else class="content-card card-markdown" aria-label="原始内容">
            <p class="state-note">此内容类型暂不能按专门版式显示，下面保留原始正文。</p>
            <div v-if="view.hasBody" v-html="renderedMarkdown"></div>
            <p v-else class="state-note">这份内容暂未提供正文。</p>
          </section>
        </template>

        <div v-else-if="error" class="state-box state-error" role="alert">
          <icon-exclamation-circle aria-hidden="true" />
          <h2>{{ error.title }}</h2>
          <p>{{ error.message }}</p>
          <button type="button" class="btn" @click="retry">
            <icon-refresh aria-hidden="true" />
            重试
          </button>
        </div>

        <div v-else-if="!loading" class="state-box" role="status">
          <p>内容不存在或已被删除</p>
        </div>
      </a-spin>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { marked } from 'marked'
import api from '@/api'
import MermaidDiagram from '@/components/MermaidDiagram.vue'
import { sanitizeHtml } from '@/utils/sanitize'
import { contentFailure, contentView, quizResult, regeneratedTarget } from './generatedContent.js'

const route = useRoute()
const router = useRouter()
const content = ref(null)
const loadedId = ref(null)
const loading = ref(false)
const regenerating = ref(false)
const error = ref(null)
const answers = ref({})
const submitted = ref(false)
let requestVersion = 0

const view = computed(() => (content.value ? contentView(content.value) : null))
const renderedMarkdown = computed(() => {
  if (!view.value?.hasBody) return ''
  return sanitizeHtml(marked(view.value.rawContent))
})
const result = computed(() => quizResult(view.value?.questions || [], answers.value))
const summary = computed(() => result.value.label)

async function fetchContent(id = route.params.id, { force = false } = {}) {
  const target = String(id)
  if (!force && loadedId.value === target && content.value) return
  const version = ++requestVersion
  loading.value = true
  error.value = null
  try {
    const payload = await api.content.getDetail(target)
    if (version !== requestVersion) return
    content.value = payload
    loadedId.value = target
    answers.value = {}
    submitted.value = false
  } catch (failure) {
    if (version !== requestVersion) return
    content.value = null
    loadedId.value = null
    error.value = contentFailure(failure)
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

function retry() {
  fetchContent(route.params.id, { force: true })
}

const handleRegenerate = async () => {
  if (regenerating.value) return
  regenerating.value = true
  try {
    const payload = await api.content.regenerate(route.params.id, {})
    const target = regeneratedTarget(route.params.id, payload)
    if (!target.ok) {
      Message.warning('重新生成返回的内容缺少编号，页面未更新；当前内容已保留。')
      return
    }
    content.value = payload
    answers.value = {}
    submitted.value = false
    if (target.changed) {
      // 后端重新生成会创建新对象：同步真实标识与地址，再由路由参数变化读回。
      await router.replace(target.to)
      Message.success('已生成新版本，地址已更新。')
    } else {
      loadedId.value = String(target.id)
      Message.success('重新生成成功')
    }
  } catch {
    Message.error('重新生成失败，已保留当前内容。')
  } finally {
    regenerating.value = false
  }
}

function feedbackClass(question, qi) {
  if (question.answerIndex === null || answers.value[qi] === undefined) return 'pending'
  return answers.value[qi] === question.answerIndex ? 'correct' : 'incorrect'
}

const submitQuiz = () => {
  submitted.value = true
  if (!result.value.scorable) Message.warning(result.value.label)
  else Message.success(result.value.label)
}

watch(
  () => route.params.id,
  id => {
    if (String(id) !== loadedId.value) fetchContent(id)
  }
)

onMounted(() => fetchContent())
</script>

<style scoped>
.generated-content-page {
  min-height: calc(100vh - var(--space-8));
  background: var(--surface-page);
  padding: var(--space-3) 0 var(--space-6);
}

.container { max-width: var(--reading-width); margin: 0 auto; padding: 0 var(--space-2); }

.content-header {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.title-group { display: grid; gap: var(--space-1); min-width: 0; }

.eyebrow { margin: 0; color: var(--action); font-size: var(--text-caption); font-weight: var(--weight-medium); }

.content-title { font-size: var(--text-page); font-weight: var(--weight-strong); color: var(--ink); margin: 0; line-height: var(--leading-tight); overflow-wrap: anywhere; }

.meta-row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); }

.meta-note, .page-note, .state-note { color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.6; }
.page-note { margin: 0 0 var(--space-2); }

.content-card {
  background: var(--surface);
  border: var(--stroke) solid var(--line);
  border-radius: var(--radius-panel);
  padding: var(--space-3);
}

.card-markdown :deep(h1), .card-markdown :deep(h2) { margin-top: 0; }
.card-markdown :deep(img) { max-width: 100%; height: auto; }

.quiz-area { display: grid; gap: var(--space-2); }

.quiz-card {
  background: var(--surface);
  border: var(--stroke) solid var(--line);
  border-radius: var(--radius-panel);
  padding: var(--space-2);
}

.quiz-question { font-size: var(--text-body); font-weight: var(--weight-medium); margin: 0 0 var(--space-1); }

.quiz-feedback { margin-top: var(--space-1); padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); font-size: var(--text-caption); line-height: 1.6; }
.quiz-feedback.correct { background: var(--positive-soft); color: var(--positive); }
.quiz-feedback.incorrect { background: var(--negative-soft); color: var(--negative); }
.quiz-feedback.pending { background: var(--surface-muted); color: var(--ink-secondary); }
.quiz-explanation { margin: var(--space-1) 0 0; color: var(--ink-secondary); }

.quiz-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.quiz-summary { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }

.exercise-area { display: grid; gap: var(--space-2); }

.code-card {
  background: var(--surface-muted);
  border: var(--stroke) solid var(--line);
  border-radius: var(--radius-panel);
  overflow: hidden;
}
.code-header { padding: var(--space-1) var(--space-2); }
.code-lang { font-size: var(--text-caption); color: var(--ink-muted); }
.code-block { padding: var(--space-2); margin: 0; overflow-x: auto; }
.code-block code { color: var(--ink); font-family: 'Fira Code', monospace; font-size: var(--text-caption); white-space: pre; }

.state-box {
  display: grid;
  justify-items: center;
  gap: var(--space-1);
  padding: var(--space-8) var(--space-2);
  border: var(--stroke) solid var(--line);
  border-radius: var(--radius-panel);
  background: var(--surface);
  color: var(--ink-secondary);
  text-align: center;
}
.state-box h2 { margin: 0; color: var(--ink); font-size: var(--text-section); }
.state-box p { margin: 0; max-width: var(--reading-width); line-height: 1.6; }
.state-error { border-color: var(--negative); background: var(--negative-soft); color: var(--negative); }
.state-error h2 { color: var(--negative); }

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  min-height: var(--control-height);
  padding: 0 var(--space-2);
  border: var(--stroke) solid var(--line-strong);
  border-radius: var(--radius-control);
  background: var(--surface);
  color: var(--ink);
  font: inherit;
  font-size: var(--text-caption);
  cursor: pointer;
}
.btn:hover { border-color: var(--action); color: var(--action); }
.btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }

.is-compact .generated-content-page .content-header { flex-direction: column; align-items: stretch; }
.is-compact .generated-content-page .content-header .arco-btn { width: 100%; }
</style>
