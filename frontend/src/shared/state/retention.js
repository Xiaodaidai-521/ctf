import { accountScope, captureAccount, onAccountClear } from './accountScope.js'

export const RETENTION_MS = 15 * 60 * 1000
const snapshots = new Map()
const storageDomains = new Map()
onAccountClear(() => { snapshots.clear(); storageDomains.clear() })

// Only caller-selected UI fields belong here, never API payloads or arbitrary forms.
export function uiSnapshot(domain, role = accountScope.value.role, now = () => Date.now()) {
  const account = captureAccount()
  const key = `${account.key}:${role}:${domain}`
  const allowed = () => account.current() && accountScope.value.role === role && role !== 'guest'
  return {
    read() {
      const saved = snapshots.get(key)
      if (!allowed() || !saved || now() - saved.at >= RETENTION_MS) { snapshots.delete(key); return null }
      return structuredClone(saved.value)
    },
    write(value) {
      if (!allowed()) return
      snapshots.set(key, { at: now(), value: structuredClone(value) })
    },
  }
}

// Legacy preference adapters can use Storage's API without writing to the browser.
export function accountMemoryStorage(domain, now = () => Date.now()) {
  const account = captureAccount()
  const key = `${account.key}:${domain}`
  if (!storageDomains.has(key)) storageDomains.set(key, new Map())
  const values = storageDomains.get(key)
  return {
    getItem: name => {
      const saved = values.get(name)
      if (!account.current() || !saved || now() - saved.at >= RETENTION_MS) { values.delete(name); return null }
      return saved.value
    },
    setItem: (name, value) => { if (account.current()) values.set(name, { value: String(value), at: now() }) },
    removeItem: name => values.delete(name),
  }
}
