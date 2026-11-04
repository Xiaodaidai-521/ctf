<template>
  <section class="path-recommendations" aria-label="学习航线">
    <header class="path-heading">
      <h3>{{ names.paths }}</h3>
      <router-link to="/learning-paths">全部{{ names.paths }}</router-link>
    </header>
    <p v-if="error" class="path-state error" role="alert">{{ error }} <button type="button" class="text-action" @click="$emit('retry')">重试</button></p>
    <p v-if="loading" class="path-state" role="status">正在读取{{ names.paths }}…</p>
    <p v-else-if="!authenticated" class="path-state">登录后可读取个性化推荐；以下为公开可选航线。</p>
    <template v-if="!loading">
      <ul v-if="views.length" class="path-list">
        <li v-for="view in views" :key="view.key">
          <div class="path-copy">
            <router-link :to="view.to" class="path-title">{{ view.title }}</router-link>
            <p class="path-meta">{{ view.meta }}</p>
            <p class="path-reason">{{ view.reason }}</p>
          </div>
          <span class="path-badge">{{ view.badge }}</span>
        </li>
      </ul>
      <p v-else-if="!error" class="path-state">暂时没有可选{{ names.paths }}。</p>
    </template>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import { names } from '@/shared/navigation/names.js'
import { asList } from '@/learning/contracts.js'
import { progressSummary } from '@/learning/paths/api.js'
const props = defineProps({
  recommendations: { type: Array, default: () => [] },
  joined: { type: Array, default: () => [] },
  optional: { type: Array, default: () => [] },
  loading: Boolean,
  error: { type: String, default: '' },
  authenticated: Boolean,
})
defineEmits(['retry'])
const joinedIds = computed(() => new Set(asList(props.joined).map(item => String(item.learning_path ?? item.id))))
// 真实推荐优先；已在学航线标“继续”；其余明确是“可选航线”，不冒充个性化推荐。
const views = computed(() => {
  const list = []
  const seen = new Set()
  for (const item of asList(props.recommendations)) {
    const id = item.path_id ?? item.learning_path ?? item.id
    if (id === undefined || seen.has(String(id))) continue
    seen.add(String(id))
    list.push({
      key: `rec-${id}`, to: `/learning-paths/${id}`,
      title: item.title || item.path_title || '学习航线',
      meta: [item.difficulty, item.estimated_hours ? `${item.estimated_hours} 小时` : null].filter(Boolean).join(' · ') || '难度与时长暂未提供',
      reason: item.reason || item.recommend_reason || '来自系统推荐',
      badge: '推荐',
    })
  }
  for (const record of asList(props.joined)) {
    const id = record.learning_path ?? record.id
    if (id === undefined) continue
    seen.add(String(id))
    const summary = progressSummary(record)
    list.push({
      key: `joined-${id}`, to: record.current_module ? `/learning-paths/${id}/modules/${record.current_module}` : `/learning-paths/${id}`,
      title: record.path_title || record.title || '在学航线',
      meta: summary.percent === null ? '进度暂不可读取' : `已完成 ${summary.percent}%`,
      reason: '已加入的航线，按顺序继续。', badge: '继续',
    })
  }
  // 其余公开航线明确标注“可选航线”，不冒充个性化推荐。
  for (const item of asList(props.optional)) {
    const id = item.id ?? item.learning_path
    if (id === undefined || seen.has(String(id)) || joinedIds.value.has(String(id))) continue
    seen.add(String(id))
    list.push({
      key: `optional-${id}`, to: `/learning-paths/${id}`,
      title: item.title || '学习航线',
      meta: [item.difficulty, item.estimated_hours ? `${item.estimated_hours} 小时` : null].filter(Boolean).join(' · ') || '难度与时长暂未提供',
      reason: '公开可选航线，可先查看章节安排再决定。', badge: '可选航线',
    })
  }
  return list.slice(0, 4)
})
</script>
<style scoped>
.path-recommendations { padding: var(--space-3); background: var(--surface); border-radius: var(--radius-panel); }
.path-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); margin-bottom: var(--space-2); }
.path-heading h3 { margin: 0; font-size: var(--text-card); }
.path-heading a { color: var(--ink-secondary); font-size: var(--text-caption); }
.path-state { margin: 0 0 var(--space-2); color: var(--ink-secondary); font-size: var(--text-caption); }
.path-state.error { padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--negative-soft); color: var(--negative); }
.text-action { border: 0; background: transparent; color: var(--action); cursor: pointer; padding: 0; }
.path-list { display: grid; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }
.path-list li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-2); align-items: start; padding-top: var(--space-2); border-top: var(--stroke) solid var(--line); }
.path-list li:first-child { border-top: 0; padding-top: 0; }
.path-title { color: var(--ink); font-weight: var(--weight-medium); }
.path-meta, .path-reason { margin: var(--space-1) 0 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.path-reason { color: var(--ink-muted); }
.path-badge { padding: 2px var(--space-1); border-radius: var(--radius-pill); background: var(--agent-soft); color: var(--agent-accent); font-size: var(--text-caption); }
</style>
