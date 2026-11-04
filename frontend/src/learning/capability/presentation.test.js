import test from 'node:test'
import assert from 'node:assert/strict'
import {
  STATE_LEGEND, allCapabilities, capabilityView, catalogSummary, changelogViews, claimResult,
  diagnosisView, evidenceView, findCapability, nodeTaskLink, prerequisiteViews, questionView,
  recommendationViews, sanitizeReason, stateInfo, trackViews,
} from './presentation.js'

function capability(overrides = {}) {
  return {
    title: '导出请求的授权与范围判断',
    observable_objective: '能依据授权范围判断敏感字段导出并保留记录',
    dimension: 'identify',
    dimension_label: '能识别',
    difficulty: 2,
    availability_label: '已开放',
    knowledge_points: [{ name: '授权范围' }, { name: '最小必要' }],
    prerequisites: [
      { title: '识别授权主体', state_label: '已有独立证据', tone: 'success' },
      { title: '整理字段清单', state_label: '待诊断', tone: 'muted' },
    ],
    state_label: '待复测',
    tone: 'warning',
    retest_due_at: '2026-11-06T02:00:00Z',
    evidence: {
      fact_count: 2,
      latest: { outcome_label: '受助通过', assisted: true, occurred_at: '2026-11-03T02:00:00Z', task_title: '导出判断' },
    },
    ...overrides,
  }
}

const track = { track: 'data', label: '数据安全', capabilities: [capability()], dimensions: [] }

test('unknown and non-evidence states stay unknown, never zero mastery', () => {
  for (const label of ['待诊断', '已完成诊断', '未开展', '未知']) {
    const info = stateInfo({ state_label: label, tone: 'muted' })
    assert.equal(info.known, false, label)
    assert.equal(info.rawLabel, label)
  }
  assert.equal(stateInfo({ state_label: '已完成诊断' }).label, '已做诊断')
  assert.equal(stateInfo({ state_label: '未开展' }).label, '未开始')
  assert.equal(stateInfo({ state_label: '未知' }).label, '状态未知')
  assert.equal(stateInfo({}).known, false)
  assert.equal(stateInfo({}).label, '状态未知')
  // 待评阅不是失败：保留原状态且不当作已知掌握。
  assert.equal(stateInfo({ state_label: '待教师评阅', tone: 'neutral' }).key, 'pending')
  assert.equal(stateInfo({ state_label: '待教师评阅', tone: 'neutral' }).label, '待老师批阅')
  assert.equal(stateInfo({ state_label: '待核验', tone: 'neutral' }).label, '待确认')
  assert.equal(stateInfo({ state_label: '需要练习', tone: 'danger' }).key, 'practice')
  assert.equal(stateInfo({ state_label: '需要练习', tone: 'danger' }).label, '继续练习')
  assert.equal(stateInfo({ state_label: '已有独立证据', tone: 'success' }).key, 'independent')
  assert.equal(stateInfo({ state_label: '已有独立证据', tone: 'success' }).label, '独立通过')
  const view = capabilityView(track, capability({ evidence: { fact_count: 0 }, state_label: '待诊断', tone: 'muted' }))
  assert.equal(view.state.known, false)
  assert.equal(view.evidence.hasEvidence, false)
  assert.equal(view.evidence.result, '还没有练习记录')
  assert.equal(STATE_LEGEND.length, 5)
  // 图例与状态名用学生能直接理解的说法，不保留评估术语。
  assert.doesNotMatch(STATE_LEGEND.map(entry => `${entry.label}${entry.note}`).join(''), /核验|可观察|证据/)
})

test('capability detail preserves objective, difficulty, points, prerequisites and evidence', () => {
  const view = capabilityView(track, capability())
  assert.equal(view.trackLabel, '数据安全')
  assert.equal(view.objective, '能依据授权范围判断敏感字段导出并保留记录')
  assert.equal(view.dimensionLabel, '能识别')
  assert.equal(view.difficulty, 2)
  assert.deepEqual(view.knownPoints, ['授权范围', '最小必要'])
  assert.equal(view.prerequisites[0].satisfied, true)
  assert.equal(view.prerequisites[0].stateLabel, '独立通过')
  assert.equal(view.prerequisites[1].satisfied, false)
  assert.equal(view.evidence.count, 2)
  assert.equal(view.evidence.result, '提示后通过')
  assert.equal(view.evidence.task, '导出判断')
  assert.equal(view.evidence.assisted, true)
  assert.notEqual(view.evidence.timeLabel, '—')
  assert.notEqual(view.retestLabel, '')
  assert.equal(view.open, true)
  assert.equal(capabilityView({}, null), null)
  assert.deepEqual(prerequisiteViews(null), [])
  assert.equal(evidenceView(undefined).hasEvidence, false)
})

test('tracks keep dimensions and real counts; selection keys never collide across tracks', () => {
  const map = {
    catalog: { version_label: 'phase2-v1', status_label: '已发布', is_published: true, updated_at: '2026-11-03T00:00:00Z' },
    summary: { open_capabilities: 2, independent_count: 1, assisted_count: 1, needs_practice_count: 0 },
    versions: { data_source_label: '本人核验结果', updated_at: '2026-11-03T00:00:00Z' },
    tracks: [
      { ...track, dimensions: [{ dimension: 'identify', label: '能识别', display_label: '待复测', tone: 'warning', capability_count: 1 }] },
      { track: 'network', label: '网络安全', capabilities: [capability({ title: '导出请求的授权与范围判断' })], dimensions: [] },
    ],
  }
  const views = trackViews(map)
  assert.equal(views.length, 2)
  // 空主线也保留目录主线本身，供页面给出“暂未收录”而不是整块消失。
  assert.equal(trackViews({ tracks: [{ track: 'network', label: '网络安全', capabilities: [], dimensions: [] }] })[0].label, '网络安全')
  assert.equal(views[0].dimensions[0].displayLabel, '待复测')
  assert.equal(views[0].dimensions[0].count, 1)
  const all = allCapabilities(map)
  assert.equal(all.length, 2)
  assert.notEqual(all[0].key, all[1].key)
  assert.equal(findCapability(map, all[1].key).track, 'network')
  assert.equal(findCapability(map, 'nope'), null)
  const summary = catalogSummary(map)
  assert.equal(summary.versionLabel, 'phase2-v1')
  assert.equal(summary.openCapabilities, 2)
  assert.equal(summary.independentCount, 1)
  assert.equal(summary.assistedCount, 1)
  assert.equal(summary.dataSource, '本人练习结果')
  assert.ok(summary.updatedLabel !== '—')
})

test('recommendations declare mainline relation and keep task or diagnosis fields', () => {
  const items = recommendationViews({
    generated_at: '2026-11-03T02:00:00Z',
    items: [
      {
        kind: 'task', category_label: '补先修', track_label: '数据安全', priority: 1,
        reason_text: '先补齐授权范围判断', task: { id: 9, title: '导出判断', version_label: 'v2', purpose_label: '验证' },
      },
      { kind: 'diagnosis', category_label: '基础诊断', track_label: '网络安全', priority: 2, reason_text: '先做诊断' },
    ],
  })
  assert.equal(items.length, 2)
  assert.equal(items[0].relationNote, '本主线推荐')
  assert.equal(items[0].task.title, '导出判断')
  assert.equal(items[0].task.versionLabel, 'v2')
  assert.equal(items[0].task.purposeLabel, '验证')
  // 后端用途直译（如“验收”“新场景复测”）改成学生用语，保留用途含义。
  assert.equal(recommendationViews({ items: [{ kind: 'task', task: { id: 1, title: 't', purpose_label: '验收' } }] })[0].task.purposeLabel, '检验掌握')
  assert.equal(recommendationViews({ items: [{ kind: 'task', task: { id: 1, title: 't', purpose_label: '新场景复测' } }] })[0].task.purposeLabel, '换新题复测')
  assert.notEqual(items[0].generatedLabel, '—')
  assert.equal(items[1].task, null)
  assert.equal(items[1].diagnosisTrack, 'network')
  assert.equal(items[0].diagnosisTrack, null)
  // 没有节点到任务的精确映射时不冒充“本节点关联”。
  assert.equal(nodeTaskLink(), null)
  assert.deepEqual(recommendationViews(null), [])
})

test('student reason text never shows catalog stable IDs as copy', () => {
  assert.equal(
    sanitizeReason('目标能力 P2-DATA-003 的先修 P2-DATA-002 尚未取得独立证据。'),
    '目标能力的先修能力还没有独立完成过。',
  )
  assert.equal(sanitizeReason('先修已满足，可进入该能力的审核任务。'), '先修已满足，可进入该能力的审核任务。')
  assert.equal(sanitizeReason(null), '')
  // 评估术语不出现在学生文案里，结论含义不变。
  assert.equal(sanitizeReason('最近核验未通过，按已确认错因练习同知识点任务。'), '最近练习未通过，按已确认错因练习同知识点任务。')
  assert.equal(sanitizeReason('目标能力 P2-DATA-003 的先修 P2-DATA-002 尚未取得独立证据。'), '目标能力的先修能力还没有独立完成过。')
  const [item] = recommendationViews({
    items: [{ kind: 'task', reason_text: '目标能力 P2-DATA-003 的先修 P2-DATA-002 尚未取得独立证据。', task: { id: 1, title: 't' } }],
  })
  assert.doesNotMatch(item.reason, /P2-DATA/)
})

test('diagnosis reports counts and per-item results without becoming evidence', () => {
  const view = diagnosisView({
    question_count: 3, answered_count: 2,
    items: [{ title: '授权范围', result_label: '建议先补基础' }],
  })
  assert.equal(view.questionCount, 3)
  assert.equal(view.answeredCount, 2)
  assert.equal(view.items[0].label, '建议先补基础')
  assert.match(view.note, /不代表已经学会/)
  assert.match(view.note, /没有作答的题不会算作不会/)
  const question = questionView({
    question_key: 'q1', capability_title: '授权范围', dimension_label: '能识别', prompt: '先确认什么？',
    options: [{ key: 'A', label: '授权范围' }],
  })
  assert.equal(question.options[0].label, '授权范围')
  assert.equal(questionView(null).capabilityTitle, '能力未知')
})

test('changelog keeps time, before/after state and reason', () => {
  const rows = changelogViews({
    items: [{
      capability_title: '导出判断', from_state_label: '待诊断', to_state_label: '受助通过',
      reason_label: '平台核验', created_at: '2026-11-03T02:00:00Z',
    }],
  })
  assert.equal(rows[0].from, '待诊断')
  assert.equal(rows[0].to, '提示后通过')
  assert.equal(rows[0].reason, '平台确认')
  assert.notEqual(rows[0].timeLabel, '—')
  // 后端原因直译（含“核验/证据”）收成学生用语，前后状态与结论不变。
  const [real] = changelogViews({ items: [{ from_state_label: '待诊断', to_state_label: '已有独立证据', reason_label: '核验通过，已有独立证据' }] })
  assert.equal(real.to, '独立通过')
  assert.equal(real.reason, '练习通过，已独立完成')
})

test('claim uses the real attempt and states the missing work surface instead of fabricating one', () => {
  const created = claimResult({ attempt_id: 'a-9', task: { title: '导出判断' }, created: true })
  assert.equal(created.ok, true)
  assert.equal(created.attemptId, 'a-9')
  assert.equal(created.created, true)
  // 领取结果是给学生看的：不暴露内部尝试编号，也不出现内部编号/工程标记。
  assert.match(created.message, /已领取/)
  assert.doesNotMatch(created.message, /a-9|尝试/)
  assert.equal(created.workSurface, null)
  assert.doesNotMatch(created.reason, /G08|工作面/)

  const existing = claimResult({ attempt_id: 'a-9', task: { title: '导出判断' }, created: false })
  assert.equal(existing.created, false)
  assert.match(existing.message, /已经领取过/)

  const missing = claimResult({ task: { title: '导出判断' }, created: true })
  assert.equal(missing.ok, false)
  assert.match(missing.reason, /无法核对/)
})
