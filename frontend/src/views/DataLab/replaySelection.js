export const replayVariants = Object.freeze(['A1', 'A2', 'A3', 'A4'])

export function currentReplays(replays, scan) {
  if (!scan?.scan_id || !scan?.profile_id) return []
  return (replays || []).filter(r => r.scan_id === scan.scan_id && r.profile_id === scan.profile_id)
}

// Attempt API returns creation order; timestamps also handle reordered responses.
// An unrevealed retry must not hide an earlier revealed round of the same variant.
export function latestRevealedReplays(replays, scan) {
  const latest = new Map()
  for (const replay of currentReplays(replays, scan)) {
    if (!replay.revealed || !replayVariants.includes(replay.scenario_variant)) continue
    const previous = latest.get(replay.scenario_variant)
    const time = Date.parse(replay.created_at)
    const previousTime = Date.parse(previous?.created_at)
    if (!previous || !Number.isFinite(time) || !Number.isFinite(previousTime) || time >= previousTime) {
      latest.set(replay.scenario_variant, replay)
    }
  }
  return replayVariants.map(variant => latest.get(variant)).filter(Boolean)
}
