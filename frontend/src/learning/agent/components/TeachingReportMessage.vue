<template>
  <section class="teaching-report" :class="{ 'is-open': expanded }">
    <button type="button" class="report-toggle" :aria-expanded="expanded" @click="expanded = !expanded">
      <span class="report-icon" aria-hidden="true"><AppIcon name="bi-clipboard-pulse" /></span>
      <span class="report-title"><strong>{{ report.title || '本次学习报告' }}</strong><small>{{ summaryText }}</small></span>
      <AppIcon :name="expanded ? 'bi-chevron-up' : 'bi-chevron-down'" />
    </button>
    <div v-if="expanded" class="report-body">
      <p v-if="report.note" class="report-note">{{ report.note }}</p>
      <dl class="report-fields">
        <template v-for="field in fields" :key="field.label">
          <dt>{{ field.label }}</dt><dd>{{ field.value }}</dd>
        </template>
      </dl>
      <p class="report-caveat">学习报告只反映本次教学线索，不作为掌握凭证。</p>
    </div>
  </section>
</template>
<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/shared/design/AppIcon.vue'
const props = defineProps({
  report: { type: Object, default: () => ({}) },
})
const expanded = ref(false)
const FIELDS = [
  ['goal', '本次目标'], ['understood', '已经理解'], ['stuck', '还需要练习'],
  ['next', '下一步建议'], ['evidence', '依据'],
]
const fields = computed(() => FIELDS
  .map(([key, label]) => ({ label, value: props.report?.[key] }))
  .filter(field => typeof field.value === 'string' && field.value.trim()))
const summaryText = computed(() => {
  const next = props.report?.next
  if (typeof next === 'string' && next.trim()) return `下一步：${next.trim()}`
  return fields.value.length ? '展开查看本次教学线索' : '本次回复没有附带可读报告'
})
</script>
<style scoped>
.teaching-report { border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); }
.report-toggle { display: flex; align-items: center; gap: var(--space-2); width: 100%; padding: var(--space-2); border: 0; background: transparent; color: var(--ink); text-align: left; cursor: pointer; }
.report-icon { display: grid; place-items: center; width: var(--space-5); height: var(--space-5); border-radius: var(--radius-control); background: var(--agent-soft); color: var(--agent-accent); }
.report-title { display: grid; flex: 1; min-width: 0; }
.report-title strong { font-weight: var(--weight-medium); }
.report-title small { color: var(--ink-secondary); font-size: var(--text-caption); overflow-wrap: anywhere; }
.report-body { padding: 0 var(--space-3) var(--space-3); }
.report-note { margin: 0 0 var(--space-2); color: var(--ink-secondary); }
.report-fields { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--space-1) var(--space-2); margin: 0; }
.report-fields dt { color: var(--ink-secondary); font-size: var(--text-caption); }
.report-fields dd { margin: 0; }
.report-caveat { margin: var(--space-2) 0 0; color: var(--ink-muted); font-size: var(--text-caption); }
</style>
