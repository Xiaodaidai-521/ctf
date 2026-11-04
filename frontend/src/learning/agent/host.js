import { sanitizeContext } from './context.js'

// 题内宿主登记当前可授权的学习对象；抽屉与宠物共用，不额外抓取页面内容。
let pageContext = null
let open = false
const listeners = new Set()
const contextListeners = new Set()

export function setPageContext(value) {
  pageContext = sanitizeContext(value)
  notifyContext()
  notify()
}
export function clearPageContext(ref) {
  if (ref !== undefined && pageContext && String(pageContext.ref) !== String(ref)) return
  pageContext = null
  notifyContext()
  notify()
}
// 抽屉内监听当前页对象变化：换题时先划清对话边界，不把上一题内容拼进新题。
export function subscribePageContext(listener) {
  contextListeners.add(listener)
  listener(pageContext)
  return () => contextListeners.delete(listener)
}
function notifyContext() {
  for (const listener of contextListeners) listener(pageContext)
}
export function currentPageContext() { return pageContext }

export function requestTutorDrawer({ context = null } = {}) {
  if (context) pageContext = sanitizeContext(context) || pageContext
  open = true
  notify()
}
export function closeTutorDrawer() {
  open = false
  notify()
}
export function subscribeTutorDrawer(listener) {
  listeners.add(listener)
  listener({ open, context: pageContext })
  return () => listeners.delete(listener)
}
export function tutorDrawerSnapshot() { return { open, context: pageContext } }
function notify() {
  const snapshot = { open, context: pageContext }
  for (const listener of listeners) listener(snapshot)
}

// 宿主切换账号或退出时，抽屉和页面上下文都要清空，避免把旧题带给新账号。
export function resetTutorHost() {
  pageContext = null
  open = false
  notifyContext()
  notify()
}
