import { createAccountGuard, onAccountClear } from '../../shared/state/accountScope.js'
import { persistPath, pathSaveError } from '../../shared/paths/savePath.js'
import { uiSnapshot } from '../../shared/state/retention.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { ref, reactive, computed, watch } from 'vue'
import { compileScript, compileTemplate, parse } from 'vue/compiler-sfc'

const implementation = { 'LearningPathsManage.vue': '../../shared/paths/PathManageEditor.vue', 'LearningPathsManageList.vue': '../../shared/paths/PathManageList.vue' }
const read = file => readFileSync(new URL(implementation[file] || file, import.meta.url), 'utf8')
const plain = value => JSON.parse(JSON.stringify(value))
for (const file of ['LearningPathsManage.vue', 'LearningPathsManageList.vue']) {
  test(`${file}: script and template compile`, () => {
    const { descriptor, errors } = parse(read(file))
    assert.deepEqual(errors, [])
    assert.ok(compileScript(descriptor, { id: file }).content)
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: file }).errors, [])
  })
}
function page(file, exposed, extra = {}) {
  const script = parse(read(file)).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  return runInNewContext(`${script}\n;({ ${exposed} })`, {
    createAccountGuard, onAccountClear, persistPath, pathSaveError, uiSnapshot, ref, reactive, computed, watch, onMounted() {}, onBeforeUnmount() {}, defineProps: () => ({ api: extra.api || {}, managementBase: '/teacher/learning-paths', home: '/teacher' }), useRouter: () => ({ push() {} }), useRoute: () => ({ params: {}, query: {}, path: '/teacher/learning-paths' }), ...extra,
  })
}
test('unsupported complete saving reports no success and preserves the complete editable draft', async () => {
  const messages = [], calls = []
  const p = page('LearningPathsManage.vue', 'pathForm, chapters, isNewPath, saving, savePath, loadPathData, saveError, notice', { alert: message => messages.push(message), api: { learningPaths: { create: payload => calls.push(payload), update: payload => calls.push(payload) } } })
  await p.loadPathData()
  Object.assign(p.pathForm, { title: '路径名称', slug: 'path-name', description: '路径说明', difficulty: 'PR', estimated_hours: 9, is_published: true })
  p.chapters.value = [{ title: '章节名称', description: '章节说明', module_type: 'challenge', content: '完整学习内容', order: 1, estimated_minutes: 60, is_required: true, solution_hint: '保留提示', prerequisites: [4], challenges: [{ id: 8 }] }]
  const original = plain({ path: p.pathForm, chapters: p.chapters.value })
  for (const isNew of [true, false]) {
    p.isNewPath.value = isNew
    await p.savePath()
    assert.match(p.saveError.value, /实验提示暂不能保存/)
    assert.match(p.notice.value, /尚未保存.*仍保留/)
    assert.doesNotMatch(p.saveError.value + p.notice.value, /成功|API|后端/)
    assert.deepEqual(plain({ path: p.pathForm, chapters: p.chapters.value }), original)
    assert.equal(p.saving.value, false)
  }
  assert.equal(calls.length, 0)
  const script = parse(read('LearningPathsManage.vue')).descriptor.scriptSetup.content
  for (const field of ['module_type', 'content', 'estimated_minutes', 'is_required', 'solution_hint', 'prerequisites', 'challenges']) assert.match(script, new RegExp(`${field}:`))
})
test('authorized knowledge transfer stays an unsaved four-stage chapter draft', async () => {
  let reads = 0
  const source = { title: '授权资料', publisher: '课程教研组', source_version: '课堂版', license_id: '课堂教学许可', attribution_text: '保留署名' }
  const p = page('LearningPathsManage.vue', 'pathForm, chapters, loadPathData, applyKnowledgeDraft, notice', {
    defineProps: () => ({ api: {}, managementBase: '/teacher/learning-paths', home: '/teacher', takeDraft: () => {
      reads++
      return { title: '授权资料（段落摘录）', text: '仅为授权摘录，不代表完整原文。', source }
    } }),
  })
  await p.loadPathData()
  assert.equal(p.pathForm.is_published, false)
  assert.equal(p.chapters.value.length, 1)
  const chapter = p.chapters.value[0]
  for (const stage of ['评估', '讲解', '练习', '检验']) assert.ok(chapter.content.includes(`## ${stage}`))
  assert.ok(chapter.content.includes('仅为授权摘录，不代表完整原文。'))
  assert.ok(chapter.content.includes('课堂教学许可'))
  assert.deepEqual(plain(chapter.source), source)
  assert.match(p.notice.value, /尚未保存或发布/)
  p.applyKnowledgeDraft()
  assert.equal(reads, 1)
  assert.equal(p.chapters.value.length, 1)
})
test('viewing a managed path uses the registered path detail route', () => {
  const routes = []
  const p = page('LearningPathsManageList.vue', 'viewPath', { useRouter: () => ({ push: value => routes.push(value) }) })
  p.viewPath(7)
  assert.deepEqual(routes, ['/learning-paths/7'])
})
