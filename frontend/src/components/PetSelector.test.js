import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { createRequire } from 'node:module'
import { ref, compile, createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { parse, compileScript, compileStyle, compileTemplate } from 'vue/compiler-sfc'
import { petThumbnailStyle } from '../utils/petRegistry.js'

const source = readFileSync(new URL('./PetSelector.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const script = compileScript(descriptor, { id: 'PetSelector' })
const tokens = new Set([...readFileSync(new URL('../shared/design/tokens.css', import.meta.url), 'utf8').matchAll(/(--[\w-]+)\s*:/g)].map(match => match[1]))
const { IconRobot } = createRequire(import.meta.url)('@arco-design/web-vue/lib/icon')
const packs = JSON.parse(readFileSync(new URL('../../public/pets/index.json', import.meta.url), 'utf8'))
const entries = packs.map(pack => ({
  pack, manifest: JSON.parse(readFileSync(new URL(`../../public${pack}/pet.json`, import.meta.url), 'utf8'))
}))

function selector(loadPetRegistry = async () => entries) {
  const emitted = []
  const unmount = []
  const bindings = Object.keys(script.bindings).filter(binding => script.bindings[binding] !== 'props' && !script.imports[binding])
  const page = runInNewContext(`${descriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')}\n;({ ${bindings.join(',')} })`, {
    ref, AbortController, loadPetRegistry, petThumbnailStyle,
    defineProps: () => ({ modelValue: '/pets/dundun' }),
    defineEmits: () => (...args) => emitted.push(args),
    onMounted() {}, onBeforeUnmount: callback => unmount.push(callback),
  })
  return { page, emitted, unmount }
}

function html(page, modelValue = '/pets/dundun') {
  const app = createSSRApp({
    setup: () => ({ ...page, modelValue, petThumbnailStyle }),
    render: compile(descriptor.template.content),
  })
  app.component('IconRobot', IconRobot)
  return renderToString(app)
}

test('selector compiles with scoped design tokens and Arco robot fallback, not Bootstrap icons', () => {
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'PetSelector.vue', id: 'PetSelector', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  for (const style of descriptor.styles) {
    assert.equal(style.scoped, true)
    assert.deepEqual(compileStyle({ source: style.content, filename: 'PetSelector.vue', id: 'PetSelector', scoped: true }).errors, [])
    for (const [, token] of style.content.matchAll(/var\((--[\w-]+)/g)) {
      assert.ok(tokens.has(token) || ['--sheet-top', '--sheet-width'].includes(token), token)
    }
    assert.doesNotMatch(style.content, /#[\da-f]{3,8}\b|rgba?\(|font-size:\s*\d/i)
    assert.match(style.content, /:focus-visible/)
  }
  assert.match(source, /<icon-robot v-else/)
  assert.doesNotMatch(source, /\bbi-[\w-]+/)
})

test('selector shows all five manifest names, emits internal pack values, and marks selected choice', async () => {
  const { page, emitted } = selector()
  await page.loadRegistry()
  const rendered = await html(page)
  for (const entry of entries) assert.ok(rendered.includes(`aria-label="${entry.manifest.displayName}"`))
  assert.equal((rendered.match(/aria-pressed="true"/g) || []).length, 1)
  assert.match(rendered, /已选择/)
  page.choose(entries[2])
  assert.deepEqual(emitted, [['update:modelValue', '/pets/yeye']])
})

test('unavailable choices and list failures never expose pack paths or parser errors as labels', async () => {
  const { page } = selector(async () => [{ pack: '/pets/internal-missing', manifest: null }])
  await page.loadRegistry()
  const rendered = await html(page, '/pets/internal-missing')
  assert.match(rendered, /aria-label="宠物伙伴 1"/)
  assert.match(rendered, /形象暂不可用 · 重试/)
  assert.match(rendered, /arco-icon-robot/)
  assert.doesNotMatch(rendered, /internal-missing|\/pets\/|pet\.json|manifest|spritesheet/i)
  const failed = selector(async () => { throw new SyntaxError('/pets/private/pet.json: invalid JSON') })
  await failed.page.loadRegistry()
  const failure = await html(failed.page)
  assert.match(failure, /宠物列表暂时无法加载/)
  assert.match(failure, /重试列表/)
  assert.doesNotMatch(failure, /\/pets\/|pet\.json|JSON|SyntaxError/)
})

test('selecting a failed choice retries its preview, preserving the selection event', async () => {
  let attempts = 0
  const { page, emitted } = selector(async () => {
    attempts++
    return entries
  })
  await page.loadRegistry()
  const failedImage = { ...entries[0], imageFailed: true }
  page.entries.value = [failedImage]
  assert.match(await html(page), /形象暂不可用 · 重试/)
  await page.choose(failedImage)
  assert.equal(attempts, 2)
  assert.equal(page.entries.value[0].imageFailed, undefined)
  assert.deepEqual(emitted, [['update:modelValue', '/pets/dundun']])
  await page.choose({ pack: '/pets/unavailable', manifest: null })
  assert.equal(attempts, 3)
})

test('registry reload and unmount abort earlier loads and ignore late results', async () => {
  const requests = []
  const { page, unmount } = selector(signal => new Promise(resolve => requests.push({ signal, resolve })))
  const first = page.loadRegistry()
  const second = page.loadRegistry()
  assert.equal(requests[0].signal.aborted, true)
  requests[1].resolve(entries)
  await second
  requests[0].resolve([])
  await first
  assert.equal(page.entries.value.length, 5)
  const third = page.loadRegistry()
  unmount.forEach(callback => callback())
  assert.equal(requests[2].signal.aborted, true)
  requests[2].resolve([])
  await third
  assert.equal(page.entries.value.length, 5)
})
