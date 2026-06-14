<template>
  <div class="challenge-modal" @click.self="handleClose">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal-container">
        <!-- 关闭按钮 -->
        <button class="close-btn" @click="handleClose">✕</button>

        <div v-if="loading" class="modal-loading">
          <div class="loading-spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else class="modal-content">
          <!-- 题目信息 -->
          <div class="challenge-section">
            <div class="challenge-header">
              <h1 class="challenge-title">{{ challenge?.title }}</h1>
              <div class="challenge-badges">
                <span class="badge" :class="`badge-${challenge?.difficulty}`">
                  {{ difficultyText }}
                </span>
                <span class="badge badge-primary">{{ challenge?.category_name }}</span>
                <span class="badge badge-success">{{ challenge?.score }} 分</span>
              </div>
            </div>

            <div class="challenge-body">
              <h2 class="section-title">📝 题目描述</h2>
              <div class="challenge-description">{{ challenge?.description }}</div>

              <div v-if="challenge?.hint" class="challenge-hint">
                <h2 class="section-title">💡 提示</h2>
                <div class="hint-content">{{ challenge.hint }}</div>
              </div>

              <div v-if="challenge?.attachment" class="challenge-attachment">
                <h2 class="section-title">📎 附件</h2>
                <a :href="challenge.attachment" class="attachment-link" target="_blank">
                  <span class="attachment-icon">⬇️</span>
                  下载附件
                </a>
              </div>

              <!-- 容器启动区域 -->
              <div
                v-if="challenge?.recommended_articles?.length || challenge?.recommended_resources?.length"
                class="challenge-guidance"
              >
                <h2 class="section-title">拓展阅读</h2>
                <p class="guidance-intro">
                  这些内容只作为导读入口展示，不会注入 AI 回答上下文。
                </p>

                <div v-if="challenge?.recommended_articles?.length" class="guidance-group">
                  <h3 class="guidance-group-title">相关阅读</h3>
                  <div
                    v-for="article in challenge.recommended_articles"
                    :key="`article-${article.article_id}`"
                    class="guidance-card"
                  >
                    <div class="guidance-card-body">
                      <div class="guidance-card-title">{{ article.title }}</div>
                      <div v-if="article.reason" class="guidance-card-reason">{{ article.reason }}</div>
                      <div v-if="article.summary" class="guidance-card-summary">{{ article.summary }}</div>
                    </div>
                    <a
                      :href="article.url"
                      class="guidance-card-link"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      前往文章
                    </a>
                  </div>
                </div>

                <div v-if="challenge?.recommended_resources?.length" class="guidance-group">
                  <h3 class="guidance-group-title">相关资源</h3>
                  <div
                    v-for="resource in challenge.recommended_resources"
                    :key="`resource-${resource.resource_id}`"
                    class="guidance-card"
                  >
                    <div class="guidance-card-body">
                      <div class="guidance-card-title">{{ resource.title }}</div>
                      <div v-if="resource.reason" class="guidance-card-reason">{{ resource.reason }}</div>
                      <div class="guidance-card-meta">
                        <span v-if="resource.category">{{ resource.category }}</span>
                        <span>{{ resource.relation_type }}</span>
                      </div>
                    </div>
                    <a
                      :href="resource.url"
                      class="guidance-card-link"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      查看资源
                    </a>
                  </div>
                </div>
              </div>

              <div v-if="challenge?.docker_image" class="challenge-container">
                <h2 class="section-title">🐳 容器环境</h2>
                <div class="container-info">
                  <div class="container-status" :class="containerStatusClass">
                    <span class="status-icon">{{ containerStatusIcon }}</span>
                    <span class="status-text">{{ containerStatusText }}</span>
                  </div>

                  <div v-if="containerInfo?.status === 'running'" class="container-actions">
                    <!-- 启动进度检查 -->
                    <div v-if="containerReadyState === 'checking'" class="startup-progress-box">
                      <div class="progress-header">
                        <span class="progress-icon">🔄</span>
                        <span class="progress-label">容器启动中...</span>
                        <span class="progress-percent">{{ startupProgress }}%</span>
                      </div>
                      <div class="progress-bar">
                        <div class="progress-fill" :style="{ width: startupProgress + '%' }"></div>
                      </div>
                      <div class="progress-steps">
                        <div class="progress-step" :class="{ active: startupProgress >= 0, current: startupProgress < 33 }">
                          <span class="step-icon">{{ startupProgress < 33 ? '🔌' : '✅' }}</span>
                          <span class="step-text">分配端口</span>
                        </div>
                        <div class="progress-step" :class="{ active: startupProgress >= 33, current: startupProgress >= 33 && startupProgress < 66 }">
                          <span class="step-icon">{{ startupProgress >= 33 && startupProgress < 66 ? '🌐' : (startupProgress >= 66 ? '✅' : '⏳') }}</span>
                          <span class="step-text">配置代理</span>
                        </div>
                        <div class="progress-step" :class="{ active: startupProgress >= 66, current: startupProgress >= 66 && startupProgress < 95 }">
                          <span class="step-icon">{{ startupProgress >= 66 && startupProgress < 95 ? '🚀' : (startupProgress >= 95 ? '✅' : '⏳') }}</span>
                          <span class="step-text">启动成功</span>
                        </div>
                      </div>
                    </div>

                    <!-- 倒计时显示（容器就绪后显示） -->
                    <div v-if="containerReadyState === 'ready'" class="countdown-box">
                      <div class="countdown-header">
                        <span class="countdown-icon">⏱️</span>
                        <span class="countdown-label">剩余时间</span>
                        <span class="countdown-time">{{ countdownDisplay }}</span>
                      </div>
                      <div class="countdown-progress-bar">
                        <div class="countdown-progress-fill" :style="{ width: countdownProgress + '%' }"></div>
                      </div>
                    </div>

                    <!-- 访问地址（容器就绪后显示） -->
                    <div v-if="containerReadyState === 'ready'" class="access-url-box">
                      <span class="access-url-label">🔗 访问地址</span>
                      <div class="access-url-actions">
                        <a
                          :href="containerInfo.access_url"
                          class="access-url-link"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {{ containerInfo.access_url }}
                        </a>
                        <button
                          class="btn-copy"
                          @click="copyAccessUrl"
                          title="复制访问地址"
                        >
                          📋
                        </button>
                      </div>
                    </div>

                    <!-- 停止按钮 -->
                    <button
                      class="btn btn-danger btn-sm btn-full"
                      @click="handleStopContainer"
                      :disabled="stoppingContainer"
                    >
                      {{ stoppingContainer ? '⏳ 停止中...' : '🛑 停止容器' }}
                    </button>
                  </div>

                  <div v-else class="container-actions">
                    <button
                      class="btn btn-success btn-full"
                      @click="handleStartContainer"
                      :disabled="startingContainer"
                    >
                      {{ startingContainer ? '⏳ 启动中...' : '🚀 启动容器（30分钟）' }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 提交区域 -->
          <div class="submit-section">
            <div v-if="challenge?.is_solved" class="success-banner">
              <div class="success-icon">🎉</div>
              <div class="success-text">
                <h3>已解决此题</h3>
                <p>获得 {{ challenge.score }} 分</p>
              </div>
            </div>

            <h2 class="section-title">🚩 提交 Flag</h2>
            <div class="submit-form">
              <input
                v-model="flagInput"
                type="text"
                class="input"
                placeholder="请输入 flag，例如: flag{...}"
                @keyup.enter="handleSubmit"
                :disabled="!userStore.isAuthenticated"
              />
              <button
                v-if="userStore.isAuthenticated"
                class="btn btn-primary"
                @click="handleSubmit"
                :disabled="submitting || challenge?.is_solved"
              >
                {{ submitting ? '提交中...' : '提交' }}
              </button>
              <router-link
                v-else
                to="/login"
                class="btn btn-primary"
              >
                登录后提交
              </router-link>
            </div>

            <div v-if="message" class="submit-message" :class="messageType">
              <span class="message-icon">{{ messageType === 'success' ? '✓' : '✗' }}</span>
              {{ message }}
            </div>

            <div class="submit-hint">
              <p>💡 提示：Flag 格式通常为 flag{...}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useChallengeStore } from '@/store/challenge'
import { useUserStore } from '@/store/user'
import api from '@/api'

const props = defineProps({
  challengeId: {
    type: Number,
    required: true
  }
})

const emit = defineEmits(['close'])

const challengeStore = useChallengeStore()
const userStore = useUserStore()

const challenge = ref(null)
const loading = ref(false)
const flagInput = ref('')
const submitting = ref(false)
const message = ref('')
const messageType = ref('')
const containerInfo = ref(null)
const startingContainer = ref(false)
const stoppingContainer = ref(false)
const remainingTime = ref(0)
const containerReadyState = ref('idle') // idle, checking, ready
const startupProgress = ref(0) // 0-100
let countdownTimer = null
let readinessCheckTimer = null
let startupProgressTimer = null

const difficultyText = computed(() => {
  const map = {
    'easy': '简单',
    'medium': '中等',
    'hard': '困难',
    'expert': '专家'
  }
  return map[challenge.value?.difficulty] || '未知'
})

const containerStatusText = computed(() => {
  if (!containerInfo.value) return '未启动'
  const statusMap = {
    'not_started': '未启动',
    'pending': '启动中',
    'running': '运行中',
    'stopped': '已停止',
    'destroyed': '已销毁',
    'error': '错误'
  }
  return statusMap[containerInfo.value.status] || containerInfo.value.status
})

const containerStatusIcon = computed(() => {
  if (!containerInfo.value) return '○'
  const iconMap = {
    'not_started': '○',
    'pending': '⏳',
    'running': '●',
    'stopped': '■',
    'destroyed': '🗑',
    'error': '❌'
  }
  return iconMap[containerInfo.value.status] || '○'
})

const containerStatusClass = computed(() => {
  if (!containerInfo.value) return 'status-idle'
  const classMap = {
    'not_started': 'status-idle',
    'pending': 'status-pending',
    'running': 'status-running',
    'stopped': 'status-stopped',
    'destroyed': 'status-destroyed',
    'error': 'status-error'
  }
  return classMap[containerInfo.value.status] || 'status-idle'
})

// 计算倒计时（秒）
const calculateRemainingTime = () => {
  if (!containerInfo.value?.expires_at) return 0
  const now = new Date()
  const expiry = new Date(containerInfo.value.expires_at)
  const diff = Math.floor((expiry - now) / 1000)
  return Math.max(0, diff)
}

// 格式化倒计时显示
const countdownDisplay = computed(() => {
  const totalSeconds = remainingTime.value
  if (totalSeconds <= 0) return '已过期'

  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
})

// 倒计时进度（百分比）
const countdownProgress = computed(() => {
  const totalTime = 30 * 60 // 30分钟 = 1800秒
  const progress = ((totalTime - remainingTime.value) / totalTime) * 100
  return Math.min(100, Math.max(0, progress))
})

// 启动倒计时
const startCountdown = () => {
  stopCountdown() // 清除之前的倒计时

  remainingTime.value = calculateRemainingTime()

  if (remainingTime.value > 0 && containerInfo.value?.status === 'running') {
    countdownTimer = setInterval(() => {
      remainingTime.value = calculateRemainingTime()

      if (remainingTime.value <= 0) {
        stopCountdown()
        // 倒计时结束，刷新容器状态
        fetchContainerStatus()
      }
    }, 1000)
  }
}

// 停止倒计时
const stopCountdown = () => {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

const formatTime = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 检查容器是否就绪（通过后端API）
const checkContainerReadiness = async () => {
  try {
    // 通过API检查容器状态，如果状态是running就认为就绪
    const response = await api.challenge.getContainer(props.challengeId)
    return response.status === 'running'
  } catch (error) {
    console.error('检查容器状态失败:', error)
    return false
  }
}

// 开始检查容器就绪状态
const startContainerReadinessCheck = () => {
  console.log('[容器] 开始就绪检查...')

  // 重置状态
  containerReadyState.value = 'checking'
  startupProgress.value = 0

  console.log('[容器] 状态已设置为 checking')

  // 模拟启动进度 - 3个阶段
  let progress = 0
  let currentStage = 0 // 0:分配端口, 1:配置代理, 2:启动成功
  const stages = [
    { threshold: 33, duration: 3000 },  // 分配端口：3秒
    { threshold: 66, duration: 3000 },  // 配置代理：3秒
    { threshold: 95, duration: 4000 },  // 启动服务：4秒
  ]

  let startTime = Date.now()

  startupProgressTimer = setInterval(() => {
    const elapsed = Date.now() - startTime

    // 根据时间计算进度
    if (currentStage < stages.length) {
      const stage = stages[currentStage]
      const stageProgress = Math.min(elapsed / stage.duration, 1) * (stage.threshold - (currentStage > 0 ? stages[currentStage - 1].threshold : 0))
      progress = (currentStage > 0 ? stages[currentStage - 1].threshold : 0) + stageProgress

      if (progress >= stage.threshold) {
        currentStage++
        startTime = Date.now() // 重置开始时间
      }
    }

    startupProgress.value = Math.min(95, Math.floor(progress))
    console.log(`[容器] 进度更新: ${startupProgress.value}% (阶段: ${currentStage})`)
  }, 100)

  // 每1秒检查一次容器是否就绪
  let checkAttempts = 0
  const maxAttempts = 30 // 最多检查30次（30秒）

  readinessCheckTimer = setInterval(async () => {
    checkAttempts++

    console.log(`[容器] 检查就绪 ${checkAttempts}/${maxAttempts}`)

    if (checkAttempts >= maxAttempts) {
      // 超时，显示访问URL
      console.log('[容器] 超时，显示访问URL')
      finishStartupProgress(true)
      return
    }

    const isReady = await checkContainerReadiness()
    console.log(`[容器] 就绪状态: ${isReady}`)

    if (isReady) {
      // 容器就绪
      console.log('[容器] 容器已就绪，显示访问URL')
      finishStartupProgress(true)
    }
  }, 1000)
}

// 完成启动进度
const finishStartupProgress = (showUrl = true) => {
  // 清理检查定时器
  clearInterval(readinessCheckTimer)
  clearInterval(startupProgressTimer)
  readinessCheckTimer = null
  startupProgressTimer = null

  // 设置为100%
  startupProgress.value = 100

  // 延迟一点显示就绪状态
  setTimeout(() => {
    if (showUrl) {
      containerReadyState.value = 'ready'
      // 启动倒计时
      startCountdown()
    } else {
      containerReadyState.value = 'idle'
    }
  }, 500)
}

// 停止容器就绪检查
const stopContainerReadinessCheck = () => {
  if (readinessCheckTimer) {
    clearInterval(readinessCheckTimer)
    readinessCheckTimer = null
  }
  if (startupProgressTimer) {
    clearInterval(startupProgressTimer)
    startupProgressTimer = null
  }
}

const fetchChallenge = async () => {
  loading.value = true
  try {
    challenge.value = await challengeStore.fetchChallengeDetail(props.challengeId)
    // 获取容器状态
    if (challenge.value?.docker_image && userStore.isAuthenticated) {
      await fetchContainerStatus()
    }
  } catch (error) {
    console.error('获取题目详情失败:', error)
    message.value = '获取题目失败'
    messageType.value = 'error'
  } finally {
    loading.value = false
  }
}

const fetchContainerStatus = async () => {
  if (!userStore.isAuthenticated) return
  try {
    const response = await api.challenge.getContainer(props.challengeId)
    containerInfo.value = response

    // 如果容器已经在运行，直接设置为ready状态
    if (response.status === 'running') {
      containerReadyState.value = 'ready'
      startCountdown()
    } else {
      containerReadyState.value = 'idle'
    }
  } catch (error) {
    console.error('获取容器状态失败:', error)
  }
}

const handleStartContainer = async () => {
  if (!userStore.isAuthenticated) {
    message.value = '请先登录'
    messageType.value = 'error'
    return
  }

  startingContainer.value = true
  message.value = ''

  try {
    // 检查容器是否已经在运行
    if (containerReadyState.value === 'ready' && containerInfo.value?.is_running) {
      message.value = '容器已在运行中，无需重复启动'
      messageType.value = 'info'
      startingContainer.value = false
      return
    }

    const result = await api.challenge.startContainer(props.challengeId)
    if (result.success) {
      message.value = result.message
      messageType.value = 'success'
      containerInfo.value = result.container

      // 开始检查容器就绪状态
      startContainerReadinessCheck()
    } else {
      message.value = result.message
      messageType.value = 'error'
    }
  } catch (error) {
    message.value = '启动容器失败，请稍后重试'
    messageType.value = 'error'
  } finally {
    startingContainer.value = false
  }
}

const handleStopContainer = async () => {
  stoppingContainer.value = true
  message.value = ''

  try {
    const result = await api.challenge.stopContainer(props.challengeId)
    if (result.success) {
      message.value = result.message
      messageType.value = 'success'
      containerInfo.value = null

      // 停止所有定时器
      stopCountdown()
      stopContainerReadinessCheck()
      remainingTime.value = 0
      containerReadyState.value = 'idle'
      startupProgress.value = 0
    } else {
      message.value = result.message
      messageType.value = 'error'
    }
  } catch (error) {
    message.value = '停止容器失败，请稍后重试'
    messageType.value = 'error'
  } finally {
    stoppingContainer.value = false
  }
}

const copyAccessUrl = async () => {
  if (!containerInfo.value?.access_url) return

  try {
    await navigator.clipboard.writeText(containerInfo.value.access_url)
    message.value = '访问地址已复制到剪贴板'
    messageType.value = 'success'
  } catch (error) {
    // 如果剪贴板 API 不可用，使用传统的复制方法
    const textarea = document.createElement('textarea')
    textarea.value = containerInfo.value.access_url
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()

    try {
      document.execCommand('copy')
      message.value = '访问地址已复制到剪贴板'
      messageType.value = 'success'
    } catch (e) {
      message.value = '复制失败，请手动复制'
      messageType.value = 'error'
    }

    document.body.removeChild(textarea)
  }
}

const handleClose = () => {
  emit('close')
}

const handleSubmit = async () => {
  if (!flagInput.value.trim()) {
    message.value = '请输入 flag'
    messageType.value = 'error'
    return
  }

  submitting.value = true
  message.value = ''

  try {
    const result = await challengeStore.submitFlag(props.challengeId, flagInput.value)
    if (result.success) {
      message.value = result.message
      messageType.value = 'success'
      flagInput.value = ''
      await fetchChallenge()
      await userStore.fetchProfile()
    } else {
      message.value = result.message
      messageType.value = 'error'
    }
  } catch (error) {
    message.value = '提交失败，请稍后重试'
    messageType.value = 'error'
  } finally {
    submitting.value = false
  }
}

// 监听容器状态变化，启动或停止倒计时
watch(() => containerInfo.value?.status, (newStatus, oldStatus) => {
  if (newStatus === 'running' && oldStatus !== 'running') {
    // 容器状态变化为运行，但不立即启动倒计时
    // 等待就绪检查完成后再启动
    if (containerReadyState.value !== 'checking') {
      containerReadyState.value = 'ready'
      startCountdown()
    }
  } else if (newStatus !== 'running') {
    stopCountdown()
    stopContainerReadinessCheck()
    remainingTime.value = 0
    containerReadyState.value = 'idle'
    startupProgress.value = 0
  }
})

// 组件卸载时清理所有定时器
onUnmounted(() => {
  stopCountdown()
  stopContainerReadinessCheck()
})

watch(() => props.challengeId, (newId) => {
  if (newId) {
    message.value = ''
    messageType.value = ''
    flagInput.value = ''
    stopCountdown()
    stopContainerReadinessCheck()
    fetchChallenge()
  }
}, { immediate: true })
</script>

<style scoped>
.challenge-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2000;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.modal-container {
  width: 100%;
  max-width: 900px;
  max-height: 90vh;
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
  animation: slideUp 0.3s ease;
  position: relative;
}

@keyframes slideUp {
  from {
    transform: translateY(30px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.modal-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  gap: 12px;
  color: var(--text-secondary);
}

.loading-spinner {
  width: 36px;
  height: 36px;
  border: 4px solid #f0f0f0;
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.close-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 32px;
  height: 32px;
  border: none;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 50%;
  font-size: 18px;
  cursor: pointer;
  transition: all 0.3s;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
}

.close-btn:hover {
  background: rgba(0, 0, 0, 0.1);
  color: var(--error-color);
  transform: rotate(90deg);
}

.modal-content {
  display: grid;
  grid-template-columns: 1fr 340px;
  height: 90vh;
  overflow: hidden;
}

@media (max-width: 768px) {
  .modal-content {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr auto;
  }
}

.challenge-section {
  padding: 24px;
  overflow-y: auto;
  border-right: 1px solid #f0f0f0;
}

@media (max-width: 768px) {
  .challenge-section {
    border-right: none;
    border-bottom: 1px solid #f0f0f0;
  }
}

.challenge-header {
  border-bottom: 2px solid #f0f0f0;
  padding-bottom: 16px;
  margin-bottom: 20px;
}

.challenge-title {
  font-size: 22px;
  font-weight: bold;
  color: var(--text-primary);
  margin-bottom: 12px;
  line-height: 1.3;
}

.challenge-badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.badge {
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 600;
  color: white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.badge-easy {
  background: linear-gradient(135deg, #52c41a 0%, #73d13d 100%);
}

.badge-medium {
  background: linear-gradient(135deg, #faad14 0%, #ffc53d 100%);
}

.badge-hard {
  background: linear-gradient(135deg, #ff4d4f 0%, #ff7875 100%);
}

.badge-expert {
  background: linear-gradient(135deg, #7235d2 0%, #9254de 100%);
}

.badge-primary {
  background: linear-gradient(135deg, #1890ff 0%, #40a9ff 100%);
}

.badge-success {
  background: linear-gradient(135deg, #52c41a 0%, #73d13d 100%);
}

.section-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.challenge-description {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
  margin-bottom: 20px;
  padding: 16px;
  background: #fafafa;
  border-radius: var(--radius-sm);
  border-left: 4px solid var(--primary-color);
}

.challenge-hint {
  margin-bottom: 20px;
}

.hint-content {
  background: linear-gradient(135deg, #fffbe6 0%, #fff7cc 100%);
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  border-left: 4px solid var(--warning-color);
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
}

.challenge-attachment {
  margin-bottom: 20px;
}

.challenge-guidance {
  margin-bottom: 20px;
  padding: 16px;
  background: linear-gradient(180deg, #f8fbff 0%, #f4f9ff 100%);
  border: 1px solid #d6e4ff;
  border-radius: var(--radius-sm);
}

.guidance-intro {
  margin: 0 0 14px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.guidance-group + .guidance-group {
  margin-top: 16px;
}

.guidance-group-title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.guidance-card {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  background: white;
  border: 1px solid #e6f4ff;
  border-radius: 10px;
}

.guidance-card + .guidance-card {
  margin-top: 10px;
}

.guidance-card-body {
  min-width: 0;
  flex: 1;
}

.guidance-card-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.5;
}

.guidance-card-reason {
  margin-top: 4px;
  font-size: 12px;
  color: #1d39c4;
  line-height: 1.5;
}

.guidance-card-summary {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.guidance-card-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-secondary);
}

.guidance-card-link {
  flex-shrink: 0;
  align-self: center;
  padding: 8px 12px;
  background: #e6f4ff;
  color: #0958d9;
  text-decoration: none;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
}

.guidance-card-link:hover {
  background: #d6e4ff;
}

.attachment-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%);
  color: var(--primary-color);
  border-radius: var(--radius-sm);
  text-decoration: none;
  transition: all 0.3s;
  font-size: 13px;
  font-weight: 500;
  box-shadow: 0 2px 8px rgba(24, 144, 255, 0.15);
}

.attachment-link:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.25);
}

.attachment-icon {
  font-size: 16px;
}

.submit-section {
  padding: 24px;
  background: #fafafa;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

.success-banner {
  padding: 16px;
  background: linear-gradient(135deg, #f6ffed 0%, #d9f7be 100%);
  border-radius: var(--radius-sm);
  border: 2px solid #b7eb8f;
  display: flex;
  align-items: center;
  gap: 12px;
}

.success-icon {
  font-size: 32px;
  animation: bounce 1s ease infinite;
}

@keyframes bounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

.success-text h3 {
  font-size: 14px;
  font-weight: bold;
  color: #52c41a;
  margin: 0 0 4px 0;
}

.success-text p {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.submit-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.submit-form .input {
  width: 100%;
}

.submit-message {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  animation: slideDown 0.3s ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.submit-message.success {
  background: #f6ffed;
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.submit-message.error {
  background: #fff1f0;
  color: #ff4d4f;
  border: 1px solid #ffccc7;
}

.message-icon {
  font-weight: bold;
  font-size: 14px;
}

.submit-hint {
  padding: 10px;
  background: #e6f7ff;
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--text-secondary);
}

.submit-hint p {
  margin: 0;
}

/* 容器相关样式 */
.challenge-container {
  margin-top: 20px;
  padding: 16px;
  background: #f5f5f5;
  border-radius: var(--radius-sm);
  border: 1px solid #e8e8e8;
}

.container-info {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.container-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
}

.status-icon {
  font-size: 16px;
}

.status-idle {
  background: #f5f5f5;
  color: var(--text-secondary);
}

.status-pending {
  background: #fff7e6;
  color: #fa8c16;
}

.status-running {
  background: #f6ffed;
  color: #52c41a;
}

.status-stopped {
  background: #f5f5f5;
  color: var(--text-secondary);
}

.status-destroyed {
  background: #f5f5f5;
  color: var(--text-secondary);
}

.status-error {
  background: #fff1f0;
  color: #ff4d4f;
}

/* 启动进度框样式 */
.startup-progress-box {
  padding: 16px;
  background: linear-gradient(135deg, #fff7e6 0%, #ffe7ba 100%);
  border-radius: var(--radius-sm);
  border: 2px solid #ffd591;
  margin-bottom: 12px;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.progress-icon {
  font-size: 18px;
  animation: spin 2s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.progress-label {
  font-size: 13px;
  color: var(--text-secondary);
  flex: 1;
  font-weight: 500;
}

.progress-percent {
  font-size: 14px;
  font-weight: bold;
  color: var(--warning-color);
  font-family: monospace;
}

.progress-bar {
  height: 8px;
  background: rgba(250, 140, 22, 0.1);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 16px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #fa8c16 0%, #ffa940 100%);
  border-radius: 4px;
  transition: width 0.5s ease;
  animation: shimmer 2s infinite;
}

@keyframes shimmer {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}

.progress-steps {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.progress-step {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  opacity: 0.3;
  transition: all 0.3s ease;
}

.progress-step.active {
  opacity: 1;
}

.progress-step.current {
  opacity: 1;
  background: rgba(250, 140, 22, 0.1);
  padding: 4px;
  border-radius: 8px;
}

.step-icon {
  font-size: 20px;
  transition: transform 0.3s ease;
}

.progress-step.active .step-icon {
  transform: scale(1.2);
}

.progress-step.current .step-icon {
  transform: scale(1.3);
  animation: bounce 0.5s ease infinite;
}

@keyframes bounce {
  0%, 100% {
    transform: scale(1.3);
  }
  50% {
    transform: scale(1.5);
  }
}

.step-text {
  font-size: 10px;
  color: var(--text-secondary);
  font-weight: 500;
}

.progress-step.current .step-text {
  color: var(--warning-color);
  font-weight: 600;
}

/* 倒计时样式 */
.countdown-box {
  padding: 16px;
  background: linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%);
  border-radius: var(--radius-sm);
  border: 2px solid #91d5ff;
  margin-bottom: 12px;
}

.countdown-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.countdown-icon {
  font-size: 18px;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.countdown-label {
  font-size: 13px;
  color: var(--text-secondary);
  flex: 1;
}

.countdown-time {
  font-size: 24px;
  font-weight: bold;
  color: var(--primary-color);
  font-family: monospace;
  letter-spacing: 2px;
}

.countdown-progress-bar {
  height: 6px;
  background: rgba(24, 144, 255, 0.1);
  border-radius: 3px;
  overflow: hidden;
}

.countdown-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #1890ff 0%, #52c41a 100%);
  border-radius: 3px;
  transition: width 1s linear;
}

/* 访问地址样式优化 */
.access-url-box {
  padding: 12px 14px;
  background: white;
  border-radius: var(--radius-sm);
  border: 2px solid #d9d9d9;
  margin-bottom: 12px;
}

.access-url-label {
  font-size: 12px;
  color: var(--text-secondary);
  display: block;
  margin-bottom: 8px;
}

.access-url-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.access-url-link {
  flex: 1;
  min-width: 0;
  color: var(--primary-color);
  text-decoration: none;
  font-size: 13px;
  font-family: 'Consolas', 'Monaco', monospace;
  word-break: break-all;
  display: flex;
  align-items: center;
  padding: 6px 10px;
  background: #f0f9ff;
  border-radius: 6px;
  border: 1px solid #d6e4ff;
  transition: all 0.2s;
}

.access-url-link:hover {
  background: #e6f7ff;
  border-color: #adc6ff;
  text-decoration: none;
  transform: translateX(2px);
}

.btn-copy {
  padding: 6px 10px;
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-copy:hover {
  background: #40a9ff;
  transform: scale(1.05);
}

.btn-copy:active {
  transform: scale(0.95);
}

/* 全宽按钮 */
.btn-full {
  width: 100%;
}

/* 容器操作区域间距优化 */
.container-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
