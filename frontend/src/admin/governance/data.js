export const countValue = value => Number.isSafeInteger(value) && value >= 0 ? value : null
export const numberValue = value => {
  if (!['number', 'string'].includes(typeof value) || (typeof value === 'string' && !value.trim())) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}
export function listValue(data) {
  const rows = Array.isArray(data) ? data : data?.results
  if (!Array.isArray(rows) || rows.some(row => !row || typeof row !== 'object' || Array.isArray(row))) {
    throw new Error('Unreadable list')
  }
  return rows
}
export function listScope(data) {
  const rows = listValue(data)
  const total = countValue(data?.count ?? data?.total)
  return total === null ? `本次已读取 ${rows.length} 条` : `本次已读取 ${rows.length} 条，共 ${total} 条`
}
export function governanceError(error, writing = false) {
  const status = error?.response?.status
  if (status === 401) return '登录已失效，请重新登录。'
  if (status === 403) return '当前账号无法执行此操作，请核对授权。'
  if (status === 404) return '当前内容不可用，请重新读取或核对授权。'
  if (status === 409) return '记录已发生变化，请核对最新内容后再操作。'
  if (status === 400) return '提交未被接受，请核对所选对象和填写内容。'
  return writing ? '未能确认操作结果，请先核对最新记录，避免重复提交。' : '暂时无法读取，请重试；这不代表没有记录。'
}
export function dateLabel(value) {
  if (!value) return '未提供'
  const date = new Date(value)
  return Number.isFinite(date.getTime()) ? date.toLocaleString('zh-CN') : '日期待核对'
}
export const scoreLabel = value => {
  const number = numberValue(value)
  return number !== null && number >= 0 && number <= 100 ? `${number.toFixed(2)} 分` : '未提供'
}
export const directionLabel = key => ({ web: '网络安全', crypto: '密码学', pwn: '二进制安全', reverse: '逆向工程', forensics: '数字取证', misc: '综合杂项' }[key] || '其他方向')

// One refresh generation, independent sources; invalidated responses cannot repopulate another account.
export function createSourceController(sources, loaders, isAllowed = () => true) {
  let generation = 0
  let controller = null
  function clear() {
    ++generation
    controller?.abort()
    for (const source of Object.values(sources)) Object.assign(source, { data: null, error: '', loading: false })
  }
  return { clear, async load() {
    clear()
    if (!isAllowed()) return
    const token = generation
    controller = new AbortController()
    const signal = controller.signal
    for (const source of Object.values(sources)) source.loading = true
    await Promise.all(Object.entries(loaders).map(async ([key, loader]) => {
      const current = () => generation === token && !signal.aborted && isAllowed()
      try { const data = await loader(signal); if (current()) sources[key].data = data }
      catch (error) { if (current()) sources[key].error = governanceError(error) }
      finally { if (current()) sources[key].loading = false }
    }))
  } }
}
