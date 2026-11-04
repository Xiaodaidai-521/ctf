<template>
  <div class="ai-tutor-chat">
    <!-- 顶部步骤进度条 -->
    <div class="tutor-steps">
      <a-steps :current="currentStep" size="small" type="arrow">
        <a-step>评估</a-step>
        <a-step>讲解</a-step>
        <a-step>练习</a-step>
        <a-step>检验</a-step>
      </a-steps>
    </div>

    <!-- 消息列表 -->
    <div class="messages-area" ref="messagesRef">
      <div v-if="!messages || messages.length === 0" class="empty-state">
        <div class="empty-icon"><AppIcon name="bi-book" /></div>
        <p>开始你的学习之旅</p>
        <p class="hint">AI 导师将引导你完成学习</p>
      </div>

      <div
        v-for="msg in messages"
        :key="msg.id"
        class="message-item"
        :class="msg.type"
      >
        <!-- 用户消息 -->
        <template v-if="msg.type === 'user'">
          <div class="message-content user-message">
            <div class="text">{{ msg.content }}</div>
            <span class="time">{{ formatTime(msg.timestamp) }}</span>
          </div>
        </template>

        <!-- 导师消息（复用 MultiAgentChat 气泡样式） -->
        <template v-else-if="msg.type === 'tutor'">
          <div class="tutor-avatar"><AppIcon name="bi-cpu" /></div>
          <div class="message-content tutor-message">
            <div class="message-label-row">
              <span class="tutor-label">{{ msg.agent_name || 'AI导师' }}</span>
              <span v-if="msg.step" class="step-badge">步骤 {{ msg.step }}</span>
              <span class="time">{{ formatTime(msg.timestamp) }}</span>
            </div>
            <div class="text" v-html="renderMarkdown(msg.content)"></div>
          </div>
        </template>

        <!-- 系统消息 -->
        <template v-else-if="msg.type === 'system'">
          <div class="system-message">
            <span class="icon"><AppIcon name="bi-lightning-charge" /></span>
            {{ msg.content }}
          </div>
        </template>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <div class="input-row">
        <a-textarea
          v-model="inputText"
          placeholder="输入你的回答或问题..."
          :auto-size="{ minRows: 1, maxRows: 4 }"
          @keydown.enter.ctrl="handleSend"
        />
        <a-button type="primary" @click="handleSend" :disabled="!inputText.trim()">
          发送
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { marked } from 'marked'
import { sanitizeHtml } from '@/utils/sanitize'

const props = defineProps({
  messages: {
    type: Array,
    default: () => []
  },
  currentStep: {
    type: Number,
    default: 0
  }
})

const emit = defineEmits(['send-message'])

const inputText = ref('')
const messagesRef = ref(null)

const formatTime = (ts) => {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const renderMarkdown = (content) => {
  if (!content) return ''
  return sanitizeHtml(marked.parse(content))
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

const handleSend = () => {
  const text = inputText.value.trim()
  if (!text) return
  emit('send-message', text)
  inputText.value = ''
}

watch(() => props.messages, () => {
  scrollToBottom()
}, { deep: true })

onMounted(() => {
  scrollToBottom()
})
</script>

<style scoped>
.ai-tutor-chat {
  display:flex;
  flex-direction:column;
  height:100%;
  background:var(--color-bg-1);
  border-radius:var(--radius-control);
  overflow:hidden;
}

/* 步骤条 */
.tutor-steps {
  padding:var(--space-1) var(--space-2);
  background:var(--color-bg-2);
  border-bottom:var(--stroke) solid var(--color-border);
  flex-shrink:0;
}

/* 消息区域 */
.messages-area {
  flex:1;
  overflow-y:auto;
  padding:var(--space-2);
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
  min-height:0;
}

.messages-area::-webkit-scrollbar {
  width:calc(var(--space-1) / 2);
}
.messages-area::-webkit-scrollbar-track {
  background:transparent;
}
.messages-area::-webkit-scrollbar-thumb {
  background:var(--color-fill-3);
  border-radius:var(--radius-control);
}

.empty-state {
  flex:1;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  color:var(--color-text-3);
}

.empty-icon {
  font-size:var(--text-page);
  margin-bottom:var(--space-2);
  opacity:0.5;
}

.hint {
  font-size:var(--text-caption);
  margin-top:var(--space-1);
}

/* 消息项 */
.message-item {
  display:flex;
  gap:var(--space-1);
}

.message-item.user {
  flex-direction:row-reverse;
}

.message-content {
  max-width:70%;
  padding:var(--space-1) var(--space-2);
  border-radius:var(--radius-panel);
  background:var(--color-bg-2);
}

.user-message {
  background:var(--action);
  color:var(--on-action);
}

/* 标签行（对齐 MultiAgentChat 样式） */
.message-label-row {
  display:flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  margin-bottom:var(--space-1);
  font-size:var(--text-caption);
}

.tutor-label {
  padding:calc(var(--stroke) * 2) var(--space-1);
  background:var(--action);
  color:var(--on-action);
  border-radius:var(--radius-control);
  font-weight: var(--weight-medium);
  font-size:var(--text-caption);
}

.step-badge {
  padding:var(--stroke) var(--space-1);
  background:var(--warning);
  color:var(--on-action);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.time {
  margin-left:auto;
  font-size:var(--text-caption);
  color:var(--color-text-3);
  white-space:nowrap;
}

.tutor-avatar {
  width:var(--space-4);
  height:var(--space-4);
  border-radius:var(--radius-control);
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:var(--text-card);
  flex-shrink:0;
  background:var(--action);
}

.text {
  line-height:1.6;
}

.text:deep(p) { margin:0 0 var(--space-1); }
.text:deep(p:last-child) { margin:0; }
.text:deep(code) {
  background:var(--surface-muted);
  padding:calc(var(--stroke) * 2) calc(var(--space-1) / 2);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
}
.text:deep(pre) {
  background:var(--color-bg-3);
  padding:var(--space-1);
  border-radius:var(--radius-control);
  overflow-x:auto;
}

.system-message {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  padding:var(--space-1) var(--space-2);
  background:var(--color-fill-1);
  border-radius:var(--radius-panel);
  font-size:var(--text-caption);
  color:var(--color-text-2);
  margin:0 auto;
}

.system-message .icon {
  font-size:var(--text-body);
}

/* 输入区域 */
.input-area {
  padding:var(--space-1) var(--space-2);
  background:var(--color-bg-2);
  border-top:var(--stroke) solid var(--color-border);
  flex-shrink:0;
}

.input-row {
  display:flex;
  gap:var(--space-1);
}

.input-row:deep(.arco-textarea) {
  flex:1;
}
</style>
