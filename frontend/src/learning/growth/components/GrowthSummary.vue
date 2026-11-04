<template>
  <section class="growth-summary" aria-labelledby="growth-summary-heading">
    <header class="summary-head">
      <div>
        <p class="eyebrow">{{ names.growth }} · 成长总览</p>
        <h1 id="growth-summary-heading">{{ greeting }}，{{ displayName }}</h1>
        <div v-if="tags.length" class="persona-tags" aria-label="画像标签">
          <span v-for="tag in tags" :key="tag" class="persona-tag">{{ tag }}</span>
        </div>
      </div>
      <router-link to="/profile" class="profile-link">查看个人画像与能力依据 →</router-link>
    </header>

    <p v-if="personaSummary" class="persona-summary">{{ personaSummary }}</p>

    <div class="summary-grid">
      <section class="progress-card" aria-labelledby="progress-heading">
        <h2 id="progress-heading">进度与画像</h2>
        <div class="progress-row">
          <div class="progress-item">
            <span class="progress-label">模块进度 · {{ modules.label }}</span>
            <strong>{{ formatPercent(modules.percent) }}</strong>
            <span class="progress-meta">{{ numberText(modules.completed) }} / {{ numberText(modules.total) }} 个模块</span>
          </div>
          <div class="progress-item">
            <span class="progress-label">做题记录 · {{ submissions.label }}</span>
            <strong>{{ formatPercent(submissions.percent) }}</strong>
            <span class="progress-meta">{{ numberText(submissions.completed) }} / {{ numberText(submissions.total) }}</span>
          </div>
        </div>
        <p class="source-note">模块进度与做题记录的统计范围不同，分别查看，不合成“总完成率”。</p>
      </section>

      <section class="next-card" aria-labelledby="next-heading">
        <h2 id="next-heading">下一步</h2>
        <ol v-if="actions.length" class="next-list">
          <li v-for="action in actions" :key="action.text">
            <span>{{ action.text }}</span>
            <small>{{ action.source }}</small>
          </li>
        </ol>
        <p v-else class="empty-note">画像与推荐暂未返回可执行的下一步；可从能力图或推荐区选择练习。</p>
        <div class="next-actions">
          <router-link to="/capability-map" class="text-link">看能力图谱</router-link>
          <router-link :to="recordsPath" class="text-link">测评记录{{ examCount === null ? '' : `（${examCount}）` }}</router-link>
          <router-link to="/my-results" class="text-link">结果与复盘</router-link>
        </div>
      </section>
    </div>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import { names } from '@/shared/navigation/names'
import { RECORDS_PATH } from '@/learning/exams/api.js'
import { formatPercent, nextActionsFrom, personaTags, progressSources } from '../presentation.js'

const props = defineProps({
  displayName: { type: String, default: '' },
  profile: { type: Object, default: null },
  persona: { type: Object, default: null },
  progressReport: { type: Object, default: null },
  submissionStats: { type: Object, default: null },
  recommendations: { type: Array, default: () => [] },
  examCount: { type: Number, default: null },
})
const recordsPath = RECORDS_PATH
const modules = computed(() => progressSources(props.progressReport, props.submissionStats).modules)
const submissions = computed(() => progressSources(props.progressReport, props.submissionStats).submissions)
const tags = computed(() => personaTags(props.persona))
const personaSummary = computed(() => props.persona?.persona_traits?.summary || '')
const actions = computed(() => nextActionsFrom(props.persona, props.recommendations))
const numberText = value => (value === null || value === undefined ? '—' : value)
const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) return '早上好'
  if (hour < 18) return '下午好'
  return '晚上好'
})
</script>
<style scoped>
.growth-summary { display: grid; gap: var(--space-2); }
.summary-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.eyebrow { margin: 0 0 2px; color: var(--ink-secondary); font-size: var(--text-caption); }
.summary-head h1 { margin: 0 0 var(--space-1); font-size: var(--text-page); line-height: var(--leading-tight); }
.persona-tags { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.persona-tag { padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--action-soft); color: var(--action); font-size: var(--text-caption); }
.profile-link, .text-link { display: inline-flex; align-items: center; min-height: var(--control-height); color: var(--action); font-size: var(--text-caption); text-decoration: none; }
.persona-summary { margin: 0; max-width: var(--reading-width); color: var(--ink-secondary); }
.summary-grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: var(--space-2); }
.progress-card, .next-card { min-width: 0; padding: var(--space-3); border-radius: var(--radius-panel); background: var(--surface); }
.progress-card h2, .next-card h2 { margin: 0 0 var(--space-2); font-size: var(--text-section); }
.progress-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-2); }
.progress-item { display: grid; gap: var(--space-1); padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); }
.progress-label { color: var(--ink-secondary); font-size: var(--text-caption); }
.progress-item strong { font-size: var(--text-page); line-height: var(--leading-tight); }
.progress-meta { color: var(--ink-muted); font-size: var(--text-caption); }
.source-note { margin: var(--space-2) 0 0; color: var(--ink-muted); font-size: var(--text-caption); }
.next-list { display: grid; gap: var(--space-1); margin: 0; padding-left: var(--space-3); }
.next-list li { display: grid; gap: 2px; }
.next-list small { color: var(--ink-muted); font-size: var(--text-caption); }
.empty-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.next-actions { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-2); }
.text-link:focus-visible, .profile-link:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.is-compact .summary-grid, .is-compact .progress-row { grid-template-columns: minmax(0, 1fr); }
</style>
