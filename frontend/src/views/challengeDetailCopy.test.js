import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { computed } from 'vue'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'
import { createWorkspaceSession } from '../learning/practice/workspaceSession.js'

const source = readFileSync(new URL('./ChallengeDetail.vue', import.meta.url), 'utf8')
const { descriptor, errors } = parse(source)
const script = descriptor.scriptSetup.content

test('direct challenge keeps original controls with readable labels and shared icons', () => {
  assert.deepEqual(errors, [])
  const compiled = compileScript(descriptor, { id: 'challenge-copy' })
  const template = compileTemplate({ source: descriptor.template.content, filename: 'ChallengeDetail.vue', id: 'challenge-copy', compilerOptions: { bindingMetadata: compiled.bindings } })
  assert.deepEqual(template.errors, [])
  // 直达页不再复制一套题面/提交 UI，而是复用与弹层同一个工作台。
  assert.match(descriptor.template.content, /ChallengeWorkspace/)
  assert.match(descriptor.template.content, /:challenge-id="challengeId"/)
  assert.match(descriptor.template.content, /mode="page"/)
  assert.match(descriptor.template.content, /返回靶场/)
  assert.match(source, /name="bi-chevron-left"/)
  assert.match(source, /router\.push\('\/challenges'\)/)
  assert.doesNotMatch(descriptor.template.content, /Loading challenge|Already solved|Submit Flag|Download attachment/)
})

test('direct challenge resolves the routed challenge and returns to the range', () => {
  const calls = []
  const bindings = Object.keys(compileScript(descriptor, { id: 'challenge-copy' }).bindings)
    .filter(binding => binding !== 'props' && !compiledImports().includes(binding))
  const page = runInNewContext(`${script.replace(/^import[^\n]+\n/gm, '')}\n;({ ${bindings.join(',')} })`, {
    computed,
    useRoute: () => ({ params: { id: '17' } }),
    useRouter: () => ({ push: path => calls.push(path) }),
  })
  assert.equal(page.challengeId.value, 17)
  page.handleClose()
  page.handleSolved({ challengeId: 17 })
  assert.deepEqual(calls, ['/challenges'])
})

function compiledImports() {
  return Object.keys(compileScript(descriptor, { id: 'challenge-copy' }).imports || {})
}

test('direct challenge submits original identity and Flag and retains server response', async () => {
  const calls = []
  const apiClient = {
    detail: async id => { calls.push(['detail', id]); return { id: 17, title: '直达题', description: '题面' } },
    list: async () => ({ results: [], count: 0 }),
    submit: async (id, flag) => { calls.push([id, flag]); return { success: true, message: '原判定', portrait_refreshed: false } },
    mySubmissions: async () => ({ results: [], count: 0, next: null }),
  }
  const session = createWorkspaceSession({ apiClient, challengeId: 17, userId: 9, schedule: () => 1, cancel: () => {} })
  await session.load()
  session.setFlag('flag{original}')
  const result = await session.submit()
  assert.equal(result.ok, true)
  assert.deepEqual(calls.filter(call => typeof call[0] === 'number'), [[17, 'flag{original}']])
  assert.ok(calls.some(call => call[0] === 'detail'))
  assert.equal(session.message.value, '原判定')
  assert.equal(session.flag.value, '')
  assert.equal(session.submitting.value, false)
})

test('direct challenge validation and failed sends do not create successful state', async () => {
  let sends = 0
  const apiClient = {
    detail: async () => ({ id: 17, title: '直达题', description: '题面' }),
    list: async () => ({ results: [], count: 0 }),
    submit: async () => { sends += 1; throw new Error('unavailable') },
  }
  const session = createWorkspaceSession({ apiClient, challengeId: 17, userId: 9, schedule: () => 1, cancel: () => {} })
  await session.load()

  const empty = await session.submit()
  assert.equal(empty.ok, false)
  assert.equal(sends, 0)
  assert.equal(session.message.value, '请输入 Flag')
  assert.equal(session.messageType.value, 'error')

  session.setFlag('flag{original}')
  const failed = await session.submit()
  assert.equal(failed.ok, false)
  assert.equal(sends, 1)
  assert.equal(session.flag.value, 'flag{original}')
  assert.equal(session.messageType.value, 'error')
  assert.match(session.message.value, /提交失败/)
  assert.equal(session.submitting.value, false)
})
