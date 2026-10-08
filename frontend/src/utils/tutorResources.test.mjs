import assert from 'node:assert/strict'
import {
  clearRememberedTutorResources,
  loadRememberedTutorResources,
  rememberTutorResources,
  tutorResourceCenterIds,
  tutorResourceListFromResponse
} from './tutorResources.js'

const resources = tutorResourceListFromResponse({
  resources: [
    {
      id: 123,
      title: 'SQL 注入 AI 讲义',
      type: 'ai_resource',
      entry: '/resources?highlight_resource=123&resource=123',
      score: 0.93,
      matchScore: 0.91,
      source: 'rag'
    }
  ]
})

assert.equal(resources.length, 1)
assert.equal(resources[0].title, 'SQL 注入 AI 讲义')
assert.equal(resources[0].entry, '/resources?highlight_resource=123&resource=123')
assert.equal(resources[0].ai_generated_label, 'AI多模态生成')
assert.equal(resources[0].location, '资源中心 / AI多模态生成 / SQL 注入 AI 讲义')
assert.equal(Object.hasOwn(resources[0], 'score'), false)
assert.equal(Object.hasOwn(resources[0], 'matchScore'), false)
assert.equal(Object.hasOwn(resources[0], 'source'), false)

const none = tutorResourceListFromResponse({ noMatchedResource: true, resources: [] })
assert.deepEqual(none, [])

const memory = new Map()
globalThis.window = {
  sessionStorage: {
    getItem: (key) => memory.has(key) ? memory.get(key) : null,
    setItem: (key, value) => memory.set(key, value),
    removeItem: (key) => memory.delete(key)
  }
}

clearRememberedTutorResources()
rememberTutorResources(resources)
rememberTutorResources([{ ...resources[0], score: 1, source: 'internal' }])
const remembered = loadRememberedTutorResources()
assert.equal(remembered.length, 1)
assert.equal(remembered[0].entry, '/resources?highlight_resource=123&resource=123')
assert.equal(Object.hasOwn(remembered[0], 'score'), false)
assert.deepEqual(tutorResourceCenterIds(), [123])

clearRememberedTutorResources()
assert.deepEqual(loadRememberedTutorResources(), [])