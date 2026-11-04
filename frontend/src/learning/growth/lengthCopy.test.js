import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse } from 'vue/compiler-sfc'
import { baseParse } from '@vue/compiler-dom'

const files = ['GrowthSummary', 'LearningRecommendations', 'ReviewReminders', 'RetestList', 'SubmissionReview', 'LearningReport', 'MasteryOverview', 'LearningActivity']
function textNodes(node) {
  return [node.type === 2 ? node.content : '', ...(node.children || []).flatMap(textNodes)].join(' ')
}

test('all folded student growth blocks speak learning language without removing source and validity boundaries', () => {
  for (const name of files) {
    const source = readFileSync(new URL(`./components/${name}.vue`, import.meta.url), 'utf8')
    const template = parse(source).descriptor.template.content
    assert.doesNotMatch(textNodes(baseParse(template)), /接口|前端|后端|后台|渲染|持久接口|六字段|\bG\d{2}\b|\b(?:API|JSON|UUID|serializer)\b/, name)
  }
  const read = name => readFileSync(new URL(`./components/${name}.vue`, import.meta.url), 'utf8')
  assert.match(read('GrowthSummary'), /统计范围不同/)
  assert.match(read('ReviewReminders'), /本人自报，不等于通过无提示复测或已独立掌握/)
  assert.match(read('ReviewReminders'), /目前不能在这里添加复习任务/)
  assert.match(read('RetestList'), /到期未参加不记为知识错误/)
  assert.match(read('LearningActivity'), /不计入本人的学习汇总/)
  assert.match(read('LearningActivity'), /完整学习历史暂未提供/)
  assert.match(read('MasteryOverview'), /未记录的方向不以 0 补齐/)
  assert.match(read('LearningReport'), /不展示模拟周报/)
})
