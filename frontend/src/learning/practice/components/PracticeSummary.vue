<template>
  <section class="practice-summary" aria-label="练习概览">
    <div class="summary-main">
      <p class="summary-eyebrow">{{ names.practice }} · 个人练习</p>
      <h2>{{ headline }}</h2>
      <p v-if="!authenticated" class="summary-note">练习进度按账号保存，重新进入后可接着上次。<router-link to="/login">去登录</router-link></p>
      <p v-else-if="statsError" class="summary-note summary-error" role="alert">
        {{ statsError }}<button type="button" class="text-action" @click="$emit('retry')">重试</button>
      </p>
      <p v-else class="summary-note">解题统计来自本人提交记录；筛选中已解数只对已完整读取的范围给结论。</p>
    </div>
    <dl class="summary-stats">
      <div><dt>我的积分</dt><dd>{{ score }}</dd></div>
      <div><dt>已解出</dt><dd>{{ solved }}</dd></div>
      <div><dt>总提交</dt><dd>{{ submissions }}</dd></div>
    </dl>
    <p class="summary-division">靶场用于练习；正式测评在<router-link to="/exam-center">试炼场</router-link>；题内辅导先讲思路再练习。</p>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import { names } from '@/shared/navigation/names.js'
defineEmits(['retry'])
const props = defineProps({
  authenticated: Boolean,
  stats: { type: Object, default: null },
  statsError: { type: String, default: '' },
  solvedCount: { type: Number, default: null },
  solvedScope: { type: String, default: '' },
})
const number = value => (value === null || value === undefined ? '—' : value)
const score = computed(() => props.authenticated ? number(props.stats?.score) : '登录后查看')
const solved = computed(() => {
  if (!props.authenticated) return '—'
  if (props.solvedCount === null) return '—'
  return props.solvedScope === 'loaded' ? `${props.solvedCount}（当前已加载）` : String(props.solvedCount)
})
const submissions = computed(() => props.authenticated ? number(props.stats?.total_submissions) : '—')
const headline = computed(() => props.authenticated
  ? (props.solvedCount ? '继续练习，保持手感' : '从一道题开始练习')
  : '登录后记录你的练习进度')
</script>
<style scoped>
.practice-summary { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: var(--space-3); padding: var(--space-3); background: var(--surface); border-radius: var(--radius-panel); box-shadow: var(--shadow-raised); }
.summary-eyebrow { margin: 0 0 var(--space-1); color: var(--agent-accent); font-size: var(--text-caption); }
.summary-main h2 { margin: 0 0 var(--space-1); font-size: var(--text-section); line-height: var(--leading-tight); }
.summary-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.summary-note a { margin-left: var(--space-1); color: var(--action); }
.summary-error { color: var(--negative); }
.text-action { margin-left: var(--space-1); border: 0; background: transparent; color: var(--action); cursor: pointer; padding: 0; font: inherit; }
.summary-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-2); margin: 0; align-items: center; }
.summary-stats dt { color: var(--ink-secondary); font-size: var(--text-caption); }
.summary-stats dd { margin: 0; font-size: var(--text-card); font-weight: var(--weight-strong); }
.summary-division { grid-column: 1 / -1; margin: 0; padding-top: var(--space-2); border-top: var(--stroke) solid var(--line); color: var(--ink-muted); font-size: var(--text-caption); }
@media (max-width: 768px) {
  .practice-summary { grid-template-columns: minmax(0, 1fr); }
  .summary-stats dd { font-size: var(--text-body); }
}
</style>
