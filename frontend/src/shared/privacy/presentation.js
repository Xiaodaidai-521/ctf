export function protectionView(status, label = '加密保存') {
  if (!status || status.storage === 'empty' || status.present === false || status.total === 0) return { visible: false }
  const state = status.storage
  if (state === 'encrypted') return { visible: true, confirmed: true, label,
    explanation: '对应内容在服务器中采用加密方式保存。查看与下载仍需通过访问权限检查；下载到本机后的文件需自行妥善保存。' }
  if (state === 'partial') return { visible: true, confirmed: false, label: '部分历史记录待处理',
    explanation: '部分记录已加密保存，仍有历史记录尚未完成迁移。' }
  return { visible: true, confirmed: false, label: '保护状态待确认',
    explanation: '暂未取得对应内容的完整加密保存核验结果。' }
}

export function profileUpdatePayload(form, originalEmail) {
  const payload = { ...form }
  const changed = typeof form.email === 'string' && form.email.trim() !== '' && form.email !== originalEmail
  if (!changed || form.email === '[REDACTED]' || form.email.includes('***')) delete payload.email
  return payload
}
