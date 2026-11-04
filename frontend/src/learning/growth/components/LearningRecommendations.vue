<template>
  <section class="learning-recommendations" aria-labelledby="recommend-heading">
    <header class="section-head">
      <div>
        <h2 id="recommend-heading">学习推荐</h2>
        <p class="section-note">结合学习记录查看推荐、洞察与航线、文章和资源；点击卡片可开启导学，不代表已完成练习或掌握知识。</p>
      </div>
    </header>

    <div class="recommend-grid">
      <section class="panel" aria-labelledby="ai-recommend-heading">
        <h3 id="ai-recommend-heading" class="panel-title">AI 推荐学习</h3>
        <p v-if="loading" class="state-note" role="status">正在读取推荐…</p>
        <p v-else-if="error" class="state-note is-error" role="alert">{{ error }}<button type="button" class="text-action" @click="load">重试</button></p>
        <p v-else-if="!recommendations.length" class="state-note">暂无推荐。</p>
        <ul v-else class="recommend-list">
          <li v-for="item in recommendations" :key="item.id" class="recommend-item">
            <button type="button" class="recommend-main" @click="open(item)">
              <span class="rec-type">{{ typeLabel(item.type) }}</span>
              <strong>{{ dashboardCopy(item.title) }}</strong>
              <span class="rec-reason">{{ dashboardCopy(item.reason) }}</span>
              <span v-if="item.estimated_time || item.expected_gain" class="rec-meta">
                <template v-if="item.estimated_time">约 {{ item.estimated_time }}</template>
                <template v-if="item.expected_gain">收益：{{ item.expected_gain }}</template>
              </span>
            </button>
            <details class="rec-evidence">
              <summary>查看推荐依据</summary>
              <button type="button" class="btn" @click="download(item, `推荐依据-${item.id}.json`)">下载完整记录</button>
            </details>
          </li>
        </ul>
      </section>

      <section class="panel" aria-labelledby="insight-heading">
        <h3 id="insight-heading" class="panel-title">学习洞察</h3>
        <p v-if="insightsLoading" class="state-note" role="status">正在读取洞察…</p>
        <p v-else-if="insightsError" class="state-note is-error" role="alert">{{ insightsError }}<button type="button" class="text-action" @click="loadInsights">重试</button></p>
        <p v-else-if="!insights.length" class="state-note">暂无洞察。</p>
        <ul v-else class="insight-list">
          <li v-for="item in insights" :key="item.id" class="insight-item">
            <span class="insight-dot" :class="`severity-${item.severity || 'info'}`"></span>
            <div class="insight-body">
              <p class="insight-title">{{ dashboardCopy(item.title) }}</p>
              <p v-if="item.description" class="insight-desc">{{ dashboardCopy(item.description) }}</p>
              <details>
                <summary>查看洞察依据</summary>
                <button type="button" class="btn" @click="download(item, `洞察依据-${item.id}.json`)">下载完整记录</button>
              </details>
            </div>
          </li>
        </ul>
      </section>

      <section class="panel" aria-labelledby="reading-heading">
        <h3 id="reading-heading" class="panel-title">{{ names.paths }} · 文章 · 资源</h3>
        <p v-if="readingLoading" class="state-note" role="status">正在读取阅读推荐…</p>
        <p v-else-if="readingError" class="state-note is-error" role="alert">{{ readingError }}</p>
        <p v-else-if="!reading.length" class="state-note">暂无阅读推荐。</p>
        <ul v-else class="reading-list">
          <li v-for="item in reading" :key="item.key">
            <router-link :to="item.link" class="reading-item">
              <span class="reading-source" :class="`source-${item.sourceType}`">{{ item.source }}</span>
              <strong>{{ item.title }}</strong>
              <span class="reading-desc">{{ item.description }}</span>
              <span class="reading-meta">{{ item.meta }}</span>
            </router-link>
          </li>
        </ul>
      </section>
    </div>

    <div v-if="actionMessage" class="action-message" role="status">{{ actionMessage }}</div>
  </section>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'
import { names, renameCopy } from '@/shared/navigation/names'
import { dashboardCopy } from '@/views/dashboardCopy'
import { downloadRecord } from '@/shared/forms/referenceFile'
import { openTutor } from '@/learning/agent/public.js'

const router = useRouter()
const emit = defineEmits(['loaded'])
const recommendations = ref([])
const insights = ref([])
const reading = ref([])
const loading = ref(true)
const insightsLoading = ref(true)
const readingLoading = ref(true)
const error = ref('')
const insightsError = ref('')
const readingError = ref('')
const actionMessage = ref('')

const TYPE_LABELS = { onboarding: '画像引导', weakness_fix: '短板练习', strength: '优势巩固', next_step: '下一步', goal_aligned: '目标对齐', exploration: '探索' }
const typeLabel = value => TYPE_LABELS[value] || '学习建议'
const normalizeArray = value => (Array.isArray(value) ? value : (value?.results || []))
const pickFirst = (items, count) => normalizeArray(items).filter(Boolean).slice(0, count)
const trimText = (text, fallback = '') => {
  const value = String(text || fallback || '').replace(/\s+/g, ' ').trim()
  return value.length > 58 ? `${value.slice(0, 58)}...` : value
}
const download = (item, filename) => downloadRecord(item, filename)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.learningAgent.recommend()
    if (Array.isArray(data?.recommendations)) {
      recommendations.value = data.recommendations.map((item, index) => ({ id: item.id ?? index + 1, ...item }))
    } else if (data?.recommendation) {
      recommendations.value = [{ id: 1, type: 'recommendation', title: '学习推荐', reason: String(data.recommendation) }]
    } else {
      recommendations.value = normalizeArray(data)
    }
  } catch {
    recommendations.value = []
    error.value = '学习推荐暂时未能读取，请重试。'
  } finally {
    loading.value = false
    // 同一份推荐只请求一次：总览的“下一步”直接使用这里的结果。
    emit('loaded', recommendations.value)
  }
}

async function loadInsights() {
  insightsLoading.value = true
  insightsError.value = ''
  try {
    insights.value = normalizeArray(await api.analytics.insights()).slice(0, 5)
  } catch {
    insights.value = []
    insightsError.value = '学习洞察暂时未能读取，请重试。'
  } finally {
    insightsLoading.value = false
  }
}

async function loadReading() {
  readingLoading.value = true
  readingError.value = ''
  try {
    const [paths, articles, resources] = await Promise.all([
      api.learningPaths.list({ page_size: 3 }),
      api.article.recommend({ limit: 3 }),
      api.resource.list({ page_size: 3, ordering: '-view_count' }),
    ])
    const pathItems = pickFirst(paths, 3).map(item => ({
      key: `path-${item.id}`, source: names.paths, sourceType: 'path', title: item.title,
      description: trimText(item.description, renameCopy('系统学习路径内容')),
      meta: item.difficulty_display || item.difficulty || '路径', link: `/learning-paths/${item.id}`,
    }))
    const articleItems = pickFirst(articles, 3).map(item => ({
      key: `article-${item.id}`, source: '社区', sourceType: 'community', title: item.title,
      description: trimText(item.summary || item.content, item.title),
      meta: item.category_name || '文章', link: `/community/article/${item.id}`,
    }))
    const resourceItems = pickFirst(resources, 3).map(item => ({
      key: `resource-${item.id}`, source: names.resources, sourceType: 'resource', title: item.title,
      description: trimText(item.description, '推荐学习资源'),
      meta: item.resource_type_display || item.category || '资源', link: `/resources?resource=${item.id}`,
    }))
    // 三类各保一条，再补足到三条；不按接口顺序吞掉某一类。
    const first = [pathItems[0], articleItems[0], resourceItems[0]].filter(Boolean)
    const rest = [...pathItems, ...articleItems, ...resourceItems].filter(item => !first.some(selected => selected.key === item.key))
    reading.value = [...first, ...rest].slice(0, 3)
  } catch {
    reading.value = []
    readingError.value = '阅读推荐暂时未能读取；航线、文章与资源各自的失败不会被当成空目录。'
  } finally {
    readingLoading.value = false
  }
}

// 推荐卡片以“唤起导学”为默认动作；有明确 action_link 时按原链接进入。
async function open(item) {
  if (item?.action_link) {
    router.push(item.action_link)
    return
  }
  const prompt = [item?.title, item?.reason].filter(Boolean).join('：')
  try {
    await openTutor(router, { prompt })
    actionMessage.value = '已打开导学并带上这条推荐作为上下文。'
  } catch {
    actionMessage.value = '导学入口暂不可用；请从导航进入智航。'
  }
}

onMounted(() => {
  load()
  loadInsights()
  loadReading()
})
defineExpose({ load, loadInsights, loadReading, open, recommendations, insights, reading, error, insightsError, readingError })
</script>
<style scoped>
.learning-recommendations { display: grid; gap: var(--space-2); }
.section-head h2 { margin: 0 0 var(--space-1); font-size: var(--text-section); }
.section-note { margin: 0; max-width: var(--reading-width); color: var(--ink-secondary); font-size: var(--text-caption); }
.recommend-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-2); align-items: start; }
.panel { min-width: 0; padding: var(--space-2); border-radius: var(--radius-panel); background: var(--surface); }
.panel-title { margin: 0 0 var(--space-2); font-size: var(--text-card); }
.state-note { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.state-note.is-error { background: var(--negative-soft); color: var(--negative); }
.text-action { margin-left: var(--space-1); padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; cursor: pointer; }
.recommend-list, .insight-list, .reading-list { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.recommend-item { display: grid; gap: var(--space-1); padding: var(--space-1); border-radius: var(--radius-control); background: var(--surface-muted); }
.recommend-main { display: grid; gap: 2px; width: 100%; padding: 0; border: 0; background: transparent; color: var(--ink); font: inherit; text-align: left; cursor: pointer; }
.rec-type { justify-self: start; padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--action-soft); color: var(--action); font-size: var(--text-caption); }
.rec-reason { color: var(--ink-secondary); font-size: var(--text-caption); }
.rec-meta { display: flex; flex-wrap: wrap; gap: var(--space-1); color: var(--ink-muted); font-size: var(--text-caption); }
.rec-evidence summary, .insight-item summary { min-height: var(--control-height); display: flex; align-items: center; color: var(--ink-muted); font-size: var(--text-caption); cursor: pointer; }
.insight-item { display: flex; gap: var(--space-1); padding: var(--space-1) 0; border-top: var(--stroke) solid var(--line); }
.insight-item:first-child { border-top: 0; }
.insight-dot { width: var(--space-1); height: var(--space-1); margin-top: var(--space-1); border-radius: 50%; background: var(--action); flex: none; }
.insight-dot.severity-warning { background: var(--warning); }
.insight-dot.severity-danger { background: var(--negative); }
.insight-body { min-width: 0; }
.insight-title { margin: 0; font-weight: var(--weight-strong); font-size: var(--text-caption); }
.insight-desc { margin: 2px 0 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.reading-item { display: grid; gap: 2px; padding: var(--space-1) 0; border-top: var(--stroke) solid var(--line); color: var(--ink); text-decoration: none; }
.reading-list li:first-child .reading-item { border-top: 0; }
.reading-source { justify-self: start; padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.reading-desc, .reading-meta { color: var(--ink-secondary); font-size: var(--text-caption); }
.btn { display: inline-flex; align-items: center; min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.action-message { padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--action-soft); color: var(--action); font-size: var(--text-caption); }
.is-compact .recommend-grid { grid-template-columns: minmax(0, 1fr); }
.recommend-main:focus-visible, .btn:focus-visible, .text-action:focus-visible, .reading-item:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
