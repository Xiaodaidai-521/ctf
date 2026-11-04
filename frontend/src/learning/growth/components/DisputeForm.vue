<template>
  <section class="dispute-form" aria-labelledby="dispute-heading">
    <h4 id="dispute-heading">提出复核</h4>
    <p class="dispute-note">写清争议点与依据。处理争议不直接改分；需要改分须由教师建立更正版本。重复提交同一申请不会重复创建。</p>
    <form @submit.prevent="submit">
      <label class="field">
        <span class="field-label">复核依据</span>
        <textarea v-model="reason" rows="3" :disabled="saving" placeholder="例如：某项评分与提交材料不一致，依据是……" aria-label="复核依据"></textarea>
      </label>
      <p v-if="message" class="form-message" :class="{ 'is-error': isError }" role="status">{{ message }}</p>
      <div class="actions">
        <button type="button" class="btn" :disabled="saving" @click="cancel">取消</button>
        <button type="submit" class="btn btn-primary" :disabled="saving || !reason.trim()">{{ saving ? '提交中…' : '提交复核' }}</button>
      </div>
    </form>
  </section>
</template>
<script setup>
import { ref } from 'vue'
import api from '@/api'
import { disputeKey, disputePayload, disputeResult, errorText } from '../reviewActions.js'

const props = defineProps({
  submission: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved'])

const reason = ref('')
const saving = ref(false)
const message = ref('')
const isError = ref(false)
// 幂等字段在打开表单时固定：失败重试沿用同一标识，由后台去重。
const clientDisputeId = disputeKey(props.submission.id, `${Date.now()}`)

async function submit() {
  if (saving.value) return
  message.value = ''
  isError.value = false
  if (!reason.value.trim()) {
    message.value = '复核依据不能为空。'
    isError.value = true
    return
  }
  saving.value = true
  try {
    const payload = await api.skillReview.createDispute(props.submission.id, disputePayload(reason.value, clientDisputeId))
    const result = disputeResult(payload)
    message.value = result.message
    isError.value = false
    emit('saved', { ...result, submissionId: props.submission.id })
  } catch (err) {
    message.value = `复核未提交：${errorText(err)}`
    isError.value = true
    emit('saved', { failed: true, submissionId: props.submission.id, message: message.value })
  } finally {
    saving.value = false
  }
}

function cancel() {
  emit('close')
}
defineExpose({ submit, cancel, reason, message, isError, clientDisputeId })
</script>
<style scoped>
.dispute-form { display: grid; gap: var(--space-1); padding: var(--space-2); border-top: var(--stroke) solid var(--line); }
.dispute-form h4 { margin: 0; font-size: var(--text-card); }
.dispute-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.field { display: grid; gap: 2px; margin: var(--space-1) 0; font-size: var(--text-caption); }
.field-label { color: var(--ink); font-weight: var(--weight-strong); }
.field textarea { width: 100%; padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; resize: vertical; }
.field textarea:hover { border-color: var(--action); }
.form-message { margin: 0; color: var(--positive); font-size: var(--text-caption); }
.form-message.is-error { color: var(--negative); }
.actions { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: var(--space-1); }
.btn { display: inline-flex; align-items: center; min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn:disabled { border-color: var(--line); background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
.btn:focus-visible, .field textarea:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
