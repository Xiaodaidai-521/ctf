import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compile, computed, createSSRApp, h, nextTick, reactive, ref, watch } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { compileScript, compileStyle, compileTemplate, parse } from 'vue/compiler-sfc'
import { queueStatusPreset } from './queueState.js'
import * as helpers from '../feedbackPresentation.js'
import * as candidateImports from './candidateImport.js'
import * as candidateLabels from '../candidatePresentation.js'
import { recordRows } from '../../shared/forms/recordPresentation.js'

const read = file => readFileSync(new URL(file, import.meta.url), 'utf8')
const plain = value => JSON.parse(JSON.stringify(value))
const tick = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
function queuePage(methods = {}, extra = {}) {
  const route = reactive({ query: {}, ...extra.route })
  let unmount
  const service = { feedback: { teacherQueue: async () => ({ items: [], counts: {}, total: 0 }), options: async () => ({}), samplingBatches: async () => ({ items: [] }), ...methods } }
  const script = parse(read('../FeedbackQueue.vue')).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  const p = runInNewContext(`${script}\n;({ embedded, queue, loading, queueLoaded, queueError, queueNext, error, optionsError, batches, batchesError, batchesLoading, batchesLoaded, statuses, categories, filters, batchForm, riskTickets, riskLoading, riskLoaded, riskError, selectedBatch, batchLoading, batchNames, batchNamesError, creatingBatch, loadQueue, loadOptions, loadBatches, createBatch, loadRiskTickets, statusTone })`, {
    ...helpers, formatDate: helpers.feedbackDate, queueStatusPreset, reactive, ref, computed, watch,
    defineProps: () => ({ embedded: !!extra.embedded }), defineEmits: () => () => {}, useRoute: () => route,
    onMounted() {}, onBeforeUnmount: fn => { unmount = fn }, service,
  })
  return { p: { ...p, ...helpers, formatDate: helpers.feedbackDate }, route, unmount: () => unmount() }
}
async function visibleQueue(p) {
  const app = createSSRApp({ render: compile(parse(read('../FeedbackQueue.vue')).descriptor.template.content), setup: () => p })
  app.component('router-link', { props: ['to'], setup: (props, { slots }) => () => h('a', { href: props.to }, slots.default?.()) })
  return await renderToString(app)
}

for (const file of ['../FeedbackWorkbench.vue', '../FeedbackQueue.vue', '../FeedbackCandidates.vue', '../FeedbackDetail.vue', '../FeedbackReconciliation.vue']) {
  test(`${file}: workbench pages compile and resolve existing domain API`, () => {
    const { descriptor, errors } = parse(read(file))
    assert.deepEqual(errors, [])
    assert.ok(compileScript(descriptor, { id: file }).content)
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: file }).errors, [])
    assert.doesNotMatch(read(file), /import service from '@\/api'|axios\.|fetch\(/)
    for (const style of descriptor.styles.filter(style => !style.src)) {
      assert.equal(style.scoped, true)
      assert.deepEqual(compileStyle({ source: style.content, filename: file, id: 'data-v-feedback', scoped: true }).errors, [])
      assert.doesNotMatch(style.content, /#[\da-f]{3,8}\b|rgba?\(/i)
    }
  })
}

test('workbench keeps two live task sections, not tabs or an embedded audit', async () => {
  const { descriptor } = parse(read('../FeedbackWorkbench.vue'))
  const app = createSSRApp({ render: compile(descriptor.template.content), setup: () => ({}) })
  for (const name of ['FeedbackQueue', 'FeedbackCandidates']) app.component(name, { props: { embedded: Boolean }, setup: props => () => h('div', { 'data-task': name, 'data-embedded': String(props.embedded) }) })
  app.component('router-link', { props: ['to'], setup: (props, { slots }) => () => h('a', { href: props.to }, slots.default?.()) })
  const html = await renderToString(app)
  assert.match(html, /id="queue"/)
  assert.match(html, /id="candidates"/)
  assert.match(html, /data-task="FeedbackQueue" data-embedded="true"/)
  assert.match(html, /data-task="FeedbackCandidates" data-embedded="true"/)
  assert.match(html, /href="\/teacher\/feedback\/reconciliation"/)
  assert.doesNotMatch(read('../FeedbackWorkbench.vue'), /import FeedbackReconciliation|tablist|tabpanel|<a-tabs/)
})

test('queue loading and read failure do not claim zero or no feedback; retry shows real empty', async () => {
  let fail = true
  const { p } = queuePage({ teacherQueue: async () => { if (fail) throw new Error('private server error'); return { items: [], total: 0 } } })
  let html = await visibleQueue(p)
  assert.match(html, /正在读取反馈待办/)
  assert.doesNotMatch(html, /当前筛选下没有反馈|共 0 条/)
  await p.loadQueue()
  html = await visibleQueue(p)
  assert.match(html, /加载教师待办失败/)
  assert.doesNotMatch(html, /当前筛选下没有反馈|共 0 条|private server error/)
  fail = false
  await p.loadQueue()
  html = await visibleQueue(p)
  assert.match(html, /当前筛选下没有反馈/)
  assert.match(html, /共 0 条/)
})

test('query status preset is passed on initial read and same-route query changes; invalid query is rejected', async () => {
  const calls = []
  const { p, route } = queuePage({ teacherQueue: async params => { calls.push(plain(params)); return { items: [], total: 0 } } }, { route: { query: { status: 'pending_evidence' } } })
  await p.loadQueue()
  assert.equal(calls[0].status, 'pending_evidence')
  route.query.status = 'reopened'; await tick()
  assert.equal(calls.at(-1).status, 'reopened')
  route.query.status = 'private'; await tick()
  assert.equal(p.filters.status, '')
  assert.equal(calls.at(-1).status, undefined)
  for (const value of [[], ['handled'], {}, 'constructor', 'draft', null]) assert.equal(queueStatusPreset(value), '')
})

test('late queue failures cannot replace current data or clear newer loading state', async () => {
  const pending = [deferred(), deferred(), deferred()]
  let index = 0
  const { p, unmount } = queuePage({ teacherQueue: () => pending[index++].promise })
  const first = p.loadQueue(), second = p.loadQueue()
  pending[0].reject(new Error('old')); await first
  assert.equal(p.loading.value, true)
  assert.equal(p.queueError.value, '')
  pending[1].resolve({ items: [{ feedback_id: 'new' }], total: 1 }); await second
  assert.equal(p.queue.items[0].feedback_id, 'new')
  const third = p.loadQueue(); unmount()
  pending[2].resolve({ items: [{ feedback_id: 'after-unmount' }], total: 1 }); await third
  assert.equal(p.queue.items[0].feedback_id, 'new')
})

test('options and batch failures are independent of successful queue, missing total is unknown not zero', async () => {
  const { p } = queuePage({
    teacherQueue: async () => ({ items: [] }), options: async () => { throw new Error('private options') },
    samplingBatches: async () => { throw new Error('private batches') },
  })
  await Promise.all([p.loadQueue(), p.loadOptions(), p.loadBatches()])
  assert.equal(p.queueError.value, '')
  assert.equal(p.queue.total, null)
  assert.match(p.optionsError.value, /选项失败/)
  assert.match(p.batchesError.value, /批次失败/)
  const html = await visibleQueue(p)
  assert.match(html, /共 未提供 条/)
  assert.doesNotMatch(html, /暂无抽查批次|private options|private batches/)
})

test('embedded queue hides duplicated main heading and refresh is a real action, with returned pagination', async () => {
  const { p } = queuePage({ teacherQueue: async params => ({ items: [{ feedback_id: 'f1' }], total: 51, page: params.page, page_size: 50 }) }, { embedded: true })
  await p.loadQueue()
  assert.equal(p.queueNext.value, 2)
  const html = await visibleQueue(p)
  assert.doesNotMatch(html, /<h1|反馈待办与随机抽查/)
  assert.match(html, /下一页/)
  assert.doesNotMatch(read('../FeedbackQueue.vue'), /<router-link[^>]*>刷新<\/router-link>/)
})

test('feedback facade forwards every retained action and original field without new endpoints', () => {
  const source = read('./api.js').replace(/^import .*$/gm, '').replace(/^export default .*$/gm, '').replace(/^export /gm, '')
  const calls = []
  const client = new Proxy({}, { get: (_, domain) => new Proxy({}, { get: (_, action) => (...args) => { calls.push({ domain, action, args }); return 'original response' } }) })
  const { createTeacherFeedbackApi } = runInNewContext(`${source}\n;({ createTeacherFeedbackApi })`, { client })
  const api = createTeacherFeedbackApi(client)
  for (const [domain, methods] of Object.entries(api)) for (const [name, method] of Object.entries(methods)) {
    const payload = { expected_version: 9, action: 'confirm', owner_id: 72, evidence_refs: ['original'], extra: { retained: true } }
    assert.equal(method('original-id', payload), 'original response')
    assert.equal(calls.at(-1).domain, domain)
    assert.equal(calls.at(-1).action, name)
    assert.equal(calls.at(-1).args[1], payload)
  }
  assert.ok(calls.length >= 30)
  assert.doesNotMatch(read('./api.js'), /\/feedback\/|\/skill-review\/|http\.|fetch\(/)
})

const configuration = {
  title: '原始候选', issue_group_ids: ['original-group'],
  baseline_config_version: 'base-original', candidate_config_version: 'candidate-original',
  single_changed_factor: 'original-factor', rollback_version: 'rollback-original',
  baseline_config: { 'original-factor': { limit: 3, enabled: false }, nested: ['retained', 0, false] },
  candidate_config: { 'original-factor': { limit: 8, enabled: false }, nested: ['retained', 0, false] },
  target_task_versions: ['original-task@3'], excluded_scope: ['原排除范围'], expected_risk: '原风险说明',
}
const report = {
  run_id: 'original-run', report_id: 'original-report', report_version: 'original-v3',
  report_digest: 'report-original-digest', candidate_config_digest: 'candidate-original-digest',
  dataset_version: 'dataset-original', baseline_config_digest: 'baseline-original-digest',
  recommendation: 'fail', completed: false, missing_cases: 3,
}
const fileEvent = value => ({ target: { files: [{ size: 1000, text: async () => typeof value === 'string' ? value : JSON.stringify(value) }], value: 'source.json' } })
function candidatesPage(methods = {}) {
  let unmount, mounted
  const emitted = []
  const script = parse(read('../FeedbackCandidates.vue')).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  const p = runInNewContext(`${script}\n;({ candidateForm, reportImports, configurationImported, message, gates, loading, loaded, loadError, groups, candidates, creatingCandidate, attachingReports, loadAll, createCandidate, importConfiguration, importReport, attachReport })`, {
    ...helpers, ...candidateImports, ...candidateLabels, ref, reactive,
    defineProps: () => ({ embedded: true }), defineEmits: () => (...args) => emitted.push(args),
    onMounted: fn => { mounted = fn }, onBeforeUnmount: fn => { unmount = fn },
    service: { feedbackPhase3: { issueGroups: async () => ({ items: [], phase3_write_enabled: false, release_enabled: false }), candidates: async () => ({ items: [] }), ...methods }, learningMap: { catalog: async () => ({ capabilities: [] }) } },
  })
  return { p, emitted, mount: () => mounted(), unmount: () => unmount() }
}

test('candidate imports validate actual source shapes without defaults, coercion or unsafe nested keys', () => {
  assert.deepEqual(candidateImports.parseCandidateConfiguration(JSON.stringify(configuration)), configuration)
  assert.deepEqual(candidateImports.parseCandidateReport(JSON.stringify(report)), report)
  for (const text of ['{', '[]', 'null', '{"constructor":{}}', JSON.stringify({ ...configuration, baseline_config: { nested: { constructor: 'unsafe' } } }), JSON.stringify({ ...configuration, target_task_versions: 'task' }), JSON.stringify({ ...configuration, baseline_config: null }), JSON.stringify({ ...configuration, candidate_config_version: '' }), JSON.stringify({ ...configuration, unknown_field: true })]) {
    assert.throws(() => candidateImports.parseCandidateConfiguration(text))
  }
  for (const key of ['run_id', 'report_id', 'report_version', 'report_digest', 'candidate_config_digest', 'completed', 'missing_cases', 'recommendation']) {
    const incomplete = { ...report }; delete incomplete[key]
    assert.throws(() => candidateImports.parseCandidateReport(JSON.stringify(incomplete)), key)
  }
  for (const values of [{ completed: 'true' }, { missing_cases: '0' }, { missing_cases: -1 }, { missing_cases: 0.5 }, { recommendation: 'constructor' }, { recommendation: 'revise' }, { unknown: 'report' }]) {
    assert.throws(() => candidateImports.parseCandidateReport(JSON.stringify({ ...report, ...values })))
  }
  assert.throws(() => candidateImports.parseCandidateReport(' '.repeat(1024 * 1024 + 1)), /文件过大/)
})

test('candidate registration requires source configuration and retains every imported request field and gates', async () => {
  const calls = []
  const { p } = candidatesPage({ createCandidate: async payload => { calls.push(plain(payload)); return {} } })
  p.candidateForm.title = '原始候选'; p.candidateForm.issue_group_ids = ['original-group']
  await p.createCandidate()
  assert.equal(calls.length, 0)
  assert.match(p.message.value, /导入/)
  await p.importConfiguration(fileEvent(configuration))
  await p.createCandidate()
  assert.deepEqual(calls, [configuration])
  assert.equal(p.gates.phase3_write_enabled, false)
  assert.equal(p.gates.release_enabled, false)
  const noOptional = { ...configuration }; delete noOptional.excluded_scope; delete noOptional.expected_risk
  await p.importConfiguration(fileEvent(noOptional))
  await p.createCandidate()
  assert.deepEqual(calls.at(-1), noOptional)
  assert.doesNotMatch(read('../FeedbackCandidates.vue'), /Date\.now\(|export_record_limit:\s*(100|120)|report_digest:\s*candidate\.config_digest/)
})

test('report attachment passes real failing, incomplete or insufficient source facts unchanged for server validation', async () => {
  const calls = []
  const { p } = candidatesPage({ attachCandidateReport: async (...args) => { calls.push(plain(args)); throw { response: { data: { code: 'phase3_write_disabled' } } } } })
  const candidate = { candidate_id: 'original-candidate', config_digest: 'do-not-substitute' }
  await p.attachReport(candidate)
  assert.equal(calls.length, 0)
  await p.importReport(candidate, fileEvent(report))
  await p.attachReport(candidate)
  assert.deepEqual(calls, [['original-candidate', report]])
  assert.match(p.message.value, /暂未开放/)
  assert.equal(p.gates.phase3_write_enabled, false)
  const insufficient = { ...report, recommendation: 'insufficient_evidence', completed: true, missing_cases: 0 }
  await p.importReport(candidate, fileEvent(insufficient))
  await p.attachReport(candidate)
  assert.deepEqual(calls.at(-1), ['original-candidate', insufficient])
  await p.importReport({ candidate_id: 'other-candidate' }, fileEvent({ ...report, report_id: 'other-report' }))
  assert.equal(p.reportImports['original-candidate'].report_id, 'original-report')
  assert.equal(p.reportImports['other-candidate'].report_id, 'other-report')
})

test('replacement imports cannot silently submit stale configuration or stale report after a bad file', async () => {
  const calls = []
  const { p } = candidatesPage({ createCandidate: async payload => calls.push(payload), attachCandidateReport: async () => calls.push('report') })
  const candidate = { candidate_id: 'original-candidate' }
  await p.importConfiguration(fileEvent(configuration))
  await p.importConfiguration(fileEvent('{'))
  await p.createCandidate()
  assert.equal(p.configurationImported.value, false)
  assert.equal(calls.length, 0)
  await p.importReport(candidate, fileEvent(report))
  await p.importReport(candidate, fileEvent({ ...report, completed: 'true' }))
  await p.attachReport(candidate)
  assert.equal(p.reportImports[candidate.candidate_id], undefined)
  assert.equal(calls.length, 0)
  await p.importReport(candidate, { target: { files: [{ size: 10, text: async () => { throw new Error('private-file-error') } }], value: '' } })
  assert.match(p.message.value, /文件未能读取/)
  assert.doesNotMatch(p.message.value, /private-file-error/)
})

test('candidate imports ignore late files and unmount and repeated clicks send only one immutable payload', async () => {
  const oldFile = deferred(), oldReport = deferred(), request = deferred(), reportRequest = deferred(), calls = []
  const page = candidatesPage({ createCandidate: payload => { calls.push(plain(payload)); return request.promise }, attachCandidateReport: (id, payload) => { calls.push([id, plain(payload)]); return reportRequest.promise } })
  const { p } = page, candidate = { candidate_id: 'candidate' }
  const slowConfig = p.importConfiguration({ target: { files: [{ size: 1, text: () => oldFile.promise }], value: '' } })
  await p.importConfiguration(fileEvent(configuration))
  oldFile.resolve(JSON.stringify({ ...configuration, candidate_config_version: 'old-version' })); await slowConfig
  assert.equal(p.candidateForm.candidate_config_version, 'candidate-original')
  const slowReport = p.importReport(candidate, { target: { files: [{ size: 1, text: () => oldReport.promise }], value: '' } })
  await p.importReport(candidate, fileEvent(report))
  oldReport.resolve(JSON.stringify({ ...report, report_id: 'old-report' })); await slowReport
  assert.equal(p.reportImports.candidate.report_id, 'original-report')
  const writing = p.createCandidate(); await p.createCandidate()
  p.candidateForm.baseline_config['original-factor'].limit = 500
  assert.equal(calls[0].baseline_config['original-factor'].limit, 3)
  assert.equal(calls.length, 1)
  request.resolve({}); await writing
  const attaching = p.attachReport(candidate); await p.attachReport(candidate)
  p.reportImports.candidate.missing_cases = 700
  assert.equal(calls[1][1].missing_cases, 3)
  assert.equal(calls.length, 2)
  page.unmount(); reportRequest.resolve({}); await attaching
  await p.importConfiguration(fileEvent({ ...configuration, candidate_config_version: 'after-unmount' }))
  assert.notEqual(p.candidateForm.candidate_config_version, 'after-unmount')
})

function reviewPage(methods = {}, query = {}) {
  let unmount
  const route = reactive({ path: '/teacher/skill-review', hash: '#retained', query })
  const destinations = []
  const service = { skillReview: {
    teacherQueue: async () => ({ counts: {} }), manualTasks: async () => ({ items: [] }), samplingItems: async () => ({ items: [] }), teacherDisputes: async () => ({ items: [] }), teacherRetests: async () => ({ items: [] }), stats: async () => ({}), regressionCases: async () => ({}), ...methods,
  } }
  const script = parse(read('../SkillReviewAdmin.vue')).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  const p = runInNewContext(`${script}\n;({ tabs, tabPreset, activeTab, loading, loadError, message, counts, manualTasks, samplingItems, disputes, retests, stats, regression, reviewForms, disputeForms, batchForm, rubricRows, loadAll, selectTab, formatDate, riskLabel, selectionLabel, rateText, createBatch, processDue, claimManual, submitManual, claimSampling, completeSampling, resolveDispute })`, {
    ref, reactive, watch, service, ...helpers, recordRows, useRoute: () => route,
    useRouter: () => ({ replace: target => { destinations.push(plain(target)); Object.assign(route, target); return Promise.resolve() } }),
    onMounted() {}, onBeforeUnmount: fn => { unmount = fn },
  })
  return { p, route, destinations, unmount: () => unmount() }
}
async function visibleReview(p, includeHtml = false) {
  const app = createSSRApp({ render: compile(parse(read('../SkillReviewAdmin.vue')).descriptor.template.content), setup: () => p })
  app.component('RecordView', { render: () => h('div') })
  const html = await renderToString(app)
  return includeHtml ? html : html.replace(/<[^>]*>/g, '')
}

test('skill review cockpit queries select exact initial and same-route sections while retaining retest and stats', async () => {
  for (const [key, heading] of [['manual', '开放题必评'], ['sampling', '常规抽查'], ['disputes', '评分争议'], ['retest', '复测安排'], ['stats', '统计口径']]) {
    const { p, route, destinations } = reviewPage({}, { tab: key, retained: 'original' })
    assert.equal(p.activeTab.value, key)
    await p.loadAll()
    assert.match(await visibleReview(p), new RegExp(heading))
    const html = await visibleReview(p, true)
    assert.match(html, new RegExp(`<h2>${heading}</h2>`))
    assert.equal((html.match(/<h2>/g) || []).length, 1)
    route.query.tab = 'disputes'; await tick()
    assert.equal(p.activeTab.value, 'disputes')
    p.selectTab('sampling'); await tick()
    assert.deepEqual(destinations.at(-1), { path: '/teacher/skill-review', query: { tab: 'sampling', retained: 'original' }, hash: '#retained' })
    for (const value of [['sampling'], {}, 'constructor', 'Sampling', ' sampling ', undefined]) assert.equal(p.tabPreset(value), 'manual')
    route.query.tab = ['sampling']; await tick()
    assert.equal(p.activeTab.value, 'manual')
  }
  const { descriptor, errors } = parse(read('../SkillReviewAdmin.vue'))
  assert.deepEqual(errors, [])
  assert.ok(compileScript(descriptor, { id: 'review' }).content)
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'review', id: 'review' }).errors, [])
})

test('skill review read failures are not empty queues, retry and late responses remain atomic', async () => {
  let fail = true
  const { p } = reviewPage({ manualTasks: async () => { if (fail) throw new Error('private-details'); return { items: [] } } })
  await p.loadAll()
  assert.match(await visibleReview(p), /未能完整读取/)
  assert.doesNotMatch(await visibleReview(p), /暂无待评|private-details/)
  fail = false; await p.loadAll()
  assert.match(await visibleReview(p), /暂无待评/)
  const reads = [deferred(), deferred(), deferred()]; let index = 0
  const page = reviewPage({ manualTasks: () => reads[index++].promise })
  const first = page.p.loadAll(), second = page.p.loadAll()
  reads[0].reject(new Error('old')); await first
  assert.equal(page.p.loading.value, true)
  reads[1].resolve({ items: [{ task_id: 'new' }] }); await second
  assert.equal(page.p.manualTasks.value[0].task_id, 'new')
  assert.equal(page.p.loadError.value, '')
  const third = page.p.loadAll(); page.unmount()
  reads[2].resolve({ items: [{ task_id: 'after-unmount' }] }); await third
  assert.equal(page.p.manualTasks.value[0].task_id, 'new')
})

test('workbench anchors wait for router scroll and final queue layout, retain query and stop after unmount', async () => {
  const route = reactive({ path: '/teacher/feedback', query: { status: 'reopened' }, hash: '#candidates' })
  const frames = [], calls = [], destinations = []; let mounted, unmount
  const script = parse(read('../FeedbackWorkbench.vue')).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  const p = runInNewContext(`${script}\n;({ queueSection, candidateSection, focusSection, sectionReady, goToSection })`, {
    ref, watch, nextTick, requestAnimationFrame: fn => frames.push(fn), useRoute: () => route,
    useRouter: () => ({ replace: target => { destinations.push(plain(target)); Object.assign(route, target); return Promise.resolve() } }),
    onMounted: fn => { mounted = fn }, onBeforeUnmount: fn => { unmount = fn },
  })
  p.queueSection.value = { focus: options => calls.push(['queue-focus', plain(options)]), scrollIntoView: options => calls.push(['queue-scroll', plain(options)]) }
  p.candidateSection.value = { focus: options => calls.push(['candidate-focus', plain(options)]), scrollIntoView: options => calls.push(['candidate-scroll', plain(options)]) }
  const initial = mounted(); await tick()
  assert.equal(calls.length, 0)
  frames.shift()(); await initial
  assert.equal(calls.at(-1)[0], 'candidate-scroll')
  p.sectionReady('candidates'); await tick()
  assert.equal(frames.length, 0)
  p.sectionReady('queue'); await tick()
  assert.equal(frames.length, 1)
  frames.shift()(); await tick()
  assert.equal(calls.filter(([name]) => name === 'candidate-scroll').length, 2)
  const navigation = p.goToSection('#queue'); await tick()
  while (frames.length) frames.shift()()
  await navigation
  assert.deepEqual(destinations.at(-1), { path: '/teacher/feedback', query: { status: 'reopened' }, hash: '#queue' })
  assert.equal(calls.at(-1)[0], 'queue-scroll')
  const late = p.focusSection(); await tick(); unmount()
  const before = calls.length; frames.shift()(); await late
  assert.equal(calls.length, before)
})
