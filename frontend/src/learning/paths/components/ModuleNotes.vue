<template>
  <section class="module-notes" aria-labelledby="module-notes-title">
    <header class="notes-head">
      <h2 id="module-notes-title">我的笔记</h2>
      <span class="status" :class="{ dirty: status.dirty }">{{ status.statusLabel }}</span>
    </header>
    <textarea
      :value="modelValue"
      aria-labelledby="module-notes-title"
      placeholder="记录你的理解与待验证的问题…"
      rows="5"
      class="notes-input"
      @input="$emit('update:modelValue', $event.target.value)"
    ></textarea>
    <p class="note">{{ status.note }}</p>
    <div class="notes-actions">
      <button type="button" class="btn" @click="$emit('save-local')">保存到本机</button>
      <button type="button" class="btn" :disabled="status.empty" @click="$emit('copy')">复制笔记</button>
      <button type="button" class="btn" :disabled="status.empty" @click="$emit('download')">下载为文件</button>
      <span class="length">{{ status.lengthLabel }}</span>
    </div>
  </section>
</template>

<script setup>
defineProps({
  modelValue: { type: String, default: '' },
  status: { type: Object, required: true },
})
defineEmits(['update:modelValue', 'save-local', 'copy', 'download'])
</script>

<style scoped>
.module-notes { display: grid; gap: var(--space-1); min-width: 0; padding: var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); }
.notes-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-1); }
h2 { margin: 0; font-size: var(--text-card); }
.status { padding: 0 var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); color: var(--ink-muted); font-size: var(--text-caption); }
.status.dirty { border-color: var(--warning); color: var(--warning); }
.notes-input { width: 100%; box-sizing: border-box; padding: var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; line-height: var(--leading-body); resize: vertical; }
.notes-input:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.note { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); line-height: 1.6; }
.notes-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1) var(--space-2); }
.btn { display: inline-flex; align-items: center; justify-content: center; min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn:hover:not(:disabled) { border-color: var(--action); color: var(--action); }
.btn:active:not(:disabled) { background: var(--surface-muted); }
.btn:disabled { border-color: var(--line); background: var(--surface-muted); color: var(--ink-muted); cursor: not-allowed; }
.btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.length { color: var(--ink-muted); font-size: var(--text-caption); }
.is-compact .module-notes .notes-actions { align-items: stretch; }
.is-compact .module-notes .btn { flex: 1; }
</style>
