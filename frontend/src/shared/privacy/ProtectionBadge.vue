<template>
  <span v-if="view.visible" class="protection-badge" :class="{ confirmed: view.confirmed }">
    <span v-if="compact" :title="view.explanation">{{ view.label }}</span>
    <details v-else>
      <summary>{{ view.label }}</summary>
      <span class="protection-explanation">{{ explanation || view.explanation }}</span>
    </details>
  </span>
</template>
<script setup>
import { computed } from 'vue'
import { protectionView } from './presentation.js'
const props = defineProps({ status: Object, label: { type: String, default: '加密保存' }, explanation: String, compact: Boolean })
const view = computed(() => protectionView(props.status, props.label))
</script>
<style scoped>
.protection-badge { display: inline-block; font-size: 12px; color: var(--ink-secondary, #555); line-height: 1.7; }
.confirmed { color: var(--success, #28744b); }
summary { cursor: pointer; border-radius: 4px; }
summary:focus-visible { outline: 2px solid var(--action, #3366cc); outline-offset: 3px; }
.protection-explanation { display: block; max-width: 38em; margin-block: 4px; color: var(--ink-secondary, #555); font-weight: normal; }
</style>
