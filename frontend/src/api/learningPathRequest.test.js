import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

test('learning path join uses the existing authenticated start action and returns its real progress', async () => {
  const source = readFileSync(new URL('./index.js', import.meta.url), 'utf8')
  const start = source.indexOf('  learningPaths: {')
  const end = source.indexOf('\n  },', start) + 5
  assert.ok(start > 0 && end > start)
  const calls = []
  const progress = Object.freeze({ learning_path: 7, progress_percentage: 40, started_at: '2026-10-01T08:00:00Z' })
  const api = { post: async (...args) => { calls.push(args); return progress } }
  const paths = runInNewContext(`({${source.slice(start, end)}}).learningPaths`, { api })
  assert.equal(await paths.start(7), progress)
  assert.deepEqual(calls, [['/learning-paths/paths/7/start/']])
})
