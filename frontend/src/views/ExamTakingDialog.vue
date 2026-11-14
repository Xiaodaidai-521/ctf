<template>
  <dialog ref="dialog" class="exam-dialog" :aria-labelledby="titleId" aria-modal="true" @cancel.prevent="emit('close')" @click.self="emit('close')">
    <div class="dialog-content">
      <h2 :id="titleId" class="dialog-title">{{ title }}</h2>
      <div class="dialog-body"><slot /></div>
      <div class="dialog-footer"><slot name="footer" /></div>
    </div>
  </dialog>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

// 只负责呈现；原生模态层管理焦点约束、Escape 和关闭后的焦点归还。
const props = defineProps({ open: Boolean, title: String, titleId: String })
const emit = defineEmits(['close'])
const dialog = ref(null)
const syncDialog = () => {
  if (!dialog.value) return
  if (props.open && !dialog.value.open) dialog.value.showModal()
  else if (!props.open && dialog.value.open) dialog.value.close()
}
watch(() => props.open, syncDialog, { flush: 'post' })
onMounted(syncDialog)
onBeforeUnmount(() => dialog.value?.close())
</script>

<style scoped>
.exam-dialog { width: min(var(--message-width), calc(100% - var(--space-2) * 2)); max-width: none; max-height: calc(100dvh - var(--space-2) * 2); padding: 0; border: 0; border-radius: var(--radius-panel); background: var(--surface); color: var(--ink); box-shadow: var(--shadow-overlay); overflow: auto; font-size: var(--text-body); line-height: var(--leading-body); }
.exam-dialog::backdrop { background: var(--overlay); }
.dialog-content { padding: var(--space-3); }
.dialog-title { margin: 0 0 var(--space-3); font-size: var(--text-section); line-height: var(--leading-tight); font-weight: var(--weight-strong); }
.dialog-body { overflow-wrap: anywhere; }
.dialog-footer { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-3); }
/* 与应用共享的 compact 状态一致，模态层仍保留在本页 DOM 内。 */
:global(.is-compact) .dialog-content { padding: var(--space-2); }
:global(.is-compact) .dialog-footer { display: grid; grid-template-columns: minmax(0, 1fr); }
</style>
