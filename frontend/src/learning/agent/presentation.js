// 智航呈现层：只做可读映射，不生成教学结论，也不模拟步骤进度。
export const TEACHING_STEPS = Object.freeze(['评估', '讲解', '练习', '检验'])

const ROLE_LABELS = Object.freeze({
  tutor: '教学辅导师', local: '本地教练', legal: '合规审查', security: '安全专家', code: '代码助手',
})

export function speakerLabel(message) {
  if (message?.role === 'user') return '我'
  const name = message?.agentName || message?.agent_name
  if (name) return name
  return ROLE_LABELS[message?.agentId] || '教学智能体'
}

export function speakerKey(message) {
  return message?.agentId || message?.agent_id || (message?.role === 'user' ? 'student' : 'tutor')
}

// 进度只认真实返回的步骤；没有数据就说“进度暂不可读取”，不按发问次数推进。
export function progressFrom(messages) {
  const steps = []
  for (const message of Array.isArray(messages) ? messages : []) {
    if (message?.role === 'user') continue
    const step = Number(message?.step)
    if (Number.isFinite(step) && step > 0) steps.push({ index: step, name: message.stepName || message.step_name || TEACHING_STEPS[step - 1] || `第 ${step} 步` })
  }
  if (!steps.length) return { available: false, label: '进度暂不可读取', items: TEACHING_STEPS.map((name, index) => ({ index: index + 1, name, state: 'unknown' })) }
  const highest = Math.max(...steps.map(item => item.index))
  return {
    available: true,
    label: `已完成到第 ${Math.min(highest, TEACHING_STEPS.length)} 步`,
    items: TEACHING_STEPS.map((name, index) => ({
      index: index + 1, name,
      state: index + 1 < highest ? 'done' : index + 1 === highest ? 'current' : 'pending',
    })),
  }
}

export function statusLine(message) {
  if (message?.kind === 'handoff') return `已转交：${message.to || '相关专家'}`
  if (message?.kind === 'tool') return message.summary || '正在准备教学资料'
  return ''
}

// 协作记录只导出真实存在的字段；没有全文就叫协作记录，不谎称完整备份。
export function collaborationRecord({ title, personaSnippet, transcript, exportedAt }) {
  return {
    title: title || '协作记录',
    note: '本记录只包含当前可读取的协作信息，不等同于完整对话备份。',
    personaSnippet: typeof personaSnippet === 'string' ? personaSnippet.slice(0, 200) : '',
    exportedAt: exportedAt || new Date().toISOString(),
    messages: (Array.isArray(transcript) ? transcript : []).map(item => ({
      role: item.role === 'user' ? 'user' : 'assistant',
      speaker: speakerLabel(item),
      content: typeof item.content === 'string' ? item.content : '',
      createdAt: item.createdAt || item.created_at || null,
    })),
  }
}

// 资源引用来自真实返回，空与加载失败分开。
export function resourceView(list, error = '') {
  const items = (Array.isArray(list) ? list : []).map(item => ({
    id: item.id ?? item.resource_id ?? item.article_id ?? null,
    title: item.title || item.name || '学习资料',
    type: item.type || item.resource_type || item.kind || '',
    reason: item.reason || item.relevance || '',
    url: item.url || item.link || '',
  }))
  if (items.length) return { items, state: 'ready', message: '' }
  return { items, state: error ? 'error' : 'empty', message: error || '这次没有匹配到可直接引用的资料。' }
}
