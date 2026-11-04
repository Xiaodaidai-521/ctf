import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

test('original administrator challenge create adapter keeps every payload field and existing endpoint', async () => {
  const source = readFileSync(new URL('./index.js', import.meta.url), 'utf8')
  const start = source.indexOf('  challenge: {')
  const end = source.indexOf('\n  },', start) + 5
  const calls = []
  const original = { title: '原题目', category: 3, difficulty: 'easy', score: 10, description: '原题目说明', flag: 'flag{original}', hint: '原提示', is_active: true, docker_image: 'local-only:offline', redirect_port: 80, redirect_type: '', extra: '原字段' }
  const reply = Object.freeze({ id: 17, ...original })
  const api = { post: async (...args) => { calls.push(args); return reply } }
  const challenge = runInNewContext(`({${source.slice(start, end)}}).challenge`, { api })
  assert.equal(await challenge.create(original), reply)
  assert.deepEqual(calls, [['/challenges/challenges/', original]])
})
