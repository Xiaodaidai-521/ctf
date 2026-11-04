import { createAccountGuard } from '../shared/state/accountScope.js'
import { accountMemoryStorage } from '../shared/state/retention.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { ref, computed, reactive, watch, nextTick, effectScope, compile, createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { parse } from 'vue/compiler-sfc'
import { createHubState } from '../learning/practice/hubStore.js'

function pageScript(file, globals, expose) {
  const source = readFileSync(new URL(`./${file}.vue`, import.meta.url), 'utf8')
  const script = parse(source).descriptor.scriptSetup.content.replace(/^import[\s\S]*?from ['"][^'"]+['"];?\s*/gm, '')
  return runInNewContext(`${script}\n;({ ${expose.join(', ')} })`, {
    ref, computed, watch, nextTick, createHubState, createAccountGuard, accountMemoryStorage,
    onMounted() {}, onUnmounted() {}, onActivated() {}, onDeactivated() {}, defineExpose() {},
    ...globals,
  })
}
function challenges(authenticated = true, api = {}) {
  const store = reactive({ challenges: [], categories: [], loading: false, fetchChallenges: async () => {}, fetchCategories: async () => {} })
  const page = pageScript('Challenges', { useChallengeStore: () => store, useUserStore: () => ({ isAuthenticated: authenticated }), api }, [
    'fetchChallenges', 'fetchCategories', 'fetchSubmissionStats', 'fetchRecentActivities', 'recentActivities',
    'listError', 'categoriesError', 'statsError', 'submissionStats', 'activitiesError', 'activitiesLoading',
    'selectedStatus', 'filteredChallenges', 'selectedChallenge', 'handleRandom', 'loadedChallenges', 'listLoading',
  ])
  return { page, store }
}
test('challenge failures have independent feedback; failed statistics never become zero', async () => {
  const scope = effectScope()
  const { page, store } = scope.run(() => challenges(true, { submission: { stats: async () => { throw Error('offline') } } }))
  store.fetchChallenges = store.fetchCategories = async () => { throw Error('offline') }
  await Promise.all([page.fetchChallenges(), page.fetchCategories(), page.fetchSubmissionStats()])
  assert.match(page.listError.value, /请重试/)
  assert.match(page.categoriesError.value, /分类/)
  assert.match(page.statsError.value, /统计/)
  assert.equal(page.submissionStats.value, null)
  store.fetchChallenges = async () => {}
  await page.fetchChallenges()
  assert.equal(page.listError.value, '')
  assert.notEqual(page.categoriesError.value, '')
  scope.stop()
})
test('challenge activity uses only own submissions and orders real records newest first', async () => {
  const scope = effectScope()
  let called = 0
  const rows = Array.from({ length: 7 }, (_, i) => ({ id: i, created_at: `2026-11-0${i + 1}T00:00:00Z`, challenge_title: `练习${i}` }))
  const { page } = scope.run(() => challenges(true, { submission: { mySubmissions: async () => { called++; return { results: rows } } } }))
  assert.equal(page.recentActivities.value.length, 0)
  await page.fetchRecentActivities()
  assert.equal(called, 1)
  assert.equal(page.recentActivities.value.length, 5)
  assert.equal(page.recentActivities.value[0].id, 6)
  assert.equal(rows[0].id, 0)
  assert.equal(page.activitiesLoading.value, false)
  scope.stop()
})
test('guest activity makes no private API call; status filtering and random selection remain functional', async () => {
  const scope = effectScope()
  const { page, store } = scope.run(() => challenges(false))
  await Promise.all([page.fetchRecentActivities(), page.fetchSubmissionStats()])
  store.fetchChallenges = async () => [{ id: 1, is_solved: true }, { id: 2, is_solved: false }]
  await page.fetchChallenges()
  page.selectedStatus.value = 'unsolved'
  await nextTick()
  page.handleRandom()
  assert.equal(page.selectedChallenge.value.id, 2)
  page.selectedChallenge.value = null
  page.listLoading.value = true
  page.handleRandom()
  assert.equal(page.selectedChallenge.value, null)
  scope.stop()
})
function resources(list) {
  return pageScript('Resources', {
    useRouter: () => ({}), useRoute: () => ({ query: {} }), useUserStore: () => ({ userInfo: { role: 'student' } }),
    api: { resource: { list } }, tutorResourceCenterIds: () => [],
  }, ['fetchResources', 'resources', 'listError', 'loading', 'total', 'currentPage', 'selectedType'])
}
test('resource failures have a retry state rather than a misleading empty list', async () => {
  const scope = effectScope()
  let fail = true
  const page = scope.run(() => resources(async () => { if (fail) throw Error('offline'); return { results: [{ id: 7 }], count: 1 } }))
  await page.fetchResources()
  assert.match(page.listError.value, /重试/)
  assert.equal(page.loading.value, false)
  fail = false
  await page.fetchResources()
  assert.equal(page.listError.value, '')
  assert.equal(page.resources.value[0].id, 7)
  scope.stop()
})
test('a late resource response cannot replace newer filters or clear their loading state', async () => {
  const scope = effectScope()
  const pending = []
  const page = scope.run(() => resources(params => new Promise(resolve => pending.push({ params, resolve }))))
  const first = page.fetchResources()
  page.selectedType.value = 'video'
  const second = page.fetchResources()
  assert.equal(pending[1].params.resource_type, 'video')
  pending[0].resolve({ results: [{ id: 1 }], count: 1 })
  await first
  assert.equal(page.loading.value, true)
  pending[1].resolve({ results: [{ id: 2 }], count: 1 })
  await second
  assert.equal(page.resources.value[0].id, 2)
  assert.equal(page.loading.value, false)
  scope.stop()
})
function examCenter(globals = {}) {
  const exams = {
    records: async () => ({ results: [] }),
    myHistory: async () => ({ records: [] }),
    startComprehensive: async () => ({ theory_record: { id: 8 } }),
    abandonComprehensive: async () => ({}),
  }
  return pageScript('ExamCenter', {
    useRouter: () => ({}),
    ...globals,
    examsApi: { ...exams, ...(globals.examsApi || {}) },
    RECORDS_PATH: '/exam-center/history',
  }, [
    'loadData', 'startExam', 'abandonAndStartNew', 'continueExam',
    'ongoingExamId', 'recordCount', 'loading', 'dataError', 'actionError', 'statusLabel', 'dataLoading',
  ])
}
test('pending vs in-progress decide the single primary action from real records', async () => {
  const routes = []
  let ongoing = null
  const page = examCenter({
    useRouter: () => ({ push: route => routes.push(route) }),
    examsApi: {
      records: async params => { assert.equal(params.status, 'in_progress'); return { results: ongoing ? [ongoing] : [] } },
      myHistory: async () => ({ records: [{ id: 1 }, { id: 2 }] }),
    },
  })
  await page.loadData()
  assert.equal(page.dataLoading.value, false)
  assert.equal(page.ongoingExamId.value, null)
  assert.equal(page.statusLabel.value, '待考')
  assert.equal(page.recordCount.value, 2)
  page.continueExam()
  assert.deepEqual(routes, [])
  await page.startExam()
  assert.deepEqual(routes, ['/exam-taking/8'])
  ongoing = { id: 41, status: 'in_progress' }
  await page.loadData()
  assert.equal(page.statusLabel.value, '进行中')
  page.continueExam()
  assert.deepEqual(routes, ['/exam-taking/8', '/exam-taking/41'])
})
test('exam status read failure never asserts there is no ongoing exam', async () => {
  const page = examCenter({
    examsApi: { records: async () => { throw Error('offline') }, myHistory: async () => { throw Error('offline') } },
  })
  await page.loadData()
  assert.equal(page.dataLoading.value, false)
  assert.match(page.dataError.value, /不会据此认为你没有进行中的测评/)
  assert.doesNotMatch(page.dataError.value, /offline/)
})
test('exam action failures stay readable, release loading and never expose backend error text', async () => {
  let existingRecord = null
  let confirmed = false
  const page = examCenter({
    confirm: () => confirmed,
    examsApi: {
      startComprehensive: async () => { throw { response: { data: { error: 'INTERNAL_SQL_DETAIL', exam_record_id: existingRecord } } } },
      abandonComprehensive: async () => { throw Error('offline') },
    },
  })
  await page.startExam()
  assert.match(page.actionError.value, /尚未创建成功/)
  assert.doesNotMatch(page.actionError.value, /INTERNAL_SQL_DETAIL/)
  assert.equal(page.loading.value, false)
  existingRecord = 19
  await page.startExam()
  assert.equal(page.ongoingExamId.value, 19)
  assert.match(page.actionError.value, /进行中的测评/)
  // 取消确认不写入任何状态。
  await page.abandonAndStartNew()
  assert.equal(page.ongoingExamId.value, 19)
  // 确认后放弃失败时不能假装已放弃。
  confirmed = true
  await page.abandonAndStartNew()
  assert.equal(page.ongoingExamId.value, 19)
  assert.match(page.actionError.value, /未能确认/)
  assert.equal(page.loading.value, false)
})


test('practice pagination renders the actual template with retained local list refs, without unwrap errors', async () => {
  const scope = effectScope()
  const { page, store } = scope.run(() => challenges(false))
  store.fetchChallenges = async () => ({ results: [{ id: 1, title: '练习', is_solved: false }], count: 30 })
  await page.fetchChallenges()
  const source = readFileSync(new URL('./Challenges.vue', import.meta.url), 'utf8')
  const desc = parse(source).descriptor
  // This real template branch previously failed only when count exceeded the first page.
  const text = desc.template.content.match(/<div v-if="!listLoading && !listError && hasMore"[\s\S]*?<\/div>/)[0]
  const app = createSSRApp({ render: compile(text), setup: () => ({ ...page, hasMore: true, totalCount: 30, loadingMore: false, loadMoreError: '', loadMore() {} }) })
  const html = await renderToString(app)
  assert.match(html, /加载更多题目（已显示 1 \/ 30）/)
  scope.stop()
})
