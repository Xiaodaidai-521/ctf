import { subscribe, lifecycleLabels } from './lifecycle.js'
import { queueDraft } from './draft.js'

export async function openTutor(router, { prompt = '', userId } = {}) {
  const failure = await router.push('/multi-agent?mode=learning')
  // 重复导航仍可向已打开的对话交接问题；守卫重定向时不留下草稿。
  if (router.currentRoute.value.path === '/multi-agent') queueDraft(prompt, userId)
  return failure
}
export function subscribeTutor(listener) {
  return subscribe(state => listener({ phase: state.phase, label: lifecycleLabels[state.phase] }))
}
