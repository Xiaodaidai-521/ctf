// 航线列表/详情/下一步的纯呈现层：只用后端真实返回的字段，缺值显示“未提供/待读取”，
// 不按完成总数猜测章节状态，不从当前页条数冒充全量。
import { asList, finiteNumber, pageInfo } from '../contracts.js'

const DIFFICULTY_LABELS = { AP: '入门', PR: '进阶', EX: '专家' }
const MODULE_TYPE_LABELS = { intro: '介绍', theory: '理论', practice: '实践', challenge: '挑战' }
const INTERNAL_ERROR = /INTERNAL|SQL|Traceback|Exception|stack/i

export function text(value) {
  if (value === undefined || value === null) return ''
  return String(value).trim()
}

export function difficultyLabel(value) {
  return DIFFICULTY_LABELS[value] || '难度未提供'
}

export function moduleTypeLabel(value) {
  return MODULE_TYPE_LABELS[value] || text(value) || '类型未提供'
}

export function formatDate(value) {
  const time = Date.parse(value)
  if (!Number.isFinite(time)) return '—'
  return new Date(time).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

export function formatDateTime(value) {
  const time = Date.parse(value)
  if (!Number.isFinite(time)) return '—'
  return new Date(time).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

// 预计/学习时长缺失或为 0（后端默认值）时显示“—”，不补成 0 小时。
export function hoursLabel(value) {
  const hours = finiteNumber(value)
  return hours !== null && hours > 0 ? `${hours} 小时` : '—'
}

export function chapterLabel(value) {
  const count = finiteNumber(value)
  return count !== null ? `章节 ${count}` : '章节未提供'
}

export function labCountLabel(value) {
  const count = finiteNumber(value)
  return count !== null ? `实验 ${count}` : '实验数未提供'
}

export function enrolledLabel(value) {
  const count = finiteNumber(value)
  return count !== null ? `${count} 人在学` : '在学人数未提供'
}

// 安全错误文案：后端内部错误不外泄，只保留短小可读的说明。
export function safeError(error, fallback = '网络或服务异常，请稍后重试。') {
  const body = error?.response?.data
  const detail = typeof body === 'string' ? body : body?.detail || body?.error
  if (typeof detail === 'string') {
    const message = detail.trim()
    if (message && message.length <= 120 && !INTERNAL_ERROR.test(message)) return message
  }
  return fallback
}

export function isNotFound(error) {
  return error?.response?.status === 404
}

export function pathCardView(path) {
  const source = path || {}
  const id = finiteNumber(source.id)
  return {
    id: id === null ? null : id,
    chapterCount: finiteNumber(source.total_modules),
    labCount: finiteNumber(source.total_labs),
    title: text(source.title) || '未命名航线',
    description: text(source.description),
    difficulty: text(source.difficulty),
    difficultyLabel: difficultyLabel(source.difficulty),
    chapterLabel: chapterLabel(source.total_modules),
    labLabel: labCountLabel(source.total_labs),
    hoursLabel: hoursLabel(source.estimated_hours),
    enrolledLabel: enrolledLabel(source.enrollment_count),
    published: source.is_published === true,
  }
}

// 列表统计：count 缺失时说明“已加载”，不用当前页 length 冒充全量；在学人数缺字段显示“未提供”。
export function listStats(payload, page = 1) {
  const info = pageInfo(payload)
  const enrolled = info.items.map(item => finiteNumber(item?.enrollment_count)).filter(value => value !== null)
  return {
    items: info.items,
    total: info.count,
    countKnown: info.count !== null,
    loaded: info.loaded,
    totalLabel: info.count !== null ? String(info.count) : `已加载 ${info.loaded}`,
    partial: info.count !== null && info.loaded < info.count,
    enrolledKnown: enrolled.length > 0,
    enrolled: enrolled.length ? enrolled.reduce((sum, value) => sum + value, 0) : null,
    enrolledLabel: enrolled.length ? String(enrolled.reduce((sum, value) => sum + value, 0)) : '未提供',
    page: Math.max(1, finiteNumber(page) ?? 1),
    hasNext: info.hasNext,
    hasPrev: Math.max(1, finiteNumber(page) ?? 1) > 1,
  }
}

export function pathDetailView(path) {
  const source = path || {}
  const chapterCount = finiteNumber(source.total_modules)
  return {
    title: text(source.title) || '未命名航线',
    description: text(source.description),
    category: text(source.category),
    difficultyLabel: difficultyLabel(source.difficulty),
    chapterKnown: chapterCount !== null,
    chapterCount,
    chapterLabel: chapterLabel(source.total_modules),
    labCount: finiteNumber(source.total_labs),
    labLabel: labCountLabel(source.total_labs),
    hoursLabel: hoursLabel(source.estimated_hours),
    published: source.is_published === true,
  }
}

// 本人进度：以后端进度记录为准；超过 100% 如实标为异常，不裁成正常满进度。
export function progressView(record) {
  if (!record) {
    return {
      known: false, percent: null, rawPercent: null, anomaly: false,
      completed: null, total: null, countLabel: '章节完成数待读取',
      startedLabel: '—', labLabel: '实验完成数待读取', complete: false, completedAt: null,
    }
  }
  const rawPercent = finiteNumber(record.progress_percentage)
  const completed = finiteNumber(record.completed_modules)
  const total = finiteNumber(record.total_modules)
  const completedLabs = finiteNumber(record.completed_labs)
  const totalLabs = finiteNumber(record.total_labs)
  return {
    known: rawPercent !== null,
    rawPercent,
    percent: rawPercent === null ? null : Math.max(0, Math.min(100, Math.round(rawPercent))),
    anomaly: rawPercent !== null && rawPercent > 100,
    completed,
    total,
    countLabel: completed !== null && total !== null ? `已完成 ${completed} / ${total} 章节` : '章节完成数待读取',
    startedLabel: formatDate(record.started_at),
    labLabel: completedLabs !== null && totalLabs !== null ? `${completedLabs} / ${totalLabs} 个实验` : '实验完成数待读取',
    complete: Boolean(record.completed_at) || (rawPercent !== null && rawPercent >= 100),
    completedAt: record.completed_at || null,
  }
}

// 进度读取结果分三类：有记录、明确未加入（404）、读取失败。失败不当成未加入。
export function progressStateOf(result) {
  if (!result) return 'loading'
  if (result.status === 'fulfilled') {
    return result.value ? 'joined' : 'failed'
  }
  return isNotFound(result.reason) ? 'notJoined' : 'failed'
}

export function flattenModules(modules) {
  const list = []
  const walk = items => {
    for (const item of asList(items)) {
      if (!item) continue
      list.push(item)
      walk(item.sub_modules)
    }
  }
  walk(modules)
  return list
}

export function moduleOrder(modules) {
  return asList(modules).slice().sort((a, b) => {
    const orderA = finiteNumber(a?.order)
    const orderB = finiteNumber(b?.order)
    if (orderA !== null && orderB !== null && orderA !== orderB) return orderA - orderB
    if (orderA !== null && orderB === null) return -1
    if (orderA === null && orderB !== null) return 1
    return (finiteNumber(a?.id) ?? 0) - (finiteNumber(b?.id) ?? 0)
  })
}

export function readableRequiresDetailed(requires, catalog) {
  const labels = []
  let missing = 0
  for (const ref of asList(requires)) {
    const id = finiteNumber(ref)
    if (id === null) continue
    const module = flattenModules(catalog).find(item => finiteNumber(item?.id) === id)
    if (module && text(module.title)) labels.push(text(module.title))
    else missing += 1
  }
  return { labels, missing }
}

// 章节视图：完成/解锁状态没有可信来源时不伪造，只标出后台返回的当前章节。
export function moduleViews(modules, { currentModuleId = null, pathId = null, catalog = modules } = {}) {
  const current = finiteNumber(currentModuleId)
  const path = finiteNumber(pathId)
  return moduleOrder(modules).map((module, index) => {
    const id = finiteNumber(module?.id)
    const requires = readableRequiresDetailed(module?.requires ?? module?.requires_modules, catalog)
    const labs = asList(module?.labs)
    return {
      id,
      order: index + 1,
      title: text(module?.title) || '未命名章节',
      description: text(module?.description),
      typeLabel: moduleTypeLabel(module?.module_type),
      required: module?.is_required === true,
      minutesLabel: finiteNumber(module?.estimated_minutes) !== null ? `${finiteNumber(module.estimated_minutes)} 分钟` : '时长未提供',
      labCount: labs.length,
      labLabel: labs.length ? `${labs.length} 个实验` : '暂无实验',
      requires: requires.labels,
      missingRequires: requires.missing,
      isCurrent: current !== null && id === current,
      to: path !== null && id !== null ? `/learning-paths/${path}/modules/${id}` : '',
    }
  })
}

// 继续学习只认后端 current_module；缺字段时说明待读取，不按 completed_modules 推测章节。
export function currentChapterView(record, modules, pathId = null) {
  const path = finiteNumber(pathId) ?? finiteNumber(record?.learning_path)
  if (!record) {
    return { known: false, moduleId: null, title: '', to: '', canEnter: false, reason: '尚未读取到本人航线进度。' }
  }
  const currentId = finiteNumber(record.current_module)
  if (currentId === null) {
    return {
      known: false, moduleId: null, title: '', canEnter: false,
      to: path !== null ? `/learning-paths/${path}` : '/learning-paths',
      reason: '后台尚未返回当前章节；请按章节列表顺序自行选择，不按完成总数推测。',
    }
  }
  const module = flattenModules(modules).find(item => finiteNumber(item?.id) === currentId)
  if (!module) {
    // 章节列表未读到，但后端已给出当前章节编号与标题：按该真实编号进入，不推测替代章节。
    const title = text(record.current_module_title)
    return {
      known: Boolean(title), moduleId: currentId, title: title || `章节 ${currentId}`,
      canEnter: Boolean(title) && path !== null,
      to: title && path !== null ? `/learning-paths/${path}/modules/${currentId}` : path !== null ? `/learning-paths/${path}` : '',
      reason: title
        ? '章节列表暂未读取，进入的是后台记录的当前章节。'
        : '后台记录了当前章节编号，但缺少标题；请刷新后再继续，不推测替代章节。',
    }
  }
  return {
    known: true, moduleId: currentId,
    title: text(module.title) || text(record.current_module_title) || `章节 ${currentId}`,
    canEnter: true,
    to: path !== null ? `/learning-paths/${path}/modules/${currentId}` : '',
    reason: '',
  }
}

// 详情页/智航共用的“下一步”说明：解释为什么是这一章，进入前需学生确认。
export function nextStepView(record, modules = [], pathId = null) {
  if (!record) {
    return {
      joined: false, pathId: null, pathTo: '/learning-paths', chapterKnown: false, title: '', chapterTitle: '',
      countsLabel: '', percentLabel: '', reason: '', confirmLabel: '', to: '', canEnter: false, note: '',
    }
  }
  const path = finiteNumber(pathId) ?? finiteNumber(record.learning_path)
  const progress = progressView(record)
  const current = currentChapterView(record, modules, path)
  const completed = progress.complete
  const reason = completed
    ? `后台记录显示这条航线已全部完成${progress.completedAt ? `（${formatDate(progress.completedAt)}）` : ''}；可以回看章节，或到能力图谱选择新的练习。`
    : current.known
      ? `你在本航线的记录显示当前章节为《${current.title}》${progress.completed !== null && progress.total !== null ? `，已完成 ${progress.completed} / ${progress.total} 章` : ''}。按已加入航线的既定顺序，先完成这一章，再进入后续章节。`
      : `${progress.countLabel}。${current.reason}`
  const canEnter = completed ? Boolean(current.to) : current.known && Boolean(current.to)
  return {
    joined: true,
    pathId: path,
    pathTo: path !== null ? `/learning-paths/${path}` : '/learning-paths',
    chapterKnown: current.known && !completed,
    title: text(record.path_title) || '在学航线',
    chapterTitle: completed ? '这条航线已完成' : current.title || '当前章节待读取',
    countsLabel: progress.countLabel,
    percentLabel: progress.percent === null ? '' : `${progress.percent}%`,
    reason,
    confirmLabel: completed ? '回看章节' : '确认，进入本章',
    to: current.to || (path !== null ? `/learning-paths/${path}` : '/learning-paths'),
    canEnter,
    note: completed
      ? '回看不会改变完成状态。'
      : '确认后进入章节页；开始章节、标记完成仍由你在章节页操作，对话不会替你自动写入。',
  }
}

export function startResult(payload, pathId) {
  if (!payload || String(payload.learning_path) !== String(pathId)) {
    return { ok: false, record: null, message: '未能确认已加入学习航线。请重新加载进度后再试。' }
  }
  return { ok: true, record: payload, message: '已加入这条航线；进度以平台记录为准。' }
}
