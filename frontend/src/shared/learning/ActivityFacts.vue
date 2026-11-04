<template>
  <div class="activity-facts">
    <dl v-if="showFacts" class="period-facts">
      <div><dt>统计窗口</dt><dd>{{ effect.periodLabel || `近 ${effect.days} 天` }}</dd></div>
      <div><dt>快照状态</dt><dd>{{ effect.hasSnapshot ? `已生成${effect.snapshotAt ? ` · ${formatTime(effect.snapshotAt)}` : ''}` : '暂无快照' }}</dd></div>
      <div><dt>日数据</dt><dd>{{ effect.hasDaily ? `${effect.dailyStats.length} 天` : '暂无按日数据' }}</dd></div>
    </dl>
    <div v-if="showTable && effect.hasDaily" class="table-scroll">
      <table><caption>每日学习分钟（秒已显式换算）</caption>
        <thead><tr><th scope="col">日期</th><th scope="col">分钟</th><th scope="col">原始秒数</th></tr></thead>
        <tbody><tr v-for="(item, index) in effect.dailyStats" :key="`${item.date}-${index}`"><th scope="row">{{ item.date }}</th><td>{{ item.minutes === null ? '—' : item.minutes }}</td><td>{{ item.rawSeconds === null ? '—' : item.rawSeconds }}</td></tr></tbody>
      </table>
    </div>
  </div>
</template>
<script setup>
defineProps({ effect: { type: Object, required: true }, showTable: { type: Boolean, default: true }, showFacts: { type: Boolean, default: true } })
const formatTime = value => {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>
<style scoped>
.period-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-1); margin: 0; }
.period-facts div { padding: var(--space-1); background: var(--surface); }
dt, caption { color: var(--ink-secondary); font-size: var(--text-caption); }
dd { margin: var(--stroke) 0 0; font-size: var(--text-caption); overflow-wrap: anywhere; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: var(--text-caption); text-align: left; font-variant-numeric: tabular-nums; }
caption { padding: var(--space-1) 0; text-align: left; }
th, td { padding: var(--space-1); border-bottom: var(--stroke) solid var(--line); }
@media (max-width: 640px) { .period-facts { grid-template-columns: minmax(0, 1fr); } }
</style>
