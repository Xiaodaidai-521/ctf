import { landingFor } from './names.js'

// Only application paths can be carried through login; auth/error pages would loop.
export function safeReturnPath(value) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000-\u001f\u007f]/.test(value)) return null
  try {
    const url = new URL(value, 'https://app.invalid')
    const path = decodeURIComponent(url.pathname)
    if (url.origin !== 'https://app.invalid' || path.startsWith('//') || /[\\\u0000-\u001f\u007f]/.test(path)) return null
    if (/^\/(?:login|register|access-denied)(?:\/|$)/i.test(path)) return null
    return value
  } catch { return null }
}

export function loginDestination(returnTo) {
  const redirect = safeReturnPath(returnTo)
  return { path: '/login', query: redirect ? { redirect } : {} }
}

export function loginUrl(returnTo) {
  const { query } = loginDestination(returnTo)
  return query.redirect ? `/login?${new URLSearchParams(query)}` : '/login'
}

export function loginReturnDestination(returnTo, router, role, canOpen) {
  const fallback = landingFor(role)
  const path = safeReturnPath(returnTo)
  if (!path) return fallback
  try {
    const resolved = router.resolve(path)
    if (!resolved.matched.length || resolved.name === 'NotFound' || !canOpen(resolved.meta, role)) return fallback
    return path
  } catch { return fallback }
}
