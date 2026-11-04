// 合规与基座治理页的显示词表。只影响界面文字，不改变任何请求值与权限判断。
const labels = {
  documentType: {
    law: '法律', regulation: '行政法规', standard: '标准', policy: '政策',
    case: '案例', template: '模板', platform_content: '平台内容', other: '其他',
  },
  documentStatus: {
    draft: '草稿', active: '有效', superseded: '已被替代', archived: '已归档',
  },
  taskStatus: {
    pending: '待处理', running: '运行中', completed: '已完成', failed: '未完成',
    draft: '草稿', exported: '已导出', open: '待处理', closed: '已关闭',
  },
  severity: { low: '低风险', medium: '需补充', high: '高风险', critical: '严重风险' },
  category: { law: '法律', regulation: '行政法规', standard: '标准', case: '案例', other: '其他' },
  source: {
    manual: '手动录入', challenge: '题目', data_processing: '数据处理', protocol: '协议',
    report: '报告', article: '文章', resource: '资源', legal_clause: '法规条款',
    legal_document: '法规文档', legal_case: '法律案例', legal_template: '合规模板',
    challenge_knowledge_pack: '题目知识包',
  },
  consentMethod: {
    clickwrap: '点击同意', checkbox: '勾选同意', admin_import: '管理员导入', api: '系统接入', other: '其他方式',
  },
  difficulty: { easy: '简单', medium: '中等', hard: '困难' },
  reportType: { compliance: '合规审查', audit: '审计', violation: '违规', other: '其他' },
  metrics: {
    start_requested: '启动请求', start_succeeded: '启动成功', start_failed: '启动失败',
    stop_requested: '停止请求', stop_succeeded: '停止成功', stop_failed: '停止失败',
    expired_cleanup: '过期清理', status_checked: '状态检查',
  },
  result: {
    requested: '已记录', success: '正常', failed: '失败', running: '运行中',
    stopped: '已停止', destroyed: '已销毁', not_found: '无会话',
  },
}

const fallback = {
  documentType: '资料类型待确认', documentStatus: '状态待确认', taskStatus: '状态待确认',
  severity: '风险等级待确认', category: '类别待确认', source: '来源待确认',
  consentMethod: '签署方式待确认', difficulty: '难度待确认', reportType: '报告类型待确认',
  metrics: '操作待确认', result: '结果待确认',
}

export function legalLabel(kind, value) {
  const group = labels[kind]
  return group && Object.hasOwn(group, value) ? group[value] : (fallback[kind] || '待确认')
}

export function legalBadgeTone(value) {
  const normalized = String(value || '').toLowerCase()
  if (['completed', 'active', 'final', 'exported', 'published', 'low', 'resolved', 'success'].includes(normalized)) return 'ok'
  if (['running', 'draft', 'medium', 'investigating', 'pending'].includes(normalized)) return 'warn'
  if (['failed', 'critical', 'high', 'open'].includes(normalized)) return 'danger'
  return 'neutral'
}
