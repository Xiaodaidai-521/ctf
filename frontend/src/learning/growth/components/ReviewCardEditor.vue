<template>
  <section class="card-editor" aria-labelledby="card-editor-heading">
    <header class="editor-head">
      <div>
        <h4 id="card-editor-heading">复盘卡</h4>
        <p class="editor-note">六字段都来自本人填写；完成复盘后后台会按规则安排复测。已完成的复盘卡只读，不能改写。</p>
      </div>
      <span v-if="draft" class="status-chip" :class="{ 'is-completed': draft.readOnly }">{{ draft.statusLabel }}</span>
    </header>

    <p v-if="loading" class="state-note" role="status">正在读取已有复盘卡…</p>
    <p v-else-if="loadError" class="state-note is-error" role="alert">{{ loadError }}<button type="button" class="text-action" @click="loadCard">重试</button></p>

    <template v-else-if="draft">
      <p v-if="draft.readOnly" class="state-note is-readonly">
        该复盘卡已于 {{ completedLabel }} 完成，内容只读。需要重新学习请创建新的任务尝试。
      </p>
      <p v-if="draft.teacherConfirmation" class="teacher-note">教师确认：{{ draft.teacherConfirmation }}</p>

      <form class="editor-form" @submit.prevent="save(true)">
        <label v-for="field in fields" :key="field.key" class="field">
          <span class="field-label">{{ field.label }}<em v-if="required.includes(field.key) && !draft.readOnly" class="required-mark" aria-hidden="true">*</em></span>
          <span class="field-hint">{{ field.hint }}</span>
          <textarea
            v-model="values[field.key]"
            rows="2"
            :readonly="draft.readOnly"
            :disabled="saving !== ''"
            :aria-label="field.label"
          ></textarea>
        </label>

        <p v-if="formMessage" class="form-message" :class="{ 'is-error': formError }" role="status">{{ formMessage }}</p>

        <div v-if="!draft.readOnly" class="editor-actions">
          <button type="button" class="btn" :disabled="saving !== ''" @click="cancel">取消</button>
          <button type="button" class="btn" :disabled="saving !== ''" @click="save(false)">{{ saving === 'draft' ? '保存中…' : '保存草稿' }}</button>
          <button type="submit" class="btn btn-primary" :disabled="saving !== ''">{{ saving === 'complete' ? '提交中…' : '完成复盘并安排复测' }}</button>
        </div>
        <div v-else class="editor-actions">
          <button type="button" class="btn" @click="cancel">关闭</button>
        </div>
      </form>
    </template>
  </section>
</template>
<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import api from '@/api'
import { CARD_FIELDS, CARD_REQUIRED, cardDraft, cardMissing, cardPayload, cardResult, errorText, formatDateTime } from '../reviewActions.js'

const props = defineProps({
  submission: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved'])

const fields = CARD_FIELDS
const required = CARD_REQUIRED
const loading = ref(true)
const loadError = ref('')
const draft = ref(null)
const values = reactive({})
const saving = ref('')
const formMessage = ref('')
const formError = ref(false)
const completedLabel = computed(() => formatDateTime(draft.value?.completedAt))

function applyDraft(card) {
  const next = cardDraft(props.submission, card)
  draft.value = next
  for (const field of CARD_FIELDS) values[field.key] = next.values[field.key]
}

// 打开编辑先读已有复盘卡，恢复草稿；读取失败时不拿空表单覆盖后台内容。
async function loadCard() {
  loading.value = true
  loadError.value = ''
  try {
    const payload = await api.skillReview.reviewCard(props.submission.id)
    applyDraft(payload?.review_card || null)
  } catch (err) {
    draft.value = null
    loadError.value = `已有复盘卡暂时未能读取：${errorText(err)}`
  } finally {
    loading.value = false
  }
}

function cancel() {
  // 取消不写任何内容：直接关闭，后台复盘卡保持原样。
  emit('close')
}

async function save(complete) {
  if (saving.value || draft.value?.readOnly) return
  formMessage.value = ''
  formError.value = false
  if (complete) {
    const missing = cardMissing(values)
    if (missing.length) {
      formMessage.value = `完成复盘前请补齐：${missing.join('、')}。内容已保留，可先保存草稿。`
      formError.value = true
      return
    }
  }
  saving.value = complete ? 'complete' : 'draft'
  try {
    const payload = await api.skillReview.saveReviewCard(props.submission.id, cardPayload(values, complete))
    const result = cardResult(payload, complete)
    if (payload?.review_card) applyDraft(payload.review_card)
    formMessage.value = result.message
    formError.value = false
    emit('saved', { complete, ...result })
  } catch (err) {
    // 失败保留输入，不自行补完成时间或创建复测结果。
    formMessage.value = `保存未完成：${errorText(err)}`
    formError.value = true
    emit('saved', { complete, failed: true, message: formMessage.value })
  } finally {
    saving.value = ''
  }
}

watch(() => props.submission?.id, () => { loadCard() })
onMounted(loadCard)
defineExpose({ loadCard, save, cancel, draft, values, loading, loadError, formMessage })
</script>
<style scoped>
.card-editor { display: grid; gap: var(--space-2); padding: var(--space-2); border-top: var(--stroke) solid var(--line); }
.editor-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--space-1) var(--space-2); }
.editor-head h4 { margin: 0 0 var(--space-1); font-size: var(--text-card); }
.editor-note { margin: 0; max-width: var(--reading-width); color: var(--ink-secondary); font-size: var(--text-caption); }
.status-chip { padding: 0 var(--space-1); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.status-chip.is-completed { background: var(--positive-soft); color: var(--positive); }
.state-note { margin: 0; padding: var(--space-2); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); }
.state-note.is-error { background: var(--negative-soft); color: var(--negative); }
.state-note.is-readonly { background: var(--action-soft); color: var(--action); }
.text-action { margin-left: var(--space-1); padding: 0; border: 0; background: transparent; color: var(--action); font: inherit; cursor: pointer; }
.teacher-note { margin: 0; color: var(--ink-secondary); font-size: var(--text-caption); }
.editor-form { display: grid; gap: var(--space-2); }
.field { display: grid; gap: 2px; font-size: var(--text-caption); color: var(--ink-secondary); }
.field-label { font-weight: var(--weight-strong); color: var(--ink); }
.required-mark { margin-left: 2px; color: var(--negative); font-style: normal; }
.field-hint { color: var(--ink-muted); }
.field textarea { width: 100%; min-height: calc(var(--control-height) * 1.6); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; resize: vertical; }
.field textarea[readonly] { background: var(--surface-muted); }
.field textarea:hover:not([readonly]) { border-color: var(--action); }
.form-message { margin: 0; color: var(--positive); font-size: var(--text-caption); }
.form-message.is-error { color: var(--negative); }
.editor-actions { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.btn { display: inline-flex; align-items: center; min-height: var(--control-height); padding: 0 var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-size: var(--text-caption); cursor: pointer; }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn:disabled { border-color: var(--line); background: var(--disabled); color: var(--disabled-ink); cursor: not-allowed; }
.btn:focus-visible, .text-action:focus-visible, .field textarea:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
</style>
