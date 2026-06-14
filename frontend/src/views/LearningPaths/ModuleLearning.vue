<template>
  <div class="module-learning-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <button class="back-button" @click="goBack">
          <i class="bi bi-arrow-left"></i>
          返回路径
        </button>
        <div class="module-breadcrumb">
          <span>{{ path.title }}</span>
          <i class="bi bi-arrow-right"></i>
          <span>{{ module.title }}</span>
        </div>
        <div class="module-meta">
          <span class="difficulty-badge" :class="path.difficulty">
            {{ getDifficultyLabel(path.difficulty) }}
          </span>
          <span class="type-badge" :class="module.module_type">
            {{ getModuleTypeLabel(module.module_type) }}
          </span>
        </div>
        <h1 class="module-title">{{ module.title }}</h1>
        <p v-if="module.description" class="module-description">
          {{ module.description }}
        </p>
      </div>

      <div class="header-actions">
        <button v-if="moduleProgress?.status !== 'COMPLETED'" class="btn btn-success" @click="markComplete">
          <i class="bi bi-check-circle"></i>
          标记完成
        </button>
        <button v-else class="btn btn-primary" disabled>
          <i class="bi bi-check-circle"></i>
          已完成
        </button>
      </div>
    </div>

    <!-- 主内容区域 -->
    <div class="main-content">
      <!-- 加载中 -->
      <div v-if="loading" class="loading-container">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>

      <!-- 内容区域 -->
      <div v-else>
        <!-- 左侧：理论内容 -->
        <div class="content-section">
          <div class="content-card">
            <!-- 理论内容渲染 -->
            <div v-if="module.module_type === 'theory'" class="theory-content">
              <div v-html="renderMarkdown(module.content)" class="markdown-body"></div>
            </div>

            <!-- 介绍内容 -->
            <div v-if="module.module_type === 'intro'" class="intro-content">
              <div v-html="renderMarkdown(module.content)" class="markdown-body"></div>
            </div>

            <!-- 实践内容 -->
            <div v-if="module.module_type === 'practice'" class="practice-content">
              <div v-html="renderMarkdown(module.content)" class="markdown-body"></div>
            </div>

            <!-- 挑战内容 -->
            <div v-if="module.module_type === 'challenge'" class="challenge-content">
              <div v-html="renderMarkdown(module.content)" class="markdown-body"></div>
            </div>

            <!-- 默认内容渲染（作为兜底） -->
            <div v-if="module.content && !['theory', 'intro', 'practice', 'challenge'].includes(module.module_type)" class="default-content">
              <div v-html="renderMarkdown(module.content)" class="markdown-body"></div>
            </div>

            <!-- 空内容提示 -->
            <div v-if="!module.content || module.content === ''" style="padding: 32px; text-align: center; color: #999;">
              <i class="bi bi-file-earmark-text" style="font-size: 48px; display: block; margin-bottom: 16px;"></i>
              <p>暂无内容</p>
            </div>

            <!-- 笔记区域 -->
            <div class="notes-section">
              <h3>我的笔记</h3>
              <textarea
                v-model="notes"
                placeholder="在这里记录你的学习笔记..."
                rows="4"
                class="form-control"
              ></textarea>
              <button class="btn btn-secondary" @click="saveNotes">
                保存笔记
              </button>
            </div>
          </div>
        </div>

        <!-- 右侧：实验列表 -->
        <div v-if="module.labs && module.labs.length" class="labs-section">
          <h3 class="section-title">实践实验</h3>

          <div class="labs-list">
            <div
              v-for="lab in module.labs"
              :key="lab.id"
              class="lab-card"
              :class="{
                'completed': isLabCompleted(lab),
                'in-progress': isLabInProgress(lab)
              }"
            >
              <div class="lab-header">
                <div class="lab-icon">
                  <i v-if="isLabCompleted(lab)" class="bi bi-flask completed"></i>
                  <i v-else-if="isLabInProgress(lab)" class="bi bi-arrow-repeat spinning"></i>
                  <i v-else class="bi bi-flask"></i>
                </div>
                <div class="lab-info">
                  <h4 class="lab-title">{{ lab.lab?.title || '未知实验' }}</h4>
                  <p class="lab-description">{{ lab.lab?.description || '暂无描述' }}</p>
                </div>
              </div>

              <div class="lab-meta">
                <span v-if="lab.lab?.difficulty" class="meta-item">
                  <i class="bi bi-lightning"></i>
                  {{ lab.lab.difficulty }}
                </span>
                <span class="meta-item">
                  <i class="bi bi-trophy"></i>
                  {{ lab.lab_score || 0 }} 分
                </span>
              </div>

              <div class="lab-actions">
                <button
                  v-if="!isLabCompleted(lab) && lab.lab"
                  class="btn btn-primary btn-sm"
                  @click="startLab(lab.lab)"
                >
                  {{ isLabInProgress(lab) ? '继续实验' : '开始实验' }}
                </button>
                <button v-else class="btn btn-success btn-sm" disabled>
                  已完成
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 实验弹窗 -->
    <div v-if="labModalVisible" class="modal-overlay" @click.self="closeLabModal">
      <div class="modal-content">
        <div class="modal-header">
          <h3>{{ currentLab?.title }}</h3>
          <button class="close-btn" @click="closeLabModal">✕</button>
        </div>
        <div class="modal-body">
          <div class="lab-modal-content">
            <!-- 实验内容区域 -->
            <div class="lab-content">
              <div v-html="renderMarkdown(currentLab?.description)" class="markdown-body"></div>

              <div v-if="currentLab?.attachment" class="lab-attachment">
                <h4>实验附件</h4>
                <a :href="currentLab.attachment" class="btn-link">
                  <i class="bi bi-download"></i>
                  下载附件
                </a>
              </div>

              <!-- Flag 提交表单 -->
              <div class="flag-submission">
                <h4>提交 Flag</h4>
                <div class="input-group">
                  <input
                    v-model="flagInput"
                    type="text"
                    class="form-control"
                    placeholder="输入 flag..."
                    @keyup.enter="submitFlag"
                  />
                  <button class="btn btn-primary" @click="submitFlag">
                    提交
                  </button>
                </div>
              </div>
            </div>

            <!-- 实验终端/环境 -->
            <div class="lab-terminal">
              <div class="terminal-header">
                <span>实验环境</span>
                <button class="btn-sm btn-secondary" @click="refreshTerminal">
                  <i class="bi bi-arrow-clockwise"></i>
                  刷新
                </button>
              </div>
              <div class="terminal-content">
                <pre>{{ terminalOutput }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import api from '@/api'
import { marked } from 'marked'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const pathId = computed(() => route.params.pathId)
const moduleId = computed(() => route.params.moduleId)

// 状态
const loading = ref(false)
const path = ref({})
const module = ref({})
const moduleProgress = ref(null)
const labProgress = ref({})
const notes = ref('')

const labModalVisible = ref(false)
const currentLab = ref(null)
const flagInput = ref('')
const terminalOutput = ref('等待连接实验环境...\n')

// 方法
const loadData = async () => {
  loading.value = true
  try {
    // 并行加载路径、模块、进度数据
    const [pathRes, moduleRes, progressRes] = await Promise.all([
      api.learningPaths.detail(pathId.value),
      api.pathModules.detail(moduleId.value),
      api.learningProgress.overview().catch(() => null),
    ])

    path.value = pathRes
    module.value = moduleRes

    // 加载模块的实验室关联
    await loadModuleLabs()

    // 获取模块进度
    if (progressRes && progressRes.modules) {
      const moduleProgressData = progressRes.modules.find(
        m => m.module === parseInt(moduleId.value)
      )
      if (moduleProgressData) {
        moduleProgress.value = moduleProgressData
      }
    }

    // 加载笔记
    await loadNotes()

    // 加载实验室进度
    if (module.value.labs && module.value.labs.length) {
      await loadLabProgress()
    }
  } catch (error) {
    console.error('Failed to load module:', error)
  } finally {
    loading.value = false
  }
}

const loadModuleLabs = async () => {
  try {
    if (module.value.labs && module.value.labs.length > 0) {
      // labs 已经在 module 数据中了
      console.log('Module labs:', module.value.labs)
    }
  } catch (error) {
    console.error('Failed to load module labs:', error)
  }
}

const loadNotes = async () => {
  try {
    const res = await api.pathModules.getNotes(moduleId.value)
    notes.value = res.content || ''
  } catch (error) {
    // 如果没有笔记，忽略错误
    notes.value = ''
  }
}

const loadLabProgress = async () => {
  try {
    const progress = await api.learningProgress.overview()
    if (progress && progress.modules) {
      const moduleData = progress.modules.find(m => m.module === parseInt(moduleId.value))
      if (moduleData && moduleData.lab_progress) {
        moduleData.lab_progress.forEach(lp => {
          labProgress.value[lp.lab] = lp
        })
      }
    }
  } catch (error) {
    console.error('Failed to load lab progress:', error)
  }
}

const saveNotes = async () => {
  try {
    await api.pathModules.saveNotes(moduleId.value, { content: notes.value })
    alert('笔记保存成功')
  } catch (error) {
    console.error('Failed to save notes:', error)
    alert('笔记保存失败')
  }
}

const markComplete = async () => {
  try {
    await api.pathModules.markComplete(moduleId.value)
    moduleProgress.value = {
      ...moduleProgress.value,
      status: 'COMPLETED',
      completed_at: new Date().toISOString()
    }
    alert('已标记为完成')
  } catch (error) {
    console.error('Failed to mark complete:', error)
    alert('标记完成失败')
  }
}

const startLab = (lab) => {
  if (!lab) {
    alert('实验数据不完整')
    return
  }
  currentLab.value = lab
  labModalVisible.value = true
  terminalOutput.value = '正在启动实验环境...\n'
  setTimeout(() => {
    terminalOutput.value += '实验环境已启动\n'
    terminalOutput.value += '提示: 点击下方链接访问实验环境\n'
    if (lab.url) {
      terminalOutput.value += `访问地址: ${lab.url}\n`
    }
  }, 1000)
}

const closeLabModal = () => {
  labModalVisible.value = false
  currentLab.value = null
  flagInput.value = ''
}

const refreshTerminal = () => {
  terminalOutput.value = '刷新中...\n'
  setTimeout(() => {
    terminalOutput.value += '实验环境运行正常\n'
  }, 500)
}

const submitFlag = async () => {
  if (!flagInput.value.trim()) {
    alert('请输入 flag')
    return
  }

  try {
    const res = await api.pathModules.submitFlag(moduleId.value, currentLab.value.id, {
      flag: flagInput.value
    })

    if (res.success) {
      alert('Flag 提交成功！')
      labProgress.value[currentLab.value.id] = {
        ...labProgress.value[currentLab.value.id],
        status: 'COMPLETED',
        completed_at: new Date().toISOString()
      }
    } else {
      alert('Flag 错误，请重试')
    }
  } catch (error) {
    console.error('Failed to submit flag:', error)
    alert('Flag 提交失败')
  }
}

const goBack = () => {
  router.push(`/learning-paths/${pathId.value}`)
}

const isLabCompleted = (lab) => {
  if (!lab?.lab?.id) return false
  return labProgress.value[lab.lab.id]?.status === 'COMPLETED'
}

const isLabInProgress = (lab) => {
  if (!lab?.lab?.id) return false
  const status = labProgress.value[lab.lab.id]?.status
  return status === 'IN_PROGRESS' || status === 'ATTEMPTED'
}

const getDifficultyLabel = (difficulty) => {
  const labels = { AP: '入门', PR: '进阶', EX: '专家' }
  return labels[difficulty] || difficulty
}

const getModuleTypeLabel = (type) => {
  const labels = {
    intro: '介绍',
    theory: '理论',
    practice: '实践',
    challenge: '挑战'
  }
  return labels[type] || type
}

const formatDuration = (seconds) => {
  if (!seconds) return '0 分钟'
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60

  if (hours > 0) {
    return `${hours} 小时 ${remainingMinutes} 分钟`
  }
  return `${remainingMinutes} 分钟`
}

const renderMarkdown = (content) => {
  if (!content) return ''
  return marked(content)
}

// 生命周期
onMounted(() => {
  loadData()
})
</script>

<style scoped>
.module-learning-page {
  min-height: 100vh;
  background: #f5f5f5;
}

.page-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-content {
  flex: 1;
}

.back-button {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  margin-bottom: 16px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.back-button:hover {
  background: rgba(255, 255, 255, 0.3);
}

.module-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  opacity: 0.9;
  margin-bottom: 12px;
  font-size: 14px;
}

.module-meta {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.difficulty-badge,
.type-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.difficulty-badge.AP {
  background: #52c41a;
}

.difficulty-badge.PR {
  background: #faad14;
}

.difficulty-badge.EX {
  background: #f5222d;
}

.type-badge.intro {
  background: #1890ff;
}

.type-badge.theory {
  background: #722ed1;
}

.type-badge.practice {
  background: #13c2c2;
}

.type-badge.challenge {
  background: #eb2f96;
}

.module-title {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 8px 0;
}

.module-description {
  font-size: 16px;
  opacity: 0.9;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.main-content {
  display: grid;
  grid-template-columns: 1fr 350px;
  gap: 24px;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.content-section {
  flex: 1;
}

.content-card {
  background: white;
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.theory-content,
.intro-content,
.practice-content,
.challenge-content {
  margin-bottom: 24px;
}

.markdown-body {
  line-height: 1.8;
}

.notes-section {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #f0f0f0;
}

.notes-section h3 {
  margin-bottom: 12px;
  font-size: 18px;
}

.notes-section textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  margin-bottom: 12px;
  font-family: inherit;
  resize: vertical;
}

.labs-section {
  background: white;
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 16px 0;
}

.labs-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.lab-card {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.3s;
}

.lab-card:hover {
  border-color: #1890ff;
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.15);
}

.lab-card.completed {
  border-color: #52c41a;
}

.lab-card.in-progress {
  border-color: #faad14;
}

.lab-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.lab-icon {
  font-size: 24px;
  color: #1890ff;
}

.lab-icon .completed {
  color: #52c41a;
}

.lab-icon .spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.lab-info {
  flex: 1;
}

.lab-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 4px 0;
}

.lab-description {
  font-size: 14px;
  color: #666;
  margin: 0;
}

.lab-meta {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 14px;
  color: #666;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.lab-actions {
  display: flex;
  justify-content: flex-end;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.btn-primary {
  background: #1890ff;
  color: white;
}

.btn-primary:hover {
  background: #40a9ff;
}

.btn-secondary {
  background: #f5f5f5;
  color: #333;
}

.btn-secondary:hover {
  background: #e6e6e6;
}

.btn-success {
  background: #52c41a;
  color: white;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
}

.btn-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #1890ff;
  text-decoration: none;
  cursor: pointer;
}

.btn-link:hover {
  text-decoration: underline;
}

.input-group {
  display: flex;
  gap: 8px;
}

.form-control {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
}

.form-control:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}

/* Modal styles */
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
  border-radius: 8px;
  width: 90%;
  max-width: 1200px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid #f0f0f0;
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
}

.close-btn:hover {
  color: #333;
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.lab-modal-content {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 24px;
}

.lab-content {
  flex: 1;
}

.lab-attachment {
  margin: 24px 0;
  padding: 16px;
  background: #f5f5f5;
  border-radius: 4px;
}

.lab-attachment h4 {
  margin: 0 0 8px 0;
  font-size: 16px;
}

.flag-submission {
  margin: 24px 0;
}

.flag-submission h4 {
  margin: 0 0 12px 0;
  font-size: 16px;
}

.lab-terminal {
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #2d2d2d;
  border-bottom: 1px solid #3e3e3e;
}

.terminal-header button {
  background: rgba(255, 255, 255, 0.1);
  border: none;
  color: white;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.terminal-header button:hover {
  background: rgba(255, 255, 255, 0.2);
}

.terminal-content {
  padding: 16px;
  flex: 1;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.terminal-content pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
}

@media (max-width: 1200px) {
  .main-content {
    grid-template-columns: 1fr;
  }

  .lab-modal-content {
    grid-template-columns: 1fr;
  }
}
</style>
