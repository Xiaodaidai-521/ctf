// Aborting transport is best effort; generation checks also reject already-resolved responses.
export function createRequestGeneration(isContextCurrent = () => true) {
  let generation = 0
  let disposed = false
  const requests = new Map()

  function invalidate() {
    generation += 1
    for (const controller of requests.values()) controller.abort()
    requests.clear()
  }

  return {
    begin(channel = 'page') {
      if (disposed) throw new Error('Request scope is disposed')
      requests.get(channel)?.abort()
      const controller = new AbortController()
      const issuedGeneration = generation
      requests.set(channel, controller)
      return {
        signal: controller.signal,
        isCurrent: () => !disposed && issuedGeneration === generation
          && requests.get(channel) === controller && !controller.signal.aborted
          && isContextCurrent(),
        finish() {
          if (requests.get(channel) === controller) requests.delete(channel)
        },
      }
    },
    invalidate,
    dispose() {
      disposed = true
      invalidate()
    },
  }
}

export function requestKey() {
  // UUID is 36 characters, under both API limits of 64.
  if (globalThis.crypto.randomUUID) return globalThis.crypto.randomUUID()
  return Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)),
    byte => byte.toString(16).padStart(2, '0')).join('')
}
