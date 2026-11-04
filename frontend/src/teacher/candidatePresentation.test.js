import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'
import { configurationVersionLabel, changedFactorLabel, approvalReasonLabel } from './candidatePresentation.js'
import { feedbackError } from './feedbackPresentation.js'
import * as candidateImports from './feedback/candidateImport.js'

const read = name => readFileSync(new URL(name, import.meta.url), 'utf8')
const plain = value => JSON.parse(JSON.stringify(value))
test('configuration labels keep readable versions and do not expose internal references', () => {
  assert.equal(configurationVersionLabel('v1.2-candidate'), 'v1.2（候选）')
  assert.equal(configurationVersionLabel('教学目录第二版'), '教学目录第二版')
  assert.equal(configurationVersionLabel('cfg_internal_01234567-89ab'), '已关联版本，完整名称可下载核对')
  assert.equal(configurationVersionLabel(''), '未指定版本')
  assert.equal(changedFactorLabel('export_record_limit'), '记录数量上限')
  assert.equal(changedFactorLabel('unknown_internal_factor'), '已关联改动因素，完整内容可下载核对')
  assert.equal(changedFactorLabel('复习间隔'), '复习间隔')
})
test('approval explanations use known reasons with a readable fallback and full record retained', () => {
  assert.equal(approvalReasonLabel('没有审批记录。'), '没有审批记录。')
  assert.doesNotMatch(approvalReasonLabel('config_digest_mismatch'), /config_digest/)
  const source = read('FeedbackCandidates.vue')
  assert.match(source, /RecordView :value="candidate"/)
  assert.match(source, /single_changed_factor: candidateForm.single_changed_factor/)
})
test('changed factor import retains exact original submit values without enabling gated flows', async () => {
  const calls = []
  const script = parse(read('FeedbackCandidates.vue')).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  const p = runInNewContext(`${script}\n;({ candidateForm, createCandidate, importConfiguration, factorFields, gates, extractError })`, {
    ...candidateImports, computed, reactive, ref, onMounted() {}, onBeforeUnmount() {}, defineProps: () => ({ embedded: false }), defineEmits: () => () => {}, feedbackError, configurationVersionLabel, changedFactorLabel, approvalReasonLabel,
    service: { feedbackPhase3: {
      createCandidate: async payload => calls.push(plain(payload)),
      issueGroups: async () => ({ items: [], phase3_write_enabled: false, release_enabled: false }),
      candidates: async () => ({ items: [] }),
    }, learningMap: { catalog: async () => ({ capabilities: [] }) } },
  })
  const configuration = { baseline_config_version: 'baseline-original', candidate_config_version: 'candidate-original', single_changed_factor: 'original_exact_factor', rollback_version: 'rollback-original', baseline_config: { original_exact_factor: { threshold: 7, enabled: false } }, candidate_config: { original_exact_factor: { threshold: 9, enabled: false } }, target_task_versions: ['original-task@7'], excluded_scope: ['original-exclusion'], expected_risk: '原始风险' }
  await p.importConfiguration({ target: { files: [{ size: 1000, text: async () => JSON.stringify(configuration) }], value: 'configuration.json' } })
  Object.assign(p.candidateForm, { title: '候选', issue_group_ids: ['original-group'], baseline_config_version: 'baseline-original', candidate_config_version: 'candidate-original', single_changed_factor: 'original_exact_factor', rollback_version: 'rollback-original' })
  await p.createCandidate()
  assert.equal(calls[0].single_changed_factor, 'original_exact_factor')
  assert.equal(calls[0].baseline_config_version, 'baseline-original')
  assert.equal(calls[0].candidate_config_version, 'candidate-original')
  assert.equal(calls[0].rollback_version, 'rollback-original')
  assert.deepEqual(calls[0].issue_group_ids, ['original-group'])
  assert.deepEqual(calls[0], { title: '候选', issue_group_ids: ['original-group'], ...configuration })
  assert.equal(p.gates.phase3_write_enabled, false)
  assert.equal(p.gates.release_enabled, false)
  assert.doesNotMatch(p.extractError({ response: { data: { code: 'phase3_write_disabled' } } }), /phase3|接口/)
})
test('imported analysis filters remain selected and submit unchanged even outside candidate lists', () => {
  const { descriptor } = parse(read('insights/EvaluationStatistics.vue'))
  const p = runInNewContext(`${descriptor.scriptSetup.content.replace(/^import .*$/gm, '')}\n;({ applyFilters, params })`, { computed, ref, watch() {}, onMounted() {}, onBeforeUnmount() {}, useUserStore: () => ({ userInfo: { role: 'teacher', id: 1 } }), configurationVersionLabel })
  const input = { student_id: 72, task_key: 'original-task-key', knowledge_point_id: 'original-point', catalog_version: 'original-catalog' }
  p.applyFilters(input)
  assert.deepEqual(plain(p.params()), { mode: 'formal', ...input })
  for (const value of ['studentId', 'taskKey', 'knowledgePoint', 'catalogVersion']) {
    assert.match(descriptor.template.content, new RegExp(`<option v-if="${value}[^\"]*" :value="${value}"`))
  }
  assert.match(descriptor.template.content, /RecordView :value="data"/)
})
test('all final presentation pages compile', () => {
  for (const name of ['CapabilityMapAdmin.vue', 'FeedbackCandidates.vue', 'LearningEffectAnalysis.vue']) {
    const { descriptor, errors } = parse(read(name))
    assert.deepEqual(errors, [])
    assert.ok(compileScript(descriptor, { id: name }).content)
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: name, id: name }).errors, [])
  }
})
