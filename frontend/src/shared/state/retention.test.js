import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import * as Vue from 'vue'
import * as Router from 'vue-router'
import { parse, compileScript } from 'vue/compiler-sfc'
import * as scope from './accountScope.js'
import * as retention from './retention.js'
import * as policy from './cachePolicy.js'
import { createWorkspaceSession } from '../../learning/practice/workspaceSession.js'
import { readDraft, draftCount } from '../../learning/practice/drafts.js'

const user = (id = 1, role = 'student') => ({ id, role })
const tick = async () => { for (let i = 0; i < 35; i++) await Promise.resolve(); await Vue.nextTick() }
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const read = file => readFileSync(new URL(file, import.meta.url), 'utf8')
function sfc(file, imports, globals = {}) {
  const { descriptor } = parse(read(file))
  const script = compileScript(descriptor, { id: 'state-contract', inlineTemplate: true }).content
    .replace(/import\s+([\s\S]*?)\s+from\s+['"]([^'"]+)['"];?/g, (_, binding, path) => binding.trim().startsWith('{')
      ? `const ${binding.replace(/\b(\w+)\s+as\s+(\w+)/g, '$1: $2')} = __imports[${JSON.stringify(path)}];`
      : `const ${binding.trim()} = __imports[${JSON.stringify(path)}];`)
    .replace('export default', 'const C =')
  return runInNewContext(`${script}\nC`, { __imports: { vue: Vue, 'vue-router': Router, ...imports }, ...globals })
}
function host() {
  const node = tag => ({ tag, props: {}, children: [], parent: null, scrollTop: 0, scrollLeft: 0, listeners: new Map(), addEventListener(name, fn) { this.listeners.set(name, fn) }, removeEventListener(name) { this.listeners.delete(name) }, getRootNode() { return { activeElement: null } }, focus() {},
    querySelectorAll(selector) { return walk(this).filter(n => selector === '[data-retain-scroll]' && Object.hasOwn(n.props, 'data-retain-scroll')) },
    get firstElementChild() { return this.children.find(n => !n.tag.startsWith('#')) },
  })
  const walk = n => [n, ...n.children.flatMap(walk)]
  const root = node('root')
  const renderer = Vue.createRenderer({
    createElement: node, createText: () => node('#text'), createComment: () => node('#comment'),
    setText() {}, setElementText(n, text) { n.text = text; n.children = [] },
    parentNode: n => n.parent, nextSibling: n => n.parent?.children[n.parent.children.indexOf(n) + 1] || null,
    insert(n, p, anchor) { if (n.parent) n.parent.children.splice(n.parent.children.indexOf(n), 1); const index = p.children.indexOf(anchor); p.children.splice(index < 0 ? p.children.length : index, 0, n); n.parent = p },
    remove(n) { if (n.parent) n.parent.children.splice(n.parent.children.indexOf(n), 1); n.parent = null },
    patchProp(n, key, previous, value) { n.props[key] = value },
  })
  const timers = new Map(), listeners = new Map(), scrolls = [], observers = []
  let timer = 0
  const window = { scrollY: 0, scrollX: 0,
    addEventListener: (name, fn) => { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn) },
    removeEventListener: (name, fn) => listeners.get(name)?.delete(fn),
    scrollTo(value) { scrolls.push(value); this.scrollY = value.top; this.scrollX = value.left }, requestAnimationFrame: fn => fn(),
  }
  class ResizeObserver { constructor(fn) { this.fn = fn; this.stopped = false; observers.push(this) } observe() {} disconnect() { this.stopped = true } }
  return { root, renderer, walk, window, timers, listeners, scrolls, observers, globals: { window, ResizeObserver,
    setTimeout(fn, ms) { timers.set(++timer, { fn, ms }); return timer }, clearTimeout: id => timers.delete(id),
  } }
}
async function routing({ role = 'student', staff = false, count = 2 } = {}) {
  scope.syncStateAccount(user(1, role), { force: true })
  const h = host(), records = []
  const C = sfc('./StateRouteView.vue', { './accountScope.js': scope, './retention.js': retention, './cachePolicy.js': policy }, h.globals)
  const probe = name => Vue.defineComponent({ name, setup() {
    const record = { name, draft: Vue.ref(''), mounted: 0, unmounted: 0, activated: 0 }
    records.push(record)
    Vue.onMounted(() => record.mounted++); Vue.onBeforeUnmount(() => record.unmounted++); Vue.onActivated(() => record.activated++)
    return () => Vue.h('main', { 'data-page': name }, [Vue.h('input', { value: record.draft.value }), Vue.h('div', { 'data-retain-scroll': '' })])
  } })
  const names = ['Guide', 'Challenges', ...Array.from({ length: count - 2 }, (_, i) => 'ChallengeDetail')]
  const routes = staff ? [{ path: '/teacher', component: Vue.defineComponent({ setup: () => () => Vue.h(C, { layer: 'staff' }) }), children: [
    { path: 'challenges', name: 'TeacherChallenges', component: probe('TeacherChallenges') },
    { path: 'resources', name: 'TeacherResources', component: probe('TeacherResources') },
  ] }] : names.map((name, i) => ({ path: `/page/${i}`, name: name === 'ChallengeDetail' ? undefined : name, component: probe(name), meta: {} }))
  // Distinct challenge params share a reviewed route name and exceed the cache maximum.
  if (!staff && count > 2) routes.splice(2, routes.length, { path: '/page/:id', name: 'ChallengeDetail', component: probe('ChallengeDetail') })
  routes.push({ path: '/private', name: 'ExamTaking', component: probe('ExamTaking'), meta: { cache: 'view' } })
  const router = Router.createRouter({ history: Router.createMemoryHistory(), routes })
  await router.push(staff ? '/teacher/challenges' : '/page/0')
  const app = h.renderer.createApp(C); app.use(router); app.mount(h.root); await tick()
  return { ...h, app, router, records }
}

test('cache policy hard-denies sensitive aliases, formal answers and privileged meta grants', () => {
  for (const name of ['DataLab', 'AdminDataCases', 'TeacherDataCases', 'LearningKnowledge', 'TeachingKnowledge', 'KnowledgeLibrary', 'ExamTaking', 'Profile', 'TeacherAssessment']) {
    for (const role of ['student', 'teacher', 'admin']) assert.equal(policy.cachePolicy({ name, path: '/resources/topics/data-security', meta: { cache: 'view' } }, role), 'none')
  }
  assert.equal(policy.cachePolicy({ name: 'Guide', path: '/guide' }, 'student'), 'view')
  assert.equal(policy.cachePolicy({ name: 'Guide', path: '/guide', meta: { sensitive: true } }, 'student'), 'none')
  assert.equal(policy.cachePolicy({ name: 'Guide', path: '/guide', meta: { cache: 'none' } }, 'student'), 'none')
  assert.equal(policy.cachePolicy({ name: 'AdminUsersHome', path: '/admin/users', meta: { cache: 'view' } }, 'admin'), 'ui')
  assert.equal(policy.cachePolicy({ name: 'AdminLegalDashboardHome', path: '/admin/legal', meta: { cache: 'view' } }, 'admin'), 'none')
})

test('UI snapshots and memory preferences expire, clone fields and reject old account/role handles', () => {
  scope.syncStateAccount(user(), { force: true }); let time = 0
  const a = retention.uiSnapshot('test:filters', 'student', () => time)
  const fields = { page: 3, filter: 'crypto' }; a.write(fields); fields.page = 9
  assert.equal(a.read().page, 3); const result = a.read(); result.page = 8; assert.equal(a.read().page, 3)
  const storage = retention.accountMemoryStorage('test:hub', () => time); storage.setItem('filters', 'saved')
  time = retention.RETENTION_MS; assert.equal(a.read(), null); assert.equal(storage.getItem('filters'), null)
  a.write(fields); storage.setItem('filters', 'old')
  scope.syncStateAccount(user(1, 'teacher')); a.write({ page: 50 }); storage.setItem('filters', 'late')
  assert.equal(a.read(), null); assert.equal(storage.getItem('filters'), null)
  scope.syncStateAccount(user()); assert.equal(retention.uiSnapshot('test:filters').read(), null)
  const old = scope.createAccountGuard(); scope.syncStateAccount(user(), { force: true }); assert.equal(old.current(), false)
})

test('real RouterView caches student drafts but remounts after account or role replacement', async t => {
  const p = await routing(); t.after(() => p.app.unmount())
  const guide = p.records[0]; guide.draft.value = '未发送的导学问题'
  await p.router.push('/page/1'); await tick(); assert.equal(guide.unmounted, 0)
  await p.router.push('/page/0'); await tick()
  assert.equal(p.records.filter(r => r.name === 'Guide').length, 1); assert.equal(guide.draft.value, '未发送的导学问题'); assert.ok(guide.activated >= 2)
  scope.syncStateAccount(user(2)); await tick(); assert.equal(guide.unmounted, 1)
  assert.equal(p.records.at(-1).draft.value, '')
  const next = p.records.at(-1); scope.syncStateAccount(user(2, 'teacher')); await tick(); assert.equal(next.unmounted, 1)
})

test('real staff shells never cache authorized list records; sensitive routes never keep views', async t => {
  const p = await routing({ role: 'teacher', staff: true }); t.after(() => p.app.unmount())
  const first = p.records[0]; await p.router.push('/teacher/resources'); await tick(); assert.equal(first.unmounted, 1)
  await p.router.push('/teacher/challenges'); await tick(); assert.equal(p.records.filter(r => r.name === 'TeacherChallenges').length, 2)
  await p.router.push('/private'); await tick(); const exam = p.records.at(-1)
  await p.router.push('/teacher/challenges'); await tick(); assert.equal(exam.unmounted, 1)
})

test('inactive view expiry and maximum twelve prune actual component instances', async t => {
  const p = await routing({ count: 14 }); t.after(() => p.app.unmount())
  const first = p.records[0]; await p.router.push('/page/1'); await tick()
  const expiry = [...p.timers.values()].find(item => item.ms === retention.RETENTION_MS); assert.ok(expiry); expiry.fn(); await tick(); assert.equal(first.unmounted, 1)
  for (let i = 2; i < 15; i++) { await p.router.push(`/page/${i}`); await tick() }
  assert.ok(p.records.filter(record => !record.unmounted).length <= 12)
})

test('scroll restores window and nested offsets, but hash and user input take priority', async t => {
  const p = await routing(); t.after(() => p.app.unmount())
  p.window.scrollY = 320; p.root.querySelectorAll('[data-retain-scroll]')[0].scrollLeft = 88
  await p.router.push('/page/1'); await tick(); await p.router.push('/page/0'); await tick()
  assert.equal(p.window.scrollY, 320); assert.equal(p.root.querySelectorAll('[data-retain-scroll]')[0].scrollLeft, 88)
  const observer = p.observers.at(-1); const before = p.scrolls.length
  for (const fn of p.listeners.get('wheel')) fn()
  observer.fn(); assert.equal(p.scrolls.length, before); assert.equal(observer.stopped, true)
  await p.router.push('/page/1'); await tick(); const count = p.scrolls.length
  await p.router.push('/page/0#specific-target'); await tick(); assert.equal(p.scrolls.length, count)
})

test('practice late submit and container responses cannot mutate a replaced account or rewrite drafts', async () => {
  scope.syncStateAccount(user(), { force: true })
  const submit = deferred(), container = deferred(); const calls = []
  const session = createWorkspaceSession({ userId: 1, challengeId: 8, apiClient: {
    detail: async () => { calls.push('detail'); return { id: 8 } }, list: async () => [],
    submit: () => submit.promise, container: () => container.promise, mySubmissions: async () => [],
  } })
  session.setFlag('flag{unsent}'); const pending = session.submit(), env = session.refreshEnvironment()
  scope.syncStateAccount(user(2)); submit.resolve({ success: true }); container.resolve({ status: 'running', access_url: '/old-account' })
  assert.equal((await pending).cancelled, true); await env
  assert.equal(session.message.value, ''); assert.equal(session.environment.value.info, null); assert.deepEqual(calls, [])
  assert.equal(draftCount(), 0); scope.syncStateAccount(user()); assert.equal(readDraft(1, 8), '')
  session.destroy()
})

test('practice deactivation cancels countdown and polling; activation rereads only real environment', async () => {
  scope.syncStateAccount(user(), { force: true }); const timers = new Map(); let serial = 0, reads = 0
  const session = createWorkspaceSession({ userId: 1, challengeId: 8, now: () => 1000,
    schedule: (fn, ms) => { timers.set(++serial, { fn, ms }); return serial }, cancel: timer => timers.delete(timer),
    apiClient: { startEnvironment: async () => ({ container: { status: 'running', access_url: '/practice/8', expires_at: new Date(61000).toISOString() } }), container: async () => { reads++; return { status: 'running', access_url: '/practice/8', expires_at: new Date(61000).toISOString() } } },
  })
  await session.startEnvironment(); assert.ok(timers.size > 0); session.suspend(); assert.equal(timers.size, 0)
  await session.resume(); assert.equal(reads, 1); assert.ok(timers.size > 0)
  session.destroy(); assert.equal(timers.size, 0); assert.equal(session.environment.value.info, null)
})

test('real Composer preserves close/reopen and A/B drafts, IME, send-clear and epoch invalidation', async t => {
  // Vue's real v-model directive checks these DOM constructors during updates.
  const oldDocument = globalThis.Document, oldShadowRoot = globalThis.ShadowRoot
  globalThis.Document = class {}; globalThis.ShadowRoot = class {}
  t.after(() => { if (oldDocument) globalThis.Document = oldDocument; else delete globalThis.Document; if (oldShadowRoot) globalThis.ShadowRoot = oldShadowRoot; else delete globalThis.ShadowRoot })
  scope.syncStateAccount(user(), { force: true })
  const h = host(), events = [], draftKey = Vue.ref('challenge:A'), showing = Vue.ref(true), composer = Vue.ref(null)
  const C = sfc('../../learning/agent/components/TutorComposer.vue', { '@/shared/state/accountScope.js': scope, '@/shared/state/retention.js': retention, '@/shared/design/AppIcon.vue': Vue.defineComponent({ setup: () => () => Vue.h('i') }) })
  const app = h.renderer.createApp({ setup: () => () => showing.value ? Vue.h(C, { ref: composer, draftKey: draftKey.value, onSubmit: text => events.push(text) }) : null })
  app.mount(h.root); t.after(() => app.unmount()); await tick()
  composer.value.setText('题 A 未发送问题'); showing.value = false; await tick(); showing.value = true; await tick()
  assert.equal(composer.value.getText(), '题 A 未发送问题')
  draftKey.value = 'challenge:B'; await tick(); assert.equal(composer.value.getText(), '')
  composer.value.setText('题 B 问题'); draftKey.value = 'challenge:A'; await tick(); assert.equal(composer.value.getText(), '题 A 未发送问题')
  const textarea = h.walk(h.root).find(n => n.tag === 'textarea'); textarea.props.onKeydown({ isComposing: true, ctrlKey: true, key: 'Enter', preventDefault() {} }); assert.equal(events.length, 0)
  textarea.props.onKeydown({ metaKey: true, key: 'Enter', preventDefault() {} }); await tick(); assert.deepEqual(events, ['题 A 未发送问题']); assert.equal(composer.value.getText(), '')
  showing.value = false; await tick(); showing.value = true; await tick(); assert.equal(composer.value.getText(), '')
  draftKey.value = 'challenge:B'; await tick(); assert.equal(composer.value.getText(), '题 B 问题')
  scope.syncStateAccount(user(2)); await tick(); assert.equal(composer.value.getText(), '')
  scope.syncStateAccount(user()); await tick(); assert.equal(composer.value.getText(), '')
})

function userStore(api) {
  const values = new Map([['userInfo', JSON.stringify(user())]]), listeners = new Map()
  const script = read('../../store/user.js').replace(/^import .*$/gm, '').replace('export const useUserStore', 'const useUserStore')
  const store = runInNewContext(`${script}\nuseUserStore()`, { ...Vue, ...scope, api,
    defineStore: (_, setup) => setup, console: { error() {}, warn() {} },
    localStorage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) },
    window: { addEventListener: (name, fn) => listeners.set(name, fn) },
  })
  return { store, values, listeners }
}

test('user store clears slow logout immediately and serializes a newer login after its cookie mutation', async () => {
  const logout = deferred(), calls = []
  const { store } = userStore({ auth: { csrf: async () => {}, logout: async () => { calls.push('logout'); await logout.promise }, login: async () => { calls.push('login'); return { user: user(2) } } } })
  const ending = store.logout(); assert.equal(store.userInfo.value, null)
  const entering = store.login({ username: 'next' }); await tick(); assert.deepEqual(calls, ['logout'])
  logout.resolve(); await ending; assert.equal((await entering).success, true); assert.deepEqual(calls, ['logout', 'login']); assert.equal(store.userInfo.value.id, 2)
})

test('profile success, failure and updates started for an old account cannot reinstall or log out the new one', async () => {
  const profile = deferred(), update = deferred()
  const { store } = userStore({ auth: { csrf: async () => {}, logout: async () => {}, login: async () => ({ user: user(2) }) }, user: { profile: () => profile.promise, updateProfile: () => update.promise } })
  const reading = store.fetchProfile(), writing = store.updateProfile({ nickname: 'old' })
  await store.login({}); profile.resolve(user()); update.resolve({ user: user() })
  assert.equal(await reading, null); assert.equal((await writing).success, false); assert.equal(store.userInfo.value.id, 2)
  const failing = deferred(); const other = userStore({ auth: { csrf: async () => {}, logout: async () => { throw Error('must not log out next account') }, login: async () => ({ user: user(3) }) }, user: { profile: () => failing.promise } })
  const request = other.store.fetchProfile(); const rejection = assert.rejects(request)
  await other.store.login({}); failing.reject(Error('old failure')); await rejection; assert.equal(other.store.userInfo.value.id, 3)
})

test('cross-tab storage invalidates local identity and old handles without trusting another user payload', () => {
  const { store, listeners } = userStore({})
  const old = scope.captureAccount(); listeners.get('storage')({ key: 'userInfo', newValue: JSON.stringify(user(99, 'admin')) })
  assert.equal(store.userInfo.value, null); assert.equal(scope.accountScope.value.role, 'guest'); assert.equal(old.current(), false)
})
