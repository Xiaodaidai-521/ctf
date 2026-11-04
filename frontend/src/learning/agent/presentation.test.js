import test from 'node:test'
import assert from 'node:assert/strict'
import {
  TEACHING_STEPS, collaborationRecord, progressFrom, resourceView, speakerKey, speakerLabel, statusLine,
} from './presentation.js'

test('speaker labels use the real agent name and never expose internal ids', () => {
  assert.equal(speakerLabel({ role: 'user' }), '我')
  assert.equal(speakerLabel({ role: 'assistant', agentName: '教学辅导师' }), '教学辅导师')
  assert.equal(speakerLabel({ role: 'assistant', agentId: 'legal' }), '合规审查')
  assert.equal(speakerLabel({ role: 'assistant' }), '教学智能体')
  assert.equal(speakerKey({ role: 'assistant', agentId: 'tutor' }), 'tutor')
  assert.equal(speakerKey({ role: 'user' }), 'student')
})

test('progress uses only returned steps and never simulates by message count', () => {
  const none = progressFrom([{ role: 'user', content: '问题' }])
  assert.equal(none.available, false)
  assert.equal(none.label, '进度暂不可读取')
  assert.deepEqual(none.items.map(item => item.state), ['unknown', 'unknown', 'unknown', 'unknown'])
  const partial = progressFrom([
    { role: 'user', content: '问题' },
    { role: 'assistant', step: 1, stepName: '评估', content: '先检查' },
    { role: 'assistant', step: 2, content: '再讲解' },
  ])
  assert.equal(partial.available, true)
  assert.deepEqual(partial.items.map(item => item.state), ['done', 'current', 'pending', 'pending'])
  assert.deepEqual(TEACHING_STEPS, ['评估', '讲解', '练习', '检验'])
})

test('status lines are plain language, not tool names or JSON', () => {
  assert.equal(statusLine({ kind: 'handoff', to: '合规审查' }), '已转交：合规审查')
  assert.equal(statusLine({ kind: 'tool', summary: '正在准备教学资料' }), '正在准备教学资料')
  assert.equal(statusLine({ kind: 'tool' }), '正在准备教学资料')
  assert.equal(statusLine({ role: 'assistant' }), '')
})

test('collaboration record is honest about being metadata, not a full backup', () => {
  const record = collaborationRecord({
    transcript: [{ role: 'user', content: '问题' }, { role: 'assistant', content: '讲解', agentName: '教学辅导师' }],
    exportedAt: '2026-11-03T00:00:00.000Z',
  })
  assert.equal(record.title, '协作记录')
  assert.match(record.note, /不等同于完整对话备份/)
  assert.deepEqual(record.messages.map(item => item.speaker), ['我', '教学辅导师'])
  assert.equal(record.messages[0].content, '问题')
})

test('resource references distinguish empty from failure and keep real reasons', () => {
  const ready = resourceView([{ resource_id: 3, title: '讲义', reason: '和当前题目同一知识点' }])
  assert.equal(ready.state, 'ready')
  assert.equal(ready.items[0].id, 3)
  assert.equal(ready.items[0].reason, '和当前题目同一知识点')
  const empty = resourceView([])
  assert.equal(empty.state, 'empty')
  assert.match(empty.message, /没有匹配/)
  const failed = resourceView([], '资料暂时未能读取。')
  assert.equal(failed.state, 'error')
  assert.equal(failed.message, '资料暂时未能读取。')
})
