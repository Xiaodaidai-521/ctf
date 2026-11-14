import { conversationMessages, restorableConversation } from './api.js'
import { sanitizeContext } from './context.js'

// 智航会话控制：创建、恢复、发送、重置、删除共用一套状态。
// 控制器活在组件之外，页面切换不会中断请求；登出或换账号会作废在途响应。
let nextMessageId = 1
const messageId = () => `local-${nextMessageId++}`

export function createSessionController({ apiClient, request, publish = () => {}, userId = null }) {
  let account = userId === null ? null : String(userId)
  let generation = 0 // 账号/会话代次，用于丢弃迟到响应
  let sendToken = 0 // 本端停止等待：只作废呈现，不声称后台已停止
  const listeners = new Set()

  const state = {
    conversationId: null,
    messages: [],
    resources: [],
    context: null,
    phase: 'idle',
    restoring: false,
    sending: false,
    error: '',
    hasHistory: false,
    // 后台真实返回的元数据（含可选 taskBinding.hintLevel）；没有就保持 null。
    metadata: null,
    protection: null,
  }

  function snapshot() { return { ...state, messages: [...state.messages] } }
  function emit() {
    const value = snapshot()
    publish(value)
    for (const listener of listeners) listener(value)
  }
  function subscribe(listener) {
    listeners.add(listener)
    listener(snapshot())
    return () => listeners.delete(listener)
  }

  function setPhase(phase) {
    state.phase = phase
    if (phase === 'working') state.sending = true
    if (phase !== 'working') state.sending = false
    emit()
  }

  function setAccount(nextUserId) {
    const next = nextUserId === null || nextUserId === undefined ? null : String(nextUserId)
    if (next === account) return false
    account = next
    generation++
    Object.assign(state, {
      conversationId: null, messages: [], resources: [], context: null,
      phase: 'idle', restoring: false, sending: false, error: '', hasHistory: false, metadata: null, protection: null,
    })
    emit()
    return true
  }

  function setContext(context) {
    state.context = sanitizeContext(context)
    emit()
  }

  // 只恢复有消息的最近会话；恢复失败保留空态并明确提示，不伪造历史。
  async function restore() {
    if (!account) return { restored: false, reason: 'unauthenticated' }
    const version = generation
    state.restoring = true
    state.protection = null
    state.error = ''
    emit()
    try {
      const list = await apiClient.conversations()
      if (version !== generation) return { restored: false, reason: 'stale' }
      const target = restorableConversation(list)
      if (!target) {
        state.hasHistory = false
        return { restored: false, reason: 'empty' }
      }
      const detail = await apiClient.conversation(target.id)
      if (version !== generation) return { restored: false, reason: 'stale' }
      state.conversationId = target.id
      state.messages = conversationMessages(detail)
      state.protection = detail.protection || null
      state.hasHistory = state.messages.length > 0
      return { restored: state.hasHistory, conversationId: target.id }
    } catch {
      if (version === generation) {
        state.error = '上次对话暂时未能恢复，你可以直接开始新的学习。'
        state.hasHistory = false
      }
      return { restored: false, reason: 'error' }
    } finally {
      if (version === generation) {
        state.restoring = false
        emit()
      }
    }
  }

  function pushUser(content) {
    state.messages.push({ id: messageId(), role: 'user', content, createdAt: new Date().toISOString() })
  }

  // 发送期间再次提交会被拒绝；晚到的旧账号/旧会话响应不会混入当前对话。
  async function send(input = {}) {
    const message = String(input.message || '').trim()
    if (!message) return { ok: false, reason: 'empty' }
    if (!account) return { ok: false, reason: 'unauthenticated' }
    if (state.sending) return { ok: false, reason: 'busy' }
    if (state.restoring) return { ok: false, reason: 'restoring' }
    const version = generation
    const token = ++sendToken
    const conversationId = state.conversationId
    state.error = ''
    pushUser(message)
    state.protection = null
    setPhase('working')
    try {
      const result = await request({
        message,
        agentIds: input.agentIds || ['tutor'],
        activeAgent: input.activeAgent || null,
        challengeId: input.challengeId || (state.context?.kind === 'challenge' ? state.context.ref : null),
        challengeQuestion: input.challengeQuestion || null,
        conversationId,
        model: input.model || { id: 'default', provider: '' },
        forceAI: Boolean(input.forceAI),
        mode: input.mode || 'learning',
        knowledgeScope: input.knowledgeScope || 'all',
      })
      if (version !== generation) return { ok: false, reason: 'stale' }
      if (token !== sendToken) return { ok: false, reason: 'cancelled' }
      if (result?.conversation_id) state.conversationId = result.conversation_id
      const responses = (result?.responses || (result?.content ? [{ content: result.content, agent_name: result.agent_name }] : []))
        .filter(response => typeof response.content === 'string' && response.content.trim() && response.provider !== 'error')
      if (!responses.length) throw new Error('No teaching response')
      for (const [index, response] of responses.entries()) {
        const last = index === responses.length - 1
        state.messages.push({
          id: messageId(), role: 'assistant', content: response.content || '',
          agentName: response.agent_name || response.agentName || '教学辅导师',
          provider: response.provider || '', step: response.step || null, stepName: response.step_name || '',
          resources: response.rag_sources || [],
          resourceList: last ? (result.resources || result.resourceList || []) : [],
          noMatchedResource: last && Boolean(result.noMatchedResource),
          imageUrl: response.image_url || null,
          createdAt: new Date().toISOString(),
        })
      }
      if (result?.resources?.length) state.resources = result.resources
      state.metadata = result?.metadata || null
      if (state.conversationId && apiClient.protection) {
        try {
          const detail = await apiClient.protection(state.conversationId)
          if (version !== generation || token !== sendToken) return { ok: false, reason: 'stale' }
          state.protection = detail.protection || null
        } catch { /* 没有完整核验结果时保留空状态。 */ }
      }
      if (version !== generation || token !== sendToken) return { ok: false, reason: 'stale' }
      state.hasHistory = true
      setPhase('complete')
      return { ok: true, result }
    } catch (error) {
      if (version !== generation) return { ok: false, reason: 'stale' }
      if (token !== sendToken) return { ok: false, reason: 'cancelled' }
      state.error = '这次讲解没有完成，请稍后再试。'
      setPhase('error')
      return { ok: false, reason: 'error', error }
    }
  }

  // 重置只清空本次会话；只有明确要求时才删除服务端会话。
  async function reset({ deleteServer = false } = {}) {
    const conversationId = state.conversationId
    generation++
    state.conversationId = null
    state.messages = []
    state.resources = []
    state.hasHistory = false
    state.restoring = false
    state.error = ''
    state.metadata = null
    state.protection = null
    setPhase('idle')
    if (deleteServer && conversationId) {
      try { await apiClient.removeConversation(conversationId) } catch { state.error = '会话已在本页清空，服务端记录暂未删除。' }
    }
    emit()
    return { conversationId }
  }

  // 没有后端取消接口：只停止本页等待，文案不暗示后台已终止。
  function cancelWaiting() {
    if (!state.sending) return false
    sendToken++
    state.sending = false
    state.phase = 'idle'
    state.error = '已停止本页等待；后台请求可能仍在处理。'
    emit()
    return true
  }

  function destroy() { generation++; sendToken++ }

  return { state, subscribe, setAccount, setContext, restore, send, reset, cancelWaiting, destroy }
}
