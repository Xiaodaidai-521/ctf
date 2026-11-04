import { accountScope, onAccountClear } from '../../shared/state/accountScope.js'
import { RETENTION_MS } from '../../shared/state/retention.js'

// Practice only: never used for a formal exam answer. Memory expires and resets per account epoch.
const drafts = new Map()
const key = (userId, challengeId) => `${accountScope.value.identity}:${accountScope.value.epoch}:${userId ?? 'guest'}:${challengeId}`
onAccountClear(clearAllDrafts)
export function readDraft(userId, challengeId) {
  const name = key(userId, challengeId), saved = drafts.get(name)
  if (!saved || Date.now() - saved.at >= RETENTION_MS) { drafts.delete(name); return '' }
  return saved.text
}
export function writeDraft(userId, challengeId, value) {
  const text = String(value ?? '')
  if (!text.trim()) drafts.delete(key(userId, challengeId))
  else drafts.set(key(userId, challengeId), { text, at: Date.now() })
}
export function clearDraft(userId, challengeId) { drafts.delete(key(userId, challengeId)) }
export function clearAllDrafts() { drafts.clear() }
export function draftCount() { return drafts.size }
