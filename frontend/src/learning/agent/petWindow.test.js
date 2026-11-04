import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { createPetWindowController } from './petWindow.js'

function fixture({ native = true, blocked = false, reject = false, pending = null } = {}) {
  const owner = new EventTarget(), child = new EventTarget()
  const calls = { native: 0, popup: 0, cleanup: 0, focus: 0, closed: 0 }
  child.closed = false
  child.opener = owner
  child.close = () => { child.closed = true; calls.closed++; child.dispatchEvent(new Event('pagehide')) }
  child.focus = () => { calls.focus++ }
  owner.open = (...args) => { calls.popup++; calls.args = args; return blocked ? null : child }
  if (native) owner.documentPictureInPicture = { requestWindow: async options => { calls.native++; calls.options = options; if (reject) throw new Error('denied'); return pending || child } }
  let state
  const controller = createPetWindowController({ owner, onChange: value => { state = value }, prepare: () => ({ target: { id: 'same-pet-target' }, cleanup: () => { calls.cleanup++ } }) })
  return { owner, child, controller, calls, state: () => state }
}
test('pet window prefers native document picture-in-picture', async () => {
  const f = fixture(); await f.controller.open()
  assert.equal(f.calls.native, 1); assert.equal(f.calls.popup, 0)
  assert.equal(f.state().mode, 'pip'); assert.equal(f.state().window, f.child)
  assert.deepEqual(f.calls.options, { width: 480, height: 700 })
  assert.match(f.state().notice, /保留平台标签页/)
  f.controller.dispose()
})
test('unsupported document picture-in-picture falls back to a real ordinary popup with an honest notice', async () => {
  const f = fixture({ native: false }); await f.controller.open()
  assert.equal(f.state().mode, 'popup'); assert.equal(f.calls.popup, 1)
  assert.equal(f.child.opener, null)
  assert.deepEqual(f.calls.args.slice(0, 2), ['', ''])
  assert.match(f.state().notice, /置顶无法保证/)
  f.controller.dispose()
})
test('native rejection does not silently attempt a popup after losing user activation', async () => {
  const f = fixture({ reject: true }); await f.controller.open()
  assert.equal(f.calls.popup, 0); assert.equal(f.state().target, null)
  assert.equal(f.state().fallbackAvailable, true)
  await f.controller.open({ popup: true })
  assert.equal(f.calls.native, 1); assert.equal(f.state().mode, 'popup')
  f.controller.dispose()
})
test('blocked popup stays inline and offers an explicit retry', async () => {
  const f = fixture({ native: false, blocked: true }); await f.controller.open()
  assert.equal(f.state().mode, 'inline'); assert.equal(f.state().opening, false)
  assert.equal(f.state().fallbackAvailable, true)
  assert.match(f.state().notice, /允许弹出窗口/)
  f.controller.dispose()
})
test('opening again focuses one existing pet window instead of creating duplicates', async () => {
  const f = fixture(); await f.controller.open(); await f.controller.open()
  assert.equal(f.calls.native, 1); assert.equal(f.calls.focus, 1)
  f.controller.dispose()
})
test('concurrent open clicks make only one native request', async () => {
  let resolve
  const pending = new Promise(done => { resolve = done })
  const f = fixture({ pending })
  const first = f.controller.open(); await f.controller.open()
  assert.equal(f.state().opening, true); assert.equal(f.calls.native, 1)
  resolve(f.child); await first; assert.equal(f.state().mode, 'pip')
  f.controller.dispose()
})
test('docking returns the same target to inline mode and cleans listeners once', async () => {
  const f = fixture(); await f.controller.open(); f.controller.dock()
  assert.equal(f.state().target, null); assert.equal(f.calls.closed, 1)
  assert.equal(f.calls.cleanup, 1); assert.match(f.state().notice, /回到平台页/)
  f.controller.dispose(); assert.equal(f.calls.cleanup, 1)
})
test('native close or child navigation returns the pet without closing user navigation again', async () => {
  const f = fixture(); await f.controller.open()
  f.child.dispatchEvent(new Event('pagehide'))
  assert.equal(f.state().window, null); assert.equal(f.calls.closed, 0)
  assert.equal(f.calls.cleanup, 1)
  f.controller.dispose()
})
test('docking while native request is pending rejects its late result', async () => {
  let resolve
  const f = fixture({ pending: new Promise(done => { resolve = done }) })
  const request = f.controller.open(); f.controller.dock()
  resolve(f.child); await request
  assert.equal(f.state().window, null); assert.equal(f.calls.closed, 1)
  f.controller.dispose()
})
test('account unmount disposal closes the window and prevents future opens', async () => {
  const f = fixture(); await f.controller.open(); f.controller.dispose(); await f.controller.open()
  assert.equal(f.calls.closed, 1); assert.equal(f.calls.native, 1); assert.equal(f.state().target, null)
})
test('account unmount during opening closes a late native window without publishing it', async () => {
  let resolve
  const f = fixture({ pending: new Promise(done => { resolve = done }) })
  const request = f.controller.open(); f.controller.dispose(); resolve(f.child); await request
  assert.equal(f.calls.closed, 1); assert.equal(f.state().target, null)
})
test('owner pagehide closes the window but bfcache return may open it again', async () => {
  const f = fixture(); await f.controller.open(); f.owner.dispatchEvent(new Event('pagehide'))
  assert.equal(f.calls.closed, 1); assert.equal(f.calls.cleanup, 1)
  f.child.closed = false
  await f.controller.open(); assert.equal(f.calls.native, 2); assert.equal(f.state().mode, 'pip')
  f.controller.dispose()
})
const source = readFileSync(new URL('../../components/PlatformPet.vue', import.meta.url), 'utf8')
const controllerSource = readFileSync(new URL('./petWindow.js', import.meta.url), 'utf8')
test('pet window teleports one live component and keeps all existing events compilable', () => {
  const { descriptor } = parse(source)
  const script = compileScript(descriptor, { id: 'pet-window' })
  const result = compileTemplate({ source: descriptor.template.content, filename: 'PlatformPet.vue', id: 'pet-window', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(result.errors, [])
  assert.equal((source.match(/id="platform-pet"/g) || []).length, 1)
  assert.match(source, /<Teleport :to="floating.target \|\| 'body'" :disabled="!floating.target"/)
  assert.match(source, /<dialog v-if="floating.target"/)
  assert.match(source, /<a-modal v-else/)
  assert.match(source, /dialog.showModal\(\)/)
  assert.match(source, /autofocus @click="restartOpen = false"/)
  assert.match(source, /@cancel="restartOpen = false" @close="closeRestartDialog"/)
  assert.doesNotMatch(controllerSource, /localStorage|sessionStorage|BroadcastChannel|postMessage|createApp|innerHTML/)
})
test('animation, visibility, keyboard focus and resize follow the actual display document', () => {
  assert.match(source, /target.requestAnimationFrame\(tick\)/)
  assert.match(source, /const displayDocument = target.document/)
  assert.match(source, /displayDocument.addEventListener\('visibilitychange'/)
  assert.match(source, /displayDocument.removeEventListener\('visibilitychange'/)
  assert.doesNotMatch(source, /target.document.removeEventListener/)
  assert.match(source, /displayWindow.value.document.activeElement/)
  assert.match(source, /new target.ResizeObserver/)
  assert.match(source, /target.cancelAnimationFrame/)
  assert.doesNotMatch(controllerSource, /setInterval|setTimeout/)
})
test('exam and hiding boundaries dock the popup, and unmount disposes it', () => {
  assert.match(source, /watch\(\(\) => props.examPage,[\s\S]*?petWindow.dock\(\)/)
  assert.match(source, /watch\(\(\) => pet.preferences.hidden,[\s\S]*?petWindow.dock\(\)/)
  assert.match(source, /if \(!props.examPage && !pet.preferences.hidden\)/)
  assert.match(source, /petWindow.dispose\(\)/)
})
test('style copy excludes scripts and copies stylesheet URLs without reading cross-origin cssRules', () => {
  assert.match(controllerSource, /querySelectorAll\('style, link\[rel="stylesheet"\]'\)/)
  assert.match(controllerSource, /clone.href = node.href/)
  assert.doesNotMatch(controllerSource, /cssRules|querySelectorAll\('script/)
  assert.match(controllerSource, /cssObserver.disconnect\(\); themeObserver.disconnect\(\)/)
})
