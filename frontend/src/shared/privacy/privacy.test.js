import test from 'node:test'
import assert from 'node:assert/strict'
import { protectionView, profileUpdatePayload } from './presentation.js'

test('only verified nonempty records display encryption success', () => {
  assert.equal(protectionView(undefined).visible, false)
  assert.equal(protectionView({ storage: 'empty' }).visible, false)
  assert.equal(protectionView({ storage: 'encrypted', total: 0 }).visible, false)
  assert.equal(protectionView({ storage: 'legacy' }).confirmed, false)
  assert.equal(protectionView({ storage: 'unknown' }).confirmed, false)
  assert.equal(protectionView({ storage: 'encrypted', present: true }).confirmed, true)
  assert.match(protectionView({ storage: 'partial' }).label, /部分历史/)
})

test('profile edits never submit masked, blank or unchanged email', () => {
  for (const email of ['', '[REDACTED]', 'zhang***@example.invalid', 'old@example.invalid']) {
    assert.deepEqual(profileUpdatePayload({ nickname: 'New name', email }, 'old@example.invalid'), { nickname: 'New name' })
  }
  assert.equal(profileUpdatePayload({ email: 'new@example.invalid' }, '[REDACTED]').email, 'new@example.invalid')
})
