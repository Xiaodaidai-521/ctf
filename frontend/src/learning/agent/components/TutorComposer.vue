<template>
  <form class="tutor-composer" :class="{ 'is-busy': busy }" @submit.prevent="submit">
    <label class="sr-only" :for="inputId">学习问题</label>
    <textarea
      ref="field"
      :id="inputId"
      v-model="text"
      :placeholder="placeholder"
      :disabled="disabled"
      rows="2"
      maxlength="2000"
      @compositionstart="composing = true"
      @compositionend="composing = false"
      @keydown="onKeydown"
    />
    <div class="composer-footer">
      <span class="composer-hint"><AppIcon name="bi-shield-check" /> {{ hint }}</span>
      <div class="composer-actions">
        <button v-if="busy" type="button" class="quiet-action" @click="$emit('stop')">停止等待</button>
        <button type="submit" class="send-action" :disabled="disabled || busy || !text.trim()">
          <span>{{ busy ? '正在组织讲解' : '发送' }}</span><AppIcon name="bi-chevron-right" />
        </button>
      </div>
    </div>
    <div v-if="quickActions.length" class="composer-quick" aria-label="教学快捷动作">
      <button v-for="action in quickActions" :key="action.value" type="button" :disabled="disabled || busy" @click="$emit('quick', action.value)">{{ action.label }}</button>
    </div>
    <p class="composer-keys">Ctrl / ⌘ + Enter 发送</p>
  </form>
</template>
<script setup>
import { nextTick, ref, watch } from 'vue'
import { accountScope } from '@/shared/state/accountScope.js'
import { uiSnapshot } from '@/shared/state/retention.js'
import AppIcon from '@/shared/design/AppIcon.vue'
const props = defineProps({
  draftKey: { type: String, default: 'general' },
  placeholder: { type: String, default: '说说目标或卡住的地方' },
  hint: { type: String, default: '先讲思路与分级提示，不代做答案' },
  busy: Boolean,
  disabled: Boolean,
  quickActions: { type: Array, default: () => [] },
})
const emit = defineEmits(['submit', 'stop', 'quick'])
const inputId = `tutor-input-${Math.random().toString(36).slice(2, 8)}`
const field = ref(null)
let retention = uiSnapshot(`composer:${props.draftKey}`)
const text = ref(retention.read()?.text || '')
const remember = () => retention.write({ text: text.value })
watch(text, remember, { flush: 'sync' })
watch(() => props.draftKey, () => {
  remember()
  retention = uiSnapshot(`composer:${props.draftKey}`)
  text.value = retention.read()?.text || ''
}, { flush: 'sync' })
watch(() => accountScope.value.epoch, () => { retention = uiSnapshot(`composer:${props.draftKey}`); text.value = '' }, { flush: 'sync' })
const composing = ref(false)
function submit() {
  const value = text.value.trim()
  if (!value || props.busy || props.disabled) return
  text.value = ''
  emit('submit', value)
  nextTick(() => field.value?.focus())
}
function onKeydown(event) {
  if (event.isComposing || composing.value) return
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault()
    submit()
  }
}
defineExpose({
  focus: () => field.value?.focus(),
  setText: value => { text.value = String(value || '') },
  getText: () => text.value,
  clear: () => { text.value = '' },
})
</script>
<style scoped>
.tutor-composer { display: grid; gap: var(--space-1); padding: var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); background: var(--surface); box-shadow: var(--shadow-raised); }
.tutor-composer:focus-within { border-color: var(--agent-accent); }
.tutor-composer textarea { width: 100%; resize: none; border: 0; background: transparent; color: var(--ink); font: inherit; line-height: var(--leading-body); padding: var(--space-1); }
.tutor-composer textarea:focus { outline: none; }
.tutor-composer textarea::placeholder { color: var(--ink-muted); }
.composer-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-2); }
.composer-hint { display: flex; align-items: center; gap: var(--space-1); color: var(--ink-secondary); font-size: var(--text-caption); }
.composer-actions { display: flex; align-items: center; gap: var(--space-1); }
.quiet-action { border: 0; background: transparent; color: var(--ink-secondary); padding: var(--space-1); cursor: pointer; font-size: var(--text-caption); }
.quiet-action:hover { color: var(--action); }
.send-action { display: flex; align-items: center; gap: var(--space-1); flex: none; min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: 0; border-radius: var(--radius-pill); background: var(--action); color: var(--on-action); cursor: pointer; white-space: nowrap; }
.send-action:disabled { opacity: .55; cursor: not-allowed; }
.composer-quick { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.composer-quick button { padding: 2px var(--space-1); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); background: transparent; color: var(--ink-secondary); font-size: var(--text-caption); cursor: pointer; }
.composer-quick button:hover:not(:disabled) { color: var(--agent-accent); border-color: var(--agent-accent); }
.composer-quick button:disabled { opacity: .5; cursor: not-allowed; }
.composer-keys { margin: 0; color: var(--ink-muted); font-size: var(--text-caption); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.is-compact .composer-hint { display: none; }
</style>
