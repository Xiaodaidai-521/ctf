<template>
  <div class="challenge-modal" @click.self="handleClose">
    <div class="modal-overlay" @click.self="handleClose">
      <div
        ref="container"
        class="modal-container"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        @keydown.esc.stop="handleClose"
      >
        <div class="modal-toolbar">
          <span>题目详情</span>
          <button ref="closeButton" class="close-btn" @click="handleClose" aria-label="关闭题目详情">
            <AppIcon name="bi-x-lg" aria-hidden="true" />
          </button>
        </div>
        <div class="modal-content">
          <ChallengeWorkspace :challenge-id="challengeId" mode="modal" @close="handleClose" @solved="handleSolved" @loaded="handleLoaded" />
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import AppIcon from '@/shared/design/AppIcon.vue'
import ChallengeWorkspace from '@/learning/practice/ChallengeWorkspace.vue'

const props = defineProps({
  challengeId: { type: Number, required: true },
})
const emit = defineEmits(['close', 'solved'])

const container = ref(null)
const closeButton = ref(null)
const title = ref('题目详情')
let previousFocus = null

// 打开时把焦点移入弹层，关闭后回到唤起点，保留原键盘行为。
function trapFocus(event) {
  if (event.key !== 'Tab' || !container.value) return
  const focusable = container.value.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])')
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}

onMounted(async () => {
  previousFocus = document.activeElement
  document.addEventListener('keydown', trapFocus)
  await nextTick()
  closeButton.value?.focus()
})
onUnmounted(() => {
  document.removeEventListener('keydown', trapFocus)
  if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus()
})

function handleClose() { emit('close') }
function handleSolved(payload) { emit('solved', payload) }
function handleLoaded(payload) { if (payload?.title) title.value = payload.title }
</script>

<style scoped>
.challenge-modal { position: fixed; inset: 0; z-index: 2000; color: var(--ink); font-family: var(--font-family); font-size: var(--text-body); line-height: var(--leading-body); }
.challenge-modal *, .challenge-modal *::before, .challenge-modal *::after { box-sizing: border-box; }
.modal-overlay { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; padding: var(--space-3); background: var(--overlay); }
.modal-container { display: flex; flex-direction: column; width: 100%; max-width: calc(var(--reading-width) + var(--sidebar-width)); max-height: calc(100vh - var(--space-6)); max-height: calc(100dvh - var(--space-6)); background: var(--surface); border-radius: var(--radius-panel); box-shadow: var(--shadow-overlay); overflow: hidden; }
.modal-toolbar { display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; gap: var(--space-2); padding: var(--space-1) var(--space-3); border-bottom: var(--stroke) solid var(--line); color: var(--ink-secondary); font-size: var(--text-caption); }
.modal-content { min-width: 0; min-height: 0; padding: var(--space-3); overflow: auto; overscroll-behavior: contain; }
.close-btn { display: inline-flex; align-items: center; justify-content: center; width: var(--control-height); min-height: var(--control-height); padding: var(--space-1); border: var(--stroke) solid transparent; border-radius: var(--radius-control); background: transparent; color: var(--ink-secondary); cursor: pointer; }
.close-btn:hover { background: var(--surface-hover); color: var(--ink); }
.close-btn:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
@media (max-width: 768px) {
  .modal-overlay { padding: var(--space-1); }
  .modal-container { max-height: calc(100vh - var(--space-2)); max-height: calc(100dvh - var(--space-2)); }
  .modal-toolbar { padding-inline: var(--space-2); }
  .modal-content { padding: var(--space-2); }
}
</style>
