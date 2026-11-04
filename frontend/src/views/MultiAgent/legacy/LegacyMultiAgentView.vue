<template>
  <div class="multi-agent-page">
    <div class="page-header">
      <div class="header-left">
        <p class="section-kicker">学习与答疑</p>
        <h1 class="page-title">{{ names.guide }} · 导学对话</h1>
        <p class="page-desc">先理解，再尝试。教学智能体会通过评估、讲解、练习和检验陪你学习。</p>
      </div>
      <div class="header-right">
        <a-button type="outline" @click="showHelp = true">
          <template #icon><icon-question-circle /></template>
          使用帮助
        </a-button>
      </div>
    </div>

    <div class="layout-grid" :class="{ 'brief-collapsed': briefCollapsed, 'info-collapsed': infoCollapsed }">
      <aside class="brief-panel" :class="{ collapsed: briefCollapsed }">
        <button
          class="panel-collapse-control left"
          type="button"
          :title="briefCollapsed ? '展开协作面板' : '收起协作面板'"
          @click="briefCollapsed = !briefCollapsed"
        >
          <AppIcon :name="['bi', briefCollapsed ? 'bi-chevron-right' : 'bi-chevron-left']" />
        </button>
        <template v-if="!briefCollapsed">
        <div class="brief-card dark">
          <div class="brief-top">
            <span>学习伙伴</span>
            <span>{{ modeLabels[sessionMode] }}</span>
          </div>
          <strong>{{ selectedAgentIds.length }}</strong>
          <p>参与智能体</p>
          <div class="brief-stats">
            <span>轮次 {{ processedCount }}</span>
            <span>切换 {{ handoffCount }}</span>
          </div>
        </div>

        <div class="info-card preset-card">
          <h4>协作预设</h4>
          <div class="preset-list">
            <div v-for="preset in presets" :key="preset.id" class="preset-item" @click="loadPreset(preset)">
              <span class="preset-icon"><AppIcon :name="['bi', presetIconClass(preset)]" /></span>
              <span class="preset-name">{{ preset.name }}</span>
              <span class="preset-count">{{ preset.agents.length }} 个</span>
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
        </template>
      </aside>

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
      <div class="info-panel" :class="{ collapsed: infoCollapsed }">
        <button
          class="panel-collapse-control right"
          type="button"
          :title="infoCollapsed ? '展开智能体面板' : '收起智能体面板'"
          @click="infoCollapsed = !infoCollapsed"
        >
          <AppIcon :name="['bi', infoCollapsed ? 'bi-chevron-left' : 'bi-chevron-right']" />
        </button>
        <template v-if="!infoCollapsed">
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
              <div class="agent-check-avatar">
                <AppIcon :name="['bi', agent.icon]" />
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
        </template>

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
          <li>法律审核师会检索法规和题目知识，给出靶场边界与数据安全建议，不替代人工法律意见</li>
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
import MultiAgentChat from '@/components/MultiAgent/legacy/LegacyMultiAgentChat.vue'
import api from '@/api'
import { names } from '@/shared/navigation/names.js'

const route = useRoute()

const HIDDEN_AGENT_IDS = new Set(['analyst', 'architect', 'developer', 'security', 'tester'])
const isVisibleAgentId = (id) => !HIDDEN_AGENT_IDS.has(id)

// 智能体配置
const agents = ref([
  {
    id: 'tutor',
    name: '教学辅导师',
    role: '学习教学与四步闭环辅导',
    icon: 'bi-mortarboard',
    color: 'var(--ink)',
    status: 'available',
    capabilities: ['水平评估', '概念讲解', '练习出题', '学习检验']
  },
  {
    id: 'xiaohei',
    name: '小黑本地AI',
    role: 'CTF全能助手',
    icon: 'bi-cpu',
    color: 'var(--ink)',
    status: 'available',
    capabilities: ['智能问答', '解题分析', '代码调试']
  },
  {
    id: 'legal_reviewer',
    name: '法律审核师',
    role: '题目与靶场实验合规审查',
    icon: 'bi-bank',
    color: 'var(--ink)',
    status: 'available',
    capabilities: ['法规检索', '题目合规分析', '靶场建议', '数据安全建议']
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
const briefCollapsed = ref(false)
const infoCollapsed = ref(false)

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
  { id: 'teaching', name: '教学辅导', icon: 'bi-mortarboard', agents: ['tutor'] },
  { id: 'knowledge', name: '知识库问答', icon: 'bi-journal-text', agents: ['xiaohei'] },
  { id: 'ai-kb', name: 'AI+知识库', icon: 'bi-database-check', agents: ['xiaohei'] },
  { id: 'legal-review', name: '法律合规审查', icon: 'bi-bank', agents: ['legal_reviewer', 'xiaohei'] },
  { id: 'full', name: '全流程', icon: 'bi-arrow-repeat', agents: ['tutor', 'xiaohei', 'legal_reviewer'] }
]
const presets = ref(defaultPresets)

const presetIconMap = {
  'code-review': 'bi-search',
  architecture: 'bi-diagram-3',
  security: 'bi-shield-check',
  full: 'bi-arrow-repeat',
  teaching: 'bi-mortarboard',
  knowledge: 'bi-journal-text',
  'ai-kb': 'bi-database-check',
  'legal-review': 'bi-bank'
}

const presetIconClass = (preset) => {
  if (presetIconMap[preset.id]) return presetIconMap[preset.id]
  if (typeof preset.icon === 'string' && preset.icon.startsWith('bi-')) return preset.icon
  return 'bi-list-check'
}

const normalizePresets = (list) => {
  return list
    .map((preset) => ({
      ...preset,
      agents: (preset.agents || []).filter(isVisibleAgentId)
    }))
    .filter((preset) => preset.agents.length > 0)
}

const syncSelectedAgents = (preferredIds = []) => {
  const availableIds = agents.value.map((agent) => agent.id)
  const nextSelected = preferredIds.filter((id) => availableIds.includes(id) && isVisibleAgentId(id))
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
      const visiblePresets = normalizePresets(data)
      presets.value = visiblePresets.length > 0 ? visiblePresets : defaultPresets
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
  display:flex;
  flex-direction:column;
  min-height:calc(100vh - var(--header-height) - var(--nav-height));
  height:calc(100vh - var(--header-height) - var(--nav-height));
  width:min(var(--page-width), calc(100% - var(--page-gutter) * 2));
  max-width:none;
  margin:0 auto;
  overflow:hidden;
  padding:var(--space-3) 0;
}

.page-header {
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:var(--space-2);
  padding:0 0 var(--space-1);
  flex-shrink:0;
}

.page-header .section-kicker {
  margin:0 0 calc(var(--stroke) * 2);
  font-size:var(--text-caption);
  line-height:1.1;
}

.page-title {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  font-size:var(--text-page);
  line-height:var(--leading-tight);
  font-weight:var(--weight-strong);
  margin:0;
}

.page-title .icon {
  font-size:var(--text-section);
}

.page-desc {
  margin:calc(var(--space-1) / 2) 0 0;
  max-width:var(--search-width);
  color:var(--text-secondary);
  font-size:var(--text-caption);
  line-height:1.35;
}

.header-right {
  flex-shrink:0;
}

.layout-grid {
  display:grid;
  grid-template-columns:var(--sidebar-width) minmax(0, 1fr) var(--panel-width);
  gap:var(--space-2);
  flex:1;
  min-height:0;
  padding:0;
}

.layout-grid.brief-collapsed {
  grid-template-columns:var(--space-5) minmax(0, 1fr) var(--panel-width);
}

.layout-grid.info-collapsed {
  grid-template-columns:var(--sidebar-width) minmax(0, 1fr) var(--space-5);
}

.layout-grid.brief-collapsed.info-collapsed {
  grid-template-columns:var(--space-5) minmax(0, 1fr) var(--space-5);
}

.panels {
  background:var(--color-bg-2);
  border-radius:var(--radius-panel);
  border:var(--stroke) solid var(--color-border);
}

.panel-header {
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:var(--space-2);
  background:var(--color-bg-2);
  border-radius:var(--radius-panel);
  border:var(--stroke) solid var(--color-border);
}

.panel-header h3 {
  margin:0;
  font-size:var(--text-caption);
}

.preset-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.preset-item {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  padding:var(--space-1) var(--space-1);
  background:var(--surface);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  cursor:pointer;
  transition:all var(--motion-normal);
}

.preset-item:hover {
  background:var(--bg-paper-2);
  border-color:var(--primary-color);
}

.preset-icon {
  width:var(--space-3);
  height:var(--space-3);
  display:inline-grid;
  place-items:center;
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  color:var(--primary-color);
  background:var(--surface);
  font-size:var(--text-caption);
  flex-shrink:0;
}

.preset-name {
  flex:1;
  font-size:var(--text-caption);
}

.preset-count {
  font-size:var(--text-caption);
  color:var(--color-text-3);
}

.chat-panel {
  display:flex;
  flex-direction:column;
  min-height:0;
  overflow:hidden;
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  background:var(--surface);
}

.brief-panel,
.info-panel {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
  min-height:0;
  overflow-y:auto;
}

.brief-panel.collapsed,
.info-panel.collapsed {
  overflow:hidden;
  align-items:center;
  background:var(--surface);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
}

.panel-collapse-control {
  width:var(--space-4);
  height:var(--space-4);
  display:inline-grid;
  place-items:center;
  margin:var(--space-1);
  padding:0;
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  color:var(--text-primary);
  background:var(--bg-paper-2);
  cursor:pointer;
  flex-shrink:0;
}

.panel-collapse-control:hover {
  color:var(--on-action);
  border-color:var(--primary-color);
  background:var(--primary-color);
}

.brief-panel > .panel-collapse-control,
.info-panel > .panel-collapse-control {
  align-self:flex-end;
  position:sticky;
  top:0;
  z-index:2;
}

.brief-panel.collapsed > .panel-collapse-control,
.info-panel.collapsed > .panel-collapse-control {
  align-self:center;
  position:static;
  margin:var(--space-1) 0;
}

.info-card {
  background:var(--surface);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  padding:var(--space-2);
}

.brief-card.dark {
  padding:var(--space-2);
  color:var(--ink);
  background:var(--surface-muted);
  border-radius:var(--radius-control);
  box-shadow: none;
}

.brief-top {
  display:flex;
  justify-content:space-between;
  gap:var(--space-1);
  padding-bottom:var(--space-2);
  margin-bottom:var(--space-2);
  border-bottom:var(--stroke) solid var(--line);
  color:var(--secondary-color);
  font-size:var(--text-caption);
  font-weight:var(--weight-strong);
  text-transform:uppercase;
}

.brief-card strong {
  display:block;
  color:var(--secondary-color);
  font-size:var(--text-page);
  line-height:var(--leading-tight);
  font-weight:var(--weight-strong);
}

.brief-card p {
  margin:var(--space-1) 0 var(--space-2);
  color:var(--ink-secondary);
}

.brief-stats {
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:var(--space-1);
}

.brief-stats span {
  padding:var(--space-1);
  border:var(--stroke) solid var(--line);
  color:var(--ink-secondary);
  font-size:var(--text-caption);
}

.info-card h4 {
  margin:0 0 var(--space-1);
  font-size:var(--text-card);
  color:var(--text-primary);
  font-weight:var(--weight-strong);
}

.card-desc {
  margin:0 0 var(--space-1);
  color:var(--text-secondary);
  font-size:var(--text-caption);
  line-height:1.5;
}

.agent-checklist {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.agent-check-item {
  display:flex;
  align-items:flex-start;
  gap:var(--space-1);
  padding:var(--space-1) var(--space-1);
  border:var(--stroke) solid var(--border-color);
  border-radius:var(--radius-control);
  background:var(--surface);
  cursor:pointer;
  transition:all var(--motion-normal);
}

.agent-check-item:hover {
  border-color:var(--primary-color);
  background:var(--bg-paper-2);
}

.agent-check-item.selected {
  border-color:var(--primary-color);
  background:var(--action-soft);
}

.agent-check-item.disabled {
  opacity:0.7;
  cursor:not-allowed;
}

.agent-checkbox {
  margin-top:calc(var(--space-1) / 2);
  accent-color:var(--primary-color);
}

.agent-check-avatar {
  width:var(--space-4);
  height:var(--space-4);
  border-radius:var(--radius-control);
  display:flex;
  align-items:center;
  justify-content:center;
  color:var(--text-primary);
  background:var(--bg-paper-2);
  border:var(--stroke) solid var(--line);
  font-size:var(--text-caption);
  flex-shrink:0;
}

.agent-check-info {
  flex:1;
  min-width:0;
}

.agent-check-name-row {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:var(--space-1);
}

.agent-check-name {
  font-size:var(--text-caption);
  font-weight:var(--weight-strong);
  color:var(--text-primary);
}

.agent-check-role {
  margin-top:calc(var(--space-1) / 2);
  font-size:var(--text-caption);
  color:var(--text-secondary);
}

.agent-check-status {
  padding:calc(var(--stroke) * 2) var(--space-1);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  white-space:nowrap;
}

.task-info {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.info-row {
  display:flex;
  justify-content:space-between;
  font-size:var(--text-caption);
}

.info-row .label {
  color:var(--color-text-3);
}

.info-row .value {
  color:var(--action);
  font-weight: var(--weight-medium);
}

.flow-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
  max-height:var(--tile-tall-height);
  overflow-y:auto;
}

.flow-item {
  display:flex;
  align-items:center;
  gap:var(--space-1);
}

.flow-dot {
  width:var(--space-1);
  height:var(--space-1);
  border-radius:50%;
  background:var(--action);
}

.flow-content {
  flex:1;
  display:flex;
  justify-content:space-between;
  font-size:var(--text-caption);
}

.flow-agent {
  color:var(--action);
  font-weight: var(--weight-medium);
}

.flow-action {
  color:var(--color-text-3);
}

.action-buttons {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
}

.help-content h4 {
  margin:var(--space-2) 0 var(--space-1);
  font-size:var(--text-caption);
}

.help-content h4:first-child {
  margin-top:0;
}

.help-content p, .help-content li {
  color:var(--color-text-2);
  font-size:var(--text-caption);
  line-height:1.6;
}

.help-content ol, .help-content ul {
  padding-left:var(--space-2);
}

@media (max-width: 1120px) {
  .layout-grid {
    grid-template-columns:1fr;
  }
  .layout-grid.brief-collapsed,
  .layout-grid.info-collapsed,
  .layout-grid.brief-collapsed.info-collapsed {
    grid-template-columns:1fr;
  }
  .brief-panel,
  .info-panel {
    order:2;
  }
}
</style>
