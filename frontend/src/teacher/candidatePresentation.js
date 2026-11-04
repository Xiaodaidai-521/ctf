export function configurationVersionLabel(value) {
  if (!value) return '未指定版本'
  const version = String(value).replace(/-candidate\b/g, '（候选）')
  if (/^(?:v)?\d+(?:[.-]\d+)*(?:（候选）)?$/i.test(version)) return version
  if (/[㐀-鿿]/.test(version) && !/[a-z]+_[a-z]|[0-9a-f]{8}-/i.test(version)) return version
  return '已关联版本，完整名称可下载核对'
}

export function changedFactorLabel(value) {
  if (value === 'export_record_limit') return '记录数量上限'
  if (!value) return '未指定改动因素'
  if (/[㐀-鿿]/.test(value) && !/[a-z]+_[a-z]/i.test(value)) return value
  return '已关联改动因素，完整内容可下载核对'
}

export function approvalReasonLabel(value) {
  const reasons = new Set([
    '没有审批记录。', '候选配置在审批后已变化，旧审批失效。',
    '基准配置在审批后已变化，旧审批失效。', '评测报告已变化，旧审批失效。',
    '评测报告内容已变化，旧审批失效。',
  ])
  return reasons.has(value) ? value : '审批依据未通过核查，请核对配置与评测报告；完整原因可下载核对。'
}
