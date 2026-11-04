<template>
  <section ref="stream" data-retain-scroll class="conversation-stream" aria-label="导学对话" aria-live="polite">
    <div v-if="!messages.length && !restoring" class="stream-empty">
      <span class="empty-mark" aria-hidden="true"><AppIcon name="bi-cpu" /></span>
      <p>说说目标或卡住的地方，先讲思路，再一起练习。</p>
      <p class="empty-note">不代做答案，也不给未获许可的 Flag。</p>
    </div>
    <p v-else-if="restoring" class="stream-restoring"><AppIcon name="bi-arrow-repeat" />正在读取上次的学习对话…</p>
    <AgentMessage v-for="message in messages" :key="message.id" :message="message">
      <template #footer>
        <TeachingReportMessage v-if="message.kind === 'report' || message.report" :report="message.report || {}" />
      </template>
    </AgentMessage>
    <slot name="tail" />
  </section>
</template>
<script setup>
import { nextTick, onActivated, onDeactivated, ref, watch } from 'vue'
import AppIcon from '@/shared/design/AppIcon.vue'
import AgentMessage from './AgentMessage.vue'
import TeachingReportMessage from './TeachingReportMessage.vue'
const props = defineProps({
  messages: { type: Array, default: () => [] },
  restoring: Boolean,
})
const stream = ref(null)
let active = true
onActivated(() => { active = true })
onDeactivated(() => { active = false })
function scrollToBottom() {
  nextTick(() => {
    const el = stream.value
    if (!active || !el) return
    // 抽屉里对话流本身不滚动，改由外层容器滚到底。
    if (el.scrollHeight > el.clientHeight) el.scrollTop = el.scrollHeight
    const parent = el.parentElement
    if (parent && parent.scrollHeight > parent.clientHeight) parent.scrollTop = parent.scrollHeight
  })
}
watch(() => props.messages.length, (now, before) => { if (now !== before) scrollToBottom() })
defineExpose({ scrollToBottom })
</script>
<style scoped>
.conversation-stream { display: grid; align-content: start; gap: var(--space-3); min-height: 0; overflow-y: auto; padding: var(--space-2) 0; scrollbar-gutter: stable; }
.stream-empty { display: grid; justify-items: center; gap: var(--space-1); padding: var(--space-8) var(--space-3); text-align: center; color: var(--ink-secondary); }
.empty-mark { display: grid; place-items: center; width: var(--space-8); height: var(--space-8); border-radius: 50%; background: var(--agent-soft); color: var(--agent-accent); font-size: var(--text-page); }
.stream-empty p { margin: 0; color: var(--ink); }
.empty-note { color: var(--ink-muted); font-size: var(--text-caption); }
.stream-restoring { display: flex; align-items: center; gap: var(--space-1); color: var(--ink-secondary); font-size: var(--text-caption); }
</style>
