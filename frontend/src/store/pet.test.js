import { test, beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createPinia, setActivePinia } from 'pinia'
import { usePetStore } from './pet.js'
import { PET_STORAGE_KEY } from '../utils/pet.js'

let storage
beforeEach(() => {
  storage = new Map()
  globalThis.localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value)
  }
  setActivePinia(createPinia())
})

test('request lifecycle: idle → working → ready → acknowledged idle', () => {
  const pet = usePetStore()
  assert.equal(pet.state, 'idle')
  assert.doesNotThrow(() => pet.acknowledge('missing'))
  assert.doesNotThrow(() => pet.clear('missing'))
  const token = pet.begin('multi-agent', { target: '/multi-agent/12', label: '解题助手' })
  assert.equal(pet.state, 'working')
  assert.equal(pet.current.target, '/multi-agent/12')
  pet.complete('multi-agent', token)
  assert.equal(pet.state, 'ready')
  pet.acknowledge('multi-agent', token)
  assert.equal(pet.state, 'idle')
})

test('needs-input stays until answered or conversation cleared; errors stay until retry', () => {
  const pet = usePetStore()
  const first = pet.begin('teaching')
  pet.complete('teaching', first, { needsInput: true })
  assert.equal(pet.state, 'needs-input')
  pet.acknowledge('teaching', first)
  assert.equal(pet.state, 'needs-input')
  const second = pet.begin('teaching')
  pet.fail('teaching', second)
  assert.equal(pet.state, 'failed')
  assert.equal(pet.complete('teaching', second), false)
  const third = pet.begin('teaching')
  assert.equal(pet.state, 'working')
  pet.clear('teaching', third)
  assert.equal(pet.state, 'idle')
})

test('real confirmation forms can request input without inventing an HTTP request', () => {
  const pet = usePetStore()
  const token = pet.requestInput('chat:handoff', { target: '/multi-agent?mode=learning', label: '确认委托' })
  assert.equal(pet.state, 'needs-input')
  assert.equal(pet.current.label, '确认委托')
  pet.acknowledge('chat:handoff', token)
  assert.equal(pet.state, 'needs-input')
  pet.clear('chat:handoff', token)
  assert.equal(pet.state, 'idle')
})

test('concurrent sources cannot hide outstanding work or erase other unread responses', () => {
  const pet = usePetStore()
  const a = pet.begin('a')
  const b = pet.begin('b')
  pet.complete('a', a)
  assert.equal(pet.state, 'working')
  pet.complete('b', b, { needsInput: true })
  assert.equal(pet.state, 'needs-input')
  pet.clear('b', b)
  assert.equal(pet.state, 'ready')
  assert.equal(pet.current.source, 'a')
})

test('stale completion, clear, and acknowledgment cannot overwrite a newer request', () => {
  const pet = usePetStore()
  const old = pet.begin('chat')
  const current = pet.begin('chat')
  assert.equal(pet.complete('chat', old), false)
  assert.equal(pet.fail('chat', old), false)
  pet.clear('chat', old)
  pet.acknowledge('chat', old)
  assert.equal(pet.state, 'working')
  pet.complete('chat', current)
  pet.acknowledge('chat', old)
  assert.equal(pet.state, 'ready')
})

test('reset rejects late events from previous login, without recycling tokens', () => {
  const pet = usePetStore()
  const old = pet.begin('chat')
  pet.reset()
  assert.equal(pet.complete('chat', old), false)
  const current = pet.begin('chat')
  assert.notEqual(current, old)
  assert.equal(pet.fail('chat', old), false)
  assert.equal(pet.state, 'working')
})

test('only preferences persist across store recreation', () => {
  const pet = usePetStore()
  pet.setPosition({ x: 40, y: 100 })
  pet.setHidden(true)
  assert.equal(pet.setPack('/pets/another-pet/'), true)
  pet.begin('chat')
  setActivePinia(createPinia())
  const restored = usePetStore()
  assert.deepEqual(restored.preferences, { hidden: true, position: { x: 40, y: 100 }, pack: '/pets/another-pet' })
  assert.equal(restored.state, 'idle')
  assert.equal(restored.setPack('https://untrusted.example/pet'), false)
  restored.setPosition({ x: NaN, y: 3 })
  assert.deepEqual(restored.preferences.position, { x: 40, y: 100 })
})

test('registry choices and visibility reuse v1 preferences without changing position or live activity', async () => {
  const position = { x: 64, y: 120 }
  storage.set(PET_STORAGE_KEY, JSON.stringify({ pack: '/pets/custom-existing', hidden: true, position }))
  const packs = JSON.parse(await readFile(new URL('../../public/pets/index.json', import.meta.url), 'utf8'))
  const pet = usePetStore()
  assert.deepEqual(pet.preferences, { pack: '/pets/custom-existing', hidden: true, position })
  const token = pet.begin('existing-request')
  for (const pack of packs) {
    assert.equal(pet.setPack(pack), true)
    assert.equal(pet.state, 'working')
    assert.equal(pet.current.token, token)
    assert.deepEqual(JSON.parse(storage.get(PET_STORAGE_KEY)), { pack, hidden: true, position })
    const restored = usePetStore(createPinia())
    assert.deepEqual(restored.preferences, { pack, hidden: true, position })
  }
  pet.setHidden(false)
  assert.equal(usePetStore(createPinia()).preferences.hidden, false)
  assert.deepEqual(pet.preferences.position, position)
  assert.equal(pet.state, 'working')
  assert.deepEqual([...storage.keys()], [PET_STORAGE_KEY])
})

test('corrupt and unavailable storage degrade without throwing', () => {
  storage.set(PET_STORAGE_KEY, '{bad-json')
  assert.equal(usePetStore().preferences.pack, '/pets/dundun')
  setActivePinia(createPinia())
  globalThis.localStorage = {
    getItem() { throw new Error('denied') },
    setItem() { throw new Error('quota') }
  }
  const pet = usePetStore()
  assert.doesNotThrow(() => pet.setHidden(true))
  assert.doesNotThrow(() => pet.setPosition({ x: 2, y: 3 }))
  assert.doesNotThrow(() => pet.setPack('/pets/custom'))
})

test('launcher starts collapsed and opening or closing never persists transient state', () => {
  const pet = usePetStore()
  assert.equal(pet.opened, false)
  pet.setOpened(true)
  assert.equal(pet.opened, true)
  assert.equal(storage.size, 0)
  pet.setOpened(false)
  assert.equal(pet.opened, false)
  assert.equal(storage.size, 0)
  pet.begin('chat')
  assert.equal(pet.opened, false, 'incoming activity does not open the launcher')
})

test('hide closes the module; reveal unhides and opens without clearing preferences or activity', () => {
  const pet = usePetStore()
  pet.setPack('/pets/xiaoju')
  pet.setPosition({ x: 64, y: 120 })
  const token = pet.requestInput('confirmation', { label: '确认下一步' })
  pet.setOpened(true)
  pet.setHidden(true)
  assert.equal(pet.preferences.hidden, true)
  assert.equal(pet.opened, false)
  pet.setOpened(true)
  assert.equal(pet.opened, false, 'a hidden module cannot be opened without unhiding it')
  pet.setHidden(false)
  assert.equal(pet.opened, false, 'unhiding alone restores only the collapsed launcher')
  pet.setHidden(true)
  pet.reveal()
  assert.equal(pet.opened, true)
  assert.deepEqual(pet.preferences, { pack: '/pets/xiaoju', hidden: false, position: { x: 64, y: 120 } })
  assert.equal(pet.state, 'needs-input')
  assert.equal(pet.current.token, token)
  assert.deepEqual(JSON.parse(storage.get(PET_STORAGE_KEY)), pet.preferences)
  const restored = usePetStore(createPinia())
  assert.equal(restored.opened, false)
  assert.equal(restored.state, 'idle')
  assert.deepEqual(restored.activities, {})
  assert.deepEqual(restored.preferences, pet.preferences)
})

test('account reset closes opened and clears every activity but preserves preferences and token sequence', () => {
  const pet = usePetStore()
  pet.setPack('/pets/yeye')
  pet.setPosition({ x: 40, y: 100 })
  pet.reveal()
  const old = pet.begin('chat')
  pet.requestInput('confirmation')
  const ready = pet.begin('reply')
  pet.complete('reply', ready)
  const failed = pet.begin('error')
  pet.fail('error', failed)
  const persisted = storage.get(PET_STORAGE_KEY)
  const preferences = structuredClone(JSON.parse(persisted))
  pet.reset()
  assert.equal(pet.opened, false)
  assert.equal(pet.state, 'idle')
  assert.equal(pet.current, null)
  assert.deepEqual(pet.activities, {})
  assert.deepEqual(pet.preferences, preferences)
  assert.equal(storage.get(PET_STORAGE_KEY), persisted)
  assert.equal(pet.complete('chat', old), false)
  const next = pet.begin('chat')
  assert.ok(next > failed)
  assert.equal(pet.fail('chat', old), false)
  pet.setHidden(true)
  pet.reset()
  assert.equal(pet.preferences.hidden, true, 'account reset must not override the hide preference')
})

test('legacy storage cannot restore activities, opened, input, or chat, and next save contains only preferences', () => {
  storage.set(PET_STORAGE_KEY, JSON.stringify({
    pack: '/pets/gugu', hidden: false, position: { x: 5, y: 10 },
    opened: true, activities: { chat: { state: 'working', token: 99 } },
    input: 'private input', chat: [{ content: 'private reply' }]
  }))
  const pet = usePetStore()
  assert.equal(pet.opened, false)
  assert.equal(pet.state, 'idle')
  assert.deepEqual(pet.activities, {})
  pet.setOpened(true)
  pet.begin('chat', { input: 'private input', chat: 'private reply' })
  pet.setPack('/pets/xiaoqing')
  assert.deepEqual(JSON.parse(storage.get(PET_STORAGE_KEY)), {
    pack: '/pets/xiaoqing', hidden: false, position: { x: 5, y: 10 }
  })
  assert.deepEqual(Object.keys(pet.current).sort(), ['label', 'source', 'state', 'target', 'token'])
})
