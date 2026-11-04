import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  CONTENT_META, answerIndex, contentFailure, contentView, quizResult, regeneratedTarget,
} from './generatedContent.js'

const tutorial = {
  id: 11,
  title: 'SQL 注入基础',
  content_type: 'tutorial',
  content_type_display: '教程',
  raw_content: '# 目标\n先确认授权范围。',
  rendered_assets: {},
}

const quiz = {
  id: 12,
  title: '注入判断小测',
  content_type: 'quiz',
  content_type_display: '测验',
  raw_content: 'raw json',
  questions: [
    { question: '哪种做法先确认授权？', options: ['A. 直接扫描', 'B. 查看授权书', 'C. 扩大范围', 'D. 忽略范围'], answer: 'B', explanation: '授权优先。' },
    { question: '数字答案题', options: ['甲', '乙'], answer: 1 },
    { question: '无答案题', options: ['甲', '乙'] },
  ],
}

const diagram = {
  id: 13,
  title: '请求流程图',
  content_type: 'diagram',
  content_type_display: '图表',
  raw_content: '```mermaid\nflowchart LR\nA-->B\n```',
  mermaid_code: 'flowchart LR\nA-->B',
}

const exercise = {
  id: 14,
  title: '参数化查询练习',
  content_type: 'exercise',
  content_type_display: '练习',
  raw_content: 'raw assistant response',
  language: 'python',
  starter_code: 'query = ""\n# TODO',
  hints: ['先看参数绑定', { text: '再核对权限' }, '', null],
  solution_code: 'SECRET ANSWER',
  test_cases: [{ input: 'x', expected: 'y' }],
}

test('generated content reads real serializer fields for all four types', () => {
  const t = contentView(tutorial)
  assert.equal(t.type, 'tutorial')
  assert.equal(t.typeLabel, '教程')
  assert.equal(t.typeColor, CONTENT_META.tutorial.color)
  assert.equal(t.rawContent, tutorial.raw_content)
  assert.equal(t.hasBody, true)
  assert.equal(t.mermaidCode, '')
  assert.equal(t.knownType, true)

  const d = contentView(diagram)
  assert.equal(d.type, 'diagram')
  assert.equal(d.mermaidCode, 'flowchart LR\nA-->B')

  const e = contentView(exercise)
  assert.equal(e.exercise.language, 'python')
  assert.equal(e.exercise.starterCode, exercise.starter_code)
  assert.deepEqual(e.exercise.hints, ['先看参数绑定', '再核对权限'])
  assert.equal('solutionCode' in e.exercise, false)
  assert.equal(JSON.stringify(e).includes('SECRET ANSWER'), false)

  const q = contentView(quiz)
  assert.equal(q.questions.length, 3)
  assert.equal(q.questions[0].answerIndex, 1)
  assert.equal(q.questions[1].answerIndex, 1)
  assert.equal(q.questions[2].answerIndex, null)
  assert.equal(q.hasQuestions, true)
})

test('quiz answers accept the real letter format and do not score unknown answers', () => {
  assert.equal(answerIndex({ options: ['A. 甲', 'B. 乙'], answer: 'B' }), 1)
  assert.equal(answerIndex({ options: ['甲', '乙'], answer: 0 }), 0)
  assert.equal(answerIndex({ options: ['A. 甲', 'B. 乙'], answer: 'b' }), 1)
  assert.equal(answerIndex({ options: ['A. 甲', 'B. 乙'], answer: 'B. 乙' }), 1)
  assert.equal(answerIndex({ options: ['A. 甲', 'B. 乙'], answer: 'Z' }), null)
  assert.equal(answerIndex({ options: ['A. 甲'], answer: 'B' }), null)
  assert.equal(answerIndex({ options: [], answer: 'A' }), null)

  const questions = contentView(quiz).questions
  const result = quizResult(questions, { 0: 1, 1: 1 })
  assert.equal(result.scorable, 2)
  assert.equal(result.correct, 2)
  assert.match(result.label, /2 \/ 2 正确/)

  const missed = quizResult(questions, { 0: 1 })
  assert.equal(missed.correct, 1)
  assert.doesNotMatch(missed.label, /未计分/)

  // 题库没有可判定答案时明确不计分，不能假装 0/0 全是正确。
  const noAnswer = quizResult([{ question: 'q', options: ['甲', '乙'], answerIndex: null }], {})
  assert.equal(noAnswer.scorable, 0)
  assert.match(noAnswer.label, /没有可判定的答案/)
})

test('unknown content types keep the original body instead of pretending a layout', () => {
  const view = contentView({ id: 15, title: '', content_type: 'podcast', raw_content: '原始文本' })
  assert.equal(view.typeLabel, '内容')
  assert.equal(view.title, '未命名内容')
  assert.equal(view.knownType, false)
  assert.equal(view.hasBody, true)
})

test('content failures separate missing/permission/expired/service without backend text', () => {
  const notFound = contentFailure({ response: { status: 404 }, message: 'Request failed' })
  assert.equal(notFound.notFound, true)
  assert.match(notFound.title, /不存在或无权查看/)

  const forbidden = contentFailure({ response: { status: 403 } })
  assert.equal(forbidden.notFound, false)
  assert.match(forbidden.title, /无权查看/)

  const expired = contentFailure({ response: { status: 401 } })
  assert.match(expired.title, /登录状态/)

  const service = contentFailure({ response: { status: 500, data: { detail: 'INTERNAL_SQL_DETAIL' } } })
  assert.equal(service.notFound, false)
  assert.equal(JSON.stringify(service).includes('INTERNAL_SQL_DETAIL'), false)
})

test('regenerate keeps the current page when no new id, and targets the real new id otherwise', () => {
  assert.deepEqual(regeneratedTarget(12, { id: 12 }), { ok: true, id: 12, changed: false, to: '/content/12' })
  assert.deepEqual(regeneratedTarget(12, { id: 31 }), { ok: true, id: 31, changed: true, to: '/content/31' })
  assert.equal(regeneratedTarget(12, {}).ok, false)
  assert.equal(regeneratedTarget(12, null).ok, false)
})

test('page consumes the adapter, reloads on id change, and keeps legacy field access out', () => {
  const source = readFileSync(new URL('./GeneratedContent.vue', import.meta.url), 'utf8')
  assert.match(source, /contentView/)
  assert.match(source, /rawContent/)
  assert.match(source, /mermaidCode/)
  assert.match(source, /view\.exercise\.starterCode/)
  // MermaidDiagram 的真实 prop 是 mermaidCode；旧页传 code 会渲染空白。
  assert.match(source, /:mermaid-code="view\.mermaidCode"/)
  assert.doesNotMatch(source, /<MermaidDiagram[^>]*:code=/)
  assert.match(source, /watch\(\s*\(\) => route\.params\.id/)
  assert.match(source, /router\.replace\(target\.to\)/)
  assert.match(source, /本地练习，不计入正式测评/)
  assert.match(source, /不自动判题/)
  assert.doesNotMatch(source, /\bcontent\.(type|body|diagram_code|code|questions)\b/)
  assert.doesNotMatch(source, /flag\s*\{|submitFlag|提交 Flag/i)
})
