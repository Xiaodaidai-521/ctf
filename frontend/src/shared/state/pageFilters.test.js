import test from 'node:test'
import assert from 'node:assert/strict'
import { effectScope, ref } from 'vue'
import fs from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import { syncStateAccount } from './accountScope.js'
import { usePageFilters } from './usePageFilters.js'

function controls() { return { searchKeyword: ref(''), page: ref(1) } }
test('list filters survive remount without preserving records or form fields', () => {
  syncStateAccount({ id: 100, role: 'admin' }, { force: true })
  const first = effectScope(); const initial = controls()
  first.run(() => usePageFilters('test-list', initial))
  initial.searchKeyword.value = '授权'; initial.page.value = 3; first.stop()
  const second = effectScope(); const restored = controls()
  second.run(() => usePageFilters('test-list', restored))
  assert.equal(restored.searchKeyword.value, '授权'); assert.equal(restored.page.value, 3)
  assert.deepEqual(Object.keys(restored), ['searchKeyword', 'page']); second.stop()
})
test('account and role changes prevent restoring previous filters and late writes', () => {
  syncStateAccount({ id: 101, role: 'admin' }, { force: true })
  const old = effectScope(); const initial = controls()
  old.run(() => usePageFilters('test-list', initial)); initial.searchKeyword.value = 'old'
  syncStateAccount({ id: 102, role: 'admin' })
  initial.searchKeyword.value = 'late'
  const next = effectScope(); const restored = controls()
  next.run(() => usePageFilters('test-list', restored)); assert.equal(restored.searchKeyword.value, '')
  old.stop(); next.stop()
})
for (const [page, keys] of [['Users', ['searchKeyword', 'page', 'pageSize']], ['Articles', ['selectedStatus', 'page', 'pageSize']], ['Submissions', ['searchKeyword', 'filterStatus', 'page', 'pageSize']], ['Announcements', ['filters']]]) {
  test(`${page} compiles and retains only explicit list controls`, () => {
    const filename = new URL(`../../admin/views/${page}.vue`, import.meta.url)
    const source = fs.readFileSync(filename, 'utf8')
    const { descriptor, errors } = parse(source); assert.equal(errors.length, 0)
    assert.ok(compileScript(descriptor, { id: page }).content)
    const matched = source.match(/usePageFilters\('[^']+', \{ ([^}]+) \}\)/)
    assert.ok(matched); assert.deepEqual(matched[1].split(',').map(item => item.trim()), keys)
    assert.doesNotMatch(matched[1], /users|submissions|articles|announcements|Form|formData|password/)
    assert.match(source, /onBeforeUnmount\(guard\.dispose\)/)
  })
}
test('governance tasks land at pending articles and the user list loads on mount', () => {
  const articles = fs.readFileSync(new URL('../../admin/views/Articles.vue', import.meta.url), 'utf8')
  assert.match(articles, /statuses\.includes\(route\.query\.status\)/)
  assert.match(articles, /watch\(\(\) => route\.query\.status/)
  const users = fs.readFileSync(new URL('../../admin/views/Users.vue', import.meta.url), 'utf8')
  assert.doesNotMatch(users, /teacher-applications|fetchTeacherApplications/)
  assert.match(users, /onMounted\(fetchUsers\)/)
})
