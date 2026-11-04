let pending = null
const listeners = new Set()
export function queueDraft(prompt, userId) {
  pending = prompt.trim() ? { prompt: prompt.trim(), userId } : null
  for (const listener of listeners) listener()
}
export function takeDraft(userId) {
  const draft = pending
  pending = null
  return draft?.userId === userId ? draft?.prompt || '' : ''
}
export function subscribeDraft(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
export function clearDraft() { pending = null }
