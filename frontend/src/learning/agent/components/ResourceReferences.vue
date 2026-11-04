<template>
  <section v-if="view.state !== 'ready'" class="resource-state" :class="view.state" aria-live="polite">
    <AppIcon :name="view.state === 'error' ? 'bi-exclamation-octagon' : 'bi-info-circle'" />{{ view.message }}
  </section>
  <section v-else class="resource-references" aria-label="参考学习资料">
    <h3><AppIcon name="bi-book" />参考学习资料</h3>
    <ul>
      <li v-for="item in view.items" :key="`${item.id}-${item.title}`">
        <span class="resource-title">{{ item.title }}</span>
        <small v-if="item.reason" class="resource-reason">{{ item.reason }}</small>
        <small v-else class="resource-reason">来自本次教学检索</small>
      </li>
    </ul>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import AppIcon from '@/shared/design/AppIcon.vue'
import { resourceView } from '../presentation.js'
const props = defineProps({
  resources: { type: Array, default: () => [] },
  error: { type: String, default: '' },
})
const view = computed(() => resourceView(props.resources, props.error))
</script>
<style scoped>
.resource-state { display: flex; align-items: center; gap: var(--space-1); padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.resource-state.error { color: var(--negative); background: var(--negative-soft); }
.resource-references { padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); }
.resource-references h3 { display: flex; align-items: center; gap: var(--space-1); margin: 0 0 var(--space-1); color: var(--ink-secondary); font-size: var(--text-caption); font-weight: var(--weight-medium); }
.resource-references ul { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.resource-references li { display: grid; gap: 2px; padding: var(--space-1) 0; border-top: var(--stroke) solid var(--line); }
.resource-references li:first-child { border-top: 0; }
.resource-title { color: var(--ink); }
.resource-reason { color: var(--ink-muted); font-size: var(--text-caption); }
</style>
