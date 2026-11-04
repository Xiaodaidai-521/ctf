<template>
  <div class="history-records">
    <p v-if="loading" role="status">正在读取学习历史…</p>
    <div v-else-if="error" class="history-error" role="alert">
      <p>{{ error }}</p>
      <button type="button" @click="$emit('retry')">重试</button>
    </div>
    <p v-else-if="!rows.length">暂无能力状态变化记录。</p>
    <template v-else>
      <table>
        <caption class="sr-only">{{ caption }}，含时间、能力、前后状态与原因</caption>
        <thead><tr><th scope="col">时间</th><th scope="col">能力</th><th scope="col">状态变化</th><th scope="col">原因</th></tr></thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="index">
            <td data-label="时间">{{ row.timeLabel }}</td>
            <td data-label="能力">{{ row.title }}</td>
            <td data-label="状态变化">{{ row.from }} → <strong>{{ row.to }}</strong></td>
            <td data-label="原因">{{ row.reason }}</td>
          </tr>
        </tbody>
      </table>
      <p class="history-note">共 {{ rows.length }} 条记录。提示后通过、待复测与环境影响会分开记录，不会抹掉之前的学习过程。</p>
    </template>
  </div>
</template>
<script setup>
defineProps({
  rows: { type: Array, default: () => [] },
  loading: Boolean,
  error: { type: String, default: '' },
  caption: { type: String, default: '能力状态变化记录' },
})
defineEmits(['retry'])
</script>
<style scoped>
.history-records { color: var(--ink-secondary); }
table { width: 100%; border-collapse: collapse; background: var(--surface); }
th, td { padding: var(--space-1) var(--space-2); border-bottom: var(--stroke) solid var(--line); text-align: left; vertical-align: top; font-size: var(--text-caption); overflow-wrap: anywhere; }
th { background: var(--surface-muted); color: var(--ink); }
.history-note { font-size: var(--text-caption); color: var(--ink-muted); }
.history-error { color: var(--negative); }
button { min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
button:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@media (max-width: 768px) {
  table, tbody, tr, td { display: block; width: 100%; box-sizing: border-box; }
  thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  tr { padding-block: var(--space-1); border-bottom: var(--stroke) solid var(--line); }
  td { border: 0; }
  td::before { content: attr(data-label) "："; color: var(--ink-muted); }
}
</style>
