import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import {
  PET_ANIMATIONS, clampPetPosition, loadPetManifest,
  normalizePetPack, petFrameAt, validatePetManifest, validatePetImage
} from './pet.js'

const manifest = JSON.parse(await readFile(new URL('../../public/pets/dundun/pet.json', import.meta.url), 'utf8'))

test('Dundun uses explicit animations mapping, including working row 7 and waiting row 6', () => {
  assert.equal(validatePetManifest(manifest), manifest)
  assert.deepEqual(Object.fromEntries(Object.entries(PET_ANIMATIONS).map(([state, key]) => [state, manifest.animations[key].row])), {
    idle: 0, working: 7, 'needs-input': 6, ready: 3, failed: 5
  })
  assert.doesNotThrow(() => validatePetImage(manifest, { naturalWidth: 1536, naturalHeight: 1872 }))
})

test('custom packs may change row order, dimensions, frame count, and fps', () => {
  const custom = structuredClone(manifest)
  custom.cellWidth = 32
  custom.cellHeight = 40
  custom.animations.working = { row: 2, frames: 3, fps: 2 }
  validatePetManifest(custom)
  const animation = custom.animations[PET_ANIMATIONS.working]
  assert.equal(animation.row, 2)
  assert.deepEqual([0, 499, 500, 1000, 1500].map(ms => petFrameAt(animation, ms)), [0, 0, 1, 2, 0])
})

test('missing, malformed, incomplete and unsafe manifest/image data fail gracefully at loader boundary', async () => {
  for (const value of [null, {}, { ...manifest, cellWidth: 0 }, { ...manifest, spritesheetPath: 'https://example.test/pet.webp' },
    { ...manifest, animations: {} }, { ...manifest, animations: { ...manifest.animations, idle: { row: -1, fps: 4, frames: 8 } } },
    { ...manifest, animations: { ...manifest.animations, working: { row: 0, fps: 0, frames: 8 } } }]) {
    assert.throws(() => validatePetManifest(value))
  }
  assert.throws(() => validatePetImage(manifest, { naturalWidth: 10, naturalHeight: 10 }))
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => ({ ok: false, status: 404 })
    await assert.rejects(loadPetManifest('/pets/missing'), /加载失败/)
    globalThis.fetch = async () => ({ ok: true, json: async () => { throw new SyntaxError('HTML fallback') } })
    await assert.rejects(loadPetManifest('/pets/renamed'), /HTML fallback/)
    globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
    await assert.rejects(loadPetManifest('/pets/offline'), /Failed to fetch/)
    globalThis.fetch = async () => ({ ok: true, json: async () => manifest })
    assert.equal(await loadPetManifest('/pets/dundun'), manifest)
  } finally {
    globalThis.fetch = original
  }
})

test('pack paths remain local directories and position is clamped to small/resized viewports', () => {
  assert.equal(normalizePetPack(' /pets/dundun/ '), '/pets/dundun')
  for (const path of ['/pets/../private', '//example.test/pets/a', 'javascript:alert(1)', '/pets/a?b', null]) {
    assert.equal(normalizePetPack(path), null)
  }
  assert.deepEqual(clampPetPosition({ x: -20, y: 999 }, { width: 320, height: 480 }, { width: 120, height: 160 }), { x: 0, y: 320 })
  assert.deepEqual(clampPetPosition({ x: 900, y: 900 }, { width: 80, height: 100 }, { width: 120, height: 160 }), { x: 0, y: 0 })
})
