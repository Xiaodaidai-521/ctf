<template>
  <ol class="teaching-progress" :aria-label="`教学进度：${progress.label}`">
    <li v-for="step in progress.items" :key="step.index" :class="step.state">
      <span class="step-dot" aria-hidden="true">{{ step.index }}</span><span class="step-name">{{ step.name }}</span>
    </li>
  </ol>
</template>
<script setup>
import { computed } from 'vue'
import { progressFrom } from '../presentation.js'
const props = defineProps({ messages: { type: Array, default: () => [] } })
const progress = computed(() => progressFrom(props.messages))
</script>
<style scoped>
.teaching-progress { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); margin: 0; padding: 0; list-style: none; color: var(--ink-muted); font-size: var(--text-caption); }
.teaching-progress li { display: flex; align-items: center; gap: var(--space-1); }
.teaching-progress li + li::before { content: ''; width: var(--space-3); height: var(--stroke); background: var(--line); margin-right: var(--space-1); }
.step-dot { display: grid; place-items: center; width: var(--space-4); height: var(--space-4); border: var(--stroke) solid var(--line); border-radius: 50%; font-size: var(--text-caption); }
.done { color: var(--ink-secondary); }
.done .step-dot { background: var(--agent-soft); border-color: transparent; color: var(--agent-accent); }
.current { color: var(--ink); }
.current .step-dot { border-color: var(--agent-accent); color: var(--agent-accent); }
.unknown { color: var(--ink-muted); }
.is-compact .step-name { display: none; }
</style>
