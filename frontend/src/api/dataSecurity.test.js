import test from 'node:test'
import assert from 'node:assert/strict'
import service, { http } from './index.js'

test('data protection controls send the existing server routes and preserve request bindings', async () => {
  const requests = []
  const previous = http.defaults.adapter
  http.defaults.adapter = async config => {
    requests.push({ method: config.method, url: config.url, params: config.params, body: config.data ? JSON.parse(config.data) : undefined })
    return { status: 200, statusText: 'OK', data: { accepted: true }, headers: {}, config }
  }
  try {
    await service.dataSecurity.policies()
    await service.dataSecurity.preview('mixed')
    await service.dataSecurity.revealRequests({ offset: 20, limit: 20 })
    await service.dataSecurity.revealSource({ source_id: 7, field: 'email', field_ref: 'users.ctfuser/email', course_id: 9 })
    const draft = { object_ref: 'user/7', object_version: 'v2', fields: [['email', 'users.ctfuser/email']], purpose: 'investigation', reason: '核对资料', course_id: 9 }
    await service.dataSecurity.createRevealRequest(draft)
    for (const action of ['approve', 'reject', 'revoke']) await service.dataSecurity.decideRevealRequest('reveal-request-a/b', action)
    await service.dataSecurity.statistics({ offset: 40 })
    assert.deepEqual(requests, [
      { method: 'get', url: '/data-security/policies/', params: undefined, body: undefined },
      { method: 'post', url: '/data-security/preview/', params: undefined, body: { case: 'mixed' } },
      { method: 'get', url: '/data-security/reveal-requests/', params: { offset: 20, limit: 20 }, body: undefined },
      { method: 'get', url: '/data-security/reveal-source/', params: { source_id: 7, field: 'email', field_ref: 'users.ctfuser/email', course_id: 9 }, body: undefined },
      { method: 'post', url: '/data-security/reveal-requests/', params: undefined, body: draft },
      ...['approve', 'reject', 'revoke'].map(action => ({ method: 'post', url: `/data-security/reveal-requests/reveal-request-a%2Fb/${action}/`, params: undefined, body: {} })),
      { method: 'get', url: '/data-security/stats/', params: { offset: 40 }, body: undefined },
    ])
    const count = requests.length
    await assert.rejects(service.dataSecurity.decideRevealRequest('reveal-request-a', 'read'))
    assert.equal(requests.length, count, 'approval controls cannot send an original-content read')
  } finally { http.defaults.adapter = previous }
})
