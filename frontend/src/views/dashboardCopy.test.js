import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'
import { dashboardCopy } from './dashboardCopy.js'

test('dashboard presents known model wording without inventing scores or changing unknown copy', () => {
  const original = 'DKT估计掌握率18%，AKT关注到相关知识与遗忘间隔，S3Rec/GNN依赖分100%。当前掌握率偏低。'
  assert.equal(dashboardCopy(original), '掌握度参考值18%，结合相关知识与复习间隔，前置知识参考值100%。当前掌握率偏低。')
  assert.equal(dashboardCopy('未知模型：original-id-17'), '未知模型：original-id-17')
  assert.equal(dashboardCopy('🎯 完成学习引导'), '完成学习引导')
  assert.equal(dashboardCopy(null), '')
})

test('dashboard retains original navigation and complete record downloads with local reflow', () => {
  const source = readFileSync(new URL('./StudentDashboard.vue', import.meta.url), 'utf8')
  const { descriptor, errors } = parse(source)
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'dashboard-copy' })
  const template = compileTemplate({ filename: 'StudentDashboard.vue', source: descriptor.template.content, id: 'dashboard-copy', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  assert.match(source, /item.action_link && router.push\(item.action_link\)/)
  assert.match(source, /downloadRecord\(item, '推荐依据.json'\)/)
  assert.match(source, /downloadRecord\(item, '洞察依据.json'\)/)
  assert.match(source, /\.rec-content\s*\{[^}]*min-width:0;[^}]*overflow-wrap:anywhere;/)
  assert.match(source, /\.rec-meta\s*\{[^}]*flex-wrap:wrap;/)
  assert.match(source, /\.card :deep\(\.arco-spin\)[\s\S]*?display:block;[\s\S]*?width:100%;[\s\S]*?max-width:100%;[\s\S]*?min-width:0;/)
  assert.match(source, /@media \(max-width: 768px\)[\s\S]*grid-template-columns:minmax\(0, 1fr\)/)
})
