<template>
  <div class="task-list">
    <p class="relation-note">按你目前的练习记录排序。</p>

    <p v-if="loading" class="state-note" role="status">正在读取推荐…</p>
    <p v-else-if="error" class="state-note is-error" role="alert">
      {{ error }}
      <button type="button" class="text-action" @click="$emit('retry')">重试</button>
    </p>
    <p v-else-if="!items.length" class="state-note">
      该主线暂无可用的任务推荐；可切换上方主线筛选，或先完成一次基础诊断。
    </p>

    <ul v-else class="items">
      <li v-for="item in items" :key="item.kind === 'task' ? `task-${item.task.id}` : `diagnosis-${item.trackLabel}-${item.priority}`" class="item">
        <div class="item-main">
          <div class="item-head">
            <span class="category">{{ item.categoryLabel }}</span>
            <span class="relation">本主线推荐</span>
            <span v-if="item.trackLabel" class="track">{{ item.trackLabel }}</span>
          </div>
          <strong class="item-title">{{ item.task ? item.task.title : `${item.trackLabel}基础诊断` }}</strong>
          <p v-if="item.reason" class="reason">{{ item.reason }}</p>
          <p class="item-meta">
            <template v-if="item.task">
              <span v-if="item.task.versionLabel">版本 {{ item.task.versionLabel }}</span>
              <span v-if="item.task.purposeLabel">用途 {{ item.task.purposeLabel }}</span>
            </template>
            <span v-else>诊断</span>
          </p>
        </div>
        <button
          v-if="item.kind === 'diagnosis'"
          type="button"
          class="btn btn-primary"
          @click="$emit('diagnose', item.diagnosisTrack)"
        >开始诊断</button>
        <button
          v-else
          type="button"
          class="btn btn-primary"
          :disabled="claimingId === item.task.id"
          @click="$emit('claim', item)"
        >{{ claimingId === item.task.id ? '领取中…' : '领取任务' }}</button>
      </li>
    </ul>

    <p v-if="claimMessage" class="claim-message" :class="{ 'is-error': claimError }" role="status">{{ claimMessage }}</p>
    <p v-if="claimDetail" class="claim-detail">{{ claimDetail }}</p>
  </div>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  claimingId: { type: [Number, String], default: null },
  claimMessage: { type: String, default: '' },
  claimDetail: { type: String, default: '' },
  claimError: { type: Boolean, default: false },
})
defineEmits(['claim', 'diagnose', 'retry'])
</script>

<style scoped>
.task-list { display: grid; gap: var(--space-1); }
.relation-note { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); line-height: 1.6; }
.state-note { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.state-note.is-error { background: var(--negative-soft); color: var(--negative); }
.text-action { margin-left: var(--space-1); padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.items { display: grid; gap: var(--space-1); margin: 0; padding: 0; list-style: none; }
.item { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--space-1) var(--space-2); padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); }
.item-main { display: grid; gap: calc(var(--space-1) / 2); min-width: 0; }
.item-head { display: flex; flex-wrap: wrap; gap: var(--space-1); align-items: center; color: var(--ink-muted); font-size: var(--text-caption); }
.category { color: var(--action); font-weight: var(--weight-strong); }
.relation { padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); }
.item-title { font-size: var(--text-caption); overflow-wrap: anywhere; }
.reason { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); line-height: 1.6; }
.item-meta { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-2); margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.claim-message { margin: 0; color: var(--positive); font-size: var(--text-caption); }
.claim-message.is-error { color: var(--negative); }
.claim-detail { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); line-height: 1.6; }
.btn { display: inline-flex; align-items: center; min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn:disabled { border-color: var(--line); background: var(--surface-muted); color: var(--ink-muted); cursor: not-allowed; }
.btn:focus-visible, .text-action:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
@media (max-width: 480px) {
  .item { flex-direction: column; }
}
</style>
