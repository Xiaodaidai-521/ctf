import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compile, computed, createSSRApp, h, reactive, ref, watch } from 'vue'
import { queueStatusPreset } from './feedback/queueState.js'
import { renderToString } from 'vue/server-renderer'
import { compileScript, compileTemplate, parse } from 'vue/compiler-sfc'
import * as presentation from './feedbackPresentation.js'
import { recordRows } from '../shared/forms/recordPresentation.js'
import { downloadRecord, parseReferenceFile } from '../shared/forms/referenceFile.js'

const files = ['FeedbackQueue.vue', 'FeedbackDetail.vue', 'FeedbackReconciliation.vue']
const exposed = {
  'FeedbackQueue.vue': 'embedded, loading, queueLoaded, queueError, optionsError, batchesLoading, batchesLoaded, batchesError, batchLoading, queueNext, queue, statuses, categories, batches, selectedBatch, error, creatingBatch, riskTickets, riskLoading, riskLoaded, riskError, batchNames, batchNamesError, filters, batchForm, statusTone, loadQueue, loadOptions, loadBatches, loadBatch, createBatch, loadRiskTickets, loadBatchNames',
  'FeedbackDetail.vue': 'detail, error, message, selectedMissing, mainTicket, mainTicketError, duplicateTickets, duplicateLoading, duplicateLoaded, duplicateError, ownerCandidates, studentRetests, options, actionForms, ownerFields, evidenceFields, externalFields, retestFields, submitAssign, submitEffect, pendingReferrals, splitRefs, load, run, requestEvidence, confirmTicket, retryEvents, download, loadDuplicateTickets, loadMainTicket',
  'FeedbackReconciliation.vue': 'data, error, message, retrying, loading, ticketNames, namesError, load, loadNames, retryTicket, retryAll',
}
const source = file => readFileSync(new URL(file, import.meta.url), 'utf8')
const plain = value => JSON.parse(JSON.stringify(value))
const tick = () => new Promise(resolve => setImmediate(resolve))
const makeTicket = (index, extra = {}) => ({
  feedback_id: `feedback-private-${index}`, student_id: 7, student_name: '小明',
  category: 'teaching', issue_type: 'scoring_dispute', task_title: `授权练习${index}`,
  status: 'pending_fact_review', created_at: '2026-11-01T12:30:00Z', waiting_days: 1,
  impact_level: 'high', novelty: 'new', conflict_flag: true, ...extra,
})

function page(file, methods = {}) {
  const defaultDetail = makeTicket('current', { version: 9, evidence: [], referrals: [], missing_evidence: [] })
  const service = { feedback: {
    teacherQueue: async () => ({ items: [], total: 0, page: 1, page_size: 100 }),
    options: async () => ({}), samplingBatches: async () => ({ items: [] }),
    teacherDetail: async () => defaultDetail, teacherAction: async () => defaultDetail,
    reconciliation: async () => ({ items: [], scanned: 0, counts: {} }), retryEvents: async () => ({}),
    ...methods,
  } }
  const script = parse(source(file)).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  const helpers = { ...presentation, formatDate: presentation.feedbackDate }
  const result = runInNewContext(`${script}\n;({ ${exposed[file]} })`, {
    ...helpers, reactive, ref, computed, watch, queueStatusPreset, defineProps: () => ({ embedded: false }), defineEmits: () => () => {}, onMounted() {}, onBeforeUnmount() {}, useRoute: () => ({ params: { id: 'current-id' }, query: {} }), service,
  })
  return { ...result, ...helpers }
}

async function visible(file, state) {
  const template = parse(source(file)).descriptor.template.content
  const app = createSSRApp({ render: compile(template), setup: () => state })
  app.component('router-link', { props: ['to'], setup: (props, { slots }) => () => h('a', { href: props.to }, slots.default?.()) })
  for (const [name, exposed] of Object.entries({ RecordView: 'rows, downloadRecord', ReferenceImport: 'error, message, hasValue, download, clear, importFile' })) {
    const { descriptor } = parse(readFileSync(new URL(`../shared/forms/${name}.vue`, import.meta.url), 'utf8'))
    app.component(name, {
      props: ['value', 'title', 'fields', 'modelValue'], render: compile(descriptor.template.content),
      setup(props, { emit }) {
        return runInNewContext(`${descriptor.scriptSetup.content.replace(/^import .*$/gm, '')}\n;({ ${exposed} })`, {
          ref, computed, recordRows, downloadRecord, parseReferenceFile, defineProps: () => props, defineEmits: () => emit,
        })
      },
    })
  }
  const html = await renderToString(app)
  // IDs must remain in routes/select values, but must not appear as visible text.
  return { html, text: html.replace(/<[^>]*>/g, '') }
}

for (const file of files) {
  test(`${file}: Vue script and template compile`, () => {
    const { descriptor, errors } = parse(source(file))
    assert.deepEqual(errors, [])
    assert.ok(compileScript(descriptor, { id: file }).content)
    const result = compileTemplate({ source: descriptor.template.content, filename: file, id: file })
    assert.deepEqual(result.errors, [])
    assert.doesNotMatch(descriptor.template.content, /style=/)
  })
}

test('enum labels use explicit vocabulary and never echo unknown values', () => {
  assert.equal(presentation.feedbackLabel('destination', 'module6'), '核验与评分复核')
  assert.equal(presentation.feedbackLabel('destination', 'module1'), '目录与推荐维护')
  assert.equal(presentation.feedbackLabel('source', 'server_linked'), '关联记录')
  assert.equal(presentation.feedbackLabel('action', 'ack_referral'), '登记接收结果')
  for (const kind of ['status', 'category', 'issue', 'role', 'owner', 'destination', 'sampling', 'event', 'action', 'slot', 'mapping', 'impact', 'novelty', 'effect', 'evidence', 'source', 'visibility', 'referral', 'eventStatus']) {
    for (const value of ['unknown_backend_enum', '__proto__', 'constructor', '', null]) {
      assert.equal(typeof presentation.feedbackLabel(kind, value), 'string')
      assert.doesNotMatch(presentation.feedbackLabel(kind, value), /unknown_backend_enum|__proto__|constructor/)
    }
  }
  assert.deepEqual(presentation.feedbackOptions([{ value: 'module6', label: '模块六' }], 'destination'), [{ value: 'module6', label: '核验与评分复核' }])
})

test('semantic feedback titles retain task, student, issue and date, never IDs', () => {
  const title = presentation.feedbackTitle(makeTicket(1))
  assert.match(title, /授权练习1.*评分争议.*小明.*2026/)
  assert.doesNotMatch(title, /feedback-private/)
  assert.match(presentation.feedbackTitle(), /暂不可用/)
  assert.doesNotMatch(presentation.feedbackDate('broken-private-id'), /broken-private-id|Invalid Date/)
})

test('known errors are actionable, arbitrary backend exceptions are never displayed', () => {
  const raw = { response: { status: 500, data: { detail: 'OperationalError internal_uuid', code: 'unknown_private_error' } } }
  assert.equal(presentation.feedbackError(raw, '读取失败'), '读取失败')
  assert.match(presentation.feedbackError({ response: { data: { code: 'version_conflict' } } }), /刷新/)
  assert.match(presentation.feedbackError({ response: { data: { code: 'risk_not_in_population' } } }), /排除既往样本/)
  assert.equal(presentation.feedbackError({ response: { data: { code: 'destination_required', required_destination: 'module6' } } }), '此反馈需要转交核验与评分复核。')
  for (const status of ['pending', 'missing', 'mismatch', 'linked', 'private_enum']) {
    assert.doesNotMatch(presentation.reconciliationNote({ status, last_error: 'OperationalError internal_uuid' }), /OperationalError|internal_uuid|private_enum/)
  }
})

test('pagination follows the returned page size, rejects incomplete responses', () => {
  assert.equal(presentation.nextFeedbackPage({ page: 1, page_size: 20, total: 41, items: [{}] }), 2)
  assert.equal(presentation.nextFeedbackPage({ page: 3, page_size: 20, total: 41, items: [{}] }), null)
  assert.throws(() => presentation.nextFeedbackPage({ page: 1, page_size: 20, total: 41, items: [] }))
  assert.throws(() => presentation.nextFeedbackPage({ items: [] }))
})

test('risk selection traverses all authorised pages independently of queue filters', async () => {
  const calls = []
  const all = Array.from({ length: 205 }, (_, i) => makeTicket(i))
  const p = page('FeedbackQueue.vue', { teacherQueue: async params => {
    calls.push(plain(params))
    return { items: all.slice((params.page - 1) * 100, params.page * 100), page: params.page, page_size: 100, total: all.length }
  } })
  p.filters.category = 'recognition'
  p.filters.owner = 'me'
  p.queue.items = all.slice(0, 50)
  await p.loadRiskTickets()
  assert.deepEqual(calls.map(call => call.page), [1, 2, 3])
  assert.ok(calls.every(call => !call.owner && !call.category && !call.status))
  assert.equal(p.riskTickets.value.length, 205)
  assert.equal(p.riskTickets.value[204].feedback_id, 'feedback-private-204')
  assert.equal(p.riskLoaded.value, true)
})

test('partial risk-list failure preserves choices, separates errors and can be retried', async () => {
  let fail = true
  const p = page('FeedbackQueue.vue', { teacherQueue: async params => {
    if (params.page === 2 && fail) throw { response: { status: 500, data: { detail: 'private failure' } } }
    return { items: [makeTicket(params.page)], page: params.page, page_size: 1, total: 2 }
  } })
  p.batchForm.risk_ticket_ids = ['feedback-private-1']
  await p.loadRiskTickets()
  assert.equal(p.error.value, '')
  assert.match(p.riskError.value, /尚未全部读取/)
  assert.equal(p.riskLoaded.value, false)
  assert.deepEqual(plain(p.batchForm.risk_ticket_ids), ['feedback-private-1'])
  fail = false
  await p.loadRiskTickets()
  assert.equal(p.riskTickets.value.length, 2)
  assert.equal(p.riskError.value, '')
  assert.equal(p.riskLoaded.value, true)
})

test('sampling payload preserves selected IDs, original scope and other options', async () => {
  const calls = []
  const p = page('FeedbackQueue.vue', { createSamplingBatch: async payload => {
    calls.push(plain(payload))
    return { batch_id: 'private-batch', items: [] }
  } })
  Object.assign(p.batchForm, { status: 'handled', sample_size: 12, exclude_prior: false, notes: '原说明', random_seed: '42', risk_ticket_ids: ['feedback-private-204', 'feedback-private-1'] })
  await p.createBatch()
  assert.deepEqual(calls[0], { scope: { statuses: ['handled'] }, sample_size: 12, exclude_prior: false, notes: '原说明', random_seed: 42, risk_ticket_ids: ['feedback-private-204', 'feedback-private-1'] })
  p.batchForm.random_seed = ''
  await p.createBatch()
  assert.equal(Object.hasOwn(calls[1], 'random_seed'), false)
})

test('queue and batch text use semantic titles while preserving internal destinations', async () => {
  const p = page('FeedbackQueue.vue')
  await Promise.all([p.loadQueue(), p.loadBatches()])
  p.queue.items = [makeTicket(1)]
  p.queue.counts = { private_state: 1 }
  p.selectedBatch.value = { batch_id: 'private-batch', method: 'private_method', created_at: '2026-11-01', items: [{ ticket_id: 'private-ticket', selected_reason: 'random', status: 'handled' }] }
  p.batchNames['private-ticket'] = makeTicket(2)
  p.batches.value = [p.selectedBatch.value]
  const { text, html } = await visible('FeedbackQueue.vue', p)
  assert.match(text, /授权练习2/)
  assert.doesNotMatch(text, /private-batch|private-ticket|private_method|private_state|UUID|高风险样本 ID/)
  assert.match(html, /href="\/teacher\/feedback\/private-ticket"/)
})

test('duplicate selector reads beyond the first page and retains all eligible primary feedback', async () => {
  const calls = []
  const p = page('FeedbackDetail.vue', { teacherQueue: async params => {
    calls.push(params.page)
    return { items: [makeTicket(params.page), makeTicket('other', { student_id: 8 })], page: params.page, page_size: 2, total: 4 }
  } })
  p.detail.value = makeTicket('current')
  await p.loadDuplicateTickets()
  assert.deepEqual(calls, [1, 2])
  assert.deepEqual(p.duplicateTickets.value.map(item => item.feedback_id), ['feedback-private-1', 'feedback-private-2'])
  assert.equal(p.duplicateLoaded.value, true)
})

test('teacher actions keep all payloads, IDs and optimistic concurrency fields', async () => {
  const calls = []
  const p = page('FeedbackDetail.vue', { teacherAction: async (id, payload) => {
    calls.push({ id, payload: plain(payload) })
    return makeTicket('current', { version: 9, status: 'handled', missing_evidence: [] })
  } })
  const cases = {
    claim: { reason: '认领理由' }, assign: { owner_id: '71', owner_role: 'teacher', reason: '分配理由' },
    triage: { impact_level: 'high', novelty: 'new', conflict_flag: true },
    request_evidence: { owner_id: '72', due_at: '2026-11-01T18:00:00+08:00', missing_slots: ['attempt_ref'] },
    confirm: { handling_destination: 'module6', evidence_refs: ['evidence-private'] }, reject: { reason: '驳回理由' },
    revise_review: { conclusion: 'confirmed', evidence_refs: ['external-private'] },
    start_handling: { handling_action: '人工处理', handling_destination: 'module1' },
    refer: { destination: 'module6', external_ref: 'outside-private' },
    ack_referral: { referral_id: 'referral-private', referral_status: 'declined', ack_note: '退回说明' },
    handle: { handling_note: '已处理说明' }, set_effect: { effect_status: 'verified', retest_fact_ref: 'fact-private', retest_attempt_ref: 'attempt-private' },
    reopen: { reason: '重开理由' }, note: { reason: '备注内容' },
    confirm_duplicate: { main_ticket_id: 'primary-private', reason: '重复理由' }, split_duplicate: { reason: '拆分理由' },
  }
  for (const [action, payload] of Object.entries(cases)) {
    p.detail.value = makeTicket('current', { version: 9 })
    await p.run(action, payload)
    assert.deepEqual(calls.at(-1), { id: 'feedback-private-current', payload: { action, expected_version: 9, ...payload } })
    assert.doesNotMatch(p.message.value, new RegExp(action === 'note' ? 'private' : action))
  }
})

test('detail options relabel destinations without dropping values; evidence forms keep references', async () => {
  const calls = []
  const p = page('FeedbackDetail.vue', {
    options: async () => ({ destinations: [{ value: 'module6', label: '模块六' }, { value: 'execution_integration', label: '里程碑 I' }] }),
    teacherAction: async (id, payload) => { calls.push(plain(payload)); return makeTicket('current', { version: 9 }) },
  })
  await p.load()
  assert.deepEqual(plain(p.options.destinations).map(item => item.value), ['module6', 'execution_integration'])
  assert.doesNotMatch(JSON.stringify(p.options.destinations.map(item => item.label)), /模块|里程碑/)
  p.selectedMissing.value = ['attempt_ref']
  Object.assign(p.actionForms.request, { owner_id: 72, due_at: '2026-11-01T18:00:00+08:00', reason: '补充说明' })
  p.requestEvidence()
  await tick()
  assert.deepEqual(calls[0].missing_slots, ['attempt_ref'])
  assert.equal(calls[0].owner_id, 72)
  p.actionForms.confirm.evidence_refs = ' arbitrary-external-ref , another-ref '
  p.confirmTicket()
  await tick()
  assert.deepEqual(calls[1].evidence_refs, ['arbitrary-external-ref', 'another-ref'])
})

test('detail resolves names and referral choices, hides references while retaining complete records', async () => {
  const p = page('FeedbackDetail.vue')
  p.detail.value = makeTicket('current', {
    submitter_name: '老师', submitter_role: 'teacher', task_key: 'private-task-key', task_version: '1',
    capability_id: 'private-capability', capability_title: '访问控制', knowledge_point_id: 'private-point', knowledge_point_name: '授权检查',
    attempt_id: 'private-attempt', missing_mapping: ['capability_or_knowledge_point'], handling_destination: 'module6',
    original_decision_snapshot: { ref: 'preserved-evidence-private' },
    referrals: [{ referral_id: 'private-referral', destination: 'module6', status: 'pending_ack', created_at: '2026-11-01' }],
    reconciliation: { counts: { pending: 1 }, items: [{ action_id: 'private-action', action: 'confirm', event_type: 'feedback_reviewed', status: 'pending', last_error: 'OperationalError' }] },
  })
  const { text, html } = await visible('FeedbackDetail.vue', p)
  assert.match(text, /访问控制.*授权检查/)
  assert.doesNotMatch(text, /private-task-key|private-capability|private-point|private-attempt|private-referral|OperationalError|feedback_reviewed|capability_or_knowledge_point/)
  assert.match(html, /value="private-referral"/)
  assert.doesNotMatch(text, /preserved-evidence-private/)
  assert.equal(p.detail.value.original_decision_snapshot.ref, 'preserved-evidence-private')
  assert.match(text, /下载原始判定完整记录/)
  assert.match(text, /分配负责人模板|可选的复测|复测核验对照/)
})

test('imported owner, review references and verified retest flow through real action wrappers', async () => {
  const calls = []
  const p = page('FeedbackDetail.vue', { teacherAction: async (id, payload) => {
    calls.push(plain(payload))
    return makeTicket('current', { version: 9, missing_evidence: [] })
  } })
  p.detail.value = makeTicket('current', { version: 9 })
  Object.assign(p.actionForms.assign, parseReferenceFile('{"owner_id":72}', p.ownerFields), { reason: '分配说明' })
  p.submitAssign()
  await tick()
  assert.deepEqual(calls[0], { action: 'assign', expected_version: 9, owner_id: 72, owner_role: 'teacher', reason: '分配说明' })
  Object.assign(p.actionForms.confirm, parseReferenceFile('{"evidence_refs":["fact-private","outside-private"]}', p.evidenceFields), { reason: '确认说明' })
  p.confirmTicket()
  await tick()
  assert.deepEqual(calls[1].evidence_refs, ['fact-private', 'outside-private'])
  Object.assign(p.actionForms.effect, parseReferenceFile('{"retest_fact_ref":"fact-private","retest_attempt_ref":"attempt-private"}', p.retestFields), { effect_status: 'verified', effect_note: '核对说明' })
  p.submitEffect()
  await tick()
  assert.deepEqual(calls[2], { action: 'set_effect', expected_version: 9, effect_status: 'verified', effect_note: '核对说明', retest_fact_ref: 'fact-private', retest_attempt_ref: 'attempt-private' })
  assert.equal(p.error.value, '')
})

test('reconciliation resolves names sequentially and retries with original IDs', async () => {
  const calls = []
  let active = 0
  let peak = 0
  const p = page('FeedbackReconciliation.vue', {
    teacherDetail: async id => { active++; peak = Math.max(peak, active); await tick(); active--; return makeTicket(id) },
    retryEvents: async payload => { calls.push(plain(payload)); return {} },
  })
  p.data.items = [{ feedback_id: 'first' }, { feedback_id: 'second' }]
  await p.loadNames()
  assert.equal(peak, 1)
  assert.match(p.ticketNames.second.task_title, /second/)
  await p.retryTicket('original-private-ticket')
  await p.retryAll()
  assert.deepEqual(calls, [{ ticket_id: 'original-private-ticket' }, {}])
})

test('reconciliation auxiliary failures do not hide retry controls or leak errors', async () => {
  const p = page('FeedbackReconciliation.vue', { teacherDetail: async () => { throw { response: { data: { detail: 'OperationalError private-message' } } } } })
  p.data.items = [{ feedback_id: 'private-ticket', status: 'private-status', counts: { pending: 1 }, items: [{ action_id: 'private-action', event_id: 'private-event', action: 'private-action-type', event_type: 'private-event-type', status: 'pending', last_error: 'OperationalError' }] }]
  await p.loadNames()
  assert.equal(p.error.value, '')
  assert.match(p.namesError.value, /标题/)
  const { text, html } = await visible('FeedbackReconciliation.vue', p)
  assert.match(text, /重试读取标题.*重试该反馈/)
  assert.doesNotMatch(text, /private-|OperationalError|事件 ID/)
  assert.match(html, /href="\/teacher\/feedback\/private-ticket"/)
})
