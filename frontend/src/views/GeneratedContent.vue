<template>
  <div class="generated-content-page">
    <div class="container">
      <a-spin :loading="loading">
        <template v-if="content">
          <div class="content-header">
            <h1 class="content-title">{{ content.title }}</h1>
            <a-tag :color="typeColor">{{ typeLabel }}</a-tag>
          </div>

          <!-- tutorial: Markdown 渲染 -->
          <div v-if="content.type === 'tutorial'" class="content-card card-markdown">
            <div v-html="renderedMarkdown"></div>
          </div>

          <!-- quiz: 交互答题 -->
          <div v-else-if="content.type === 'quiz'" class="quiz-area">
            <div v-for="(q, qi) in questions" :key="qi" class="quiz-card">
              <h3 class="quiz-question">{{ qi + 1 }}. {{ q.question }}</h3>
              <a-radio-group v-model="answers[qi]" direction="vertical">
                <a-radio v-for="(opt, oi) in q.options" :key="oi" :value="oi">{{ opt }}</a-radio>
              </a-radio-group>
              <div v-if="submitted && answers[qi] !== undefined" class="quiz-feedback" :class="{ correct: answers[qi] === q.answer }">
                {{ answers[qi] === q.answer ? '回答正确！' : `正确答案：${q.options[q.answer]}` }}
              </div>
            </div>
            <a-button type="primary" @click="submitQuiz" :disabled="submitted">提交答案</a-button>
          </div>

          <!-- diagram: Mermaid 渲染 -->
          <div v-else-if="content.type === 'diagram'" class="content-card">
            <MermaidDiagram :code="content.body || content.diagram_code || ''" />
          </div>

          <!-- exercise: 代码 + 折叠提示 -->
          <div v-else-if="content.type === 'exercise'" class="exercise-area">
            <div class="code-card">
              <div class="code-header">
                <span class="code-lang">{{ content.language || 'python' }}</span>
              </div>
              <pre class="code-block"><code>{{ content.code || content.body }}</code></pre>
            </div>
            <div v-if="content.hints && content.hints.length" class="hints-section">
              <a-collapse>
                <a-collapse-item v-for="(hint, hi) in content.hints" :key="hi" :header="`提示 ${hi + 1}`">
                  <p>{{ hint }}</p>
                </a-collapse-item>
              </a-collapse>
            </div>
          </div>

          <!-- 未知类型回退 -->
          <div v-else class="content-card">
            <div v-html="renderedMarkdown"></div>
          </div>

          <div class="regenerate-area">
            <a-button type="primary" :loading="regenerating" @click="handleRegenerate">重新生成</a-button>
          </div>
        </template>

        <div v-else-if="!loading" class="empty-state">
          <p>内容不存在或已被删除</p>
        </div>
      </a-spin>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { marked } from 'marked'
import api from '@/api'
import MermaidDiagram from '@/components/MermaidDiagram.vue'

const route = useRoute()
const content = ref(null)
const loading = ref(false)
const regenerating = ref(false)
const answers = ref({})
const submitted = ref(false)

const questions = computed(() => {
  if (!content.value || content.value.type !== 'quiz') return []
  const qs = content.value.questions || content.value.body?.questions || []
  return qs
})

const typeLabel = computed(() => {
  const map = { tutorial: '教程', quiz: '测验', diagram: '图表', exercise: '练习' }
  return map[content.value?.type] || '内容'
})

const typeColor = computed(() => {
  const map = { tutorial: 'blue', quiz: 'orange', diagram: 'purple', exercise: 'green' }
  return map[content.value?.type] || 'gray'
})

const renderedMarkdown = computed(() => {
  const body = content.value?.body
  if (!body) return ''
  return typeof body === 'string' ? marked(body) : marked(JSON.stringify(body))
})

const fetchContent = async () => {
  loading.value = true
  try {
    content.value = await api.content.getDetail(route.params.id)
  } catch {
    content.value = null
  } finally {
    loading.value = false
  }
}

const handleRegenerate = async () => {
  regenerating.value = true
  try {
    const result = await api.content.regenerate(route.params.id, {})
    content.value = result
    answers.value = {}
    submitted.value = false
    Message.success('重新生成成功')
  } catch {
    Message.error('重新生成失败')
  } finally {
    regenerating.value = false
  }
}

const submitQuiz = () => {
  submitted.value = true
  const correct = questions.value.filter((q, i) => answers.value[i] === q.answer).length
  Message.success(`答题结果：${correct}/${questions.value.length} 正确`)
}

onMounted(fetchContent)
</script>

<style scoped>
.generated-content-page {
  min-height: calc(100vh - 64px);
  background: #f6f7f8;
  padding: 24px 0;
}

.container { max-width: 900px; margin: 0 auto; padding: 0 16px; }

.content-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 24px; }

.content-title { font-size: 24px; font-weight: 600; color: #1f1f1f; margin: 0; }

.content-card {
  background: white;
  border-radius: 10px;
  padding: 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}

.card-markdown :deep(h1), .card-markdown :deep(h2) { margin-top: 0; }

.quiz-card {
  background: white;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}

.quiz-question { font-size: 16px; font-weight: 500; margin: 0 0 12px; }

.quiz-feedback { margin-top: 10px; padding: 8px 12px; border-radius: 6px; font-size: 13px; }
.quiz-feedback.correct { background: #f6ffed; color: #52c41a; }
.quiz-feedback:not(.correct) { background: #fff1f0; color: #f5222d; }

.code-card {
  background: #1e1e1e;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 16px;
}

.code-header { padding: 8px 16px; background: #333; }

.code-lang { font-size: 12px; color: #ccc; }

.code-block { padding: 16px; margin: 0; overflow-x: auto; }

.code-block code { color: #d4d4d4; font-family: 'Fira Code', monospace; font-size: 13px; white-space: pre; }

.regenerate-area { margin-top: 24px; text-align: center; }

.empty-state { text-align: center; padding: 80px 0; color: #9499a0; }
</style>
