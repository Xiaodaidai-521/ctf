<template>
  <section v-if="phase !== 'idle' || error" class="execution-status" :class="phase" aria-live="polite">
    <AppIcon :name="icon" />
    <span>{{ text }}</span>
    <button v-if="phase === 'working'" type="button" class="stop-action" @click="$emit('stop')">停止等待</button>
  </section>
</template>
<script setup>
import { computed } from 'vue'
import AppIcon from '@/shared/design/AppIcon.vue'
const props = defineProps({ phase: { type: String, default: 'idle' }, error: { type: String, default: '' } })
defineEmits(['stop'])
const text = computed(() => {
  if (props.error) return props.error
  return {
    working: '正在组织讲解，请稍候…',
    complete: '讲解已准备好',
    error: '这次讲解没有完成，请稍后再试。',
    idle: '',
  }[props.phase] || ''
})
const icon = computed(() => ({
  working: 'bi-arrow-repeat', complete: 'bi-check-circle', error: 'bi-exclamation-octagon',
}[props.phase] || 'bi-info-circle'))
</script>
<style scoped>
.execution-status { display: flex; align-items: center; gap: var(--space-1); padding: var(--space-1) var(--space-2); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.execution-status.complete { color: var(--positive); background: var(--positive-soft); }
.execution-status.error { color: var(--negative); background: var(--negative-soft); }
.stop-action { margin-left: auto; border: 0; background: transparent; color: var(--ink-secondary); text-decoration: underline; cursor: pointer; }
</style>
