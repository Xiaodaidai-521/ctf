import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { PET_ANIMATIONS, PET_LABELS, validatePetManifest, validatePetImage, petFrameAt } from './pet.js'

const publicRoot = new URL('../../public/pets/', import.meta.url)
const evidence = JSON.parse(readFileSync(new URL('../../../evidence/frontend-overhaul/phase6/assets.json', import.meta.url), 'utf8'))
const readJSON = path => JSON.parse(readFileSync(new URL(path, publicRoot), 'utf8'))
const packs = ['dundun', 'xiaoju', 'yeye', 'gugu', 'xiaoqing']
const mapping = {
  idle: { row: 0, frames: 8, fps: 5 },
  runRight: { row: 1, frames: 8, fps: 10 },
  runLeft: { row: 2, frames: 8, fps: 10 },
  wave: { row: 3, frames: 8, fps: 8 },
  jump: { row: 4, frames: 8, fps: 9 },
  failed: { row: 5, frames: 8, fps: 4 },
  waiting: { row: 6, frames: 8, fps: 4 },
  working: { row: 7, frames: 8, fps: 12 },
  review: { row: 8, frames: 8, fps: 6 },
}

// Decode actual PNG and WebP pixels, not just manifest/header claims. Python's
// isolated mode prevents imports from the worktree or an asset directory.
const decoded = spawnSync('python3', ['-I', '-c', `
import json, sys
from pathlib import Path
from hashlib import sha256
from PIL import Image
root = Path(sys.argv[1])
result = {}
for pack in ['dundun', 'xiaoju', 'yeye', 'gugu', 'xiaoqing']:
    for extension in ['png', 'webp']:
        relative = f'{pack}/spritesheet.{extension}'
        with Image.open(root / relative) as source:
            image = source.convert('RGBA')
        result[relative] = {
            'dimensions': list(image.size),
            'frameRows': [[sha256(image.crop((column * 192, row * 208, (column + 1) * 192, (row + 1) * 208)).tobytes()).hexdigest() for column in range(8)] for row in range(9)]
        }
print(json.dumps(result))
`, fileURLToPath(publicRoot)], { encoding: 'utf8', maxBuffer: 1024 * 1024 })

let decodedImages
function images() {
  assert.equal(decoded.status, 0, `Pillow decoding failed: ${decoded.error?.message || decoded.stderr}`)
  decodedImages ||= JSON.parse(decoded.stdout)
  return decodedImages
}

test('all 16 resources retain current-worktree source SHA-256 identity', () => {
  assert.equal(evidence.complete, true)
  assert.equal(evidence.resourceCount, 16)
  assert.equal(evidence.assets.length, 16)
  assert.match(evidence.provenance, /current worktree, not git HEAD/)
  assert.deepEqual(readJSON('index.json'), packs.map(pack => `/pets/${pack}`))
  assert.deepEqual(readdirSync(publicRoot).sort(), [...packs, 'index.json'].sort())
  for (const pack of packs) {
    assert.deepEqual(readdirSync(new URL(`${pack}/`, publicRoot)).sort(), ['pet.json', 'spritesheet.png', 'spritesheet.webp'])
  }
  for (const asset of evidence.assets) {
    const bytes = readFileSync(new URL(asset.path, publicRoot))
    const hash = createHash('sha256').update(bytes).digest('hex')
    assert.equal(asset.identical, true, asset.path)
    assert.equal(hash, asset.sourceSha256, asset.path)
    assert.equal(hash, asset.destinationSha256, asset.path)
    assert.equal(bytes.length, asset.sourceBytes, asset.path)
    assert.equal(bytes.length, asset.destinationBytes, asset.path)
  }
})

for (const pack of packs) {
  test(`${pack}: both PNG/WebP decode at 1536×1872 and all 9 animation rows / 72 frames match source evidence`, () => {
    const manifest = readJSON(`${pack}/pet.json`)
    assert.equal(validatePetManifest(manifest), manifest)
    assert.deepEqual(manifest.animations, mapping)
    assert.deepEqual([manifest.cellWidth, manifest.cellHeight, manifest.columns], [192, 208, 8])
    assert.deepEqual(Object.fromEntries(Object.entries(PET_ANIMATIONS).map(([state, key]) => [state, manifest.animations[key].row])), {
      idle: 0, working: 7, 'needs-input': 6, ready: 3, failed: 5,
    })
    const proof = evidence.packs.find(entry => entry.pack === `/pets/${pack}`)
    assert.deepEqual(proof.sourceAnimations, mapping)
    assert.deepEqual(proof.destinationAnimations, mapping)
    assert.equal(proof.animationsIdentical, true)
    assert.equal(proof.images.length, 2)
    for (const extension of ['png', 'webp']) {
      const path = `${pack}/spritesheet.${extension}`
      const image = images()[path]
      const asset = evidence.assets.find(entry => entry.path === path)
      const recorded = proof.images.find(entry => entry.path === path)
      assert.deepEqual(image.dimensions, [1536, 1872], path)
      assert.deepEqual(image.dimensions, asset.sourceDimensions, path)
      assert.deepEqual(image.dimensions, asset.destinationDimensions, path)
      assert.deepEqual(image.dimensions, recorded.sourceDimensions, path)
      assert.deepEqual(image.dimensions, recorded.destinationDimensions, path)
      assert.doesNotThrow(() => validatePetImage(manifest, { naturalWidth: image.dimensions[0], naturalHeight: image.dimensions[1] }))
      assert.equal(recorded.rows.length, 9)
      for (const row of recorded.rows) {
        assert.deepEqual({ row: row.row, frames: row.frames, fps: row.fps }, mapping[row.animation])
        assert.deepEqual(row.frameDimensions, [192, 208])
        assert.equal(row.identical, true)
        assert.deepEqual(image.frameRows[row.row], row.sourceFrameSha256, `${path} ${row.animation}`)
        assert.deepEqual(image.frameRows[row.row], row.destinationFrameSha256, `${path} ${row.animation}`)
      }
    }
  })
}

test('state labels stay human-readable and lower-frame custom animations never select unused columns', () => {
  assert.deepEqual(Object.keys(PET_LABELS).sort(), Object.keys(PET_ANIMATIONS).sort())
  for (const label of Object.values(PET_LABELS)) {
    assert.match(label, /[一-鿿]/)
    assert.doesNotMatch(label, /\/pets\/|pet\.json|spritesheet|manifest|needs-input/i)
  }
  for (const frames of [1, 2, 3]) {
    const animation = { row: 7, frames, fps: 12 }
    assert.equal(petFrameAt(animation, -100), 0)
    for (let elapsed = 0; elapsed < 10000; elapsed += 17) {
      const frame = petFrameAt(animation, elapsed)
      assert.ok(frame >= 0 && frame < frames)
    }
  }
})
