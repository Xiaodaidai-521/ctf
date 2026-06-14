<template>
  <div class="resources-page">
    <header class="page-header">
      <div class="header-content">
        <h1 class="page-title">学习资源中心</h1>
        <p class="page-subtitle">探索丰富的学习资料，提升你的技能</p>
      </div>
      <button class="btn btn-primary" @click="handleUpload" v-if="isTeacherOrAdmin">
        <span>➕</span> 上传资源
      </button>
    </header>

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

    <ResourceDetailModal
      v-if="selectedResourceId"
      :resourceId="selectedResourceId"
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
</script>

<style scoped>
.resources-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 32px 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.header-content h1 {
  font-size: 36px;
  font-weight: 800;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.page-subtitle {
  font-size: 16px;
  color: var(--text-secondary);
}

.filters-section {
  background: white;
  padding: 24px;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
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
  border: 2px solid #e8e8e8;
  border-radius: var(--radius-md);
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
  font-weight: 600;
  color: var(--text-primary);
}

.filter-select {
  padding: 8px 16px;
  border: 1px solid #d9d9d9;
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
  border: 4px solid #f0f0f0;
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
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 24px;
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
  background: white;
  border: 1px solid #d9d9d9;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.3s;
}

.page-btn:hover:not(:disabled) {
  background: var(--primary-color);
  color: white;
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
