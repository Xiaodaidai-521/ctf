import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileStyle, compileTemplate } from 'vue/compiler-sfc'

const tokenSource = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8')
const tokens = new Set([...tokenSource.matchAll(/(--[\w-]+)\s*:/g)].map(match => match[1]))
const pages = [
  'Challenges', 'Resources', 'ExamCenter', 'SkillReview/MyResults',
  'Register', 'ProfileSetup', 'Profile',
  'LearningPaths/LearningPathsList', 'LearningPaths/LearningPathsManageList', 'LearningPaths/LearningPathsManage',
]
// 记录区子视图迁到 learning/exams/components，同样按设计语言与令牌校验。
const relocated = {
  'learning/exams/components/ExamRecords': '../../learning/exams/components/ExamRecords.vue',
  'learning/exams/components/ExamRecordDetail': '../../learning/exams/components/ExamRecordDetail.vue',
  'learning/exams/components/ExamOverview': '../../learning/exams/components/ExamOverview.vue',
  'shared/paths/PathManageEditor': '../../shared/paths/PathManageEditor.vue',
  'shared/paths/PathManageList': '../../shared/paths/PathManageList.vue',
  'teacher/paths/LearningPathsManage': '../../teacher/paths/LearningPathsManage.vue',
  'teacher/paths/LearningPathsManageList': '../../teacher/paths/LearningPathsManageList.vue',
}
for (const [page, file] of [...pages.map(name => [name, `../../views/${name}.vue`]), ...Object.entries(relocated), ['components/ChallengeCard', '../../components/ChallengeCard.vue'], ['components/ResourceCard', '../../components/ResourceCard.vue']]) test(`phase-one skin: ${page} compiles and uses declared tokens`, () => {
  const source = readFileSync(new URL(file, import.meta.url), 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: `${page}.vue`, id: 'skin' }).errors, [])
  for (const style of descriptor.styles) {
    assert.equal(style.scoped, true)
    const styleContent = style.src ? readFileSync(new URL(style.src, new URL(file, import.meta.url)), 'utf8') : style.content
    const compiled = compileStyle({ source: styleContent, filename: `${page}.vue`, id: 'data-v-skin', scoped: true })
    assert.deepEqual(compiled.errors, [])
    assert.doesNotMatch(styleContent, /#[\da-f]{3,8}\b|rgba?\(/i)
    assert.doesNotMatch(styleContent, /@import/)
    assert.doesNotMatch(compiled.code, /\.is-compact\s*\{/)
    for (const [, name] of styleContent.matchAll(/var\((--[\w-]+)/g)) {
      assert.ok(tokens.has(name) || ['--path-color', '--confidence'].includes(name), `${page}: ${name}`)
    }
  }
})
test('feedback rules stay within the feedback page and retain compact forms', () => {
  const css = readFileSync(new URL('../../assets/feedback.css', import.meta.url), 'utf8')
  for (const line of css.trim().split('\n')) assert.match(line, /^(\.fb-page|\.is-compact \.fb-page)/)
  assert.doesNotMatch(css, /#[\da-f]{3,8}\b|rgba?\(/i)
  assert.match(css, /:focus-visible/)
  assert.match(css, /:disabled/)
  assert.match(css, /\.is-compact .*\.fb-form-grid/)
})
