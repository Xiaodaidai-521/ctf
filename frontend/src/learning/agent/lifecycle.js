// 会话内部发布真实请求状态；全站只通过 public.js 订阅。
let snapshot = Object.freeze({ phase: 'idle' })
let generation = 0
const listeners = new Set()
function publish(phase) {
  snapshot = Object.freeze({ phase })
  for (const listener of listeners) listener(snapshot)
}
export function subscribe(listener) {
  listeners.add(listener)
  listener(snapshot)
  return () => listeners.delete(listener)
}
export async function trackRequest(action) {
  const version = ++generation
  publish('working')
  try {
    const result = await action()
    if (version === generation) publish('complete')
    return result
  } catch (error) {
    if (version === generation) publish('error')
    throw error
  }
}
export function resetLifecycle() { generation++; publish('idle') }
export const lifecycleLabels = Object.freeze({ idle: '随时一起学', working: '正在组织讲解', complete: '讲解已准备好', error: '暂时没能完成，请重试' })
