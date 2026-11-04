import test from 'node:test'
import assert from 'node:assert/strict'
import {
  CARD_FIELDS, CARD_REQUIRED, cardDraft, cardMissing, cardPayload, cardResult, claimTarget,
  disputeKey, disputePayload, disputeResult, disputeView, errorText, retestView, submissionView,
} from './reviewActions.js'

const submission = {
  submission_id: 's-1',
  task: { title: '隔离验收任务', version_label: 'v2', track_label: '网络安全' },
  submitted_at: '2026-11-03T02:00:00Z',
  overall_status: 'passed',
  overall_status_label: '通过',
  program_status_label: '通过',
  manual_status_label: '已评分',
  assistance: { independence_label: '独立完成', answer_exposure: true },
  save_status_label: '保存成功',
  verification_note: '程序核验通过。',
  items: [
    { label: '证据', kind_label: '程序核验', status: 'passed', status_label: '通过', score: 2, max_points: 2 },
    { label: '依据', kind_label: '人工评阅', status: 'scored', status_label: '已评分', score: 1, max_points: 2 },
  ],
  total_score: 3,
  max_total_score: 8,
  review_remarks: '依据需要补充出处。',
  result_version: 2,
  corrected: true,
}

test('submission keeps every verification field instead of a single score', () => {
  const view = submissionView(submission)
  assert.equal(view.taskTitle, '隔离验收任务')
  assert.equal(view.versionLabel, 'v2')
  assert.equal(view.programLabel, '通过')
  assert.equal(view.manualLabel, '已评分')
  assert.equal(view.independenceLabel, '独立完成')
  assert.equal(view.answerExposure, true)
  assert.equal(view.note, '程序核验通过。')
  assert.equal(view.items.length, 2)
  assert.deepEqual(view.items[1], {
    label: '依据', kindLabel: '人工评阅', status: 'scored', statusLabel: '已评分',
    score: 1, maxPoints: 2, reason: '',
  })
  assert.equal(view.totalScore, 3)
  assert.equal(view.maxTotalScore, 8)
  assert.equal(view.remarks, '依据需要补充出处。')
  assert.equal(view.corrected, true)
  assert.equal(submissionView({}), null)
})

test('card draft restores all six fields and keeps the generated summary', () => {
  const view = submissionView(submission)
  const empty = cardDraft(view, null)
  assert.equal(empty.readOnly, false)
  assert.equal(empty.values.original_task_summary, '隔离验收任务 · v2')
  assert.equal(empty.values.error_evidence, '')
  assert.deepEqual(Object.keys(empty.values), CARD_REQUIRED)
  assert.equal(CARD_FIELDS.length, 6)

  const saved = cardDraft(view, {
    status: 'draft', status_label: '草稿', original_task_summary: '我写的摘要',
    error_evidence: '漏看范围', judgment_at_time: '默认可用', correct_basis: '先读授权',
    next_verification: '重放请求', student_reflection: '先写范围', completed_at: null,
  })
  assert.equal(saved.values.original_task_summary, '我写的摘要')
  assert.equal(saved.values.next_verification, '重放请求')
  assert.equal(saved.statusLabel, '草稿')
  assert.equal(saved.readOnly, false)

  const completed = cardDraft(view, {
    status: 'completed', status_label: '已完成', completed_at: '2026-11-03T03:00:00Z',
    original_task_summary: '摘要', error_evidence: '证据', judgment_at_time: '判断',
    correct_basis: '依据', next_verification: '验证', student_reflection: '反思',
    teacher_confirmation: '教师已确认',
  })
  assert.equal(completed.readOnly, true)
  assert.equal(completed.teacherConfirmation, '教师已确认')
})

test('completion requires all six real fields; payload trims and flags complete', () => {
  const values = {
    original_task_summary: ' 摘要 ', error_evidence: '证据 ', judgment_at_time: '判断',
    correct_basis: '依据', next_verification: '验证', student_reflection: ' ',
  }
  assert.deepEqual(cardMissing(values), ['我的反思'])
  assert.deepEqual(cardPayload(values, false), {
    original_task_summary: '摘要', error_evidence: '证据', judgment_at_time: '判断',
    correct_basis: '依据', next_verification: '验证', student_reflection: '', complete: false,
  })
  assert.equal(cardMissing({ ...values, student_reflection: '反思' }).length, 0)
})

test('card result speaks from the backend retest payload', () => {
  const draft = cardResult({ review_card: { status: 'draft' } }, false)
  assert.equal(draft.completed, false)
  assert.match(draft.message, /草稿已保存/)

  const withRetest = cardResult({
    review_card: { status: 'completed' },
    retest: { task: { title: '新场景' }, due_at: '2026-11-06T02:00:00Z' },
  }, true)
  assert.equal(withRetest.completed, true)
  assert.equal(withRetest.retest.task.title, '新场景')
  assert.match(withRetest.message, /新场景/)

  const noTask = cardResult({ review_card: { status: 'completed' }, retest: { task: null } }, true)
  assert.match(noTask.message, /等待补题/)
})

test('retest list keeps status, due date, version, outcome and pending item', () => {
  const due = retestView({
    assignment_id: 'a-1', status: 'due', status_label: '已到期',
    task: { title: '新场景', version_label: 'v3' }, due_at: '2026-11-06T02:00:00Z',
    original_task_title: '原任务', outcome_label: '', note: '教师调整说明',
  })
  assert.equal(due.statusLabel, '已到期')
  assert.equal(due.taskTitle, '新场景')
  assert.equal(due.versionLabel, 'v3')
  assert.notEqual(due.dueLabel, '—')
  assert.equal(due.originalTaskTitle, '原任务')
  assert.equal(due.note, '教师调整说明')
  assert.equal(due.claimable, true)
  assert.equal(due.claimLabel, '领取复测')

  const pending = retestView({ assignment_id: 'a-2', status: 'pending_item', task: null })
  assert.equal(pending.pendingItem, true)
  assert.equal(pending.claimable, false)
  assert.equal(pending.statusLabel, '待补题')

  const inProgress = retestView({ assignment_id: 'a-3', status: 'in_progress', task: { title: '新场景' } })
  assert.equal(inProgress.claimable, true)
  assert.equal(inProgress.claimLabel, '继续复测')
  assert.equal(retestView({}), null)
})

test('claim target uses the returned attempt, task, created flag and note', () => {
  const created = claimTarget({
    attempt_id: 'attempt-9', task: { title: '新场景', version_label: 'v3' }, created: true,
    note: '复测默认无提示完成；实际使用帮助会记为受助。',
  })
  assert.equal(created.available, true)
  assert.equal(created.attemptId, 'attempt-9')
  assert.equal(created.created, true)
  assert.equal(created.taskTitle, '新场景')
  assert.equal(created.versionLabel, 'v3')
  // 没有已存在的练习工作面时如实说明，不跳证据页、不假定 DataLab。
  assert.equal(created.path, null)
  assert.equal(created.unresolved, true)
  assert.match(created.reason, /G08/)
  assert.match(created.message, /attempt-9/)
  assert.match(created.note, /无提示/)

  const existing = claimTarget({ attempt_id: 'attempt-9', task: { title: '新场景' }, created: false })
  assert.equal(existing.created, false)
  assert.equal(existing.unresolved, true)
  assert.match(existing.message, /未重复创建/)

  const missing = claimTarget({ task: { title: '新场景' }, created: true })
  assert.equal(missing.available, false)
  assert.match(missing.reason, /无法核对/)
})

test('dispute key is stable across retries and result is idempotent', () => {
  assert.equal(disputeKey('s-1', 'seed-7'), 'd-s-1-seed-7')
  assert.equal(disputeKey('s-1', 'seed-7'), disputeKey('s-1', 'seed-7'))
  assert.deepEqual(disputePayload(' 分数不对 ', disputeKey('s-1', 'seed-7')), {
    client_dispute_id: 'd-s-1-seed-7', reason: '分数不对',
  })
  const first = disputeResult({ status: 'submitted', status_label: '已提交', created: true })
  assert.equal(first.created, true)
  assert.match(first.message, /已提交/)
  const repeat = disputeResult({ status: 'submitted', status_label: '已提交', created: false })
  assert.equal(repeat.created, false)
  assert.match(repeat.message, /未重复创建/)
})

test('own dispute list shows status and resolution', () => {
  const view = disputeView({
    dispute_id: 'd-1', task_title: '隔离验收任务', reason: '依据评分过低', status: 'resolved',
    status_label: '已解决', resolution: '已建立更正版本。', created_at: '2026-11-03T02:00:00Z',
    resolved_at: '2026-11-03T04:00:00Z',
  })
  assert.equal(view.statusLabel, '已解决')
  assert.equal(view.resolution, '已建立更正版本。')
  assert.notEqual(view.resolvedLabel, '—')
  assert.equal(disputeView({}), null)
})

test('error text surfaces backend detail and falls back honestly', () => {
  assert.equal(errorText({ response: { data: { detail: '复盘卡已完成，不能改写。' } } }), '复盘卡已完成，不能改写。')
  assert.equal(errorText({ response: { data: { detail: { code: 'x', detail: '版本已变化' } } } }), '版本已变化')
  assert.equal(errorText({ response: { data: { reason: '字段不能为空' } } }), '字段不能为空')
  assert.equal(errorText({}), '网络或服务异常，操作未完成。')
})
