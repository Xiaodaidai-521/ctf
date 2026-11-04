import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { asList, finiteNumber } from '../contracts.js'

// 域适配器是纯函数；剥掉 @/api 依赖后按真实源码加载，避免测试替身改写字段口径。
const source = readFileSync(new URL('./api.js', import.meta.url), 'utf8')
  .replace(/^import .*$/gm, '')
  .replace(/^export /gm, '')
const exams = runInNewContext(`${source}\n;({
  EXAM_STATUS_FILTERS, EXAM_TYPE_FILTERS, RECORDS_PATH, RESULT_PATH,
  accuracy, filterRecords, formatDuration, levelInfo, levelView, parseRecordQuery,
  passCondition, recordQuery, recordView, recordsHref, resultView, examTypeLabel, examStatusLabel, statPercent,
})`, { asList, finiteNumber, URLSearchParams })
// 跨 realm 对象需转成本域结构才能 deepEqual。
const plain = value => JSON.parse(JSON.stringify(value))

test('level progress uses real rules and never invents a grade when rules are absent', () => {
  assert.deepEqual(plain(exams.levelView([], 80)), { known: false, current: null, next: null, remaining: null, percent: null, top: false })
  const rules = [
    { grade: 'S', title: '大师', minScore: 90 },
    { grade: 'D', title: '初学者', minScore: 0 },
    { grade: 'C', title: '进阶', minScore: 60 },
  ]
  const mid = exams.levelView(rules, 75)
  assert.equal(mid.known, true)
  assert.equal(mid.current.grade, 'C')
  assert.equal(mid.next.grade, 'S')
  assert.equal(mid.remaining, 15)
  assert.equal(mid.percent, 50)
  assert.equal(mid.top, false)
  const top = exams.levelView(rules, 95)
  assert.equal(top.current.grade, 'S')
  assert.equal(top.top, true)
  assert.equal(top.percent, 100)
  assert.equal(top.remaining, null)
  // 平均成绩缺失时不按 0 分落到最低等级。
  const unknown = exams.levelView(rules, null)
  assert.equal(unknown.current, null)
  assert.equal(unknown.percent, null)
  assert.equal(unknown.known, true)
})

test('record view keeps real statuses, missing scores and durations distinct', () => {
  const unknown = exams.recordView({ id: 3, exam_title: '未命名', status: 'INTERNAL_STATE' })
  assert.equal(unknown.statusLabel, '状态待确认')
  assert.equal(unknown.score, null)
  assert.equal(unknown.passed, null)
  assert.equal(unknown.href, '/exam-center/result/3')
  const completed = exams.recordView({ id: 4, exam_type: 'theory', exam_type_display: '理论考试', status: 'completed', score: '10.00', time_spent: 0, is_passed: false })
  assert.equal(completed.score, 10)
  assert.equal(completed.durationSeconds, 0)
  assert.equal(completed.typeLabel, '理论考试')
  assert.equal(completed.passed, false)
  const pending = exams.recordView({ id: 5, status: 'pending' })
  assert.equal(pending.statusLabel, '未开始')
  assert.equal(pending.passed, null)
  assert.equal(pending.score, null)
})

test('result view reads exam keys as primary keys, not objects, and never fabricates answers', () => {
  const result = exams.resultView({
    score: 6, total_points: 10, correct_count: 1, total_questions: 2, is_passed: false,
    theory_exam: 3, practice_exam: null,
    answers: [
      { theory_question: 7, user_answer: 'A', is_correct: false, points_earned: 0 },
      { theory_question: 8, user_answer: 'B', is_correct: true, points_earned: 6, correct_answer: 'B' },
    ],
  })
  assert.equal(result.theoryExamId, 3)
  assert.equal(result.practiceExamId, null)
  assert.equal(result.passScore, null)
  assert.deepEqual(exams.passCondition(result).text, '未通过（后台判定）')
  assert.equal(result.answers[0].questionRef, 7)
  assert.equal(result.answers[0].correctAnswer, null)
  assert.equal(result.answers[1].correctAnswer, 'B')
  assert.equal(result.answers[1].score, 6)
  assert.equal(exams.accuracy(1, 2), 50)
  assert.equal(exams.accuracy(0, 0), null)
  assert.equal(exams.accuracy(undefined, 2), null)
  // 只有对象形态才可能携带及格线，主键形态不能被当作对象读取。
  assert.equal(exams.resultView({ theory_exam: 3, practice_exam: 4 }).passScore, null)
  assert.equal(exams.resultView({ theory_exam: { id: 3, pass_score: 72 } }).passScore, 72)
  assert.equal(exams.resultView({ theory_exam: 3, practice_exam: 4, pass_score: 72 }).passScore, 72)
  // DRF 的 DecimalField 返回字符串；结果页按数字展示，缺值保持 null。
  const decimal = exams.resultView({ score: '10.00', total_points: '10', correct_count: '1', time_spent: '65' })
  assert.equal(decimal.score, 10)
  assert.equal(decimal.totalPoints, 10)
  assert.equal(decimal.correctCount, 1)
  assert.equal(decimal.time_spent, 65)
  assert.equal(exams.resultView({ score: null }).score, null)
})

test('overview stats do not turn "no completed exams" into a 0% average', () => {
  assert.equal(exams.statPercent(0, 0), '—')
  assert.equal(exams.statPercent(0, null), '—')
  assert.equal(exams.statPercent(86.25, 4), '86.3%')
  assert.equal(exams.statPercent(0, 3), '0.0%')
  assert.equal(exams.statPercent(null, 3), '—')
})

test('duration formatting keeps zero and missing values honest', () => {
  assert.equal(exams.formatDuration(null), '—')
  assert.equal(exams.formatDuration(0), '0秒')
  assert.equal(exams.formatDuration(59), '59秒')
  assert.equal(exams.formatDuration(61), '1分1秒')
  assert.equal(exams.formatDuration(3660), '1小时1分')
})

test('record filters round-trip through the URL and unknown values fall back to all', () => {
  assert.deepEqual(plain(exams.parseRecordQuery({ type: 'theory', status: 'completed' })), { type: 'theory', status: 'completed' })
  assert.deepEqual(plain(exams.parseRecordQuery({ type: 'bogus', status: 'INTERNAL' })), { type: '', status: '' })
  assert.equal(exams.recordQuery({ type: 'theory', status: '' }), '?type=theory')
  assert.equal(exams.recordQuery({}), '')
  assert.equal(exams.recordsHref({ type: 'practice', status: 'abandoned' }), '/exam-center/history?type=practice&status=abandoned')
  assert.equal(exams.RECORDS_PATH, '/exam-center/history')
  assert.equal(exams.RESULT_PATH(12), '/exam-center/result/12')
  const rows = [
    { id: 1, exam_type: 'theory', status: 'completed' },
    { id: 2, exam_type: 'practice', status: 'abandoned' },
    { id: 3, exam_type: 'theory', status: 'in_progress' },
  ]
  assert.deepEqual(plain(exams.filterRecords(rows, { type: 'theory' }).map(row => row.id)), [1, 3])
  assert.deepEqual(plain(exams.filterRecords(rows, { status: 'abandoned' }).map(row => row.id)), [2])
  assert.deepEqual(plain(exams.filterRecords(rows, {}).map(row => row.id)), [1, 2, 3])
  assert.deepEqual(plain(exams.filterRecords(null, { type: 'theory' })), [])
  assert.equal(exams.EXAM_STATUS_FILTERS.length, 6)
  assert.equal(exams.EXAM_TYPE_FILTERS.length, 3)
})

test('exam routes keep canonical record URLs and old deep links redirect with their query', () => {
  const routerSource = readFileSync(new URL('../../router/index.js', import.meta.url), 'utf8')
  assert.match(routerSource, /path: '\/exam-center\/history'[\s\S]*?name: 'ExamHistory'[\s\S]*?ExamRecords\.vue/)
  assert.match(routerSource, /path: '\/exam-center\/result\/:id'[\s\S]*?name: 'ExamResult'[\s\S]*?ExamRecordDetail\.vue/)
  assert.match(routerSource, /path: '\/exam-history'[\s\S]*?redirect: to => \(\{ path: '\/exam-center\/history', query: to\.query \}\)/)
  assert.match(routerSource, /path: '\/exam-result\/:id'[\s\S]*?redirect: to => \(\{ path: `\/exam-center\/result\/\$\{to\.params\.id\}`, query: to\.query \}\)/)
})
