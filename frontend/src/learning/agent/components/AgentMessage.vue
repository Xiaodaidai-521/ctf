<template>
  <article class="agent-message" :class="[message.role === 'user' ? 'is-student' : 'is-agent', `tone-${tone}`]" :aria-label="`${speaker}的消息`">
    <header class="message-meta">
      <span class="speaker-avatar" aria-hidden="true"><AppIcon :name="message.role === 'user' ? 'bi-person' : 'bi-cpu'" /></span>
      <span class="speaker-name">{{ speaker }}</span>
      <time v-if="message.createdAt" class="message-time">{{ formattedTime }}</time>
    </header>
    <div v-if="message.kind === 'status'" class="status-line"><AppIcon name="bi-arrow-repeat" />{{ message.summary || '正在协作处理' }}</div>
    <div v-else class="message-body" v-html="html"></div>
    <slot name="footer" />
  </article>
</template>
<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import AppIcon from '@/shared/design/AppIcon.vue'
import { sanitizeHtml } from '@/utils/sanitize.js'
import { speakerLabel, statusLine } from '../presentation.js'
const props = defineProps({ message: { type: Object, required: true } })
const speaker = computed(() => speakerLabel(props.message))
const tone = computed(() => (props.message.role === 'user' ? 'neutral' : 'agent'))
const html = computed(() => {
  if (props.message.kind === 'status') return ''
  const content = typeof props.message.content === 'string' ? props.message.content : ''
  return content ? sanitizeHtml(marked.parse(content)) : ''
})
const formattedTime = computed(() => {
  const time = Date.parse(props.message.createdAt)
  return Number.isFinite(time) ? new Date(time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''
})
defineExpose({ statusText: () => statusLine(props.message) })
</script>
<style scoped>
.agent-message { display: grid; gap: var(--space-1); max-width: 100%; }
.message-meta { display: flex; align-items: center; gap: var(--space-1); color: var(--ink-secondary); font-size: var(--text-caption); }
.speaker-avatar { display: grid; place-items: center; width: var(--space-4); height: var(--space-4); border-radius: 50%; background: var(--agent-soft); color: var(--agent-accent); }
.is-student .speaker-avatar { background: var(--surface-muted); color: var(--ink-secondary); }
.speaker-name { color: var(--ink); font-weight: var(--weight-medium); }
.message-body { padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); background: var(--surface); border: var(--stroke) solid var(--line); line-height: var(--leading-body); overflow-wrap: anywhere; }
.is-student { justify-items: end; }
.is-student .message-meta { flex-direction: row-reverse; }
.is-student .message-body { background: var(--agent-soft); border-color: transparent; }
.message-body :deep(p) { margin: 0 0 var(--space-2); }
.message-body :deep(p:last-child) { margin-bottom: 0; }
.message-body :deep(pre) { overflow-x: auto; padding: var(--space-2); border-radius: var(--radius-control); background: var(--ink); color: var(--on-action); }
.message-body :deep(code) { font-size: var(--text-caption); }
.message-body :deep(img) { max-width: 100%; height: auto; border-radius: var(--radius-control); }
.status-line { display: inline-flex; align-items: center; gap: var(--space-1); padding: var(--space-1) var(--space-2); border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
</style>
