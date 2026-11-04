import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { computed, reactive, ref, watch, effectScope, nextTick } from 'vue'
import { parse, compileScript, compileStyle, compileTemplate } from 'vue/compiler-sfc'
import { createLearningReadApi } from '../../shared/learning/api.js'
import { configurationVersionLabel } from '../candidatePresentation.js'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const defer = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const settle = async () => { for (let index = 0; index < 40; index++) await Promise.resolve(); await nextTick() }
function page(path, mocks, names) {
  const script = parse(read(path)).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  return runInNewContext(`${script}\n;({ ${names} })`, { computed, reactive, ref, watch, onBeforeUnmount() {}, configurationVersionLabel, ...mocks })
}
const files = ['../TeacherLearningDashboard.vue', '../TeacherLearningEffect.vue', '../LearningEffectAnalysis.vue', '../TeacherOperations.vue', '../assessment/TeacherAssessment.vue', './EvaluationStatistics.vue', '../../shared/learning/ActivityFacts.vue', '../../shared/learning/TeachingPlan.vue', '../../shared/learning/TrendChart.vue', '../../learning/growth/components/LearningActivity.vue']
for (const file of files) test(`scoped teacher/shared page compiles: ${file}`, () => {
  const source = read(file), { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'insights' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: 'insights', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  for (const style of descriptor.styles) {
    assert.equal(style.scoped, true)
    const css = style.src ? readFileSync(new URL(style.src, new URL(file, import.meta.url)), 'utf8') : style.content
    assert.deepEqual(compileStyle({ source: css, filename: file, id: 'insights', scoped: true }).errors, [])
    assert.doesNotMatch(css, /#[\da-f]{3,8}\b|rgba?\(/i)
  }
})
test('teacher pages import neither admin pages, student internals nor personal read APIs', () => {
  for (const file of files.slice(0, 6)) {
    const source = read(file)
    assert.doesNotMatch(source, /from ['"]@\/(admin\/views|learning\/)/)
    assert.doesNotMatch(source, /learningAgent\.recommend|analytics\.insights\(|weeklySummary\(|mySubmissions|\/me\b|mockTeacherAnalytics/)
  }
  assert.match(read('../LearningEffectAnalysis.vue'), /id="task-evidence"/)
  assert.doesNotMatch(read('../LearningEffectAnalysis.vue'), /TeacherOperations/)
  const admin = read('../../admin/views/LearningScores.vue')
  assert.doesNotMatch(admin, /@\/teacher|isTeacherView|getDemo|createTeacherScore/)
  assert.match(admin, /AssessmentSupervision/)
  const supervisionApi = read('../../admin/insights/api.js')
  for (const endpoint of ['adminStudentReport', 'adminScores', 'adminTeachingPlan']) assert.match(supervisionApi, new RegExp(endpoint))
  assert.doesNotMatch(supervisionApi, /createAdminScore\(/)
  assert.match(read('../assessment/api.js'), /createTeacherScore/)
})
test('student activity retains its existing request, chart, reference interactions and exposes shared facts', () => {
  const activity = read('../../learning/growth/components/LearningActivity.vue')
  for (const marker of ['learningEffectSummary(undefined, days)', 'selectWindow', 'drawChart', 'drawReference', 'referenceActivity', 'legend', 'requestVersion', 'defineExpose']) assert.ok(activity.includes(marker))
  assert.match(activity, /ActivityFacts :effect="effect" :show-table="false"/)
  assert.match(activity, /ActivityFacts :effect="effect" :show-facts="false"/)
  assert.match(activity, /RecordView v-if="item.evidence" :value="item.evidence"/)
  assert.doesNotMatch(activity, /JSON.stringify\(evidence\)/)
  const mastery = read('../../learning/growth/components/MasteryOverview.vue')
  assert.match(mastery, /RecordView class="score-dims" :value="score.dimension_scores"/)
  assert.doesNotMatch(mastery, /entries.map\(\(\[key, value\]\)/)
})
test('catalog versions in task detail and runtime use the same readable label', () => {
  const source = read('./EvaluationStatistics.vue')
  assert.match(source, /configurationVersionLabel\(run\.versions\?\.catalog_version\)/)
  assert.match(source, /configurationVersionLabel\(detail\.versions\?\.catalog_version\)/)
  assert.doesNotMatch(source, /\{\{ (?:run|detail)\.versions\?\.catalog_version \|\|/)
})
test('student roster keeps readable column headings inside its mobile scroll container', () => {
  const css = read('./learning.css')
  assert.match(read('../TeacherLearningDashboard.vue'), /class="table-scroll"><table>/)
  assert.match(css, /\.table-scroll \{ overflow-x: auto; \}/)
  assert.match(css, /\.teacher-insights \.table-scroll table \{ min-width: 720px; \}/)
  assert.match(css, /\.teacher-insights \.table-scroll th \{ white-space: nowrap; \}/)
})
test('teaching plan with missing basis does not invent effective teacher scores', () => {
  const plan = read('../../shared/learning/TeachingPlan.vue')
  assert.match(plan, /方案依据暂未返回/)
  assert.doesNotMatch(plan, /\|\| '依据：学生自评与有效评分'/)
})
test('new chart has one axis, thin line, non-color-only table and safe crosshair tooltip', () => {
  const chart = read('../../shared/learning/TrendChart.vue')
  assert.match(chart, /width: 2/); assert.match(chart, /symbolSize: 8/); assert.match(chart, /renderMode: 'richText'/)
  assert.match(chart, /axisPointer: \{ type: 'line' \}/); assert.match(chart, /<table>/); assert.match(chart, /connectNulls: false/)
})
test('central domain adapters call only existing teacher and authorized shared APIs', async () => {
  const calls = [], record = name => (...args) => { calls.push([name, ...args]); return name }
  const client = { analytics: Object.fromEntries(['teacherStudentReport', 'teacherScores', 'createTeacherScore', 'teacherTeachingPlan', 'learningEffectSummary'].map(name => [name, record(name)])), learningMap: { teacherCatalog: record('catalog') }, skillReview: { teacherRetests: record('retests') } }
  const evalClient = Object.fromEntries(['students', 'learning', 'runtime', 'attempt', 'todos', 'createTodo', 'changeTodo', 'syncTodos', 'consumeReceipts'].map(name => [name, record(name)]))
  const extract = (file, name) => runInNewContext(`${read(file).replace(/^import .*$/gm, '').replace(/^export default.*$/gm, '').replace('export function', 'function')}\n;${name}`, { createLearningReadApi })
  const scores = extract('../assessment/api.js', 'createTeacherAssessmentApi')(client)
  scores.students(); scores.scores(2); scores.save({ student: 2 }); scores.plan(2)
  const insights = extract('./api.js', 'createTeacherInsightsApi')(client, evalClient)
  insights.effect(2, 90); insights.plan(2); insights.learning({ mode: 'demo' }); insights.runtime({ mode: 'demo' })
  assert.equal(calls[0][0], 'teacherStudentReport'); assert.equal(calls[1][1].student_id, 2)
  assert.deepEqual(calls[4], ['learningEffectSummary', 2, 90]); assert.equal(calls[6][1].mode, 'demo'); assert.equal(calls[7][1].mode, 'demo')
})
function evaluationPage(overrides = {}) {
  const user = reactive({ userInfo: { role: 'teacher', id: 8 } })
  const service = { catalog: async () => ({ capabilities: [] }), evaluationStudents: async ({ mode }) => ({ source: mode, students: mode === 'formal' ? [{ id: 1, username: '甲' }] : [] }), learning: async ({ mode, student_id }) => ({ source: mode, rows: ['a', 'b'].map(attempt_id => ({ attempt_id, student_id: student_id || 1, source: mode })), version_groups: [], source_status: {} }), runtime: async ({ mode }) => ({ source: mode, records: [] }), ...overrides }
  const scope = effectScope()
  const p = scope.run(() => page('./EvaluationStatistics.vue', { useUserStore: () => user, evaluation: service }, 'load, resetMode, showDetail, loadRuntime, data, detail, runtime, loading, mode, studentId, taskKey, knowledgePoint, catalogVersion, errorMessage, params'))
  return { p, user, service, scope }
}
test('evaluation preserves strict demo isolation and all original filter arguments', async () => {
  const { p, scope } = evaluationPage(); await settle()
  p.studentId.value = 2; p.taskKey.value = 'task'; p.knowledgePoint.value = 'point'; p.catalogVersion.value = 'version'
  assert.equal(p.data.value, null)
  const params = JSON.parse(JSON.stringify(p.params()))
  assert.deepEqual(params, { mode: 'formal', student_id: 2, task_key: 'task', knowledge_point_id: 'point', catalog_version: 'version' })
  p.mode.value = 'demo'; await p.resetMode()
  assert.equal(p.data.value.source, 'demo'); assert.equal('student_id' in p.params(), false)
  await p.showDetail('a'); assert.equal(p.detail.value, null)
  scope.stop()
})
test('evaluation detail ignores late clicks and invalidates on changed filters and account', async () => {
  const a = defer(), b = defer(); const { p, user, scope } = evaluationPage({ attempt: id => id === 'a' ? a.promise : b.promise }); await settle()
  const first = p.showDetail('a'), second = p.showDetail('b')
  b.resolve({ attempt_id: 'b', student_id: 1, source: 'formal', task_title: '最近点击' }); await second
  a.reject(Error('old failure')); await first
  assert.equal(p.detail.value.task_title, '最近点击'); assert.equal(p.errorMessage.value, '')
  p.taskKey.value = 'other'; assert.equal(p.data.value, null); assert.equal(p.detail.value, null)
  user.userInfo = null; assert.equal(p.runtime.value, null)
  scope.stop()
})
test('evaluation rejects a formal payload in demo mode instead of merging real students', async () => {
  const { p, service, scope } = evaluationPage(); await settle()
  service.learning = async () => ({ source: 'formal', rows: [] }); p.mode.value = 'demo'; await p.resetMode()
  assert.equal(p.data.value, null); assert.match(p.errorMessage.value, /未使用演示数据替代/)
  scope.stop()
})
test('runtime requests are mode-scoped and late responses cannot survive filter changes', async () => {
  const pending = defer(); const calls = []
  const { p, scope } = evaluationPage({ runtime: params => { calls.push(params); return pending.promise } }); await settle()
  const reading = p.loadRuntime(); p.studentId.value = 2; pending.resolve({ source: 'formal', records: [{ run_id: 'old' }] }); await reading
  assert.equal(p.runtime.value, null); assert.equal(calls[0].mode, 'formal')
  scope.stop()
})
test('independent actions handle duplicate writes, changing student and failed transfers', async () => {
  const user = reactive({ userInfo: { role: 'teacher', id: 8 } }), scope = effectScope(), writes = [], pending = defer()
  const evaluation = { todos: async () => ({ groups: {} }), students: async () => [{ id: 1, username: '甲' }], retests: async () => ({ items: [] }), learning: async () => ({ source: 'formal', rows: [{ attempt_id: 'attempt', student_id: 1, source: 'formal', task_title: '任务' }] }), createTodo: data => { writes.push(data); return pending.promise }, changeTodo: async () => { throw { response: { status: 409 } } } }
  const p = scope.run(() => page('../TeacherOperations.vue', { useUserStore: () => user, evaluation }, 'run, create, resolveTransfer, createStudent, attemptId, attempts, ownerNames, drafts, message, groups, busy'))
  await settle(); assert.equal(p.busy.value, false, 'initial roster/options loading must finish before testing writes'); assert.equal(p.attempts.value.length, 1)
  p.createStudent.value = '1'; p.attemptId.value = 'attempt'
  const saving = p.run(p.create); await p.run(p.create); assert.equal(writes.length, 1)
  p.createStudent.value = '2'; assert.equal(p.attemptId.value, '')
  user.userInfo = null; pending.resolve({}); await saving
  assert.equal(p.message.value, ''); assert.equal(Object.keys(p.groups.value).length, 0)
  user.userInfo = { id: 9, role: 'teacher' }; await settle()
  const item = { todo_id: 'todo', attempt_id: 'attempt', student_id: 1, owner_id: 9, revision: 1 }
  p.groups.value = { help: [item] }; p.drafts.todo = { assigneeId: '9', summary: '交接' }
  await p.run(() => p.resolveTransfer(item))
  assert.match(p.message.value, /待办已变化/); assert.equal(p.busy.value, false)
  scope.stop()
})
test('switching mode invalidates a pending real detail immediately, without needing a change event', async () => {
  const pending = defer(), roster = defer()
  const { p, service, scope } = evaluationPage({ attempt: () => pending.promise }); await settle()
  const reading = p.showDetail('a')
  service.evaluationStudents = () => roster.promise
  p.mode.value = 'demo'
  assert.equal(p.data.value, null); assert.equal(p.detail.value, null)
  pending.resolve({ attempt_id: 'a', student_id: 1, source: 'formal' }); await reading
  assert.equal(p.detail.value, null)
  roster.resolve({ source: 'demo', students: [] }); await settle()
  assert.equal(p.data.value.source, 'demo')
  scope.stop()
})
test('evaluation rejects wrong-student details, mixed demo rows and wrong-student runtime', async () => {
  const { p, service, scope } = evaluationPage({ attempt: async () => ({ attempt_id: 'a', student_id: 2, source: 'formal' }) }); await settle()
  await p.showDetail('a'); assert.equal(p.detail.value, null); assert.match(p.errorMessage.value, /明细读取失败/)
  service.learning = async () => ({ source: 'formal', rows: [{ attempt_id: 'a', student_id: 1, source: 'demo' }], version_groups: [] })
  await p.load(); assert.equal(p.data.value, null)
  service.learning = async () => ({ source: 'formal', rows: [{ attempt_id: 'a', student_id: 1, source: 'formal' }], version_groups: [] })
  p.studentId.value = 1; await p.load()
  service.runtime = async () => ({ source: 'formal', records: [{ run_id: 'r', student_id: 2 }] })
  await p.loadRuntime(); assert.equal(p.runtime.value, null)
  scope.stop()
})
test('catalog requests follow the selected version and reject old or mismatched catalogs', async () => {
  const a = defer(), b = defer(), calls = []
  const { p, scope } = evaluationPage({ catalog: params => { calls.push(params); return params.version === 'a' ? a.promise : params.version === 'b' ? b.promise : Promise.resolve({ capabilities: [] }) } }); await settle()
  p.catalogVersion.value = 'a'; p.catalogVersion.value = 'b'
  b.resolve({ version: 'b', capabilities: [] }); await settle()
  a.resolve({ version: 'a', capabilities: [] }); await settle()
  assert.equal(calls.at(-1).version, 'b')
  scope.stop()
})
test('non-teachers cannot trigger evaluation reads through imported filters or mode changes', async () => {
  const calls = []
  const { p, user, service, scope } = evaluationPage(); await settle()
  user.userInfo = { role: 'student', id: 1 }
  for (const name of ['catalog', 'evaluationStudents', 'learning', 'runtime', 'attempt']) service[name] = async () => { calls.push(name); return {} }
  p.catalogVersion.value = 'v2'; p.mode.value = 'demo'
  await p.load(); await p.resetMode(); await p.loadRuntime(); await p.showDetail('a')
  assert.deepEqual(calls, []); assert.equal(p.data.value, null)
  scope.stop()
})
const todo = (extra = {}) => ({ todo_id: 'todo', attempt_id: 'attempt', student_id: 1, owner_id: 8, revision: 1, status: 'in_progress', ...extra })
async function operationsPage(overrides = {}) {
  const user = reactive({ userInfo: { role: 'teacher', id: 8 } }), scope = effectScope()
  const service = { todos: async () => ({ groups: { help: [todo()] } }), students: async () => [{ id: 1, username: '甲', role: 'student' }], retests: async () => ({ items: [] }), learning: async () => ({ source: 'formal', rows: [{ attempt_id: 'attempt', student_id: 1, source: 'formal' }] }), ...overrides }
  const p = scope.run(() => page('../TeacherOperations.vue', { useUserStore: () => user, evaluation: service }, 'run, refresh, create, change, resolveTransfer, importAssignee, canEdit, retestsFor, createStudent, attemptId, attempts, retests, drafts, message, groups, busy, needsRefresh'))
  await settle(); assert.equal(p.busy.value, false)
  return { p, user, service, scope }
}
test('todo POST success is not readback success: stale GET blocks duplicate writes and preserves input', async () => {
  let writes = 0
  const { p, service, scope } = await operationsPage({ createTodo: async () => { writes++; return todo({ todo_id: 'created' }) } })
  p.createStudent.value = '1'; p.attemptId.value = 'attempt'
  await p.run(p.create)
  assert.equal(writes, 1); assert.equal(p.attemptId.value, 'attempt'); assert.equal(p.needsRefresh.value, true)
  assert.match(p.message.value, /写入已确认.*未能读回/)
  await p.run(p.create); assert.equal(writes, 1)
  service.todos = async () => ({ groups: { help: [todo({ todo_id: 'created' })] } })
  await p.run(p.refresh); assert.equal(p.needsRefresh.value, false)
  scope.stop()
})
test('empty or unconfirmed todo write results never produce local demo success', async () => {
  const { p, scope } = await operationsPage({ createTodo: async () => ({}) })
  p.createStudent.value = '1'; p.attemptId.value = 'attempt'; await p.run(p.create)
  assert.equal(p.needsRefresh.value, true); assert.match(p.message.value, /未能确认写入/); assert.equal(p.attemptId.value, 'attempt')
  assert.equal(p.groups.value.help.length, 1)
  scope.stop()
})
test('todo options reject demo or another student attempts instead of relabeling them as selected student', async () => {
  for (const row of [{ attempt_id: 'demo', source: 'demo', student_id: 1 }, { attempt_id: 'other', source: 'formal', student_id: 2 }]) {
    const { p, scope } = await operationsPage({ learning: async () => ({ source: 'formal', rows: [row] }) })
    assert.equal(p.attempts.value.length, 0); assert.match(p.message.value, /部分学生.*未能读取/); scope.stop()
  }
})
test('only the current owner can mutate a current revision and retest choices bind the original attempt', async () => {
  let writes = 0
  const { p, scope } = await operationsPage({ changeTodo: async () => { writes++ } })
  const owned = p.groups.value.help[0]
  p.retests.value = [{ assignment_id: 'same', student_id: 1, original_attempt_id: 'attempt' }, { assignment_id: 'other-task', student_id: 1, original_attempt_id: 'other' }, { assignment_id: 'other-student', student_id: 2, original_attempt_id: 'attempt' }]
  assert.equal(p.retestsFor(owned).length, 1)
  p.drafts.todo = { summary: '观察', retest: 'other-task' }
  await p.run(() => p.change(owned, 'verify')); assert.equal(writes, 0)
  p.groups.value = { help: [todo({ owner_id: 9 })] }; assert.equal(p.canEdit(p.groups.value.help[0]), false)
  await p.run(() => p.change(p.groups.value.help[0], 'handle')); assert.equal(writes, 0)
  await p.run(() => p.change(todo({ revision: 0 }), 'claim')); assert.equal(writes, 0); assert.match(p.message.value, /待办已变化/)
  scope.stop()
})
test('real verification that remains pending is not labeled improved, and transfer uses imported original references', async () => {
  const writes = [], updated = todo({ revision: 2, status: 'pending_verification', proof: { verified: false } })
  const { p, service, scope } = await operationsPage({ changeTodo: async (id, data) => { writes.push(data); return updated } })
  service.todos = async () => ({ groups: { help: [updated] } })
  await p.run(() => p.change(p.groups.value.help[0], 'verify'))
  assert.match(p.message.value, /仍待验证，不计为改善/)
  p.drafts.todo = { summary: '交接', assigneeId: '教师甲' }
  await p.run(() => p.resolveTransfer(p.groups.value.help[0])); assert.equal(writes.length, 1)
  p.importAssignee(p.groups.value.help[0], { assignee_id: 12 })
  assert.equal(p.drafts.todo.assigneeId, 12)
  service.changeTodo = async (id, data) => { writes.push(data); return { ...updated, revision: 3, owner_id: 12 } }
  service.todos = async () => ({ groups: { help: [{ ...updated, revision: 3, owner_id: 12 }] } })
  await p.run(() => p.resolveTransfer(p.groups.value.help[0]))
  assert.equal(writes[1].assignee_id, 12); assert.equal(p.canEdit(p.groups.value.help[0]), false)
  scope.stop()
})
test('transfer UI retains actual account references only in imports, not visible ID inputs or invented names', async () => {
  const template = parse(read('../TeacherOperations.vue')).descriptor.template.content
  assert.match(template, /ReferenceImport title="接手负责人"/); assert.match(template, /已导入待核对负责人/)
  assert.doesNotMatch(template, /v-model[^>]*assigneeId|type="number"|账号编号|输入教师姓名/)
  const { p, scope } = await operationsPage()
  const original = p.groups.value.help[0]
  p.importAssignee(original, { assignee_id: 12 }); assert.equal(p.drafts.todo.assigneeId, 12)
  p.groups.value = { help: [todo()] }
  p.importAssignee(original, { assignee_id: 99 }); assert.equal(p.drafts.todo.assigneeId, 12, 'late import cannot affect a replaced todo/account instance')
  scope.stop()
})
test('trend observes a chart appearing after an empty state and disposes replaced containers', async () => {
  const props = reactive({ rows: [], title: '真实趋势', unit: '分钟', max: 100 }), instances = [], observed = [], hooks = []
  let disconnected = 0
  const scope = effectScope()
  const p = scope.run(() => page('../../shared/learning/TrendChart.vue', {
    defineProps: () => props, nextTick, onMounted() {}, onBeforeUnmount: callback => hooks.push(callback),
    window: { addEventListener() {}, removeEventListener() {} },
    ResizeObserver: class { observe(node) { observed.push(node) } disconnect() { disconnected++ } },
    tokenValue: () => '', tokenNumber: () => 12,
    echarts: { init: node => { const instance = { node, disposed: false, options: [], setOption(option) { this.options.push(option) }, dispose() { this.disposed = true }, resize() {} }; instances.push(instance); return instance } },
  }, 'draw, chartRef'))
  await p.draw(); assert.equal(instances.length, 0)
  props.rows = [{ date: '2026-11-03', value: 0 }]; p.chartRef.value = { id: 'first' }; await p.draw()
  assert.equal(instances.length, 1); assert.equal(observed.length, 1)
  assert.equal(instances[0].options.at(-1).series[0].data[0], 0)
  props.rows = []; p.chartRef.value = null; await p.draw(); assert.equal(instances[0].disposed, true)
  props.rows = [{ date: '2026-11-03', value: 5 }]; p.chartRef.value = { id: 'second' }; await p.draw()
  assert.equal(instances.length, 2); assert.equal(observed.length, 2)
  props.unit = '分'; props.max = 50; await settle()
  assert.equal(instances[1].options.at(-1).yAxis.max, 50); assert.equal(instances[1].options.at(-1).yAxis.name, '分')
  hooks[0](); assert.equal(instances[1].disposed, true); assert.ok(disconnected >= 2)
  scope.stop()
})
