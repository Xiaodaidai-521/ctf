import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { ref, computed, reactive, watch } from 'vue'
import { parse, compileScript, compileStyle, compileTemplate } from 'vue/compiler-sfc'
import * as pathsPresentation from '../../learning/paths/presentation.js'
import * as moduleLearning from '../../learning/paths/moduleLearning.js'
import { asList } from '../../learning/contracts.js'

const require = createRequire(import.meta.url)
const tokens = new Set([...readFileSync(new URL('../../shared/design/tokens.css', import.meta.url), 'utf8').matchAll(/(--[\w-]+)\s*:/g)].map(match => match[1]))
const iconExports = readFileSync(require.resolve('@arco-design/web-vue/es/icon/index.js'), 'utf8')
const main = readFileSync(new URL('../../main.js', import.meta.url), 'utf8')
const pages = ['LearningPathDetail', 'ModuleLearning']
const load = name => parse(readFileSync(new URL(`./${name}.vue`, import.meta.url), 'utf8')).descriptor
const loadComponent = name => parse(readFileSync(new URL(`../../learning/paths/components/${name}.vue`, import.meta.url), 'utf8')).descriptor
const normalize = value => value.split('\n').map(line => line.trimEnd()).join('\n')

function nodes(root) {
  return [root, ...(root.children || []).flatMap(nodes)]
}
function directives(page, name) {
  return nodes(load(page).template.ast).flatMap(node => node.props || []).filter(prop => prop.type === 7 && prop.name === name)
}
function expressions(page) {
  return nodes(load(page).template.ast).filter(node => node.type === 5).map(node => normalize(node.content.content).trim())
}
function requireExpressions(page, expected) {
  const actual = expressions(page)
  for (const expression of expected) assert.ok(actual.includes(expression), `${page} must retain ${expression}`)
}
function requireEvents(page, expected) {
  const actual = directives(page, 'on').map(prop => `${prop.arg.content}${prop.modifiers.map(modifier => `.${modifier.content || modifier}`).join('')}: ${prop.exp.content}`)
  for (const event of expected) assert.ok(actual.includes(event), `${page} must retain ${event}`)
}

for (const page of pages) {
  test(`${page}: template, script and scoped CSS compile`, () => {
    const descriptor = load(page)
    const script = compileScript(descriptor, { id: 'learning-skin' })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: `${page}.vue`, id: 'learning-skin', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
    assert.equal(descriptor.styles.length, 1)
    assert.equal(descriptor.styles[0].scoped, true)
    const style = compileStyle({ source: descriptor.styles[0].content, filename: `${page}.vue`, id: 'data-v-learning-skin', scoped: true })
    assert.deepEqual(style.errors, [])
    assert.doesNotMatch(style.code, /\.is-compact\s*\{|\.is-compact\[data-v-/)
    assert.match(style.code, /\.is-compact [^{]+\[data-v-learning-skin\]/)
  })

  test(`${page}: uses declared semantic tokens and globally registered Arco icons`, () => {
    const descriptor = load(page)
    const css = descriptor.styles[0].content
    assert.doesNotMatch(css + descriptor.template.content, /#[\da-f]{3,8}\b|rgba?\(|hsla?\(|gradient\(|\bbi(?:-|\s)|[\p{Extended_Pictographic}✕]/iu)
    assert.doesNotMatch(css, /@import|\b\d+(?:px|rem|em)\b/)
    for (const [, token] of css.matchAll(/var\((--[\w-]+)/g)) assert.ok(tokens.has(token), `${page}: unknown ${token}`)
    for (const [, value] of css.matchAll(/box-shadow:\s*([^;}]*)/g)) assert.match(value, /^(?:none|var\(--shadow-(?:raised|overlay)\))$/)
    assert.match(css, /:focus-visible/)
    assert.match(css, /:disabled/)
    assert.match(css, /:hover/)
    assert.match(css, /:active/)
    assert.match(css, /prefers-reduced-motion: reduce/)
    assert.match(css, /\.spinner\s*\{\s*animation: none/)
    assert.match(main, /app\.use\(ArcoIcon\)/)
    const icons = [...descriptor.template.content.matchAll(/<(icon-[\w-]+)/g)]
    assert.ok(icons.length > 0)
    for (const [, tag] of icons) {
      const component = tag.split('-').map(part => part[0].toUpperCase() + part.slice(1)).join('')
      assert.ok(iconExports.includes(`as ${component} }`), `${page}: missing global ${component}`)
    }
  })

}

test('module back action uses the shared learning-path name', () => {
  const descriptor = load('ModuleLearning')
  assert.match(descriptor.template.content, /返回\{\{ names\.paths \}\}/)
  assert.match(descriptor.scriptSetup.content, /import \{ names \} from '@\/shared\/navigation\/names'/)
})

// P14 页面脚本以真实导出的呈现函数执行，不注入页面里不存在的接口。
function harness(api, exposed) {
  const pushes = []
  const timers = []
  const script = load('LearningPathDetail').scriptSetup.content.replace(/^import [\s\S]*?from ['"][^'"]+['"];?\s*$/gm, '')
  const deps = {
    ref, computed, reactive, watch, api,
    onMounted: () => {},
    useRoute: () => ({ params: { id: '7' } }),
    useRouter: () => ({ push: value => { pushes.push(value); return Promise.resolve() } }),
    names: { paths: '学习航线' },
    pathsApi: api.pathsApi,
    PathNextStep: {},
    setTimeout: callback => { timers.push(callback) },
    clearTimeout: () => {},
    ...pathsPresentation,
  }
  const run = new Function(...Object.keys(deps), `${script}\nreturn { ${exposed.join(', ')} }`)
  return { ...run(...Object.values(deps)), pushes, timers }
}

function detailApi({ path = { id: 7, title: '授权航线', total_modules: 2, total_labs: 1, estimated_hours: 2 }, modules = [{ id: 1, title: '第一章', order: 1, requires: [], labs: [] }, { id: 2, title: '第二章', order: 2, requires: [1], labs: [] }], progress } = {}) {
  const calls = []
  return {
    calls,
    pathsApi: {
      detail: async id => { calls.push(['detail', id]); if (path instanceof Error) throw path; return path },
      modules: async params => { calls.push(['modules', params]); if (modules instanceof Error) throw modules; return modules },
      progress: async id => {
        calls.push(['progress', id])
        if (progress instanceof Error) throw progress
        return progress
      },
      start: async id => { calls.push(['start', id]); return { learning_path: Number(id), progress_percentage: 0, completed_modules: 0, total_modules: 2, current_module: 1 } },
    },
  }
}

test('path detail reads per-path progress, keeps 404 apart from read failures, and never joins on read', async () => {
  const joined = detailApi({ progress: { learning_path: 7, progress_percentage: 50, completed_modules: 1, total_modules: 2, current_module: 2, started_at: '2026-11-01T00:00:00Z' } })
  const state = harness(joined, ['loadPath', 'progressState', 'progress', 'currentChapter', 'moduleList', 'pathError', 'pathNotFound'])
  await state.loadPath()
  assert.equal(state.progressState.value, 'joined')
  assert.equal(state.progress.value.countLabel, '已完成 1 / 2 章节')
  assert.equal(state.currentChapter.value.to, '/learning-paths/7/modules/2')
  assert.equal(state.moduleList.value.find(item => item.id === 2).isCurrent, true)
  assert.ok(joined.calls.every(call => call[0] !== 'start'))

  const notFound = new Error('未加入'); notFound.response = { status: 404 }
  const absent = harness(detailApi({ progress: notFound }), ['loadPath', 'progressState', 'progressError', 'progress', 'continueLearning'])
  await absent.loadPath()
  assert.equal(absent.progressState.value, 'notJoined')
  assert.equal(absent.progressError.value, '')
  await absent.continueLearning()
  assert.deepEqual(absent.pushes, [])

  const broken = new Error('boom'); broken.response = { status: 500, data: { detail: 'INTERNAL_SQL_DETAIL' } }
  const failed = harness(detailApi({ progress: broken }), ['loadPath', 'progressState', 'progressError'])
  await failed.loadPath()
  assert.equal(failed.progressState.value, 'failed')
  assert.doesNotMatch(failed.progressError.value, /INTERNAL_SQL_DETAIL/)
  assert.match(failed.progressError.value, /稍后重试/)
})

test('path join uses the original start action and only trusts progress for this path', async () => {
  const api = detailApi({ progress: (() => { const error = new Error('未加入'); error.response = { status: 404 }; return error })() })
  const state = harness(api, ['loadPath', 'startLearning', 'progressState', 'progress', 'starting', 'joinMessage'])
  await state.loadPath()
  assert.equal(state.progressState.value, 'notJoined')
  await state.startLearning()
  assert.equal(state.starting.value, false)
  assert.equal(state.progressState.value, 'joined')
  assert.equal(state.progress.value.percent, 0)
  assert.equal(api.calls.filter(call => call[0] === 'start').length, 1)

  const wrong = detailApi({ progress: null })
  wrong.pathsApi.start = async () => ({ learning_path: 99, progress_percentage: 100 })
  const mismatch = harness(wrong, ['startLearning', 'progressState', 'joinMessage'])
  await mismatch.startLearning()
  assert.equal(mismatch.progressState.value, 'loading')
  assert.match(mismatch.joinMessage.value, /未能确认/)
})

test('path continue follows only the server current module and explains when it is missing', async () => {
  const noCurrent = detailApi({ progress: { learning_path: 7, progress_percentage: 50, completed_modules: 1, total_modules: 2 } })
  const state = harness(noCurrent, ['loadPath', 'continueLearning', 'currentChapter', 'message'])
  await state.loadPath()
  // 页面展示用的 nextStep 说明缺当前章节；进入判定要求后端当前章节可核对。
  assert.equal(state.currentChapter.value.chapterKnown, false)
  await state.continueLearning()
  assert.deepEqual(state.pushes, [])
  assert.match(state.message.text, /不按完成总数推测/)

  const titleOnly = detailApi({
    modules: new Error('offline'),
    progress: { learning_path: 7, progress_percentage: 50, completed_modules: 1, total_modules: 2, current_module: 2, current_module_title: '第二章' },
  })
  const degraded = harness(titleOnly, ['loadPath', 'currentChapter', 'modulesError'])
  await degraded.loadPath()
  assert.equal(degraded.currentChapter.value.to, '/learning-paths/7/modules/2')
  assert.match(degraded.modulesError.value, /稍后重试/)
})

test('path detail surfaces server progress anomalies and 404 routes without creating records', async () => {
  const anomaly = detailApi({ progress: { learning_path: 7, progress_percentage: 140, completed_modules: 3, total_modules: 2, current_module: 2 } })
  const state = harness(anomaly, ['loadPath', 'progress'])
  await state.loadPath()
  assert.equal(state.progress.value.anomaly, true)
  assert.equal(state.progress.value.rawPercent, 140)

  const missing = new Error('not found'); missing.response = { status: 404 }
  const gone = harness(detailApi({ path: missing }), ['loadPath', 'pathError', 'pathNotFound'])
  await gone.loadPath()
  assert.equal(gone.pathNotFound.value, true)
  assert.match(gone.pathError.value, /可能已下架/)
})

test('path detail template keeps join, continue, chapter list, graph entry and honest gaps', () => {
  const template = load('LearningPathDetail').template.content
  requireEvents('LearningPathDetail', [
    'click: goBack', 'click: loadPath', 'click: loadProgress', 'click: startLearning',
    'click: loadModules', 'click: goToModule(module)', 'click: graphNoteVisible = true',
    'confirm: continueLearning',
  ])
  requireExpressions('LearningPathDetail', [
    'detail.title', 'detail.description', 'detail.difficultyLabel',
    'detail.chapterKnown ? `${detail.chapterCount} 章` : \'未提供\'', 'detail.labCount === null ? \'未提供\' : `${detail.labCount} 个`', 'detail.hoursLabel', 'progress.countLabel', 'progress.startedLabel',
    'progress.rawPercent', 'progress.labLabel', 'module.title', 'module.typeLabel',
    'module.minutesLabel', 'module.labLabel', 'module.requires.join(\'、\')',
  ])
  assert.match(template, /:disabled="starting" :aria-busy="starting"/)
  assert.match(template, /role="alert">\{\{ progressError \}\}/)
  assert.match(template, /读取失败不代表尚未加入/)
  assert.match(template, /数据异常：后台记录进度为 \{\{ progress\.rawPercent \}\}%/)
  assert.match(template, /完整航线图谱接口尚未提供/)
  assert.match(template, /不以编号充当名称/)
  assert.match(template, /进入章节不会自动开始学习/)
  const conditions = [...directives('LearningPathDetail', 'if'), ...directives('LearningPathDetail', 'else-if')].map(prop => prop.exp.content)
  for (const condition of ['pathLoading', 'pathError', "progressState === 'failed'", "progressState === 'joined'", 'modulesLoading', 'modulesError', '!moduleList.length', 'message.visible', 'progress.anomaly']) {
    assert.ok(conditions.includes(condition), condition)
  }
})


test('compact reflow stays page-scoped and keeps all learning sections visible', () => {
  const path = load('LearningPathDetail').styles[0].content
  const module = load('ModuleLearning').styles[0].content
  assert.match(path, /\.is-compact \.path-detail-page :is\(\.join-panel, \.detail-grid\)\s*\{\s*grid-template-columns: minmax\(0, 1fr\)/)
  assert.match(path, /\.is-compact \.path-detail-page \.module-main\s*\{\s*flex-wrap: wrap/)
  assert.match(path, /\.is-compact \.path-detail-page \.join-actions\s*\{\s*flex-direction: column/)
  assert.match(module, /\.is-compact \.module-learning-page :is\(\.learning-columns\.has-labs\)\s*\{\s*grid-template-columns: minmax\(0, 1fr\)/)
  assert.match(module, /\.is-compact \.module-learning-page \.module-nav\s*\{\s*flex-direction: column/)
  assert.match(module, /\.is-compact \.module-learning-page \.header-actions \.btn\s*\{\s*flex: 1/)
  assert.doesNotMatch(path + module, /display:\s*none|visibility:\s*hidden|line-clamp/)
  assert.match(path, /\.progress-circle\s*\{[^}]*position: relative/)
  assert.match(path, /\.progress-circle \.progress-text\s*\{[^}]*position: absolute/)
  assert.doesNotMatch(path, /(?:^|\n)\.progress-text\s*\{[^}]*position: absolute/)
  // 章节两栏只加在读取完成后的容器上，不落在单一加载容器里。
  assert.match(load('ModuleLearning').template.content, /<div class="learning-columns" :class="\{ 'has-labs': labs\.length \}">/)
})

// P15：章节页以真实导出的模块客户端执行，不注入 saveNotes/graph 等不存在的函数。
function moduleHarness(client, exposed, options = {}) {
  const calls = []
  const warnings = []
  const alerts = []
  const storage = new Map()
  const pathsApi = {
    detail: async id => { calls.push(['path', id]); return { id: Number(id), title: '授权航线', difficulty: 'AP' } },
    module: async id => {
      calls.push(['module', id])
      if (options.moduleError) throw options.moduleError
      return options.module || { id: Number(id), title: '第一章', module_type: 'theory', content: '## 要点\n\n先确认范围。', estimated_minutes: 20, requires: [], labs: [] }
    },
    modules: async params => {
      calls.push(['catalog', params])
      if (options.catalogError) throw options.catalogError
      return options.catalog || [{ id: 12, title: '第一章', order: 1 }, { id: 13, title: '第二章', order: 2 }]
    },
    startModule: async id => { calls.push(['start', id]); if (options.startError) throw options.startError; return { id: 1, module: Number(id), status: 'IN_PROGRESS', started_at: '2026-11-03T10:00:00Z' } },
    completeModule: async id => {
      calls.push(['complete', id])
      if (options.completeError) throw options.completeError
      return { id: 1, module: Number(id), status: 'COMPLETED', started_at: '2026-11-03T10:00:00Z', completed_at: '2026-11-03T11:00:00Z' }
    },
  }
  const script = load('ModuleLearning').scriptSetup.content.replace(/^import [\s\S]*?from ['"][^'"]+['"];?\s*$/gm, '')
  const deps = {
    ref, computed, reactive, watch, asList,
    onMounted: () => {},
    onBeforeUnmount: () => {},
    onBeforeRouteLeave: callback => { deps.__leave = callback },
    onBeforeRouteUpdate: callback => { deps.__update = callback },
    useRoute: () => ({ params: { pathId: '7', moduleId: '12' } }),
    useRouter: () => ({ push: value => calls.push(['push', value]) }),
    useUserStore: () => ({ userInfo: { id: 17 } }),
    pathsApi,
    names: { paths: '学习航线' },
    marked: content => `<p>${content}</p>`,
    sanitizeHtml: html => `sanitized:${html}`,
    localStorage: {
      getItem: key => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    },
    navigator: { clipboard: { writeText: async value => calls.push(['clipboard', value]) } },
    URL: { createObjectURL: () => 'blob:local', revokeObjectURL: () => {} },
    Blob: class { constructor(parts) { calls.push(['blob', parts[0]]) } },
    document: { createElement: () => ({ click() { calls.push(['download']) } }) },
    window: { confirm: () => options.confirmLeave ?? true, addEventListener() {}, removeEventListener() {} },
    setTimeout: () => 0,
    clearTimeout: () => {},
    ...moduleLearning,
  }
  const run = new Function(...Object.keys(deps), `${script}\nreturn { ${exposed.join(', ')} }`)
  return { ...run(...Object.values(deps)), calls, storage, deps, __client: client }
}

test('module learning reads only real serializer fields and never starts on read', async () => {
  const state = moduleHarness(null, ['loadData', 'view', 'requires', 'position', 'labs', 'status', 'notesStatus', 'renderedContent', 'error'])
  await state.loadData()
  assert.equal(state.view.value.title, '第一章')
  assert.equal(state.view.value.typeLabel, '理论')
  assert.equal(state.view.value.minutesLabel, '20 分钟')
  assert.equal(state.renderedContent.value, 'sanitized:<p>## 要点\n\n先确认范围。</p>')
  assert.equal(state.position.value.label, '第 1 / 2 章')
  assert.equal(state.position.value.next.to, '/learning-paths/7/modules/13')
  assert.equal(state.status.value.known, false)
  assert.match(state.status.value.label, /尚未读取/)
  assert.equal(state.labs.value.length, 0)
  assert.ok(state.calls.every(call => call[0] !== 'start' && call[0] !== 'complete'))
})

test('module start and complete follow real responses; missing progress is explained honestly', async () => {
  const state = moduleHarness(null, ['loadData', 'startModule', 'markComplete', 'status', 'message'])
  await state.loadData()
  await state.startModule()
  assert.equal(state.status.value.status, 'IN_PROGRESS')
  assert.equal(state.status.value.canComplete, true)
  await state.markComplete()
  assert.equal(state.status.value.status, 'COMPLETED')
  assert.equal(state.status.value.label, '已完成')
  assert.match(state.message.text, /不代表已独立掌握/)
  assert.deepEqual(state.calls.filter(call => call[0] === 'complete'), [['complete', '12']])

  const missing = new Error('no progress'); missing.response = { status: 404, data: { error: '未找到模块进度' } }
  const blocked = moduleHarness(null, ['markComplete', 'status', 'message'], { completeError: missing })
  await blocked.markComplete()
  assert.match(blocked.message.text, /请先点击“开始学习”/)
  assert.equal(blocked.status.value.status, '')

  const prereq = new Error('prereq'); prereq.response = { status: 400, data: { error: '请先完成前置模块' } }
  const halted = moduleHarness(null, ['startModule', 'message'], { startError: prereq })
  await halted.startModule()
  assert.match(halted.message.text, /先完成前置模块|先修条件/)
  assert.equal(halted.message.type, 'warning')

})

test('module page never fakes notes, labs, terminal output or path graph', async () => {
  const template = load('ModuleLearning').template.content
  const script = load('ModuleLearning').scriptSetup.content
  assert.doesNotMatch(script, /setTimeout\([^)]*terminal|terminalOutput|refreshTerminal|submitFlag|saveNotes|getNotes|labProgress|\.markComplete/)
  assert.doesNotMatch(script, /console\.(log|error)/)
  assert.doesNotMatch(script, /alert\(/)
  assert.match(script, /pathsApi\.startModule/)
  assert.match(script, /pathsApi\.completeModule/)
  assert.match(script, /localStorage\.setItem/)
  assert.match(script, /onBeforeRouteLeave/)
  assert.match(template, /不称已独立掌握/)
  const labsTemplate = loadComponent('ModuleLabs').template.content
  assert.match(labsTemplate, /查看说明/)
  assert.match(labsTemplate, /当前不可提交/)
  assert.match(labsTemplate, /待接口接入/)
  for (const component of ['ModuleContent', 'ModuleNotes', 'ModuleLabs', 'PathConceptPreview']) {
    assert.ok(template.includes(`<${component}`), component)
  }
  const labs = loadComponent('ModuleLabs')
  assert.doesNotMatch(labs.scriptSetup.content, /api\.|axios|fetch\(/)
  assert.match(labs.template.content, /实验环境与提交/)

  const state = moduleHarness(null, ['loadData', 'notes', 'notesStatus', 'saveLocal', 'copyNotes', 'downloadNotes', 'message', 'labs', 'capability'])
  await state.loadData()
  assert.match(state.notesStatus.value.note, /没有章节笔记读写接口/)
  state.notes.value = '我记下的要点'
  assert.equal(state.notesStatus.value.dirty, true)
  assert.equal(state.notesStatus.value.statusLabel, '尚未保存 · 仅在当前浏览器')
  assert.equal(state.deps.__leave() === false || state.deps.__leave() === true, true)
  state.saveLocal()
  assert.equal(state.notesStatus.value.dirty, false)
  assert.ok([...state.storage.values()].includes('我记下的要点'))
  await state.copyNotes()
  assert.deepEqual(state.calls.find(call => call[0] === 'clipboard'), ['clipboard', '我记下的要点'])
  state.downloadNotes()
  assert.ok(state.calls.some(call => call[0] === 'blob'))
  assert.equal(state.capability.canSubmit, false)
  assert.match(state.capability.reason, /没有题目编号/)
})

test('module labs render only association summary fields and requires map to readable titles', async () => {
  const module = {
    id: 12, title: '第一章', module_type: 'practice', content: '',
    requires: [13, 99],
    labs: [
      { id: 2, order: 2, is_optional: true, lab_title: '实验二', lab_description: '说明二', lab_difficulty: 'PR', lab_score: 15 },
      { id: 1, order: 1, is_optional: false, lab_title: '', lab_description: '', lab_difficulty: '', lab_score: null },
    ],
  }
  const catalog = [{ id: 12, title: '第一章', order: 1 }, { id: 13, title: '第二章', order: 2 }]
  const state = moduleHarness(null, ['loadData', 'labs', 'requires', 'view'], { module, catalog })
  await state.loadData()
  assert.deepEqual(state.labs.value.map(lab => lab.title), ['实验名称未提供', '实验二'])
  assert.deepEqual(state.labs.value.map(lab => lab.scoreLabel), ['分值未提供', '15 分'])
  assert.equal(state.labs.value[1].optional, true)
  assert.equal(state.labs.value[1].difficultyLabel, '进阶')
  assert.match(state.requires.value.label, /第二章/)
  assert.match(state.requires.value.label, /1 项先修未能从章节目录读取名称/)
  assert.doesNotMatch(state.requires.value.label, /99/)

  const failed = moduleHarness(null, ['loadData', 'error', 'requires'], { catalogError: new Error('offline'), module: { id: 12, title: '第一章', requires: [13] } })
  await failed.loadData()
  assert.equal(failed.error.value, '')
  assert.match(failed.requires.value.label, /未能从章节目录读取名称/)
})

test('module page keeps breadcrumb, content fallback and honest graph entry', () => {
  const template = load('ModuleLearning').template.content
  requireEvents('ModuleLearning', [])
  assert.match(template, /返回\{\{ names\.paths \}\}/)
  assert.match(template, /:to="`\/learning-paths\/\$\{pathId\}`"/)
  assert.match(loadComponent('ModuleContent').template.content, /本章节暂未提供教材内容/)
  const preview = loadComponent('PathConceptPreview').template.content
  assert.match(preview, /查看完整图谱说明/)
  assert.match(preview, /不拿全部概念或固定条数冒充本航线图谱/)
  assert.match(template, /章节目录暂未读取，无法显示上一章\/下一章/)
  const conditions = [...directives('ModuleLearning', 'if'), ...directives('ModuleLearning', 'else-if')].map(prop => prop.exp.content)
  for (const condition of ['loading', 'error', 'status.canStart', 'status.canComplete', 'message.visible']) {
    assert.ok(conditions.includes(condition), condition)
  }
})

test('real exported API client exposes module start/complete/labs wrappers (comment-swallow regression)', async () => {
  const { default: client } = await import('../../api/index.js')
  for (const method of ['list', 'detail', 'start', 'complete', 'labs']) {
    assert.equal(typeof client.pathModules[method], 'function', `pathModules.${method}`)
  }
  for (const method of ['list', 'detail', 'start', 'progress', 'my']) {
    assert.equal(typeof client.learningPaths[method], 'function', `learningPaths.${method}`)
  }
  // 页面与领域客户端指向同一组真实包装；不再调用不存在的 saveNotes/markComplete/submitFlag。
  const page = load('ModuleLearning').scriptSetup.content
  assert.match(page, /pathsApi\.startModule\(moduleId\.value\)/)
  assert.match(page, /pathsApi\.completeModule\(moduleId\.value\)/)
  const source = readFileSync(new URL('../../api/index.js', import.meta.url), 'utf8')
  const moduleBlock = source.slice(source.indexOf('pathModules:'), source.indexOf('learningProgress:'))
  assert.doesNotMatch(moduleBlock, /saveNotes|getNotes|markComplete|submitFlag/)
  assert.match(source, /start: \(id\) => api\.post\(`\/learning-paths\/modules\/\$\{id\}\/start\/`\)/)
  assert.match(source, /complete: \(id\) => api\.post\(`\/learning-paths\/modules\/\$\{id\}\/complete\/`\)/)
  assert.match(source, /labs: \(id\) => api\.get\(`\/learning-paths\/modules\/\$\{id\}\/labs\/`\)/)
})

test('module read failures separate not-found from network errors without leaking backend text', async () => {
  const gone = new Error('not found'); gone.response = { status: 404, data: 'No PathModule matches the given query.' }
  const state = moduleHarness(null, ['loadData', 'error', 'view'], { moduleError: gone })
  await state.loadData()
  assert.equal(state.error.value, '章节不存在或已下架，请返回航线详情重新选择章节。')
  const broken = new Error('boom'); broken.response = { status: 500, data: { detail: 'INTERNAL_SQL_DETAIL' } }
  const failed = moduleHarness(null, ['loadData', 'error'], { moduleError: broken })
  await failed.loadData()
  assert.doesNotMatch(failed.error.value, /INTERNAL_SQL_DETAIL/)
  assert.match(failed.error.value, /稍后重试/)
})
