<template>
  <div ref="root" class="retained-route">
    <RouterView v-slot="{ Component, route: renderedRoute }">
      <KeepAlive :key="scopeKey" :include="included" :max="12">
        <component v-if="cacheable(renderedRoute)" :is="entry(renderedRoute)" :node="Component" :key="retentionKey(renderedRoute)" />
      </KeepAlive>
      <component v-if="!cacheable(renderedRoute)" :is="Component" :key="directKey(renderedRoute)" />
    </RouterView>
  </div>
</template>
<script setup>
import { cloneVNode, computed, defineComponent, markRaw, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { accountScope, captureAccount } from './accountScope.js'
import { cachePolicy, isStaffLayout, retentionKey, RETENTION_MS } from './cachePolicy.js'
import { uiSnapshot } from './retention.js'
const props = defineProps({ layer: { type: String, default: 'root' } })
const route = useRoute()
const router = useRouter()
const root = ref(null)
const entries = shallowRef(new Map())
const timers = new Map()
const scopeKey = computed(() => `${accountScope.value.identity}:${accountScope.value.epoch}`)
const included = computed(() => [...entries.value.values()].map(item => item.name))
let serial = 0, restoreVersion = 0, observer, restoreTimer
const cacheable = value => !isStaffLayout(value, props.layer) && cachePolicy(value, accountScope.value.role) === 'view'
function directKey(value) {
  const path = isStaffLayout(value, props.layer) ? value.path.startsWith('/teacher') ? 'teacher-layout' : 'admin-layout' : retentionKey(value)
  return `${scopeKey.value}:${path}`
}
function entry(value) {
  const key = retentionKey(value)
  if (timers.has(key)) { clearTimeout(timers.get(key)); timers.delete(key) }
  if (!entries.value.has(key)) {
    const name = `RetainedView${++serial}`
    const type = markRaw(defineComponent({ name, props: ['node'], setup: p => () => p.node ? cloneVNode(p.node) : null }))
    const next = new Map(entries.value)
    next.set(key, { name, type })
    if (next.size > 12) next.delete(next.keys().next().value)
    entries.value = next
  }
  return entries.value.get(key).type
}
function stopRestore() {
  restoreVersion++
  observer?.disconnect()
  clearTimeout(restoreTimer)
}
function eligible(value) {
  return !isStaffLayout(value, props.layer) && cachePolicy(value, accountScope.value.role) !== 'none'
}
function saveScroll(value) {
  if (!eligible(value) || !root.value || typeof window === 'undefined') return
  const nested = [...root.value.querySelectorAll('[data-retain-scroll]')].map(el => ({ left: el.scrollLeft, top: el.scrollTop }))
  uiSnapshot(`scroll:${value.fullPath || value.path}`).write({ top: window.scrollY, left: window.scrollX, nested })
}
async function restoreScroll(value) {
  stopRestore()
  // Explicit deep links belong to the page's ready/open-and-focus lifecycle.
  if (value.hash || isStaffLayout(value, props.layer) || typeof window === 'undefined') return
  const snapshot = eligible(value) ? uiSnapshot(`scroll:${value.fullPath || value.path}`).read() : null
  const version = restoreVersion, account = captureAccount()
  await nextTick()
  if (version !== restoreVersion || !account.current()) return
  const restore = () => {
    if (version !== restoreVersion || !account.current()) return
    window.scrollTo({ top: snapshot?.top || 0, left: snapshot?.left || 0, behavior: 'instant' })
    const elements = root.value?.querySelectorAll('[data-retain-scroll]') || []
    snapshot?.nested?.forEach((position, index) => { if (elements[index]) { elements[index].scrollLeft = position.left; elements[index].scrollTop = position.top } })
  }
  window.requestAnimationFrame(() => {
    restore()
    // A UI-only list rereads permissions/data. Restore after its real content arrives.
    if (snapshot && typeof ResizeObserver !== 'undefined' && root.value?.firstElementChild) {
      observer = new ResizeObserver(restore)
      observer.observe(root.value.firstElementChild)
      restoreTimer = setTimeout(() => observer?.disconnect(), 2000)
    }
  })
}
const offBefore = router.beforeEach((to, from) => {
  stopRestore()
  saveScroll(from)
})
const offAfter = router.afterEach((to, from, failure) => {
  if (failure) return
  const previous = retentionKey(from)
  if (previous !== retentionKey(to) && entries.value.has(previous)) {
    clearTimeout(timers.get(previous))
    timers.set(previous, setTimeout(() => {
      const next = new Map(entries.value); next.delete(previous); entries.value = next; timers.delete(previous)
    }, RETENTION_MS))
  }
  if (retentionKey(to) !== retentionKey(from)) restoreScroll(to)
})
const interruptEvents = ['wheel', 'touchstart', 'pointerdown']
for (const name of interruptEvents) window.addEventListener(name, stopRestore, { passive: true })
function onKey(event) { if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', 'Home', 'End', ' '].includes(event.key)) stopRestore() }
window.addEventListener('keydown', onKey)
watch(scopeKey, () => {
  stopRestore()
  for (const timer of timers.values()) clearTimeout(timer)
  timers.clear(); entries.value = new Map()
}, { flush: 'sync' })
// Register before rendering so KeepAlive includes the very first mount, not just later updates.
watch(() => [scopeKey.value, route.path, route.name, route.meta?.cache, route.meta?.sensitive], () => {
  if (cacheable(route)) entry(route)
}, { immediate: true })
onBeforeUnmount(() => {
  offBefore(); offAfter(); stopRestore()
  for (const name of interruptEvents) window.removeEventListener(name, stopRestore)
  window.removeEventListener('keydown', onKey)
  for (const timer of timers.values()) clearTimeout(timer)
})
</script>
<style scoped>
.retained-route { display: contents; }
</style>
