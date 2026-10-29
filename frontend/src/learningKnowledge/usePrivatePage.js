import { onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'
import { createRequestGeneration } from './requestGeneration.js'

// This protects in-memory display, not authorization. Every API rechecks server permissions.
export function usePrivatePage(clearContent) {
  const route = useRoute()
  const user = useUserStore()
  const paused = ref(true)
  const sessionChanged = ref(false)
  let disposed = false
  let activeRoute = ''
  let activeUser = null
  const foreground = () => document.visibilityState === 'visible' && document.hasFocus()
  const generations = createRequestGeneration(() => !paused.value && !sessionChanged.value
    && foreground() && user.isAuthenticated && activeUser === user.userInfo
    && activeRoute === route.fullPath)

  function clear() {
    generations.invalidate()
    paused.value = true
    clearContent()
  }

  function resume() {
    if (disposed || sessionChanged.value || !foreground() || !user.isAuthenticated) return false
    clear()
    activeRoute = route.fullPath
    activeUser = user.userInfo
    paused.value = false
    return true
  }

  function visibilityChanged() {
    if (document.visibilityState !== 'visible') clear()
  }

  function storageChanged(event) {
    // Another tab can change the session cookie without updating this tab's Pinia store.
    if (event.key === 'userInfo' || event.key === null) {
      sessionChanged.value = true
      clear()
    }
  }

  watch(() => user.userInfo, clear, { deep: true, flush: 'sync' })
  watch(() => route.fullPath, clear, { flush: 'sync' })
  onBeforeRouteLeave(clear)
  onDeactivated(clear)
  onMounted(() => {
    window.addEventListener('blur', clear)
    window.addEventListener('pagehide', clear)
    window.addEventListener('storage', storageChanged)
    document.addEventListener('visibilitychange', visibilityChanged)
  })
  onBeforeUnmount(() => {
    disposed = true
    clear()
    generations.dispose()
    activeUser = null
    window.removeEventListener('blur', clear)
    window.removeEventListener('pagehide', clear)
    window.removeEventListener('storage', storageChanged)
    document.removeEventListener('visibilitychange', visibilityChanged)
  })

  return {
    paused,
    sessionChanged,
    clear,
    resume,
    reload: () => window.location.reload(),
    begin() {
      if (disposed || paused.value || sessionChanged.value || !foreground() || !user.isAuthenticated) {
        clear()
        return null
      }
      return generations.begin()
    },
  }
}
