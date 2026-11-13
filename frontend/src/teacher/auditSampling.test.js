import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { parse } from 'vue/compiler-sfc'
import { reactive, ref, watch } from 'vue'
import * as helpers from './feedbackPresentation.js'

function page(write) {
  const source = parse(readFileSync(new URL('./SkillReviewAdmin.vue', import.meta.url), 'utf8')).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  const service = { skillReview: {
    reviewSampling: write, teacherQueue: async () => ({ counts: {} }), manualTasks: async () => ({ items: [] }), samplingItems: async () => ({ items: [] }), teacherDisputes: async () => ({ items: [] }), teacherRetests: async () => ({ items: [] }), stats: async () => ({}), regressionCases: async () => ({}),
  } }
  return runInNewContext(`${source}\n;({ samplingForm, completeSampling, message })`, { ...helpers, reactive, ref, watch, service, useRoute: () => ({ path: '/teacher/skill-review', query: {}, hash: '' }), useRouter: () => ({}), onMounted() {}, onBeforeUnmount() {} })
}

test('sampling records only the checks and conclusion the teacher actually entered', async () => {
  const writes = [], p = page(async (id, payload) => writes.push(JSON.parse(JSON.stringify({ id, payload }))))
  const item = { item_id: 'actual-sample' }
  await p.completeSampling(item)
  assert.equal(writes.length, 0)
  const form = p.samplingForm(item)
  form.evidence_checked = true; form.conclusion = '证据已核对，其余项尚待复核'; form.notes = '原始说明'
  await p.completeSampling(item)
  assert.deepEqual(writes[0], { id: item.item_id, payload: { findings: { evidence_checked: true, verifier_checked: false, rubric_checked: false, help_checked: false, independence_checked: false, conclusion: form.conclusion }, notes: form.notes } })
})

test('a repeated sampling click cannot send two writes or alter the first payload', async () => {
  let finish, calls = 0, payload
  const request = new Promise(resolve => { finish = resolve })
  const p = page((id, data) => { calls++; payload = data; return request }), item = { item_id: 'actual-sample' }
  const form = p.samplingForm(item); form.conclusion = '待核对结论'
  const first = p.completeSampling(item)
  form.evidence_checked = true; form.conclusion = '后来填写的内容'
  await p.completeSampling(item)
  assert.equal(calls, 1); assert.equal(payload.findings.evidence_checked, false); assert.equal(payload.findings.conclusion, '待核对结论')
  finish({}); await first
})
