import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { runInNewContext } from 'node:vm'
import * as Vue from 'vue'
import { renderToString } from 'vue/server-renderer'
import { parse, compileScript, compileTemplate, compileStyle } from 'vue/compiler-sfc'
import { asList, finiteNumber } from '../src/learning/contracts.js'

const require = createRequire(import.meta.url)
const icons = require('@arco-design/web-vue/lib/icon')
const read = file => readFileSync(new URL(file, new URL('../src/views/examTaking.test.js', import.meta.url)), 'utf8')
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
  app.component('RouterLink', { props: ['to'], template: '<a :href="to"><slot /></a>' })
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


const auditResults = {};
const callsExpired = [];
const expiry = ready(examPage({ submitAnswer: async (id, payload) => { callsExpired.push(['answer', id, payload]); throw Object.assign(new Error('expired'), {response: {status: 400, data: {code:'exam_time_expired'}}}); }, submitExam: async id => callsExpired.push(['submit', id]) }));
expiry.page.selectOption('选项一');
expiry.page.timeRemaining.value = 0;
await expiry.page.handleTimeUp();
auditResults.theoryExpiry = { apiCalls: callsExpired, alert: expiry.alerts, notice: expiry.page.timeoutNotice.value, resultRoute: expiry.routes };
const persistedAnswers = new Map();
const clearSaved = ready(examPage({submitAnswer: async (id, p) => { persistedAnswers.set(p.theory_question_id, p.user_answer); }, submitExam: async () => {}, getExamResult: async () => ({})}));
clearSaved.page.goToQuestion(1); clearSaved.page.selectOption('甲');
await clearSaved.page.submitAllTheoryAnswers(); clearSaved.page.closeSubmitDialog();
clearSaved.page.selectOption('甲');
await clearSaved.page.submitAllTheoryAnswers(); await clearSaved.page.confirmSubmit();
auditResults.deselectPreviouslySaved = { displayedAnsweredCount: clearSaved.page.answeredCount.value, persistedAnswers: [...persistedAnswers], resultRoute: clearSaved.routes };
const practiceDescription = ready(examPage(), 'practice');
practiceDescription.page.formatQuestion({id: 7, challenge: 101, challenge_title: '标题', challenge_description: '<p>实际题面：附件下载与测试环境说明</p>'});
auditResults.practiceDescription = { backendChallengeIsPrimaryKey: true, expectedDescription: '<p>实际题面：附件下载与测试环境说明</p>', actualRenderedInput: practiceDescription.sanitized };
console.log(JSON.stringify(auditResults, null, 2));
