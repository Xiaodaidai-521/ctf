const statuses = new Set([
  'submitted', 'deduplicating', 'duplicate', 'pending_fact_review', 'pending_evidence',
  'confirmed', 'rejected', 'handling', 'handled', 'reopened',
])

export function queueStatusPreset(value) {
  return typeof value === 'string' && statuses.has(value) ? value : ''
}
