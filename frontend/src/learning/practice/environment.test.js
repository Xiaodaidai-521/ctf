import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeEnvironment, countdown, phaseFor } from './environment.js'
import { createWorkspaceSession } from './workspaceSession.js'

// 环境状态只解释服务端字段：没有就绪证据就不给可用结论，没有到期时间就写“未提供”。
test('environment states map server fields without inventing readiness', () => {
  assert.deepEqual(normalizeEnvironment(null), { status: 'not_started', label: '未启动', running: false, accessUrl: '', expiresAt: null })
  assert.equal(normalizeEnvironment({ status: 'pending' }).label, '启动中')
  assert.equal(normalizeEnvironment({ status: 'stopped' }).label, '已停止')
  assert.equal(normalizeEnvironment({ status: 'destroyed' }).label, '已销毁')
  assert.equal(normalizeEnvironment({ status: 'error' }).label, '暂不可用')
  // 未知状态按未启动解释，不臆造运行中。
  const unknown = normalizeEnvironment({ status: 'whatever' })
  assert.equal(unknown.status, 'not_started')
  assert.equal(unknown.running, false)
  const running = normalizeEnvironment({ status: 'running', access_url: 'https://x.test/a', expires_at: '2026-11-03T12:00:00Z' })
  assert.equal(running.running, true)
  assert.equal(running.accessUrl, 'https://x.test/a')
  assert.equal(running.expiresAt, '2026-11-03T12:00:00Z')
  // is_running/is_expired 优先于 status 文本。
  assert.equal(normalizeEnvironment({ status: 'pending', is_running: true }).running, true)
  assert.equal(normalizeEnvironment({ status: 'running', is_expired: true }).expired, true)
})

test('countdown only interprets expires_at and says when it is missing', () => {
  assert.deepEqual(countdown(null, 0), { text: '未提供', seconds: null })
  assert.deepEqual(countdown('not-a-date', 0), { text: '未提供', seconds: null })
  assert.deepEqual(countdown('2026-11-03T12:00:00Z', Date.parse('2026-11-03T12:00:05Z')), { text: '已到期', seconds: 0 })
  assert.deepEqual(countdown('2026-11-03T12:30:00Z', Date.parse('2026-11-03T12:00:00Z')), { text: '30:00', seconds: 1800 })
  assert.deepEqual(countdown('2026-11-03T12:01:05Z', Date.parse('2026-11-03T12:00:00Z')), { text: '01:05', seconds: 65 })
})

test('phase only becomes ready with a running runtime and a real access URL', () => {
  assert.equal(phaseFor({ status: 'running', access_url: 'https://x.test/a' }), 'ready')
  assert.equal(phaseFor({ status: 'running' }), 'waiting')
  assert.equal(phaseFor({ status: 'running', is_expired: true, access_url: 'https://x.test/a' }), 'expired')
  assert.equal(phaseFor({ status: 'pending' }), 'waiting')
  assert.equal(phaseFor({ status: 'error' }), 'error')
  assert.equal(phaseFor({ status: 'stopped' }), 'idle')
  assert.equal(phaseFor(null), 'idle')
})

function make(apiClient, options = {}) {
  const scheduled = []
  return {
    session: createWorkspaceSession({
      apiClient, challengeId: 41, userId: 7,
      schedule: (fn, ms) => { scheduled.push({ fn, ms }); return scheduled.length },
      cancel: () => {}, now: () => Date.parse('2026-11-03T12:00:00Z'),
      ...options,
    }),
    scheduled,
  }
}

test('expired runtime is shown as expired with no countdown, and re-reading does not fake readiness', async () => {
  const { session } = make({ container: async () => ({ status: 'running', is_expired: true, access_url: 'https://x.test/a', expires_at: '2026-11-03T11:00:00Z' }) })
  await session.refreshEnvironment()
  assert.equal(session.environment.value.phase, 'expired')
  assert.equal(session.countdownText.value, '已到期')
  await session.refreshEnvironment()
  assert.equal(session.environment.value.phase, 'expired')
})

test('running runtime without expires_at says 未提供 and never fabricates a limit', async () => {
  const { session } = make({ container: async () => ({ status: 'running', access_url: 'https://x.test/a' }) })
  await session.refreshEnvironment()
  assert.equal(session.environment.value.phase, 'ready')
  assert.equal(session.countdownText.value, '未提供')
})

test('copy failure is reported without claiming the address was copied', async () => {
  const { session } = make({
    container: async () => ({ status: 'running', access_url: 'https://x.test/a' }),
    clipboard: { writeText: async () => { throw Error('denied') } },
  })
  await session.refreshEnvironment()
  const result = await session.copyAccess()
  assert.equal(result.ok, false)
  assert.equal(result.message, '复制失败，请手动复制访问地址。')
})

test('copy without an access URL does nothing', async () => {
  const { session } = make({ container: async () => ({ status: 'pending' }), clipboard: { writeText: async () => { throw Error('should not run') } } })
  await session.refreshEnvironment()
  assert.deepEqual(await session.copyAccess(), { ok: false })
})

test('stop failure keeps the running environment visible with honest feedback', async () => {
  const { session } = make({
    container: async () => ({ status: 'running', access_url: 'https://x.test/a' }),
    stopEnvironment: async () => { throw Error('offline') },
  })
  await session.refreshEnvironment()
  const result = await session.stopEnvironment()
  assert.equal(result.ok, false)
  assert.equal(result.message, '停止环境失败，请稍后重试。')
  assert.equal(session.environment.value.stopping, false)
  assert.equal(session.environmentStatus.value.accessUrl, 'https://x.test/a')
  assert.equal(session.environment.value.phase, 'ready')
})

test('explicit stop clears local runtime state and timers', async () => {
  const cancelled = []
  const { session, scheduled } = make({
    startEnvironment: async () => ({ success: true, container: { status: 'running', access_url: 'https://x.test/a', expires_at: '2026-11-03T12:30:00Z' } }),
    stopEnvironment: async () => ({ success: true, message: '已停止' }),
  }, { cancel: timer => cancelled.push(timer) })
  await session.startEnvironment()
  assert.equal(session.environment.value.phase, 'ready')
  assert.equal(scheduled.length, 1)
  const stopped = await session.stopEnvironment()
  assert.equal(stopped.ok, true)
  assert.equal(stopped.message, '已停止')
  assert.equal(session.environment.value.phase, 'idle')
  assert.equal(session.environment.value.info, null)
  assert.equal(session.countdownText.value, '未提供')
  // 停止后本轮倒计时定时器必须被取消，不能再在后台写状态。
  assert.deepEqual(cancelled, [1])
})

test('start refusal from the server keeps its message and does not poll', async () => {
  const { session, scheduled } = make({ startEnvironment: async () => ({ success: false, message: '环境额度已用完' }) })
  const result = await session.startEnvironment()
  assert.equal(result.ok, false)
  assert.equal(session.environment.value.error, '环境额度已用完')
  assert.equal(session.environment.value.phase, 'error')
  assert.equal(scheduled.length, 0)
})

test('polling does not overlap even when a status read is slow', async () => {
  let active = 0
  let maxActive = 0
  let resolveFirst
  let reads = 0
  const { session, scheduled } = make({
    startEnvironment: async () => ({ success: true, container: { status: 'pending' } }),
    container: async () => {
      reads += 1
      active += 1
      maxActive = Math.max(maxActive, active)
      if (reads === 1) {
        const value = await new Promise(resolve => { resolveFirst = resolve })
        active -= 1
        return value
      }
      active -= 1
      return { status: 'pending' }
    },
  }, { maxPolls: 3 })
  await session.startEnvironment()
  // 第一轮挂起期间不应排入下一轮；下一轮只在前一轮结束后再排队。
  const firstPoll = scheduled.shift()
  const polling = firstPoll.fn()
  assert.equal(scheduled.length, 0)
  resolveFirst({ status: 'pending' })
  await polling
  assert.equal(maxActive, 1)
  assert.equal(scheduled.length, 1)
})
