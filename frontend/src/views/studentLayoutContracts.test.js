import { createAccountGuard } from '../shared/state/accountScope.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { runInNewContext } from 'node:vm'
import { ref, computed, compile, createSSRApp, h, toRaw } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { parse, compileScript, compileStyle, compileTemplate } from 'vue/compiler-sfc'
import { names } from '../shared/navigation/names.js'
import * as guideModel from '../learning/guide/model.js'
import * as pathPresentation from '../learning/paths/presentation.js'

const files = {
  home: './Home.vue',
  guide: '../learning/guide/GuideView.vue',
  dashboard: './StudentDashboard.vue',
}
const source = key => readFileSync(new URL(files[key], import.meta.url), 'utf8')
const descriptor = key => parse(source(key)).descriptor
const tokenSource = readFileSync(new URL('../shared/design/tokens.css', import.meta.url), 'utf8')
const tokenNames = new Set([...tokenSource.matchAll(/(--[\w-]+)\s*:/g)].map(match => match[1]))
const dashboardMarker = "/* 学生布局契约：必须由 role === 'student' 显式启用。 */"
const hash = value => createHash('sha256').update(value).digest('hex')

function page(key, options = {}) {
  const user = options.user || { isAuthenticated: true, userInfo: { role: 'student', id: 17 }, userName: '学习者' }
  const routes = [], drafts = []
  const router = { push: target => routes.push(target), replace: target => routes.push(target) }
  const mounted = []
  const globals = {
    ref, computed, names, createAccountGuard,
    onMounted: callback => mounted.push(callback), onBeforeUnmount() {},
    useRouter: () => router, useUserStore: () => user,
    useChallengeStore: () => options.challengeStore || { challenges: [], fetchChallenges: async () => {} },
    openTutor: (targetRouter, draft) => drafts.push({ targetRouter, draft }),
    learningLinks: [{ key: 'practice', path: '/challenges', label: names.practice, icon: 'icon-code' }],
    guideApi: options.guideApi || { paths: async () => [], reviews: async () => [], conversations: async () => [] },
    // P05：智航四块额外读真实航线/教学建议，失败与空态同原口径。
    pathsApi: { my: async () => [] }, growthApi: { teachingPlan: async () => null },
    readArtifacts: async ({ plan, paths, reviews }) => {
      const settle = async fn => { try { return { ok: true, value: await fn() } } catch { return { ok: false } } }
      const [p, t, r] = await Promise.all([settle(plan), settle(paths), settle(reviews)])
      return { plan: p.ok ? p.value : null, path: null, reviews: r.ok ? { items: [] } : { items: [], failed: true }, failures: [p.ok ? null : '教学建议', t.ok ? null : '学习航线', r.ok ? null : '复习提醒'].filter(Boolean), loadedAt: null }
    },
    ...guideModel,
    ...pathPresentation,
    PathNextStep: {},
    api: options.api || {},
    dashboardCopy: value => value, renameCopy: value => value,
    downloadRecord: options.downloadRecord || (() => {}), ChallengeCard: {},
  }
  const desc = descriptor(key)
  const script = desc.scriptSetup.content.replace(/^import[\s\S]*?from ['"][^'"]+['"];?\s*/gm, '')
  const bindings = Object.keys(compileScript(desc, { id: 'layout-contract' }).bindings)
  const state = runInNewContext(`${script}\n;({ ${bindings.join(', ')} })`, globals)
  return { state, user, routes, drafts, mounted }
}

// 真实 SFC 组件按同一编译流程参与 SSR，避免用桩组件替身骗取渲染断言。
function realComponent(url, props) {
  const desc = parse(readFileSync(new URL(url, import.meta.url), 'utf8')).descriptor
  return { props, render: compile(desc.template.content) }
}

async function html(key, instance) {
  const desc = descriptor(key)
  const app = createSSRApp({ render: compile(desc.template.content), setup: () => instance.state })
  app.component('PathNextStep', realComponent('../learning/paths/components/PathNextStep.vue', ['step', 'pending', 'showAdjust']))
  const tags = new Set([...desc.template.content.matchAll(/<([\w-]+)/g)].map(match => match[1]))
  for (const tag of tags) {
    if (!tag.startsWith('a-') && !tag.startsWith('icon-') && !['AppIcon', 'ChallengeCard', 'router-link'].includes(tag)) continue
    app.component(tag, {
      props: ['to', 'description', 'challenge'],
      setup(props, { slots }) {
        return () => h(tag === 'router-link' ? 'a' : 'div', {
          'data-component': tag,
          ...(tag === 'router-link' ? { href: props.to } : {}),
          ...(props.challenge ? { 'data-challenge-id': props.challenge.id } : {}),
        }, slots.default?.() || props.description || '')
      },
    })
  }
  return renderToString(app)
}

for (const key of Object.keys(files)) {
  test(`${key}: template/styles compile, student overrides are role-gated and token-only`, () => {
    const text = source(key)
    const desc = descriptor(key)
    assert.deepEqual(parse(text).errors, [])
    assert.deepEqual(compileTemplate({ source: desc.template.content, filename: files[key], id: 'layout-contract' }).errors, [])
    for (const style of desc.styles) {
      assert.equal(style.scoped, true)
      const compiled = compileStyle({ source: style.content, filename: files[key], id: 'data-v-layout', scoped: true })
      assert.deepEqual(compiled.errors, [])
      assert.doesNotMatch(style.content, /#[\da-f]{3,8}\b|rgba?\(|hsla?\(/i)
      const start = style.content.indexOf(key === 'dashboard' ? dashboardMarker : '/* 学生')
      assert.ok(start >= 0, 'explicitly separated student layout rules')
      const rules = compileStyle({ source: style.content.slice(start), filename: files[key], id: 'data-v-layout', scoped: true })
      assert.deepEqual(rules.errors, [])
      rules.rawResult.root.walkRules(rule => {
        for (const selector of rule.selectors) assert.match(selector, /\.(student-layout|guest-layout)\b/, selector)
      })
      for (const [, name] of style.content.matchAll(/var\((--[\w-]+)/g)) assert.ok(tokenNames.has(name) || name === '--progress-deg', `${key}: declared ${name}`)
      for (const match of style.content.matchAll(/var\((--student-[\w-]+)([^)]*)\)/g)) {
        assert.ok(['--student-hero-size', '--student-hero-gradient', '--student-console-radius'].includes(match[1]))
        assert.match(match[2], /^,\s*\S/, 'every new token has a usable fallback')
      }
    }
    assert.doesNotMatch(desc.template.content, /<canvas|<svg|粒子|72%|6 天|示例对话/)
    assert.doesNotMatch(desc.styles.map(style => style.content).join('\n'), /animation\s*:|@keyframes/)
  })
}

test('dashboard keeps the entire pre-existing teacher CSS and administrator template byte-for-byte', () => {
  const text = source('dashboard')
  const originalStyle = descriptor('dashboard').styles[0].content.split(dashboardMarker)[0]
  assert.equal(hash(originalStyle), 'e9ec6a29951af0d7bd910bfa5c2a1b3e68b68f09e8536eb7562c2664a9a757a0')
  const admin = text.slice(text.indexOf('    <!-- ===== 管理员视图'), text.indexOf('    <!-- ===== 用户视图'))
  assert.equal(hash(admin), '1888373847e12e31f90fb8bf345bd3c5919d7212ca944307b74669f1f375f5b2')
  assert.match(originalStyle, /\.card :deep\(\.arco-spin\),\s*\.card :deep\(\.arco-spin-children\)[\s\S]*?width:100%;[\s\S]*?min-width:0;/)
  assert.match(originalStyle, /@media \(max-width: 768px\)[\s\S]*?grid-template-columns:minmax\(0, 1fr\)/)
})

test('only the explicit student role receives the dashboard console and new layout; teacher cards remain unchanged', async () => {
  for (const role of ['student', 'teacher', 'admin', undefined]) {
    const instance = page('dashboard', { user: { isAuthenticated: true, userInfo: { role }, userName: '当前用户' } })
    const rendered = await html('dashboard', instance)
    assert.equal(rendered.includes('student-layout'), role === 'student')
    assert.equal(rendered.includes('id="dashboard-question"'), role === 'student')
    if (role === 'teacher') {
      for (const card of ['recommend', 'review', 'insights', 'teaching', 'articles', 'progress']) assert.ok(rendered.includes(`${card}-card`))
      instance.state.progressData.value = {}
      assert.ok((await html('dashboard', instance)).includes('progress-ring-center'), 'legacy teacher progress behavior is untouched')
    }
    if (role === 'admin') assert.ok(rendered.includes('用户总数'))
  }
})

test('guest Home uses only public challenges and keeps login/register/path/practice entrances plus empty/retry states', async () => {
  let offline = false, requests = 0
  const challengeStore = { challenges: Array.from({ length: 8 }, (_, id) => ({ id, title: `真实题目${id}` })), fetchChallenges: async () => { requests++; if (offline) throw Error('offline') } }
  const instance = page('home', { user: { isAuthenticated: false, userInfo: null }, challengeStore })
  await instance.state.load()
  assert.equal(requests, 1)
  assert.equal(instance.state.featuredChallenges.value.length, 6)
  assert.equal(toRaw(instance.state.featuredChallenges.value[0]), challengeStore.challenges[0])
  let rendered = await html('home', instance)
  assert.ok(rendered.includes('guest-layout'))
  for (const href of ['/guide', '/register', '/learning-paths', '/challenges', '/dashboard']) assert.ok(rendered.includes(`href="${href}"`))
  assert.equal((rendered.match(/data-challenge-id=/g) || []).length, 6)
  assert.match(source('home'), /<ChallengeCard\b[^>]*@click="openChallenge"/)
  instance.state.openChallenge({ id: 7 })
  assert.equal(instance.routes[0].name, 'ChallengeDetail')
  assert.equal(instance.routes[0].params.id, 7)
  challengeStore.challenges = []
  await instance.state.load()
  assert.ok((await html('home', instance)).includes('暂时没有公开练习'))
  offline = true
  await instance.state.load()
  rendered = await html('home', instance)
  assert.ok(rendered.includes('题目暂时无法读取。'))
  assert.ok(rendered.includes('重试'))
  assert.equal(instance.state.loading.value, false)
})

test('Guide keeps real conversation/path/review records, all original empty states and independent API failures', async () => {
  const instance = page('guide', { guideApi: {
    paths: async () => { throw Error('offline') },
    reviews: async () => [{ id: 9, concept_name: '真实复习知识点', recall_probability: 0.4 }],
    conversations: async () => [{ id: 3, title: '真实会话标题', message_count: 2 }],
  } })
  await instance.state.load()
  assert.deepEqual(Array.from(instance.state.failed.value), ['学习记录'])
  let rendered = await html('guide', instance)
  for (const copy of ['真实会话标题', '真实复习知识点', '学习记录暂时无法读取', '已读取的内容仍可使用', '暂不据此安排新的学习顺序']) assert.ok(rendered.includes(copy), copy)
  for (const id of ['continue-heading', 'plan-heading', 'review-heading', 'path-heading']) assert.ok(rendered.includes(`id="${id}"`))
  const empty = page('guide')
  await empty.state.load()
  rendered = await html('guide', empty)
  for (const copy of ['还没有进行中的学习', '目前没有待复习提醒', '先选一条适合自己的航线', '还没有足够的学习记录']) assert.ok(rendered.includes(copy), copy)
  assert.ok(rendered.includes('href="/learning-paths"'))
  assert.ok(rendered.includes('href="/my-results"'))
  assert.doesNotMatch(rendered, /已完成 0 \/ 0|\d+%/)
})

test('Guide shows chapter counts only when both API fields exist, without hiding the path or continuation link', async () => {
  const instance = page('guide')
  for (const [counts, expected] of [[{}, false], [{ completed_modules: null, total_modules: 4 }, false], [{ completed_modules: '', total_modules: 4 }, false], [{ completed_modules: 0, total_modules: 4 }, true], [{ completed_modules: 2, total_modules: 4 }, true]]) {
    instance.state.paths.value = [{ learning_path: 7, path_title: '真实学习航线', ...counts }]
    const rendered = await html('guide', instance)
    assert.equal(rendered.includes(' · 已完成 '), expected)
    assert.ok(rendered.includes('真实学习航线'))
    assert.ok(rendered.includes('href="/learning-paths/7"'))
  }
})

test('Guide and dashboard hand typed input and identity to the existing tutor; blank input never launches a conversation', () => {
  for (const key of ['guide', 'dashboard']) {
    const instance = page(key)
    const ask = instance.state[key === 'guide' ? 'ask' : 'askTutor']
    instance.state.question.value = '  '
    ask()
    assert.equal(instance.drafts.length, 0)
    instance.state.question.value = '我当前真实的问题'
    ask()
    assert.equal(instance.drafts.length, 1)
    assert.equal(instance.drafts[0].draft.prompt, '我当前真实的问题')
    assert.equal(instance.drafts[0].draft.userId, 17)
    assert.equal(instance.drafts[0].targetRouter, instance.state.router)
    assert.match(source(key), /@keydown\.ctrl\.enter\.prevent="(?:ask|askTutor)"/)
    assert.match(source(key), /maxlength="2000"/)
    assert.match(source(key), /继续导学对话/)
  }
})

test('student progress and memory rates are never synthesized from IDs, missing fields, invalid values or failed requests', async () => {
  const instance = page('dashboard', { api: { analytics: { progressReport: async () => { throw Error('offline') } }, submission: { stats: async () => ({}) } } })
  for (const value of [undefined, null, '', ' ', true, {}, 'bad', Infinity, -1]) {
    instance.state.progressData.value = { completion_rate: value }
    assert.equal(instance.state.hasStudentProgress.value, false)
    const rendered = await html('dashboard', instance)
    assert.doesNotMatch(rendered, /progress-ring-center|>0%/)
    assert.ok(rendered.includes('加载进度数据中...'))
    assert.ok(rendered.includes('without-student-progress'))
  }
  for (const [value, expected] of [[0, '0%'], [0.5, '50%'], ['25', '25%']]) {
    instance.state.progressData.value = { completion_rate: value }
    assert.equal(instance.state.hasStudentProgress.value, true)
    assert.ok((await html('dashboard', instance)).includes(`>${expected}</strong>`))
  }
  assert.equal(instance.state.formatMemoryRate({ id: 1, mastery_level: 1, times_viewed: 5 }), '—')
  for (const value of [undefined, null, '', true, 'bad', -0.1, 1.1]) assert.equal(instance.state.formatMemoryRate({ recall_probability: value }), '—')
  assert.equal(instance.state.formatMemoryRate({ recall_probability: 0 }), '0%')
  assert.equal(instance.state.formatMemoryRate({ recall_probability: '0.4' }), '40%')
  await instance.state.fetchProgress()
  assert.equal(instance.state.progressData.value, null)
  assert.equal(instance.state.progressLoading.value, false)
  const teacher = page('dashboard', { user: { userInfo: { role: 'teacher' } } })
  teacher.state.reviewReminders.value = [{ id: 1, concept_name: '老师原复习记录' }]
  assert.ok((await html('dashboard', teacher)).includes('记忆率 —'))
  teacher.state.reviewReminders.value[0].recall_probability = 1
  assert.ok((await html('dashboard', teacher)).includes('记忆率 100%'))
  assert.doesNotMatch(source('dashboard'), /hash %|masteryBoost|reviewBoost/)
})

test('dashboard preserves complete recommendation, review, insight, teaching and article fields and raw-record downloads', async () => {
  const instance = page('dashboard')
  instance.state.recommendations.value = [{ id: 1, type: 'next_step', title: '真实推荐标题', reason: '真实推荐依据', estimated_time: '真实时长', expected_gain: '真实预期收益', action_link: '/challenges', private_evidence: { original: true } }]
  instance.state.reviewReminders.value = [{ id: 3, concept_name: '真实复习概念', recall_probability: 0.4, challenge: { id: 2, title: '真实关联题目' } }]
  instance.state.insights.value = [{ id: 2, title: '真实洞察标题', description: '真实洞察描述', severity: 'info', extra: '原始证据' }]
  instance.state.teachingPlan.value = { validity_label: '真实方案有效性', summary: '真实方案摘要', plan_items: [{ phase: '真实阶段', title: '真实阶段标题', duration: '真实阶段时长', actions: ['真实行动一', '真实行动二', '真实行动三', '真实行动四'] }] }
  instance.state.recommendedArticles.value = [{ key: 'path-1', source: names.paths, sourceType: 'path', meta: '真实文章元数据', title: '真实文章标题', description: '真实文章描述', link: '/learning-paths/1' }]
  const rendered = await html('dashboard', instance)
  for (const copy of ['真实推荐标题', '真实推荐依据', '真实时长', '真实预期收益', '真实复习概念', '真实关联题目', '真实洞察标题', '真实洞察描述', '真实方案有效性', '真实方案摘要', '真实阶段', '真实阶段标题', '真实阶段时长', '真实行动一', '真实行动二', '真实行动三', '真实行动四', '真实文章元数据', '真实文章标题', '真实文章描述']) assert.ok(rendered.includes(copy), copy)
  assert.match(source('dashboard'), /downloadRecord\(item, '推荐依据\.json'\)/)
  assert.match(source('dashboard'), /downloadRecord\(item, '洞察依据\.json'\)/)
  const downloads = []
  const handlers = [...source('dashboard').matchAll(/@click\.stop="(downloadRecord[^\"]+)"/g)]
  for (const [index, [, handler]] of handlers.entries()) {
    const item = index === 0 ? instance.state.recommendations.value[0] : instance.state.insights.value[0]
    runInNewContext(handler, { item, downloadRecord: (record, filename) => downloads.push({ record, filename }) })
    assert.equal(downloads[index].record, item, 'download retains the original item, including fields not shown on the card')
  }
  assert.equal(downloads[0].record.private_evidence.original, true)
  assert.equal(downloads[1].record.extra, '原始证据')
  assert.match(source('dashboard'), /@click="goReviewPractice\(item\)"/)
  assert.match(source('dashboard'), /@click="completeReview\(item\)"/)
  instance.state.goReviewPractice(instance.state.reviewReminders.value[0])
  assert.equal(instance.routes[0].name, 'ChallengeDetail')
  assert.equal(instance.routes[0].params.id, 2)
})

test('dashboard retains all original data calls, completion refresh and failed/empty feedback', async () => {
  const calls = []
  const response = name => async (...args) => { calls.push([name, ...args]); return [] }
  const api = {
    studentProfile: { persona: response('persona') },
    learningAgent: { recommend: response('recommend') },
    analytics: { insights: response('insights'), progressReport: response('progressReport'), teachingPlan: response('teachingPlan') },
    submission: { stats: response('stats') },
    learningPaths: { list: response('paths'), reviewReminders: response('reviews'), completeReview: response('completeReview') },
    article: { recommend: response('articles') },
    resource: { list: response('resources') },
  }
  const instance = page('dashboard', { api })
  await Promise.all(['fetchPersona', 'fetchRecommendations', 'fetchInsights', 'fetchProgress', 'fetchRecommendedArticles', 'fetchReviewReminders', 'fetchTeachingPlan'].map(method => instance.state[method]()))
  assert.deepEqual(calls.map(call => call[0]).sort(), ['persona', 'recommend', 'insights', 'progressReport', 'stats', 'paths', 'articles', 'resources', 'reviews', 'teachingPlan'].sort())
  assert.equal(calls.find(call => call[0] === 'paths')[1].page_size, 3)
  assert.equal(calls.find(call => call[0] === 'articles')[1].limit, 3)
  assert.equal(calls.find(call => call[0] === 'resources')[1].ordering, '-view_count')
  calls.length = 0
  await instance.state.completeReview({ id: 9 })
  assert.equal(calls[0][0], 'completeReview')
  assert.equal(calls[0][1].state_id, 9)
  assert.equal(calls[0][1].success, true)
  assert.deepEqual(calls.slice(1).map(call => call[0]).sort(), ['reviews', 'progressReport', 'stats'].sort())
  assert.equal(instance.state.reviewCompletingId.value, null)
  const originalReminder = { id: 11, concept_name: '完成失败仍保留的复习项' }
  instance.state.reviewReminders.value = [originalReminder]
  api.learningPaths.completeReview = async () => { throw Error('completion offline') }
  await assert.rejects(instance.state.completeReview(originalReminder), /completion offline/)
  assert.equal(instance.state.reviewCompletingId.value, null)
  assert.equal(instance.state.reviewReminders.value[0].id, 11)
  api.learningAgent.recommend = async () => { throw Error('offline') }
  api.analytics.insights = api.analytics.teachingPlan = api.learningPaths.reviewReminders = api.article.recommend = async () => { throw Error('offline') }
  await Promise.all(['fetchRecommendations', 'fetchInsights', 'fetchRecommendedArticles', 'fetchReviewReminders', 'fetchTeachingPlan'].map(method => instance.state[method]()))
  const rendered = await html('dashboard', instance)
  for (const copy of ['暂无推荐', '暂无待复习项', '暂无洞察', '暂无教学方案', '暂无推荐文章']) assert.ok(rendered.includes(copy), copy)
})
