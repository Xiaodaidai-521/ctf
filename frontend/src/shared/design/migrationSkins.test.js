import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { parse, compileScript, compileStyle, compileTemplate } from 'vue/compiler-sfc'
import { iconCatalog, iconName } from './iconCatalog.js'
import { sequentialColor, tokenNumber, tokenValue } from './chartTokens.js'

const root = new URL('../../', import.meta.url)
const tokenSource = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8')
const tokens = new Set([...tokenSource.matchAll(/(--[\w-]+)\s*:/g)].map(match => match[1]))
const pages = [
  'teacher/CapabilityMapAdmin', 'teacher/SkillReviewAdmin', 'teacher/FeedbackCandidates',
  'teacher/TeacherLearningDashboard', 'teacher/LearningEffectAnalysis',
  'views/LearningMap/CapabilityMap', 'views/LearningMap/ChangeLog', 'views/DataLab/DataLab',
  'components/MultiAgent/MultiAgentChat', 'views/MultiAgent/MultiAgentView',
  'admin/views/legal/LegalWorkspace', 'admin/views/legal/ComplianceAgentCenter', 'admin/views/legal/ComplianceCenter',
  'components/AIAssistant', 'components/AITutorChat', 'views/ChallengeDetail', 'views/GeneratedContent',
  'views/LearningAnalytics', 'views/StudentDashboard', 'learningKnowledge/KnowledgeLibrary',
  'learningKnowledge/KnowledgeConceptSource', 'admin/views/StudentLearning', 'admin/views/LearningScores',
  'components/AbilityRadarCard', 'components/PersonalizedRecommendationCard',
  'teacher/TeacherChallengePanel', 'teacher/TeacherResourcePanel', 'admin/views/legal/AuditLogs',
  'admin/views/legal/ComplianceDashboard', 'admin/views/legal/ComplianceExercises',
  'components/AnnouncementBanner', 'components/ArticleCard', 'components/CommentItem', 'components/MermaidDiagram',
  'admin/views/Users', 'admin/views/Challenges', 'admin/views/Submissions', 'admin/views/Categories',
  'admin/views/Resources', 'admin/views/Articles', 'admin/views/Announcements', 'admin/views/Dashboard',
  'views/ResourceUpload', 'views/Leaderboard', 'views/ArticleEditor', 'views/ArticleDetail', 'views/Community',
  'components/KnowledgeMap', 'admin/views/legal/KnowledgeBase', 'shared/design/AppIcon', 'shared/forms/ReferenceImport', 'shared/forms/RecordView',
]

for (const page of pages) test(`migrated skin: ${page} compiles with scoped token styles`, () => {
  const url = new URL(`${page}.vue`, root)
  const source = readFileSync(url, 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = descriptor.script || descriptor.scriptSetup ? compileScript(descriptor, { id: 'migration' }) : { bindings: {} }
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: `${page}.vue`, id: 'migration', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  const localTokens = new Set([...source.matchAll(/(--[\w-]+)\s*[:'"]/g)].map(match => match[1]))
  for (const style of descriptor.styles) {
    assert.equal(style.scoped, true, `${page}: unscoped style`)
    const css = style.src ? readFileSync(new URL(style.src, url), 'utf8') : style.content
    assert.doesNotMatch(css, /@import|#[\da-f]{3,8}\b|rgba?\(/i)
    assert.doesNotMatch(css, /var\([^)]*\)[\da-f]{2,}\b|outline\s*:\s*none/i)
    assert.deepEqual(compileStyle({ source: css, filename: `${page}.vue`, id: 'data-v-migration', scoped: true }).errors, [])
    for (const [, name] of css.matchAll(/var\((--[\w-]+)/g)) {
      assert.ok(tokens.has(name) || localTokens.has(name), `${page}: undeclared ${name}`)
    }
  }
})

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), dir)
    return entry.isDirectory() ? files(url) : /\.(vue|js)$/.test(entry.name) ? [url] : []
  })
}

test('all remaining legacy icon names resolve to imported Arco icons, without an unknown fallback', () => {
  const adapter = readFileSync(new URL('./AppIcon.vue', import.meta.url), 'utf8')
  const imports = new Set([...adapter.split("from '@arco-design/web-vue/es/icon'")[0].matchAll(/\bIcon\w+/g)].map(match => match[0]))
  const exports = readFileSync(new URL('../../../node_modules/@arco-design/web-vue/es/icon/index.js', import.meta.url), 'utf8')
  for (const [name, component] of Object.entries(iconCatalog)) {
    assert.ok(imports.has(component), `${name}: missing adapter import ${component}`)
    assert.match(exports, new RegExp(`\\b${component}\\b`))
  }
  for (const url of files(root)) {
    if (url.pathname.endsWith('.test.js')) continue
    const source = readFileSync(url, 'utf8')
    for (const name of new Set(source.match(/\bbi-[\w-]+\b/g) || [])) assert.ok(Object.hasOwn(iconCatalog, name), `${url.pathname}: ${name}`)
    if (url.pathname.endsWith('.vue')) {
      assert.doesNotMatch(source, /<i\b[^>]*(?:\bbi\b|menu\.icon)/)
      if (!/\/(LearningKnowledge|EvidenceCard)\.vue$/.test(url.pathname)) {
        const { descriptor } = parse(source)
        assert.doesNotMatch(descriptor.template.content, /[\u{1f300}-\u{1faff}☀-➿]/u)
      }
    }
  }
  assert.equal(iconName('bi bi-bookmark'), 'bi-bookmark')
  assert.equal(iconName(['bi', 'bi-cpu']), 'bi-cpu')
  assert.equal(iconName('unknown-icon'), undefined)
  assert.match(adapter, /aria-hidden="true" focusable="false"/)
  const main = readFileSync(new URL('main.js', root), 'utf8')
  assert.doesNotMatch(main, /bootstrap-icons/)
  assert.match(main, /app\.component\('AppIcon', AppIcon\)/)
})

test('record presentation does not inherit the feedback definition grid', () => {
  const source = readFileSync(new URL('../forms/RecordView.vue', import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  assert.match(descriptor.template.content, /class="record-view"/)
  assert.doesNotMatch(source, /fb-definition/)
  const compiled = compileStyle({ source: descriptor.styles[0].content, filename: 'RecordView.vue', id: 'data-v-record', scoped: true })
  assert.deepEqual(compiled.errors, [])
  assert.match(compiled.code, /\.record-view\[data-v-record\]/)
  assert.match(compiled.code, /dl\[data-v-record\]/)
  const feedback = readFileSync(new URL('../../assets/feedback.css', import.meta.url), 'utf8')
  assert.match(feedback, /\.fb-page \.fb-definition/)
  assert.doesNotMatch(feedback, /record-view/)
})

test('legal search cards constrain mobile grid and textarea widths', () => {
  const workspace = readFileSync(new URL('../../admin/views/legal/LegalWorkspace.vue', import.meta.url), 'utf8')
  const page = readFileSync(new URL('../../admin/views/legal/KnowledgeBase.vue', import.meta.url), 'utf8')
  assert.match(workspace, /@media \(max-width: 768px\)[\s\S]*\.content-grid[\s\S]*grid-template-columns:minmax\(0, 1fr\)/)
  assert.match(workspace, /\.content-grid > \.page-card\s*\{\s*min-width:0/)
  assert.match(workspace, /\.page-header\s*\{\s*flex-direction:column;\s*align-items:stretch/)
  assert.match(page, /\.form-textarea\s*\{\s*width: 100%;\s*max-width: 100%;\s*min-width: 0;\s*box-sizing: border-box/)
})

test('learning trend identities have line and point encoding besides color', () => {
  const source = readFileSync(new URL('../../views/LearningAnalytics.vue', import.meta.url), 'utf8')
  for (const [name, symbol, line] of [['Web', 'circle', 'solid'], ['Crypto', 'rect', 'dashed'], ['Reverse', 'triangle', 'dotted']]) {
    assert.match(source, new RegExp(`name: '${name}'[^\\n]*symbol: '${symbol}', lineStyle: \\{ type: '${line}' \\}`))
  }
  assert.match(source, /tooltip: \{ trigger: 'axis' \}/)
  assert.match(source, /legend: \{ bottom: 0, icon: 'roundRect' \}/)
})

test('canvas colors and typography resolve from live shared tokens', () => {
  const original = globalThis.getComputedStyle
  const element = {}
  const values = new Map([...tokenSource.matchAll(/--([\w-]+):\s*([^;]+);/g)].map(match => [`--${match[1]}`, match[2]]))
  globalThis.getComputedStyle = target => {
    assert.equal(target, element)
    return { getPropertyValue: name => values.get(name) || '' }
  }
  try {
    assert.equal(tokenValue('surface', element), '#ffffff')
    assert.equal(tokenNumber('text-caption', element), 14)
    assert.equal(sequentialColor(0, element), 'rgb(205, 226, 251)')
    assert.equal(sequentialColor(1, element), 'rgb(28, 92, 171)')
    assert.equal(sequentialColor(-1, element), sequentialColor(0, element))
    assert.equal(sequentialColor(2, element), sequentialColor(1, element))
  } finally {
    if (original) globalThis.getComputedStyle = original
    else delete globalThis.getComputedStyle
  }
  for (const page of ['components/AbilityRadarCard', 'views/LearningAnalytics', 'admin/views/legal/ComplianceDashboard', 'components/KnowledgeMap']) {
    const { descriptor } = parse(readFileSync(new URL(`${page}.vue`, root), 'utf8'))
    assert.doesNotMatch(descriptor.scriptSetup.content, /#[\da-f]{3,8}\b|rgba?\([\d.,\s]+\)/i)
    assert.match(descriptor.scriptSetup.content, /chartTokens/)
  }
})
