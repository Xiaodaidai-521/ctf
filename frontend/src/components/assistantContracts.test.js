import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { ref, computed, nextTick } from 'vue'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'
import { parse as parseTemplate } from '@vue/compiler-dom'

const source = readFileSync(new URL('./AIAssistant.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
function assistant(http, props = { challengeId: '42', challengeInfo: null }) {
  const mounted = []
  const watchers = []
  const script = descriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')
  const compiled = compileScript(descriptor, { id: 'assistant' })
  const bindings = Object.keys(compiled.bindings).filter(key => !compiled.imports[key] && compiled.bindings[key] !== 'props')
  const page = runInNewContext(`${script}\n;({ ${bindings.join(',')} })`, {
    ref, computed, nextTick, http, sanitizeHtml: value => value,
    onMounted: callback => mounted.push(callback), watch: (...args) => watchers.push(args),
    defineProps: () => props, defineEmits: () => () => {}, console: { error() {} },
  })
  return { page, mounted, watchers, props }
}
const plain = value => JSON.parse(JSON.stringify(value))
const redacted = { id: 7, role: 'user', content: '[历史内容未能验证材料权限，已隐藏]', redacted: true, created_at: '2026-11-02T18:00:00Z', metadata: {} }

test('assistant compiles and keeps original modes, sanitized rendering and loading guards', () => {
  const script = compileScript(descriptor, { id: 'assistant' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'AIAssistant.vue', id: 'assistant', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  for (const mode of ['single', 'multi', 'tutoring']) assert.ok(descriptor.template.content.includes(`value="${mode}"`))
  assert.match(source, /sanitizeHtml\(safeContent/)
  assert.match(source, /conversationLoading/)
  assert.doesNotMatch(source, /\/messages\//)
})

test('assistant finds an existing conversation beyond first page and retains server redaction and actual time', async () => {
  const calls = []
  const { page } = assistant({ get: async (url, options) => {
    calls.push([url, options])
    if (url.endsWith('/11/')) return { messages: [redacted] }
    return options.params.page === 1 ? { results: [{ id: 10, challenge_id: 1 }], next: 'http://server/api/ai/conversations/?page=2' } : { results: [{ id: 11, challenge_id: 42 }], next: null }
  } })
  await page.loadConversation()
  assert.equal(page.conversationId.value, 11)
  assert.deepEqual(plain(page.messages.value), [{ ...redacted, timestamp: redacted.created_at }])
  assert.deepEqual(plain(calls), [['/ai/conversations/', { params: { page: 1 } }], ['/ai/conversations/', { params: { page: 2 } }], ['/ai/conversations/11/', null]])
  assert.equal(page.conversationLoading.value, false)
})

test('assistant accepts array lists and absence without inventing history', async () => {
  const { page } = assistant({ get: async () => [] })
  await page.loadConversation()
  assert.equal(page.conversationId.value, null)
  assert.equal(page.messages.value.length, 0)
  assert.equal(page.conversationError.value, '')
})

test('assistant mount opens and reads existing history; original toggle still closes and reopens', async () => {
  let reads = 0
  const { page, mounted } = assistant({ get: async () => { reads++; return [] } })
  mounted[0]()
  await nextTick()
  assert.equal(page.isOpen.value, true)
  assert.equal(reads, 1)
  page.toggleAssistant()
  assert.equal(page.isOpen.value, false)
  page.toggleAssistant()
  await nextTick()
  assert.equal(page.isOpen.value, true)
  assert.equal(reads, 2)
})

test('failed history read is readable and does not create a duplicate conversation', async () => {
  let writes = 0
  const { page } = assistant({ get: async () => { throw Error('denied') }, post: async () => { writes++ } })
  await page.loadConversation()
  assert.match(page.conversationError.value, /重新展开/)
  page.inputMessage.value = '核查授权范围'
  await page.sendMessage()
  assert.equal(writes, 0)
  assert.equal(page.inputMessage.value, '核查授权范围')
})

test('failed creation retains input, never sends to null and serializes simultaneous sends', async () => {
  const calls = []
  let reject
  const { page } = assistant({ post: (url, data) => { calls.push([url, data]); return new Promise((_, fail) => { reject = fail }) } })
  page.inputMessage.value = '核查授权范围'
  const first = page.sendMessage()
  await page.sendMessage()
  assert.equal(calls.length, 1)
  reject(Error('unavailable'))
  await first
  assert.equal(page.inputMessage.value, '核查授权范围')
  assert.equal(page.isTyping.value, false)
  assert.deepEqual(plain(calls), [['/ai/conversations/', { challenge_id: '42' }]])
})

test('sending uses unchanged create/chat fields and displays actual response', async () => {
  const calls = []
  const { page } = assistant({ post: async (url, data) => { calls.push([url, data]); return url === '/ai/conversations/' ? { id: 11 } : { content: '先确认授权范围。', timestamp: redacted.created_at } } })
  page.inputMessage.value = '  核查授权范围  '
  await page.sendMessage()
  assert.deepEqual(plain(calls), [['/ai/conversations/', { challenge_id: '42' }], ['/ai/conversations/11/chat/', { message: '核查授权范围' }]])
  assert.equal(page.messages.value[1].content, '先确认授权范围。')
  assert.equal(page.inputMessage.value, '')
})

test('known unavailable replies are readable without replacing real answers or stored content', () => {
  const { page } = assistant({})
  assert.equal(page.formatMessage('[WARNING] AI service is not configured. Please set API Key.'), '当前解题助手暂不可用，请稍后重试。')
  assert.equal(page.formatMessage('AI service is not configured.'), '当前解题助手暂不可用，请稍后重试。')
  assert.equal(page.formatMessage('先确认授权范围。'), '先确认授权范围。')
})

test('old history response cannot populate another challenge', async () => {
  let resolve
  const { page, props } = assistant({ get: () => new Promise(done => { resolve = done }) })
  const load = page.loadConversation()
  props.challengeId = '43'
  resolve({ results: [{ id: 11, challenge_id: 42 }], next: null })
  await load
  assert.equal(page.conversationId.value, null)
  assert.equal(page.messages.value.length, 0)
})

test('admin tables keep all columns in constrained local scroll and mobile resource content remains readable', () => {
  const css = readFileSync(new URL('../admin/assets/admin.css', import.meta.url), 'utf8')
  assert.match(css, /\.table-container \{ max-width: 100%; overflow-x: auto/)
  assert.match(css, /\.table-container \.admin-table \{ min-width: var\(--table-width\)/)
  for (const name of ['Users', 'Submissions']) {
    const page = readFileSync(new URL(`../admin/views/${name}.vue`, import.meta.url), 'utf8')
    assert.match(page, /class="table-container"/)
    assert.match(page, /<style scoped src="\.\.\/assets\/admin.css"/)
  }
  const users = readFileSync(new URL('../admin/views/Users.vue', import.meta.url), 'utf8')
  assert.doesNotMatch(parse(users).descriptor.template.content, /鍏|鍒涘|淇濆|涓婁|涓嬩|绠＄|璇疯|鐢ㄦ|鉁|馃/)
  const resources = readFileSync(new URL('../shared/content/content.css', import.meta.url), 'utf8')
  assert.match(resources, /\.resource-item \{ flex-direction:column/)
  assert.match(resources, /\.resource-title \{ white-space:normal; overflow-wrap:anywhere/)
  assert.match(resources, /\.table-container \{ max-width: 100%; overflow-x: auto/)
  assert.match(resources, /\.content-table \{[^\n]*min-width: var\(--table-width\)/)
  const challenges = readFileSync(new URL('../admin/views/Challenges.vue', import.meta.url), 'utf8')
  assert.match(challenges, /<ChallengeTable[^>]*@edit="edit" @delete="remove"/)
})

test('shared create/edit challenge dialog keeps all eleven original fields and one complete panel', () => {
  const source = readFileSync(new URL('../shared/content/ChallengeEditor.vue', import.meta.url), 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const ast = parseTemplate(descriptor.template.content)
  const elements = node => (node.children || []).filter(child => child.type === 1)
  const root = elements(ast)[0]
  assert.equal(root.tag, 'ContentDialog')
  const fields = []
  const walk = node => { for (const child of elements(node)) { const model = child.props.find(prop => prop.type === 7 && prop.name === 'model'); if (model) fields.push(model.exp.content.split('.').pop()); walk(child) } }
  walk(root)
  assert.deepEqual(fields, ['title', 'category', 'difficulty', 'score', 'description', 'flag', 'hint', 'is_active', 'docker_image', 'redirect_port', 'redirect_type'])
  const dialog = parse(readFileSync(new URL('../shared/content/ContentDialog.vue', import.meta.url), 'utf8')).descriptor.template.content
  assert.match(dialog, /<dialog[\s\S]*class="dialog-header"[\s\S]*class="dialog-body"[\s\S]*class="dialog-footer"[\s\S]*<\/dialog>/)
  assert.match(source, /mode === 'edit' \? '编辑题目' : '新增题目'/)
})
