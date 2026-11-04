import { agentApi } from './api.js'
import { requestTeaching } from './request.js'
import { createSessionController } from './sessionController.js'
import { resetTutorHost } from './host.js'
import { clearDraft } from './draft.js'

// 全站唯一会话控制器：智航、对话页、题内抽屉、宠物都读同一次状态。
export const agentSession = createSessionController({
  apiClient: agentApi,
  request: requestTeaching,
})

let syncedUserId

export function syncAgentAccount(userId) {
  const next = userId === null || userId === undefined ? null : String(userId)
  if (next === syncedUserId) return agentSession
  syncedUserId = next
  clearDraft()
  resetTutorHost()
  if (agentSession.setAccount(next) && next) agentSession.restore()
  return agentSession
}

export function signOutAgent() {
  syncedUserId = null
  clearDraft()
  resetTutorHost()
  agentSession.destroy()
  agentSession.setAccount(null)
}
