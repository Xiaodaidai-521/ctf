import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const router = read('../../router/index.js')
const entry = read('../../shared/navigation/DashboardEntry.vue')
const view = read('./GrowthView.vue')
const recommendations = read('./components/LearningRecommendations.vue')
const radar = read('../../components/AbilityRadarCard.vue')
const activity = read('./components/LearningActivity.vue')

test('/dashboard dispatches students to the growth overview and keeps teacher view', () => {
  assert.match(entry, /TeacherLearningDashboard v-if="isTeacher"/)
  assert.match(entry, /GrowthView v-else-if="isStudent"/)
  assert.match(entry, /import\('@\/learning\/growth\/GrowthView\.vue'\)/)
  assert.match(entry, /import\('@\/teacher\/TeacherLearningDashboard\.vue'\)/)
  // 教师业务页没有被替换成学生总览。
  assert.doesNotMatch(entry, /StudentDashboard v-else-if/)
})

test('/analytics keeps teacher access but sends students to the analysis section', () => {
  assert.match(router, /return \{ path: '\/dashboard', query: \{ \.\.\.to\.query, section: 'activity' \}, hash: to\.hash \}/)
  assert.match(router, /role === 'teacher' \|\| role === 'admin'/)
  assert.match(router, /path: '\/analytics'/)
})

test('growth overview uses shared section names and one recommendation request', () => {
  assert.match(view, /growthDestination/)
  assert.match(view, /growthSectionTarget/)
  assert.match(view, /growthSectionQuery/)
  assert.match(view, /id="growth-overview"/)
  assert.match(view, /id="growth-activity"/)
  assert.match(view, /id="growth-results"/)
  assert.match(view, /@loaded="recommendations = \$event"/)
  // 推荐只在 LearningRecommendations 内请求一次，总览不再重复拉取。
  assert.doesNotMatch(view, /api\.learningAgent\.recommend\(\)/)
  assert.match(recommendations, /emit\('loaded'/)
})

test('learning activity never renders the backend English placeholder message', () => {
  // 真实接口在没有快照时返回 message: 'Analytics snapshot is not available yet.'。
  assert.doesNotMatch(activity, /\{\{\s*effect\.message/)
  assert.match(activity, /emptyNote/)
  assert.match(activity, /这一时间窗还没有可绘制的学习日数据/)
  assert.match(activity, /暂不显示曲线、热度或累计天数/)
})

test('radar card delegates missing-score logic to the pure model', () => {
  assert.match(radar, /abilityModel/)
  assert.doesNotMatch(radar, /Number\(value\) \|\| 0/)
  assert.match(radar, /scoreText/)
})
