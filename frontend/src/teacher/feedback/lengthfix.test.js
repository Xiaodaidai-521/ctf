import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compile, createSSRApp, h, nextTick, reactive, ref, watch } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { compileScript, compileTemplate, parse } from 'vue/compiler-sfc'

const read = file => readFileSync(new URL(file, import.meta.url), 'utf8')
function workbench(hash = '') {
  const route = reactive({ path: '/teacher/feedback', query: { status: 'reopened' }, hash })
  const destinations = []
  let unmount
  const script = parse(read('../FeedbackWorkbench.vue')).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  const page = runInNewContext(`${script}\n;({ candidateOpen, queueSection, candidateSection, focusSection, goToSection, sectionReady })`, {
    ref, watch, nextTick, requestAnimationFrame: fn => fn(), useRoute: () => route,
    useRouter: () => ({ replace: target => { destinations.push(JSON.parse(JSON.stringify(target))); Object.assign(route, target); return Promise.resolve() } }),
    onMounted() {}, onBeforeUnmount: fn => { unmount = fn },
  })
  return { page, route, destinations, unmount: () => unmount() }
}

for (const file of ['../FeedbackWorkbench.vue', '../FeedbackQueue.vue']) {
  test(`length fix: ${file} keeps a compilable native disclosure`, () => {
    const { descriptor, errors } = parse(read(file))
    assert.deepEqual(errors, [])
    assert.ok(compileScript(descriptor, { id: file }).content)
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: file }).errors, [])
    assert.match(descriptor.template.content, /<details[^>]*class="[^"]*length-disclosure/)
    assert.match(descriptor.template.content, /<summary class="length-disclosure__summary">/)
    assert.doesNotMatch(descriptor.template.content, /<details[^>]*\bname=/)
  })
}

test('default feedback keeps the queue mounted and collapses candidates without lazy-remounting them', async () => {
  const { page } = workbench()
  assert.equal(page.candidateOpen.value, false)
  const app = createSSRApp({ render: compile(parse(read('../FeedbackWorkbench.vue')).descriptor.template.content), setup: () => page })
  for (const name of ['FeedbackQueue', 'FeedbackCandidates']) app.component(name, { props: ['embedded'], setup: () => () => h('div', { 'data-preserved': name }) })
  app.component('router-link', { props: ['to'], setup: (props, { slots }) => () => h('a', { href: props.to }, slots.default?.()) })
  const html = await renderToString(app)
  assert.match(html, /data-preserved="FeedbackQueue"/)
  assert.match(html, /data-preserved="FeedbackCandidates"/)
  assert.doesNotMatch(html.match(/<details[^>]*>/)?.[0] || '', /\bopen(?:=|\s|>)/)
  assert.doesNotMatch(read('../FeedbackWorkbench.vue'), /<Feedback(?:Queue|Candidates)[^>]*v-(?:if|show)/)
  assert.match(html, /href="\/teacher\/feedback\/reconciliation"/)
})

test('candidate links and legacy anchors reveal their retained panel before focusing it', async () => {
  const { page, destinations } = workbench()
  const calls = []
  page.candidateSection.value = { focus: () => calls.push(['focus', page.candidateOpen.value]), scrollIntoView: () => calls.push(['scroll', page.candidateOpen.value]) }
  await page.goToSection('#candidates')
  assert.equal(page.candidateOpen.value, true)
  assert.deepEqual(calls, [['focus', true], ['scroll', true]])
  assert.deepEqual(destinations.at(-1), { path: '/teacher/feedback', query: { status: 'reopened' }, hash: '#candidates' })
  page.candidateOpen.value = false
  await page.focusSection()
  assert.equal(page.candidateOpen.value, true)
  assert.equal(workbench('#candidates').page.candidateOpen.value, true)
})

test('sampling navigation opens the native panel and focuses its accessible summary', async () => {
  const { page } = workbench()
  const sampling = { open: false }
  const calls = []
  const summary = { focus: () => calls.push(['focus', sampling.open]), scrollIntoView: () => calls.push(['scroll', sampling.open]) }
  page.queueSection.value = { querySelector: selector => selector === '#feedback-sampling' ? sampling : summary }
  await page.goToSection('#sampling')
  assert.equal(sampling.open, true)
  assert.deepEqual(calls, [['focus', true], ['scroll', true]])
})

test('sampling disclosure retains every input and write/read action while defaulting closed', () => {
  const template = parse(read('../FeedbackQueue.vue')).descriptor.template.content
  const opening = template.match(/<details id="feedback-sampling"[^>]*>/)?.[0]
  assert.ok(opening)
  assert.doesNotMatch(opening, /\bopen(?:=|\s|>)/)
  for (const field of ['status', 'sample_size', 'random_seed', 'exclude_prior', 'risk_ticket_ids', 'notes']) assert.match(template, new RegExp(`v-model(?:\\.number)?="batchForm\\.${field}"`))
  for (const action of ['createBatch', 'loadRiskTickets', 'loadBatchNames', 'loadBatches', 'loadBatch(batch.batch_id)']) assert.ok(template.includes(`@click="${action}"`), action)
  assert.match(template, /最近批次/)
  assert.match(template, /selectedBatch\.items/)
  assert.doesNotMatch(template, /<details[^>]*v-if|<div[^>]*v-if=".*(?:sampling|candidateOpen)/)
})

test('disclosure styling remains class-bounded, token-based and keyboard-visible', () => {
  const css = read('../../shared/layout/disclosure.css')
  assert.match(css, /\.length-disclosure > \.length-disclosure__summary:focus-visible/)
  assert.match(css, /min-height: var\(--control-height\)/)
  assert.doesNotMatch(css, /#[\da-f]{3,8}\b|rgba?\(|display:\s*none;[^}]*\.length-disclosure__body/i)
})
