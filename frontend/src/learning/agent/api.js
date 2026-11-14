import api from '@/api'

// 智航域 API：所有请求复用原 /api/ 包装，不新增后端接口，也不在组件里拼 URL。
export const agentApi = {
  agents: () => api.learningAgent.agents(),
  multiAgents: () => api.multiAgent.agents(),
  presets: () => api.multiAgent.presets(),
  tutoring: payload => api.learningAgent.tutoring(payload),
  recommend: () => api.learningAgent.recommend(),
  conversations: () => api.conversation.list(),
  conversation: id => api.conversation.detail(id),
  removeConversation: id => api.conversation.remove(id),
  profile: () => api.studentProfile.get(),
  protection: id => api.privacy.conversation(id),
}

// 只使用后端真实存在的会话字段；空历史就是空历史，不补造欢迎语为历史消息。
export function conversationMessages(payload) {
  const source = payload?.messages || payload?.conversation?.messages || []
  if (!Array.isArray(source)) return []
  return source
    .filter(item => item && (item.content || item.message))
    .map(item => ({
      id: item.id,
      role: item.role === 'user' ? 'user' : 'assistant',
      content: item.content || item.message || '',
      agentName: item.agent_name || item.agent || '',
      createdAt: item.created_at || item.timestamp || null,
      protection: item.protection || null,
    }))
}

// 列表接口的 message_count 用于挑选可恢复会话；不把没有消息的会话当成“上次对话”。
export function restorableConversation(list) {
  const items = Array.isArray(list) ? list : Array.isArray(list?.results) ? list.results : []
  return items
    .filter(item => Number(item?.message_count) > 0)
    .sort((a, b) => (Date.parse(b.updated_at || 0) || 0) - (Date.parse(a.updated_at || 0) || 0))[0] || null
}
