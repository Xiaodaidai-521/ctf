<template>
  <div class="learning-paths-manage-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">学习路径管理</h1>
        <p class="page-subtitle">创建和管理学习路径内容</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" @click="goBack">
          <i class="bi bi-arrow-left"></i>
          返回
        </button>
        <button class="btn btn-primary" @click="createPath">
          <i class="bi bi-plus-lg"></i>
          创建路径
        </button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon" style="background: #e6f7ff; color: #1890ff;">
          <i class="bi bi-book"></i>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">总路径数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: #f6ffed; color: #52c41a;">
          <i class="bi bi-check-circle"></i>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.published }}</div>
          <div class="stat-label">已发布</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: #fff7e6; color: #fa8c16;">
          <i class="bi bi-file-earmark"></i>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.draft }}</div>
          <div class="stat-label">草稿</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background: #fff1f0; color: #ff4d4f;">
          <i class="bi bi-people"></i>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.enrolled }}</div>
          <div class="stat-label">学习人数</div>
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
          placeholder="搜索路径名称..."
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
          <i class="bi bi-arrow-counterclockwise"></i>
          重置
        </button>
        <button class="action-btn btn-primary" @click="loadLearningPaths">
          <i class="bi bi-search"></i>
          搜索
        </button>
      </div>
    </div>

    <!-- 路径列表 -->
    <div v-if="loading" class="loading-container">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <div v-else-if="filteredPaths.length === 0" class="empty-state">
      <i class="bi bi-inbox"></i>
      <p>暂无学习路径</p>
      <button class="btn btn-primary btn-sm" @click="createPath">
        <i class="bi bi-plus-lg"></i>
        创建第一个路径
      </button>
    </div>

    <div v-else class="paths-grid">
      <div
        v-for="path in filteredPaths"
        :key="path.id"
        class="path-card"
        :style="{ '--path-color': path.color }"
      >
        <div class="path-header">
          <div class="path-badge">
            <i class="bi bi-journal-bookmark"></i>
            <span>{{ getDifficultyLabel(path.difficulty) }}</span>
          </div>
          <span class="path-status" :class="{ 'published': path.is_published }">
            {{ path.is_published ? '已发布' : '草稿' }}
          </span>
        </div>
        <h3 class="path-title">{{ path.title }}</h3>
        <p class="path-description">{{ path.description }}</p>

        <div class="path-meta">
          <div class="meta-item">
            <i class="bi bi-layers"></i>
            <span>{{ path.module_count || 0 }} 章节</span>
          </div>
          <div class="meta-item">
            <i class="bi bi-clock"></i>
            <span>{{ path.estimated_hours }} 小时</span>
          </div>
          <div class="meta-item">
            <i class="bi bi-people"></i>
            <span>{{ path.enrollment_count || 0 }} 人在学</span>
          </div>
        </div>

        <div class="path-actions">
          <button class="action-btn btn-secondary" @click="viewPath(path.id)">
            <i class="bi bi-eye"></i>
            查看
          </button>
          <button class="action-btn btn-primary" @click="editPath(path.id)">
            <i class="bi bi-pencil"></i>
            编辑
          </button>
          <button class="action-btn btn-danger" @click="deletePath(path)">
            <i class="bi bi-trash"></i>
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
          <button class="close-btn" @click="confirmModalVisible = false">✕</button>
        </div>
        <div class="modal-body">
          <p>{{ confirmMessage }}</p>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="confirmModalVisible = false">取消</button>
          <button class="action-btn btn-danger" @click="confirmDelete">确认删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'

const router = useRouter()

// 数据
const loading = ref(false)
const paths = ref([])
const searchQuery = ref('')
const filterDifficulty = ref('')
const filterStatus = ref('')

// 统计
const stats = reactive({
  total: 0,
  published: 0,
  draft: 0,
  enrolled: 0,
})

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
      p.title.toLowerCase().includes(query) ||
      p.description.toLowerCase().includes(query)
    )
  }

  if (filterDifficulty.value) {
    result = result.filter(p => p.difficulty === filterDifficulty.value)
  }

  if (filterStatus.value) {
    result = result.filter(p => 
      filterStatus.value === 'published' ? p.is_published : !p.is_published
    )
  }

  return result
})

// 方法
const loadLearningPaths = async () => {
  loading.value = true
  try {
    const res = await api.learningPaths.list()
    paths.value = res.results || res || []

    // 计算统计
    stats.total = paths.value.length
    stats.published = paths.value.filter(p => p.is_published).length
    stats.draft = paths.value.filter(p => !p.is_published).length
    stats.enrolled = paths.value.reduce((sum, p) => sum + (p.enrollment_count || 0), 0)
  } catch (error) {
    console.error('Failed to load learning paths:', error)
  } finally {
    loading.value = false
  }
}

const createPath = () => {
  router.push('/learning-paths/new')
}

const editPath = (id) => {
  router.push(`/learning-paths/${id}/edit`)
}

const viewPath = (id) => {
  router.push(`/learning-paths/detail/${id}`)
}

const deletePath = (path) => {
  deleteTarget.value = path
  confirmMessage.value = `确定要删除学习路径"${path.title}"吗？此操作不可撤销。`
  confirmModalVisible.value = true
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return

  try {
    await api.learningPaths.delete(deleteTarget.value.id)
    await loadLearningPaths()
    alert('删除成功')
  } catch (error) {
    console.error('Failed to delete path:', error)
    alert('删除失败')
  } finally {
    confirmModalVisible.value = false
    deleteTarget.value = null
  }
}

const goBack = () => {
  router.push('/admin/dashboard')
}

const resetFilters = () => {
  searchQuery.value = ''
  filterDifficulty.value = ''
  filterStatus.value = ''
}

const getDifficultyLabel = (difficulty) => {
  const labels = { AP: '入门', PR: '进阶', EX: '专家' }
  return labels[difficulty] || difficulty
}

// 生命周期
onMounted(() => {
  loadLearningPaths()
})
</script>

<style scoped>
.learning-paths-manage-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  background: #f5f7fa;
  min-height: 100vh;
}

/* 页面头部 */
.page-header {
  background: white;
  padding: 24px 32px;
  border-radius: 12px;
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.header-content {
  flex: 1;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0 0 8px 0;
}

.page-subtitle {
  font-size: 14px;
  color: #666;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: white;
  padding: 20px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 13px;
  color: #999;
}

/* 筛选栏 */
.filter-bar {
  background: white;
  padding: 16px 24px;
  border-radius: 12px;
  margin-bottom: 24px;
  display: flex;
  gap: 24px;
  align-items: flex-end;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-label {
  font-size: 12px;
  font-weight: 500;
  color: #666;
}

.search-input,
.filter-select {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  font-size: 14px;
  min-width: 200px;
}

.search-input:focus,
.filter-select:focus {
  outline: none;
  border-color: #1890ff;
}

.filter-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

/* 路径卡片网格 */
.paths-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}

.path-card {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  border-top: 3px solid var(--path-color, #1890ff);
}

.path-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  transform: translateY(-2px);
}

.path-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.path-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #f0f7ff;
  color: #1890ff;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.path-status {
  padding: 4px 10px;
  background: #f5f5f5;
  color: #999;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.path-status.published {
  background: #f6ffed;
  color: #52c41a;
}

.path-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0 0 12px 0;
  line-height: 1.4;
}

.path-description {
  font-size: 14px;
  color: #666;
  margin: 0 0 20px 0;
  line-height: 1.6;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.path-meta {
  display: flex;
  gap: 16px;
  padding: 16px 0;
  border-top: 1px solid #f0f0f0;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 16px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #666;
}

.meta-item i {
  color: #999;
}

.path-actions {
  display: flex;
  gap: 8px;
}

/* 加载和空状态 */
.loading-container {
  text-align: center;
  padding: 60px 20px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #f3f3f3;
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: #999;
}

.empty-state i {
  font-size: 64px;
  margin-bottom: 16px;
  display: block;
}

/* 按钮 */
.btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
}

.btn-primary {
  background: #1890ff;
  color: white;
}

.btn-primary:hover {
  background: #40a9ff;
}

.btn-secondary {
  background: #fff;
  color: #333;
  border: 1px solid #d9d9d9;
}

.btn-secondary:hover {
  color: #1890ff;
  border-color: #1890ff;
}

.btn-danger {
  background: #fff;
  color: #ff4d4f;
  border: 1px solid #ff4d4f;
}

.btn-danger:hover {
  background: #ff4d4f;
  color: white;
}

.action-btn {
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  border: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.action-btn.btn-primary {
  background: #1890ff;
  color: white;
  flex: 1;
}

.action-btn.btn-secondary {
  background: #f5f5f5;
  color: #666;
  flex: 1;
}

.action-btn.btn-danger {
  background: white;
  color: #ff4d4f;
  border: 1px solid #ff4d4f;
}

.action-btn:hover {
  opacity: 0.85;
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  width: 100%;
  max-width: 400px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #f0f0f0;
}

.modal-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #999;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: #f5f5f5;
  color: #333;
}

.modal-body {
  padding: 24px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}

.action-btn.btn-default {
  background: white;
  color: #333;
  border: 1px solid #d9d9d9;
}
</style>
