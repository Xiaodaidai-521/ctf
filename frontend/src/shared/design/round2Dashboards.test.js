import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate, compileStyle } from 'vue/compiler-sfc'
import { createSourceController, listValue } from '../../admin/governance/data.js'
import { challengeDistributions, platformStats } from '../../admin/insights/presentation.js'

const source = role => readFileSync(new URL(role === 'admin' ? '../../admin/views/Dashboard.vue' : '../../teacher/TeacherDashboard.vue', import.meta.url), 'utf8')
const platformSource = () => readFileSync(new URL('../../admin/insights/PlatformInsights.vue', import.meta.url), 'utf8')
function admin(api) {
  const sources = { leaderboard: { data: null }, challenges: { data: null } }
  const controller = createSourceController(sources, {
    leaderboard: () => api.user.leaderboard({ page_size: 100 }),
    challenges: async () => { const data = await api.challenge.getChallenges(); listValue(data); return data },
  })
  return { api, sources, fetchStats: controller.load, get stats() { return platformStats(sources) },
    get categoryStats() { return challengeDistributions(sources.challenges.data).categories },
    get difficultyStats() { return challengeDistributions(sources.challenges.data).difficulties } }
}

test('staff overviews retain shared tokens, role-specific primary action and work entrances', () => {
  for (const role of ['teacher', 'admin']) {
    const text = source(role), descriptor = parse(text).descriptor
    assert.deepEqual(parse(text).errors, [])
    const script = compileScript(descriptor, { id: 'dashboard-contract' })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: `${role}.vue`, id: 'dashboard-contract', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
    for (const style of descriptor.styles) {
      assert.equal(style.scoped, true)
      const css = style.src ? readFileSync(new URL(style.src, new URL('../../admin/views/Dashboard.vue', import.meta.url)), 'utf8') : style.content
      assert.deepEqual(compileStyle({ source: css, filename: `${role}.vue`, id: 'dashboard-contract', scoped: true }).errors, [])
      assert.doesNotMatch(css, /#[\da-f]{3,8}\b|rgba?\(|@keyframes|animation\s*:/i)
      assert.ok(css.includes('var(--student-hero-gradient)'))
      if (role === 'teacher') {
        assert.ok(css.includes('var(--student-console-radius)'))
        assert.match(css, /var\(--shadow-(?:raised|sm)\)/)
      }
    }
    if (role === 'admin') {
      assert.match(text, /class="governance-primary"[^>]*@click="load"/)
      assert.match(text, /governanceTiles/)
      assert.doesNotMatch(text, /to="\/multi-agent"|collaboration-console/)
      assert.match(text, /to="\/admin\/student-learning"/)
    } else {
      assert.match(text, /to="\/multi-agent"/)
      assert.match(text, /class="btn btn-primary"[^>]*@click="load"/)
      assert.doesNotMatch(text, /class="btn btn-primary" to="\/multi-agent"/)
    }
    assert.doesNotMatch(text, /<canvas|72%|6 天/)
  }
  const teacher = source('teacher')
  const contentNav = readFileSync(new URL('../knowledge/ContentAreaNav.vue', import.meta.url), 'utf8')
  assert.match(teacher, /<ContentAreaNav/)
  for (const target of ['/teacher/learning-paths', '/teacher/challenges', '/teacher/learning-scores', '/teacher/learning-effect', '/teacher/resources', '/teacher/knowledge', '/teacher/materials']) assert.ok(`${teacher}\n${contentNav}`.includes(target), target)
})

test('admin statistics remain real, now in platform insights rather than governance to-dos', async () => {
  const calls = []
  const state = admin({ user: { leaderboard: async params => { calls.push(params); return { total: 4 } } }, challenge: { getChallenges: async () => ({ results: [{ category_name: '授权基础', difficulty: 'easy' }, { category_name: 'Web', difficulty: 'hard' }, { category_name: 'Web', difficulty: 'medium' }] }) } })
  await state.fetchStats()
  assert.equal(calls[0].page_size, 100)
  assert.equal(state.stats.rankedUsers, 4)
  assert.equal(state.stats.totalChallenges, 3)
  for (const key of ['totalUsers', 'newUsers', 'activeChallenges', 'totalSubmissions', 'successRate', 'totalScore', 'avgScore']) assert.equal(state.stats[key], null, key)
  assert.equal(state.categoryStats.find(c => c.name === '授权基础').count, 1)
  assert.equal(state.categoryStats.find(c => c.name === 'Web').percentage, 67)
  assert.equal(state.difficultyStats.reduce((sum, d) => sum + d.count, 0), 3)
  assert.equal(state.sources.leaderboard.error, '')
  assert.doesNotMatch(platformSource(), /successRate=65|totalUsers\*|username:'user1'/)
})

test('admin read failures and malformed data still never fabricate zero; retry restores independent real results', async () => {
  let fail = true
  const state = admin({ user: { leaderboard: async () => { if (fail) throw Error('offline'); return { total: 0 } } }, challenge: { getChallenges: async () => fail ? { wrong: [] } : [] } })
  await state.fetchStats()
  assert.equal(state.stats.rankedUsers, null)
  assert.equal(state.stats.totalChallenges, null)
  assert.equal(state.categoryStats.length, 0)
  assert.match(state.sources.leaderboard.error, /暂时无法读取/)
  assert.match(state.sources.challenges.error, /暂时无法读取/)
  fail = false
  await state.fetchStats()
  assert.equal(state.stats.rankedUsers, 0)
  assert.equal(state.stats.totalChallenges, 0)
  assert.equal(state.categoryStats.length, 0)
  assert.equal(state.sources.leaderboard.error, '')
  state.api.user.leaderboard = async () => ({ total: null })
  state.api.challenge.getChallenges = async () => [{ category_name: 'Crypto', difficulty: 'expert' }]
  await state.fetchStats()
  assert.equal(state.stats.rankedUsers, null)
  assert.equal(state.stats.totalChallenges, 1)
})

test('admin missing categories retain explicit labels and absent metrics are never zero-filled', async () => {
  const state = admin({ user: { leaderboard: async () => ({ total: 2 }) }, challenge: { getChallenges: async () => [{}, { category_name: 'Web', difficulty: 'easy' }] } })
  await state.fetchStats()
  assert.equal(state.categoryStats.find(c => c.name === '未分类').percentage, 50)
  assert.equal(state.difficultyStats.find(d => d.name === '未标注').count, 1)
  const text = platformSource()
  assert.match(text, /metric\.value === null \? '未提供'/)
  for (const label of ['平台用户总数', '新增人数', '题目总数', '平台总提交数', '平台提交正确率', '总分发放', '平均分', '题目分类分布', '题目难度分布', '最新解题动态']) assert.ok(text.includes(label), label)
  assert.match(text, /role="alert"/)
  assert.match(text, /@click="load"/)
})
