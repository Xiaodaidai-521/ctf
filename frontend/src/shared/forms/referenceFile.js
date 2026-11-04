const forbiddenKeys = new Set(['__proto__', 'prototype', 'constructor'])

export function downloadRecord(value, filename = '核查资料.json') {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function parseReferenceFile(text, fields) {
  if (text.length > 1024 * 1024) throw new Error('文件过大，请使用下载的格式模板。')
  let data
  try { data = JSON.parse(text) } catch { throw new Error('文件格式不正确，请使用下载的格式模板。') }
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('请使用下载的格式模板填写资料。')
  const names = new Set(fields.map(field => field.key))
  if (Object.keys(data).some(key => forbiddenKeys.has(key) || !names.has(key))) throw new Error('文件包含不支持的内容，请使用下载的格式模板。')
  const result = {}
  for (const field of fields) {
    const value = data[field.key] ?? (field.type === 'list' ? [] : '')
    if (field.type === 'list') {
      if (!Array.isArray(value) || value.some(item => typeof item !== 'string' || item.length > 2000)) throw new Error(`${field.label}内容不正确。`)
      result[field.key] = value
    } else if (field.type === 'number') {
      if (value !== '' && ((typeof value !== 'number' && (typeof value !== 'string' || !/^[1-9]\d*$/.test(value))) || !Number.isSafeInteger(Number(value)) || Number(value) <= 0)) throw new Error(`${field.label}内容不正确。`)
      result[field.key] = value === '' ? '' : Number(value)
    } else {
      if (typeof value !== 'string' || value.length > 2000) throw new Error(`${field.label}内容不正确。`)
      result[field.key] = value
    }
  }
  return result
}
