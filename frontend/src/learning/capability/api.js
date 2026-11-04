import api from '@/api'
import { asList, finiteNumber } from '@/learning/contracts.js'

export const capabilityApi = {
  map: () => api.learningMap.myMap(),
  recommendations: track => api.learningMap.myRecommendations(track ? { goal_track: track } : {}),
  diagnosticQuestions: track => api.learningMap.diagnosticQuestions(track ? { track } : {}),
  submitDiagnosis: (track, answers) => api.learningMap.submitDiagnosis({ goal_track: track, answers }),
  claimTask: id => api.learningMap.claimTask(id),
  changelog: params => api.learningMap.myChangelog(params),
}

export const capabilityName = node => node?.name || node?.title || node?.capability_name || '未命名能力'

// 未知状态明确未知，不画 0 掌握；未开放能力单列。
export function capabilityState(node) {
  const state = node?.state || node?.status
  if (!state) return { key: 'unknown', label: '掌握情况未知' }
  const map = {
    mastered: { key: 'mastered', label: '已掌握' },
    independent: { key: 'independent', label: '独立证据' },
    assisted: { key: 'assisted', label: '提示后待复测' },
    learning: { key: 'learning', label: '学习中' },
    not_started: { key: 'not_started', label: '未开始' },
    locked: { key: 'locked', label: '未开放' },
  }
  return map[state] || { key: 'unknown', label: '掌握情况未知' }
}

export function evidenceSummary(node) {
  const recent = node?.recent_evidence || node?.evidence
  if (!recent) return { result: '暂无证据', task: null, time: null, assisted: null, retestAt: null }
  return {
    result: recent.result_label || recent.result || '结果未知',
    task: recent.task_title || recent.task?.title || null,
    time: recent.occurred_at || recent.created_at || null,
    assisted: typeof recent.assisted === 'boolean' ? recent.assisted : null,
    retestAt: recent.retest_at || null,
  }
}

// 领取必须使用服务端真实 attempt；没有落点时如实说明。
export function claimDestination(payload) {
  const attemptId = finiteNumber(payload?.attempt_id)
  if (attemptId !== null) return { available: true, path: `/learning-knowledge/${attemptId}` }
  return { available: false, reason: '领取成功，但任务入口暂未提供。' }
}

export { asList }
