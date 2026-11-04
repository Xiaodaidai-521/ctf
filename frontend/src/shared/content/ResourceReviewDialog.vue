<template>
  <ContentDialog title="审核备注" :busy="busy" @close="$emit('close')">
    <form id="resource-review-form" class="content-form single-column" @submit.prevent="$emit('confirm')"><p>{{ resource.title }}</p><label>{{ action === 'approved' ? '审核意见（可选）' : '拒绝原因（必填）' }}<textarea :value="note" :required="action === 'rejected'" :disabled="busy" rows="4" @input="$emit('update:note', $event.target.value)"></textarea></label><p v-if="error" class="content-error" role="alert">{{ error }}</p></form>
    <template #footer><button class="content-button" :disabled="busy" @click="$emit('close')">取消</button><button class="content-button primary" form="resource-review-form" type="submit" :disabled="busy">{{ busy ? '审核中…' : '确认' }}</button></template>
  </ContentDialog>
</template>
<script setup>
import ContentDialog from './ContentDialog.vue'
defineProps({ role: { type: String, required: true }, resource: { type: Object, required: true }, action: { type: String, required: true }, note: String, busy: Boolean, error: String })
defineEmits(['close', 'confirm', 'update:note'])
</script>
<style scoped src="./content.css"></style>
