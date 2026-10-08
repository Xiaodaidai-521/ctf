<template>
  <div class="learning-paths-page">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">学习路径</h1>
        <p class="page-subtitle">系统化学习路线，从入门到精通</p>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon stat-icon-primary">
          <i class="bi bi-book"></i>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">总路径数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon stat-icon-accent">
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
    </div>

    <div v-else class="paths-grid">
      <div
        v-for="path in filteredPaths"
        :key="path.id"
        class="path-card"
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
          <button class="action-btn btn-primary" @click="viewPath(path.id)">
            <i class="bi bi-play-fill"></i>
            开始学习
          </button>
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

// 统计
const stats = reactive({
  total: 0,
  enrolled: 0,
})

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

  // 只显示已发布的路径
  result = result.filter(p => p.is_published)

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
    stats.enrolled = paths.value.reduce((sum, p) => sum + (p.enrollment_count || 0), 0)
  } catch (error) {
    console.error('Failed to load learning paths:', error)
  } finally {
    loading.value = false
  }
}

const viewPath = (id) => {
  router.push(`/learning-paths/${id}`)
}

const resetFilters = () => {
  searchQuery.value = ''
  filterDifficulty.value = ''
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
.learning-paths-page {
  padding: 42px 24px 72px;
  max-width: 1180px;
  margin: 0 auto;
  background:
    linear-gradient(90deg, rgba(24, 23, 19, 0.045) 1px, transparent 1px) 0 0 / 44px 44px,
    linear-gradient(180deg, #faf7f0 0%, var(--bg-paper) 100%);
  min-height: 100vh;
}

/* 页面头部 */
.page-header {
  background: transparent;
  padding: 0 0 22px;
  border-bottom: 1px solid var(--border-color);
  border-radius: 0;
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: none;
}

.header-content {
  flex: 1;
}

.page-title {
  font-size: 44px;
  line-height: 1;
  font-weight: 950;
  color: var(--text-primary);
  margin: 0 0 12px;
}

.page-subtitle {
  font-size: 15px;
  color: var(--text-secondary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: rgba(255, 250, 242, 0.72);
  padding: 20px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: none;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  border: 1px solid var(--border-color);
}

.stat-icon-primary {
  background: var(--bg-paper-2);
  color: var(--text-primary);
}

.stat-icon-accent {
  background: rgba(183, 53, 45, 0.1);
  color: var(--primary-color);
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 筛选栏 */
.filter-bar {
  background: rgba(255, 250, 242, 0.72);
  padding: 16px 24px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  margin-bottom: 24px;
  display: flex;
  gap: 24px;
  align-items: flex-end;
  box-shadow: none;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-label {
  font-size: 12px;
  font-weight: 850;
  color: var(--text-secondary);
}

.search-input,
.filter-select {
  padding: 8px 12px;
  background: rgba(255, 250, 242, 0.78);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 14px;
  min-width: 200px;
  color: var(--text-primary);
}

.search-input:focus,
.filter-select:focus {
  outline: none;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(183, 53, 45, 0.12);
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
  background: rgba(255, 250, 242, 0.72);
  border-radius: 8px;
  padding: 24px;
  box-shadow: none;
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-color);
  border-top: 4px solid var(--text-primary);
}

.path-card:hover {
  box-shadow: 8px 8px 0 rgba(24, 23, 19, 0.1);
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
  background: var(--bg-paper-2);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 850;
}

.path-status {
  padding: 4px 10px;
  background: rgba(24, 23, 19, 0.06);
  color: var(--text-secondary);
  border: 1px dashed var(--border-color);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 850;
}

.path-status.published {
  background: var(--bg-paper-2);
  color: var(--text-primary);
  border-style: solid;
}

.path-title {
  font-size: 22px;
  font-weight: 950;
  color: var(--text-primary);
  margin: 0 0 12px 0;
  line-height: 1.4;
}

.path-description {
  font-size: 14px;
  color: var(--text-secondary);
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
  border-top: 1px solid var(--border-color);
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 16px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.meta-item i {
  color: var(--text-muted);
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
  border: 3px solid var(--bg-paper-2);
  border-top-color: var(--text-primary);
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
  color: var(--text-muted);
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

.btn-primary {
  background: var(--text-primary);
  color: #fbf7ef;
}

.btn-primary:hover {
  background: #2a2823;
}

.btn-secondary {
  background: rgba(255, 250, 242, 0.72);
  color: var(--text-primary);
  border: 1px solid var(--text-primary);
}

.btn-secondary:hover {
  color: var(--primary-color);
  border-color: var(--primary-color);
}

.btn-danger {
  background: rgba(255, 250, 242, 0.72);
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
}

.btn-danger:hover {
  background: var(--primary-color);
  color: #fbf7ef;
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
  background: var(--text-primary);
  color: #fbf7ef;
  flex: 1;
}

.action-btn.btn-secondary {
  background: var(--bg-paper-2);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  flex: 1;
}

.action-btn.btn-danger {
  background: rgba(255, 250, 242, 0.72);
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
}

.action-btn:hover {
  opacity: 1;
  transform: translateY(-1px);
  box-shadow: 5px 5px 0 rgba(24, 23, 19, 0.12);
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
  background: #fffaf2;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  width: 100%;
  max-width: 400px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--text-muted);
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
  background: var(--bg-paper-2);
  color: var(--text-primary);
}

.modal-body {
  padding: 24px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-paper);
}

.action-btn.btn-default {
  background: rgba(255, 250, 242, 0.72);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}
</style>
