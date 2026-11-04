<template>
  <article class="artifact-view" :class="`is-${artifact.kind}`">
    <header class="artifact-heading">
      <span class="artifact-kind">{{ kindLabel }}</span>
      <strong>{{ artifact.title || sourceLabel }}</strong>
      <small class="artifact-source">{{ sourceLabel }}<template v-if="artifact.updatedAt"> · {{ updatedLabel }}</template></small>
    </header>

    <template v-if="artifact.kind === 'plan'">
      <p v-if="artifact.summary" class="artifact-summary">{{ artifact.summary }}</p>
      <ol v-if="artifact.items.length" class="artifact-list">
        <li v-for="item in artifact.items" :key="`${item.index}-${item.title}`">
          <strong>{{ item.title }}</strong><span v-if="item.duration" class="artifact-duration">{{ item.duration }}</span>
          <ul v-if="item.actions.length"><li v-for="action in item.actions" :key="action">{{ action }}</li></ul>
          <p v-if="item.reason" class="artifact-reason">理由：{{ item.reason }}</p>
        </li>
      </ol>
      <p v-if="artifact.note" class="artifact-note">{{ artifact.note }}</p>
    </template>

    <template v-else-if="artifact.kind === 'path'">
      <p class="artifact-summary">{{ artifact.currentTitle || '到航线中选择章节' }}</p>
      <p class="artifact-meta">
        <span v-if="artifact.completed !== null && artifact.total !== null">已完成 {{ artifact.completed }} / {{ artifact.total }} 个章节</span>
        <span v-else>章节进度暂不可读取</span>
      </p>
      <p class="artifact-reason">理由：{{ artifact.reason }}</p>
      <router-link class="artifact-link" :to="artifact.target">继续学习</router-link>
    </template>

    <template v-else-if="artifact.kind === 'review'">
      <ul v-if="artifact.items.length" class="artifact-list review-items">
        <li v-for="item in artifact.items" :key="item.id">
          <strong>{{ item.concept }}</strong>
          <span class="artifact-meta"><template v-if="item.probability !== null">记忆概率 {{ percent(item.probability) }}</template><template v-else>概率暂未提供</template><template v-if="item.dueAt"> · {{ dateLabel(item.dueAt) }} 复习</template></span>
          <p v-if="item.reason" class="artifact-reason">{{ item.reason }}</p>
        </li>
      </ul>
      <p v-else-if="artifact.failed" class="artifact-note">复习提醒暂时无法读取，不代表没有待复习内容。</p>
      <p v-else class="artifact-note">目前没有待复习提醒。</p>
    </template>

    <slot name="actions" />
  </article>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ artifact: { type: Object, required: true } })
const kindLabel = computed(() => ({ plan: '教学建议', path: '航线进度', review: '复习提醒' }[props.artifact.kind] || '教学产出'))
const sourceLabel = computed(() => props.artifact.source || '教学记录')
const updatedLabel = computed(() => {
  const time = Date.parse(props.artifact.updatedAt)
  return Number.isFinite(time) ? new Date(time).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''
})
const percent = value => `${Math.round(value * 100)}%`
const dateLabel = value => {
  const time = Date.parse(value)
  return Number.isFinite(time) ? new Date(time).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) : '日期未知'
}
</script>
<style scoped>
.artifact-view { display: grid; gap: var(--space-1); padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.artifact-heading { display: grid; gap: 2px; }
.artifact-kind { color: var(--agent-accent); font-size: var(--text-caption); }
.artifact-heading strong { font-size: var(--text-body); }
.artifact-source { color: var(--ink-muted); font-size: var(--text-caption); }
.artifact-summary { margin: 0; color: var(--ink-secondary); }
.artifact-list { display: grid; gap: var(--space-1); margin: 0; padding-left: var(--space-2); }
.artifact-list ul { margin: var(--space-1) 0 0; padding-left: var(--space-2); color: var(--ink-secondary); }
.artifact-duration { margin-left: var(--space-1); color: var(--ink-muted); font-size: var(--text-caption); }
.artifact-reason { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.artifact-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.artifact-meta { display: block; color: var(--ink-secondary); font-size: var(--text-caption); }
.artifact-link { color: var(--action); font-size: var(--text-caption); }
</style>
