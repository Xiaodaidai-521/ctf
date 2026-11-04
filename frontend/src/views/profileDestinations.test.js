import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { ref } from 'vue'
import { parse } from 'vue/compiler-sfc'

const source = readFileSync(new URL('./Profile.vue', import.meta.url), 'utf8')
const script = parse(source).descriptor.scriptSetup.content

test('profile path progress uses learning_path identity, not progress record identity', async () => {
  const block = script.slice(script.indexOf('const fetchLearningPaths ='), script.indexOf('const fetchPersona ='))
  const learningPaths = ref([])
  const page = runInNewContext(`${block};({ fetchLearningPaths })`, {
    api: { learningPaths: { my: async () => ({ results: [{ id: 93, learning_path: 17, path_title: '原航线', progress_percentage: 35, completed_modules: 2, total_modules: 6, completed_labs: 1, total_labs: 4 }] }) } },
    learningPaths, console,
  })
  await page.fetchLearningPaths()
  assert.deepEqual(JSON.parse(JSON.stringify(learningPaths.value)), [{ id: 17, title: '原航线', progress: 35, completed_modules: 2, total_modules: 6, completed_experiments: 1, total_experiments: 4 }])
})

test('profile reads real paginated and array submission records without dropping fields', async () => {
  const block = script.slice(script.indexOf('const fetchSubmissions ='), script.indexOf('const fetchFavorites ='))
  const record = { id: 8, challenge_title: '原题目', category_name: '原分类', created_at: '2026-11-02T18:00:00Z', is_correct: true, flag: 'flag{original}', extra: { retained: true } }
  for (const response of [{ count: 1, results: [record] }, [record]]) {
    const submissions = ref([])
    const page = runInNewContext(`${block};({ fetchSubmissions })`, { api: { submission: { mySubmissions: async () => response } }, submissions, console })
    await page.fetchSubmissions()
    assert.deepEqual(JSON.parse(JSON.stringify(submissions.value)), [record])
  }
})

test('profile continues original path and opens original challenge route', () => {
  const block = script.slice(script.indexOf('const handleTrackPath ='), script.indexOf('onMounted(async'))
  const calls = []
  const page = runInNewContext(`${block};({ handleTrackPath, handleChallengeClick })`, { router: { push: value => calls.push(value) } })
  page.handleTrackPath({ id: 17 })
  page.handleChallengeClick({ id: 42 })
  assert.deepEqual(calls, ['/learning-paths/17', '/challenge/42'])
  const routes = readFileSync(new URL('../router/index.js', import.meta.url), 'utf8')
  assert.match(routes, /path: '\/challenge\/:id'/)
})
