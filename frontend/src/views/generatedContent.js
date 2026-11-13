// 生成内容页的纯适配层：只读取后端四个 serializer 真实返回的字段。
// content_type/raw_content/mermaid_code/starter_code 对应原页面的类型/正文/图/代码；
// questions/language/hints 继续保留。旧字段 body/type/diagram_code/code 不再参与渲染。
import { finiteNumber } from '../learning/contracts.js'

const text = value => (value === null || value === undefined ? '' : String(value).trim())

export const CONTENT_META = Object.freeze({
  tutorial: { label: '教程', color: 'blue' },
  quiz: { label: '测验', color: 'orange' },
  diagram: { label: '图表', color: 'purple' },
  exercise: { label: '练习', color: 'green' },
})

function normalizeOptions(options) {
  return Array.isArray(options)
    ? options.map(option => text(option)).filter(option => option !== '')
    : []
}

// 生成器要求 answer 为选项字母（如 "B"），旧页面按数组下标比较会永远判错；
// 这里统一把字母、数字下标和完整选项文本折算为可比较的下标，无法判定时明确返回 null。
export function answerIndex(question) {
  const options = normalizeOptions(question?.options)
  const raw = question?.answer
  if (typeof raw === 'number' && Number.isInteger(raw) && raw >= 0 && raw < options.length) return raw
  if (typeof raw === 'string') {
    const value = raw.trim()
    if (/^[A-Za-z]$/.test(value)) {
      const index = value.toUpperCase().charCodeAt(0) - 65
      return index >= 0 && index < options.length ? index : null
    }
    if (/^\d+$/.test(value)) {
      const index = Number(value)
      return index >= 0 && index < options.length ? index : null
    }
    if (!value) return null
    const exact = options.findIndex(option => option === value)
    if (exact >= 0) return exact
    const prefixed = options.findIndex(option => option.toUpperCase().startsWith(`${value.toUpperCase()}.`))
    return prefixed >= 0 ? prefixed : null
  }
  return null
}

function normalizeQuestions(questions) {
  if (!Array.isArray(questions)) return []
  return questions
    .map(question => {
      const options = normalizeOptions(question?.options)
      const label = text(question?.question)
      if (!label || options.length < 2) return null
      return {
        question: label,
        options,
        answerIndex: answerIndex({ ...question, options }),
        explanation: text(question?.explanation),
      }
    })
    .filter(Boolean)
}

function normalizeHints(hints) {
  if (!Array.isArray(hints)) return []
  return hints
    .map(hint => {
      if (typeof hint === 'string') return hint.trim()
      if (hint && typeof hint === 'object') return text(hint.text ?? hint.hint ?? hint.content)
      return ''
    })
    .filter(Boolean)
}

export function contentView(source) {
  const raw = source || {}
  const type = text(raw.content_type)
  const meta = CONTENT_META[type] || { label: '内容', color: 'gray' }
  const body = typeof raw.raw_content === 'string' ? raw.raw_content : ''
  const questions = type === 'quiz' ? normalizeQuestions(raw.questions) : []
  return {
    id: finiteNumber(raw.id),
    title: text(raw.title) || '未命名内容',
    type,
    typeLabel: text(raw.content_type_display) || meta.label,
    typeColor: meta.color,
    rawContent: body,
    hasBody: body.trim() !== '',
    mermaidCode: type === 'diagram' ? text(raw.mermaid_code) : '',
    exercise: {
      language: text(raw.language),
      starterCode: typeof raw.starter_code === 'string' ? raw.starter_code : '',
      hints: normalizeHints(raw.hints),
    },
    questions,
    hasQuestions: questions.length > 0,
    knownType: CONTENT_META[type] !== undefined,
  }
}

// 测验只是本页练习：只对能判定的题目计分，未提供答案的题目明确不计入。
export function quizResult(questions, answers) {
  const list = Array.isArray(questions) ? questions : []
  const scorable = list.filter(question => question.answerIndex !== null)
  const correct = scorable.filter(question => {
    const qi = list.indexOf(question)
    const answer = answers?.[qi]
    return answer !== null && answer !== undefined && Number(answer) === question.answerIndex
  }).length
  if (!list.length) return { scorable: 0, correct: 0, label: '本测验暂未提供题目。' }
  if (!scorable.length) return { scorable: 0, correct: 0, label: '本测验没有可判定的答案，暂不计分；题目内容仍可阅读。' }
  const skipped = list.length - scorable.length
  return {
    scorable: scorable.length,
    correct,
    label: `本地判分：${correct} / ${scorable.length} 正确${skipped ? `；另有 ${skipped} 道题未提供可判定答案，未计入` : ''}。`,
  }
}

export function contentFailure(error) {
  const status = error?.response?.status
  if (status === 404) {
    return {
      notFound: true,
      title: '内容不存在或无权查看',
      message: '内容可能已删除、已下架，或不属于当前账号；请从原生成入口重新打开，或确认登录账号。',
    }
  }
  if (status === 403) {
    return { notFound: false, title: '当前账号无权查看', message: '这份生成内容没有向当前账号开放；请联系教师核对归属。' }
  }
  if (status === 401) {
    return { notFound: false, title: '登录状态已失效', message: '请重新登录后再打开这份生成内容；页面不会展示猜测内容。' }
  }
  return {
    notFound: false,
    title: '内容暂时无法读取',
    message: '读取生成内容时遇到问题，请稍后重试；页面不会用缓存或猜测内容代替。',
  }
}

export function regeneratedTarget(currentId, payload) {
  const id = finiteNumber(payload?.id)
  if (id === null) return { ok: false, id: null, changed: false, to: '' }
  const type = payload?.content_type
  const suffix = Object.hasOwn(CONTENT_META, type) ? `?content_type=${encodeURIComponent(type)}` : ''
  return { ok: true, id, changed: String(id) !== String(currentId), to: `/content/${id}${suffix}` }
}
