import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { loadPetRegistry, petThumbnailStyle } from './petRegistry.js'

const publicFile = path => new URL(`../../public${path}`, import.meta.url)
const readJSON = async path => JSON.parse(await readFile(publicFile(path), 'utf8'))

test('registry loads every built-in display name and local spritesheet from its manifest', async t => {
  const requests = []
  const controller = new AbortController()
  t.mock.method(globalThis, 'fetch', async (url, { signal }) => {
    requests.push(url)
    assert.equal(signal, controller.signal)
    return { ok: true, json: () => readJSON(url) }
  })
  const entries = await loadPetRegistry(controller.signal)
  assert.deepEqual(entries.map(entry => entry.pack), await readJSON('/pets/index.json'))
  for (const { pack, manifest } of entries) {
    assert.deepEqual(manifest, await readJSON(`${pack}/pet.json`))
    assert.ok(manifest.displayName.trim())
    assert.ok((await readFile(publicFile(`${pack}/${manifest.spritesheetPath}`))).length)
  }
  assert.equal(requests.length, entries.length + 1)
})

test('registry normalizes and deduplicates paths without dropping healthy packs when one fails', async t => {
  const manifest = await readJSON('/pets/dundun/pet.json')
  t.mock.method(globalThis, 'fetch', async url => {
    if (url === '/pets/index.json') return { ok: true, json: async () => ['/pets/dundun/', '/pets/missing', '/pets/dundun', '/pets/unnamed'] }
    if (url === '/pets/missing/pet.json') return { ok: false }
    return { ok: true, json: async () => url.includes('unnamed') ? { ...manifest, displayName: '' } : manifest }
  })
  const entries = await loadPetRegistry()
  assert.equal(entries.length, 3)
  assert.equal(entries[0].manifest.displayName, manifest.displayName)
  assert.deepEqual(entries.slice(1), [
    { pack: '/pets/missing', manifest: null },
    { pack: '/pets/unnamed', manifest: null }
  ])
})

test('registry rejects missing, invalid JSON, empty, malformed, and nonlocal indexes', async t => {
  for (const response of [
    { ok: false },
    { ok: true, json: async () => { throw new SyntaxError('HTML instead of JSON') } },
    ...[[], {}, ['/pets/dundun', 'https://example.com/pet'], [null], ['/pets/../outside']]
      .map(value => ({ ok: true, json: async () => value }))
  ]) {
    const fetch = t.mock.method(globalThis, 'fetch', async () => response)
    await assert.rejects(loadPetRegistry())
    assert.equal(fetch.mock.callCount(), 1, 'invalid registry must not fetch individual packs')
    fetch.mock.restore()
  }
})

test('aborted registry loads reject instead of becoming unavailable choices', async t => {
  const controller = new AbortController()
  t.mock.method(globalThis, 'fetch', async url => {
    if (url === '/pets/index.json') return { ok: true, json: async () => ['/pets/dundun'] }
    controller.abort()
    throw controller.signal.reason
  })
  await assert.rejects(loadPetRegistry(controller.signal), { name: 'AbortError' })
})

test('idle thumbnail crops the first frame using manifest dimensions, columns and idle row', () => {
  assert.deepEqual(petThumbnailStyle({ cellWidth: 192, cellHeight: 208, columns: 8, animations: { idle: { row: 0 } } }), {
    width: '48px', height: '52px', '--sheet-width': '384px', '--sheet-top': '0px'
  })
  assert.deepEqual(petThumbnailStyle({ cellWidth: 100, cellHeight: 200, columns: 3, animations: { idle: { row: 2 } } }), {
    width: '26px', height: '52px', '--sheet-width': '78px', '--sheet-top': '-104px'
  })
})
