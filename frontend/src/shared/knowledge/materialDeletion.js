import { requestKey } from '../../learningKnowledge/requestGeneration.js'

export const initialMaterialDeletion = () => ({ target: null, reason: '', busy: false, error: '', message: '', uncertain: false })
export function materialDeletionError(error) {
  const status = error.response?.status
  if (status === 401) return '登录已失效，请重新登录后核对材料。'
  if (status === 403) return '你没有删除这份材料的权限，请联系课程负责人或管理员。'
  if (status === 404) return '这份材料已不可用，请重新加载列表核对。'
  if (status === 409) return '材料版本或状态已变化，请重新加载并检查最新版本后再删除。'
  if (status === 400) return '删除未被接受，请检查理由和材料版本后重试。'
  return '删除结果尚未确认，请重新加载列表核对，不要重复提交。'
}

export function createMaterialDeletion({ state, privacy, api, getRole, reload }) {
  const allowed = () => ['teacher', 'admin'].includes(getRole())
  function clear() { Object.assign(state, initialMaterialDeletion()) }
  function open(row) {
    if (!allowed() || state.busy || state.uncertain || !row?.material_id) return
    clear()
    state.target = { material_id: row.material_id, revision: row.revision, title: row.title }
  }
  function close() { if (!state.busy && !state.uncertain) state.target = null }
  async function confirm() {
    if (!allowed() || state.busy || state.uncertain || !state.target) return
    if (!state.reason.trim()) { state.error = '请填写删除理由。'; return }
    if (!Number.isSafeInteger(state.target.revision) || state.target.revision < 1) { state.error = '材料版本尚未确认，请重新加载列表后再删除。'; return }
    const ticket = privacy.begin()
    if (!ticket) return
    const target = state.target
    const body = { expected_revision: target.revision, reason: state.reason.trim(), idempotency_key: requestKey() }
    state.busy = true; state.error = ''; state.message = ''
    let confirmed = false
    try {
      await api.deleteMaterial(target.material_id, body, ticket.signal)
      if (!ticket.isCurrent()) return
      confirmed = true
      state.target = null; state.reason = ''
      state.message = '材料已删除，正在核对列表。'
      await reload(ticket, target.material_id)
      if (ticket.isCurrent()) state.message = '材料已删除，列表已更新。'
    } catch (error) {
      if (!ticket.isCurrent()) return
      if (confirmed) {
        state.message = '材料已删除，但列表暂未更新，请重新加载。'
        state.uncertain = true
      } else {
        state.error = materialDeletionError(error)
        state.uncertain = ![400, 401, 403, 404, 409].includes(error.response?.status)
      }
    } finally { if (ticket.isCurrent()) state.busy = false; ticket.finish() }
  }
  return { clear, open, close, confirm }
}
