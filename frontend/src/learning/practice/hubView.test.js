import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { computed, reactive } from 'vue'
import { parse } from 'vue/compiler-sfc'
import { asList, finiteNumber } from '../contracts.js'

// 域 API 模块依赖 @/api，node 测试无法解析别名；这里只加载纯函数部分。
const pathsApiSource = readFileSync(new URL('../paths/api.js', import.meta.url), 'utf8')
  .replace(/^import .*$/gm, '')
  .replace(/^export /gm, '')
const { progressSummary } = runInNewContext(`${pathsApiSource}\n;({ progressSummary })`, { asList, finiteNumber })

const names = { paths: '学习航线', practice: '靶场' }
const plain = value => JSON.parse(JSON.stringify(value))

function component(file, props, expose) {
  const source = readFileSync(new URL(`./components/${file}.vue`, import.meta.url), 'utf8')
  const parsed = parse(source).descriptor
  const script = parsed.scriptSetup.content.replace(/^import[\s\S]*?from ['"][^'"]+['"];?\s*/gm, '')
  const bindings = runInNewContext(`${script}\n;({ ${expose.join(', ')} })`, {
    computed, names, asList, progressSummary,
    defineProps: () => reactive(props),
    defineEmits: () => () => {},
  })
  return { bindings, template: parsed.template.content }
}

test('practice summary never turns missing statistics into zero and offers a retry', () => {
  const { bindings } = component('PracticeSummary', {
    authenticated: true, stats: null, statsError: '提交统计暂时未能加载。', solvedCount: null, solvedScope: '',
  }, ['score', 'solved', 'submissions', 'headline'])
  assert.equal(bindings.score.value, '—')
  assert.equal(bindings.solved.value, '—')
  assert.equal(bindings.submissions.value, '—')

  const guest = component('PracticeSummary', { authenticated: false }, ['score', 'solved', 'headline'])
  assert.equal(guest.bindings.score.value, '登录后查看')
  assert.equal(guest.bindings.solved.value, '—')
  assert.equal(guest.bindings.headline.value, '登录后记录你的练习进度')

  const partial = component('PracticeSummary', {
    authenticated: true, stats: { score: 30, total_submissions: 8 }, solvedCount: 3, solvedScope: 'loaded',
  }, ['solved'])
  assert.equal(partial.bindings.solved.value, '3（当前已加载）')
})

test('resume entry names its real source and keeps an exit when the target is unavailable', () => {
  const local = component('ResumePractice', { candidate: { id: 7, title: '栈溢出', available: true }, source: 'local' }, ['label', 'reason'])
  assert.equal(local.bindings.label.value, '继续上次')
  assert.match(local.bindings.reason.value, /本机记录/)
  assert.doesNotMatch(local.bindings.reason.value, /最近一次未通过/)

  const recent = component('ResumePractice', { candidate: { id: 8, title: '命令注入', available: true }, source: 'recent' }, ['label', 'reason'])
  assert.equal(recent.bindings.label.value, '继续最近练习')
  assert.match(recent.bindings.reason.value, /最近一次未通过提交/)

  const stale = component('ResumePractice', { candidate: { id: 9, title: '已下架', available: false }, source: 'local' }, ['reason'])
  assert.match(stale.bindings.reason.value, /回到列表/)
  assert.match(stale.template, /查看题目/)
  assert.match(stale.template, /返回题目列表/)
})

test('path recommendations separate real recommendations, in-progress paths and optional routes', () => {
  const { bindings, template } = component('PathRecommendations', {
    recommendations: [
      { path_id: 1, path_title: '授权航线', path_difficulty: 'AP', estimated_hours: 2, reason: '最近两次提交集中在授权边界' },
      { path_id: 1, path_title: '重复推荐', reason: '重复' },
    ],
    joined: [{ learning_path: 2, path_title: '在学航线', total_modules: 4, completed_modules: 1 }],
    optional: [
      { id: 1, title: '授权航线' },
      { id: 3, title: '公开航线', difficulty: 'EX', estimated_hours: 8 },
    ],
  }, ['views'])
  const views = bindings.views.value
  assert.deepEqual(plain(views.map(v => [v.title, v.badge])), [
    ['授权航线', '推荐'], ['在学航线', '继续'], ['公开航线', '可选航线'],
  ])
  assert.equal(views[0].reason, '最近两次提交集中在授权边界')
  assert.equal(views[1].meta, '已完成 25%')
  assert.match(views[2].reason, /公开可选航线/)
  assert.doesNotMatch(views[2].reason, /适合你/)
  assert.equal(views[2].to, '/learning-paths/3')
  assert.match(template, /全部\{\{ names\.paths \}\}/)
})

test('path progress that cannot be read stays honest instead of inventing a percentage', () => {
  const { bindings } = component('PathRecommendations', {
    joined: [{ learning_path: 5, path_title: '缺进度航线' }],
  }, ['views'])
  assert.equal(bindings.views.value[0].meta, '进度暂不可读取')
})
