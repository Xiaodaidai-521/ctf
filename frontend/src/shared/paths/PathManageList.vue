<template>
  <div class="learning-paths-manage-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">{{ names.paths }}管理</h1>
        <p class="page-subtitle">创建和管理{{ names.paths }}内容</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="goBack">
          <AppIcon name="bi-arrow-left" />
          返回
        </button>
        <button class="btn btn-primary" @click="createPath">
          <AppIcon name="bi-plus-lg" />
          创建{{ names.paths }}
        </button>
      </div>
    </div>

    <!-- 统计只覆盖完整读取的有权航线，不填补缺失字段。 -->
    <div class="stats-grid" :aria-busy="loading">
      <div class="stat-card">
        <div class="stat-icon">
          <AppIcon name="bi-book" />
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ loading ? '读取中' : loadError || !loaded ? '未读取' : stats.total ?? '未提供' }}</div>
          <div class="stat-label">可管理航线</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">
          <AppIcon name="bi-check-circle" />
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ loading ? '读取中' : loadError || !loaded ? '未读取' : stats.published ?? '未提供' }}</div>
          <div class="stat-label">已发布</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">
          <AppIcon name="bi-file-earmark" />
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ loading ? '读取中' : loadError || !loaded ? '未读取' : stats.draft ?? '未提供' }}</div>
          <div class="stat-label">草稿</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">
          <AppIcon name="bi-people" />
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ loading ? '读取中' : loadError || !loaded ? '未读取' : stats.enrolled ?? '未提供' }}</div>
          <div class="stat-label">在学人次</div>
        </div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-group">
        <label class="filter-label">搜索</label>
        <input
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="搜索航线名称..."
        />
      </div>
      <div class="filter-group">
        <label class="filter-label">难度</label>
        <select v-model="filterDifficulty" class="filter-select">
          <option value="">全部</option>
          <option value="AP">入门</option>
          <option value="PR">进阶</option>
          <option value="EX">专家</option>
        </select>
      </div>
      <div class="filter-group">
        <label class="filter-label">状态</label>
        <select v-model="filterStatus" class="filter-select">
          <option value="">全部</option>
          <option value="published">已发布</option>
          <option value="draft">草稿</option>
        </select>
      </div>
      <div class="filter-actions">
        <button class="action-btn btn-secondary" @click="resetFilters">
          <AppIcon name="bi-arrow-counterclockwise" />
          重置
        </button>
        <button class="action-btn btn-secondary" :disabled="loading" @click="loadLearningPaths">
          <AppIcon name="bi-search" />
          重新读取
        </button>
      </div>
    </div>

    <!-- 路径列表 -->
    <div v-if="loading" class="loading-container">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <div v-else-if="loadError" class="empty-state" role="alert">
      <p>{{ loadError }}</p>
      <button class="btn btn-secondary" @click="loadLearningPaths">重新读取</button>
    </div>
    <div v-else-if="loaded && filteredPaths.length === 0" class="empty-state">
      <AppIcon name="bi-inbox" />
      <p>{{ paths.length ? "没有符合当前筛选的航线，可调整筛选条件。" : `暂无可管理的${names.paths}。` }}</p>
      <button class="btn btn-secondary btn-sm" @click="createPath">
        <AppIcon name="bi-plus-lg" />
        创建第一条学习航线
      </button>
    </div>

    <div v-else class="paths-grid">
      <div
        v-for="path in filteredPaths"
        :key="path.id"
        class="path-card"
        
      >
        <div class="path-header">
          <div class="path-badge">
            <AppIcon name="bi-journal-bookmark" />
            <span>{{ getDifficultyLabel(path.difficulty) }}</span>
          </div>
          <span class="path-status" :class="{ 'published': path.is_published }">
            {{ path.is_published === true ? '已发布' : path.is_published === false ? '草稿' : '未提供状态' }}
          </span>
        </div>
        <h3 class="path-title">{{ path.title }}</h3>
        <p class="path-description">{{ path.description }}</p>

        <div class="path-meta">
          <div class="meta-item">
            <AppIcon name="bi-layers" />
            <span>{{ validNumber(path.module_count) ?? '未提供' }} 章节</span>
          </div>
          <div class="meta-item">
            <AppIcon name="bi-clock" />
            <span>{{ validNumber(path.estimated_hours) ?? '未提供' }} 小时</span>
          </div>
          <div class="meta-item">
            <AppIcon name="bi-people" />
            <span>{{ validNumber(path.enrollment_count) ?? '未提供' }} 人在学</span>
          </div>
        </div>

        <div class="path-actions">
          <button class="action-btn btn-secondary" @click="viewPath(path.id)">
            <AppIcon name="bi-eye" />
            查看
          </button>
          <button class="action-btn btn-secondary" @click="editPath(path.id)">
            <AppIcon name="bi-pencil" />
            编辑
          </button>
          <button class="action-btn btn-danger" @click="deletePath(path)">
            <AppIcon name="bi-trash" />
            删除
          </button>
        </div>
      </div>
    </div>

    <!-- 确认删除弹窗 -->
    <div v-if="confirmModalVisible" class="modal-overlay" @click.self="confirmModalVisible = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>确认删除</h3>
          <button class="close-btn" @click="confirmModalVisible = false" aria-label="关闭"><AppIcon name="bi-x-lg" /></button>
        </div>
        <div class="modal-body">
          <p>{{ confirmMessage }}</p>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="confirmModalVisible = false">取消</button>
          <button class="action-btn btn-danger" :disabled="deleting" @click="confirmDelete">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { names } from '@/shared/navigation/names'

import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createAccountGuard } from '@/shared/state/accountScope.js'
import { uiSnapshot } from '@/shared/state/retention.js'
const props = defineProps({ api: { type: Object, required: true }, managementBase: { type: String, default: '/teacher/learning-paths' }, home: { type: String, default: '/teacher' } })
const managementApi = props.api

const router = useRouter()
const route = useRoute()

// 数据
const loading = ref(true)
const loaded = ref(false)
const loadError = ref('')
const deleting = ref(false)
let loadGeneration = 0
let alive = true
const account = createAccountGuard()
const retention = uiSnapshot(`paths:list:${props.managementBase}`)
const saved = retention.read()
onBeforeUnmount(() => {
  retention.write({ search: searchQuery.value, difficulty: filterDifficulty.value, status: filterStatus.value })
  alive = false; account.dispose(); ++loadGeneration; paths.value = []
})
const paths = ref([])
const searchQuery = ref(saved?.search || '')
const filterDifficulty = ref(saved?.difficulty || '')
const presetStatus = value => ['draft', 'published'].includes(value) ? value : ''
const filterStatus = ref(Object.hasOwn(route.query || {}, 'status') ? presetStatus(route.query?.status) : saved?.status || '')
watch(() => route.query?.status, value => { filterStatus.value = presetStatus(value) })

const validNumber = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null
const stats = computed(() => ({
  total: paths.value.length,
  published: paths.value.filter(p => p.is_published === true).length,
  draft: paths.value.filter(p => p.is_published === false).length,
  enrolled: paths.value.every(p => validNumber(p.enrollment_count) !== null)
    ? paths.value.reduce((sum, p) => sum + p.enrollment_count, 0) : null,
}))

// 确认弹窗
const confirmModalVisible = ref(false)
const confirmMessage = ref('')
const deleteTarget = ref(null)

// 计算属性
const filteredPaths = computed(() => {
  let result = paths.value

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(p => 
      String(p.title || '').toLowerCase().includes(query) ||
      String(p.description || '').toLowerCase().includes(query)
    )
  }

  if (filterDifficulty.value) {
    result = result.filter(p => p.difficulty === filterDifficulty.value)
  }

  if (filterStatus.value) {
    result = result.filter(p => 
      filterStatus.value === 'published' ? p.is_published === true : p.is_published === false
    )
  }

  return result
})

// 方法
const loadLearningPaths = async () => {
  const generation = ++loadGeneration
  loading.value = true
  loadError.value = ''
  try {
    const rows = await managementApi.list()
    if (!alive || !account.current() || generation !== loadGeneration) return
    if (!Array.isArray(rows)) throw new Error('Incomplete list')
    paths.value = rows
    loaded.value = true
  } catch {
    if (alive && account.current() && generation === loadGeneration) loadError.value = '航线列表未能完整读取，请重试。'
  } finally {
    if (alive && account.current() && generation === loadGeneration) loading.value = false
  }
}

const createPath = () => {
  router.push(`${props.managementBase}/new`)
}

const editPath = (id) => {
  router.push(`${props.managementBase}/${id}/edit`)
}

const viewPath = (id) => {
  router.push(`/learning-paths/${id}`)
}

const deletePath = (path) => {
  deleteTarget.value = path
  confirmMessage.value = `确定要删除${names.paths}"${path.title}"吗？此操作不可撤销。`
  confirmModalVisible.value = true
}

const confirmDelete = async () => {
  if (!deleteTarget.value || deleting.value) return
  deleting.value = true

  try {
    await managementApi.delete(deleteTarget.value.id)
    if (!alive || !account.current()) return
    await loadLearningPaths()
    if (alive && account.current()) alert(loadError.value ? '删除已完成，但列表读取失败，请重新读取。' : '删除成功')
  } catch (error) {
    if (!alive || !account.current()) return
    console.error('Failed to delete path:', error)
    alert('删除失败')
  } finally {
    if (!alive || !account.current()) return
    deleting.value = false
    confirmModalVisible.value = false
    deleteTarget.value = null
  }
}

const goBack = () => {
  router.push(props.home)
}

const resetFilters = () => {
  searchQuery.value = ''
  filterDifficulty.value = ''
  filterStatus.value = ''
}

const getDifficultyLabel = (difficulty) => {
  const labels = { AP: '入门', PR: '进阶', EX: '专家' }
  return labels[difficulty] || '未标注'
}

// 生命周期
onMounted(() => {
  loadLearningPaths()
})
</script>

<style scoped src="./path-list.css"></style>
