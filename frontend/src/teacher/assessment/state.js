import { emptyScoreForm, scorePayload } from './presentation.js'
const idOf = value => value?.id ?? value
export function createAssessmentState({ api, wrap = value => value, today } = {}) {
  let account = null, generation = 0, rosterGeneration = 0, disposed = false
  let saveRequest = null
  const state = wrap({ students: [], studentId: '', rows: [], effectiveIds: [], summary: null, plan: null, rules: null,
    rosterLoading: false, loading: false, planLoading: false, saving: false, rosterError: '', scoresError: '', planError: '', message: '', needsReconciliation: false, form: emptyScoreForm(today) })
  function clearSelection() {
    generation++
    state.studentId = ''; state.rows = []; state.effectiveIds = []; state.summary = state.plan = state.rules = null
    state.loading = state.planLoading = false; state.scoresError = state.planError = state.message = ''
    state.form = emptyScoreForm(today); state.needsReconciliation = false
  }
  function setAccount(next) {
    next = typeof next === 'string' && /^teacher:[1-9]\d*$/.test(next) ? next : null
    if (next === account) return false
    account = next; rosterGeneration++; clearSelection(); state.students = []; state.rosterError = ''; state.rosterLoading = false
    state.saving = false; saveRequest = null
    return true
  }
  const permitted = id => account && !disposed && state.students.some(student => String(student.id) === String(id))
  async function loadStudents() {
    if (!account || disposed) return
    const version = ++rosterGeneration, owner = account
    state.rosterLoading = true; state.rosterError = ''; state.students = []; clearSelection()
    try {
      const rows = await api.students()
      if (owner !== account || version !== rosterGeneration || disposed) return
      if (!Array.isArray(rows)) throw new Error('Invalid roster')
      state.students = rows.filter(row => ['number', 'string'].includes(typeof row?.id) && /^[1-9]\d*$/.test(String(row.id)) && Number.isSafeInteger(Number(row.id)) && (row.role === undefined || row.role === 'student'))
      if (state.students.length) await selectStudent(state.students[0].id)
    } catch {
      if (owner === account && version === rosterGeneration && !disposed) state.rosterError = '学生名单未能读取，请重试；不会补入演示学生。'
    } finally { if (owner === account && version === rosterGeneration && !disposed) state.rosterLoading = false }
  }
  async function readSelection() {
    const id = state.studentId
    if (!permitted(id)) return
    const version = ++generation, owner = account
    const current = () => !disposed && owner === account && version === generation && String(id) === String(state.studentId)
    state.rows = []; state.effectiveIds = []; state.summary = state.plan = state.rules = null
    state.loading = state.planLoading = true; state.scoresError = state.planError = ''
    await Promise.all([
      (async () => {
        try {
          const payload = await api.scores(id)
          if (!current()) return
          if (!Array.isArray(payload?.results) || payload.results.some(row => !row?.id || String(idOf(row.student)) !== String(id))) throw new Error('Invalid student scores')
          if (payload.effective_score_ids !== undefined && !Array.isArray(payload.effective_score_ids)) throw new Error('Invalid effective scores')
          state.rows = payload.results; state.effectiveIds = payload.effective_score_ids || []; state.summary = payload.score_summary || null; state.rules = payload.filter_rules || null
          state.needsReconciliation = false
        } catch { if (current()) state.scoresError = '评分记录未能读取，请重试。' }
        finally { if (current()) state.loading = false }
      })(),
      (async () => {
        try {
          const plan = await api.plan(id)
          if (!current()) return
          if (plan && String(idOf(plan.student)) !== String(id)) throw new Error('Wrong student plan')
          state.plan = plan || null
        } catch { if (current()) state.planError = '教学方案未能读取；不影响已保存的评分。' }
        finally { if (current()) state.planLoading = false }
      })(),
    ])
  }
  async function selectStudent(id) {
    clearSelection()
    if (!permitted(id)) return
    state.studentId = id
    await readSelection()
  }
  async function save() {
    if (saveRequest || state.needsReconciliation || !permitted(state.studentId)) return false
    let data
    try { data = scorePayload(state.form, state.studentId, today) }
    catch (error) { state.message = error.message; return false }
    const owner = account, id = state.studentId, version = generation, request = {}
    saveRequest = request; state.saving = true; state.message = ''
    const current = () => !disposed && owner === account && version === generation && String(id) === String(state.studentId)
    try {
      const saved = await api.save(data)
      if (!current()) return false
      if (!saved?.id || String(idOf(saved.student)) !== String(id)) throw new Error('Unconfirmed write')
      state.message = '评分已保存。正在重新读取评分与教学方案。'
      state.form = emptyScoreForm(today)
      await readSelection()
      if (!disposed && owner === account && String(id) === String(state.studentId) && generation === version + 1) {
        const found = state.rows.some(row => String(row.id) === String(saved.id))
        state.message = state.scoresError || state.planError || !found || !state.plan ? '评分已保存，但本次记录或方案暂未读回（历史最多读取 100 条）；请重新读取，不要重复提交。' : '评分已保存，本次评分记录与教学方案已读回。'
      }
      return true
    } catch (error) {
      if (current()) {
        const rejected = [400, 401, 403, 404].includes(error.response?.status)
        state.needsReconciliation = !rejected
        state.message = rejected ? '评分未保存，请核对权限、日期、分数与备注；填写内容已保留。' : '未能确认评分保存结果；填写内容已保留。请先重新读取历史，确认后再提交。'
      }
      return false
    } finally {
      if (saveRequest === request) { saveRequest = null; state.saving = false }
    }
  }
  function dispose() { disposed = true; generation++; rosterGeneration++ }
  return { state, setAccount, loadStudents, selectStudent, readSelection, save, dispose }
}
