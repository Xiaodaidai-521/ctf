import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { governancePages, searchGovernance, governancePage } from './governance.js'
import { createRecentVisits } from './recentVisits.js'
import { searchEntries, entriesFor } from './config.js'
import { pageTitle } from './access.js'

const memoryStorage = () => {
  const data = new Map()
  return { getItem: key => data.get(key), setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key), data }
}

test('all canonical governance pages are searchable, including pages outside the sidebar', () => {
  assert.equal(new Set(governancePages.map(page => page.path)).size, governancePages.length)
  for (const item of governancePages) assert.ok(searchEntries('admin', item.label).some(result => result.path === item.path))
  for (const item of entriesFor('admin')) assert.ok(governancePages.some(page => page.path === item.path))
  assert.ok(searchGovernance('索引 健康').some(page => page.path === '/admin/legal/kb/health'))
  assert.ok(searchGovernance('材料授权').some(page => page.path.endsWith('/authorization')))
  assert.ok(searchGovernance('审计日志').some(page => page.path.endsWith('/audit')))
  assert.deepEqual(searchGovernance('不存在的栏目'), [])
})
test('governance catalog never sends admins into teaching or student workspaces', () => {
  assert.ok(governancePages.every(item => item.path.startsWith('/admin/') && item.roles.join() === 'admin'))
  assert.ok(searchEntries('student', '索引工具').length === 0)
  assert.ok(searchEntries('teacher', '授权监督').length === 0)
  assert.equal(governancePage('/admin/legal/kb/health?detail=secret#row')?.path, '/admin/legal/kb/health')
  assert.equal(governancePage('/teacher/materials'), undefined)
})
test('recent visits are canonical, deduplicated, ordered and capped at eight', () => {
  const storage = memoryStorage()
  const visits = createRecentVisits(storage)
  visits.account(1, 'admin')
  for (const page of governancePages) visits.record(page.path)
  assert.equal(visits.list().length, 8)
  visits.record('/admin/legal/kb?query=secret#private')
  visits.record('/admin/legal/kb')
  assert.equal(visits.list()[0].path, '/admin/legal/kb')
  assert.equal(visits.list().filter(page => page.path === '/admin/legal/kb').length, 1)
  assert.ok(![...storage.data.values()].join().includes('secret'))
  assert.equal(createRecentVisits(storage).account(1, 'admin')[0].path, '/admin/legal/kb')
})
test('account change and logout remove previous account visits; non-admins cannot record', () => {
  const storage = memoryStorage()
  const visits = createRecentVisits(storage)
  visits.account('first', 'admin'); visits.record('/admin/users')
  assert.deepEqual(visits.account('second', 'admin'), [])
  assert.ok(!storage.data.has('governance-visits:first'))
  visits.record('/admin/resources'); assert.equal(visits.list().length, 1)
  assert.deepEqual(visits.account('second', 'teacher'), [])
  assert.deepEqual(visits.record('/admin/users'), [])
  assert.ok(!storage.data.has('governance-visits:second'))
})
test('corrupt storage and private links are ignored, unavailable storage remains usable', () => {
  const storage = memoryStorage()
  storage.setItem('governance-visits:1', JSON.stringify(['/admin/users', '/admin/users', '/admin/users?secret=x', '/teacher/materials', 7, '__proto__']))
  assert.deepEqual(createRecentVisits(storage).account(1, 'admin').map(page => page.path), ['/admin/users'])
  storage.setItem('governance-visits:2', '{bad')
  assert.deepEqual(createRecentVisits(storage).account(2, 'admin'), [])
  const unavailable = createRecentVisits({ getItem() { throw Error() }, setItem() { throw Error() }, removeItem() { throw Error() } })
  unavailable.account(1, 'admin'); unavailable.record('/admin/users')
  assert.equal(unavailable.list().length, 1); assert.deepEqual(unavailable.clear(), [])
})
test('admin titles distinguish supervision from teaching assessment', () => {
  assert.equal(pageTitle({ name: 'AdminLearningScoresHome' }, 'admin'), '评测监督')
  assert.equal(pageTitle({ name: 'TeacherLearningScores' }, 'teacher'), '动态评测')
  assert.equal(pageTitle({ name: 'AdminLegalKbHealth' }, 'admin'), '索引健康')
})
test('header gives mobile search a name, uses native links and a removable shortcut', () => {
  const source = fs.readFileSync(new URL('../layout/GlobalHeader.vue', import.meta.url), 'utf8')
  assert.match(source, /:aria-label=.*搜索治理页面/)
  assert.match(source, /:input-attrs="\{ 'aria-label': '搜索页面关键词' \}"/)
  assert.match(source, /aria-label="最近访问"/)
  assert.match(source, /router-link v-for="item in recent"/)
  assert.match(source, /event\.ctrlKey \|\| event\.metaKey/)
  assert.match(source, /removeEventListener\('keydown', searchShortcut\)/)
  assert.match(source, /visits\.account\(user\.userInfo\?\.id, role\.value\)/)
})
