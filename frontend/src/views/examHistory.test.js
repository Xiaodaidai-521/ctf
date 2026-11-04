import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { ref, computed, compile, createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { parse } from 'vue/compiler-sfc'

import { asList, finiteNumber } from '../learning/contracts.js'

const source = readFileSync(new URL('../learning/exams/components/ExamRecords.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const script = descriptor.scriptSetup.content.replace(/^import[\s\S]*?from ['"][^'"]+['"];?\s*$/gm, '')
// 域适配器是纯函数：剥掉 @/api 依赖后按真实源码加载，测试不另外复制字段口径。
const examAdapters = (() => {
  const api = readFileSync(new URL('../learning/exams/api.js', import.meta.url), 'utf8')
    .replace(/^import .*$/gm, '')
    .replace(/^export /gm, '')
  return runInNewContext(`${api}\n;({ EXAM_STATUS_FILTERS, EXAM_TYPE_FILTERS, RECORDS_PATH, RESULT_PATH, examsApi, filterRecords, formatDuration, parseRecordQuery, recordView })`, { asList, finiteNumber, URLSearchParams })
})()
function harness(myHistory) {
  const pushes = []
  const replaced = []
  const state = runInNewContext(`${script}\n;({ history, loading, error, filterType, filterStatus, filteredHistory, formatTime, formatDateTime, viewResult, backToCenter, goToExamCenter, loadHistory, typeOptions, statusOptions })`, {
    ref, computed, onMounted() {}, watch() {}, defineExpose() {},
    useRouter: () => ({ push: value => pushes.push(value), replace: value => replaced.push(value) }),
    useRoute: () => ({ query: {} }),
    ...examAdapters,
    examsApi: { myHistory },
  })
  return { ...state, names: { exams: '试炼场' }, pushes }
}
async function render(state) {
  const app = createSSRApp({ render: compile(descriptor.template.content), setup: () => state })
  app.component('ExamOverview', { template: '<section aria-label="测评成长" />' })
  app.component('AppIcon', { template: '<svg aria-hidden="true" />' })
  return renderToString(app)
}

test('exam history keeps filtering and all existing navigation without merging pages', async () => {
  const rows = [
    { id: 1, exam_type: 'theory', status: 'completed' },
    { id: 2, exam_type: 'practice', status: 'completed' },
    { id: 3, exam_type: 'theory', status: 'pending' },
  ]
  const state = harness(async () => ({ records: rows }))
  await state.loadHistory()
  assert.deepEqual(state.filteredHistory.value.map(row => row.id), [1, 2, 3])
  state.filterType.value = 'theory'
  state.filterStatus.value = 'completed'
  assert.deepEqual(state.filteredHistory.value.map(row => row.id), [1])
  assert.equal(state.filteredHistory.value[0].typeLabel, '理论考试')
  assert.equal(state.filteredHistory.value[0].statusLabel, '已完成')
  state.viewResult(1)
  state.backToCenter()
  state.goToExamCenter()
  assert.deepEqual(state.pushes, ['/exam-center/result/1', '/exam-center', '/exam-center'])
  state.filterType.value = 'practice'
  state.filterStatus.value = 'pending'
  const html = await render(state)
  assert.match(html, /没有符合当前筛选的记录/)
  assert.doesNotMatch(html, /暂无考试记录/)
})

test('exam history request failure is not an empty success; retry preserves filters and recovers', async () => {
  let failed = true
  const state = harness(async () => { if (failed) throw Error('INTERNAL_SQL_DETAIL'); return { records: [] } })
  state.filterStatus.value = 'pending'
  await state.loadHistory()
  assert.equal(state.loading.value, false)
  const errorHtml = await render(state)
  assert.match(errorHtml, /role="alert"/)
  assert.match(errorHtml, /测评记录暂时未能读取，请重试/)
  assert.doesNotMatch(errorHtml, /INTERNAL_SQL_DETAIL|暂无考试记录/)
  failed = false
  await state.loadHistory()
  assert.equal(state.error.value, '')
  assert.equal(state.filterStatus.value, 'pending')
  assert.match(await render(state), /暂无考试记录/)
})

test('exam history renders real statuses and distinguishes missing results from failed grades', async () => {
  const state = harness(async () => ({ records: [] }))
  state.loading.value = false
  for (const [status, label] of [['pending', '未开始'], ['in_progress', '进行中'], ['abandoned', '已放弃'], ['timeout', '已超时'], ['INTERNAL_STATE', '状态待确认']]) {
    for (const score of [null, undefined]) {
      state.history.value = [{ id: 1, exam_title: '练习', status, score, is_passed: null }]
      const html = await render(state)
      assert.match(html, new RegExp(`class="history-status">${label}`))
      assert.match(html, /class="history-score">—/)
      assert.doesNotMatch(html, /history-score (?:passed|failed)|未通过|INTERNAL_STATE|—分/)
    }
  }
  for (const [passed, label, className] of [[true, '通过', 'passed'], [false, '未通过', 'failed'], [null, '待判定', '']]) {
    state.history.value = [{ id: 1, status: 'completed', score: 0, is_passed: passed, time_spent: 0, total_questions: 0 }]
    const html = await render(state)
    assert.match(html, new RegExp(`history-score${className ? ' ' + className : ''}">0分`))
    assert.match(html, new RegExp(`history-passed">${label}`))
    assert.match(html, /用时 0秒/)
    assert.match(html, /共 0 题/)
  }
})

test('history uses native keyboard buttons, labelled filters and compact reflow', () => {
  assert.match(descriptor.template.content, /<button v-for="record in filteredHistory"[^>]*type="button"[^>]*@click="viewResult\(record.id\)"/)
  assert.match(descriptor.template.content, /<label>\s*考试类型/)
  assert.match(descriptor.template.content, /<label>\s*考试状态/)
  assert.match(descriptor.styles[0].content, /:focus-visible/)
  assert.match(descriptor.styles[0].content, /\.is-compact \.history-item[^}]*flex-direction: column/)
  assert.doesNotMatch(source, /class="bi|📋|alert\(/)
})

test('history elapsed time preserves zero and avoids exposing invalid date strings', () => {
  const state = harness(async () => ({}))
  assert.equal(state.formatTime(0), '0秒')
  assert.equal(state.formatTime(61), '1分1秒')
  assert.equal(state.formatTime(3600), '1小时0分')
  assert.equal(state.formatTime(undefined), '—')
  assert.equal(state.formatDateTime('not-a-date'), '—')
})
