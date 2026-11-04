<template>
  <div class="multi-agent-chat">
    <div
      v-if="isTutorSelected || currentTutorStep > 0"
      class="tutor-progress-shell"
      :class="{ collapsed: tutorProgressCollapsed }"
    >
      <button class="tutor-progress-toggle" type="button" @click="tutorProgressCollapsed = !tutorProgressCollapsed">
        <span>进度</span>
        <AppIcon :name="['bi', tutorProgressCollapsed ? 'bi-chevron-down' : 'bi-chevron-up']" />
      </button>

      <div v-if="tutorProgressCollapsed" class="tutor-progress-compact">
        <span class="compact-title">教学进度</span>
        <span class="compact-step">{{ Math.min(currentTutorStep || 0, 4) }}/4</span>
        <span class="compact-hint">{{ currentTutorStep >= 4 ? '学习报告已完成' : isProcessing ? '正在组织讲解' : currentTutorStep ? '可以继续学习' : '从一个学习问题开始' }}</span>
      </div>

      <template v-else>
        <!-- 教学授课完成报告 -->
        <div v-if="currentTutorStep >= 4" class="tutor-report">
          <div class="report-icon"><AppIcon name="bi-clipboard2-check" /></div>
          <div class="report-content">
            <h4>学习报告</h4>
            <p>四步教学已完成。评估→讲解→练习→检验 闭环结束。</p>
            <p class="report-hint">你可以继续提问或切换到其他学习主题。</p>
          </div>
        </div>

        <!-- 教学授课模式步骤进度条 -->
        <div class="tutor-steps-bar">
          <div
            v-for="(s, i) in ['评估', '讲解', '练习', '检验']"
            :key="i"
            class="tutor-step-item"
            :class="{ active: currentTutorStep >= i + 1, done: currentTutorStep > i + 1 }"
          >
            <span class="step-dot"><AppIcon v-if="currentTutorStep > i + 1" name="bi-check2" /><template v-else>{{ i + 1 }}</template></span>
            <span class="step-label">{{ s }}</span>
          </div>
        </div>
      </template>
    </div>

    <!-- 消息区域 -->
    <div class="messages-area" ref="messagesRef" :class="{ 'has-messages': messages.length > 0 }">
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon"><AppIcon name="bi-cpu" /></div>
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
          <div class="agent-avatar">
            <AppIcon :name="['bi', getAgentIcon(msg.agent_id)]" />
          </div>
          <div class="message-content agent-message">
            <!-- 标签行：[智能体名称]·[AI厂商] -->
            <div class="message-label-row">
              <span class="agent-label">
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
            <RecordView v-if="msg.content && typeof msg.content === 'object'" :value="msg.content" title="回复资料" />
            <img
              v-if="msg.image_url"
              class="demo-report-image"
              :src="msg.image_url"
              alt="学习分析演示图"
            />
            <div v-if="msg.agent_id === 'tutor' && messageResources(msg).length" class="tutor-resource-panel">
              <div class="tutor-resource-panel-title">智库资料</div>
              <div
                v-for="resource in messageResources(msg)"
                :key="`${resource.type}_${resource.id}_${resource.entry}`"
                class="tutor-resource-card"
              >
                <div class="tutor-resource-card-head">
                  <span class="tutor-resource-title">{{ resource.title }}</span>
                  <span v-if="resource.ai_generated_label" class="tutor-resource-badge">
                    {{ resource.ai_generated_label }}
                  </span>
                </div>
                <div class="tutor-resource-location">
                  {{ resource.location || ('智库 / AI多模态生成 / ' + resource.title) }}
                </div>
                <p v-if="resource.summary" class="tutor-resource-summary">{{ resource.summary }}</p>
                <button type="button" class="tutor-resource-link" @click="openTutorResource(resource)">
                  跳转学习
                </button>
              </div>
            </div>
            <div v-else-if="msg.agent_id === 'tutor' && msg.noMatchedResource" class="tutor-resource-empty">
              当前未检索到匹配的智库资料
            </div>
            <details v-if="msg.agent_id !== 'tutor' && msg.rag_sources?.length" class="rag-reference-panel">
              <summary><AppIcon name="bi-journal-bookmark" /> 参考资料 {{ msg.rag_sources.length }}</summary>
              <a v-for="source in msg.rag_sources" :key="`${source.type}_${source.entry}`" :href="source.entry">
                <span>{{ source.title }}</span>
                <small>{{ source.type === 'article' ? '文章' : '资源' }}</small>
              </a>
            </details>
            <div v-if="msg.agent_id === 'legal_reviewer' && hasLegalEvidenceMeta(msg)" class="legal-evidence-note">
              已检索法规 {{ msg.legal_evidence_count || 0 }} 条，题目知识 {{ msg.challenge_knowledge_count || 0 }} 条
            </div>
            
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
            <AppIcon :name="['bi', getAgentIcon(msg.agent_id)]" />
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
        当前: <span class="badge"><AppIcon :name="['bi', currentAgent.icon]" />{{ currentAgent.name }}</span>
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
        <a-checkbox v-model="forceAI" style="margin-left:var(--space-1);">专家模式</a-checkbox>
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
          <div class="avatar"><AppIcon :name="['bi', agent.icon]" /></div>
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
              {{ agent.name }} - {{ agent.role }}
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
import { ref, computed, onMounted, onActivated, onDeactivated, onBeforeUnmount, nextTick, watch } from 'vue'
import { requestTeaching } from '@/learning/agent/request.js'
import { agentSession } from '@/learning/agent/runtime.js'
import { resetLifecycle } from '@/learning/agent/lifecycle.js'
import { takeDraft, subscribeDraft } from '@/learning/agent/draft.js'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { marked } from 'marked'
import api from '@/api'
import RecordView from '@/shared/forms/RecordView.vue'
import { useUserStore } from '@/store/user'
import { sanitizeHtml } from '@/utils/sanitize'
import {
  clearRememberedTutorResources,
  rememberTutorResources,
  tutorResourceListFromResponse
} from '@/utils/tutorResources'

const props = defineProps({
  challengeId: { type: [Number, String], default: null },
  initialAgents: { type: Array, default: () => [] },
  selectedAgentIds: { type: Array, default: () => [] },
  initialMode: { type: String, default: 'collaborative' }
})

const emit = defineEmits(['session-created', 'handoff', 'complete', 'mode-change', 'message-sent', 'agent-switch'])
const router = useRouter()
const userStore = useUserStore()

const HIDDEN_AGENT_IDS = new Set(['analyst', 'architect', 'developer', 'security', 'tester'])
const isVisibleAgent = (agent) => agent && !HIDDEN_AGENT_IDS.has(agent.id)

// 智能体配置，父组件会传入包含教学辅导师的统一列表
const agents = ref([
  { id: 'tutor', name: '教学辅导师', role: '学习教学与四步闭环辅导', icon: 'bi-mortarboard', color: 'var(--ink-secondary)', status: 'available' },
  { id: 'xiaohei', name: '小黑本地AI', role: 'CTF全能助手', icon: 'bi-cpu', color: 'var(--ink-secondary)', status: 'available' },
  { id: 'legal_reviewer', name: '法律审核师', role: '题目与靶场实验合规审查', icon: 'bi-bank', color: 'var(--ink-secondary)', status: 'available' }
])

// 监听父组件传入的智能体列表变化
watch(() => props.initialAgents, (newAgents) => {
  if (newAgents?.length) {
    agents.value = newAgents.filter(isVisibleAgent)
    if (!currentAgent.value || !agents.value.find(a => a.id === currentAgent.value?.id)) {
      currentAgent.value = agents.value[0] || null
    }
  }
}, { deep: true })

const currentAgent = ref(null)
// 协作请求独立完成；教学投影不替换协作消息、忙碌状态或持久化 ID。
const collaborationMessages = ref([])
const teachingMessages = ref([])
const messages = computed(() => isTutorSelected.value ? teachingMessages.value : collaborationMessages.value)
const inputText = ref('')
const collaborationProcessing = ref(false)
const teachingProcessing = ref(false)
const isProcessing = computed(() => isTutorSelected.value ? teachingProcessing.value : collaborationProcessing.value)
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
const tutorProgressCollapsed = ref(true)
const showHandoffDialog_ = ref(false)
const handoffFromAgent = ref(null)

const handoffForm = ref({
  targetId: null,
  reason: '',
  context: ''
})

// 强制使用真AI开关（勾选后跳过预设答案，直接调真AI）
const forceAI = ref(false)

const MODEL_STORAGE_KEY = 'learningCenterConversationModel'
const CHART_MODE_STORAGE_KEY = 'learningCenterChartMode'
const conversationModels = [
  {
    id: 'auto',
    name: '智能推荐',
    provider: 'auto',
    icon: 'bi-stars',
    desc: '保持当前会话的默认调度策略'
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    provider: 'deepseek',
    icon: 'bi-lightning-charge',
    desc: '适合推理、代码分析和安全题拆解'
  },
  {
    id: 'moonshot',
    name: 'Kimi',
    provider: 'moonshot',
    icon: 'bi-moon-stars',
    desc: '适合长上下文阅读和学习资料整理'
  },
  {
    id: 'qwen',
    name: '通义千问',
    provider: 'qwen',
    icon: 'bi-chat-square-text',
    desc: '适合中文讲解、步骤化辅导和知识问答'
  }
]

const loadConversationModel = () => {
  const storedId = sessionStorage.getItem(MODEL_STORAGE_KEY)
  return conversationModels.find((model) => model.id === storedId) || conversationModels[0]
}

const selectedConversationModel = ref(loadConversationModel())
const chartModeEnabled = ref(sessionStorage.getItem(CHART_MODE_STORAGE_KEY) === 'enabled')

const chartImageTriggers = [
  {
    keyword: '请分析我当前在SQL注入学习中遇到的具体问题',
    imageUrl: '/assets/demo_images/sql_injection_user_analysis.png?v=2'
  },
  {
    keyword: '请分析我的学习进度表',
    imageUrl: '/assets/demo_images/learning_progress_analysis.png?v=2'
  },
  {
    keyword: '请评估我对SQL注入知识的掌握情况并给出可视化总结',
    imageUrl: '/assets/demo_images/knowledge_mastery_summary.png'
  }
]

const getChartImageForMessage = (message) => {
  if (!chartModeEnabled.value) return null
  const text = String(message || '')
  return chartImageTriggers.find((item) => text.includes(item.keyword))?.imageUrl || null
}

const availableAgents = computed(() => agents.value.filter(isVisibleAgent))
const selectedAgents = computed(() => {
  const selected = availableAgents.value.filter((agent) => props.selectedAgentIds.includes(agent.id))
  return selected.length ? selected : availableAgents.value.slice(0, 1)
})
const isTutorSelected = computed(() => selectedAgents.value.some((agent) => agent.id === 'tutor'))
const otherAgents = computed(() => availableAgents.value.filter(a => a.id !== handoffFromAgent.value))

// 辅助函数
const getAgentColor = (id) => agents.value.find(a => a.id === id)?.color || 'var(--ink-secondary)'
const getAgentIcon = (id) => agents.value.find(a => a.id === id)?.icon || 'bi-cpu'
const getAgentById = (id) => agents.value.find(a => a.id === id)

// 厂商名称映射
const PROVIDER_NAMES = {
  volcano: { name: '火山引擎', short: '火山', color: 'var(--ink-secondary)' },
  deepseek: { name: 'DeepSeek', short: 'DeepSeek', color: 'var(--ink-secondary)' },
  moonshot: { name: '月之暗面', short: 'Kimi', color: 'var(--ink-secondary)' },
  wenxin: { name: '文心一言', short: '文心', color: 'var(--ink-secondary)' },
  qwen: { name: '通义千问', short: '通义', color: 'var(--ink-secondary)' },
  spark: { name: '讯飞星火', short: '星火', color: 'var(--ink-secondary)' },
  preset: { name: '预设答案', short: '预设', color: 'var(--ink-secondary)' },
  error: { name: '暂时不可用', short: '不可用', color: 'var(--negative)' },
  none: { name: '未配置', short: '--', color: 'var(--ink-secondary)' },
  fallback: { name: '参考讲解', short: '参考', color: 'var(--ink-secondary)' },
  local_tutor: { name: '本地教学', short: '教学', color: 'var(--ink-secondary)' },
  knowledge_pack: { name: '知识包', short: '知识包', color: 'var(--ink-secondary)' },
}

const getProviderName = (providerId) => {
  return Object.hasOwn(PROVIDER_NAMES, providerId) ? PROVIDER_NAMES[providerId].name : '教学服务'
}

const getProviderShort = (providerId) => {
  return Object.hasOwn(PROVIDER_NAMES, providerId) ? PROVIDER_NAMES[providerId].short : '教学'
}

const getProviderColor = (providerId) => {
  return PROVIDER_NAMES[providerId]?.color || 'var(--ink-secondary)'
}

const shouldShowProvider = (message) => {
  const hiddenProviders = new Set(['fallback', 'local_tutor', 'knowledge_pack', 'none', 'error'])
  if (!message || hiddenProviders.has(message.provider)) return false
  if (message.agent_id === 'xiaohei' || message.agent_name === '小黑本地AI') return false
  if (message.agent_id === 'tutor' || message.agent_name === '教学辅导师') return false
  return true
}

const hasLegalEvidenceMeta = (message) => {
  return message?.legal_evidence_count !== undefined || message?.challenge_knowledge_count !== undefined
}

const messageResources = (message) => tutorResourceListFromResponse(message)

const openTutorResource = (resourceOrEntry) => {
  const resource = typeof resourceOrEntry === 'object' && resourceOrEntry !== null ? resourceOrEntry : null
  if (resource) rememberTutorResources([resource])
  const target = String(resource?.entry || resourceOrEntry || '').trim()
  if (!target) return
  if (/^https?:\/\//i.test(target)) {
    window.open(target, '_blank', 'noopener,noreferrer')
    return
  }
  router.push(target)
}

const formatTime = (ts) => {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const readableMessageContent = (content) => {
  if (typeof content === 'string') return content
  if (typeof content?.content === 'string') return content.content
  return content ? '回复资料已记录，可查看并下载完整内容。' : ''
}

const renderMarkdown = (content) => {
  const text = readableMessageContent(content)
  return text ? sanitizeHtml(marked.parse(text)) : ''
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

const requireLogin = () => {
  if (userStore.isAuthenticated) return true
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
  // 无协作 ID 时不取全局最近会话：它可能是宠物共用的教学会话。
  if (!userStore.isAuthenticated || !conversationId.value) return
  const version = sessionVersion.value
  const owner = userStore.userInfo?.id
  const isCurrent = () => mounted && version === sessionVersion.value && owner === userStore.userInfo?.id
  collaborationProcessing.value = true
  try {
    const conversation = await api.conversation.detail(conversationId.value)
    if (!isCurrent()) return
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

        const structuredResources = tutorResourceListFromResponse(metadata)
        rememberTutorResources(structuredResources)

        return {
          id: `history_${item.id}`,
          type: 'agent',
          agent_id: item.agent_id || 'tutor',
          agent_name: item.agent_id === 'tutor' ? '教学辅导师' : (item.agent_name || '教学辅导师'),
          content: item.content,
          provider: item.provider || 'unknown',
          step: metadata.step,
          step_name: metadata.step_name,
          legal_evidence_count: metadata.legal_evidence_count,
          challenge_knowledge_count: metadata.challenge_knowledge_count,
          legal_sources: metadata.legal_sources,
          rag_mode: metadata.rag_mode,
          rag_sources: metadata.rag_sources || [],
          resources: structuredResources,
          resourceList: structuredResources,
          noMatchedResource: Boolean(metadata.noMatchedResource),
          image_url: metadata.image_url,
          timestamp: item.created_at
        }
      })

    collaborationMessages.value = restoredMessages
    if (restoredMessages.length) scrollToBottom()
  } catch (error) {
    if (!isCurrent()) return
    console.warn('恢复会话失败:', error)
    sessionStorage.removeItem('multiAgentConversationId')
    conversationId.value = null
  } finally {
    if (isCurrent()) collaborationProcessing.value = false
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

  if (isTutorSelected.value) {
    if (agentSession.state.sending || agentSession.state.restoring) return
    inputText.value = ''
    const result = await agentSession.send({ message: text, agentIds: ['tutor'], activeAgent,
      model: selectedConversationModel.value, forceAI: forceAI.value, mode: collaborationMode.value,
      knowledgeScope: knowledgeScope.value, challengeId: props.challengeId })
    if (result.ok) emit('message-sent')
    return
  }

  const userMsgId = uniqueId()
  const requestVersion = sessionVersion.value
  const requestMessages = collaborationMessages.value
  requestMessages.push({
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
  collaborationProcessing.value = true

  const thinkingIds = pendingAgents.map((agent) => {
    const thinkingId = uniqueId()
    requestMessages.push({
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
    const response = await callAgentAPI(
      selectedAgents.value.map((agent) => agent.id),
      text,
      activeAgent
    )

    if (requestVersion !== sessionVersion.value) return

    rememberConversation(response.conversation_id)

    thinkingIds.forEach((thinkingId) => {
      const idx = requestMessages.findIndex((message) => message.id === thinkingId)
      if (idx > -1) requestMessages.splice(idx, 1)
    })

    const agentResponses = (response.responses || []).filter((agentResp) => {
      const content = readableMessageContent(agentResp?.content)
      return String(content || '').trim().length > 0
    })

    const chartImageUrl = getChartImageForMessage(text)
    const structuredResources = tutorResourceListFromResponse(response)
    rememberTutorResources(structuredResources)
    const lastTutorResponseIndex = agentResponses.reduce((lastIndex, agentResp, index) => {
      const responseAgentId = agentResp.agent_id || activeAgent.id
      return responseAgentId === 'tutor' ? index : lastIndex
    }, -1)

    if (agentResponses.length > 0) {
      agentResponses.forEach((agentResp, index) => {
        const displayContent = agentResp.content
        const fallbackChartImage = index === agentResponses.length - 1 ? chartImageUrl : null

        requestMessages.push({
          id: uniqueId(),
          type: 'agent',
          agent_id: agentResp.agent_id || activeAgent.id,
          agent_name: agentResp.agent_name || activeAgent.name,
          content: displayContent,
          provider: agentResp.provider,
          step: agentResp.step,
          step_name: agentResp.step_name,
          handoff: agentResp.handoff,
          legal_evidence_count: agentResp.legal_evidence_count,
          challenge_knowledge_count: agentResp.challenge_knowledge_count,
          legal_sources: agentResp.legal_sources,
          rag_mode: agentResp.rag_mode,
          rag_sources: agentResp.rag_sources || [],
          resources: index === lastTutorResponseIndex ? structuredResources : [],
          resourceList: index === lastTutorResponseIndex ? structuredResources : [],
          noMatchedResource: index === lastTutorResponseIndex ? Boolean(response.noMatchedResource) : false,
          image_url: chartModeEnabled.value ? (agentResp.image_url || fallbackChartImage) : null,
          timestamp: new Date().toISOString()
        })
      })
    } else {
      requestMessages.push({
        id: uniqueId(),
        type: 'agent',
        agent_id: activeAgent.id,
        agent_name: activeAgent.name,
        content: response.content || '未收到有效响应',
        resources: structuredResources,
        resourceList: structuredResources,
        noMatchedResource: Boolean(response.noMatchedResource),
        image_url: chartImageUrl,
        timestamp: new Date().toISOString()
      })
    }

    const handoffResp = agentResponses.find((responseItem) => responseItem.handoff)
    if (handoffResp?.handoff) {
      const targetAgent = getAgentById(handoffResp.handoff.to_agent_id)
      if (targetAgent) {
        if (!isTutorSelected.value) currentAgent.value = targetAgent
        requestMessages.push({
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
      : '暂时无法完成讲解，请稍后重试。已输入的问题仍保留在对话中。'
    Message.error(errorMessage)

    thinkingIds.forEach((thinkingId) => {
      const idx = requestMessages.findIndex((message) => message.id === thinkingId)
      if (idx > -1) requestMessages.splice(idx, 1)
    })

    requestMessages.push({
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
      collaborationProcessing.value = false
      scrollToBottom()
    }
  }
}

const looksLikeChallengeQuestion = (message) => {
  const text = String(message || '').trim()
  return /第\s*\d+\s*题|题目\s*\d+|题\s*\d+|\d+\s*题|挑战\s*\d+|challenge\s*#?\s*\d+|#\s*\d+|id[=:\s#]*\d+/i.test(text)
}

const callAgentAPI = (agentIds, message, activeAgent) => requestTeaching({
  agentIds, message, activeAgent, challengeId: props.challengeId,
  conversationId: conversationId.value, model: selectedConversationModel.value,
  forceAI: forceAI.value, mode: collaborationMode.value, knowledgeScope: knowledgeScope.value,
  challengeQuestion: looksLikeChallengeQuestion(message),
})

// 清空会话
const clearSession = async () => {
  if (isTutorSelected.value) {
    inputText.value = ''
    await agentSession.reset({ deleteServer: true })
    return
  }
  sessionVersion.value += 1
  resetLifecycle()
  const oldConversationId = conversationId.value
  collaborationMessages.value = []
  inputText.value = ''
  collaborationProcessing.value = false
  sessionStorage.removeItem('multiAgentConversationId')
  sessionStorage.removeItem(MODEL_STORAGE_KEY)
  sessionStorage.removeItem(CHART_MODE_STORAGE_KEY)
  clearRememberedTutorResources()
  conversationId.value = null
  selectedConversationModel.value = conversationModels[0]
  chartModeEnabled.value = false
  agents.value.forEach(a => a.status = 'available')

  if (oldConversationId && userStore.isAuthenticated) {
    try {
      await api.conversation.remove(oldConversationId)
    } catch (error) {
      if (error.response?.status !== 404) {
        console.warn('删除历史会话失败:', error)
        Message.warning('页面已清空，但历史记录未能删除，请稍后重试。')
        return
      }
    }
  }

  Message.success('会话已重置')
}

defineExpose({ setCurrentAgent, addSystemMessage, clearSession })

let mounted = true
let active = true
let ready = false
const consumeDraft = () => {
  if (!mounted || !active || !ready) return
  const draft = takeDraft(userStore.userInfo?.id)
  if (!draft) return
  inputText.value = draft
  if (!isProcessing.value) sendMessage()
  else Message.info('问题已放入输入框，当前讲解结束后可发送。')
}
const unsubscribeDraft = subscribeDraft(consumeDraft)
function applyTeachingSession(snapshot) {
  if (!mounted || !active || !isTutorSelected.value) return
  let chartImage = null
  teachingMessages.value = snapshot.messages.map((message, index) => {
    if (message.role === 'user') chartImage = getChartImageForMessage(message.content)
    const lastReply = message.role === 'assistant' && snapshot.messages[index + 1]?.role !== 'assistant'
    return {
      id: message.id, type: message.role === 'user' ? 'user' : 'agent', content: message.content,
      agent_id: 'tutor', agent_name: message.agentName || '教学辅导师', timestamp: message.createdAt,
      provider: message.provider, step: message.step, step_name: message.stepName, rag_sources: message.resources || [],
      resources: message.resourceList || [], resourceList: message.resourceList || [],
      noMatchedResource: Boolean(message.noMatchedResource),
      image_url: chartModeEnabled.value ? (message.imageUrl || (lastReply ? chartImage : null)) : null,
    }
  })
  if (snapshot.error) teachingMessages.value.push({ id: 'teaching-error', type: 'system', content: snapshot.error })
  teachingProcessing.value = snapshot.sending || snapshot.restoring
  scrollToBottom()
}
const unsubscribeTeaching = agentSession.subscribe(applyTeachingSession)
watch(isTutorSelected, selected => {
  if (selected) applyTeachingSession(agentSession.state)
  scrollToBottom()
})
onMounted(async () => {
  if (props.initialAgents?.length) {
    agents.value = props.initialAgents.filter(isVisibleAgent)
  }
  currentAgent.value = selectedAgents.value[0] || availableAgents.value[0] || null
  applyTeachingSession(agentSession.state)
  // 即使先显示教学，也把协作历史恢复到独立状态，期间禁止另发协作请求。
  await restoreConversation()
  if (!mounted) return
  ready = true
  consumeDraft()
})
onActivated(() => { active = true; applyTeachingSession(agentSession.state); consumeDraft() })
onDeactivated(() => { active = false })
onBeforeUnmount(() => { mounted = false; active = false; unsubscribeDraft(); unsubscribeTeaching(); sessionVersion.value++; resetLifecycle() })
</script>

<style scoped>
.multi-agent-chat {
  display:flex;
  flex-direction:column;
  height:100%;
  background:var(--color-bg-1);
  border-radius:var(--radius-control);
  overflow:hidden;
}

.thinking-indicator {
  width:calc(var(--space-1) / 2);
  height:calc(var(--space-1) / 2);
  background:var(--action);
  border-radius:50%;
  animation:pulse var(--motion-loop) infinite;
}

@keyframes pulse {
  0%, 100% { opacity:1; }
  50% { opacity:0.4; }
}

.messages-area {
  flex:1;
  overflow-y:auto;
  padding:var(--space-2);
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
  min-height:0;
  scroll-behavior:smooth;
}

/* 消息少时从底部开始显示 */
.messages-area::before {
  content:'';
  flex:1;
  min-height:0;
}

.messages-area.has-messages::before {
  display:none;
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
  min-height:0;
}

.empty-icon {
  width:var(--space-7);
  height:var(--space-7);
  display:grid;
  place-items:center;
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  color:var(--primary-color);
  background:var(--surface);
  font-size:var(--text-section);
  margin-bottom:var(--space-2);
  opacity:0.5;
}

.hint {
  font-size:var(--text-caption);
  margin-top:var(--space-1);
}

.message-item {
  display:flex;
  gap:var(--space-1);
}

.message-item.user {
  flex-direction:row-reverse;
}

.agent-avatar {
  width:var(--space-4);
  height:var(--space-4);
  border-radius:var(--radius-control);
  display:flex;
  align-items:center;
  justify-content:center;
  color:var(--text-primary);
  background:var(--bg-paper-2);
  border:var(--stroke) solid var(--line);
  font-size:var(--text-body);
  flex-shrink:0;
}

.agent-avatar.thinking {
  animation:pulse var(--motion-loop) infinite;
}

.demo-report-image {
  display:block;
  width:min(100%, var(--message-width));
  margin-top:var(--space-1);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  background:var(--surface);
}

.tutor-resource-panel,
.tutor-resource-empty {
  margin-top:var(--space-1);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  background:var(--surface);
  padding:var(--space-1);
}

.tutor-resource-panel-title {
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  color:var(--text-secondary);
  margin-bottom:var(--space-1);
}

.tutor-resource-card {
  display:grid;
  gap:calc(var(--space-1) / 2);
  padding:var(--space-1);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  background:var(--surface);
}

.tutor-resource-card + .tutor-resource-card {
  margin-top:var(--space-1);
}

.tutor-resource-card-head {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  min-width:0;
}

.tutor-resource-title {
  min-width:0;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  color:var(--text-primary);
  font-weight: var(--weight-strong);
}

.tutor-resource-badge {
  flex-shrink:0;
  padding:calc(var(--stroke) * 2) calc(var(--space-1) / 2);
  border-radius:var(--radius-control);
  background:var(--agent-accent);
  color:var(--on-action);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.tutor-resource-location,
.tutor-resource-summary,
.tutor-resource-empty {
  color:var(--text-secondary);
  font-size:var(--text-caption);
  line-height:1.45;
}

.tutor-resource-summary {
  margin:0;
}

.tutor-resource-link {
  justify-self:start;
  height:var(--space-3);
  padding:0 var(--space-1);
  border:var(--stroke) solid var(--primary-color);
  border-radius:var(--radius-control);
  background:var(--primary-color);
  color:var(--on-action);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  cursor:pointer;
}

.tutor-resource-link:hover {
  filter:brightness(0.94);
}
.rag-reference-panel {
  margin-top:var(--space-1);
  border-top:var(--stroke) solid var(--border-color);
  color:var(--text-secondary);
  font-size:var(--text-caption);
}

.rag-reference-panel summary {
  display:flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  padding:var(--space-1) 0 calc(var(--space-1) / 2);
  color:var(--text-secondary);
  cursor:pointer;
  list-style:none;
}

.rag-reference-panel summary::-webkit-details-marker {
  display:none;
}

.rag-reference-panel a {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:var(--space-1);
  padding:calc(var(--space-1) / 2) 0;
  color:var(--text-primary);
  text-decoration:none;
}

.rag-reference-panel a:hover span {
  color:var(--primary-color);
}

.rag-reference-panel a span {
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.rag-reference-panel a small {
  flex-shrink:0;
  color:var(--text-secondary);
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

.message-label-row {
  display:flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  margin-bottom:var(--space-1);
  font-size:var(--text-caption);
  flex-wrap:wrap;
}

.agent-label {
  padding:calc(var(--stroke) * 2) var(--space-1);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  color:var(--text-primary);
  background:var(--bg-paper-2);
  font-weight: var(--weight-strong);
  font-size:var(--text-caption);
}

.label-separator {
  color:var(--color-text-3);
  font-weight: var(--weight-strong);
  margin:0 var(--stroke);
}

.provider-label {
  padding:calc(var(--stroke) * 2) var(--space-1);
  border-radius:var(--radius-control);
  color:var(--on-action);
  font-size:var(--text-caption);
}

.provider-label.unknown {
  background:var(--surface-muted);
}

.tutor-progress-shell {
  position:relative;
  flex-shrink:0;
  border-bottom:var(--stroke) solid var(--color-border);
  background:var(--surface);
  box-shadow: none;
}

.tutor-progress-shell.collapsed {
  min-height:var(--space-5);
}

.tutor-progress-toggle {
  position:absolute;
  top:calc(var(--space-1) / 2);
  right:var(--space-1);
  z-index:2;
  display:inline-flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  height:var(--space-3);
  padding:0 var(--space-1);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  color:var(--text-secondary);
  background:var(--surface);
  cursor:pointer;
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.tutor-progress-toggle:hover {
  color:var(--on-action);
  border-color:var(--primary-color);
  background:var(--primary-color);
}

.tutor-progress-compact {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  height:var(--space-5);
  padding:0 var(--row-label-width) 0 var(--space-2);
  color:var(--text-secondary);
  font-size:var(--text-caption);
}

.compact-title,
.compact-step {
  color:var(--text-primary);
  font-weight: var(--weight-strong);
}

.compact-step {
  padding:calc(var(--stroke) * 2) calc(var(--space-1) / 2);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  background:var(--bg-paper-2);
}

.compact-hint {
  min-width:0;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.legal-evidence-note {
  background:var(--positive-soft);
  border:var(--stroke) solid var(--positive);
  border-radius:var(--radius-control);
  color:var(--positive);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  margin-top:var(--space-1);
  padding:calc(var(--space-1) / 2) var(--space-1);
}

.step-badge {
  margin-left:auto;
  padding:var(--stroke) var(--space-1);
  background:var(--action);
  color:var(--on-action);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

/* 学习报告 */
.tutor-report {
  display:flex; gap:var(--space-1);
  padding:var(--space-2) var(--space-2);
  margin:0;
  background: var(--surface-muted);
  border:var(--stroke) solid var(--line);
  border-radius:0;
  flex-shrink:0;
}
.report-icon { font-size:var(--text-section); }
.report-content h4 { margin:0 0 calc(var(--space-1) / 2); font-size:var(--text-caption); color:var(--action); }
.report-content p { margin:0; font-size:var(--text-caption); color:var(--ink); }
.report-hint { color:var(--ink-secondary) !important; margin-top:calc(var(--space-1) / 2) !important; }

/* 教学授课步骤进度条 */
.tutor-steps-bar {
  display:flex;
  justify-content:space-around;
  padding:var(--space-1) var(--space-2);
  background:var(--color-bg-2);
  border-top:var(--stroke) solid var(--color-border);
  flex-shrink:0;
}
.tutor-step-item {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  opacity:0.4;
  transition:opacity var(--motion-normal);
}
.tutor-step-item.active { opacity:1; }
.tutor-step-item.done { opacity:0.7; }
.step-dot {
  width:var(--space-3); height:var(--space-3);
  border-radius:50%;
  background:var(--color-fill-3);
  display:flex; align-items:center; justify-content:center;
  font-size:var(--text-caption); font-weight: var(--weight-strong);
  transition:all var(--motion-normal);
}
.tutor-step-item.active .step-dot { background:var(--action); color:var(--on-action); }
.tutor-step-item.done .step-dot { background:var(--positive); color:var(--on-action); }
.step-label { font-size:var(--text-caption); white-space:nowrap; }

.time {
  margin-left:auto;
  font-size:var(--text-caption);
  color:var(--color-text-3);
  white-space:nowrap;
}

.message-label-row .time {
  margin-left:calc(var(--space-1) / 2);
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

.handoff-tag {
  display:flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  margin-top:var(--space-1);
  padding:var(--space-1) var(--space-1);
  background:var(--warning-soft);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  color:var(--warning);
}

.handoff-tag .arrow {
  font-size:var(--text-caption);
}

.handoff-tag .reason {
  margin-left:auto;
  opacity:0.7;
}

.message-actions {
  display:flex;
  gap:var(--space-1);
  margin-top:var(--space-1);
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

.thinking-message {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  padding:var(--space-1) var(--space-2);
  background:var(--color-bg-2);
  border-radius:var(--radius-panel);
}

.thinking-message .agent-name {
  color:var(--action);
  font-weight: var(--weight-medium);
}

.dots {
  display:flex;
  gap:calc(var(--space-1) / 2);
}

.dots span {
  width:calc(var(--space-1) / 2);
  height:calc(var(--space-1) / 2);
  background:var(--action);
  border-radius:50%;
  animation:bounce var(--motion-loop) infinite;
}

.dots span:nth-child(2) { animation-delay:var(--motion-normal); }
.dots span:nth-child(3) { animation-delay:var(--motion-normal); }

@keyframes bounce {
  0%, 80%, 100% { transform:translateY(0); }
  40% { transform:translateY(calc(calc(var(--space-1) / 2) * -1)); }
}

.input-area {
  padding:var(--space-1) var(--space-2);
  background:var(--color-bg-2);
  border-top:var(--stroke) solid var(--color-border);
  flex-shrink:0;
}

.current-agent {
  margin-bottom:var(--space-1);
  font-size:var(--text-caption);
  color:var(--color-text-2);
}

.current-agent .badge {
  display:inline-flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
  padding:calc(var(--stroke) * 2) var(--space-1);
  background:var(--bg-paper-2);
  color:var(--text-primary);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.input-row {
  display:flex;
  gap:var(--space-1);
  margin-bottom:var(--space-1);
}

.input-row:deep(.arco-textarea) {
  flex:1;
}

.quick-actions {
  display:flex;
  gap:var(--space-1);
}

/* 弹窗样式 */
.agent-select-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.agent-select-item {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  padding:var(--space-1);
  background:var(--color-fill-1);
  border-radius:var(--radius-control);
  cursor:pointer;
  transition:all var(--motion-normal);
}

.agent-select-item:hover {
  background:var(--color-fill-2);
}

.agent-select-item.current {
  border:var(--stroke) solid var(--action);
}

.agent-select-item .avatar {
  width:var(--space-5);
  height:var(--space-5);
  border-radius:var(--radius-control);
  display:flex;
  align-items:center;
  justify-content:center;
  color:var(--text-primary);
  background:var(--bg-paper-2);
  border:var(--stroke) solid var(--line);
  font-size:var(--text-card);
}

.agent-select-item .info {
  flex:1;
}

.agent-select-item .name {
  font-weight: var(--weight-medium);
}

.agent-select-item .role {
  font-size:var(--text-caption);
  color:var(--color-text-3);
}

/* Phase 2 Editorial chat override */
.multi-agent-chat {
  background:transparent;
}

.tutor-steps-bar,
.input-area {
  background:var(--surface);
  border-color:var(--border-color);
}

.summary-label {
  color:var(--text-secondary);
  font-weight: var(--weight-strong);
}

.summary-badge,
.agent-label,
.provider-label,
.step-badge,
.current-agent .badge {
  border-radius:var(--radius-control);
}

.messages-area {
  padding:var(--space-2);
}

.empty-state,
.time,
.hint {
  color:var(--text-muted);
}

.message-content,
.thinking-message {
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  background:var(--surface);
}

.user-message {
  color:var(--on-action);
  background:var(--text-primary);
  border-color:var(--text-primary);
}

.legal-evidence-note {
  color:var(--success-color);
  background:var(--positive-soft);
  border:var(--stroke) solid var(--positive);
  border-radius:var(--radius-control);
}

.step-badge,
.thinking-indicator,
.dots span {
  background:var(--primary-color);
  color:var(--on-action);
}

.report-icon {
  width:var(--space-5);
  height:var(--space-5);
  display:grid;
  place-items:center;
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
  color:var(--primary-color);
  background:var(--surface);
  flex-shrink:0;
}

.tutor-report {
  background:var(--surface-muted);
  border:var(--stroke) solid var(--line);
  border-radius:var(--radius-control);
}

.tutor-progress-shell .tutor-report {
  padding-right:var(--row-label-width);
  border-right:0;
  border-left:0;
  border-radius:0;
}

.tutor-progress-shell .tutor-steps-bar {
  border-bottom:0;
}

.report-content h4 {
  color:var(--text-primary);
}

.report-content p,
.current-agent,
.system-message,
.agent-select-item .role {
  color:var(--text-secondary);
}

.report-hint {
  color:var(--text-muted) !important;
}

.step-dot {
  background:var(--bg-paper-2);
}

.tutor-step-item.active .step-dot {
  background:var(--primary-color);
  color:var(--on-action);
}

.tutor-step-item.done .step-dot {
  background:var(--success-color);
  color:var(--on-action);
}

.handoff-tag {
  color:var(--warning);
  background:var(--warning-soft);
  border-radius:var(--radius-control);
}

.system-message,
.agent-select-item {
  background:var(--surface);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
}

.agent-select-item:hover {
  background:var(--bg-paper-2);
}

.agent-select-item.current {
  border-color:var(--primary-color);
}

.agent-select-item .name {
  color:var(--text-primary);
  font-weight: var(--weight-strong);
}
</style>
