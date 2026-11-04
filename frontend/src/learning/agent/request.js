import api, { http } from '@/api'
import { tutorResourceListFromResponse } from '@/utils/tutorResources'
import { trackRequest } from './lifecycle.js'

// 保留原教学、多智能体、题目三种后端请求及全部编排参数。
export function requestTeaching({ agentIds, message, activeAgent, challengeId, conversationId, model, forceAI, mode, knowledgeScope, challengeQuestion }) {
  return trackRequest(async () => {
    if (agentIds.includes('tutor')) {
      let studentLevel = 'beginner'
      try {
        const profile = await api.studentProfile.get()
        if (profile?.preference?.difficulty_bias !== undefined) {
          const bias = profile.preference.difficulty_bias
          studentLevel = bias > 0.3 ? 'advanced' : bias < -0.3 ? 'beginner' : 'intermediate'
        }
      } catch { /* 沿用原请求的初始水平。 */ }
      const res = await api.learningAgent.tutoring({
        concept_name: message, question: message, student_level: studentLevel,
        conversation_id: conversationId, selected_model: model.id, selected_provider: model.provider,
      })
      const resources = tutorResourceListFromResponse(res)
      const signal = res.noMatchedResource ?? res.resourcePreparation?.noMatchedResource
      return {
        conversation_id: res.conversation_id, mode: 'tutoring', resources, resourceList: resources,
        metadata: res.metadata || null,
        noMatchedResource: signal === undefined ? false : Boolean(signal),
        responses: (res.steps || []).map((step, index) => ({
          agent_id: 'tutor', agent_name: activeAgent?.id === 'tutor' ? activeAgent.name : '教学辅导师',
          content: step.content || '', provider: step.provider || 'unknown', step: step.step || index + 1,
          step_name: step.step_name, rag_mode: step.rag_mode, rag_sources: step.rag_sources || [], image_url: step.image_url,
        })),
      }
    }
    const isChallenge = challengeId || challengeQuestion
    return http.post('/ai/multi-agent/chat/', {
      message, agent_ids: agentIds, mode: isChallenge ? 'challenge_solution' : mode,
      challenge_id: challengeId || null, force_ai: forceAI, conversation_id: conversationId,
      selected_model: model.id, selected_provider: model.provider,
      knowledge_scope: isChallenge ? 'current' : knowledgeScope,
    })
  })
}
