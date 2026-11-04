// 章节页的纯呈现层：只消费已有接口真实返回的字段。
// 后端没有章节进度读取、模块笔记、实验题目映射与航线图谱；缺什么就说明缺什么，不补造。
import { asList, finiteNumber } from '../contracts.js'
import {
  difficultyLabel, flattenModules, formatDateTime, moduleTypeLabel, readableRequiresDetailed,
  safeError, text,
} from './presentation.js'

export const MODULE_STATUS_LABELS = {
  AVAILABLE: '未开始',
  IN_PROGRESS: '进行中',
  COMPLETED: '已完成',
  LOCKED: '未解锁',
}

// 章节内容来自 PathModuleSerializer 的 content 字段；四类 module_type 共用同一 Markdown 渲染与回退。
export function moduleView(module) {
  const source = module || {}
  const content = typeof source.content === 'string' ? source.content : ''
  const minutes = finiteNumber(source.estimated_minutes)
  return {
    id: finiteNumber(source.id),
    title: text(source.title) || '未命名章节',
    description: text(source.description),
    typeLabel: moduleTypeLabel(source.module_type),
    moduleType: text(source.module_type),
    required: source.is_required === true,
    content,
    hasContent: content.trim() !== '',
    minutesLabel: minutes !== null && minutes > 0 ? `${minutes} 分钟` : '时长未提供',
    requires: asList(source.requires ?? source.requires_modules)
      .map(value => finiteNumber(value))
      .filter(value => value !== null),
  }
}

// 章节进度只能由 start/complete 的真响应获得；加载详情本身不创建记录，也不推测状态。
export function moduleStatusView(record) {
  if (!record) {
    return {
      known: false,
      status: '',
      label: '尚未读取到本章节进度',
      startedLabel: '—',
      completedLabel: '—',
      canStart: true,
      canComplete: true,
      note: '点击“开始学习”后由后台创建章节进度；读取页面不会自动创建。',
    }
  }
  const status = text(record.status).toUpperCase()
  return {
    known: MODULE_STATUS_LABELS[status] !== undefined,
    status,
    label: MODULE_STATUS_LABELS[status] || '状态未提供',
    startedLabel: record.started_at ? formatDateTime(record.started_at) : '—',
    completedLabel: record.completed_at ? formatDateTime(record.completed_at) : '—',
    canStart: status !== 'COMPLETED' && status !== 'IN_PROGRESS',
    canComplete: status !== 'COMPLETED',
    note: status === 'COMPLETED'
      ? '本章节已完成；此状态只表示已学完章节，不代表已独立掌握。'
      : '状态来自后台返回；完成与否以平台记录为准。',
  }
}

// ModuleLabSerializer 只有关联摘要（order/is_optional/lab_title/lab_description/lab_difficulty/lab_score），
// 没有题目编号、附件或本人实验进度，因此只展示这些真实字段。
export function labViews(labs) {
  return asList(labs)
    .slice()
    .sort((a, b) => (finiteNumber(a?.order) ?? 0) - (finiteNumber(b?.order) ?? 0))
    .map((lab, index) => {
      const score = finiteNumber(lab?.lab_score)
      return {
        id: finiteNumber(lab?.id),
        order: index + 1,
        optional: lab?.is_optional === true,
        title: text(lab?.lab_title) || '实验名称未提供',
        description: text(lab?.lab_description) || '实验说明未提供',
        difficultyLabel: text(lab?.lab_difficulty) ? difficultyLabel(lab.lab_difficulty) : '难度未提供',
        scoreLabel: score !== null ? `${score} 分` : '分值未提供',
      }
    })
}

// 关联摘要不含题目编号：不提供进入/提交入口，也不发任何题库请求。
export function labCapability() {
  return {
    canEnter: false,
    canSubmit: false,
    statusLabel: '状态未提供',
    reason: '实验关联字段只包含摘要，没有题目编号与本人实验进度；当前不能从这里进入练习或提交 Flag，也不显示“已同步航线成绩”。',
  }
}

export function requiresView(requires, catalog) {
  const detail = readableRequiresDetailed(requires, catalog)
  const missingNote = detail.missing
    ? `有 ${detail.missing} 项先修未能从章节目录读取名称；不以编号充当名称。`
    : ''
  return {
    labels: detail.labels,
    missing: detail.missing,
    label: detail.labels.length
      ? `先修：${detail.labels.join('、')}${missingNote ? `；${missingNote}` : ''}`
      : (missingNote || '本章无先修要求。'),
  }
}

export function modulePosition(moduleId, modules, pathId) {
  const list = flattenModules(modules)
  const index = list.findIndex(item => finiteNumber(item?.id) === finiteNumber(moduleId))
  const path = finiteNumber(pathId)
  if (index < 0) return { known: false, label: '章节位置待读取', previous: null, next: null }
  const target = item => {
    const id = finiteNumber(item?.id)
    return id !== null && path !== null ? { id, title: text(item.title), to: `/learning-paths/${path}/modules/${id}` } : null
  }
  return {
    known: true,
    label: `第 ${index + 1} / ${list.length} 章`,
    previous: index > 0 ? target(list[index - 1]) : null,
    next: index < list.length - 1 ? target(list[index + 1]) : null,
  }
}

export function notesView({ content, saved }) {
  const body = typeof content === 'string' ? content : ''
  const baseline = typeof saved === 'string' ? saved : ''
  return {
    empty: body.trim() === '',
    dirty: body !== baseline,
    lengthLabel: `${body.length} 字`,
    statusLabel: body === baseline
      ? (body.trim() ? '本地草稿（不会上传到服务器）' : '尚未记录笔记')
      : '尚未保存 · 仅在当前浏览器',
    note: '现有后端没有章节笔记读写接口，这里的内容只保存在本机浏览器，可手动复制或下载保全；刷新或换设备不会同步。',
  }
}

export function completeResult(payload, moduleId) {
  const status = text(payload?.status).toUpperCase()
  if (String(payload?.module) !== String(moduleId) || status !== 'COMPLETED') {
    return { ok: false, message: '未能确认章节已完成；进度以平台记录为准，请重新读取后再试。' }
  }
  return { ok: true, message: '已记录本章节完成；这只表示已学完章节，不代表已独立掌握。' }
}

// 后端要求先有模块进度记录才能完成；404 时给出可操作说明，不伪造完成。
export function completeFailure(error) {
  if (error?.response?.status === 404) {
    return { needsStart: true, message: '后台还没有本章节的进度记录。请先点击“开始学习”，再在学完后标记完成。' }
  }
  if (error?.response?.status === 403) {
    return { needsStart: false, message: '当前账号没有完成该章节的权限，请联系教师核对。' }
  }
  return { needsStart: false, message: safeError(error, '标记完成暂时失败，请稍后重试；未写入任何完成状态。') }
}

export function loadFailure(error) {
  if (error?.response?.status === 404) {
    return { notFound: true, message: '章节不存在或已下架，请返回航线详情重新选择章节。' }
  }
  return { notFound: false, message: safeError(error, '章节暂时无法读取，请稍后重试。') }
}

export function startFailure(error) {
  if (error?.response?.status === 400) {
    return { blocked: true, message: safeError(error, '本章节还有未满足的先修条件，请先完成前置章节。') }
  }
  return { blocked: false, message: safeError(error, '开始学习暂时失败，请稍后重试；未写入学习记录。') }
}
