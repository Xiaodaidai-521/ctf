import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { computed, reactive, ref } from 'vue'
import { compileScript, compileTemplate, parse } from 'vue/compiler-sfc'
import { feedbackError, feedbackLabel } from '../feedback/presentation.js'
import { parseReferenceFile } from './referenceFile.js'

const read = file => readFileSync(new URL(`../../${file}`, import.meta.url), 'utf8')
const plain = value => JSON.parse(JSON.stringify(value))
const pages = ['teacher/SkillReviewAdmin.vue', 'teacher/CapabilityMapAdmin.vue', 'teacher/LearningEffectAnalysis.vue', 'teacher/FeedbackCandidates.vue', 'views/Feedback/FeedbackCenter.vue', 'views/Feedback/FeedbackDetail.vue', 'views/DataLab/DataLab.vue', 'views/DataLab/DataLabTeacher.vue', 'components/MultiAgent/legacy/LegacyMultiAgentChat.vue', 'admin/views/legal/ProtocolSigning.vue', 'admin/views/legal/ComplianceReports.vue', 'admin/views/legal/ComplianceExercises.vue', 'admin/foundation/FoundationLibrary.vue', 'admin/views/legal/ComplianceCenter.vue']
test('all copy-cleanup pages compile without changing their submit-side contracts', () => {
  for (const file of pages) {
    const { descriptor, errors } = parse(read(file))
    assert.deepEqual(errors, [], file)
    assert.ok(compileScript(descriptor, { id: file }).content, file)
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: file }).errors, [], file)
  }
})
function feedbackPage(file, exposed, service) {
  const script = parse(read(`views/Feedback/${file}`)).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  return runInNewContext(`${script}\n;({ ${exposed} })`, {
    computed, reactive, ref, feedbackError, feedbackLabel, service, names: {}, watch() {}, onMounted() {},
    useUserStore: () => ({ userInfo: { role: 'teacher' } }), useRoute: () => ({ params: { id: 'ticket-private' } }),
    crypto: { randomUUID: () => 'request-private' },
  })
}
test('feedback creation preserves all imported original references, versions and evidence', async () => {
  const calls = []
  const p = feedbackPage('FeedbackCenter.vue', 'form, options, evidenceDraft, decisionFields, referenceFields, teacherFields, applyTeacherReferences, updateEvidence, submit', { feedback: {
    create: async payload => { calls.push(plain(payload)); return { feedback_id: 'ticket-private', status: 'pending_evidence' } },
    myList: async () => ({ items: [] }),
  } })
  p.options.categories = [{ value: 'recognition', required_slots: [{ slot: 'sample_location', label: '样本出处' }] }]
  p.form.dispute = '保留完整争议说明'
  p.form.reason = '完整理由'
  p.form.expected_result = '期望重新复核'
  p.form.original_decision_version = 'v1'
  p.applyTeacherReferences(parseReferenceFile('{"student":72,"task_key":"task-private","task_version":"v2","catalog_version":"v3","attempt_id":"attempt-private"}', p.teacherFields))
  Object.assign(p.form, parseReferenceFile('{"original_decision_ref":"decision-private"}', p.decisionFields))
  const evidence = parseReferenceFile('{"ref":"evidence-private"}', p.referenceFields)
  p.updateEvidence('sample_location', 'ref', evidence.ref)
  p.updateEvidence('sample_location', 'version', 'v4')
  p.updateEvidence('sample_location', 'summary', '核查摘要')
  await p.submit()
  assert.deepEqual(calls[0], { client_request_id: 'request-private', category: 'recognition', issue_type: 'false_positive', dispute: '保留完整争议说明', reason: '完整理由', expected_result: '期望重新复核', original_decision_ref: 'decision-private', original_decision_version: 'v1', student: 72, task_key: 'task-private', task_version: 'v2', catalog_version: 'v3', attempt_id: 'attempt-private', evidence: [{ slot: 'sample_location', ref: 'evidence-private', version: 'v4', summary: '核查摘要' }] })
})
test('supplementary feedback evidence preserves imported reference, version, summary and attachment', async () => {
  const calls = []
  const p = feedbackPage('FeedbackDetail.vue', 'detail, evidenceForm, referenceFields, addEvidence', { feedback: { addEvidence: async (id, payload) => { calls.push({ id, payload: plain(payload) }); return { feedback_id: id } } } })
  p.detail.value = { feedback_id: 'ticket-private' }
  Object.assign(p.evidenceForm, { slot: 'sample_location', version: 'v2', summary: '追加说明', attachment_id: 'attachment-private' }, parseReferenceFile('{"ref":"evidence-private"}', p.referenceFields))
  await p.addEvidence()
  assert.deepEqual(calls[0], { id: 'ticket-private', payload: { items: [{ slot: 'sample_location', ref: 'evidence-private', version: 'v2', summary: '追加说明', attachment_id: 'attachment-private' }] } })
})
test('structured teaching replies retain original objects instead of rendering raw JSON', () => {
  // 学生端统一对话使用 AgentMessage；旧协作视图保留在教师兼容装配中。
  const student = parse(read('learning/agent/components/AgentMessage.vue')).descriptor
  assert.match(student.template.content, /v-html="html"/)
  assert.doesNotMatch(student.template.content, /JSON\.stringify/)
  const legacy = parse(read('components/MultiAgent/legacy/LegacyMultiAgentChat.vue')).descriptor
  const helper = legacy.scriptSetup.content.match(/const readableMessageContent = \(content\) => \{[\s\S]*?\n\}/)[0]
  const readable = runInNewContext(`${helper}\n;readableMessageContent`)
  assert.equal(readable('SQL query explanation'), 'SQL query explanation')
  assert.equal(readable({ content: '完整讲解', ref: 'private-reference' }), '完整讲解')
  assert.doesNotMatch(readable({ action_id: 'private-reference' }), /action_id|private-reference|\{/)
  assert.match(legacy.template.content, /RecordView[^>]*:value="msg.content"/)
  assert.match(legacy.scriptSetup.content, /const displayContent = agentResp.content/)
  assert.doesNotMatch(legacy.scriptSetup.content, /JSON.stringify\(agentResp.content\)|JSON.stringify\(displayContent\)/)
})
test('data-lab outcomes and replay choices display human vocabulary while retaining original values', () => {
  const { descriptor } = parse(read('views/DataLab/DataLab.vue'))
  const snippet = descriptor.scriptSetup.content.match(/const submissionLabels = [\s\S]*?(?=const emptyBasis)/)[0]
  const label = runInNewContext(`${snippet}\n;submissionLabel`)
  assert.equal(label('saved'), '已保存')
  assert.equal(label('independent'), '平台内独立')
  assert.equal(label('unknown_backend_enum'), '待确认')
  assert.match(descriptor.template.content, /RecordView :value="r.frozen"/)
  assert.match(descriptor.template.content, /judgment.actions.map\(decisionLabel\)/)
  assert.doesNotMatch(descriptor.template.content, /JSON.stringify|模块六|\{\{ card.card_id \}\}|\{\{ id \}\}/)
})
