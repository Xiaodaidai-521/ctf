<template>
  <a-drawer
    v-model:visible="visible"
    :width="compact ? '100%' : 'min(520px, 46vw)'"
    :footer="false"
    :mask-closable="true"
    :title="null"
    unmount-on-close
    class="tutor-drawer"
    @cancel="close"
  >
    <TutorHost mode="drawer" />
  </a-drawer>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { breakpoints } from '@/shared/design/breakpoints.js'
import { closeTutorDrawer, subscribeTutorDrawer } from '../host.js'
import TutorHost from './TutorHost.vue'

const route = useRoute()
const visible = ref(false)
const media = window.matchMedia(`(max-width: ${breakpoints.compact}px)`)
const compact = ref(media.matches)
const resize = () => { compact.value = media.matches }
media.addEventListener('change', resize)
let returnFocus = null
const unsubscribe = subscribeTutorDrawer(snapshot => {
  if (snapshot.open && !visible.value) returnFocus = document.activeElement
  const closing = !snapshot.open && visible.value
  visible.value = snapshot.open
  // 关闭后回到唤起点（“请给一点提示”按钮或宠物），键盘用户不丢失位置。
  if (closing) {
    const target = returnFocus
    returnFocus = null
    requestAnimationFrame(() => {
      if (target && target.isConnected) target.focus()
    })
  }
})
function close() { closeTutorDrawer() }

// Arco 抽屉不提供焦点锁定：Tab / Shift+Tab 在抽屉内首尾循环，避免焦点跑到被遮挡的页面。
const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
function focusables() {
  const root = document.querySelector('.tutor-drawer')
  // 逗号选择器只有第一项带后代关系；改为在抽屉根节点内查询。
  return root ? [...root.querySelectorAll(FOCUSABLE)].filter(el => el.getClientRects().length > 0) : []
}
function onKeydown(event) {
  if (event.key !== 'Tab' || !visible.value) return
  const list = focusables()
  if (!list.length) return
  const active = document.activeElement
  const index = list.indexOf(active)
  // 逐项移动而不是交给浏览器：抽屉是浮层，DOM 顺序可能与被遮挡页面交错。
  const next = index === -1
    ? 0
    : event.shiftKey
      ? (index - 1 + list.length) % list.length
      : (index + 1) % list.length
  event.preventDefault()
  list[next].focus()
}
// 监听常驻、由 visible 守卫：订阅回调可能在 watcher 注册前就打开抽屉。
// 正式答题页不出现题内辅导抽屉。
watch(() => route.path, path => { if (path.startsWith('/exam-taking')) closeTutorDrawer() })
onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  if (route.path.startsWith('/exam-taking')) closeTutorDrawer()
})
onBeforeUnmount(() => { unsubscribe(); media.removeEventListener('change', resize); document.removeEventListener('keydown', onKeydown) })
defineExpose({ close })
</script>
<style scoped>
:deep(.tutor-drawer .arco-drawer-body) { padding: var(--space-2); display: flex; min-height: 0; }
</style>
