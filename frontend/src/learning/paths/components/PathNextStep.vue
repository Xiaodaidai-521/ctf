<template>
  <section v-if="step && step.joined" class="next-step" aria-labelledby="next-step-title">
    <header class="next-step-head">
      <div>
        <p class="eyebrow">下一步 · 已加入航线</p>
        <h2 id="next-step-title">{{ step.chapterTitle }}</h2>
      </div>
      <span v-if="step.percentLabel" class="progress-pill">已完成 {{ step.percentLabel }}</span>
    </header>
    <p class="path-name">{{ step.title }}<span v-if="step.countsLabel"> · {{ step.countsLabel }}</span></p>
    <p class="reason">{{ step.reason }}</p>
    <p class="note">{{ step.note }}</p>
    <div class="actions">
      <button v-if="step.canEnter" type="button" class="btn btn-primary" :disabled="pending" @click="$emit('confirm')">
        {{ pending ? '正在进入…' : step.confirmLabel }}
      </button>
      <router-link v-if="step.canEnter" :to="step.to" class="text-link">直接打开章节</router-link>
      <router-link v-else :to="step.pathTo" class="btn btn-secondary">查看航线全部章节</router-link>
      <button v-if="showAdjust" type="button" class="btn btn-secondary" :disabled="pending" @click="$emit('adjust')">
        和智航调整目标
      </button>
    </div>
  </section>
  <section v-else class="next-step next-step-empty">
    <p class="eyebrow">下一步</p>
    <p>还没有可继续的已加入航线；先选一条航线，从章节列表自行开始。</p>
    <router-link to="/learning-paths" class="text-link">浏览学习航线</router-link>
  </section>
</template>

<script setup>
defineProps({
  step: { type: Object, default: null },
  pending: { type: Boolean, default: false },
  showAdjust: { type: Boolean, default: false },
})
defineEmits(['confirm', 'adjust'])
</script>

<style scoped>
.next-step { display: grid; gap: var(--space-1); padding: var(--space-3); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-raised); }
.next-step-empty { color: var(--ink-secondary); font-size: var(--text-caption); }
.next-step-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.eyebrow { margin: 0; color: var(--agent-accent); font-size: var(--text-caption); font-weight: var(--weight-medium); }
h2 { margin: var(--space-1) 0 0; font-size: var(--text-section); line-height: var(--leading-tight); overflow-wrap: anywhere; }
.path-name { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.progress-pill { padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); color: var(--ink-secondary); font-size: var(--text-caption); white-space: nowrap; }
.reason { margin: var(--space-1) 0 0; color: var(--ink); font-size: var(--text-caption); line-height: 1.7; }
.note { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); line-height: 1.6; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1) var(--space-2); margin-top: var(--space-1); }
.btn { display: inline-flex; align-items: center; justify-content: center; min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn:hover:not(:disabled) { border-color: var(--action); color: var(--action); }
.btn-primary:hover:not(:disabled) { background: var(--action-hover); border-color: var(--action-hover); color: var(--on-action); }
.btn:disabled { background: var(--surface-muted); border-color: var(--line); color: var(--ink-muted); cursor: not-allowed; }
.btn:focus-visible, .text-link:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.text-link { color: var(--action); font-size: var(--text-caption); }
.text-link:hover { color: var(--action-hover); text-decoration: underline; }
.is-compact .next-step { padding: var(--space-2); }
.is-compact .next-step .actions { flex-direction: column; align-items: stretch; }
.is-compact .next-step .text-link { text-align: center; }
</style>
