import { shallowRef } from 'vue'

// Frontend isolation, not authorization: the server still checks every request.
export const accountScope = shallowRef({ identity: 'guest', role: 'guest', epoch: 0 })
const cleaners = new Set()
export function accountIdentity(user) {
  return user?.id != null && user?.role ? `${user.id}:${user.role}` : 'guest'
}
export function onAccountClear(clear) {
  cleaners.add(clear)
  return () => cleaners.delete(clear)
}
export function syncStateAccount(user, { force = false } = {}) {
  const identity = accountIdentity(user)
  if (!force && identity === accountScope.value.identity) return false
  accountScope.value = { identity, role: user?.role || 'guest', epoch: accountScope.value.epoch + 1 }
  for (const clear of cleaners) clear()
  return true
}
export function captureAccount() {
  const scope = accountScope.value
  return { key: `${scope.identity}:${scope.epoch}`, current: () => accountScope.value === scope }
}
export function createAccountGuard() {
  const account = captureAccount()
  let alive = true
  return { current: () => alive && account.current(), dispose: () => { alive = false } }
}
