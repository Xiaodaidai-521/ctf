import test from 'node:test'
import assert from 'node:assert/strict'
import { protectionView, profileUpdatePayload, exportConfirmed } from './presentation.js'

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

test('export completion requires redaction, encryption and downloadable output', () => {
  const row = { state: 'generated', can_download: true, protection: { redaction: 'completed', storage: 'encrypted' } }
  assert.equal(exportConfirmed(row), true)
  assert.equal(exportConfirmed({ ...row, state: 'pending' }), false)
  assert.equal(exportConfirmed({ ...row, can_download: false }), false)
  assert.equal(exportConfirmed({ ...row, protection: { storage: 'encrypted' } }), false)
  assert.equal(exportConfirmed(null), false)
})
