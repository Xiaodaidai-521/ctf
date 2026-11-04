<template>
  <div class="fb-slot">
    <p class="fb-muted">{{ title }}：尚无完整可选名单，可按格式模板填写后导入；提交时仍会核验访问权限。</p>
    <div class="fb-actions">
      <button class="fb-btn" type="button" @click="download">下载{{ title }}模板</button>
      <label class="fb-btn">导入{{ title }}
        <input type="file" accept=".json,application/json" :aria-label="`导入${title}`" @change="importFile" />
      </label>
      <button class="fb-btn" type="button" @click="clear">清除{{ title }}</button>
    </div>
    <ul>
      <li v-for="field in fields" :key="field.key">{{ field.label }}：{{ hasValue(field) ? '已填写' : '未填写' }}</li>
    </ul>
    <p v-if="error" class="fb-error" role="alert">{{ error }}</p>
    <p v-else-if="message" class="fb-success" role="status">{{ message }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { downloadRecord, parseReferenceFile } from './referenceFile.js'

const props = defineProps({
  title: { type: String, default: '关联资料' },
  fields: { type: Array, required: true },
  modelValue: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue'])
const error = ref('')
const message = ref('')
const empty = () => Object.fromEntries(props.fields.map(field => [field.key, field.type === 'list' ? [] : '']))
const hasValue = field => field.type === 'list' ? Boolean(props.modelValue[field.key]?.length) : Boolean(props.modelValue[field.key])
function download() { downloadRecord({ ...empty(), ...props.modelValue }, `${props.title}模板.json`) }
function clear() {
  emit('update:modelValue', empty())
  error.value = ''
  message.value = '已清除关联资料。'
}
async function importFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  error.value = ''
  message.value = ''
  try {
    if (file.size > 1024 * 1024) throw new Error('文件过大，请使用下载的格式模板。')
    let text
    try { text = await file.text() } catch { throw new Error('文件未能读取，请重试。') }
    emit('update:modelValue', parseReferenceFile(text, props.fields))
    message.value = '资料已导入；请核对其他内容后再提交。'
  } catch (err) { error.value = err.message || '文件未能读取，请重试。' }
}
</script>

<style scoped>
.fb-slot { padding: var(--space-2); background: var(--surface-muted); border: var(--stroke) solid var(--line); border-radius: var(--radius-control); color: var(--ink); font-size: var(--text-caption); }
.fb-muted { margin: 0 0 var(--space-2); color: var(--ink-secondary); line-height: var(--leading-body); }
.fb-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); }
.fb-btn { display: inline-flex; align-items: center; flex-wrap: wrap; gap: var(--space-1); min-height: var(--control-height); max-width: 100%; padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; cursor: pointer; }
.fb-btn:hover { background: var(--surface-hover); }
.fb-btn input { max-width: 100%; min-width: 0; color: var(--ink); font: inherit; }
.fb-slot ul { margin: var(--space-2) 0 0; padding-left: var(--space-3); line-height: var(--leading-body); }
.fb-error, .fb-success { margin: var(--space-2) 0 0; padding: var(--space-1); border-radius: var(--radius-control); line-height: var(--leading-body); }
.fb-error { color: var(--negative); background: var(--negative-soft); }
.fb-success { color: var(--positive); background: var(--positive-soft); }
</style>
