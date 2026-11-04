// 移动同一份宠物 DOM，不创建第二个会话，也不把正文同步到存储或消息广播。
export function preparePetWindow(owner, child, getStyleSource) {
  const doc = child.document
  doc.title = '智航伙伴'
  const base = doc.createElement('base')
  base.href = owner.location.href
  doc.head.append(base)
  const root = doc.createElement('div')
  root.className = 'pet-window-root'
  doc.body.append(root)
  let styles = []
  const syncTheme = () => {
    doc.documentElement.className = owner.document.documentElement.className
    doc.body.className = owner.document.body.className
    const source = owner.getComputedStyle(getStyleSource?.() || owner.document.body)
    for (const name of source) if (name.startsWith('--')) doc.documentElement.style.setProperty(name, source.getPropertyValue(name))
    doc.body.style.margin = '0'
    doc.body.style.background = 'var(--surface)'
    doc.body.style.color = 'var(--ink)'
    doc.body.style.fontFamily = source.fontFamily
  }
  const syncStyles = () => {
    for (const node of styles) node.remove()
    styles = [...owner.document.querySelectorAll('style, link[rel="stylesheet"]')].map(node => {
      const clone = node.cloneNode(true)
      if (node.tagName === 'LINK') clone.href = node.href
      doc.head.append(clone)
      return clone
    })
    syncTheme()
  }
  syncStyles()
  const cssObserver = new owner.MutationObserver(syncStyles)
  cssObserver.observe(owner.document.head, { subtree: true, childList: true, characterData: true, attributes: true })
  const themeObserver = new owner.MutationObserver(syncTheme)
  let ancestor = getStyleSource?.() || owner.document.body
  while (ancestor) {
    themeObserver.observe(ancestor, { attributes: true, attributeFilter: ['class', 'style', 'data-theme', 'data-density'] })
    ancestor = ancestor.parentElement
  }
  return { target: root, cleanup() { cssObserver.disconnect(); themeObserver.disconnect() } }
}

export function createPetWindowController({ owner, onChange, getStyleSource, prepare = preparePetWindow }) {
  let active = null
  let generation = 0
  let opening = false
  let disposed = false
  let notice = ''
  let fallbackAvailable = false
  const publish = () => onChange({ window: active?.window || null, target: active?.target || null, mode: active?.mode || 'inline', opening, notice, fallbackAvailable })
  function dock({ close = true } = {}) {
    generation++
    opening = false
    const previous = active
    active = null
    fallbackAvailable = false
    notice = previous ? '小窗已关闭，宠物已回到平台页。' : ''
    if (previous) {
      previous.window.removeEventListener('pagehide', previous.onClose)
      previous.cleanup()
    }
    publish()
    if (close && previous && !previous.window.closed) previous.window.close()
  }
  async function open({ popup = false } = {}) {
    if (disposed || opening) return
    if (active && !active.window.closed) { active.window.focus(); return }
    const token = ++generation
    opening = true
    notice = ''
    fallbackAvailable = false
    publish()
    let child
    try {
      const native = !popup && typeof owner.documentPictureInPicture?.requestWindow === 'function'
      child = native
        ? await owner.documentPictureInPicture.requestWindow({ width: 480, height: 700 })
        : owner.open('', '', 'popup,width=480,height=700,resizable=yes,scrollbars=yes')
      if (disposed || token !== generation) { child?.close(); return }
      if (!child || child.closed) throw new Error('window-unavailable')
      // 普通小窗不需要通过 opener 操作平台；同一 Vue 实例仍由平台持有。
      if (!native) child.opener = null
      const prepared = prepare(owner, child, getStyleSource)
      const onClose = () => dock({ close: false })
      active = { window: child, ...prepared, mode: native ? 'pip' : 'popup', onClose }
      child.addEventListener('pagehide', onClose)
      notice = native ? '置顶小窗已开启。请保留平台标签页。' : '当前是普通小窗，置顶无法保证，可手动并排放置。请保留平台标签页。'
    } catch {
      child?.close()
      if (disposed || token !== generation) return
      notice = '小窗未能打开。请允许弹出窗口，或尝试普通小窗；普通小窗不保证置顶。'
      fallbackAvailable = true
    } finally {
      if (!disposed && token === generation) { opening = false; publish() }
    }
  }
  const ownerHidden = () => dock()
  function dispose() { disposed = true; dock(); owner.removeEventListener('pagehide', ownerHidden) }
  owner.addEventListener('pagehide', ownerHidden)
  publish()
  return { open, dock, dispose }
}
