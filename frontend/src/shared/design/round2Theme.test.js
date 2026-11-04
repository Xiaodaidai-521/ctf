import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compileStyle } from 'vue/compiler-sfc'

const tokens = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8')
const styles = readFileSync(new URL('../../assets/styles/main.css', import.meta.url), 'utf8')
const value = name => tokens.match(new RegExp(`--${name}:\\s*([^;]+);`))?.[1]

test('round-two shared theme uses the approved G surfaces and red brand, not the superseded paper theme', () => {
  for (const [name, expected] of Object.entries({
    'surface-page': '#fafafa', surface: '#ffffff', ink: '#131316', action: '#b7352d',
    'button-primary': '#131316', 'radius-control': '16px', 'radius-panel': '20px',
    'student-console-radius': '22px',
  })) assert.equal(value(name), expected)
  assert.equal(value('student-hero-gradient'), 'linear-gradient(92deg, #b7352d, #d96c33 55%, #e8a93d)')
  assert.match(value('shadow-raised'), /^0 \d+px \d+px /)
  assert.match(value('shadow-overlay'), /^0 \d+px \d+px /)
  assert.doesNotMatch(tokens, /#f8f4ed|#fffaf2|#efc46b|8px 8px 0|14px 14px 0|#225bd6/i)
  assert.deepEqual(compileStyle({ source: tokens, filename: 'tokens.css', id: 'theme', scoped: false }).errors, [])
})

test('black capsule primary actions reuse local tokens while brand accents and disabled states stay separate', () => {
  assert.match(styles, /:is\(\.btn-primary, \.fb-btn-primary, \.material-primary, \.arco-btn-primary\)\s*\{[^}]*--action: var\(--button-primary\);[^}]*--action-hover: var\(--button-primary-hover\);[^}]*--action-pressed: var\(--button-primary-pressed\);[^}]*--radius-control: var\(--radius-pill\);/)
  assert.match(styles, /\.btn:disabled[^}]*var\(--disabled-ink\)[^}]*var\(--disabled\)/)
  assert.match(styles, /\.arco-btn\.arco-btn-disabled:disabled[^}]*var\(--disabled-ink\)/)
  assert.match(styles, /:focus-visible[^}]*var\(--focus-width\)[^}]*var\(--action\)/)
  assert.deepEqual(compileStyle({ source: styles, filename: 'main.css', id: 'theme', scoped: false }).errors, [])
})

test('all three roles inherit the same theme, with density and chart identities preserved', () => {
  assert.match(tokens, /:root\s*\{/)
  assert.doesNotMatch(tokens + styles, /data-theme=['"]student|body\[data-density/)
  assert.match(tokens, /\[data-density='teacher'\] \{ --density-gap: var\(--space-2\); \}/)
  assert.match(tokens, /\[data-density='admin'\] \{ --density-gap: var\(--space-1\); \}/)
  for (const [name, expected] of Object.entries({ 'series-1': '#2a78d6', 'series-2': '#eb6834', 'series-3': '#199e70' })) assert.equal(value(name), expected)
  assert.match(tokens, /--primary-6: 183, 53, 45;/)
  assert.match(tokens, /prefers-reduced-motion: reduce/)
})
