import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { computed, ref } from 'vue'
import { parse } from 'vue/compiler-sfc'
import { asList, finiteNumber } from '../learning/contracts.js'

const source = readFileSync(new URL('../learning/exams/components/ExamRecordDetail.vue', import.meta.url), 'utf8')
const script = parse(source).descriptor.scriptSetup.content.replace(/^import[\s\S]*?from ['"][^'"]+['"];?\s*/gm, '')
// 域适配器是纯函数：按真实源码加载，测试不复制字段口径。
const examAdapters = (() => {
  const api = readFileSync(new URL('../learning/exams/api.js', import.meta.url), 'utf8')
    .replace(/^import .*$/gm, '')
    .replace(/^export /gm, '')
  return runInNewContext(`${api}\n;({
    RECORDS_PATH, accuracy, examTypeLabel, examsApi, formatDuration, passCondition, resultView,
  })`, { asList, finiteNumber, URLSearchParams })
})()

function resultPage(exams) {
  const routes = []
  const page = runInNewContext(`${script}\n;({ loadResult, record, error, loading, answers, questionCount, accuracyText, formatDateTime, goToPracticeExam, backToRecords, retakeExam })`, {
    ref, computed, onMounted() {}, watch() {}, defineExpose() {},
    useRoute: () => ({ params: { id: 12 } }),
    useRouter: () => ({ push: route => routes.push(route) }),
    ...examAdapters,
    examsApi: { result: id => exams.getExamResult(id) },
  })
  return { page, routes }
}

test('result fetch failure stays on the page with a working retry instead of redirecting', async () => {
  let failing = true
  const { page, routes } = resultPage({ getExamResult: async id => {
    assert.equal(id, 12)
    if (failing) throw Error('private_server_detail')
    return { score: 0, answers: [] }
  } })
  await page.loadResult()
  assert.equal(page.loading.value, false)
  assert.equal(page.record.value, null)
  assert.match(page.error.value, /请重试/)
  assert.doesNotMatch(page.error.value, /private_server_detail/)
  assert.deepEqual(routes, [])
  failing = false
  await page.loadResult()
  assert.equal(page.record.value.score, 0)
  assert.equal(page.error.value, '')
})

test('answer detail failure retains result and never borrows answers from another endpoint', async () => {
  let failing = true
  const calls = []
  const { page } = resultPage({
    getExamResult: async () => {
      if (failing) return { score: 6, theory_exam: 3, answers: [{ theory_question: 7, user_answer: 'learner answer' }] }
      return { score: 6, theory_exam: 3, answers: [{ theory_question: 7, user_answer: 'learner answer', correct_answer: '服务端返回的答案' }] }
    },
    getTheoryQuestions: async id => { calls.push(id); throw Error('not used by the result page') },
  })
  await page.loadResult()
  assert.equal(page.record.value.score, 6)
  assert.equal(page.error.value, '')
  assert.equal(page.record.value.theoryExamId, 3)
  assert.equal(page.answers.value[0].answer, 'learner answer')
  // 结果接口没给参考答案时保持缺失，不去拉题库补取。
  assert.equal(page.answers.value[0].correctAnswer, null)
  assert.deepEqual(calls, [])
  failing = false
  await page.loadResult()
  assert.equal(page.answers.value[0].correctAnswer, '服务端返回的答案')
  assert.deepEqual(calls, [])
})

test('pass condition reads the pass line without treating the exam primary key as an object', async () => {
  const { page } = resultPage({
    getExamResult: async () => ({ score: 40, total_points: 120, is_passed: false, theory_exam: 3, answers: [] }),
  })
  await page.loadResult()
  assert.equal(page.record.value.passScore, null)
  assert.deepEqual(page.record.value.theoryExamId, 3)
  assert.equal(page.questionCount.value, 0)
  assert.equal(page.accuracyText.value, '—')
})

// 模板直接调用的适配器函数必须真实 import；单测曾用注入替身掩盖过漏 import，真浏览器才暴露。
test('result template imports every adapter helper it calls', () => {
  const apiSource = readFileSync(new URL('../learning/exams/api.js', import.meta.url), 'utf8')
  const exported = [...apiSource.matchAll(/^export (?:function|const) (\w+)/gm)].map(match => match[1])
  const template = parse(source).descriptor.template.content
  const callsInTemplate = exported.filter(name => new RegExp(`\\b${name}\\s*\\(`).test(template))
  const importLine = source.match(/import \{([^}]+)\} from '\.\.\/api\.js'/)?.[1] || ''
  const imported = new Set(importLine.split(',').map(part => part.trim()).filter(Boolean))
  assert.ok(callsInTemplate.length > 0)
  for (const name of callsInTemplate) assert.ok(imported.has(name), `${name} 在模板中调用但未从 ../api.js 导入`)
  assert.ok(imported.has('passCondition'))
})

test('practice relation, navigation actions and zero-second duration remain available', async () => {
  const { page, routes } = resultPage({
    getExamResult: async () => ({ practice_exam: 4, practice_record_id: 9, time_spent: 0, total_questions: 0, answers: [{ practice_question: 8 }] }),
  })
  await page.loadResult()
  assert.equal(page.record.value.practiceRecordId, 9)
  assert.equal(page.answers.value[0].questionRef, 8)
  page.goToPracticeExam()
  page.backToRecords()
  page.retakeExam()
  assert.deepEqual(routes, ['/exam-taking/9', '/exam-center/history', '/exam-center'])
  assert.equal(examAdapters.formatDuration(null), '—')
  assert.equal(examAdapters.formatDuration(0), '0秒')
  assert.equal(examAdapters.formatDuration(61), '1分1秒')
  assert.equal(page.formatDateTime('not-a-date'), '—')
})
