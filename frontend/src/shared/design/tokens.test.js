import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileStyle } from 'vue/compiler-sfc'
const css = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8')
const tokens = Object.fromEntries([...css.matchAll(/--([\w-]+):\s*(#[\da-f]{6});/gi)].map(match => [match[1], match[2]]))
const luminance = hex => hex.slice(1).match(/../g).map(value => parseInt(value, 16) / 255).map(c => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0)
const contrast = (a, b) => { const x = luminance(tokens[a]), y = luminance(tokens[b]); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) }
for (const [ink, surface] of [
  ['ink', 'surface'], ['ink-secondary', 'surface'], ['ink-muted', 'surface-page'],
  ['action', 'action-soft'], ['on-action', 'action'], ['agent-accent', 'agent-soft'],
  ['positive', 'positive-soft'], ['warning', 'warning-soft'], ['negative', 'negative-soft'],
  ['disabled-ink', 'disabled'],
]) test(`shared text contrast ${ink}/${surface} is at least 4.5:1`, () => {
  assert.ok(contrast(ink, surface) >= 4.5, `${contrast(ink, surface).toFixed(2)}:1`)
})
test('compact component CSS targets descendants, never the entire app shell', () => {
  for (const file of ['../layout/GlobalHeader.vue', '../../learning/guide/GuideView.vue', '../../components/PlatformPet.vue', '../../views/Home.vue']) {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8')
    const style = parse(source).descriptor.styles[0]
    const css = compileStyle({ source: style.content, id: 'data-v-check', scoped: true }).code
    assert.doesNotMatch(css, /\.is-compact\s*\{/)
    assert.match(css, /\.is-compact\s+\./)
  }
})
test('keyboard focus boundary has at least 3:1 contrast', () => assert.ok(contrast('action', 'surface') >= 3))
test('design provides five typography levels and reduced motion', () => {
  for (const level of ['page', 'section', 'card', 'body', 'caption']) assert.match(css, new RegExp(`--text-${level}:`))
  assert.match(css, /prefers-reduced-motion: reduce/)
  for (const duration of ['150ms', '200ms', '250ms']) assert.ok(css.includes(duration))
})
