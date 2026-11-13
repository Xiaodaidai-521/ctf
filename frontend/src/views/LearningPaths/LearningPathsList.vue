<template>
  <div class="paths-page">
    <div class="page-header">
      <div class="header-copy">
        <p class="eyebrow">学习面 · {{ names.paths }}</p>
        <h1>{{ names.paths }}</h1>
        <p class="subtitle">选一条航线查看章节安排；进入详情不会自动加入，确认加入后才开始记录进度。</p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn btn-secondary" :disabled="loading" @click="reload">
          <icon-refresh aria-hidden="true" /> 刷新
        </button>
      </div>
    </div>

    <section class="stats-strip" aria-label="航线概览">
      <div class="stat-tile">
        <span class="stat-label">航线总数</span>
        <strong class="stat-value">{{ stats.totalLabel }}</strong>
        <span class="stat-note">{{ stats.countKnown ? '来自接口计数' : '接口未返回总数，仅显示已加载' }}</span>
      </div>
      <div class="stat-tile">
        <span class="stat-label">当前已加载</span>
        <strong class="stat-value">{{ stats.loaded }}</strong>
        <span class="stat-note">{{ stats.partial ? '还有更多，可继续加载' : '已加载全部可见航线' }}</span>
      </div>
      <div class="stat-tile">
        <span class="stat-label">在学人数</span>
        <strong class="stat-value">{{ stats.enrolledLabel }}</strong>
        <span class="stat-note">{{ stats.enrolledKnown ? '按接口返回累加' : '接口未返回该字段' }}</span>
      </div>
    </section>

    <section class="filter-bar" aria-label="筛选航线">
      <label class="field">
        <span>搜索</span>
        <input v-model="searchQuery" type="search" placeholder="搜索航线名称或简介…" autocomplete="off" />
      </label>
      <label class="field">
        <span>难度</span>
        <select v-model="filterDifficulty">
          <option value="">全部</option>
          <option value="AP">入门</option>
          <option value="PR">进阶</option>
          <option value="EX">专家</option>
        </select>
      </label>
      <div class="filter-actions">
        <button type="button" class="btn btn-secondary" @click="resetFilters">重置</button>
        <button type="button" class="btn btn-primary" :disabled="loading" @click="reload">搜索</button>
      </div>
      <p v-if="searchQuery || filterDifficulty" class="filter-note">
        搜索与难度筛选作用于当前已加载的 {{ stats.loaded }} 条{{ stats.partial ? '；更多航线请继续加载后再筛选' : '' }}。
      </p>
    </section>

    <div v-if="loading" class="state-box" aria-live="polite">
      <div class="spinner"></div>
      <p>正在读取{{ names.paths }}…</p>
    </div>

    <div v-else-if="error" class="state-box state-error" role="alert">
      <icon-exclamation-circle aria-hidden="true" />
      <h2>航线暂时无法读取</h2>
      <p>{{ error }}</p>
      <button type="button" class="btn btn-secondary" @click="reload">重试</button>
    </div>

    <template v-else>
      <div v-if="!filteredPaths.length" class="state-box state-empty">
        <icon-archive aria-hidden="true" />
        <p v-if="cards.length">当前筛选下没有航线；可重置搜索与难度。</p>
        <p v-else>暂无可选航线。</p>
        <button v-if="cards.length" type="button" class="btn btn-secondary" @click="resetFilters">重置筛选</button>
      </div>

      <div v-else class="paths-grid">
        <article v-for="path in filteredPaths" :key="path.id" class="path-card">
          <header class="path-head">
            <span class="difficulty-tag" :class="`level-${path.difficulty || 'na'}`">{{ path.difficultyLabel }}</span>
            <span v-if="!path.published" class="draft-tag">未发布</span>
          </header>
          <h2 class="path-title">{{ path.title }}</h2>
          <p v-if="path.description" class="path-description">{{ path.description }}</p>
          <dl class="path-meta">
            <div><dt>章节</dt><dd>{{ path.chapterCount === null ? '未提供' : `${path.chapterCount} 章` }}</dd></div>
            <div><dt>实验</dt><dd>{{ path.labCount === null ? '未提供' : `${path.labCount} 个` }}</dd></div>
            <div><dt>时长</dt><dd>{{ path.hoursLabel }}</dd></div>
            <div><dt>在学</dt><dd>{{ path.enrolledLabel }}</dd></div>
          </dl>
          <div class="path-actions">
            <button type="button" class="btn btn-primary" @click="viewPath(path.id)">
              <icon-play-arrow aria-hidden="true" /> 查看详情
            </button>
            <span class="action-note">进入详情后再确认加入</span>
          </div>
        </article>
      </div>

      <div v-if="cards.length" class="list-footer">
        <p class="loaded-note">
          已加载 {{ stats.loaded }}{{ stats.countKnown ? ` / ${stats.total} 条` : ' 条' }}。
        </p>
        <button v-if="stats.hasNext" type="button" class="btn btn-secondary" :disabled="loadingMore" @click="loadMore">
          {{ loadingMore ? '正在加载…' : '加载更多' }}
        </button>
        <p v-else class="loaded-note">已到列表末尾。</p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { createAccountGuard } from '@/shared/state/accountScope.js'
import { useRoute, useRouter } from 'vue-router'
import { names } from '@/shared/navigation/names'
import { pathsApi } from '@/learning/paths/api.js'
import { asList } from '@/learning/contracts.js'
import { safeError, listStats, pathCardView } from '@/learning/paths/presentation.js'

const router = useRouter()
const route = useRoute()
const guard = createAccountGuard()
onBeforeUnmount(guard.dispose)
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')
const cards = ref([])
const stats = ref(listStats([], 1))
const page = ref(1)
// 搜索/难度写回路由查询，返回列表时保留筛选与分页入口（不写入浏览器持久缓存）。
const listQuery = value => typeof value === 'string' ? value : ''
const searchQuery = ref(listQuery(route.query.search))
const filterDifficulty = ref(listQuery(route.query.difficulty))
let generation = 0
watch([searchQuery, filterDifficulty], ([search, difficulty]) => {
  const query = { ...route.query }
  if (search.trim()) query.search = search.trim(); else delete query.search
  if (difficulty) query.difficulty = difficulty; else delete query.difficulty
  if (JSON.stringify(query) !== JSON.stringify(route.query)) router.replace({ path: route.path, query, hash: route.hash })
})

// 返回/前进或书签直达时同步输入框；不把筛选写入持久缓存。
watch(
  () => [route.query.search, route.query.difficulty],
  ([search, difficulty]) => {
    const nextSearch = listQuery(search)
    const nextDifficulty = listQuery(difficulty)
    if (searchQuery.value !== nextSearch) searchQuery.value = nextSearch
    if (filterDifficulty.value !== nextDifficulty) filterDifficulty.value = nextDifficulty
  }
)

const filteredPaths = computed(() => {
  let result = cards.value
  const query = searchQuery.value.trim().toLowerCase()
  if (query) result = result.filter(item => item.title.toLowerCase().includes(query) || item.description.toLowerCase().includes(query))
  if (filterDifficulty.value) result = result.filter(item => item.difficulty === filterDifficulty.value)
  return result
})

function assertPayload(payload) {
  if (!Array.isArray(payload) && !Array.isArray(payload?.results)) throw new Error('Invalid list response')
}

function applyPayload(payload, targetPage) {
  assertPayload(payload)
  stats.value = listStats(payload, targetPage)
  cards.value = stats.value.items.map(pathCardView)
  page.value = targetPage
}

async function load(targetPage = 1) {
  const version = ++generation
  error.value = ''
  if (targetPage === 1) loading.value = true
  else loadingMore.value = true
  try {
    const payload = await pathsApi.list()
    if (!guard.current() || version !== generation) return
    applyPayload(payload, 1)
  } catch (failure) {
    if (!guard.current() || version !== generation) return
    error.value = safeError(failure, '航线暂时未能读取，请稍后重试。')
    if (targetPage === 1) cards.value = []
  } finally {
    if (guard.current() && version === generation) {
      loading.value = false
      loadingMore.value = false
    }
  }
}

// 后端默认分页 20 条；继续读取同一既有路径的下一页，不拼接本页 length 冒充全量。
async function loadMore() {
  const version = ++generation
  loadingMore.value = true
  error.value = ''
  try {
    const payload = await pathsApi.list({ page: page.value + 1 })
    if (!guard.current() || version !== generation) return
    assertPayload(payload)
    const nextStats = listStats(payload, page.value + 1)
    const fresh = nextStats.items.filter(item => !cards.value.some(card => card.id === item.id))
    if (!fresh.length && nextStats.hasNext) throw new Error('Repeated list page')
    const merged = [...cards.value, ...fresh.map(pathCardView)]
    const seen = new Set()
    cards.value = merged.filter(item => {
      if (item.id === null || seen.has(item.id)) return false
      seen.add(item.id)
      return true
    })
    page.value += 1
    stats.value = { ...nextStats, loaded: cards.value.length, totalLabel: nextStats.countKnown ? String(nextStats.total) : `已加载 ${cards.value.length}` }
  } catch (failure) {
    if (!guard.current() || version !== generation) return
    error.value = safeError(failure, '更多航线暂时未能读取，请稍后重试。')
  } finally {
    if (guard.current() && version === generation) loadingMore.value = false
  }
}

function reload() {
  load(1)
}

function resetFilters() {
  searchQuery.value = ''
  filterDifficulty.value = ''
}

function viewPath(id) {
  if (id === null) return
  router.push(`/learning-paths/${id}`)
}

onMounted(() => load(1))
</script>

<style scoped>
.paths-page { display: grid; gap: var(--space-3); width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: var(--space-4) auto var(--space-8); }
.page-header { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--space-2); }
.eyebrow { margin: 0 0 var(--space-1); color: var(--action); font-size: var(--text-caption); font-weight: var(--weight-medium); }
h1 { margin: 0; font-size: var(--text-page); line-height: var(--leading-tight); }
.subtitle { margin: var(--space-1) 0 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.header-actions { display: flex; gap: var(--space-1); }
.stats-strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-2); }
.stat-tile { display: grid; gap: calc(var(--space-1) / 2); padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.stat-label { color: var(--ink-muted); font-size: var(--text-caption); }
.stat-value { font-size: var(--text-section); line-height: var(--leading-tight); overflow-wrap: anywhere; }
.stat-note { color: var(--ink-muted); font-size: var(--text-caption); line-height: 1.5; }
.filter-bar { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--space-2); padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.field { display: grid; gap: calc(var(--space-1) / 2); min-width: var(--panel-width); color: var(--ink-secondary); font-size: var(--text-caption); }
.field input, .field select { min-height: var(--control-height); padding: 0 var(--space-1); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; }
.filter-actions { display: flex; gap: var(--space-1); }
.filter-note { flex-basis: 100%; margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.paths-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--panel-width), 1fr)); gap: var(--space-2); }
.path-card { display: grid; gap: var(--space-1); align-content: start; min-width: 0; padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-raised); }
.path-head { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); }
.difficulty-tag { padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); color: var(--ink-secondary); font-size: var(--text-caption); }
.level-AP { border-color: var(--positive); color: var(--positive); }
.level-PR { border-color: var(--action); color: var(--action); }
.level-EX { border-color: var(--warning); color: var(--warning); }
.draft-tag { padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-muted); font-size: var(--text-caption); }
.path-title { margin: 0; font-size: var(--text-card); line-height: var(--leading-tight); overflow-wrap: anywhere; }
.path-description { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.6; overflow-wrap: anywhere; }
.path-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: calc(var(--space-1) / 2) var(--space-2); margin: 0; }
.path-meta div { display: flex; justify-content: space-between; gap: var(--space-1); min-width: 0; font-size: var(--text-caption); }
.path-meta dt { color: var(--ink-muted); }
.path-meta dd { margin: 0; color: var(--ink-secondary); text-align: right; overflow-wrap: anywhere; }
.path-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1) var(--space-2); margin-top: var(--space-1); }
.action-note { color: var(--ink-muted); font-size: var(--text-caption); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1); min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn:hover:not(:disabled) { border-color: var(--action); color: var(--action); }
.btn-primary:hover:not(:disabled) { background: var(--action-hover); border-color: var(--action-hover); color: var(--on-action); }
.btn:active:not(:disabled) { background: var(--surface-muted); }
.btn-primary:active:not(:disabled) { background: var(--action-pressed); border-color: var(--action-pressed); }
.btn:disabled { border-color: var(--line); background: var(--surface-muted); color: var(--ink-muted); cursor: not-allowed; }
.btn:focus-visible, input:focus-visible, select:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.state-box { display: grid; justify-items: center; gap: var(--space-1); padding: var(--space-6) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); text-align: center; color: var(--ink-secondary); }
.state-box p { margin: 0; }
.state-error { border-color: var(--negative); background: var(--negative-soft); color: var(--negative); }
.state-empty { color: var(--ink-muted); }
.spinner { width: var(--control-height); height: var(--control-height); border: var(--focus-width) solid var(--line); border-top-color: var(--action); border-radius: var(--radius-pill); animation: spin calc(var(--motion-slow) * 4) linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.list-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.loaded-note { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.is-compact .paths-page .stats-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.is-compact .paths-page .paths-grid { grid-template-columns: minmax(0, 1fr); }
.is-compact .paths-page .field { min-width: 100%; }
.is-compact .paths-page .filter-actions { flex: 1; }
.is-compact .paths-page .list-footer { align-items: stretch; }
@media (prefers-reduced-motion: reduce) {
  .spinner { animation: none; }
}
</style>
