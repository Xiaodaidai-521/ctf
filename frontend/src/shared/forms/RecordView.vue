<template>
  <div class="record-view">
    <p v-if="!rows.length" class="fb-muted">暂无记录。</p>
    <dl v-else>
      <template v-for="(row, index) in rows" :key="index">
        <dt>{{ row.label }}</dt><dd>{{ row.value }}</dd>
      </template>
    </dl>
    <button class="fb-btn" type="button" @click="downloadRecord(value, `${title}.json`)">下载{{ title }}完整记录</button>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { recordRows } from './recordPresentation.js'
import { downloadRecord } from './referenceFile.js'
const props = defineProps({ value: { default: null }, title: { type: String, default: '核查资料' } })
const rows = computed(() => recordRows(props.value))
</script>

<style scoped>
.record-view { color: var(--ink); font-size: var(--text-caption); line-height: var(--leading-body); }
.fb-muted { color: var(--ink-secondary); }
.record-view dl { display: grid; grid-template-columns: minmax(var(--space-10), var(--row-label-width)) minmax(0, 1fr); gap: var(--space-1) var(--space-2); margin: 0 0 var(--space-2); }
.record-view dt { color: var(--ink-secondary); font-weight: var(--weight-medium); overflow-wrap: anywhere; }
.record-view dd { min-width: 0; margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.fb-btn { min-height: var(--control-height); max-width: 100%; padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.fb-btn:hover { background: var(--surface-hover); }
@media (max-width: 768px) { .record-view dl { grid-template-columns: minmax(0, 1fr); } }
</style>
