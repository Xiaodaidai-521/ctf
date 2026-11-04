import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { persistPath, pathSaveError } from './savePath.js'

const module = () => ({ id: 10, title: '原章节', description: '', module_type: 'theory', content: '讲解', order: 0, estimated_minutes: 30, is_required: true, prerequisites: [], challenges: [], solution_hint: '' })
const path = () => ({ id: 1, title: '原航线', description: '教学目标', difficulty: 'AP', color: '#B7352D', estimated_hours: 1, order: 0, is_published: true })
function harness() {
  let savedPath = path(), savedModule = module()
  const originalModules = [module()], chapters = [module()], form = path(), calls = []
  const api = {
    update: async (id, body) => { calls.push(['PUT path', id, body]); savedPath = { ...savedPath, ...body }; return savedPath },
    updateModule: async (id, body) => { calls.push(['PUT module', id, body]); savedModule = { ...savedModule, ...body }; return savedModule },
    create: async body => { calls.push(['POST path', body]); savedPath = { ...body, id: 2 }; return savedPath },
    createModule: async body => { calls.push(['POST module', body]); savedModule = { ...body, id: 20 }; return savedModule },
    detail: async () => savedPath, modules: async () => [savedModule],
  }
  return { calls, api, form, chapters, originalModules, originalPublished: true, current: () => true,
    acknowledged: (kind, id, chapter) => { if (kind === 'path') form.id = id; else chapter.id = id } }
}
test('existing published path saves only writable basic and chapter fields, then verifies readback', async () => {
  const h = harness(); h.form.title = '已修改航线'; h.chapters[0].content = '修改后的教学正文'
  const result = await persistPath(h)
  assert.equal(result.path.title, '已修改航线'); assert.equal(result.modules[0].content, '修改后的教学正文')
  assert.equal(h.calls[0][0], 'PUT path'); assert.equal(h.calls[1][0], 'PUT module')
  for (const call of h.calls) assert.doesNotMatch(JSON.stringify(call[2]), /chapters|prerequisites|challenges|requires|solution_hint|expanded/)
})
test('new save calls existing POST and retains acknowledged identities for partial module failures', async () => {
  const h = harness(); h.form.id = null; h.form.slug = 'unique-name'; h.originalModules = []; h.chapters[0].id = 'new-1'
  h.api.createModule = async () => { throw { response: { status: 500 } } }
  await assert.rejects(persistPath(h)); assert.equal(h.calls[0][0], 'POST path'); assert.equal(h.form.id, 2)
  assert.equal(h.calls[0][1].slug, 'unique-name')
})
test('creation rejection is not successful and does not send chapters or manufacture ids', async () => {
  const h = harness(); h.form.id = null; h.originalModules = []
  h.api.create = async () => { throw { response: { status: 500 } } }
  await assert.rejects(persistPath(h)); assert.equal(h.form.id, null); assert.equal(h.calls.length, 0)
})
test('draft change is saved and verified before complete success', async () => {
  const h = harness(); h.form.is_published = false
  const result = await persistPath(h)
  assert.equal(h.calls[0][2].is_published, false)
  assert.equal(result.path.is_published, false)
  assert.equal(h.calls[1][0], 'PUT module')
})
for (const change of ['prerequisites', 'labs', 'hint', 'delete']) test(`unsupported ${change} change is explicitly rejected before any write`, async () => {
  const h = harness()
  if (change === 'prerequisites') h.chapters[0].prerequisites = [99]
  if (change === 'labs') h.chapters[0].challenges = [{ id: 99 }]
  if (change === 'hint') h.chapters[0].solution_hint = '新提示'
  if (change === 'delete') h.chapters = []
  await assert.rejects(persistPath(h), /暂不能保存|暂不支持|暂不能保存更改/); assert.equal(h.calls.length, 0)
})
test('new draft uses generated slug when blank and verifies all acknowledged chapters', async () => {
  const h = harness(); h.form.id = null; h.form.slug = ''; h.form.is_published = false
  h.originalModules = []; h.chapters[0].id = 'new-1'
  h.api.create = async body => { h.calls.push(['POST path', body]); return { ...body, id: 2, slug: 'generated-name' } }
  h.api.detail = async () => ({ ...h.form, slug: 'generated-name' })
  const result = await persistPath(h)
  assert.equal(Object.hasOwn(h.calls[0][1], 'slug'), false)
  assert.equal(h.calls[1][0], 'POST module'); assert.equal(h.calls[1][1].learning_path, 2)
  assert.equal(result.path.slug, 'generated-name'); assert.equal(result.path.is_published, false)
  assert.equal(h.chapters[0].id, 20)
})
test('draft can publish but mismatched publication readback cannot succeed', async () => {
  const h = harness(); h.originalPublished = false; h.form.is_published = true
  assert.equal((await persistPath(h)).path.is_published, true)
  h.api.detail = async () => ({ ...h.form, is_published: false })
  await assert.rejects(persistPath(h), /读回不一致/)
})
test('adding a chapter keeps existing module identities and creates only the added chapter', async () => {
  const h = harness(), extra = { ...module(), id: 'new-2', title: '新增章节', order: 1 }
  h.chapters.push(extra)
  h.api.modules = async () => [h.chapters[0], { ...extra, id: 20 }]
  await persistPath(h)
  assert.deepEqual(h.calls.map(call => call[0]), ['PUT path', 'PUT module', 'POST module'])
  assert.equal(h.chapters[0].id, 10); assert.equal(extra.id, 20)
})
test('readback mismatch cannot become a complete success', async () => {
  const h = harness(); h.api.modules = async () => [{ ...module(), content: '旧正文' }]; h.chapters[0].content = '新正文'
  await assert.rejects(persistPath(h), /读回不一致/)
})
test('late account response does not issue a next write or acknowledged id', async () => {
  const h = harness(); h.current = () => false; h.acknowledged = () => assert.fail('late account mutation')
  assert.equal(await persistPath(h), null); assert.equal(h.calls.length, 1)
})
test('save failures explain known fields and never expose raw backend errors or HTML', () => {
  for (const status of [400, 401, 403, 404, 500]) {
    const text = pathSaveError({ response: { status, data: { title: ['internal_uuid <script>'] } } })
    assert.doesNotMatch(text, /internal_uuid|<script>|接口/); assert.ok(text)
  }
  assert.match(pathSaveError({ response: { status: 400, data: { title: ['bad'] } } }), /标题/)
})
test('management write facade calls unchanged path and module endpoints', async () => {
  const text = readFileSync(new URL('./api.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/^export /gm, '').replace(/default createPathManagementApi\(\)/, '')
  const create = runInNewContext(text + '\n;createPathManagementApi', { client: {} }), calls = []
  const methods = prefix => Object.fromEntries(['create', 'update'].map(name => [name, (...args) => calls.push([prefix, name, ...args])]))
  const api = create({ learningPaths: methods('path'), pathModules: methods('module') })
  const data = { title: '课程' }; await api.create(data); await api.update(1, data); await api.createModule(data); await api.updateModule(10, data)
  assert.deepEqual(calls, [['path', 'create', data], ['path', 'update', 1, data], ['module', 'create', data], ['module', 'update', 10, data]])
})
