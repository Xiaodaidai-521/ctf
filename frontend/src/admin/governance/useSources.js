import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, watch } from 'vue'
import { useUserStore } from '@/store/user'
import { createSourceController } from './data.js'

export function useGovernanceSources(loaders) {
  const user = useUserStore()
  const allowed = computed(() => user.isAuthenticated && user.userInfo?.role === 'admin')
  const sources = reactive(Object.fromEntries(Object.keys(loaders).map(key => [key, { data: null, error: '', loading: false }])))
  let active = true
  let sessionChanged = false
  const controller = createSourceController(sources, loaders, () => allowed.value && active && !sessionChanged)
  const loading = computed(() => Object.values(sources).some(source => source.loading))
  const storageChanged = event => {
    if (event.key === 'userInfo' || event.key === null) { sessionChanged = true; controller.clear() }
  }
  watch(() => user.userInfo, () => controller.clear(), { deep: true, flush: 'sync' })
  onMounted(() => { controller.load(); window.addEventListener('storage', storageChanged) })
  onActivated(() => { if (!active) { active = true; controller.load() } })
  onDeactivated(() => { active = false; controller.clear() })
  onBeforeUnmount(() => { active = false; controller.clear(); window.removeEventListener('storage', storageChanged) })
  return { user, allowed, sources, loading, load: controller.load, clear: controller.clear }
}
