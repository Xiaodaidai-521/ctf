<template>
  <div class="resources-page">
    <header class="page-header">
      <div class="header-content">
        <p class="section-kicker">RESOURCE INDEX / Knowledge Shelf</p>
        <h1 class="page-title">学习资源中心</h1>
        <p class="page-subtitle">把文档、视频、报告、压缩包和 AI 学习辅助资料整理成可检索的训练资料索引。</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" type="button" @click="resetTutorHighlights" v-if="hasAISurfacedResources">
          清除AI推荐状态
        </button>
        <button class="btn btn-primary" @click="handleUpload" v-if="isTeacherOrAdmin">
        <i class="bi bi-upload"></i>
        上传资源
      </button>
      </div>
    </header>

    <div class="resources-layout">
      <ResourceSidebar @resource-clicked="focusResourceList" />
      <main class="resource-content">
    <div class="filters-section">
      <div class="search-box">
        <input
          v-model="searchQuery"
          type="text"
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

    <div v-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>加载资源中...</p>
    </div>

    <div v-else-if="resources.length === 0" class="empty-state">
      <div class="empty-icon">📦</div>
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

    <div class="pagination" v-if="totalPages > 1">
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
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
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
const currentPage = ref(1)
const pageSize = ref(12)
const total = ref(0)
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
  loading.value = true
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
    resources.value = data.results || []
    total.value = data.count || 0
  } catch (error) {
    console.error('获取资源列表失败:', error)
    resources.value = []
  } finally {
    loading.value = false
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
.resources-page {
  width: min(1180px, calc(100% - 40px));
  max-width: none;
  margin: 0 auto;
  padding: 42px 0 72px;
}
.resources-layout{display:block}.resource-content{min-width:0}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 24px;
  margin-bottom: 28px;
}

.header-content h1 {
  margin-top: 6px;
  font-size: 52px;
  line-height: 1;
  font-weight: 950;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.btn-secondary {
  background: rgba(255, 250, 242, 0.82);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.page-subtitle {
  max-width: 620px;
  font-size: 16px;
  line-height: 1.8;
  color: var(--text-secondary);
}

.filters-section {
  background: rgba(255, 250, 242, 0.74);
  padding: 20px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: none;
  margin-bottom: 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.search-box {
  width: 100%;
}

.search-input {
  width: 100%;
  padding: 14px 20px;
  color: var(--text-primary);
  background: rgba(255, 250, 242, 0.82);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 15px;
  transition: all 0.3s;
}

.search-input:focus {
  outline: none;
  border-color: var(--primary-color);
}

.filter-options {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-group label {
  font-size: 14px;
  font-weight: 850;
  color: var(--text-primary);
}

.filter-select {
  padding: 8px 16px;
  color: var(--text-primary);
  background: rgba(255, 250, 242, 0.82);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 14px;
  cursor: pointer;
  min-width: 120px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: var(--text-secondary);
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid var(--bg-paper-2);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.empty-icon {
  font-size: 80px;
  margin-bottom: 24px;
}

.empty-state h3 {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 8px;
}

.empty-state p {
  color: var(--text-secondary);
}

.resources-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 18px;
  margin-bottom: 32px;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  padding: 24px;
}

.page-btn {
  padding: 10px 24px;
  background: rgba(255, 250, 242, 0.82);
  border: 1px solid var(--text-primary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.3s;
}

.page-btn:hover:not(:disabled) {
  background: var(--primary-color);
  color: #fbf7ef;
  border-color: var(--primary-color);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

@media (max-width: 768px) {
  .resources-layout{grid-template-columns:1fr}
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .header-content h1 {
    font-size: 28px;
  }

  .filter-options {
    flex-direction: column;
    gap: 12px;
  }

  .filter-group {
    width: 100%;
  }

  .filter-select {
    flex: 1;
  }

  .resources-grid {
    grid-template-columns: 1fr;
  }
}
</style>
