import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { ref } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import { canOpen } from './access.js'
import { safeReturnPath, loginDestination, loginUrl, loginReturnDestination } from './returnTarget.js'
import { http } from '../../api/index.js'

function routerForReturn() {
  const component = { render: () => null }
  return createRouter({ history: createMemoryHistory(), routes: [
    { path: '/guide', component, meta: { requiresAuth: true } },
    { path: '/challenge/:id', component, meta: { requiresAuth: true } },
    { path: '/teacher', component, meta: { requiresTeacherOnly: true } },
    { path: '/admin/users', component, meta: { requiresAdmin: true } },
    { path: '/:pathMatch(.*)*', name: 'NotFound', component },
  ] })
}

test('login carries the complete internal URL including repeated queries and fragment', () => {
  const path = '/challenge/7?tag=a&tag=b&topic=%E7%BD%91%E7%BB%9C#solution'
  assert.equal(safeReturnPath(path), path)
  assert.deepEqual(loginDestination(path), { path: '/login', query: { redirect: path } })
  assert.equal(new URL(loginUrl(path), 'https://app.invalid').searchParams.get('redirect'), path)
  assert.equal(loginReturnDestination(path, routerForReturn(), 'student', canOpen), path)
})

test('external, malformed, repeated and authentication-loop return targets fall back by role', () => {
  const router = routerForReturn()
  const targets = [
    undefined, ['/', '/guide'], '', 'https://example.com/', '//example.com/', '/\\example.com/',
    '/%2f%2fexample.com/', '/%5cexample.com/', '/guide\n', '/%00guide', '/%ZZ',
    '/login?redirect=/guide', '/LOGIN/', '/register', '/access-denied', '/guide/../login', '/missing-page',
  ]
  for (const [role, fallback] of [['student', '/guide'], ['teacher', '/teacher'], ['admin', '/admin/dashboard']]) {
    for (const target of targets) assert.equal(loginReturnDestination(target, router, role, canOpen), fallback, `${role}: ${target}`)
  }
  assert.equal(loginReturnDestination('/admin/users', router, 'student', canOpen), '/guide')
  assert.equal(loginReturnDestination('/teacher', router, 'admin', canOpen), '/admin/dashboard')
  assert.equal(loginReturnDestination('/admin/users', router, 'admin', canOpen), '/admin/users')
})

test('the login form uses the validated destination after successful authentication', async () => {
  const source = readFileSync(new URL('../../views/Login.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const router = routerForReturn()
  const replaced = []
  router.replace = async target => { replaced.push(target) }
  const user = { userInfo: null, login: async () => { user.userInfo = { role: 'student' }; return { success: true } } }
  const login = runInNewContext(`${script}\n;({ form, handleLogin, loading, error })`, {
    ref, useRouter: () => router, useRoute: () => ({ query: { redirect: '/challenge/7?tab=hints#hint-2' } }),
    useUserStore: () => user, canOpen, loginReturnDestination,
  })
  login.form.value = { username: 'student', password: 'test-password' }
  await login.handleLogin()
  assert.deepEqual(replaced, ['/challenge/7?tab=hints#hint-2'])
  assert.equal(login.loading.value, false)
  assert.equal(login.error.value, '')
})

test('session expiry retains the current URL and leaves authentication forms in place', async () => {
  const oldWindow = globalThis.window, oldStorage = globalThis.localStorage
  const adapter = http.defaults.adapter
  const removed = []
  try {
    globalThis.localStorage = { removeItem: key => removed.push(key) }
    http.defaults.adapter = async () => { throw { response: { status: 401 } } }
    globalThis.window = { location: { pathname: '/challenge/7', search: '?tab=hints', hash: '#hint-2', href: '' } }
    await assert.rejects(http.get('/users/profile/'))
    assert.equal(new URL(window.location.href, 'https://app.invalid').searchParams.get('redirect'), '/challenge/7?tab=hints#hint-2')
    for (const pathname of ['/login', '/login/', '/register']) {
      window.location = { pathname, search: '?redirect=%2Fguide', hash: '', href: 'unchanged' }
      await assert.rejects(http.get('/users/profile/'))
      assert.equal(window.location.href, 'unchanged')
    }
    assert.ok(removed.every(key => key === 'userInfo'))
  } finally {
    http.defaults.adapter = adapter
    if (oldWindow === undefined) delete globalThis.window; else globalThis.window = oldWindow
    if (oldStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = oldStorage
  }
})
