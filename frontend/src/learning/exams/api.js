import api from '@/api'
import { asList, finiteNumber } from '@/learning/contracts.js'

// 试炼场域 API：全部复用原 /api/exams/ 包装，不新增后端。
export const examsApi = {
  levelRules: () => api.exams.levelRules(),
  statistics: () => api.exams.statistics(),
  scoreTrend: () => api.exams.scoreTrend(),
  myHistory: () => api.exams.myHistory(),
  records: params => api.exams.records(params),
  startComprehensive: () => api.exams.startComprehensiveExam(),
  abandonComprehensive: () => api.exams.startComprehensiveExam({ abandon: true }),
  result: recordId => api.exams.getExamResult(recordId),
  theoryExam: id => api.exams.getTheoryExam(id),
  practiceExam: id => api.exams.getPracticeExam(id),
  theoryQuestions: id => api.exams.getTheoryQuestions(id),
  practiceQuestions: id => api.exams.getPracticeQuestions(id),
  submitAnswer: (recordId, data) => api.exams.submitAnswer(recordId, data),
  submitExam: recordId => api.exams.submitExam(recordId),
}

export const EXAM_TYPE_FILTERS = Object.freeze([
  { value: '', label: '全部类型' },
  { value: 'theory', label: '理论考试' },
  { value: 'practice', label: '实战考试' },
])

export const EXAM_STATUS_FILTERS = Object.freeze([
  { value: '', label: '全部状态' },
  { value: 'in_progress', label: '进行中' },
  { value: 'completed', label: '已完成' },
  { value: 'abandoned', label: '已放弃' },
  { value: 'timeout', label: '超时' },
  { value: 'pending', label: '未开始' },
])

export const RECORDS_PATH = '/exam-center/history'
export const RESULT_PATH = id => `/exam-center/result/${id}`

const TYPE_LABELS = Object.freeze({ theory: '理论考试', practice: '实战考试' })
const STATUS_LABELS = Object.freeze({
  in_progress: '进行中', pending: '未开始', completed: '已完成', abandoned: '已放弃', timeout: '已超时',
})

export function examTypeLabel(value) {
  return TYPE_LABELS[value] || '考试'
}

// 未知状态不猜成通过/失败，只标注“状态待确认”。
export function examStatusLabel(value) {
  return STATUS_LABELS[value] || '状态待确认'
}

// 等级规则字段是 minScore（大小写混合），按真实字段读取。
export function levelInfo(rules, score) {
  const list = asList(rules).slice().sort((a, b) => Number(a.minScore) - Number(b.minScore))
  // 平均成绩缺失（null/undefined/空串）不能当作 0 分落到最低等级。
  const total = finiteNumber(score)
  let current = null
  for (const rule of list) if (Number.isFinite(total) && total >= Number(rule.minScore)) current = rule
  const next = list.find(rule => !current || Number(rule.minScore) > Number(current.minScore)) || null
  return {
    current,
    next,
    remaining: next && Number.isFinite(total) ? Math.max(0, Math.ceil(Number(next.minScore) - total)) : null,
  }
}

// 等级进度只画当前级到下一级之间的真实得分，不补造默认等级。
export function levelView(rules, score) {
  const { current, next, remaining } = levelInfo(rules, score)
  const total = finiteNumber(score)
  if (!current && !next) return { known: false, current: null, next: null, remaining: null, percent: null, top: false }
  const floor = current ? Number(current.minScore) : null
  const ceiling = next ? Number(next.minScore) : null
  let percent = null
  if (total !== null && ceiling !== null && floor !== null && ceiling > floor) {
    percent = Math.max(0, Math.min(100, Math.round(((total - floor) / (ceiling - floor)) * 100)))
  } else if (total !== null && ceiling === null && floor !== null) {
    percent = 100
  }
  return { known: true, current, next, remaining, percent, top: Boolean(current && !next) }
}

// 记录状态只按真实值呈现；未完成不标失败，缺分显示“—”。
export function recordView(record) {
  const status = record?.status || ''
  const score = finiteNumber(record?.total_score ?? record?.score)
  const passedSource = record?.is_passed ?? record?.passed
  const date = record?.start_time || record?.created_at || record?.completed_at || null
  return {
    id: record?.id ?? null,
    title: record?.exam_title || record?.title || record?.exam?.title || '测评记录',
    type: record?.exam_type || '',
    typeLabel: record?.exam_type_display || record?.exam_type_label || examTypeLabel(record?.exam_type),
    date,
    status,
    statusLabel: examStatusLabel(status),
    passed: typeof passedSource === 'boolean' ? passedSource : null,
    score,
    totalPoints: finiteNumber(record?.total_points),
    questionCount: record?.total_questions ?? record?.question_count ?? null,
    durationSeconds: finiteNumber(record?.time_spent ?? record?.time_spent_seconds ?? record?.duration_seconds),
    correctCount: finiteNumber(record?.correct_count),
    href: record?.id != null ? RESULT_PATH(record.id) : null,
    protection: record?.protection || null,
  }
}

// 结果里的理论/实战字段是主键；只有对象形态才可能带 pass_score。
export function resultView(payload) {
  if (!payload) return null
  const theoryExam = payload.theory_exam
  const practiceExam = payload.practice_exam
  const theoryExamId = typeof theoryExam === 'object' ? theoryExam?.id ?? null : theoryExam ?? null
  const practiceExamId = typeof practiceExam === 'object' ? practiceExam?.id ?? null : practiceExam ?? null
  // 结果接口的逐题记录字段是 answers；兼容仅提供 questions 形状时同样归一。
  const source = asList(payload.answers).length ? asList(payload.answers) : asList(payload.questions || payload.question_results)
  const answers = source.map(item => ({
    ...item,
    questionRef: item.theory_question ?? item.practice_question ?? item.question_id ?? null,
    stem: item.question_text ?? item.stem ?? item.question?.content ?? '',
    answer: item.user_answer ?? item.answer ?? null,
    // 只采用服务端返回的答案字段；不借其他接口补取正确答案。
    correctAnswer: item.correct_answer ?? item.correctAnswer ?? null,
    score: finiteNumber(item.points_earned ?? item.score),
    maxScore: finiteNumber(item.max_score ?? item.points ?? item.question_points),
    correct: typeof item.is_correct === 'boolean' ? item.is_correct : null,
  }))
  return {
    ...payload,
    // DRF 把 DecimalField 序列化为字符串；展示层统一转成数字，缺值仍是 null。
    score: finiteNumber(payload.score),
    total_points: finiteNumber(payload.total_points),
    correct_count: finiteNumber(payload.correct_count),
    time_spent: finiteNumber(payload.time_spent),
    totalPoints: finiteNumber(payload.total_points),
    correctCount: finiteNumber(payload.correct_count),
    timeSpent: finiteNumber(payload.time_spent),
    theoryExamId,
    practiceExamId,
    practiceRecordId: payload.practice_record_id ?? null,
    theoryRecordId: payload.theory_record_id ?? null,
    passScore: finiteNumber(payload.pass_score ?? (typeof theoryExam === 'object' ? theoryExam?.pass_score : null) ?? (typeof practiceExam === 'object' ? practiceExam?.pass_score : null)),
    answers,
    questions: answers,
  }
}

// 通过条件只陈述后台已判定的结果；及格线缺失时不填默认 60。
export function passCondition(view) {
  if (!view) return { known: false, text: '待判定' }
  if (view.is_passed === true) return { known: true, text: view.passScore === null ? '已通过（后台判定）' : `已通过（及格线 ${view.passScore} 分）` }
  if (view.is_passed === false) return { known: true, text: view.passScore === null ? '未通过（后台判定）' : `未通过（及格线 ${view.passScore} 分）` }
  return { known: false, text: '待判定' }
}

// 统计接口在没有任何已完成记录时返回 0；0 分与“没有数据”不是一回事，不能显示 0.0%。
export function statPercent(value, totalExams) {
  const sample = finiteNumber(totalExams)
  if (sample === null || sample <= 0) return '—'
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)}%` : '—'
}

export function accuracy(correct, total) {
  const a = finiteNumber(correct)
  const b = finiteNumber(total)
  if (a === null || b === null || b <= 0) return null
  return Math.round((a / b) * 100)
}

export function formatDuration(seconds) {
  const value = finiteNumber(seconds)
  if (value === null || value < 0) return '—'
  const whole = Math.floor(value)
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  if (hours > 0) return `${hours}小时${minutes}分`
  if (minutes > 0) return `${minutes}分${whole % 60}秒`
  return `${whole}秒`
}

// 理论卷：试卷题目条目 id 与原始题目 id 不是同一个值。保存答案要用原始题目 `question`，
// 结果里的 theory_question 也按原始题目返回，页面展示与已答状态则按试卷条目 id 归位。
export function theoryQuestionRef(item) {
  const value = finiteNumber(item?.question ?? item?.theory_question_id ?? item?.question_id)
  return value
}

// 实战卷：保存答案使用实战试卷题目关联 id（PracticeExamQuestion.id）。
export function practiceQuestionRef(item) {
  return finiteNumber(item?.id)
}

export function theoryExamId(record) {
  const value = record?.theory_exam
  if (value === null || value === undefined || value === '') return null
  return finiteNumber(typeof value === 'object' ? value?.id : value)
}

export function savedAnswerRef(theory, answer) {
  return theory ? finiteNumber(answer?.theory_question) : finiteNumber(answer?.practice_question)
}

// 记录区筛选写回 URL，刷新与分享后保持同一筛选。
export function parseRecordQuery(query = {}) {
  const type = EXAM_TYPE_FILTERS.some(item => item.value === query.type) ? query.type : ''
  const status = EXAM_STATUS_FILTERS.some(item => item.value === query.status) ? query.status : ''
  return { type, status }
}

export function recordQuery({ type = '', status = '' } = {}) {
  const params = new URLSearchParams()
  if (type) params.set('type', type)
  if (status) params.set('status', status)
  const text = params.toString()
  return text ? `?${text}` : ''
}

export function recordsHref({ type = '', status = '' } = {}) {
  return `${RECORDS_PATH}${recordQuery({ type, status })}`
}

export function filterRecords(list, { type = '', status = '' } = {}) {
  return asList(list).filter(record => (!type || record?.exam_type === type) && (!status || record?.status === status))
}
