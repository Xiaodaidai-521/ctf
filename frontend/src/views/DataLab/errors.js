function messages(value) {
  if (typeof value === 'string') return [value]
  if (Array.isArray(value)) return value.flatMap(messages)
  if (value && typeof value === 'object') {
    return Object.entries(value).flatMap(([field, detail]) =>
      messages(detail).map(message => ['detail', 'message', 'non_field_errors'].includes(field) ? message : `${field}：${message}`),
    )
  }
  return []
}

export function readableError(error, fallback = '操作未完成，请重试当前步骤') {
  const data = error?.response?.data
  // A proxy's HTML error page is not an API validation message.
  if (data && typeof data === 'object') {
    const detail = messages(data.detail ?? data.message ?? data).join('；')
    if (detail) return detail
  }
  const status = error?.response?.status
  if (status === 401) return '登录已失效，请重新登录'
  if (status === 403) return '当前账号没有此操作权限'
  if (status === 404) return '记录不存在或当前账号无权访问，请刷新列表'
  if (status === 409) return '状态已变化，请刷新后重试'
  if (status >= 500) return '服务暂不可用，请稍后重试'
  if (error?.code === 'ECONNABORTED' || error?.code === 'ETIMEDOUT') return '请求超时，请重试当前步骤'
  if (error?.code === 'ERR_NETWORK' || (error?.request && !error?.response)) return '连接中断，请检查网络后重试'
  return error?.message || fallback
}
