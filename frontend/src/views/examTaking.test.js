import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { runInNewContext } from 'node:vm'
import * as Vue from 'vue'
import { renderToString } from 'vue/server-renderer'
import { parse, compileScript, compileTemplate, compileStyle } from 'vue/compiler-sfc'
import { asList, finiteNumber } from '../learning/contracts.js'

const require = createRequire(import.meta.url)
const icons = require('@arco-design/web-vue/lib/icon')
const read = file => readFileSync(new URL(file, import.meta.url), 'utf8')
const source = read('./ExamTaking.vue')
const css = read('./examTaking.css')
const files = ['ExamTaking', 'ExamTakingDialog']
const compiled = Object.fromEntries(files.map(name => {
  const { descriptor, errors } = parse(read(`./${name}.vue`), { filename: `${name}.vue` })
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: name, genDefaultAs: '__component' })
  const template = compileTemplate({ source: descriptor.template.content, filename: `${name}.vue`, id: name, compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  return [name, { descriptor, script, template }]
}))

// Run the actual SFC-compiled script and render, with only boundary imports mocked.
function importsForVm(code) {
  return code.replace(/^import\s+([\s\S]*?)\s+from\s+['"]([^'"]+)['"];?\s*$/gm, (_, specifier, path) => {
    const binding = specifier.trim().startsWith('{') ? specifier.replace(/\bas\b/g, ':') : `{ default: ${specifier} }`
    return `const ${binding} = __imports[${JSON.stringify(path)}];\n`
  })
}
function component(name, imports, globals = {}) {
  const { script, template } = compiled[name]
  return runInNewContext(`${importsForVm(script.content)}\n${importsForVm(template.code).replace('export function render', 'function render')}\n__component.render = render; __component`, { __imports: imports, ...globals })
}
const Dialog = component('ExamTakingDialog', { vue: Vue })
// 域适配器是纯函数：剥离 @/api 依赖后在 vm 中加载，避免用测试替身改写真实字段口径。
const examAdapters = (() => {
  const source = read('../learning/exams/api.js')
    .replace(/^import .*$/gm, '')
    .replace(/^export /gm, '')
  return runInNewContext(`${source}\n;({ RESULT_PATH, practiceQuestionRef, savedAnswerRef, theoryExamId, theoryQuestionRef })`, { asList, finiteNumber })
})()
function examPage(exams = {}) {
  const mounted = [], unmounted = [], routes = [], alerts = [], sanitized = [], watchers = []
  const intervals = new Map(), delays = []
  const params = Vue.reactive({ id: 12 })
  let timerId = 0
  const Page = component('ExamTaking', {
    vue: { ...Vue, onMounted: callback => mounted.push(callback), onUnmounted: callback => unmounted.push(callback), watch: (getter, callback) => { watchers.push({ getter, callback }) } },
    'vue-router': { useRoute: () => ({ params }), useRouter: () => ({ push: route => routes.push(route) }) },
    '@/api': { default: { exams: {
      getTheoryExam: async () => ({ duration: 180 }),
      getPracticeExam: async () => ({ duration: 180 }),
      ...exams,
      getExamResult: async id => ({ start_time: new Date().toISOString(), answers: [], ...(await exams.getExamResult?.(id)) }),
    } } },
    '@/utils/sanitize': { sanitizeHtml: value => { sanitized.push(value); return '<p>经过清理的题面</p>' } },
    '@/shared/navigation/names': { names: { exams: '试炼场' } },
    '@/learning/exams/api.js': examAdapters,
    './ExamTakingDialog.vue': { default: Dialog },
  }, {
    console: { log() {}, error() {} }, alert: message => alerts.push(message),
    setInterval: (callback, ms) => { intervals.set(++timerId, { callback, ms }); return timerId },
    clearInterval: id => intervals.delete(id),
    setTimeout: (callback, ms) => { delays.push({ callback, ms }); return delays.length },
  })
  const page = Page.setup({}, { expose() {} })
  return { page, Page, mounted, unmounted, routes, alerts, sanitized, intervals, delays, params, watchers }
}
async function html(harness) {
  const app = Vue.createSSRApp({ setup: () => harness.page, render: harness.Page.render })
  for (const [key, icon] of Object.entries(icons)) if (key.startsWith('Icon')) app.component(key, icon)
  return renderToString(app)
}
const plain = value => JSON.parse(JSON.stringify(value))
const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); await Vue.nextTick() }
const theoryQuestions = () => [
  { id: 19, question: 91, points: 10, question_detail: { question_type: 'single_choice', question_text: '<p>原始题面</p>', options: ['选项一', '选项二'] } },
  { id: 5, question: 22, points: 5, question_detail: { question_type: 'multiple_choice', question_text: '多选题面', options: ['甲', '乙', '丙'] } },
  { id: 3, question: 80, points: 5, question_detail: { question_type: 'true_false', question_text: '判断题面', options: ['正确', '错误'] } },
]
function ready(harness, type = 'theory') {
  harness.page.loading.value = false
  harness.page.examType.value = type
  harness.page.examInfo.value = { title: '正式测评题目' }
  harness.page.questions.value = type === 'theory' ? theoryQuestions() : [
    { id: 7, points: 50, challenge: { description: '<p>实战环境说明与题面链接</p>' }, challenge_difficulty: 'hard', challenge_points: 50 },
    { id: 4, challenge: { description: '第二道实战题' }, challenge_difficulty: 'easy', challenge_points: 20 },
  ]
  harness.page.timeRemaining.value = 600
  return harness
}

test('both actual SFCs compile; page-scoped external styles use declared tokens and real Arco icons', () => {
  const tokens = new Set([...read('../shared/design/tokens.css').matchAll(/(--[\w-]+)\s*:/g)].map(match => match[1]))
  for (const name of files) {
    const { descriptor, script } = compiled[name]
    assert.ok(script.content.includes('setup('))
    for (const style of descriptor.styles) {
      assert.equal(style.scoped, true)
      const content = style.src ? read(style.src) : style.content
      const result = compileStyle({ source: content, filename: `${name}.vue`, id: `data-v-${name}`, scoped: true })
      assert.deepEqual(result.errors, [])
      assert.doesNotMatch(content, /#[\da-f]{3,8}\b|rgba?\(|gradient\(|\d+(?:px|rem)|position:\s*fixed/i)
      for (const [, token] of content.matchAll(/var\((--[\w-]+)/g)) assert.ok(tokens.has(token), token)
      assert.doesNotMatch(result.code, /\.is-compact\[data-v-/)
    }
  }
  assert.equal(compiled.ExamTaking.descriptor.styles[0].src, './examTaking.css')
  assert.doesNotMatch(source, /\bbi[- ]|\p{Extended_Pictographic}/u)
  for (const [, name] of source.matchAll(/<(icon-[a-z-]+)/g)) {
    const exported = name.split('-').map(word => word[0].toUpperCase() + word.slice(1)).join('')
    assert.ok(icons[exported], name)
  }
  assert.match(css, /:focus-visible/)
  assert.match(css, /:disabled[^}]*var\(--disabled-ink\)/)
  assert.match(css, /prefers-reduced-motion: reduce/)
})

test('compact skin rearranges header, sidebar, answers and actions rather than retaining fixed widths', () => {
  for (const selector of ['exam-header', 'exam-content', 'flag-input']) {
    assert.match(css, new RegExp(`\\.is-compact \\.${selector}[^}]*grid-template-columns: minmax\\(0, 1fr\\)`))
  }
  assert.match(css, /\.is-compact \.quick-nav[^}]*repeat\(2, minmax\(0, 1fr\)\)/)
  assert.match(css, /\.nav-grid[^}]*auto-fill, minmax\(var\(--control-height\), 1fr\)/)
  assert.match(css, /overflow-wrap: anywhere/)
  assert.match(css, /\.question-detail :deep\(pre\)[^}]*overflow: auto/)
  assert.match(read('./ExamTakingDialog.vue'), /100dvh/)
})

test('theory record loading retains server question order, saved answer mapping and existing API arguments', async () => {
  const calls = []
  const harness = examPage({
    getExamResult: async id => { calls.push(['result', id]); return { theory_exam: 6, exam_title: '真实正式测评', answers: [{ theory_question: 22, user_answer: '甲', is_correct: true, points_earned: 5 }] } },
    getTheoryExam: async id => { calls.push(['exam', id]); return { duration: 30 } },
    getTheoryQuestions: async id => { calls.push(['theory', id]); return theoryQuestions() },
    records: async () => { throw Error('Do not use a different record or unfiltered list to restore answers') },
  })
  assert.equal(harness.page.loading.value, true)
  await harness.page.loadExamInfo()
  assert.deepEqual(calls, [['result', 12], ['exam', 6], ['theory', 6]])
  assert.ok(harness.page.timeRemaining.value <= 30 * 60)
  assert.ok(harness.page.timeRemaining.value > 29 * 60)
  assert.deepEqual(plain(harness.page.questions.value.map(q => q.id)), [19, 5, 3])
  assert.equal(harness.page.answers.value[5].user_answer, '甲')
  assert.equal(harness.page.answeredCount.value, 1)
  assert.equal(harness.page.accuracyRate.value, 100)
  assert.equal(harness.page.loading.value, false)
  assert.equal(harness.page.examInfo.value.title, '真实正式测评')
})

test('keyboard-capable answer buttons and navigation retain single, multiple, judgement and first-unanswered operations', async () => {
  const harness = ready(examPage())
  const { page } = harness
  page.selectOption('选项二')
  assert.equal(page.isOptionSelected('选项二'), true)
  let rendered = await html(harness)
  assert.match(rendered, /<button[^>]*class="option-item selected"[^>]*aria-pressed="true"/)
  assert.match(rendered, /aria-label="第 1 题，已答，当前题"/)
  assert.match(rendered, /aria-current="step"/)
  assert.match(rendered, /经过清理的题面/)
  assert.ok(harness.sanitized.includes('<p>原始题面</p>'))
  page.nextQuestion()
  page.selectOption('甲'); page.selectOption('乙')
  assert.equal(page.answers.value[5].user_answer, '甲,乙')
  assert.equal(page.isOptionSelected('甲'), true)
  assert.equal(page.isOptionSelected('乙'), true)
  assert.equal(page.isOptionSelected('丙'), false)
  rendered = await html(harness)
  assert.equal((rendered.match(/class="option-item selected"[^>]*aria-pressed="true"/g) || []).length, 2)
  page.selectOption('甲')
  assert.equal(page.answers.value[5].user_answer, '乙')
  page.goToFirstUnanswered()
  assert.equal(page.currentQuestionIndex.value, 2)
  page.selectOption('正确')
  assert.equal(page.answers.value[3].user_answer, '正确')
  page.currentAnswer.value = '旧输入'; page.submissionResult.value = { is_correct: false }
  page.prevQuestion()
  assert.equal(page.currentQuestionIndex.value, 1)
  assert.equal(page.currentAnswer.value, '')
  assert.equal(page.submissionResult.value, null)
  page.goToQuestion(0)
  page.prevQuestion()
  assert.equal(page.currentQuestionIndex.value, 0)
  page.goToQuestion(2); page.nextQuestion()
  assert.equal(page.currentQuestionIndex.value, 2)
  assert.equal(page.hasUnanswered.value, false)
  rendered = await html(harness)
  assert.match(rendered, /disabled>跳转未答/)
})

test('theory submission sends original question IDs in order, opens confirmation, then transitions to practice only after confirm', async () => {
  const calls = []
  const harness = ready(examPage({
    submitAnswer: async (id, payload) => calls.push(['answer', id, plain(payload)]),
    submitExam: async id => calls.push(['submit', id]),
    getExamResult: async id => { calls.push(['result', id]); return { practice_record_id: 18 } },
  }))
  const { page } = harness
  page.selectOption('选项一'); page.goToQuestion(2); page.selectOption('错误')
  page.elapsedTime.value = 65.8
  page.submitExam()
  assert.equal(page.preparingSubmit.value, true)
  await flush()
  assert.deepEqual(calls, [
    ['answer', 12, { theory_question_id: 91, user_answer: '选项一', time_spent: 65 }],
    ['answer', 12, { theory_question_id: 80, user_answer: '错误', time_spent: 65 }],
  ])
  assert.equal(page.preparingSubmit.value, false)
  assert.equal(page.showSubmitDialog.value, true)
  assert.deepEqual(harness.routes, [])
  const rendered = await html(harness)
  assert.match(rendered, /还有 1 道题未答，确认提交吗？/)
  assert.match(rendered, /已用时间/)
  page.closeSubmitDialog()
  assert.equal(page.showSubmitDialog.value, false)
  await page.confirmSubmit()
  assert.deepEqual(calls.slice(-2), [['submit', 12], ['result', 12]])
  assert.deepEqual(harness.routes, ['/exam-taking/18'])
})

test('two selected choices stay selected after navigation and retain the original comma-joined submission payload', async () => {
  const calls = []
  const harness = ready(examPage({ submitAnswer: async (id, payload) => calls.push([id, plain(payload)]) }))
  const { page } = harness
  page.goToQuestion(1)
  page.selectOption('甲'); page.selectOption('乙')
  page.goToQuestion(0); page.goToQuestion(1)
  assert.equal(page.isOptionSelected('甲'), true)
  assert.equal(page.isOptionSelected('乙'), true)
  assert.equal(page.isOptionSelected('丙'), false)
  await page.submitAllTheoryAnswers()
  assert.deepEqual(calls, [[12, { theory_question_id: 22, user_answer: '甲,乙', time_spent: 0 }]])
})

test('practice loading, Flag submission, correctness feedback and original delayed advancement remain unchanged', async () => {
  const calls = []
  const questions = ready(examPage(), 'practice').page.questions.value
  let correct = false
  const harness = examPage({
    getExamResult: async () => ({ practice_exam: 9, exam_title: '实战测评', answers: [{ practice_question: 4, user_answer: 'flag{old}', is_correct: true, points_earned: 20 }] }),
    getPracticeQuestions: async id => { assert.equal(id, 9); return questions },
    submitAnswer: async (id, payload) => { calls.push([id, plain(payload)]); return { is_correct: correct, points_earned: correct ? 50 : 0 } },
  })
  const { page } = harness
  await page.loadExamInfo()
  assert.equal(page.examType.value, 'practice')
  assert.equal(page.answers.value[4].user_answer, 'flag{old}')
  await page.submitAnswer()
  assert.equal(calls.length, 0)
  page.currentAnswer.value = ' flag{test} '
  page.elapsedTime.value = 30.5
  await page.submitAnswer()
  assert.deepEqual(calls, [[12, { practice_question_id: 7, user_answer: 'flag{test}', time_spent: 30 }]])
  assert.equal(page.submissionResult.value.is_correct, false)
  assert.match(await html(harness), /答案错误，请重试/)
  correct = true
  await page.submitAnswer()
  assert.match(await html(harness), /答案正确！/)
  assert.equal(harness.delays[0].ms, 1500)
  harness.delays[0].callback()
  assert.equal(page.currentQuestionIndex.value, 1)
  assert.equal(page.currentAnswer.value, '')
  assert.equal(page.submissionResult.value, null)
  page.currentAnswer.value = 'flag{last}'
  await page.submitAnswer()
  harness.delays[1].callback()
  assert.equal(page.showSubmitDialog.value, true)
})

test('each theory/practice surface has only one filled main action; states have readable labels', async () => {
  for (const type of ['theory', 'practice']) {
    const harness = ready(examPage(), type)
    const rendered = await html(harness)
    const surface = rendered.replace(/<dialog[\s\S]*?<\/dialog>/g, '')
    assert.equal((surface.match(/class="btn btn-primary"/g) || []).length, 1)
    assert.match(surface, /上一题|下一题/)
    assert.match(surface, /剩余时间/)
    assert.match(surface, /role="timer" aria-live="off"/)
    if (type === 'practice') {
      assert.match(surface, /for="exam-flag"/)
      assert.match(surface, /id="exam-flag"/)
      assert.match(surface, /困难/)
      assert.doesNotMatch(surface, />hard</)
    }
    harness.page.timeRemaining.value = 299
    assert.match(await html(harness), /不足 5 分钟/)
    harness.page.timeRemaining.value = 59
    assert.match(await html(harness), /不足 1 分钟/)
  }
  const loading = examPage()
  assert.match(await html(loading), /role="status" aria-busy="true"/)
  loading.page.loading.value = false
  assert.match(await html(loading), /本场考试暂无题目/)
})

test('load failures retain original alert/return behavior without leaking internal server details', async () => {
  const harness = examPage({ getExamResult: async () => { throw Error('INTERNAL_SQL_DETAIL') } })
  await harness.page.loadExamInfo()
  assert.equal(harness.page.loading.value, false)
  assert.match(harness.alerts[0], /试炼场重试/)
  assert.doesNotMatch(harness.alerts[0], /INTERNAL_SQL_DETAIL/)
  assert.deepEqual(harness.routes, ['/exam-center'])
  const rendered = await html(harness)
  assert.match(rendered, /class="page-state load-error" role="alert"/)
  assert.doesNotMatch(rendered, /INTERNAL_SQL_DETAIL/)
})

test('request loading indicators release after failure and do not fabricate saved or successful answers', async () => {
  let reject
  const harness = ready(examPage({ submitAnswer: () => new Promise((_, fail) => { reject = fail }) }), 'practice')
  harness.page.currentAnswer.value = 'flag{test}'
  const pending = harness.page.submitAnswer()
  assert.equal(harness.page.submittingAnswer.value, true)
  assert.match(await html(harness), /disabled aria-busy="true">正在提交答案/)
  reject(Error('offline')); await pending
  assert.equal(harness.page.submittingAnswer.value, false)
  assert.equal(harness.page.answeredCount.value, 0)
  assert.equal(harness.page.submissionResult.value, null)
  assert.match(harness.alerts[0], /请重试/)
  const theory = ready(examPage({ submitAnswer: async () => { throw Error('offline') } }))
  theory.page.selectOption('选项一')
  await theory.page.submitAllTheoryAnswers()
  assert.equal(theory.page.preparingSubmit.value, false)
  assert.equal(theory.page.showSubmitDialog.value, false)
  assert.equal(theory.page.answers.value[19].user_answer, '选项一')
})

test('confirmed submission preserves result routes and failed final submission leaves the dialog available', async () => {
  for (const type of ['theory', 'practice']) {
    const harness = ready(examPage({ submitExam: async () => {}, getExamResult: async () => ({}) }), type)
    await harness.page.confirmSubmit()
    assert.deepEqual(harness.routes, ['/exam-center/result/12'])
    assert.equal(harness.page.submittingExam.value, false)
  }
  const failing = ready(examPage({ submitExam: async () => { throw Error('offline') } }))
  failing.page.showSubmitDialog.value = true
  await failing.page.confirmSubmit()
  assert.equal(failing.page.showSubmitDialog.value, true)
  assert.equal(failing.page.submittingExam.value, false)
  assert.deepEqual(failing.routes, [])
  assert.match(failing.alerts[0], /请重试/)
})

test('exit choices preserve cancel, return, abandonment API and failure behavior', async () => {
  const calls = []
  const harness = ready(examPage({ startComprehensiveExam: async payload => calls.push(plain(payload)) }))
  harness.page.exitExam()
  assert.equal(harness.page.showExitDialog.value, true)
  assert.match(await html(harness), /仅保留已提交的答案，尚未提交的选择不会保存/)
  harness.page.closeExitDialog()
  assert.equal(harness.page.showExitDialog.value, false)
  assert.deepEqual(calls, [])
  harness.page.exitWithoutAbandon()
  assert.deepEqual(harness.routes, ['/exam-center'])
  await harness.page.abandonAndExit()
  assert.deepEqual(calls, [{ abandon: true }])
  assert.deepEqual(harness.routes, ['/exam-center', '/exam-center'])
  const failure = ready(examPage({ startComprehensiveExam: async () => { throw Error('offline') } }))
  failure.page.exitExam()
  await failure.page.abandonAndExit()
  assert.equal(failure.page.showExitDialog.value, true)
  assert.equal(failure.page.abandoning.value, false)
  assert.deepEqual(failure.routes, [])
  assert.match(failure.alerts[0], /放弃考试失败/)
})

test('countdown cadence, elapsed time, expiry submission and unmount cleanup retain original behavior', async () => {
  const calls = []
  const harness = examPage({
    getExamResult: async () => ({ theory_exam: 6 }), getTheoryQuestions: async () => theoryQuestions(),
    records: async () => ({}), submitExam: async id => calls.push(id),
  })
  await harness.mounted[0]()
  assert.equal(harness.page.timeRemaining.value, 180 * 60)
  const interval = [...harness.intervals.values()][0]
  assert.equal(interval.ms, 1000)
  interval.callback()
  assert.equal(harness.page.timeRemaining.value, 180 * 60 - 1)
  assert.equal(harness.page.elapsedTime.value, 1)
  harness.page.timeRemaining.value = 0
  interval.callback()
  await flush()
  assert.deepEqual(calls, [12])
  assert.equal(harness.intervals.size, 0)
  assert.deepEqual(harness.routes, ['/exam-center/result/12'])
  const another = examPage({ getExamResult: async () => ({ theory_exam: 6 }), getTheoryQuestions: async () => [], records: async () => ({}) })
  await another.mounted[0]()
  another.unmounted[0]()
  assert.equal(another.intervals.size, 0)
})

test('reload uses the original start time and never resets the countdown or restores another record', async () => {
  const harness = examPage({
    getExamResult: async () => ({ theory_exam: 6, start_time: new Date(Date.now() - 120000).toISOString(), answers: [{ theory_question: 22, user_answer: '乙', is_correct: true }] }),
    getTheoryExam: async () => ({ duration: 30 }),
    getTheoryQuestions: async () => theoryQuestions(),
  })
  await harness.page.loadExamInfo()
  assert.equal(harness.page.elapsedTime.value, 120)
  assert.equal(harness.page.timeRemaining.value, 28 * 60)
  assert.equal(harness.page.answers.value[5].user_answer, '乙')
  assert.equal(harness.page.answers.value[19], undefined)
})

test('missing timing facts fail explicitly; completed records do not restart the timer or permit more answers', async () => {
  const missing = examPage({ getExamResult: async () => ({ theory_exam: 6 }), getTheoryExam: async () => ({}), getTheoryQuestions: async () => theoryQuestions() })
  await missing.mounted[0]()
  assert.ok(missing.page.loadError.value)
  assert.equal(missing.intervals.size, 0)
  const finished = examPage({ getExamResult: async () => ({ theory_exam: 6, status: 'completed' }) })
  await finished.mounted[0]()
  assert.deepEqual(finished.routes, ['/exam-center/result/12'])
  assert.equal(finished.intervals.size, 0)
})

test('page-local native modal synchronizes open/close without owning exam state and keeps keyboard cancel hooks', () => {
  const mounted = [], unmounted = [], watchers = [], calls = []
  const Modal = component('ExamTakingDialog', { vue: { ...Vue,
    onMounted: callback => mounted.push(callback), onBeforeUnmount: callback => unmounted.push(callback),
    watch: (getter, callback) => watchers.push(callback),
  } })
  const props = { open: false, title: '提交考试', titleId: 'exam-submit-heading' }
  const modal = Modal.setup(props, { expose() {}, emit() {} })
  modal.dialog.value = { open: false, showModal() { this.open = true; calls.push('open') }, close() { this.open = false; calls.push('close') } }
  mounted[0]()
  props.open = true; watchers[0]()
  assert.equal(modal.dialog.value.open, true)
  watchers[0]()
  assert.deepEqual(calls, ['open'])
  props.open = false; watchers[0]()
  assert.equal(modal.dialog.value.open, false)
  props.open = true; watchers[0]()
  unmounted[0]()
  assert.deepEqual(calls, ['open', 'close', 'open', 'close'])
  const template = compiled.ExamTakingDialog.descriptor.template.content
  assert.match(template, /<dialog[^>]*:aria-labelledby="titleId" aria-modal="true"/)
  assert.match(template, /@cancel.prevent="emit\('close'\)"/)
  assert.match(template, /@click.self="emit\('close'\)"/)
  assert.equal((source.match(/autofocus @click="close(?:Submit|Exit)Dialog"/g) || []).length, 2)
})

test('switching recordId reloads the paper and discards responses from the previous record', async () => {
  let releaseOld
  const calls = []
  const harness = examPage({
    getExamResult: async id => {
      calls.push(['result', id])
      if (id === 12) {
        return new Promise(resolve => { releaseOld = () => resolve({ theory_exam: 6, start_time: new Date().toISOString(), answers: [] }) })
      }
      return { theory_exam: 7, exam_title: '另一份卷子', start_time: new Date().toISOString(), answers: [{ theory_question: 22, user_answer: '乙', is_correct: true }] }
    },
    getTheoryExam: async id => ({ duration: 30 }),
    getTheoryQuestions: async id => id === 7
      ? [{ id: 40, question: 22, points: 5, question_detail: { question_type: 'single_choice', question_text: '新卷题面', options: ['甲', '乙'] } }]
      : theoryQuestions(),
  })
  const first = harness.page.loadExamInfo()
  await flush()
  // 换记录：新卷先完成，旧卷响应随后到达也不得覆盖。
  harness.params.id = 13
  harness.watchers[0].callback(13, 12)
  await flush()
  assert.equal(harness.page.examInfo.value.title, '另一份卷子')
  assert.deepEqual(plain(harness.page.questions.value.map(q => q.id)), [40])
  assert.equal(harness.page.answers.value[40].user_answer, '乙')
  releaseOld()
  await first
  await flush()
  assert.equal(harness.page.examInfo.value.title, '另一份卷子')
  assert.deepEqual(plain(harness.page.questions.value.map(q => q.id)), [40])
  assert.deepEqual(calls, [['result', 12], ['result', 13]])
})

test('time limit never pretends unsaved choices were submitted', async () => {
  const calls = []
  const harness = ready(examPage({ submitExam: async id => calls.push(['submit', id]), submitAnswer: async () => { throw Error('offline') } }))
  const { page } = harness
  page.selectOption('选项一')
  page.timeRemaining.value = 0
  await page.handleTimeUp()
  await flush()
  assert.deepEqual(calls, [])
  assert.match(page.timeoutNotice.value, /不会把未保存的答案当作已交卷/)
  assert.equal(page.answers.value[19].user_answer, '选项一')
  assert.equal(harness.intervals.size, 0)
  const rendered = await html(harness)
  assert.match(rendered, /exam-notice is-error/)
})

test('abandon re-reads the record and only leaves when the server confirms it is no longer in progress', async () => {
  let serverStatus = 'in_progress'
  const calls = []
  const harness = ready(examPage({
    startComprehensiveExam: async payload => { calls.push(plain(payload)); if (!payload?.abandon) throw Error('unexpected') },
    getExamResult: async () => ({ theory_exam: 6, status: serverStatus }),
  }))
  harness.page.exitExam()
  await harness.page.abandonAndExit()
  assert.deepEqual(calls, [{ abandon: true }])
  assert.deepEqual(harness.routes, [])
  assert.equal(harness.page.showExitDialog.value, true)
  assert.match(harness.page.submitError.value, /放弃可能未生效/)
  serverStatus = 'abandoned'
  await harness.page.abandonAndExit()
  assert.deepEqual(harness.routes, ['/exam-center'])
  assert.equal(harness.page.showExitDialog.value, false)
})
