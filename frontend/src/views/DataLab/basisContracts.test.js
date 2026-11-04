import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { ref } from 'vue'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'

const source = readFileSync(new URL('./DataLab.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const script = descriptor.scriptSetup.content

test('DataLab actual template and script still compile after read-only basis projection', () => {
  const compiled = compileScript(descriptor, { id: 'basis-contract' })
  assert.deepEqual(compileTemplate({ filename: 'DataLab.vue', source: descriptor.template.content, id: 'basis-contract', compilerOptions: { bindingMetadata: compiled.bindings } }).errors, [])
})

test('DataLab repeated basis saves send six original writable fields and retain read-only cards in state', async () => {
  const defaults = script.slice(script.indexOf('const emptyBasis ='), script.indexOf('const emptyReview ='))
  const load = script.slice(script.indexOf('async function load('), script.indexOf('function resetAttempt('))
  const save = script.slice(script.indexOf('async function saveBasis('), script.indexOf('async function identify('))
  const cards = [{ card_id: 'BC-DS-001', title: '实际依据卡', content: '原文', extra: { preserved: true } }]
  const original = { entity_category: '授权主体', personal_information: '演示信息', data_classification: '受控', uncertainties: '待核查', fact_ids: ['F1', 'F2'], basis_ids: ['BC-DS-001'] }
  const next = { revision: 3, basis: { ...original, cards }, replays: [], scan: null }
  const state = ref(null)
  const basis = {}
  const posts = []
  const page = runInNewContext(`${defaults}\n${load}\n${save}\n({load,saveBasis})`, {
    generation: 0, attemptId: ref('real-attempt'), state, basis, scan: ref(null), selected: ref(null), predictions: {},
    aid: (suffix = '', id = 'real-attempt') => `attempts/${id}/${suffix}`,
    labApi: { get: async () => next, post: async (url, body) => posts.push({ url, body }) },
  })
  await page.load()
  await page.saveBasis()
  await page.saveBasis()
  for (const post of posts) {
    assert.equal(post.url, 'attempts/real-attempt/basis/')
    assert.deepEqual(JSON.parse(JSON.stringify(post.body)), { ...original, expected_revision: 3 })
    assert.equal(Object.hasOwn(post.body, 'cards'), false)
  }
  assert.deepEqual(JSON.parse(JSON.stringify(state.value.basis.cards)), cards)
  assert.deepEqual(next.basis, { ...original, cards })
})
