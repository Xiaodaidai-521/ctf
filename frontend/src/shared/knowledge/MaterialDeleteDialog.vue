<template>
  <ContentDialog title="删除材料" :busy="state.busy" @close="$emit('close')">
    <p>确定删除「{{ state.target.title }}」吗？删除后将不再提供这份材料，已有版本与审阅记录会保留。</p>
    <p>如果这份材料用于课程任务，请先与课程负责人核对影响。</p>
    <label class="delete-reason">删除理由<textarea v-model="state.reason" rows="3" maxlength="500" :disabled="state.busy || state.uncertain" autocomplete="off" /></label>
    <p v-if="state.error" class="delete-error" role="alert">{{ state.error }}</p>
    <template #footer>
      <button class="content-button" :disabled="state.busy || state.uncertain" @click="$emit('close')">取消</button>
      <button v-if="state.uncertain" class="content-button" @click="$emit('reload')">重新加载列表核对</button>
      <button v-else class="content-button danger" :disabled="state.busy || !state.reason.trim()" @click="$emit('confirm')">{{ state.busy ? '正在删除…' : '确认删除' }}</button>
    </template>
  </ContentDialog>
</template>
<script setup>
import ContentDialog from '../content/ContentDialog.vue'
defineProps({ state: { type: Object, required: true } })
defineEmits(['close', 'confirm', 'reload'])
</script>
<style scoped src="../content/content.css"></style>
<style scoped>
.delete-reason { display: grid; gap: var(--space-1); margin-top: var(--space-2); }
textarea { font: inherit; color: var(--ink); background: var(--surface); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); padding: var(--space-1); width: 100%; box-sizing: border-box; resize: vertical; }
textarea:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.delete-error { color: var(--negative); }
</style>
