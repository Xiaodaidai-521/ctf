import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

function examApi() {
  const source = readFileSync(new URL('./index.js', import.meta.url), 'utf8')
  const start = source.indexOf('  exams: {')
  const end = source.indexOf('\n  },', start) + 5
  assert.ok(start > 0 && end > start)
  const requests = []
  const api = { post: (url, data) => { requests.push({ url, data }); return Promise.resolve({}) } }
  return { service: runInNewContext(`({${source.slice(start, end)}}).exams`, { api }), requests }
}
for (const question of [{ theory_question_id: 3 }, { practice_question_id: 7 }]) {
  test(`exam answer adapter includes required record association for ${Object.keys(question)[0]}`, async () => {
    const { service, requests } = examApi()
    const answer = Object.freeze({ ...question, user_answer: 'example', time_spent: 10 })
    await service.submitAnswer(12, answer)
    assert.equal(requests[0].url, '/exams/records/12/answer/')
    assert.deepEqual(JSON.parse(JSON.stringify(requests[0].data)), { ...answer, exam_record_id: 12 })
    assert.equal(Object.hasOwn(answer, 'exam_record_id'), false)
  })
}
test('exam answer association follows the requested record, not an inconsistent optional field', async () => {
  const { service, requests } = examApi()
  await service.submitAnswer(12, { exam_record_id: 4, user_answer: 'example' })
  assert.equal(requests[0].data.exam_record_id, 12)
})
test('comprehensive exam adapter preserves the confirmed abandon request', async () => {
  const { service, requests } = examApi()
  const data = Object.freeze({ abandon: true })
  await service.startComprehensiveExam(data)
  await service.startComprehensiveExam()
  assert.equal(requests[0].url, '/exams/records/start_comprehensive_exam/')
  assert.deepEqual(requests[0].data, data)
  assert.equal(requests[1].data, undefined)
})
