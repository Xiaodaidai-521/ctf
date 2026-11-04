import { watch } from 'vue'
import { uiSnapshot } from './retention.js'

// Pages explicitly pass only filter controls; record data and editors stay out.
export function usePageFilters(domain, controls) {
  const snapshot = uiSnapshot(domain)
  const saved = snapshot.read()
  for (const [key, control] of Object.entries(controls)) {
    if (saved && Object.hasOwn(saved, key) && typeof saved[key] === typeof control.value) control.value = saved[key]
  }
  watch(Object.values(controls), () => {
    snapshot.write(Object.fromEntries(Object.entries(controls).map(([key, control]) => [key, control.value])))
  }, { deep: true, flush: 'sync' })
}
