<template>
  <div class="multi-agent-chat">
    <div class="chat-toolbar">
      <div class="toolbar-summary">
        <span class="summary-label">参与智能体</span>
        <div class="summary-badges">
          <span
            v-for="agent in selectedAgents"
            :key="agent.id"
            class="summary-badge"
            :style="{ background: agent.color }"
          >
            {{ agent.icon }} {{ agent.name }}
          </span>
        </div>
      </div>
    </div>

    <!-- 教学授课完成报告 -->
    <div v-if="currentTutorStep >= 4" class="tutor-report">
      <div class="report-icon">📋</div>
      <div class="report-content">
        <h4>学习报告</h4>
        <p>四步教学已完成。评估→讲解→练习→检验 闭环结束。</p>
        <p class="report-hint">你可以继续提问或切换到其他学习主题。</p>
      </div>
    </div>

    <!-- 教学授课模式步骤进度条 -->
    <div v-if="isTutorSelected || currentTutorStep > 0" class="tutor-steps-bar">
      <div
        v-for="(s, i) in ['评估', '讲解', '练习', '检验']"
        :key="i"
        class="tutor-step-item"
        :class="{ active: currentTutorStep >= i + 1, done: currentTutorStep > i + 1 }"
      >
        <span class="step-dot">{{ currentTutorStep > i + 1 ? '✓' : i + 1 }}</span>
        <span class="step-label">{{ s }}</span>
      </div>
    </div>

    <!-- 消息区域 -->
    <div class="messages-area" ref="messagesRef" :class="{ 'has-messages': messages.length > 0 }">
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon">🤖</div>
        <p>选择智能体开始协作</p>
        <p class="hint">多个智能体可以协同处理复杂任务</p>
      </div>
      
      <div v-for="(msg, index) in messages" :key="msg.id" class="message-item" :class="msg.type">
        <!-- 用户消息 -->
        <template v-if="msg.type === 'user'">
          <div class="message-content user-message">
            <div class="message-header">
              <span class="sender">你</span>
              <span class="time">{{ formatTime(msg.timestamp) }}</span>
            </div>
            <div class="text">{{ msg.content }}</div>
          </div>
        </template>
        
        <!-- 智能体消息 -->
        <template v-else-if="msg.type === 'agent'">
          <div class="agent-avatar" :style="{ background: getAgentColor(msg.agent_id) }">
            {{ getAgentIcon(msg.agent_id) }}
          </div>
          <div class="message-content agent-message">
            <!-- 标签行：[智能体名称]·[AI厂商] -->
            <div class="message-label-row">
              <span class="agent-label" :style="{ background: getAgentColor(msg.agent_id) }">
                {{ msg.agent_name }}
              </span>
              <span v-if="shouldShowProvider(msg)" class="label-separator">·</span>
              <span
                class="provider-label"
                v-if="shouldShowProvider(msg) && msg.provider"
                :style="{ background: getProviderColor(msg.provider) }"
              >
                {{ getProviderName(msg.provider) }}
              </span>
              <span v-else-if="shouldShowProvider(msg)" class="provider-label unknown">未知厂商</span>
              <span
                v-if="msg.step"
                class="step-badge"
              >{{ msg.step_name || '步骤 ' + msg.step }}</span>
              <span class="time">{{ formatTime(msg.timestamp) }}</span>
            </div>
            <div class="text" v-html="renderMarkdown(msg.content)"></div>
            
            <!-- 委托提示 -->
            <div v-if="msg.handoff" class="handoff-tag">
              <span class="arrow">→</span>
              委托给 {{ msg.handoff.to_agent_name }}
              <span class="reason">{{ msg.handoff.reason }}</span>
            </div>
            
            <!-- 操作按钮 -->
            <div class="message-actions">
              <a-button size="mini" @click="switchToAgent(getAgentById(msg.agent_id))">
                切换到此智能体
              </a-button>
              <a-button size="mini" @click="showHandoffDialog(msg.agent_id)">
                委托给其他智能体
              </a-button>
            </div>
          </div>
        </template>
        
        <!-- 系统消息 -->
        <template v-else-if="msg.type === 'system'">
          <div class="system-message">
            <span class="icon">[!]</span>
            {{ msg.content }}
          </div>
        </template>
        
        <!-- 思考中 -->
        <template v-else-if="msg.type === 'thinking'">
          <div class="agent-avatar thinking">
            {{ getAgentIcon(msg.agent_id) }}
          </div>
          <div class="thinking-message">
            <span class="agent-name">{{ msg.agent_name }}</span>
            <span class="dots">
              <span></span><span></span><span></span>
            </span>
          </div>
        </template>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <div class="current-agent" v-if="currentAgent">
        当前: <span class="badge">{{ currentAgent.icon }} {{ currentAgent.name }}</span>
      </div>
      
      <div class="input-row">
        <a-textarea
          v-model="inputText"
          placeholder="输入消息，Ctrl+Enter 发送..."
          :auto-size="{ minRows: 1, maxRows: 4 }"
          @keydown.ctrl.enter="sendMessage"
        />
        <a-button type="primary" @click="sendMessage" :loading="isProcessing" :disabled="!inputText.trim()">
          {{ isProcessing ? '处理中' : '发送' }}
        </a-button>
      </div>
      
      <!-- 快捷操作 -->
      <div class="quick-actions">
        <a-button size="small" @click="showSwitchDialog = true">切换智能体</a-button>
        <a-button size="small" @click="showHandoffDialog(currentAgent?.id)">委托任务</a-button>
        <a-button size="small" @click="clearSession">重新开始</a-button>
        <a-checkbox v-model="forceAI" style="margin-left: 12px;">专家模式</a-checkbox>
      </div>
    </div>

    <!-- 切换智能体弹窗 -->
    <a-modal v-model:visible="showSwitchDialog" title="切换智能体" :footer="false">
      <div class="agent-select-list">
        <div 
          v-for="agent in availableAgents" 
          :key="agent.id"
          class="agent-select-item"
          :class="{ current: agent.id === currentAgent?.id }"
          @click="confirmSwitch(agent)"
        >
          <div class="avatar" :style="{ background: agent.color }">{{ agent.icon }}</div>
          <div class="info">
            <div class="name">{{ agent.name }}</div>
            <div class="role">{{ agent.role }}</div>
          </div>
          <a-tag v-if="agent.status === 'thinking'" color="arcoblue">思考中</a-tag>
          <a-tag v-else-if="agent.status === 'available'" color="green">空闲</a-tag>
        </div>
      </div>
    </a-modal>

    <!-- 委托弹窗 -->
    <a-modal v-model:visible="showHandoffDialog_" title="委托任务" @ok="confirmHandoff">
      <a-form :model="handoffForm" layout="vertical">
        <a-form-item label="目标智能体">
          <a-select v-model="handoffForm.targetId">
            <a-option v-for="agent in otherAgents" :key="agent.id" :value="agent.id">
              {{ agent.icon }} {{ agent.name }} - {{ agent.role }}
            </a-option>
          </a-select>
        </a-form-item>
        <a-form-item label="委托原因">
          <a-textarea v-model="handoffForm.reason" placeholder="说明为什么需要委托..." />
        </a-form-item>
        <a-form-item label="传递上下文">
          <a-textarea v-model="handoffForm.context" placeholder="需要传递的信息..." />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { marked } from 'marked'
import api, { http } from '@/api'

const props = defineProps({
  challengeId: { type: [Number, String], default: null },
  initialAgents: { type: Array, default: () => [] },
  selectedAgentIds: { type: Array, default: () => [] },
  initialMode: { type: String, default: 'collaborative' }
})

const emit = defineEmits(['session-created', 'handoff', 'complete', 'mode-change', 'message-sent', 'agent-switch'])
const router = useRouter()

// 智能体配置，父组件会传入包含教学智能体的统一列表
const agents = ref([
  { id: 'xiaohei', name: '小黑本地AI', role: 'CTF全能助手', icon: '🤖', color: '#8b5cf6', status: 'available' },
  { id: 'analyst', name: '分析师', role: '题目拆解专家', icon: '🔍', color: '#00f5ff', status: 'available' },
  { id: 'architect', name: '架构师', role: '系统规划师', icon: '🏗️', color: '#ff00ff', status: 'available' },
  { id: 'developer', name: '开发专家', role: '代码实战派', icon: '⌨️', color: '#39ff14', status: 'available' },
  { id: 'security', name: '安全专家', role: '渗透测试老兵', icon: '🔓', color: '#ff0055', status: 'available' },
  { id: 'tester', name: '测试专家', role: '边界测试员', icon: '🧪', color: '#ff6b35', status: 'available' },
  { id: 'tutor', name: '教学智能体', role: '学习教学与四步闭环辅导', icon: '🎓', color: '#4fc3f7', status: 'available' }
])

// 监听父组件传入的智能体列表变化
watch(() => props.initialAgents, (newAgents) => {
  if (newAgents?.length) {
    agents.value = newAgents
    if (!currentAgent.value || !agents.value.find(a => a.id === currentAgent.value?.id)) {
      currentAgent.value = agents.value[0]
    }
  }
}, { deep: true })

const currentAgent = ref(null)
const messages = ref([])
const inputText = ref('')
const isProcessing = ref(false)
const collaborationMode = ref(props.initialMode || 'collaborative')
const conversationId = ref(sessionStorage.getItem('multiAgentConversationId') || null)
const sessionVersion = ref(0)
const knowledgeScope = ref(props.challengeId ? 'current' : 'category')

// 教学授课当前步骤
const currentRoundMessages = computed(() => {
  const lastUserIndex = [...messages.value].map((m, index) => ({ ...m, index }))
    .reverse()
    .find((m) => m.type === 'user')?.index
  if (lastUserIndex === undefined) return messages.value
  return messages.value.slice(lastUserIndex + 1)
})

const currentTutorStep = computed(() => {
  const agentMsgs = currentRoundMessages.value.filter(m => m.type === 'agent' && m.step)
  if (!agentMsgs.length) return 0
  return Math.max(...agentMsgs.map(m => m.step || 0))
})

// 监听模式变化，同步给父组件
watch(collaborationMode, (newVal) => {
  emit('mode-change', newVal)
})
const messagesRef = ref(null)
const showSwitchDialog = ref(false)
const showHandoffDialog_ = ref(false)
const handoffFromAgent = ref(null)

const handoffForm = ref({
  targetId: null,
  reason: '',
  context: ''
})

// 强制使用真AI开关（勾选后跳过预设答案，直接调真AI）
const forceAI = ref(false)

const availableAgents = computed(() => agents.value)
const selectedAgents = computed(() => {
  const selected = agents.value.filter((agent) => props.selectedAgentIds.includes(agent.id))
  return selected.length ? selected : agents.value.slice(0, 1)
})
const isTutorSelected = computed(() => selectedAgents.value.some((agent) => agent.id === 'tutor'))
const otherAgents = computed(() => agents.value.filter(a => a.id !== handoffFromAgent.value))

// 辅助函数
const getAgentColor = (id) => agents.value.find(a => a.id === id)?.color || '#00f5ff'
const getAgentIcon = (id) => agents.value.find(a => a.id === id)?.icon || '🤖'
const getAgentById = (id) => agents.value.find(a => a.id === id)

// 厂商名称映射
const PROVIDER_NAMES = {
  volcano: { name: '火山引擎', short: '火山', color: '#FF6D60' },
  deepseek: { name: 'DeepSeek', short: 'DeepSeek', color: '#2563EB' },
  moonshot: { name: '月之暗面', short: 'Kimi', color: '#7C3AED' },
  wenxin: { name: '文心一言', short: '文心', color: '#2563EB' },
  qwen: { name: '通义千问', short: '通义', color: '#059669' },
  spark: { name: '讯飞星火', short: '星火', color: '#DC2626' },
  preset: { name: '预设答案', short: '预设', color: '#6B7280' },
  error: { name: '错误', short: 'ERR', color: '#EF4444' },
  none: { name: '未配置', short: '--', color: '#9CA3AF' },
  fallback: { name: '本地兜底', short: '兜底', color: '#9CA3AF' },
  local_tutor: { name: '本地教学', short: '教学', color: '#4fc3f7' },
  knowledge_pack: { name: '知识包', short: '知识包', color: '#6B7280' },
}

const getProviderName = (providerId) => {
  return PROVIDER_NAMES[providerId]?.name || providerId
}

const getProviderShort = (providerId) => {
  return PROVIDER_NAMES[providerId]?.short || providerId
}

const getProviderColor = (providerId) => {
  return PROVIDER_NAMES[providerId]?.color || '#9CA3AF'
}

const shouldShowProvider = (message) => {
  const hiddenProviders = new Set(['fallback', 'local_tutor', 'knowledge_pack', 'none', 'error'])
  if (!message || hiddenProviders.has(message.provider)) return false
  if (message.agent_id === 'xiaohei' || message.agent_name === '小黑本地AI') return false
  if (message.agent_id === 'tutor' || message.agent_name === '教学智能体') return false
  return true
}

const formatTime = (ts) => {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const renderMarkdown = (content) => {
  if (!content) return ''
  return marked.parse(content)
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

const requireLogin = () => {
  if (localStorage.getItem('token')) return true
  Message.warning('请先登录后使用多智能体')
  router.push('/login')
  return false
}

const rememberConversation = (id) => {
  if (!id) return
  const value = String(id)
  conversationId.value = value
  sessionStorage.setItem('multiAgentConversationId', value)
  emit('session-created', value)
}

const restoreConversation = async () => {
  if (!localStorage.getItem('token')) return

  try {
    if (!conversationId.value) {
      const conversationList = await api.conversation.list()
      const latest = (conversationList || []).find((item) => item.message_count > 0)
      if (!latest?.id) return
      rememberConversation(latest.id)
    }

    const conversation = await api.conversation.detail(conversationId.value)
    const restoredMessages = (conversation.messages || [])
      .filter((item) => String(item.content || '').trim())
      .map((item) => {
        const metadata = item.metadata || {}
        if (item.role === 'user') {
          return {
            id: `history_${item.id}`,
            type: 'user',
            content: item.content,
            timestamp: item.created_at
          }
        }

        return {
          id: `history_${item.id}`,
          type: 'agent',
          agent_id: item.agent_id || 'tutor',
          agent_name: item.agent_name || '教学智能体',
          content: item.content,
          provider: item.provider || 'unknown',
          step: metadata.step,
          step_name: metadata.step_name,
          timestamp: item.created_at
        }
      })

    messages.value = restoredMessages
    if (restoredMessages.length) scrollToBottom()
  } catch (error) {
    console.warn('恢复会话失败:', error)
    sessionStorage.removeItem('multiAgentConversationId')
    conversationId.value = null
  }
}

// 切换智能体
const confirmSwitch = (agent) => {
  const prevAgent = currentAgent.value
  currentAgent.value = agent
  showSwitchDialog.value = false
  
  messages.value.push({
    id: uniqueId(),
    type: 'system',
    content: `已切换到 ${agent.name}`,
    timestamp: new Date().toISOString()
  })
  scrollToBottom()
  
  // 通知父组件：切换了智能体
  if (prevAgent?.id !== agent.id) {
    emit('agent-switch', { from: prevAgent, to: agent })
  }
}

const switchToAgent = (agent) => {
  if (agent) confirmSwitch(agent)
}

// 显示委托弹窗
const showHandoffDialog = (agentId) => {
  handoffFromAgent.value = agentId || currentAgent.value?.id
  handoffForm.value = { targetId: null, reason: '', context: '' }
  showHandoffDialog_.value = true
}

// 确认委托
const confirmHandoff = async () => {
  if (!handoffForm.value.targetId) {
    Message.warning('请选择目标智能体')
    return
  }
  
  const fromAgent = getAgentById(handoffFromAgent.value)
  const toAgent = getAgentById(handoffForm.value.targetId)
  
  // 标记最后一条消息
  const lastAgentMsg = [...messages.value].reverse().find(m => m.type === 'agent')
  if (lastAgentMsg) {
    lastAgentMsg.handoff = {
      to_agent_id: toAgent.id,
      to_agent_name: toAgent.name,
      reason: handoffForm.value.reason
    }
  }
  
  // 添加系统消息
  messages.value.push({
    id: uniqueId(),
    type: 'system',
    content: `${fromAgent?.name} 将任务委托给 ${toAgent.name}`,
    timestamp: new Date().toISOString()
  })
  
  // 切换到目标智能体
  currentAgent.value = toAgent
  showHandoffDialog_.value = false
  
  // 发送委托上下文
  if (handoffForm.value.context) {
    inputText.value = `[承接任务]\n${handoffForm.value.context}`
    await sendMessage()
  }
  
  emit('handoff', { from: fromAgent, to: toAgent, reason: handoffForm.value.reason })
  scrollToBottom()
}

// 唯一ID生成器（避免 Date.now() 重复）
let _msgIdCounter = 0
const uniqueId = () => `${Date.now()}_${++_msgIdCounter}`

// 暴露给父组件的方法（View 通过 ref 调用）
const setCurrentAgent = (agent) => {
  if (!agent || agent.status === 'thinking') return
  const prev = currentAgent.value
  currentAgent.value = agent
  if (prev?.id !== agent.id) {
    emit('agent-switch', { from: prev, to: agent })
  }
}

// 暴露给父组件的方法（需在 defineExpose 前定义）
const addSystemMessage = (content) => {
  messages.value.push({
    id: uniqueId(),
    type: 'system',
    content,
    timestamp: new Date().toISOString()
  })
  scrollToBottom()
}

const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms))

const naturalDelay = (response, startedAt) => {
  const elapsed = Date.now() - startedAt
  let minimum = 0
  if (response?.mode === 'challenge_solution') {
    minimum = 9000 + Math.floor(Math.random() * 3500)
  } else if (response?.mode === 'tutoring') {
    minimum = 8000 + Math.floor(Math.random() * 3000)
  } else if (response?.mode === 'preset') {
    minimum = 7500
  } else {
    const responseCount = Array.isArray(response?.responses) ? response.responses.length : 1
    minimum = 7000 + Math.min(responseCount, 4) * 1200 + Math.floor(Math.random() * 3000)
  }
  return Math.max(0, minimum - elapsed)
}

// 发送消息
const sendMessage = async () => {
  const text = inputText.value.trim()
  if (!text || isProcessing.value) return

  if (!requireLogin()) return

  if (!selectedAgents.value.length) {
    Message.warning('请至少选择一个智能体')
    return
  }

  const activeAgent = currentAgent.value && selectedAgents.value.find((agent) => agent.id === currentAgent.value.id)
    ? currentAgent.value
    : selectedAgents.value[0]
  if (activeAgent?.id !== currentAgent.value?.id) {
    currentAgent.value = activeAgent
  }

  const userMsgId = uniqueId()
  const requestVersion = sessionVersion.value
  messages.value.push({
    id: userMsgId,
    type: 'user',
    content: text,
    timestamp: new Date().toISOString()
  })

  inputText.value = ''
  scrollToBottom()

  const pendingAgents = selectedAgents.value
    .map((item) => agents.value.find((agent) => agent.id === item.id))
    .filter(Boolean)
  pendingAgents.forEach((agent) => {
    agent.status = 'thinking'
  })
  isProcessing.value = true

  const thinkingIds = pendingAgents.map((agent) => {
    const thinkingId = uniqueId()
    messages.value.push({
      id: thinkingId,
      type: 'thinking',
      agent_id: agent.id,
      agent_name: agent.name,
      timestamp: new Date().toISOString()
    })
    return thinkingId
  })
  scrollToBottom()

  try {
    const requestStartedAt = Date.now()
    const response = await callAgentAPI(
      selectedAgents.value.map((agent) => agent.id),
      text,
      activeAgent
    )

    if (requestVersion !== sessionVersion.value) return

    rememberConversation(response.conversation_id)

    const delayMs = naturalDelay(response, requestStartedAt)
    if (delayMs > 0) await wait(delayMs)

    thinkingIds.forEach((thinkingId) => {
      const idx = messages.value.findIndex((message) => message.id === thinkingId)
      if (idx > -1) messages.value.splice(idx, 1)
    })

    const agentResponses = (response.responses || []).filter((agentResp) => {
      const content = typeof agentResp?.content === 'object' && agentResp.content !== null
        ? agentResp.content.content || JSON.stringify(agentResp.content)
        : agentResp?.content
      return String(content || '').trim().length > 0
    })

    if (agentResponses.length > 0) {
      agentResponses.forEach((agentResp) => {
        let displayContent = agentResp.content
        if (typeof displayContent === 'object' && displayContent !== null) {
          displayContent = displayContent.content || JSON.stringify(displayContent)
        }

        messages.value.push({
          id: uniqueId(),
          type: 'agent',
          agent_id: agentResp.agent_id || activeAgent.id,
          agent_name: agentResp.agent_name || activeAgent.name,
          content: displayContent,
          provider: agentResp.provider,
          step: agentResp.step,
          step_name: agentResp.step_name,
          handoff: agentResp.handoff,
          timestamp: new Date().toISOString()
        })
      })
    } else {
      messages.value.push({
        id: uniqueId(),
        type: 'agent',
        agent_id: activeAgent.id,
        agent_name: activeAgent.name,
        content: response.content || '未收到有效响应',
        timestamp: new Date().toISOString()
      })
    }

    const handoffResp = agentResponses.find((responseItem) => responseItem.handoff)
    if (handoffResp?.handoff) {
      const targetAgent = getAgentById(handoffResp.handoff.to_agent_id)
      if (targetAgent) {
        currentAgent.value = targetAgent
        messages.value.push({
          id: uniqueId(),
          type: 'system',
          content: `智能体自动委托给 ${targetAgent.name}: ${handoffResp.handoff.reason}`,
          timestamp: new Date().toISOString()
        })
      }
    }

    emit('message-sent')
  } catch (error) {
    if (requestVersion !== sessionVersion.value) return

    console.error('API 调用失败:', error)
    const errorMessage = error.response?.status === 401
      ? '登录已失效，请重新登录后再试'
      : (error.response?.data?.error || error.response?.data?.detail || '请求失败，请稍后重试')
    Message.error(errorMessage)

    thinkingIds.forEach((thinkingId) => {
      const idx = messages.value.findIndex((message) => message.id === thinkingId)
      if (idx > -1) messages.value.splice(idx, 1)
    })

    messages.value.push({
      id: uniqueId(),
      type: 'agent',
      agent_id: activeAgent.id,
      agent_name: activeAgent.name,
      content: `抱歉，${errorMessage}。`,
      timestamp: new Date().toISOString()
    })
  } finally {
    if (requestVersion === sessionVersion.value) {
      pendingAgents.forEach((agent) => {
        agent.status = 'available'
      })
      isProcessing.value = false
      scrollToBottom()
    }
  }
}

const looksLikeChallengeQuestion = (message) => {
  const text = String(message || '').trim()
  return /第\s*\d+\s*题|题目\s*\d+|题\s*\d+|\d+\s*题|挑战\s*\d+|challenge\s*#?\s*\d+|#\s*\d+|id[=:\s#]*\d+/i.test(text)
}

// 调用后端 API（使用多智能体端点，不需要认证）
const callAgentAPI = async (agentIds, message, activeAgent) => {
  const shouldUseChallengeWorkflow = props.challengeId || looksLikeChallengeQuestion(message)

  if (agentIds.includes('tutor')) {
    let studentLevel = 'beginner'
    try {
      const profile = await api.studentProfile.get()
      if (profile?.preference?.difficulty_bias !== undefined) {
        const bias = profile.preference.difficulty_bias
        studentLevel = bias > 0.3 ? 'advanced' : bias < -0.3 ? 'beginner' : 'intermediate'
      }
    } catch {}

    const res = await api.learningAgent.tutoring({
      concept_name: message,
      question: message,
      student_level: studentLevel,
      conversation_id: conversationId.value
    })
    return {
      conversation_id: res.conversation_id,
      mode: 'tutoring',
      responses: (res.steps || []).map((step, index) => ({
        agent_id: 'tutor',
        agent_name: activeAgent?.id === 'tutor' ? activeAgent.name : '教学智能体',
        content: step.content || '',
        provider: step.provider || 'unknown',
        step: step.step || index + 1,
        step_name: step.step_name
      }))
    }
  }

  const requestAgentIds = shouldUseChallengeWorkflow
    ? ['analyst', 'security', 'developer', 'tester', 'xiaohei']
    : agentIds

  const res = await http.post('/ai/multi-agent/chat/', {
    message,
    agent_ids: requestAgentIds,
    mode: shouldUseChallengeWorkflow ? 'challenge_solution' : collaborationMode.value,
    challenge_id: props.challengeId || null,
    force_ai: forceAI.value,
    conversation_id: conversationId.value,
    knowledge_scope: shouldUseChallengeWorkflow ? 'current' : knowledgeScope.value
  })
  return res
}

// 清空会话
const clearSession = async () => {
  sessionVersion.value += 1
  const oldConversationId = conversationId.value
  messages.value = []
  inputText.value = ''
  isProcessing.value = false
  sessionStorage.removeItem('multiAgentConversationId')
  conversationId.value = null
  agents.value.forEach(a => a.status = 'available')

  if (oldConversationId && localStorage.getItem('token')) {
    try {
      await api.conversation.remove(oldConversationId)
    } catch (error) {
      if (error.response?.status !== 404) {
        console.warn('删除历史会话失败:', error)
        Message.warning('页面已清空，但数据库历史删除失败')
        return
      }
    }
  }

  Message.success('会话已重置')
}

defineExpose({ setCurrentAgent, addSystemMessage, clearSession })

onMounted(async () => {
  if (props.initialAgents?.length) {
    agents.value = props.initialAgents
  }
  currentAgent.value = selectedAgents.value[0] || agents.value[0]
  await restoreConversation()
})
</script>

<style scoped>
.multi-agent-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg-1);
  border-radius: 8px;
  overflow: hidden;
}

.chat-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 16px;
  background: var(--color-bg-2);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.toolbar-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.summary-label {
  font-size: 12px;
  color: var(--color-text-3);
}

.summary-badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.summary-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
}

.thinking-indicator {
  width: 6px;
  height: 6px;
  background: rgb(var(--primary-6));
  border-radius: 50%;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  scroll-behavior: smooth;
}

/* 消息少时从底部开始显示 */
.messages-area::before {
  content: '';
  flex: 1;
  min-height: 0;
}

.messages-area.has-messages::before {
  display: none;
}

.messages-area::-webkit-scrollbar {
  width: 6px;
}
.messages-area::-webkit-scrollbar-track {
  background: transparent;
}
.messages-area::-webkit-scrollbar-thumb {
  background: var(--color-fill-3);
  border-radius: 3px;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--color-text-3);
  min-height: 0;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.hint {
  font-size: 12px;
  margin-top: 8px;
}

.message-item {
  display: flex;
  gap: 12px;
}

.message-item.user {
  flex-direction: row-reverse;
}

.agent-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.agent-avatar.thinking {
  animation: pulse 1s infinite;
}

.message-content {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 12px;
  background: var(--color-bg-2);
}

.user-message {
  background: rgb(var(--primary-6));
  color: #fff;
}

.message-label-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
  font-size: 12px;
  flex-wrap: wrap;
}

.agent-label {
  padding: 2px 10px;
  border-radius: 10px;
  color: #fff;
  font-weight: 500;
  font-size: 12px;
}

.label-separator {
  color: var(--color-text-3);
  font-weight: 600;
  margin: 0 1px;
}

.provider-label {
  padding: 2px 8px;
  border-radius: 10px;
  color: #fff;
  font-size: 11px;
}

.provider-label.unknown {
  background: #9CA3AF;
}

.step-badge {
  margin-left: auto;
  padding: 1px 8px;
  background: rgb(var(--primary-6));
  color: #fff;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

/* 学习报告 */
.tutor-report {
  display: flex; gap: 12px;
  padding: 16px 20px;
  margin: 0 16px 8px;
  background: linear-gradient(135deg, #f0f5ff, #e6f7ff);
  border: 1px solid #91d5ff;
  border-radius: 10px;
  flex-shrink: 0;
}
.report-icon { font-size: 28px; }
.report-content h4 { margin: 0 0 4px; font-size: 15px; color: #0050b3; }
.report-content p { margin: 0; font-size: 13px; color: #434343; }
.report-hint { color: #8c8c8c !important; margin-top: 4px !important; }

/* 教学授课步骤进度条 */
.tutor-steps-bar {
  display: flex;
  justify-content: space-around;
  padding: 12px 16px;
  background: var(--color-bg-2);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.tutor-step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  opacity: 0.4;
  transition: opacity 0.3s;
}
.tutor-step-item.active { opacity: 1; }
.tutor-step-item.done { opacity: 0.7; }
.step-dot {
  width: 24px; height: 24px;
  border-radius: 50%;
  background: var(--color-fill-3);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600;
  transition: all 0.3s;
}
.tutor-step-item.active .step-dot { background: rgb(var(--primary-6)); color: #fff; }
.tutor-step-item.done .step-dot { background: rgb(var(--green-6)); color: #fff; }
.step-label { font-size: 13px; white-space: nowrap; }

.time {
  margin-left: auto;
  font-size: 11px;
  color: var(--color-text-3);
  white-space: nowrap;
}

.message-label-row .time {
  margin-left: 4px;
}

.text {
  line-height: 1.6;
}

.text :deep(p) { margin: 0 0 8px; }
.text :deep(p:last-child) { margin: 0; }
.text :deep(code) {
  background: rgba(0,0,0,0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}
.text :deep(pre) {
  background: var(--color-bg-3);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
}

.handoff-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(var(--warning-6), 0.1);
  border-radius: 6px;
  font-size: 12px;
  color: rgb(var(--warning-6));
}

.handoff-tag .arrow {
  font-size: 14px;
}

.handoff-tag .reason {
  margin-left: auto;
  opacity: 0.7;
}

.message-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.system-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--color-fill-1);
  border-radius: 16px;
  font-size: 13px;
  color: var(--color-text-2);
  margin: 0 auto;
}

.thinking-message {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-bg-2);
  border-radius: 12px;
}

.thinking-message .agent-name {
  color: rgb(var(--primary-6));
  font-weight: 500;
}

.dots {
  display: flex;
  gap: 4px;
}

.dots span {
  width: 6px;
  height: 6px;
  background: rgb(var(--primary-6));
  border-radius: 50%;
  animation: bounce 1.4s infinite;
}

.dots span:nth-child(2) { animation-delay: 0.2s; }
.dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-6px); }
}

.input-area {
  padding: 12px 16px;
  background: var(--color-bg-2);
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}

.current-agent {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--color-text-2);
}

.current-agent .badge {
  padding: 2px 8px;
  background: rgb(var(--primary-6));
  color: #fff;
  border-radius: 10px;
  font-size: 12px;
}

.input-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.input-row :deep(.arco-textarea) {
  flex: 1;
}

.quick-actions {
  display: flex;
  gap: 8px;
}

/* 弹窗样式 */
.agent-select-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-select-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--color-fill-1);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.agent-select-item:hover {
  background: var(--color-fill-2);
}

.agent-select-item.current {
  border: 1px solid rgb(var(--primary-6));
}

.agent-select-item .avatar {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.agent-select-item .info {
  flex: 1;
}

.agent-select-item .name {
  font-weight: 500;
}

.agent-select-item .role {
  font-size: 12px;
  color: var(--color-text-3);
}

@media (max-width: 768px) {
  .chat-toolbar {
    flex-direction: column;
  }
}
</style>
