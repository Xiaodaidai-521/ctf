import { normalizeEffect, canUseWindow } from '../../shared/learning/presentation.js'
export function createInsightsState({ api, wrap = value => value } = {}) {
  let account = null, rosterGen = 0, effectGen = 0, planGen = 0, dead = false
  const state = wrap({ students: [], studentId: '', days: 7, rosterLoading: false, effectLoading: false, planLoading: false,
    rosterError: '', effectError: '', planError: '', effect: null, rawEffect: null, plan: null })
  function clearStudent() {
    effectGen++; planGen++
    state.studentId = ''; state.effect = state.rawEffect = state.plan = null
    state.effectError = state.planError = ''; state.effectLoading = state.planLoading = false
  }
  function setAccount(next) {
    next = typeof next === 'string' && /^teacher:[1-9]\d*$/.test(next) ? next : null
    if (next === account) return false
    account = next; rosterGen++; clearStudent(); state.students = []; state.rosterError = ''; state.rosterLoading = false
    return true
  }
  async function loadStudents() {
    if (!account || dead) return
    const owner = account, gen = ++rosterGen
    state.rosterLoading = true; state.rosterError = ''; state.students = []; clearStudent()
    try {
      const rows = await api.students()
      if (dead || owner !== account || gen !== rosterGen) return
      if (!Array.isArray(rows)) throw new Error('Invalid roster')
      state.students = rows.filter(row => ['number', 'string'].includes(typeof row?.id) && /^[1-9]\d*$/.test(String(row.id)) && Number.isSafeInteger(Number(row.id)) && (row.role === undefined || row.role === 'student'))
    } catch { if (!dead && owner === account && gen === rosterGen) state.rosterError = '学生名单暂未能读取，请重试。' }
    finally { if (!dead && owner === account && gen === rosterGen) state.rosterLoading = false }
  }
  const permitted = id => account && !dead && state.students.some(student => String(student.id) === String(id))
  async function selectStudent(id) {
    clearStudent()
    if (!permitted(id)) return
    state.studentId = id
    await Promise.all([loadEffect(state.days), loadPlan()])
  }
  async function loadEffect(days = state.days) {
    if (!canUseWindow(days) || !permitted(state.studentId)) return
    state.days = Number(days)
    const id = state.studentId, owner = account, gen = ++effectGen
    const current = () => !dead && owner === account && gen === effectGen && String(id) === String(state.studentId)
    state.effect = state.rawEffect = null; state.effectError = ''; state.effectLoading = true
    try {
      const raw = await api.effect(id, Number(days))
      if (!current()) return
      if (String(raw?.student?.id) !== String(id)) throw new Error('Wrong student effect')
      const effect = normalizeEffect(raw, Number(days))
      if (!effect) throw new Error('Wrong window')
      state.rawEffect = raw; state.effect = effect
    } catch { if (current()) state.effectError = '本期学习活动未能读取，请重试；未用其他学生或参考数据替代。' }
    finally { if (current()) state.effectLoading = false }
  }
  async function loadPlan() {
    if (!permitted(state.studentId)) return
    const id = state.studentId, owner = account, gen = ++planGen
    const current = () => !dead && owner === account && gen === planGen && String(id) === String(state.studentId)
    state.plan = null; state.planError = ''; state.planLoading = true
    try {
      const plan = await api.plan(id)
      if (!current()) return
      if (plan && String(plan.student?.id ?? plan.student) !== String(id)) throw new Error('Wrong student plan')
      state.plan = plan || null
    } catch { if (current()) state.planError = '该学生教学方案暂未能读取，请重试。' }
    finally { if (current()) state.planLoading = false }
  }
  function dispose() { dead = true; rosterGen++; effectGen++; planGen++ }
  return { state, setAccount, loadStudents, selectStudent, loadEffect, loadPlan, dispose }
}
