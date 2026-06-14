<template>
  <div class="multi-agent-page">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">
          多智能体协作
        </h1>
        <p class="page-desc">多个AI智能体协同处理复杂任务，支持智能切换和任务委托</p>
      </div>
      <div class="header-right">
        <a-button type="outline" @click="showHelp = true">
          <template #icon><icon-question-circle /></template>
          使用帮助
        </a-button>
      </div>
    </div>

    <div class="layout-grid">
      <!-- 中间：对话区域 -->
      <div class="chat-panel">
        <MultiAgentChat
          ref="chatRef"
          :challenge-id="challengeId"
          :initial-agents="agents"
          :selected-agent-ids="selectedAgentIds"
          :initial-mode="sessionMode"
          @handoff="handleHandoff"
          @complete="handleComplete"
          @mode-change="onModeChange"
          @message-sent="onMessageSent"
          @agent-switch="onAgentSwitch"
        />
      </div>

      <!-- 右侧：任务信息 -->
      <div class="info-panel">
        <div class="info-card">
          <h4>参与智能体</h4>
          <p class="card-desc">从右侧垂直列表中多选，至少保留一个智能体参与对话。</p>
          <div class="agent-checklist">
            <div
              v-for="agent in agents"
              :key="agent.id"
              class="agent-check-item"
              :class="{
                selected: selectedAgentIds.includes(agent.id),
                disabled: agent.status === 'thinking'
              }"
              @click="toggleAgentSelection(agent.id)"
            >
              <input
                class="agent-checkbox"
                type="checkbox"
                :checked="selectedAgentIds.includes(agent.id)"
                :disabled="agent.status === 'thinking'"
                @click.stop="toggleAgentSelection(agent.id)"
              />
              <div class="agent-check-avatar" :style="{ background: agent.color }">
                {{ agent.icon }}
              </div>
              <div class="agent-check-info">
                <div class="agent-check-name-row">
                  <span class="agent-check-name">{{ agent.name }}</span>
                  <span class="agent-check-status" :class="agent.status">
                    {{ statusText[agent.status] }}
                  </span>
                </div>
                <div class="agent-check-role">{{ agent.role }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="info-card">
          <h4>协作预设</h4>
          <div class="preset-list">
            <div v-for="preset in presets" :key="preset.id" class="preset-item" @click="loadPreset(preset)">
              <span class="preset-icon">{{ preset.icon }}</span>
              <span class="preset-name">{{ preset.name }}</span>
              <span class="preset-count">{{ preset.agents.length }} 个智能体</span>
            </div>
          </div>
        </div>

        <div class="info-card">
          <h4>操作</h4>
          <div class="action-buttons">
            <a-button long @click="exportSession">
              <template #icon><icon-download /></template>
              导出记录
            </a-button>
            <a-button long status="danger" @click="resetSession">
              <template #icon><icon-refresh /></template>
              重新开始
            </a-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 帮助弹窗 -->
    <a-modal v-model:visible="showHelp" title="多智能体协作说明" :footer="false">
      <div class="help-content">
        <h4>什么是多智能体协作？</h4>
        <p>多个AI智能体可以协同处理复杂任务，每个智能体有不同的专业领域。</p>
        
        <h4>如何使用？</h4>
        <ol>
          <li>选择一个智能体开始对话</li>
          <li>输入你的问题或任务</li>
          <li>智能体会分析并响应，可能委托给其他专家</li>
          <li>你可以手动切换智能体或委托任务</li>
        </ol>
        
        <h4>协作模式</h4>
        <ul>
          <li><b>协作模式</b>: 多个智能体共同讨论</li>
          <li><b>串行模式</b>: 按顺序依次处理</li>
          <li><b>竞争模式</b>: 多个方案选最优</li>
        </ul>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import MultiAgentChat from '@/components/MultiAgent/MultiAgentChat.vue'
import api from '@/api'

const route = useRoute()

// 智能体配置
const agents = ref([
  {
    id: 'xiaohei',
    name: '小黑本地AI',
    role: 'CTF全能助手',
    icon: '🤖',
    color: '#8b5cf6',
    status: 'available',
    capabilities: ['智能问答', '解题分析', '代码调试']
  },
  {
    id: 'analyst',
    name: '分析师',
    role: '题目拆解专家',
    icon: '🔍',
    color: '#00f5ff',
    status: 'available',
    capabilities: ['信息提取', '知识点定位', '攻题规划']
  },
  {
    id: 'architect',
    name: '架构师',
    role: '系统规划师',
    icon: '🏗️',
    color: '#ff00ff',
    status: 'available',
    capabilities: ['架构分析', '协议解析', '方案评审']
  },
  {
    id: 'developer',
    name: '开发专家',
    role: '代码实战派',
    icon: '⌨️',
    color: '#39ff14',
    status: 'available',
    capabilities: ['POC/EXP', '脚本开发', '工具定制']
  },
  {
    id: 'security',
    name: '安全专家',
    role: '渗透测试老兵',
    icon: '🔓',
    color: '#ff0055',
    status: 'available',
    capabilities: ['漏洞分析', 'Web渗透', '逆向分析']
  },
  {
    id: 'tester',
    name: '测试专家',
    role: '边界测试员',
    icon: '🧪',
    color: '#ff6b35',
    status: 'available',
    capabilities: ['边界测试', 'Fuzzing', '鲁棒性验证']
  },
  {
    id: 'tutor',
    name: '教学智能体',
    role: '学习教学与四步闭环辅导',
    icon: '🎓',
    color: '#4fc3f7',
    status: 'available',
    capabilities: ['水平评估', '概念讲解', '练习出题', '学习检验']
  }
])

const currentAgent = ref(null)
const selectedAgentIds = ref([])
const sessionMode = ref('collaborative')
const processedCount = ref(0)
const handoffCount = ref(0)
const flowHistory = ref([])
const chatRef = ref(null)
const showHelp = ref(false)

const challengeId = computed(() => route.params.challengeId || null)

const statusText = {
  available: '空闲',
  thinking: '思考中',
  working: '工作中'
}

const modeLabels = {
  collaborative: '协作模式',
  sequential: '串行模式',
  competitive: '竞争模式',
  teaching: '教学授课'
}

const defaultPresets = [
  { id: 'code-review', name: '代码审查', icon: '🔍', agents: ['analyst', 'developer', 'tester', 'security'] },
  { id: 'architecture', name: '架构设计', icon: '📐', agents: ['analyst', 'architect', 'developer'] },
  { id: 'security', name: '安全审计', icon: '🛡️', agents: ['analyst', 'security', 'tester'] },
  { id: 'full', name: '全流程', icon: '🔄', agents: ['xiaohei', 'analyst', 'architect', 'developer', 'tester', 'security'] },
  { id: 'teaching', name: '教学辅导', icon: '🎓', agents: ['tutor'] },
  { id: 'knowledge', name: '知识库问答', icon: '🧠', agents: ['xiaohei'] },
  { id: 'ai-kb', name: 'AI+知识库', icon: '[!]', agents: ['analyst', 'security', 'xiaohei'] }
]
const presets = ref(defaultPresets)

const syncSelectedAgents = (preferredIds = []) => {
  const availableIds = agents.value.map((agent) => agent.id)
  const nextSelected = preferredIds.filter((id) => availableIds.includes(id))
  selectedAgentIds.value = nextSelected.length ? nextSelected : availableIds.slice(0, 1)
  currentAgent.value = agents.value.find((agent) => agent.id === selectedAgentIds.value[0]) || null
}

const toggleAgentSelection = (agentId) => {
  const agent = agents.value.find((item) => item.id === agentId)
  if (!agent || agent.status === 'thinking') return

  const isSelected = selectedAgentIds.value.includes(agentId)
  if (isSelected) {
    if (selectedAgentIds.value.length === 1) {
      Message.warning('至少保留一个智能体参与对话')
      return
    }
    selectedAgentIds.value = selectedAgentIds.value.filter((id) => id !== agentId)
  } else {
    selectedAgentIds.value = agentId === 'tutor'
      ? ['tutor']
      : [...selectedAgentIds.value.filter((id) => id !== 'tutor'), agentId]
  }

  if (!selectedAgentIds.value.includes(currentAgent.value?.id)) {
    currentAgent.value = agents.value.find((item) => item.id === selectedAgentIds.value[0]) || null
  }
}

const loadPreset = (preset) => {
  sessionMode.value = 'collaborative'
  const nextSelected = agents.value
    .filter((agent) => preset.agents.includes(agent.id))
    .map((agent) => agent.id)
  if (nextSelected.length > 0) {
    syncSelectedAgents(nextSelected)
    Message.success(`已加载预设: ${preset.name}`)
  }
}

const loadPresets = async () => {
  try {
    const data = await api.multiAgent.presets()
    if (Array.isArray(data) && data.length > 0) {
      presets.value = data
    }
  } catch (error) {
    console.error('Failed to load multi-agent presets:', error)
  }
}

const handleHandoff = ({ from, to }) => {
  handoffCount.value++
  flowHistory.value.unshift({
    agent: from?.name,
    action: `委托给 ${to?.name}`
  })
}

const handleComplete = () => {
  Message.success('任务已完成')
}

// 模式切换回调（从子组件同步过来）
const onModeChange = (mode) => {
  sessionMode.value = mode
}

// 消息发送完成回调（更新轮次）
const onMessageSent = () => {
  processedCount.value++
}

// 智能体切换回调（更新切换次数）
const onAgentSwitch = ({ from, to }) => {
  currentAgent.value = to || currentAgent.value
  handoffCount.value++
  flowHistory.value.unshift({
    agent: from?.name || to?.name,
    action: `切换到 ${to?.name}`
  })
}

const exportSession = () => {
  const data = {
    mode: sessionMode.value,
    processedCount: processedCount.value,
    handoffCount: handoffCount.value,
    flowHistory: flowHistory.value,
    timestamp: new Date().toISOString()
  }
  
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `multi-agent-session-${Date.now()}.json`
  a.click()
  
  Message.success('导出成功')
}

const resetSession = async () => {
  processedCount.value = 0
  handoffCount.value = 0
  flowHistory.value = []
  agents.value.forEach(a => a.status = 'available')
  syncSelectedAgents(agents.value.slice(0, 1).map((agent) => agent.id))
  
  if (chatRef.value) {
    await chatRef.value.clearSession()
  }
}

onMounted(async () => {
  await loadPresets()
  if (route.query.mode === 'learning') {
    syncSelectedAgents(['tutor'])
  } else {
    syncSelectedAgents([agents.value[0].id])
  }
})
</script>

<style scoped>
.multi-agent-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 1400px;
  margin: 0 auto;
  overflow: hidden;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 24px 12px;
  flex-shrink: 0;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 24px;
  font-weight: 600;
  margin: 0;
}

.page-title .icon {
  font-size: 28px;
}

.page-desc {
  margin-top: 8px;
  color: var(--color-text-2);
  font-size: 14px;
}

.layout-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
  flex: 1;
  min-height: 0;
  padding: 0 24px 24px;
}

.panels {
  background: var(--color-bg-2);
  border-radius: 12px;
  border: 1px solid var(--color-border);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: var(--color-bg-2);
  border-radius: 12px;
  border: 1px solid var(--color-border);
}

.panel-header h3 {
  margin: 0;
  font-size: 14px;
}

.preset-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preset-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-fill-1);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.preset-item:hover {
  background: var(--color-fill-2);
}

.preset-icon {
  font-size: 16px;
}

.preset-name {
  flex: 1;
  font-size: 13px;
}

.preset-count {
  font-size: 11px;
  color: var(--color-text-3);
}

.chat-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.info-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  overflow-y: auto;
}

.info-card {
  background: var(--color-bg-2);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 16px;
}

.info-card h4 {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--color-text-1);
}

.card-desc {
  margin: 0 0 12px;
  color: var(--color-text-3);
  font-size: 12px;
  line-height: 1.5;
}

.agent-checklist {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-check-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-fill-1);
  cursor: pointer;
  transition: all 0.2s;
}

.agent-check-item:hover {
  border-color: rgb(var(--primary-6));
  background: var(--color-fill-2);
}

.agent-check-item.selected {
  border-color: rgb(var(--primary-6));
  background: rgba(var(--primary-6), 0.08);
}

.agent-check-item.disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.agent-checkbox {
  margin-top: 4px;
  accent-color: rgb(var(--primary-6));
}

.agent-check-avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 16px;
  flex-shrink: 0;
}

.agent-check-info {
  flex: 1;
  min-width: 0;
}

.agent-check-name-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.agent-check-name {
  font-size: 13px;
  font-weight: 600;
}

.agent-check-role {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-3);
}

.agent-check-status {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  white-space: nowrap;
}

.task-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.info-row .label {
  color: var(--color-text-3);
}

.info-row .value {
  color: rgb(var(--primary-6));
  font-weight: 500;
}

.flow-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.flow-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.flow-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgb(var(--primary-6));
}

.flow-content {
  flex: 1;
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.flow-agent {
  color: rgb(var(--primary-6));
  font-weight: 500;
}

.flow-action {
  color: var(--color-text-3);
}

.action-buttons {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.help-content h4 {
  margin: 16px 0 8px;
  font-size: 14px;
}

.help-content h4:first-child {
  margin-top: 0;
}

.help-content p, .help-content li {
  color: var(--color-text-2);
  font-size: 13px;
  line-height: 1.6;
}

.help-content ol, .help-content ul {
  padding-left: 20px;
}

@media (max-width: 1200px) {
  .layout-grid {
    grid-template-columns: 1fr;
  }
  .info-panel {
    order: 2;
  }
}
</style>
