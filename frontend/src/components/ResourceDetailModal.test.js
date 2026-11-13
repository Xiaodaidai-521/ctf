import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import * as Vue from 'vue'
import { parse } from 'vue/compiler-sfc'

const source = readFileSync(new URL('./ResourceDetailModal.vue', import.meta.url), 'utf8')
const script = parse(source).descriptor.scriptSetup.content.replace(/^import[^\n]*\n/gm, '')
const settle = async () => { await Vue.nextTick(); await Promise.resolve(); await Promise.resolve() }

function harness() {
  const props = Vue.reactive({ resourceId: 1, highlightResourceId: null })
  const details = [], downloads = [], unmount = []
  const scope = Vue.effectScope()
  const api = { resource: {
    detail(id, params) { return new Promise((resolve, reject) => details.push({ id, params, resolve, reject })) },
    download(id, params) { return new Promise((resolve, reject) => downloads.push({ id, params, resolve, reject })) },
  } }
  const page = scope.run(() => vm.runInNewContext(`${script}\n;({ resource, loading, showPreview, previewMarkdown, previewLoading, message, canPreview, isImageFile, loadAiPreview, handleClose })`, {
    ...Vue, onBeforeUnmount: fn => unmount.push(fn), defineProps: () => props,
    defineEmits: () => () => {}, api, DOMPurify: { sanitize: text => text },
    marked: { parse: text => text }, console: { error() {} },
  }))
  return { props, page, details, downloads, dispose() { unmount.forEach(fn => fn()); scope.stop() } }
}

test('image preview uses safe API extension and rejects script-capable images', () => {
  const h = harness()
  try {
    h.page.resource.value = { id: 1, resource_type: 'document', file_type: '.png', file_name: 'resource-1.png', file_url: '/api/resources/1/download/' }
    assert.equal(h.page.canPreview.value, true)
    h.page.resource.value = { id: 1, resource_type: 'document', file_type: '.svg', file_name: 'unsafe.svg', file_url: '/api/resources/1/download/' }
    assert.equal(h.page.canPreview.value, false)
    h.page.resource.value = { id: 1, resource_type: 'document', file_type: '.png', file_url: null }
    assert.equal(h.page.canPreview.value, false)
  } finally { h.dispose() }
})

test('late old detail cannot replace a newly selected resource', async () => {
  const h = harness()
  try {
    h.props.resourceId = 2
    await settle()
    h.details[1].resolve({ id: 2, title: 'New', resource_type: 'document' })
    await settle()
    h.details[0].resolve({ id: 1, title: 'Old', resource_type: 'document' })
    await settle()
    assert.equal(h.page.resource.value.id, 2)
    assert.equal(h.page.loading.value, false)
  } finally { h.dispose() }
})

test('late old markdown cannot replace the current resource body', async () => {
  const h = harness()
  try {
    h.details[0].resolve({ id: 1, resource_type: 'ai_resource' })
    await settle()
    h.props.resourceId = 2
    await settle()
    h.details[1].resolve({ id: 2, resource_type: 'ai_resource' })
    await settle()
    h.downloads[1].resolve({ data: { text: async () => 'New body' } })
    await settle()
    h.downloads[0].resolve({ data: { text: async () => 'Old body' } })
    await settle()
    assert.equal(h.page.resource.value.id, 2)
    assert.equal(h.page.previewMarkdown.value, 'New body')
    assert.equal(h.page.previewLoading.value, false)
  } finally { h.dispose() }
})

test('old failure and clearing selection do not mutate the current state', async () => {
  const h = harness()
  try {
    h.props.resourceId = 2
    await settle()
    h.details[0].reject(new Error('Old request failed'))
    await settle()
    assert.equal(h.page.message.value, '')
    assert.equal(h.page.loading.value, true)
    h.props.resourceId = null
    await settle()
    h.details[1].resolve({ id: 2, resource_type: 'document' })
    await settle()
    assert.equal(h.page.resource.value, null)
    assert.equal(h.page.loading.value, false)
  } finally { h.dispose() }
})

test('close invalidates pending detail and preview responses', async () => {
  const h = harness()
  try {
    h.page.handleClose()
    h.details[0].resolve({ id: 1, resource_type: 'ai_resource' })
    await settle()
    assert.equal(h.page.resource.value, null)
    assert.equal(h.downloads.length, 0)
  } finally { h.dispose() }
})
