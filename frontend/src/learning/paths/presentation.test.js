import test from 'node:test'
import assert from 'node:assert/strict'
import {
  chapterLabel, currentChapterView, difficultyLabel, formatDate, hoursLabel, isNotFound,
  listStats, moduleViews, nextStepView, pathCardView, pathDetailView, progressStateOf,
  progressView, safeError, startResult,
} from './presentation.js'

const modules = [
  { id: 2, title: '第二章', order: 2, requires: [1], estimated_minutes: 20, module_type: 'practice', labs: [{ id: 9 }] },
  { id: 1, title: '第一章', order: 1, requires: [], estimated_minutes: 15, module_type: 'theory', labs: [] },
]

test('missing counts and hours are labelled, never invented as zero', () => {
  assert.equal(chapterLabel(undefined), '章节未提供')
  assert.equal(chapterLabel(0), '章节 0')
  assert.equal(hoursLabel(undefined), '—')
  assert.equal(hoursLabel(0), '—')
  assert.equal(hoursLabel(2.5), '2.5 小时')
  assert.equal(difficultyLabel('EX'), '专家')
  assert.equal(difficultyLabel('ZZ'), '难度未提供')
  assert.equal(formatDate(null), '—')

  const card = pathCardView({ id: 1, title: '航线', total_modules: 3, total_labs: 2, estimated_hours: 0 })
  assert.equal(card.chapterLabel, '章节 3')
  assert.equal(card.enrolledLabel, '在学人数未提供')
  assert.equal(card.hoursLabel, '—')
  const missing = pathCardView({ id: 2 })
  assert.equal(missing.chapterLabel, '章节未提供')
  assert.equal(missing.title, '未命名航线')
})

test('list statistics use the server count and do not turn the current page into a total', () => {
  const stats = listStats({ count: 26, results: [{ id: 1 }, { id: 2 }] }, 1)
  assert.equal(stats.total, 26)
  assert.equal(stats.totalLabel, '26')
  assert.equal(stats.partial, true)
  assert.equal(stats.hasNext, true)
  assert.equal(stats.enrolledKnown, false)
  assert.equal(stats.enrolledLabel, '未提供')

  const unpaginated = listStats([{ id: 1, enrollment_count: 4 }, { id: 2, enrollment_count: 6 }], 2)
  assert.equal(unpaginated.countKnown, false)
  assert.equal(unpaginated.totalLabel, '已加载 2')
  assert.equal(unpaginated.enrolledLabel, '10')
  assert.equal(unpaginated.hasPrev, true)
})

test('progress preserves missing data, anomalies and the real current module', () => {
  const view = progressView({ learning_path: 7, progress_percentage: 140, completed_modules: 3, total_modules: 2, started_at: '2026-11-03T00:00:00Z' })
  assert.equal(view.percent, 100)
  assert.equal(view.rawPercent, 140)
  assert.equal(view.anomaly, true)
  assert.equal(view.countLabel, '已完成 3 / 2 章节')
  assert.notEqual(view.startedLabel, '—')
  assert.equal(view.labLabel, '实验完成数待读取')

  const empty = progressView({ learning_path: 8 })
  assert.equal(empty.known, false)
  assert.equal(empty.percent, null)
  assert.equal(empty.countLabel, '章节完成数待读取')

  const unknown = progressView(null)
  assert.equal(unknown.known, false)
  assert.equal(unknown.startedLabel, '—')
})

test('progress read states keep not-joined(404) separate from a failed read', () => {
  assert.equal(progressStateOf({ status: 'fulfilled', value: { learning_path: 7 } }), 'joined')
  assert.equal(progressStateOf({ status: 'fulfilled', value: null }), 'failed')
  assert.equal(progressStateOf({ status: 'rejected', reason: { response: { status: 404 } } }), 'notJoined')
  assert.equal(progressStateOf({ status: 'rejected', reason: { response: { status: 500 } } }), 'failed')
  assert.equal(isNotFound({ response: { status: 404 } }), true)
  assert.equal(isNotFound({ response: { status: 403 } }), false)
})

test('module views map prerequisite IDs to real titles and mark only the server current chapter', () => {
  const views = moduleViews(modules, { currentModuleId: 2, pathId: 7, catalog: modules })
  assert.deepEqual(views.map(view => view.title), ['第一章', '第二章'])
  assert.equal(views[0].isCurrent, false)
  assert.equal(views[1].isCurrent, true)
  assert.deepEqual(views[1].requires, ['第一章'])
  assert.equal(views[1].missingRequires, 0)
  assert.equal(views[0].labLabel, '暂无实验')
  assert.equal(views[1].labLabel, '1 个实验')
  assert.equal(views[0].required, false)
  assert.match(views[0].to, /\/learning-paths\/7\/modules\/1$/)

  const missing = moduleViews([{ id: 5, title: '孤立章节', requires: [99] }], { pathId: 7, catalog: modules })
  assert.equal(missing[0].requires.length, 0)
  assert.equal(missing[0].missingRequires, 1)
  assert.equal(missing[0].minutesLabel, '时长未提供')
})

test('continuing uses only the backend current_module and never guesses a chapter', () => {
  const joined = { learning_path: 7, current_module: 2, current_module_title: '第二章' }
  const current = currentChapterView(joined, modules, 7)
  assert.equal(current.known, true)
  assert.equal(current.to, '/learning-paths/7/modules/2')

  const noCurrent = currentChapterView({ learning_path: 7, completed_modules: 1 }, modules, 7)
  assert.equal(noCurrent.known, false)
  assert.equal(noCurrent.to, '/learning-paths/7')
  assert.match(noCurrent.reason, /不按完成总数推测/)

  const unread = currentChapterView({ learning_path: 7, current_module: 99 }, modules, 7)
  assert.equal(unread.known, false)
  assert.match(unread.reason, /不推测替代章节/)
  assert.equal(unread.to, '/learning-paths/7')
})

test('next-step explanation is grounded in the real record and asks for confirmation', () => {
  const guide = nextStepView({ learning_path: 7, path_title: '授权航线', current_module: 2, current_module_title: '第二章', completed_modules: 1, total_modules: 2, progress_percentage: 50 }, modules, 7)
  assert.equal(guide.joined, true)
  assert.equal(guide.chapterTitle, '第二章')
  assert.equal(guide.countsLabel, '已完成 1 / 2 章节')
  assert.equal(guide.percentLabel, '50%')
  assert.match(guide.reason, /当前章节为《第二章》/)
  assert.equal(guide.confirmLabel, '确认，进入本章')
  assert.match(guide.note, /不会替你自动写入/)

  const noCurrent = nextStepView({ learning_path: 7, path_title: '授权航线', completed_modules: 1, total_modules: 2 })
  assert.equal(noCurrent.chapterTitle, '当前章节待读取')
  assert.match(noCurrent.reason, /不按完成总数推测/)
  assert.equal(noCurrent.confirmLabel, '确认，进入本章')
  assert.equal(noCurrent.canEnter, false)

  const done = nextStepView({ learning_path: 7, path_title: '授权航线', completed_at: '2026-11-02T00:00:00Z', progress_percentage: 100 })
  assert.equal(done.confirmLabel, '回看章节')
  assert.match(done.reason, /已全部完成/)

  assert.equal(nextStepView(null).joined, false)
})

test('join result only accepts progress for the requested path', () => {
  const ok = startResult({ learning_path: 7, progress_percentage: 0 }, 7)
  assert.equal(ok.ok, true)
  assert.equal(ok.record.progress_percentage, 0)
  for (const payload of [null, { learning_path: 8 }]) {
    assert.equal(startResult(payload, 7).ok, false)
  }
})

test('safe errors do not leak internal details', () => {
  assert.equal(safeError(new Error('INTERNAL_SQL_DETAIL'), '请重试。'), '请重试。')
  assert.equal(safeError({ response: { data: { error: '请先完成前置模块' } } }, '请重试。'), '请先完成前置模块')
  assert.equal(safeError({ response: { data: { detail: 'Traceback at line 1' } } }, '请重试。'), '请重试。')
  assert.equal(pathDetailView({ total_modules: 2, estimated_hours: null }).hoursLabel, '—')
})
