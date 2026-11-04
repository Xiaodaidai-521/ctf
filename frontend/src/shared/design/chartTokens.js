export function tokenValue(name, element = globalThis.document?.documentElement) {
  if (!element || typeof globalThis.getComputedStyle !== 'function') return ''
  return globalThis.getComputedStyle(element).getPropertyValue(`--${name}`).trim()
}

export function tokenNumber(name, element) {
  return Number.parseFloat(tokenValue(name, element))
}

export function sequentialColor(value, element) {
  const amount = Math.max(0, Math.min(1, Number(value) || 0))
  const colors = ['sequence-low', 'sequence-high'].map(name => tokenValue(name, element))
  if (colors.some(color => !/^#[\da-f]{6}$/i.test(color))) return tokenValue('ink', element)
  const channels = [1, 3, 5].map(offset => {
    const low = Number.parseInt(colors[0].slice(offset, offset + 2), 16)
    const high = Number.parseInt(colors[1].slice(offset, offset + 2), 16)
    return Math.round(low + (high - low) * amount)
  })
  return `rgb(${channels.join(', ')})`
}
