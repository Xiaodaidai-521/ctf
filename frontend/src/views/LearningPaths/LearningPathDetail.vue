<template>
  <div class="learning-path-detail-page">
    <!-- 页面头部 -->
    <div class="page-header" :style="{ background: `linear-gradient(135deg, ${path.color}20, ${path.color}05)` }">
      <div class="header-content">
        <button class="back-button" @click="goBack">
          <i class="bi bi-arrow-left"></i>
          返回
        </button>
        <div class="path-info">
          <div class="path-meta">
            <span class="difficulty-badge" :class="path.difficulty">
              {{ getDifficultyLabel(path.difficulty) }}
            </span>
            <span v-if="path.category" class="category-badge">
              {{ path.category }}
            </span>
          </div>
          <h1 class="path-title">{{ path.title }}</h1>
          <p class="path-description">{{ path.description }}</p>
          <div class="path-stats">
            <span class="stat-item">
              <i class="bi bi-book"></i>
              {{ path.total_modules || 0 }} 章节
            </span>
            <span class="stat-item">
              <i class="bi bi-flask"></i>
              {{ path.total_labs || 0 }} 实验
            </span>
            <span class="stat-item">
              <i class="bi bi-clock"></i>
              {{ path.estimated_hours || 0 }} 小时
            </span>
          </div>
        </div>
      </div>

      <!-- 开始学习按钮 -->
      <div class="header-actions">
        <template v-if="myProgress">
          <div class="progress-summary">
            <div class="progress-circle">
              <svg viewBox="0 0 36 36">
                <path
                  class="progress-bg"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
                <path
                  class="progress-fill"
                  :stroke-dasharray="`${myProgress.progress_percentage}, 100`"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  :style="{ stroke: path.color || '#1890ff' }"
                />
              </svg>
              <span class="progress-text">{{ myProgress.progress_percentage }}%</span>
            </div>
            <div class="progress-info">
              <p class="progress-label">学习进度</p>
              <p class="progress-detail">
                {{ myProgress.completed_modules }} / {{ path.total_modules }} 章节完成
              </p>
            </div>
          </div>
          <button
            v-if="myProgress.progress_percentage < 100"
            class="btn btn-primary btn-continue"
            @click="continueLearning"
          >
            <i class="bi bi-play-fill"></i>
            继续学习
          </button>
          <button v-else class="btn btn-success" disabled>
            <i class="bi bi-check-circle"></i>
            已完成
          </button>
        </template>
        <button v-else class="btn btn-primary" @click="startLearning">
          <i class="bi bi-play-fill"></i>
          开始学习
        </button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-container">
      <div class="spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- 主要内容区域 -->
    <div v-else class="main-content">
      <!-- 章节列表 -->
      <div class="modules-section">
        <h2 class="section-title">学习章节</h2>

        <div v-if="modulesLoading" class="loading-container">
          <div class="spinner"></div>
          <p>加载章节中...</p>
        </div>

        <div v-else-if="modules.length === 0" class="empty-modules">
          <i class="bi bi-inbox"></i>
          <p>暂无章节内容</p>
        </div>

        <div v-else class="modules-list">
          <div
            v-for="(module, index) in modules"
            :key="module.id"
            class="module-card"
            :class="{
              'locked': !isModuleUnlocked(module),
              'completed': isModuleCompleted(module),
              'in-progress': isModuleInProgress(module)
            }"
            @click="handleModuleClick(module)"
          >
            <div class="module-header">
              <div class="module-order">
                <span v-if="isModuleCompleted(module)">
                  <i class="bi bi-check-circle-fill"></i>
                </span>
                <span v-else-if="isModuleInProgress(module)">
                  <i class="bi bi-arrow-repeat"></i>
                </span>
                <span v-else>{{ index + 1 }}</span>
              </div>
              <div class="module-type-badge" :class="module.module_type">
                {{ getModuleTypeLabel(module.module_type) }}
              </div>
              <span v-if="module.is_required" class="required-badge">必修</span>
            </div>

            <div class="module-body">
              <h3 class="module-title">{{ module.title }}</h3>
              <p class="module-description">{{ module.description }}</p>

              <div class="module-meta">
                <span class="meta-item">
                  <i class="bi bi-clock"></i>
                  {{ module.estimated_minutes || 0 }} 分钟
                </span>
                <span v-if="module.labs && module.labs.length" class="meta-item">
                  <i class="bi bi-flask"></i>
                  {{ module.labs.length }} 实验
                </span>
              </div>

              <div v-if="module.progress" class="module-progress">
                <div class="progress-bar">
                  <div
                    class="progress-fill"
                    :style="{ width: `${module.progress.percentage}%` }"
                  ></div>
                </div>
                <span class="progress-text">{{ module.progress.percentage }}%</span>
              </div>

              <div v-if="module.requires_modules && module.requires_modules.length" class="prerequisites">
                <i class="bi bi-lock-fill"></i>
                需要先完成：
                <template v-for="(req, i) in module.requires_modules" :key="req.id">
                  {{ req.title }}{{ i < module.requires_modules.length - 1 ? '、' : '' }}
                </template>
              </div>
            </div>

            <div class="module-arrow">
              <i class="bi bi-chevron-right"></i>
            </div>
          </div>
        </div>
      </div>

      <!-- 侧边栏 -->
      <div class="sidebar">
        <!-- 知识图谱 -->
        <div class="sidebar-card">
          <h3 class="sidebar-title">知识图谱</h3>
          <div v-if="graphLoading" class="loading-mini">
            <div class="spinner mini"></div>
          </div>
          <div v-else class="knowledge-graph-preview">
            <div v-if="topConcepts.length > 0" class="graph-nodes">
              <div
                v-for="concept in topConcepts"
                :key="concept.id"
                class="concept-node"
                :class="{ mastered: concept.mastery_level >= 0.7 }"
              >
                {{ concept.name }}
              </div>
            </div>
            <div v-else class="empty-graph">
              <p>暂无知识图谱数据</p>
            </div>
            <button class="btn-link" @click="showGraphModal">
              查看完整图谱
            </button>
          </div>
        </div>

        <!-- 学习统计 -->
        <div v-if="myProgress" class="sidebar-card">
          <h3 class="sidebar-title">学习统计</h3>
          <div class="stats-list">
            <div class="stat-item">
              <span class="stat-label">开始时间</span>
              <span class="stat-value">{{ formatDate(myProgress.started_at) }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">学习时长</span>
              <span class="stat-value">{{ formatDuration(myProgress.total_time_spent) }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">完成实验</span>
              <span class="stat-value">{{ myProgress.completed_labs || 0 }} / {{ path.total_labs || 0 }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 知识图谱弹窗 -->
    <div v-if="graphModalVisible" class="modal-overlay" @click.self="graphModalVisible = false">
      <div class="modal-content graph-modal">
        <div class="modal-header">
          <h3>知识图谱</h3>
          <button class="close-btn" @click="graphModalVisible = false">✕</button>
        </div>
        <div class="modal-body">
          <div v-if="graphLoading" class="loading-container">
            <div class="spinner"></div>
            <p>加载图谱中...</p>
          </div>
          <div v-else ref="graphContainer" class="graph-container">
            <p class="graph-placeholder">知识图谱将在此处显示</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 提示消息 -->
    <div v-if="message.visible" class="toast" :class="`toast-${message.type}`">
      <i class="bi" :class="message.type === 'success' ? 'bi-check-circle' : 'bi-exclamation-circle'"></i>
      <span>{{ message.text }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import api from '@/api'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const pathId = computed(() => route.params.id)

// 状态
const loading = ref(false)
const modulesLoading = ref(false)
const graphLoading = ref(false)
const path = ref({})
const modules = ref([])
const myProgress = ref(null)
const topConcepts = ref([])
const graphModalVisible = ref(false)
const graphContainer = ref(null)

// 提示消息
const message = ref({
  visible: false,
  type: 'info',
  text: ''
})

// 显示提示
const showMessage = (type, text) => {
  message.value = { visible: true, type, text }
  setTimeout(() => {
    message.value.visible = false
  }, 3000)
}

// 方法
const loadData = async () => {
  loading.value = true
  try {
    const [pathRes, modulesRes, progressRes] = await Promise.all([
      api.learningPaths.detail(pathId.value),
      api.pathModules.list({ learning_path: pathId.value }),
      api.learningPaths.my().catch(() => null),
    ])

    path.value = pathRes || {}
    modules.value = modulesRes.results || modulesRes || []

    if (progressRes && Array.isArray(progressRes)) {
      const progress = progressRes.find(p => p.path === parseInt(pathId.value))
      myProgress.value = progress || null
    }

    // 加载每个模块的进度
    if (myProgress.value) {
      await loadModuleProgress()
    }
  } catch (error) {
    console.error('Failed to load path detail:', error)
    showMessage('error', '加载失败')
  } finally {
    loading.value = false
  }
}

const loadModuleProgress = async () => {
  try {
    const moduleProgress = await api.learningProgress.overview()
    if (moduleProgress && moduleProgress.modules) {
      modules.value.forEach(module => {
        const progress = moduleProgress.modules.find(m => m.module === module.id)
        if (progress) {
          module.progress = {
            percentage: progress.status === 'COMPLETED' ? 100 :
                        progress.status === 'IN_PROGRESS' ? 50 : 0,
            status: progress.status
          }
        }
      })
    }
  } catch (error) {
    console.error('Failed to load module progress:', error)
  }
}

const loadTopConcepts = async () => {
  graphLoading.value = true
  try {
    const concepts = await api.knowledgeGraph.concepts({ limit: 6 })
    topConcepts.value = concepts.results || concepts || []
  } catch (error) {
    console.error('Failed to load concepts:', error)
    topConcepts.value = []
  } finally {
    graphLoading.value = false
  }
}

const startLearning = async () => {
  try {
    await api.learningPaths.start(pathId.value)
    showMessage('success', '已开始学习')
    myProgress.value = { 
      progress_percentage: 0, 
      completed_modules: 0,
      completed_labs: 0,
      total_labs: path.value.total_labs,
      started_at: new Date().toISOString() 
    }
  } catch (error) {
    console.error('Start learning failed:', error)
    showMessage('error', '开始学习失败')
  }
}

const continueLearning = () => {
  // 找到第一个未完成的模块
  const nextModule = modules.value.find(m => !isModuleCompleted(m))
  if (nextModule) {
    goToModule(nextModule.id)
  }
}

const goBack = () => {
  router.push('/learning-paths')
}

const goToModule = (moduleId) => {
  router.push(`/learning-paths/${pathId.value}/modules/${moduleId}`)
}

const handleModuleClick = (module) => {
  if (!isModuleUnlocked(module)) {
    showMessage('warning', '请先完成前置章节')
    return
  }
  goToModule(module.id)
}

const isModuleUnlocked = (module) => {
  if (!module.requires_modules || module.requires_modules.length === 0) return true
  return module.requires_modules.every(req => isModuleCompleted(req))
}

const isModuleCompleted = (module) => {
  return module.progress?.status === 'COMPLETED'
}

const isModuleInProgress = (module) => {
  return module.progress?.status === 'IN_PROGRESS'
}

const getDifficultyLabel = (difficulty) => {
  const labels = { AP: '入门', PR: '进阶', EX: '专家' }
  return labels[difficulty] || difficulty
}

const getModuleTypeLabel = (type) => {
  const labels = { intro: '介绍', theory: '理论', practice: '实践', challenge: '挑战' }
  return labels[type] || type
}

const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('zh-CN')
}

const formatDuration = (seconds) => {
  if (!seconds) return '0小时'
  const hours = Math.floor(seconds / 3600)
  return `${hours}小时`
}

const showGraphModal = async () => {
  graphModalVisible.value = true
  graphLoading.value = true
  try {
    // 加载完整图谱数据并渲染
    const graphData = await api.knowledgeGraph.graph({ learning_path: pathId.value })
    // 这里可以使用 echarts 或其他图表库渲染图谱
  } catch (error) {
    console.error('Failed to load graph:', error)
  } finally {
    graphLoading.value = false
  }
}

// 生命周期
onMounted(() => {
  loadData()
  loadTopConcepts()
})
</script>

<style scoped>
.learning-path-detail-page {
  min-height: 100vh;
  background: #f5f7fa;
}

/* 页面头部 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 32px 40px;
  background: linear-gradient(135deg, #1890ff20, #1890ff05);
}

.header-content {
  flex: 1;
}

.back-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: white;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: all 0.2s;
  margin-bottom: 20px;
}

.back-button:hover {
  color: #1890ff;
  border-color: #1890ff;
}

.path-info {
  max-width: 600px;
}

.path-meta {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.difficulty-badge {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.difficulty-badge.AP {
  background: #e6f7ff;
  color: #1890ff;
}

.difficulty-badge.PR {
  background: #fff7e6;
  color: #fa8c16;
}

.difficulty-badge.EX {
  background: #fff1f0;
  color: #ff4d4f;
}

.category-badge {
  padding: 4px 12px;
  background: #f6ffed;
  color: #52c41a;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.path-title {
  font-size: 32px;
  font-weight: 600;
  color: #333;
  margin: 0 0 12px 0;
  line-height: 1.3;
}

.path-description {
  font-size: 16px;
  color: #666;
  margin: 0 0 20px 0;
  line-height: 1.6;
}

.path-stats {
  display: flex;
  gap: 24px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #666;
}

.stat-item i {
  color: #999;
}

/* 进度摘要 */
.progress-summary {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 20px;
  background: white;
  border-radius: 12px;
  margin-bottom: 16px;
}

.progress-circle {
  width: 80px;
  height: 80px;
}

.progress-circle svg {
  transform: rotate(-90deg);
}

.progress-bg {
  fill: none;
  stroke: #f0f0f0;
  stroke-width: 3;
}

.progress-fill {
  fill: none;
  stroke: #1890ff;
  stroke-width: 3;
  stroke-linecap: round;
  transition: stroke-dasharray 0.5s ease;
}

.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.progress-info {
  flex: 1;
}

.progress-label {
  font-size: 12px;
  color: #999;
  margin: 0 0 4px 0;
}

.progress-detail {
  font-size: 14px;
  color: #333;
  margin: 0;
}

/* 按钮 */
.btn {
  padding: 10px 24px;
  border-radius: 6px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.btn-primary {
  background: #1890ff;
  color: white;
}

.btn-primary:hover {
  background: #40a9ff;
}

.btn-success {
  background: #52c41a;
  color: white;
}

.btn-continue {
  font-size: 16px;
  padding: 12px 32px;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 主要内容 */
.main-content {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 24px;
  padding: 24px 40px;
  max-width: 1400px;
  margin: 0 auto;
}

.modules-section {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin: 0 0 20px 0;
}

/* 章节卡片 */
.modules-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.module-card {
  display: flex;
  align-items: center;
  padding: 20px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.module-card:hover:not(.locked) {
  border-color: #1890ff;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.1);
}

.module-card.locked {
  opacity: 0.6;
  cursor: not-allowed;
  background: #fafafa;
}

.module-card.completed {
  border-color: #52c41a;
  background: #f6ffed;
}

.module-card.in-progress {
  border-color: #1890ff;
  background: #e6f7ff;
}

.module-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-right: 16px;
}

.module-order {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 600;
  color: #999;
  border-radius: 8px;
  background: #f5f5f5;
}

.module-card.completed .module-order {
  background: #52c41a;
  color: white;
}

.module-card.in-progress .module-order {
  background: #1890ff;
  color: white;
}

.module-type-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.module-type-badge.intro { background: #f0f0f0; color: #666; }
.module-type-badge.theory { background: #e6f7ff; color: #1890ff; }
.module-type-badge.practice { background: #f6ffed; color: #52c41a; }
.module-type-badge.challenge { background: #fff2e8; color: #fa8c16; }

.required-badge {
  align-self: flex-start;
  padding: 2px 8px;
  background: #ffec3d;
  color: #8c6900;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.module-body {
  flex: 1;
}

.module-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0 0 8px 0;
}

.module-description {
  font-size: 14px;
  color: #666;
  margin: 0 0 12px 0;
  line-height: 1.5;
}

.module-meta {
  display: flex;
  gap: 16px;
}

.module-meta .meta-item {
  font-size: 13px;
  color: #999;
}

.module-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: #f0f0f0;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: #1890ff;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 13px;
  font-weight: 500;
  color: #1890ff;
}

.prerequisites {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  font-size: 13px;
  color: #999;
}

.prerequisites i {
  color: #ff4d4f;
}

.module-arrow {
  color: #999;
  font-size: 20px;
}

/* 侧边栏 */
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sidebar-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0 0 16px 0;
}

.knowledge-graph-preview {
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
}

.graph-nodes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.concept-node {
  padding: 6px 12px;
  background: white;
  border: 1px solid #e8e8e8;
  border-radius: 20px;
  font-size: 13px;
  color: #666;
  transition: all 0.2s;
}

.concept-node.mastered {
  background: #f6ffed;
  border-color: #52c41a;
  color: #52c41a;
}

.btn-link {
  background: none;
  border: none;
  color: #1890ff;
  cursor: pointer;
  font-size: 13px;
  text-decoration: none;
}

.btn-link:hover {
  text-decoration: underline;
}

.stats-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stats-list .stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stats-list .stat-label {
  font-size: 13px;
  color: #999;
}

.stats-list .stat-value {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

/* 加载状态 */
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

.spinner.mini {
  width: 24px;
  height: 24px;
  border-width: 2px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-mini {
  display: flex;
  justify-content: center;
  padding: 20px;
}

.loading-container p {
  color: #999;
  margin: 0;
}

/* 空状态 */
.empty-modules,
.empty-graph {
  text-align: center;
  padding: 40px 20px;
  color: #999;
}

.empty-modules i,
.empty-graph i {
  font-size: 48px;
  display: block;
  margin-bottom: 16px;
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
  max-width: 900px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-content.graph-modal {
  max-width: 80%;
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
  overflow-y: auto;
  max-height: calc(90vh - 80px);
}

.graph-container {
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.graph-placeholder {
  color: #999;
  font-size: 16px;
}

/* 提示消息 */
.toast {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  padding: 12px 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  z-index: 2000;
  animation: slideDown 0.3s ease;
}

.toast-success {
  background: #f6ffed;
  color: #52c41a;
  border: 1px solid #52c41a;
}

.toast-error {
  background: #fff1f0;
  color: #ff4d4f;
  border: 1px solid #ff4d4f;
}

.toast-warning {
  background: #fff7e6;
  color: #fa8c16;
  border: 1px solid #fa8c16;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translate(-50%, -20px);
  }
  to {
    opacity: 1;
    transform: translate(-50%, 0);
  }
}

/* 响应式 */
@media (max-width: 1024px) {
  .main-content {
    grid-template-columns: 1fr;
  }
  
  .sidebar {
    order: -1;
  }
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 20px;
  }
  
  .header-actions {
    width: 100%;
  }
  
  .progress-summary {
    width: 100%;
  }
}
</style>
