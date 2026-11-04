<template>
  <div class="ai-assistant-container">
    <div class="ai-header">
      <div class="ai-title">
        <span class="ai-icon"><AppIcon name="bi-cpu" /></span>
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
      <p v-if="conversationError" role="alert">{{ conversationError }}</p>
      <div v-if="hasReadingGuidance" class="guidance-banner">
        <div class="guidance-banner-title">阅读导引</div>
        <div class="guidance-banner-text">
          如果你想继续巩固，可以查看题目详情里的“相关阅读”和“相关资源”。
        </div>
      </div>

      <div class="messages-container" ref="messagesContainer">
        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-icon"><AppIcon name="bi-chat-dots" /></div>
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
            <AppIcon :name="msg.role === 'user' ? 'bi-person' : 'bi-cpu'" />
          </div>
          <div class="message-content">
            <div class="message-text" v-html="formatMessage(msg.content)"></div>
            <div class="message-time">{{ formatTime(msg.timestamp) }}</div>
          </div>
        </div>

        <div v-if="isTyping" class="message-item assistant">
          <div class="message-avatar"><AppIcon name="bi-cpu" /></div>
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
          :disabled="isTyping || conversationLoading"
          @keydown.enter.prevent="handleEnter"
        ></textarea>
        <button
          class="send-btn"
          :disabled="!inputMessage.trim() || isTyping || conversationLoading || !!conversationError"
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
import { http } from '@/api'
import { sanitizeHtml } from '@/utils/sanitize'

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
const conversationLoading = ref(false)
const conversationError = ref('')
const messagesContainer = ref(null)
const inputArea = ref(null)
const chatMode = ref('single')

const hasReadingGuidance = computed(() => {
  const articles = props.challengeInfo?.recommended_articles || []
  const resources = props.challengeInfo?.recommended_resources || []
  return articles.length > 0 || resources.length > 0
})

const formatMessage = (content) => {
  const unavailable = new Set([
    '[WARNING] AI service is not configured. Please set API Key.',
    'AI service is not configured.',
  ])
  const safeContent = unavailable.has(content)
    ? '当前解题助手暂不可用，请稍后重试。'
    : String(content || '')
  return sanitizeHtml(safeContent
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>'))
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

let conversationLoad = 0
const loadConversation = async () => {
  const load = ++conversationLoad
  const challengeId = props.challengeId
  conversationLoading.value = true
  conversationError.value = ''
  try {
    let page = 1
    for (;;) {
      const data = await http.get('/ai/conversations/', { params: { page } })
      if (load !== conversationLoad || challengeId !== props.challengeId) return
      const conversations = Array.isArray(data) ? data : data.results
      const relevantConversation = conversations.find((item) => String(item.challenge_id) === String(challengeId))
      if (relevantConversation) {
        const detail = await http.get(`/ai/conversations/${relevantConversation.id}/`)
        if (load !== conversationLoad || challengeId !== props.challengeId) return
        conversationId.value = relevantConversation.id
        messages.value = detail.messages.map((message) => ({ ...message, timestamp: message.created_at }))
        scrollToBottom()
        return
      }
      if (Array.isArray(data) || !data.next) return
      page += 1
    }
  } catch (error) {
    if (load === conversationLoad && challengeId === props.challengeId) {
      conversationError.value = '暂时无法读取已有对话，请收起后重新展开再试。'
    }
    console.error('加载对话失败:', error)
  } finally {
    if (load === conversationLoad) conversationLoading.value = false
  }
}

const createConversation = async () => {
  const data = await http.post('/ai/conversations/', { challenge_id: props.challengeId })
  return data.id
}

const sendMessage = async () => {
  const content = inputMessage.value.trim()
  if (!content || isTyping.value || conversationLoading.value || conversationError.value) return

  isTyping.value = true
  const challengeId = props.challengeId
  try {
    if (!conversationId.value) {
      const id = await createConversation()
      if (challengeId !== props.challengeId) return
      conversationId.value = id
    }
    if (challengeId !== props.challengeId) return
    inputMessage.value = ''
    messages.value.push({
      id: Date.now(),
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    })
    scrollToBottom()
    const data = await http.post(`/ai/conversations/${conversationId.value}/chat/`, { message: content })
    if (challengeId !== props.challengeId) return

    if (!data) {
      throw new Error('发送失败')
    }

    messages.value.push({
      id: Date.now() + 1,
      role: 'assistant',
      content: data.content,
      timestamp: data.timestamp,
    })
    scrollToBottom()
  } catch (error) {
    console.error('发送消息失败:', error)
    if (challengeId !== props.challengeId) return
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
    loadConversation()
  },
)

watch(chatMode, (value) => {
  emit('chatMode', value)
})

onMounted(() => {
  isOpen.value = true
  loadConversation()
})
</script>

<style scoped>
.ai-assistant-container {
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-panel);
  margin-top:var(--space-4);
  background:var(--surface);
  overflow:hidden;
  box-shadow:none;
}

.ai-header {
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:var(--space-2) var(--space-2);
  background: var(--surface-muted);
  border-bottom:calc(var(--stroke) * 2) solid var(--line);
}

.ai-title {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  font-size:var(--text-card);
  font-weight: var(--weight-strong);
  color:var(--action);
}

.ai-icon {
  font-size:var(--text-section);
}

.ai-toggle-btn {
  padding:calc(var(--space-1) / 2) var(--space-2);
  border:var(--stroke) solid var(--line);
  background:var(--surface);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  color:var(--text-primary);
  cursor:pointer;
  transition:all var(--motion-normal);
}

.ai-toggle-btn:hover {
  border-color:var(--primary-color);
  color:var(--primary-color);
}

.ai-toggle-btn.active {
  background:var(--primary-color);
  border-color:var(--primary-color);
  color:var(--on-action);
}

.ai-body {
  display:flex;
  flex-direction:column;
  height:var(--chart-height);
}

.guidance-banner {
  padding:var(--space-1) var(--space-2);
  background: var(--surface-muted);
  border-bottom:var(--stroke) solid var(--line);
}

.guidance-banner-title {
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--ink-secondary);
}

.guidance-banner-text {
  margin-top:calc(var(--space-1) / 2);
  font-size:var(--text-caption);
  line-height:1.5;
  color:var(--ink-secondary);
}

.messages-container {
  flex:1;
  overflow-y:auto;
  padding:var(--space-2);
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.empty-state {
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  height:100%;
  color:var(--text-secondary);
  text-align:center;
}

.empty-icon {
  font-size:var(--text-page);
  margin-bottom:var(--space-1);
  opacity:0.6;
}

.empty-state p {
  margin:calc(var(--space-1) / 2) 0;
  font-size:var(--text-caption);
}

.message-item {
  display:flex;
  gap:var(--space-1);
  animation:slideIn var(--motion-normal) ease;
}

@keyframes slideIn {
  from {
    opacity:0;
    transform:translateY(var(--space-1));
  }

  to {
    opacity:1;
    transform:translateY(0);
  }
}

.message-item.user {
  flex-direction:row-reverse;
}

.message-avatar {
  width:var(--space-4);
  height:var(--space-4);
  border-radius:50%;
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:var(--text-card);
  flex-shrink:0;
  background:var(--surface);
}

.message-item.user .message-avatar {
  background:var(--primary-color);
}

.message-content {
  max-width:70%;
  display:flex;
  flex-direction:column;
  gap:calc(var(--space-1) / 2);
}

.message-text {
  padding:var(--space-1) var(--space-2);
  border-radius:var(--radius-panel);
  font-size:var(--text-caption);
  line-height:1.5;
  word-break:break-word;
  background:var(--surface);
  color:var(--text-primary);
}

.message-item.user .message-text {
  background:var(--primary-color);
  color:var(--on-action);
}

.message-time {
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.message-item.user .message-time {
  text-align:right;
}

.typing-indicator {
  display:flex;
  gap:calc(var(--space-1) / 2);
  padding:var(--space-1) var(--space-2);
  background:var(--surface);
  border-radius:var(--radius-panel);
}

.typing-indicator span {
  width:var(--space-1);
  height:var(--space-1);
  border-radius:50%;
  background:var(--surface-muted);
  animation:typing var(--motion-loop) infinite ease-in-out;
}

.typing-indicator span:nth-child(2) {
  animation-delay:var(--motion-normal);
}

.typing-indicator span:nth-child(3) {
  animation-delay:var(--motion-normal);
}

@keyframes typing {
  0%,
  60%,
  100% {
    transform:translateY(0);
  }

  30% {
    transform:translateY(calc(var(--space-1) * -1));
  }
}

.mode-selector {
  display:flex;
  justify-content:center;
  padding:var(--space-1) var(--space-2) 0;
  border-top:var(--stroke) solid var(--line);
}

.input-container {
  display:flex;
  gap:var(--space-1);
  padding:var(--space-2);
  border-top:var(--stroke) solid var(--line);
  background:var(--surface);
}

.input-area {
  flex:1;
  padding:var(--space-1) var(--space-2);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  resize:none;
  outline-offset:var(--focus-offset);
  transition:border-color var(--motion-normal);
  font-family: var(--font-family);
  min-height:var(--space-5);
  max-height:var(--tile-height);
}

.input-area:focus {
  border-color:var(--primary-color);
}

.input-area:disabled {
  background:var(--surface);
  cursor:not-allowed;
}

.send-btn {
  padding:var(--space-1) var(--space-2);
  background:var(--primary-color);
  color:var(--on-action);
  border:none;
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight: var(--weight-medium);
  cursor:pointer;
  transition:all var(--motion-normal);
  white-space:nowrap;
}

.send-btn:hover:not(:disabled) {
  background:var(--action-hover);
}

.send-btn:disabled {
  color:var(--disabled-ink);
  background:var(--disabled);
  cursor:not-allowed;
}

.message-text:deep(code) {
  padding:calc(var(--stroke) * 2) calc(var(--space-1) / 2);
  background:var(--surface-muted);
  border-radius:var(--radius-control);
  font-family:'Courier New', monospace;
  font-size:var(--text-caption);
}

.message-item.user .message-text:deep(code) {
  color:var(--ink);
  background:var(--surface-muted);
}

.message-text:deep(strong) {
  font-weight: var(--weight-strong);
}
</style>
