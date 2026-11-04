import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { computed, effectScope, reactive, ref, watch } from 'vue'
import { usePageFilters } from '../../shared/state/usePageFilters.js'
import { syncStateAccount } from '../../shared/state/accountScope.js'
import { parse } from 'vue/compiler-sfc'
import { createRequestGeneration } from '../../learningKnowledge/requestGeneration.js'
import { dateLabel, governanceError, listScope, listValue } from './data.js'
import { documentStatus, documentType, grantPayload, jobStatus, materialClass, materialStatus, retrievalScore, supervisionFacts } from '../foundation/presentation.js'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
function transport(client) {
  const source = read('../../shared/knowledge/governanceApi.js').replace(/^import.*$/gm, '').replace('export const governanceKnowledgeApi', 'const governanceKnowledgeApi')
  return runInNewContext(`${source}\n;governanceKnowledgeApi`, { axios: { create: () => client }, encodeURIComponent, String })
}

test('staff transport preserves endpoint params, signal, encoded paths and CSRF-first mutations', async () => {
  const calls = [], signal = new AbortController().signal
  const api = transport({ get: async (path, options) => { calls.push(['get', path, options]); return { data: { results: [] } } }, post: async (path, body, options) => { calls.push(['post', path, body, options]); return { data: { status: 'completed' } } } })
  await api.jobs({ page: 2, page_size: 50 }, signal)
  assert.equal(calls[0][1], '/legal-kb/ingestion-jobs/'); assert.equal(calls[0][2].params.page, 2); assert.equal(calls[0][2].signal, signal)
  calls.length = 0
  await api.indexDocument('source/a', signal)
  assert.equal(calls[0][1], '/users/csrf/'); assert.equal(calls[1][1], '/legal-kb/documents/source%2Fa/ingest/')
  assert.equal(calls[1][3].timeout, 180000); assert.equal(calls[1][3].signal, signal)
  calls.length = 0
  const body = { catalog_version: 'course', user_id: 9, active: false, can_review: false, maintain_secrets: false }
  await api.grant(body, signal)
  assert.equal(calls[0][1], '/users/csrf/'); assert.equal(calls[1][1], '/teaching-knowledge/grants/'); assert.equal(calls[1][2], body)
})

test('CSRF failure stops a governance mutation and never falls back to another transport', async () => {
  let writes = 0
  const api = transport({ get: async () => { throw { response: { status: 403 } } }, post: async () => { writes++ } })
  await assert.rejects(api.grant({ user_id: 1 }), error => error.response.status === 403)
  assert.equal(writes, 0)
})

function page(file, api, fields) {
  const scopes = []
  let privacy
  const source = parse(read(file)).descriptor.scriptSetup.content.replace(/^import.*$/gm, '')
  const deps = { computed, reactive, ref, watch, onMounted() {}, usePageFilters() {}, useRoute: () => ({ query: {} }), names: {},
    foundationApi: api, documentStatus, documentType, jobStatus, retrievalScore, materialStatus, materialClass, grantPayload, supervisionFacts,
    dateLabel, governanceError, listScope, listValue,
    useGovernanceSources(loaders) {
      const sources = reactive(Object.fromEntries(Object.keys(loaders).map(key => [key, { data: null, error: '', loading: false }])))
      const clear = () => { for (const source of Object.values(sources)) { source.data = null; source.error = ''; source.loading = false } }
      scopes.push(sources)
      return { sources, loading: ref(false), clear, load: async () => {} }
    },
    usePrivatePage(clearContent) {
      const generations = createRequestGeneration()
      privacy = { paused: ref(false), clear() { generations.invalidate(); clearContent() }, resume() { this.clear(); this.paused.value = false; return true }, begin: () => generations.begin() }
      return privacy
    },
  }
  const bindings = runInNewContext(`${source}\n;({ ${fields.join(', ')} })`, deps)
  return { ...bindings, scopes, privacy }
}
const toolFields = ['pendingDocument', 'updateIndex', 'uncertain', 'busy', 'error', 'message', 'mutationPending', 'query', 'retrieve', 'hits', 'retrieved']
const authFields = ['confirmation', 'submitGrant', 'uncertain', 'busy', 'error', 'message', 'mutationPending', 'form', 'selectedCatalog', 'acknowledged', 'confirmGrant']

test('index update uses the selected real document and distinguishes completed, failed and unknown replies', async () => {
  const calls = []
  const state = page('../foundation/IndexTools.vue', { indexDocument: async id => { calls.push(id); return { status: 'completed' } } }, toolFields)
  state.pendingDocument.value = { id: 12, title: '法律资料' }; await state.updateIndex()
  assert.equal(calls[0], 12); assert.match(state.message.value, /已完成/); assert.equal(state.busy.value, false)
  const failed = page('../foundation/IndexTools.vue', { indexDocument: async () => ({ status: 'failed' }) }, toolFields)
  failed.pendingDocument.value = { id: 12, title: '法律资料' }; await failed.updateIndex()
  assert.match(failed.message.value, /处理失败/); assert.doesNotMatch(failed.message.value, /已完成/)
  const unknown = page('../foundation/IndexTools.vue', { indexDocument: async () => ({ status: 'unknown' }) }, toolFields)
  unknown.pendingDocument.value = { id: 12, title: '法律资料' }; await unknown.updateIndex()
  assert.equal(unknown.uncertain.value, true); assert.match(unknown.error.value, /未能确认/)
})

test('unknown index timeout locks repeated writes; denied mutation is not a fabricated success', async () => {
  let writes = 0
  const state = page('../foundation/IndexTools.vue', { indexDocument: async () => { writes++; throw Error('timeout') } }, toolFields)
  state.pendingDocument.value = { id: 12, title: '资料' }; await state.updateIndex(); await state.updateIndex()
  assert.equal(writes, 1); assert.equal(state.uncertain.value, true)
  assert.equal(state.message.value, ''); assert.match(state.error.value, /未能确认/)
  const denied = page('../foundation/IndexTools.vue', { indexDocument: async () => { throw { response: { status: 403 } } } }, toolFields)
  denied.pendingDocument.value = { id: 12, title: '资料' }; await denied.updateIndex()
  assert.equal(denied.uncertain.value, false); assert.match(denied.error.value, /授权/); assert.equal(denied.message.value, '')
})

test('clearing a private page during an index mutation suppresses late success and locks retry', async () => {
  let finish
  const state = page('../foundation/IndexTools.vue', { indexDocument: () => new Promise(done => { finish = done }) }, toolFields)
  state.pendingDocument.value = { id: 12, title: '私有资料' }; const pending = state.updateIndex(); state.privacy.clear()
  finish({ status: 'completed' }); await pending
  assert.equal(state.message.value, ''); assert.equal(state.pendingDocument.value, null)
  assert.equal(state.uncertain.value, true); assert.equal(state.mutationPending.value, false)
})

test('检索 action sends the real question, preserves citations and treats errors as errors', async () => {
  const calls = []
  const state = page('../foundation/IndexTools.vue', { retrieve: async body => { calls.push(body); return { answer: '资料摘要', citations: [{ title: '法规出处', excerpt: '第三条', score: 0.2 }] } } }, toolFields)
  state.query.value = '  许可范围  '; await state.retrieve()
  assert.equal(calls[0].query, '许可范围'); assert.equal(calls[0].top_k, 5)
  assert.equal(state.hits.value[0].title, '法规出处'); assert.equal(state.retrieved.value, true)
  const denied = page('../foundation/IndexTools.vue', { retrieve: async () => { throw { response: { status: 403 } } } }, toolFields)
  denied.query.value = '许可'; await denied.retrieve()
  assert.equal(denied.retrieved.value, false); assert.equal(denied.hits.value.length, 0); assert.match(denied.error.value, /授权/)
})

function grantState(api) {
  const state = page('../foundation/AuthorizationSupervision.vue', api, authFields)
  state.confirmation.value = { payload: { catalog_version: 'course', user_id: 9, active: false, can_review: false, maintain_secrets: false }, person: '教师', course: '课程' }
  return state
}
test('authorization submits only the confirmed snapshot and distinguishes receipt from complete readback', async () => {
  const calls = []
  const state = grantState({ grant: async body => { calls.push(body); return { grant_id: 18, active: false } } })
  await state.submitGrant()
  assert.equal(calls[0].active, false); assert.equal(calls[0].user_id, 9)
  assert.match(state.message.value, /请求已受理/); assert.match(state.message.value, /完整授权详情仍需核对/)
  assert.equal(state.confirmation.value, null); assert.equal(state.acknowledged.value, false)
})

test('authorization timeout and mismatched receipts lock retries; forbidden replies keep explicit failure', async () => {
  let calls = 0
  const unknown = grantState({ grant: async () => { calls++; throw Error('timeout') } })
  await unknown.submitGrant(); await unknown.submitGrant()
  assert.equal(calls, 1); assert.equal(unknown.uncertain.value, true); assert.equal(unknown.message.value, '')
  const mismatch = grantState({ grant: async () => ({ active: true }) }); await mismatch.submitGrant()
  assert.equal(mismatch.uncertain.value, true); assert.match(mismatch.error.value, /未能确认/)
  const denied = grantState({ grant: async () => { throw { response: { status: 403 } } } }); await denied.submitGrant()
  assert.equal(denied.uncertain.value, false); assert.match(denied.error.value, /授权/); assert.equal(denied.message.value, '')
})

test('account/foreground clearing during authorization removes private drafts and suppresses late success', async () => {
  let finish
  const state = grantState({ grant: () => new Promise(done => { finish = done }) })
  const pending = state.submitGrant(); state.privacy.clear(); finish({ active: false }); await pending
  assert.equal(state.uncertain.value, true); assert.equal(state.confirmation.value, null); assert.equal(state.form.user, '')
  assert.equal(state.message.value, ''); assert.equal(state.selectedCatalog.value, '')
})

test('authorization confirmation requires acknowledgement and real named course/person selections', () => {
  const state = page('../foundation/AuthorizationSupervision.vue', {}, authFields)
  state.scopes[0].catalog.data = { version: 'course', label: '真实课程' }
  state.scopes[0].people.data = [{ id: 9, username: '真实教师', role: 'teacher' }]
  state.form.user = 9; state.selectedCatalog.value = 'course'; state.confirmGrant()
  assert.equal(state.confirmation.value, null)
  state.acknowledged.value = true; state.confirmGrant()
  assert.equal(state.confirmation.value.person, '真实教师'); assert.equal(state.confirmation.value.course, '真实课程')
})

test('governance snapshots retain only safe options and never student searches or private records', () => {
  const contracts = [
    ['../insights/PlatformInsights.vue', "usePageFilters('admin-global-insights', { sort })"],
    ['../foundation/IndexHealth.vue', "usePageFilters('admin-index-health', { filter, page })"],
    ['../foundation/IndexTools.vue', "usePageFilters('admin-index-tools', { page })"],
    ['../foundation/AuthorizationSupervision.vue', "usePageFilters('admin-authorization-supervision', { status })"],
  ]
  for (const [file, contract] of contracts) {
    const source = read(file); assert.ok(source.includes(contract))
    assert.doesNotMatch(source, /usePageFilters\([^\n]*(?:query|search|personSearch|detail|students|selectedStudent|selectedCatalog|form|sources)/)
  }
})

test('safe governance filter/page choices survive remount but clear on account or role change', () => {
  syncStateAccount({ id: 71, role: 'admin' }, { force: true })
  const first = effectScope(), controls = { filter: ref('all'), page: ref(1) }
  first.run(() => usePageFilters('admin-index-health', controls))
  controls.filter.value = 'attention'; controls.page.value = 2; first.stop()
  const restored = { filter: ref('all'), page: ref(1) }, second = effectScope()
  second.run(() => usePageFilters('admin-index-health', restored))
  assert.equal(restored.filter.value, 'attention'); assert.equal(restored.page.value, 2); second.stop()
  syncStateAccount({ id: 72, role: 'admin' })
  const other = { filter: ref('all'), page: ref(1) }, third = effectScope()
  third.run(() => usePageFilters('admin-index-health', other))
  assert.equal(other.filter.value, 'all'); assert.equal(other.page.value, 1); third.stop()
  syncStateAccount({ id: 71, role: 'teacher' })
  const teacher = { filter: ref('all'), page: ref(1) }, fourth = effectScope()
  fourth.run(() => usePageFilters('admin-index-health', teacher))
  assert.equal(teacher.filter.value, 'all'); assert.equal(teacher.page.value, 1); fourth.stop()
  syncStateAccount(null)
})

test('platform overview reflows complete scope descriptions below each metric on mobile', () => {
  const source = read('../insights/PlatformInsights.vue')
  assert.match(source, /class="platform-overview"/)
  assert.match(source, /@media \(max-width: 768px\)/)
  assert.match(source, /\.platform-overview tr \{ display: grid; grid-template-columns: minmax\(0, 1fr\) auto/)
  assert.match(source, /\.platform-overview td:last-child \{ grid-column: 1 \/ -1/)
  assert.match(source, /min-width: 0; padding: 0/)
})
