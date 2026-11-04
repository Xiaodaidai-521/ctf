import test from 'node:test'
import assert from 'node:assert/strict'
import { growthDestination, parseGrowthSection } from '../../shared/navigation/phase2.js'
import {
  GROWTH_SECTION_TARGETS, growthSection, growthSectionQuery, growthSectionTarget, growthWindow,
} from './sections.js'

test('growth section query uses the shared four sections and legacy aliases', () => {
  assert.equal(growthSection('activity'), 'activity')
  assert.equal(growthSection('analysis'), 'activity')
  assert.equal(growthSection('analytics'), 'activity')
  assert.equal(growthSection('results'), 'results')
  assert.equal(growthSection('review'), 'results')
  assert.equal(growthSection('capability'), 'capability')
  assert.equal(growthSection('mastery'), 'capability')
  assert.equal(growthSection('overview'), 'overview')
  assert.equal(growthSection('unknown'), null)
  assert.equal(growthSection(undefined), null)

  assert.equal(growthSectionTarget('analysis'), 'growth-activity')
  assert.equal(growthSectionTarget('review'), 'growth-results')
  assert.equal(growthSectionTarget('capability'), 'growth-mastery')
  assert.equal(growthSectionTarget('overview'), 'growth-overview')
  assert.equal(growthSectionQuery('growth-activity'), 'activity')
  assert.equal(growthSectionQuery('growth-results'), 'results')
  assert.equal(growthSectionQuery('growth-mastery'), 'capability')
  assert.equal(growthSectionQuery('growth-report'), null)
  // 页面锚点与 shared/navigation/phase2.js 的分区集合保持一一对应。
  assert.deepEqual(Object.keys(GROWTH_SECTION_TARGETS).sort(), ['activity', 'capability', 'overview', 'results'])
  assert.equal(parseGrowthSection('capability'), 'capability')
  assert.equal(growthDestination('activity', { window: 30 }), '/dashboard?section=activity&window=30')
})

test('learning activity windows accept only 7/30/90', () => {
  assert.equal(growthWindow(7), 7)
  assert.equal(growthWindow('30'), 30)
  assert.equal(growthWindow(90), 90)
  assert.equal(growthWindow(14), null)
  assert.equal(growthWindow('abc'), null)
  assert.equal(growthWindow(undefined), null)
})
