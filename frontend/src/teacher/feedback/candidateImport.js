// Imports retain the source payload. Shape checks are not proof of evaluation:
// permissions, report provenance, digests and transitions remain server-owned.
const forbidden = new Set(['__proto__', 'prototype', 'constructor'])
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const text = (value, max) => typeof value === 'string' && Boolean(value.trim()) && value.length <= max
const strings = value => Array.isArray(value) && value.every(item => text(item, 2000))
function safe(value) {
  if (Array.isArray(value)) return value.every(safe)
  if (object(value)) return Object.entries(value).every(([key, item]) => !forbidden.has(key) && safe(item))
  return typeof value !== 'number' || Number.isFinite(value)
}
function parse(textValue) {
  if (typeof textValue !== 'string' || textValue.length > 1024 * 1024) throw new Error('文件过大，请导入不超过 1 MB 的 JSON 资料。')
  let value
  try { value = JSON.parse(textValue) } catch { throw new Error('文件不是有效的 JSON，请使用真实资料导出文件。') }
  if (!object(value) || !safe(value)) throw new Error('资料必须是对象，且不能包含不安全的字段。')
  return value
}
function known(value, keys) {
  if (Object.keys(value).some(key => !keys.includes(key))) throw new Error('资料包含不支持的字段，请导入登记请求所需的原始字段。')
}
const candidateKeys = ['title', 'issue_group_ids', 'baseline_config_version', 'candidate_config_version', 'single_changed_factor', 'target_task_versions', 'excluded_scope', 'expected_risk', 'rollback_version', 'baseline_config', 'candidate_config']
export function validateCandidateConfiguration(value) {
  if (!object(value) || !safe(value)) throw new Error('请先导入真实候选配置。')
  for (const [key, max] of [['baseline_config_version', 64], ['candidate_config_version', 64], ['single_changed_factor', 128], ['rollback_version', 64]]) {
    if (!text(value[key], max)) throw new Error('请导入完整的候选配置：版本、改动因素和回退版本须完整填写。')
  }
  if (!object(value.baseline_config) || !object(value.candidate_config) || !strings(value.target_task_versions)) throw new Error('请导入基准配置、候选配置对象及适用任务版本列表；不能使用界面默认配置。')
  if ('excluded_scope' in value && !strings(value.excluded_scope)) throw new Error('排除范围必须是字符串列表。')
  if ('expected_risk' in value && typeof value.expected_risk !== 'string') throw new Error('预期风险必须是文本。')
  if ('title' in value && !text(value.title, 200)) throw new Error('候选名称内容不正确。')
  if ('issue_group_ids' in value && (!strings(value.issue_group_ids) || !value.issue_group_ids.length)) throw new Error('关联问题组必须是非空列表。')
  return value
}
export function parseCandidateConfiguration(textValue) {
  const value = parse(textValue)
  known(value, candidateKeys)
  return validateCandidateConfiguration(value)
}
const reportKeys = ['run_id', 'report_id', 'report_version', 'report_digest', 'dataset_version', 'baseline_config_digest', 'candidate_config_digest', 'recommendation', 'completed', 'missing_cases']
export function validateCandidateReport(value) {
  if (!object(value) || !safe(value)) throw new Error('请先导入真实评测报告引用。')
  known(value, reportKeys)
  for (const [key, max] of [['run_id', 128], ['report_id', 128], ['report_version', 64], ['report_digest', 64], ['candidate_config_digest', 64]]) {
    if (!text(value[key], max)) throw new Error('报告运行、报告编号、版本和摘要须完整提供，不能自动补造。')
  }
  for (const key of ['dataset_version', 'baseline_config_digest']) {
    if (key in value && (typeof value[key] !== 'string' || value[key].length > 64)) throw new Error('报告数据集版本或基准摘要格式不正确。')
  }
  if (!['pass', 'fail', 'insufficient_evidence'].includes(value.recommendation) || typeof value.completed !== 'boolean' || !Number.isSafeInteger(value.missing_cases) || value.missing_cases < 0) throw new Error('报告须提供原始建议、完成状态及缺失案例数；不能使用默认通过值。')
  return value
}
export function parseCandidateReport(textValue) {
  return validateCandidateReport(parse(textValue))
}
