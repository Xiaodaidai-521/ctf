import { governancePage } from './governance.js'

const MAX_VISITS = 8
export function createRecentVisits(storage) {
  let identity = ''
  let visits = []
  const key = () => `governance-visits:${identity}`
  function save() {
    try { storage?.setItem(key(), JSON.stringify(visits)) } catch { /* 浏览器禁用存储时仍保留当前会话。 */ }
  }
  return {
    account(userId, role) {
      const next = role === 'admin' && userId != null ? String(userId) : ''
      if (next === identity) return this.list()
      if (identity) { try { storage?.removeItem(key()) } catch { /* 退出仍清空内存。 */ } }
      identity = next
      visits = []
      if (identity) {
        try {
          const saved = JSON.parse(storage?.getItem(key()) || '[]')
          if (Array.isArray(saved)) visits = [...new Set(saved.filter(path => typeof path === 'string' && governancePage(path)?.path === path))].slice(0, MAX_VISITS)
        } catch { /* 损坏或不可用的记录不进入界面。 */ }
      }
      return this.list()
    },
    record(path) {
      const page = identity && governancePage(path)
      if (page) { visits = [page.path, ...visits.filter(item => item !== page.path)].slice(0, MAX_VISITS); save() }
      return this.list()
    },
    list() { return identity ? visits.map(path => governancePage(path)).filter(Boolean) : [] },
    clear() { visits = []; if (identity) { try { storage?.removeItem(key()) } catch { /* 清空当前内存已生效。 */ } } return [] },
  }
}
