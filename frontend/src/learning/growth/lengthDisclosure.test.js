import { createAccountGuard } from '../../shared/state/accountScope.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'
import * as sections from './sections.js'
import * as presentation from './presentation.js'
import { growthDestination } from '../../shared/navigation/phase2.js'
import { createInsightsState } from '../../teacher/insights/state.js'
import * as teacherPresentation from '../../teacher/insights/presentation.js'
import { DIRECTIONS } from '../../teacher/assessment/presentation.js'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const studentFile = './GrowthView.vue'
const teacherFile = '../../teacher/TeacherLearningEffect.vue'
const studentIds = ['growth-overview', 'growth-mastery', 'growth-activity', 'growth-report', 'growth-review', 'growth-recommend', 'growth-results']
const teacherIds = teacherPresentation.GROWTH_SECTIONS.map(section => `teacher-growth-${section.key}`)
const settle = async () => { for (let index = 0; index < 40; index++) await Promise.resolve(); await Vue.nextTick() }
const defer = () => { let resolve; const promise = new Promise(yes => { resolve = yes }); return { promise, resolve } }

// Execute the actual SFC setup and compiled template, without a browser, server or new test dependency.
function component(file, imports, globals = {}) {
  const { descriptor, errors } = parse(read(file))
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'length-disclosure', inlineTemplate: true })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: 'length-disclosure', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  const code = script.content
    .replace(/^import\s+['"][^'"]+['"];?\s*$/gm, '')
    .replace(/import\s+([\s\S]*?)\s+from\s+['"]([^'"]+)['"];?/g, (_, binding, source) => {
      const value = `__imports[${JSON.stringify(source)}]`
      if (binding.trim().startsWith('{')) return `const ${binding.replace(/\b(\w+)\s+as\s+(\w+)/g, '$1: $2')} = ${value};`
      return `const ${binding.trim()} = ${value};`
    })
    .replace('export default', 'const __component =')
  return runInNewContext(`${code}\n;__component`, { __imports: { vue: Vue, ...imports }, ...globals })
}

// This renderer models native details.open/toggle, including coalesced programmatic toggle events.
// Hidden details bodies remain in the host tree, so mount/unmount/ref assertions exercise Vue itself.
function host() {
  const root = { tag: 'root', children: [], props: {} }, scrolls = [], resizes = []
  const node = (tag, text = '') => ({ tag, text, children: [], props: {}, parent: null, open: false })
  const walk = (element, result = []) => {
    result.push(element)
    for (const child of element.children) walk(child, result)
    return result
  }
  const find = predicate => walk(root).find(predicate)
  const setOpen = (element, value) => {
    if (element.open === Boolean(value)) return
    element.open = Boolean(value)
    if (element.toggleQueued) return
    element.toggleQueued = true
    Promise.resolve().then(() => {
      element.toggleQueued = false
      element.props.onToggle?.({ currentTarget: element })
    })
  }
  const renderer = Vue.createRenderer({
    createElement: tag => node(tag), createText: text => node('#text', text), createComment: text => node('#comment', text),
    setText: (element, text) => { element.text = text },
    setElementText: (element, text) => { element.text = text; element.children = [] },
    parentNode: element => element.parent,
    nextSibling: element => element.parent?.children[element.parent.children.indexOf(element) + 1] || null,
    insert(element, parent, anchor = null) {
      if (element.parent) element.parent.children.splice(element.parent.children.indexOf(element), 1)
      const index = anchor ? parent.children.indexOf(anchor) : -1
      if (index < 0) parent.children.push(element); else parent.children.splice(index, 0, element)
      element.parent = parent
    },
    remove(element) {
      if (element.parent) element.parent.children.splice(element.parent.children.indexOf(element), 1)
      element.parent = null
    },
    patchProp(element, key, previous, value) {
      element.props[key] = value
      if (key === 'open') setOpen(element, value)
    },
  })
  const section = id => find(element => element.props.id === id)
  const disclosure = id => section(id)?.children.find(element => element.tag === 'details')
  const document = { getElementById: id => {
    const element = section(id)
    if (element) element.scrollIntoView = () => scrolls.push({ id, open: disclosure(id).open })
    return element
  } }
  const window = { location: { hash: '' }, Event: class { constructor(type) { this.type = type } }, dispatchEvent: event => resizes.push(event.type) }
  const click = id => {
    const link = find(element => element.tag === 'a' && element.props.href === `#${id}`)
    assert.ok(link, `navigation link ${id}`)
    link.props.onClick({ preventDefault() {}, stopPropagation() {} })
  }
  return { root, renderer, section, disclosure, find, setOpen, document, window, scrolls, resizes, click }
}

function child(name, records, props = [], mounted) {
  return Vue.defineComponent({
    name, props, emits: ['loaded', 'window-change', 'card-saved'],
    setup(values, { emit, expose }) {
      const draft = Vue.ref(''), record = { name, props: values, draft, emit, mounted: 0, unmounted: 0, reads: 0 }
      record.load = () => { record.reads++ }
      expose({ load: record.load, draft })
      records.push(record)
      Vue.onMounted(() => { record.mounted++; record.load(); mounted?.(emit) })
      Vue.onBeforeUnmount(() => { record.unmounted++ })
      return () => Vue.h('div', { 'data-component': name }, [Vue.h('input', { value: draft.value, onInput: event => { draft.value = event.target.value } })])
    },
  })
}

async function studentPage({ query = {}, hash = '', user: suppliedUser, globals = true } = {}) {
  const h = host(), records = [], calls = [], replacements = []
  const user = suppliedUser || Vue.reactive({ userInfo: { id: 1, role: 'student' }, userName: '同学' })
  const route = Vue.reactive({ query, hash })
  const router = { replace(value) {
    replacements.push(value)
    const url = typeof value === 'string' ? new URL(value, 'https://local.test') : null
    route.query = url ? Object.fromEntries(url.searchParams) : value.query || {}
    route.hash = url ? url.hash : value.hash || ''
  } }
  const request = (name, data) => async () => { calls.push(name); return data }
  const imports = {
    '@/shared/state/accountScope.js': { createAccountGuard },
    'vue-router': { useRoute: () => route, useRouter: () => router },
    '@/store/user': { useUserStore: () => user },
    '@/api': { studentProfile: { get: request('profile', {}), persona: request('persona', {}), growth: request('growth', {}), learningDirections: request('directions', []) }, analytics: { teachingPlan: request('plan', {}), progressReport: request('progress', {}) }, submission: { stats: request('stats', {}) } },
    '@/shared/navigation/phase2.js': { growthDestination },
    '@/learning/exams/api.js': { RECORDS_PATH: '/exam-center/history', examsApi: { myHistory: request('exams', { records: [] }) }, recordView: value => value },
    './presentation.js': presentation, './sections.js': sections,
  }
  const childProps = {
    GrowthSummary: ['displayName', 'profile', 'persona', 'progressReport', 'submissionStats', 'recommendations', 'examCount'],
    MasteryOverview: ['directions', 'growth', 'teachingPlan'], LearningActivity: ['initialDays'],
    LearningReport: ['teachingPlan', 'teachingLoading', 'teachingError'], ReviewReminders: [],
    LearningRecommendations: [], RetestList: [], SubmissionReview: [],
  }
  for (const [name, props] of Object.entries(childProps)) {
    imports[`./components/${name}.vue`] = child(name, records, props, name === 'LearningRecommendations' ? emit => emit('loaded', [{ title: '已有建议' }]) : undefined)
  }
  const C = component(studentFile, imports, globals ? { window: h.window, document: h.document } : {})
  const app = h.renderer.createApp(C)
  app.component('router-link', Vue.defineComponent({ setup(_, { slots }) { return () => Vue.h('a', slots.default?.()) } }))
  const instance = app.mount(h.root)
  await settle()
  return { ...h, app, instance, records, calls, replacements, user, route, C }
}

const effectPayload = (id, days) => ({ student: { id }, period: { days }, snapshot: null, daily_stats: [{ date: '2026-11-03', effective_learning_seconds: 60 }] })
async function teacherPage({ hash = '', overrides = {} } = {}) {
  const h = host(), records = [], calls = [], route = Vue.reactive({ params: {}, query: {}, hash })
  const user = Vue.reactive({ userInfo: { id: 8, role: 'teacher' } })
  const service = {
    students: async () => { calls.push(['students']); return [{ id: 1, username: '甲', goals: '甲的目标' }, { id: 2, username: '乙', goals: '乙的目标' }] },
    effect: async (id, days) => { calls.push(['effect', id, days]); return effectPayload(id, days) },
    plan: async id => { calls.push(['plan', id]); return { student: id } }, ...overrides,
  }
  let model
  const C = component(teacherFile, {
    'vue-router': { useRoute: () => route, useRouter: () => ({ replace: value => { route.hash = value.hash } }) },
    '@/store/user': { useUserStore: () => user }, './insights/api.js': service,
    './insights/state.js': { createInsightsState: options => { model = createInsightsState(options); return model } },
    './insights/presentation.js': teacherPresentation, './assessment/presentation.js': { DIRECTIONS },
    '@/shared/learning/presentation.js': presentation,
    '@/shared/learning/ActivityFacts.vue': child('ActivityFacts', records, ['effect']),
    '@/shared/learning/TeachingPlan.vue': child('TeachingPlan', records, ['plan', 'loading', 'error']),
    '@/shared/learning/TrendChart.vue': child('TrendChart', records, ['rows', 'title', 'unit', 'showTable']),
  }, { document: h.document })
  const app = h.renderer.createApp(C)
  app.mount(h.root)
  await settle()
  return { ...h, app, records, calls, model, service, route, user }
}

for (const [file, ids] of [[studentFile, studentIds], [teacherFile, teacherIds]]) {
  test(`${file}: all seven original section shells contain native accessible non-exclusive disclosures`, () => {
    const source = read(file), template = parse(source).descriptor.template.content
    assert.match(source, /import '@\/shared\/layout\/disclosure\.css'/)
    assert.equal((template.match(/<details\b/g) || []).length, 7)
    assert.equal((template.match(/<summary class="length-disclosure__summary">[^<]+<\/summary>/g) || []).length, 7)
    assert.equal((template.match(/<div class="length-disclosure__body">/g) || []).length, 7)
    for (const id of ids) assert.match(template, new RegExp(`<section id="${id}"[^>]*>\\s*<details class="length-disclosure"`))
    assert.doesNotMatch(template, /<details[^>]*\bname=|(?:v-if|v-show|:key)="[^"]*expandedSections/)
    assert.doesNotMatch(template, /<summary[^>]*(?:tabindex|role)=/)
  })
}

test('student default opens only growth overview; all original props and children are already mounted', async t => {
  const p = await studentPage(); t.after(() => p.app.unmount())
  assert.deepEqual(studentIds.filter(id => p.disclosure(id).open), ['growth-overview'])
  assert.equal(p.records.length, 8)
  assert.ok(p.records.every(record => record.mounted === 1 && record.unmounted === 0 && record.reads === 1))
  assert.deepEqual(p.calls.sort(), ['directions', 'exams', 'growth', 'persona', 'plan', 'profile', 'progress', 'stats'])
  const summary = p.records.find(record => record.name === 'GrowthSummary')
  assert.deepEqual(Object.keys(summary.props).sort(), ['displayName', 'examCount', 'persona', 'profile', 'progressReport', 'recommendations', 'submissionStats'])
  assert.equal(summary.props.recommendations[0].title, '已有建议')
  assert.equal(p.records.find(record => record.name === 'LearningActivity').props.initialDays, 7)
  assert.match(read(studentFile), /<RetestList ref="retestList"/)
  assert.match(read(studentFile), /<SubmissionReview ref="submissionReview" @card-saved="onCardSaved"/)
})

test('student folding preserves bodies, drafts, refs and request counts, allowing several sections open', async t => {
  const p = await studentPage(); t.after(() => p.app.unmount())
  const originalBodies = studentIds.map(id => p.disclosure(id).children[1]), originalReads = [...p.calls]
  const review = p.records.find(record => record.name === 'SubmissionReview')
  const input = p.find(element => element.tag === 'input' && element.parent.props['data-component'] === 'SubmissionReview')
  input.props.onInput({ target: { value: '未提交的复盘草稿' } })
  for (const id of studentIds) {
    p.setOpen(p.disclosure(id), true); await settle()
    p.setOpen(p.disclosure(id), false); await settle()
  }
  p.setOpen(p.disclosure('growth-report'), true); p.setOpen(p.disclosure('growth-results'), true); await settle()
  assert.equal(p.disclosure('growth-report').open, true); assert.equal(p.disclosure('growth-results').open, true)
  assert.deepEqual(studentIds.map(id => p.disclosure(id).children[1]), originalBodies)
  assert.equal(p.find(element => element === input), input)
  assert.equal(review.draft.value, '未提交的复盘草稿')
  assert.equal(input.props.value, '未提交的复盘草稿')
  assert.deepEqual(p.calls, originalReads)
  assert.ok(p.records.every(record => record.mounted === 1 && record.unmounted === 0 && record.reads === 1))
  assert.ok(p.resizes.length >= 7); assert.ok(p.resizes.every(type => type === 'resize'))
})

test('only opening a student disclosure emits the guarded post-layout chart resize', async t => {
  const p = await studentPage(); t.after(() => p.app.unmount())
  const before = p.resizes.length
  p.setOpen(p.disclosure('growth-activity'), true); await settle()
  assert.equal(p.resizes.length, before + 1)
  p.setOpen(p.disclosure('growth-activity'), false); await settle()
  assert.equal(p.resizes.length, before + 1)
  p.setOpen(p.disclosure('growth-activity'), true); await settle()
  assert.equal(p.resizes.length, before + 2)
})

test('a completed review still refreshes the original retest ref while results are closed', async t => {
  const p = await studentPage(); t.after(() => p.app.unmount())
  const review = p.records.find(record => record.name === 'SubmissionReview'), retests = p.records.find(record => record.name === 'RetestList')
  assert.equal(p.disclosure('growth-results').open, false)
  review.emit('card-saved', { completed: false }); review.emit('card-saved', { completed: true, failed: true })
  assert.equal(retests.reads, 1)
  review.emit('card-saved', { completed: true, failed: false })
  assert.equal(retests.reads, 2)
  assert.equal(retests.mounted, 1); assert.equal(retests.unmounted, 0)
  assert.equal(p.disclosure('growth-results').open, false)
})

test('student navigation opens each destination before scrolling without rerunning reads', async t => {
  const p = await studentPage(); t.after(() => p.app.unmount())
  const reads = [...p.calls]
  for (const id of studentIds) {
    p.setOpen(p.disclosure(id), false); await settle()
    p.click(id); await settle()
    assert.equal(p.disclosure(id).open, true)
    assert.equal(p.scrolls.at(-1).id, id); assert.equal(p.scrolls.at(-1).open, true)
    assert.equal(p.instance.activeSection, id)
  }
  assert.deepEqual(p.calls, reads)
})

test('student query aliases, all seven hashes and hash precedence restore open destinations', async t => {
  for (const [section, id] of [['overview', 'growth-overview'], ['analysis', 'growth-activity'], ['analytics', 'growth-activity'], ['review', 'growth-results'], ['results', 'growth-results'], ['mastery', 'growth-mastery'], ['capability', 'growth-mastery']]) {
    const p = await studentPage({ query: { section } }); t.after(() => p.app.unmount())
    assert.equal(p.disclosure(id).open, true); assert.equal(p.instance.activeSection, id)
    assert.ok(p.scrolls.every(scroll => scroll.open))
  }
  const p = await studentPage({ query: { section: 'activity' }, hash: '#growth-report' }); t.after(() => p.app.unmount())
  assert.equal(p.disclosure('growth-report').open, true)
  assert.equal(p.disclosure('growth-activity').open, false)
  for (const id of studentIds) {
    p.setOpen(p.disclosure(id), false); await settle()
    p.route.hash = `#${id}`; await settle()
    assert.equal(p.disclosure(id).open, true)
  }
  assert.ok(p.scrolls.every(scroll => scroll.open))
})

test('student 7/30/90 URL windows and window-change contracts survive a hidden activity section', async t => {
  for (const days of [7, 30, 90]) {
    const p = await studentPage({ query: { section: 'activity', window: String(days) } }); t.after(() => p.app.unmount())
    const activity = p.records.find(record => record.name === 'LearningActivity')
    assert.equal(activity.props.initialDays, days)
    p.setOpen(p.disclosure('growth-activity'), false); await settle()
    p.click('growth-activity'); await settle()
    assert.equal(p.route.query.window, String(days))
    activity.emit('window-change', days); await settle()
    assert.equal(p.route.query.section, 'activity'); assert.equal(p.route.query.window, String(days))
    assert.equal(activity.mounted, 1); assert.equal(activity.reads, 1)
  }
  const p = await studentPage({ query: { window: '14' } }); t.after(() => p.app.unmount())
  assert.equal(p.records.find(record => record.name === 'LearningActivity').props.initialDays, 7)
})

test('student display state resets on account change and the existing keyed app boundary isolates data', async t => {
  const p = await studentPage(); t.after(() => p.app.unmount())
  p.click('growth-results'); await settle()
  p.user.userInfo = { id: 2, role: 'student' }; await settle()
  assert.deepEqual(studentIds.filter(id => p.disclosure(id).open), ['growth-overview'])
  assert.equal(p.instance.activeSection, 'growth-overview')
  assert.match(read('../../App.vue'), /:key="`\$\{user\.userInfo\?\.id \|\| 'guest'\}:\$\{role\}`"/)
  // Changing accounts is not a folding action: App unmounts the old keyed route and its drafts.
  p.app.unmount()
  assert.ok(p.records.every(record => record.unmounted === 1))
  const next = await studentPage({ user: p.user }); t.after(() => next.app.unmount())
  assert.ok(next.records.every(record => record.draft.value === ''))
  assert.deepEqual(studentIds.filter(id => next.disclosure(id).open), ['growth-overview'])
})

test('student open and navigation are safe without a browser window or document', async t => {
  const p = await studentPage({ globals: false }); t.after(() => p.app.unmount())
  p.setOpen(p.disclosure('growth-activity'), true); await settle()
  p.instance.goSection('growth-results'); await settle()
  assert.equal(p.disclosure('growth-results').open, true)
  assert.deepEqual(p.resizes, [])
})

test('teacher default opens only overview, preserving all sections, components, props and writes', async t => {
  const p = await teacherPage(); t.after(() => p.app.unmount())
  assert.deepEqual(teacherIds.filter(id => p.disclosure(id).open), ['teacher-growth-overview'])
  assert.deepEqual(p.calls, [['students'], ['effect', 1, 7], ['plan', 1]])
  assert.deepEqual(p.records.map(record => record.name).sort(), ['ActivityFacts', 'TeachingPlan', 'TrendChart'])
  const trend = p.records.find(record => record.name === 'TrendChart'), plan = p.records.find(record => record.name === 'TeachingPlan')
  assert.equal(trend.props.title, '每日学习分钟'); assert.equal(trend.props.unit, '分钟'); assert.equal(trend.props.showTable, false)
  assert.equal(plan.props.plan.student, 1); assert.equal(plan.props.loading, false); assert.equal(plan.props.error, '')
  const source = read(teacherFile)
  for (const marker of ['model.selectStudent($event.target.value)', 'model.loadEffect(Number($event.target.value))', '@click="model.loadPlan"', 'reportMastery(student)', 'student.solved_count', 'student.score', 'student.skills?.[direction.key]', 'concept.mastery', 'metricText(metric.value)', 'effective_learning_seconds', 'item.action_text', 'item.reason', 'item.content']) assert.ok(source.includes(marker), marker)
})

test('teacher folding and every navigation link retain component identity and request counts', async t => {
  const p = await teacherPage(); t.after(() => p.app.unmount())
  const calls = [...p.calls], bodies = teacherIds.map(id => p.disclosure(id).children[1])
  for (const id of teacherIds) {
    p.setOpen(p.disclosure(id), false); await settle()
    p.click(id); await settle()
    assert.equal(p.disclosure(id).open, true)
    assert.equal(p.route.hash, `#${id}`)
    assert.deepEqual(p.scrolls.at(-1), { id, open: true })
  }
  assert.equal(teacherIds.filter(id => p.disclosure(id).open).length, 7)
  assert.deepEqual(teacherIds.map(id => p.disclosure(id).children[1]), bodies)
  assert.deepEqual(p.calls, calls)
  assert.ok(p.records.every(record => record.mounted === 1 && record.unmounted === 0 && record.reads === 1))
})

test('teacher 7/30/90 controls retain authorized reads while activity remains collapsed', async t => {
  const p = await teacherPage(); t.after(() => p.app.unmount())
  const windows = p.find(element => element.tag === 'select' && element.children.some(option => option.props.value === 90))
  assert.ok(windows)
  assert.deepEqual(windows.children.filter(option => option.tag === 'option').map(option => option.props.value), [7, 30, 90])
  for (const days of [30, 90, 7]) {
    windows.props.onChange({ target: { value: String(days) } }); await settle()
    assert.equal(p.model.state.days, days)
    assert.deepEqual(p.calls.at(-1), ['effect', 1, days])
    assert.equal(p.disclosure('teacher-growth-activity').open, false)
  }
  const before = p.calls.length
  await p.model.loadEffect(14)
  assert.equal(p.calls.length, before)
})

test('teacher initial and changed hashes expand the destination before scrolling', async t => {
  const p = await teacherPage({ hash: '#teacher-growth-report' }); t.after(() => p.app.unmount())
  assert.equal(p.disclosure('teacher-growth-report').open, true)
  assert.equal(p.disclosure('teacher-growth-activity').open, false)
  p.route.hash = '#teacher-growth-mastery'; await settle()
  assert.equal(p.disclosure('teacher-growth-mastery').open, true)
  assert.ok(p.scrolls.length); assert.ok(p.scrolls.every(scroll => scroll.open))
})

test('teacher student and account switches reset disclosure state, clear old data and reject late records', async t => {
  const p = await teacherPage(); t.after(() => p.app.unmount())
  p.click('teacher-growth-activity'); p.click('teacher-growth-report'); await settle()
  const pending = defer()
  p.service.effect = (id, days) => pending.promise
  const reading = p.model.selectStudent(2)
  assert.equal(p.model.state.effect, null); assert.equal(p.model.state.rawEffect, null)
  await settle()
  assert.deepEqual(teacherIds.filter(id => p.disclosure(id).open), ['teacher-growth-overview'])
  assert.equal(p.model.state.studentId, 2)
  p.user.userInfo = null
  assert.equal(p.model.state.studentId, ''); assert.equal(p.model.state.plan, null)
  pending.resolve(effectPayload(2, 7)); await reading; await settle()
  assert.equal(p.model.state.effect, null); assert.equal(p.model.state.plan, null)
  assert.ok(teacherIds.every(id => !p.section(id)))
  p.service.effect = async (id, days) => effectPayload(id, days)
  p.user.userInfo = { id: 9, role: 'teacher' }; await settle()
  assert.deepEqual(teacherIds.filter(id => p.disclosure(id).open), ['teacher-growth-overview'])
  assert.equal(p.model.state.studentId, 1)
})


test('cached Growth ignores unrelated route windows and hashes, then restores its own window or explicit deep link', async t => {
  const p = await studentPage({ query: { section: 'activity', window: '30' } }); t.after(() => p.app.unmount())
  const activity = p.records.find(record => record.name === 'LearningActivity')
  assert.equal(activity.props.initialDays, 30)
  const scrolls = p.scrolls.length
  p.route.path = '/guide'; p.route.query = { window: '7', section: 'results' }; p.route.hash = '#growth-results'; await settle()
  assert.equal(activity.props.initialDays, 30); assert.equal(p.scrolls.length, scrolls)
  p.route.path = '/dashboard'; p.route.query = {}; p.route.hash = ''; await settle(); assert.equal(activity.props.initialDays, 30)
  p.route.query = { section: 'activity', window: '90' }; p.route.hash = '#growth-activity'; await settle()
  assert.equal(activity.props.initialDays, 90); assert.equal(p.disclosure('growth-activity').open, true)
})
