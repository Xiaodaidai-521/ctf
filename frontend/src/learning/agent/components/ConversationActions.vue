<template>
  <div class="conversation-actions">
    <a-dropdown trigger="click" position="top">
      <button type="button" class="quiet-action" :disabled="disabled">记录<AppIcon name="bi-chevron-up" /></button>
      <template #content>
        <a-doption value="export" :disabled="!messages.length" @click="$emit('export')">导出协作记录</a-doption>
        <a-doption value="restart" @click="$emit('restart')">重新开始</a-doption>
        <a-doption value="delete" :disabled="!conversationId" @click="confirmOpen = true">删除这段历史</a-doption>
      </template>
    </a-dropdown>
    <a-modal v-model:visible="confirmOpen" title="删除这段协作历史？" :width="420" @ok="confirmDelete">
      <p>删除后这段对话将从你的历史记录中移除，本页也无法再回看。</p>
      <p class="modal-note">只影响你本人的这段记录，不会影响学习任务或练习成绩。</p>
    </a-modal>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import AppIcon from '@/shared/design/AppIcon.vue'
const props = defineProps({ messages: { type: Array, default: () => [] }, conversationId: { type: [Number, String], default: null }, disabled: Boolean })
const emit = defineEmits(['export', 'restart', 'delete'])
const confirmOpen = ref(false)
function confirmDelete() {
  confirmOpen.value = false
  emit('delete')
}
</script>
<style scoped>
.quiet-action { display: flex; align-items: center; gap: 2px; flex: none; white-space: nowrap; padding: var(--space-1); border: 0; background: transparent; color: var(--ink-secondary); cursor: pointer; font-size: var(--text-caption); }
.quiet-action:hover:not(:disabled) { color: var(--ink); }
.quiet-action:disabled { opacity: .5; cursor: not-allowed; }
.modal-note { color: var(--ink-secondary); font-size: var(--text-caption); }
</style>
