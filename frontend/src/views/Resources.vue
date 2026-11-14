<template>
  <div class="resources-page">
    <header class="page-header">
      <div class="header-content">

        <h1 class="page-title">{{ names.resources }}</h1>
        <p class="page-subtitle">查找文档、视频、报告和学习辅助资料。</p>
      </div>
      <div class="header-actions">
        <router-link to="/resources/topics/data-security" class="btn btn-secondary">数据安全实验</router-link>
        <router-link v-if="isTeacherOrAdmin" class="btn btn-secondary"
          :to="userStore.userInfo?.role === 'teacher' ? '/teacher/knowledge' : '/admin/legal/kb'">
          {{ userStore.userInfo?.role === 'teacher' ? names.knowledge : names.foundation }}
        </router-link>
        <button class="btn btn-secondary" type="button" @click="resetTutorHighlights" v-if="hasAISurfacedResources">
          清除推荐标记
        </button>
        <button class="btn btn-primary" @click="handleUpload" v-if="isTeacherOrAdmin">
        <icon-upload aria-hidden="true" />
        上传资源
      </button>
      </div>
    </header>

    <section class="learning-topics" aria-labelledby="topics-heading">
      <div>
        <h2 id="topics-heading">学习专题</h2>
        <p>数据安全案例：从事实与依据出发，练习发现、复核与决策，再提交结果并复盘。</p>
      </div>
      <router-link class="btn btn-secondary" to="/resources/topics/data-security">进入数据安全案例</router-link>
      <router-link v-if="isTeacherOrAdmin" class="topic-management" :to="userStore.userInfo?.role === 'teacher' ? '/teacher/data-cases' : '/admin/data-cases'">{{ userStore.userInfo?.role === 'admin' ? '监督案例状态' : '管理教学案例' }}</router-link>
    </section>

    <div class="resources-layout">
      <ResourceSidebar @resource-clicked="focusResourceList" />
      <main class="resource-content">
    <div class="filters-section">
      <div class="search-box">
        <input
          v-model="searchQuery"
          type="text"
          aria-label="搜索资源"
          placeholder="搜索资源..."
          @input="handleSearch"
          class="search-input"
        />
      </div>

      <div class="filter-options">
        <div class="filter-group">
          <label>类型：</label>
          <select v-model="selectedType" @change="handleFilter" class="filter-select">
            <option value="">全部</option>
            <option value="document">文档</option>
            <option value="video">视频</option>
            <option value="report">报告</option>
            <option value="zip">压缩包</option>
            <option value="ai_resource">AI资源</option>
          </select>
        </div>

        <div class="filter-group">
          <label>分类：</label>
          <select v-model="selectedCategory" @change="handleFilter" class="filter-select">
            <option value="">全部</option>
            <option value="网络安全">网络安全</option>
            <option value="Web安全">Web安全</option>
            <option value="逆向工程">逆向工程</option>
            <option value="密码学">密码学</option>
            <option value="渗透测试">渗透测试</option>
          </select>
        </div>

        <div class="filter-group">
          <label>排序：</label>
          <select v-model="sortBy" @change="handleFilter" class="filter-select">
            <option value="-created_at">最新</option>
            <option value="-download_count">热门</option>
            <option value="-view_count">最多查看</option>
            <option value="title">名称</option>
          </select>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading-state" role="status">
      <p>正在加载资源…</p>
    </div>

    <div v-else-if="listError" class="empty-state error-state" role="alert">
      <p>{{ listError }}</p>
      <button class="btn" @click="fetchResources">重新加载资源</button>
    </div>

    <div v-else-if="listError" class="empty-state" role="alert">
      <p>{{ listError }}</p>
      <button class="btn btn-secondary" type="button" @click="fetchResources">重试读取资源</button>
    </div>
    <div v-else-if="resources.length === 0" class="empty-state">
      <icon-search class="empty-icon" aria-hidden="true" />
      <h3>暂无资源</h3>
      <p>还没有找到符合条件的资源</p>
    </div>

    <div v-else class="resources-grid">
      <ResourceCard
        v-for="resource in resources"
        :key="resource.id"
        :resource="resource"
        @click="handleResourceClick"
      />
    </div>

    <div class="pagination" v-if="!loading && !listError && totalPages > 1">
      <button
        class="page-btn"
        :disabled="currentPage === 1"
        @click="handlePageChange(currentPage - 1)"
      >
        上一页
      </button>
      <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
      <button
        class="page-btn"
        :disabled="currentPage === totalPages"
        @click="handlePageChange(currentPage + 1)"
      >
        下一页
      </button>
    </div>

      </main>
    </div>

    <ResourceDetailModal
      v-if="selectedResourceId"
      :resourceId="selectedResourceId"
      :highlightResourceId="detailHighlightResourceId"
      @close="handleCloseModal"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { names } from '@/shared/navigation/names'
import api from '@/api'
import ResourceCard from '@/components/ResourceCard.vue'
import ResourceDetailModal from '@/components/ResourceDetailModal.vue'
import ResourceSidebar from '@/components/ResourceSidebar.vue'
import {
  clearRememberedTutorResources,
  loadRememberedTutorResources,
  tutorResourceCenterIds
} from '@/utils/tutorResources'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const resources = ref([])
const loading = ref(false)
const listError = ref('')
let alive = true, resourceRead = 0
onUnmounted(() => { alive = false; ++resourceRead })
const currentPage = ref(1)
const pageSize = ref(12)
const total = ref(null)
const searchQuery = ref('')
const selectedType = ref('')
const selectedCategory = ref('')
const sortBy = ref('-created_at')
const selectedResourceId = ref(null)
const rememberedTutorResources = ref([])
const parsePositiveIds = (value) => {
  const rawItems = Array.isArray(value) ? value : String(value || '').split(',')
  return rawItems
    .map((item) => Number(String(item).trim()))
    .filter((item) => Number.isFinite(item) && item > 0)
}
const highlightResourceId = computed(() => {
  const value = Number(route.query.highlight_resource)
  return Number.isFinite(value) && value > 0 ? value : null
})

const rememberedHighlightIds = computed(() => tutorResourceCenterIds(rememberedTutorResources.value))
const routeHighlightIds = computed(() => [
  ...parsePositiveIds(route.query.highlight_resource),
  ...parsePositiveIds(route.query.highlight_resources)
])
const currentHighlightResourceIds = computed(() => {
  const seen = new Set()
  return [...routeHighlightIds.value, ...rememberedHighlightIds.value].filter((id) => {
    if (seen.has(id)) return false
    seen.add(id)
    return true
  })
})
const hasAISurfacedResources = computed(() => currentHighlightResourceIds.value.length > 0)
const detailHighlightResourceId = computed(() => {
  const selectedId = Number(selectedResourceId.value)
  if (Number.isFinite(selectedId) && currentHighlightResourceIds.value.includes(selectedId)) return selectedId
  return highlightResourceId.value
})

const refreshRememberedTutorResources = () => {
  rememberedTutorResources.value = loadRememberedTutorResources()
}

const isTeacherOrAdmin = computed(() => {
  const role = userStore.userInfo?.role
  return role === 'teacher' || role === 'admin'
})

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))

const fetchResources = async () => {
  if (!alive) return
  const read = ++resourceRead
  loading.value = true
  listError.value = ''
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      ordering: sortBy.value,
    }
    if (searchQuery.value) params.search = searchQuery.value
    if (selectedType.value) params.resource_type = selectedType.value
    if (selectedCategory.value) params.category = selectedCategory.value
    if (highlightResourceId.value) params.highlight_resource = highlightResourceId.value
    if (currentHighlightResourceIds.value.length) params.highlight_resources = currentHighlightResourceIds.value.join(',')

    const data = await api.resource.list(params)
    if (!alive || read !== resourceRead) return
    if (!Array.isArray(data.results)) throw new Error('Incomplete resource response')
    resources.value = data.results
    total.value = typeof data.count === 'number' && Number.isFinite(data.count) && data.count >= 0 ? data.count : null
  } catch (error) {
    if (alive && read === resourceRead) listError.value = '资源列表读取失败，请重试。'
  } finally {
    if (alive && read === resourceRead) loading.value = false
  }
}

const handleSearch = debounce(() => {
  currentPage.value = 1
  fetchResources()
}, 500)

const handleFilter = () => {
  currentPage.value = 1
  fetchResources()
}

const handlePageChange = (page) => {
  currentPage.value = page
  fetchResources()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const focusResourceList = (selection = {}) => {
  if (selection.category) {
    selectedCategory.value = selection.category
    currentPage.value = 1
    fetchResources()
  }
  document.querySelector('.filters-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const handleResourceClick = (resource) => {
  selectedResourceId.value = resource.id
}

const handleCloseModal = () => {
  selectedResourceId.value = null
  if (route.query.resource) {
    const query = { ...route.query }
    delete query.resource
    router.replace({ path: '/resources', query })
  }
  fetchResources()
}

const resetTutorHighlights = () => {
  clearRememberedTutorResources()
  rememberedTutorResources.value = []
  selectedResourceId.value = null
  const query = { ...route.query }
  delete query.highlight_resource
  delete query.highlight_resources
  delete query.resource
  currentPage.value = 1
  Promise.resolve(router.replace({ path: '/resources', query })).finally(() => fetchResources())
}

const handleUpload = () => {
  router.push('/resources/upload')
}

function debounce(fn, delay) {
  let timeoutId
  return function(...args) {
    clearTimeout(timeoutId)
    timeoutId = setTimeout(() => fn.apply(this, args), delay)
  }
}

onMounted(() => {
  refreshRememberedTutorResources()
  if (route.query.resource) {
    selectedResourceId.value = Number(route.query.resource)
  }
  fetchResources()
})

watch(
  () => route.query.resource,
  (resourceId) => {
    selectedResourceId.value = resourceId ? Number(resourceId) : null
  }
)

watch(
  () => [route.query.highlight_resource, route.query.highlight_resources],
  () => {
    refreshRememberedTutorResources()
    currentPage.value = 1
    fetchResources()
  }
)
</script>

<style scoped>
.resources-page { width: min(var(--page-width), calc(100% - var(--page-gutter) * 2)); margin: 0 auto; padding: var(--space-3) 0 var(--space-6); }
.learning-topics { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); padding-block: var(--space-2); border-block: var(--stroke) solid var(--line); }
.learning-topics div { flex: 1; min-width: min(100%, var(--menu-width)); }
.learning-topics h2 { margin: 0; font-size: var(--text-card); }
.learning-topics p { margin: var(--space-1) 0 0; color: var(--ink-secondary); }
.topic-management { color: var(--action); font-size: var(--text-caption); }
.resources-layout { display: block; }
.resource-content { min-width: 0; }
.page-header { display: flex; justify-content: space-between; align-items: start; gap: var(--density-gap); margin-bottom: var(--space-3); }
.header-content { min-width: 0; }
.header-content h1 { margin: 0 0 var(--space-1); font-size: var(--text-page); line-height: var(--leading-tight); }
.header-actions { display: flex; align-items: center; gap: var(--space-1); flex-wrap: wrap; justify-content: end; }
.page-subtitle { max-width: var(--reading-width); color: var(--ink-secondary); margin: 0; }
.filters-section { background: var(--surface); padding: var(--space-3); border-radius: var(--radius-panel); margin-bottom: var(--density-gap); display: grid; gap: var(--space-2); }
.search-box { width: 100%; }
.search-input, .filter-select { min-height: var(--control-height); padding: var(--space-1) var(--space-2); color: var(--ink); background: var(--surface); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); font: inherit; }
.search-input { width: 100%; }
.search-input:hover, .filter-select:hover { border-color: var(--action); }
.filter-options { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.filter-group { display: flex; align-items: center; gap: var(--space-1); }
.filter-group label { font-size: var(--text-caption); color: var(--ink-secondary); }
.filter-select { cursor: pointer; min-width: 0; }
.loading-state, .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: var(--space-6) var(--space-3); text-align: center; color: var(--ink-secondary); background: var(--surface); border-radius: var(--radius-panel); }
.empty-icon { font-size: var(--text-section); margin-bottom: var(--space-2); }
.empty-state h3 { font-size: var(--text-card); margin: 0 0 var(--space-1); color: var(--ink); }
.error-state { background: var(--negative-soft); color: var(--negative); }
.resources-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, var(--menu-width)), 1fr)); gap: var(--density-gap); margin-bottom: var(--space-3); }
.pagination { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: var(--space-2); padding: var(--space-3) 0; }
.page-btn { min-height: var(--control-height); padding: var(--space-1) var(--space-2); color: var(--ink); background: var(--surface); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); font: inherit; cursor: pointer; transition: background var(--motion-fast); }
.page-btn:hover:not(:disabled) { background: var(--surface-hover); }
.page-btn:active:not(:disabled) { background: var(--surface-muted); }
.page-btn:disabled { background: var(--disabled); color: var(--disabled-ink); border-color: var(--line); cursor: not-allowed; }
.page-info { font-size: var(--text-caption); }
.is-compact .page-header { flex-direction: column; }
.is-compact .header-actions { justify-content: start; }
.is-compact .filters-section { padding: var(--space-2); }
.is-compact .filter-options { flex-direction: column; gap: var(--space-2); }
.is-compact .filter-select { flex: 1; }
</style>
