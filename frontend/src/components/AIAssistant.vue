<template>
  <div class="ai-assistant-container">
    <div class="ai-header">
      <div class="ai-title">
        <span class="ai-icon">🤖</span>
        <span>AI助手</span>
      </div>
      <button
        class="ai-toggle-btn"
        :class="{ active: isOpen }"
        @click="toggleAssistant"
      >
        {{ isOpen ? '收起' : '展开' }}
      </button>
    </div>

    <div v-show="isOpen" class="ai-body">
      <div v-if="hasReadingGuidance" class="guidance-banner">
        <div class="guidance-banner-title">阅读导引</div>
        <div class="guidance-banner-text">
          如果你想继续巩固，可以查看题目详情里的“相关阅读”和“相关资源”。
        </div>
      </div>

      <div class="messages-container" ref="messagesContainer">
        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-icon">💬</div>
          <p>我是你的 AI 解题助手</p>
          <p>遇到困难时可以问我</p>
        </div>

        <div
          v-for="msg in messages"
          :key="msg.id"
          class="message-item"
          :class="msg.role"
        >
          <div class="message-avatar">
            {{ msg.role === 'user' ? '🧑' : '🤖' }}
          </div>
          <div class="message-content">
            <div class="message-text" v-html="formatMessage(msg.content)"></div>
            <div class="message-time">{{ formatTime(msg.timestamp) }}</div>
          </div>
        </div>

        <div v-if="isTyping" class="message-item assistant">
          <div class="message-avatar">🤖</div>
          <div class="message-content">
            <div class="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        </div>
      </div>

      <div class="mode-selector">
        <a-radio-group v-model="chatMode" type="button" size="small">
          <a-radio value="single">单智能体</a-radio>
          <a-radio value="multi">多智能体协作</a-radio>
          <a-radio value="tutoring">教学授课</a-radio>
        </a-radio-group>
      </div>

      <div class="input-container">
        <textarea
          ref="inputArea"
          v-model="inputMessage"
          class="input-area"
          placeholder="输入你的问题..."
          rows="1"
          :disabled="isTyping"
          @keydown.enter.prevent="handleEnter"
        ></textarea>
        <button
          class="send-btn"
          :disabled="!inputMessage.trim() || isTyping"
          @click="sendMessage"
        >
          <span v-if="isTyping">...</span>
          <span v-else>发送</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

const props = defineProps({
  challengeId: {
    type: [Number, String],
    required: true,
  },
  challengeInfo: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['open', 'chatMode'])

const isOpen = ref(false)
const inputMessage = ref('')
const messages = ref([])
const isTyping = ref(false)
const conversationId = ref(null)
const messagesContainer = ref(null)
const inputArea = ref(null)
const chatMode = ref('single')

const hasReadingGuidance = computed(() => {
  const articles = props.challengeInfo?.recommended_articles || []
  const resources = props.challengeInfo?.recommended_resources || []
  return articles.length > 0 || resources.length > 0
})

const formatMessage = (content) => {
  const safeContent = String(content || '')
  return safeContent
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

const formatTime = (timestamp) => {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return date.toLocaleDateString()
}

const toggleAssistant = () => {
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    emit('open')
    loadConversation()
  }
}

const loadConversation = async () => {
  try {
    const token = localStorage.getItem('token')
    const response = await fetch('http://localhost:8000/api/ai/conversations/', {
      headers: {
        Authorization: `Token ${token}`,
      },
    })

    if (!response.ok) return

    const conversations = await response.json()
    const relevantConversation = conversations.find((item) => item.challenge_id == props.challengeId)
    if (relevantConversation) {
      conversationId.value = relevantConversation.id
      await loadMessages(relevantConversation.id)
    }
  } catch (error) {
    console.error('加载对话失败:', error)
  }
}

const loadMessages = async (convId) => {
  try {
    const token = localStorage.getItem('token')
    const response = await fetch(`http://localhost:8000/api/ai/conversations/${convId}/messages/`, {
      headers: {
        Authorization: `Token ${token}`,
      },
    })

    if (!response.ok) return

    messages.value = await response.json()
    scrollToBottom()
  } catch (error) {
    console.error('加载消息失败:', error)
  }
}

const createConversation = async () => {
  try {
    const token = localStorage.getItem('token')
    const response = await fetch('http://localhost:8000/api/ai/conversations/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Token ${token}`,
      },
      body: JSON.stringify({ challenge_id: props.challengeId }),
    })

    if (!response.ok) return

    const data = await response.json()
    conversationId.value = data.id
  } catch (error) {
    console.error('创建对话失败:', error)
  }
}

const sendMessage = async () => {
  const content = inputMessage.value.trim()
  if (!content || isTyping.value) return

  if (!conversationId.value) {
    await createConversation()
  }

  inputMessage.value = ''

  messages.value.push({
    id: Date.now(),
    role: 'user',
    content,
    timestamp: new Date().toISOString(),
  })
  scrollToBottom()

  isTyping.value = true

  try {
    const token = localStorage.getItem('token')
    const response = await fetch(`http://localhost:8000/api/ai/conversations/${conversationId.value}/chat/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Token ${token}`,
      },
      body: JSON.stringify({ message: content }),
    })

    if (!response.ok) {
      throw new Error('发送失败')
    }

    const data = await response.json()
    messages.value.push({
      id: Date.now() + 1,
      role: 'assistant',
      content: data.content,
      timestamp: data.timestamp,
    })
    scrollToBottom()
  } catch (error) {
    console.error('发送消息失败:', error)
    messages.value.push({
      id: Date.now() + 1,
      role: 'assistant',
      content: '抱歉，我遇到了一些问题，请稍后再试。',
      timestamp: new Date().toISOString(),
    })
  } finally {
    isTyping.value = false
    scrollToBottom()
  }
}

const handleEnter = (event) => {
  if (event.shiftKey) return
  sendMessage()
}

const scrollToBottom = async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

watch(inputMessage, () => {
  if (inputArea.value) {
    inputArea.value.style.height = 'auto'
    inputArea.value.style.height = `${Math.min(inputArea.value.scrollHeight, 120)}px`
  }
})

watch(
  () => props.challengeId,
  () => {
    conversationId.value = null
    messages.value = []
  },
)

watch(chatMode, (value) => {
  emit('chatMode', value)
})

onMounted(() => {
  isOpen.value = true
})
</script>

<style scoped>
.ai-assistant-container {
  border: 3px solid #1890ff;
  border-radius: 12px;
  margin-top: 30px;
  background: white;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.3);
}

.ai-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%);
  border-bottom: 2px solid #1890ff;
}

.ai-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 18px;
  font-weight: 700;
  color: #1890ff;
}

.ai-icon {
  font-size: 24px;
}

.ai-toggle-btn {
  padding: 6px 16px;
  border: 1px solid #d9d9d9;
  background: white;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.3s;
}

.ai-toggle-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.ai-toggle-btn.active {
  background: var(--primary-color);
  border-color: var(--primary-color);
  color: white;
}

.ai-body {
  display: flex;
  flex-direction: column;
  height: 400px;
}

.guidance-banner {
  padding: 12px 16px;
  background: linear-gradient(135deg, #fff9e6 0%, #fff1b8 100%);
  border-bottom: 1px solid #ffe58f;
}

.guidance-banner-title {
  font-size: 12px;
  font-weight: 700;
  color: #ad6800;
}

.guidance-banner-text {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #8c6d1f;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.6;
}

.empty-state p {
  margin: 4px 0;
  font-size: 14px;
}

.message-item {
  display: flex;
  gap: 12px;
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-item.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
  background: #f0f0f0;
}

.message-item.user .message-avatar {
  background: var(--primary-color);
}

.message-content {
  max-width: 70%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.message-text {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
  background: #f5f5f5;
  color: var(--text-primary);
}

.message-item.user .message-text {
  background: var(--primary-color);
  color: white;
}

.message-time {
  font-size: 11px;
  color: var(--text-secondary);
}

.message-item.user .message-time {
  text-align: right;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
  background: #f5f5f5;
  border-radius: 12px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ccc;
  animation: typing 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%,
  60%,
  100% {
    transform: translateY(0);
  }

  30% {
    transform: translateY(-10px);
  }
}

.mode-selector {
  display: flex;
  justify-content: center;
  padding: 10px 16px 0;
  border-top: 1px solid #f0f0f0;
}

.input-container {
  display: flex;
  gap: 8px;
  padding: 16px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}

.input-area {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #d9d9d9;
  border-radius: 8px;
  font-size: 14px;
  resize: none;
  outline: none;
  transition: border-color 0.3s;
  font-family: inherit;
  min-height: 40px;
  max-height: 120px;
}

.input-area:focus {
  border-color: var(--primary-color);
}

.input-area:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.send-btn {
  padding: 10px 20px;
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s;
  white-space: nowrap;
}

.send-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.message-text :deep(code) {
  padding: 2px 6px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
}

.message-item.user .message-text :deep(code) {
  background: rgba(255, 255, 255, 0.2);
}

.message-text :deep(strong) {
  font-weight: 600;
}
</style>
