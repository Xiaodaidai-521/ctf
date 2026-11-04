<template>
  <div v-show="!pet.preferences.hidden" ref="home" class="pet-layer" :data-state="pet.state">
    <button ref="launcher" type="button" class="tutor-pet pet-launcher" :aria-expanded="pet.opened" aria-controls="platform-pet" aria-label="智航伙伴，唤出或收起宠物" @click="togglePet">
      <icon-robot aria-hidden="true" /><span>智航伙伴</span>
    </button>
    <Teleport :to="floating.target || 'body'" :disabled="!floating.target">
    <div class="pet-surface" :class="{ 'is-window': floating.target }" :data-window-mode="floating.mode" :data-state="pet.state">
    <aside v-show="pet.opened" id="platform-pet" ref="container" class="platform-pet" :style="floating.target ? undefined : { left: `${position.x}px`, top: `${position.y}px` }" aria-label="智航伙伴" @keydown.esc.stop="escape">
      <div class="pet-scene">
        <button ref="body" type="button" class="pet-body" :aria-label="`${manifest?.displayName || '学习伙伴'}，${statusLabel}；右键打开菜单，${floating.target ? '拖动窗口标题栏移动' : '方向键移动'}`" aria-haspopup="menu" :aria-expanded="settingsOpen" @contextmenu.prevent="openMenu" @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="endDrag" @pointercancel="cancelDrag" @lostpointercapture="cancelDrag" @keydown="bodyKeydown" @click="focusInput">
          <span v-if="manifest && imageReady" class="pet-sprite" :style="spriteStyle" aria-hidden="true"></span>
          <icon-robot v-else class="pet-fallback" aria-hidden="true" />
        </button>
        <section class="pet-bubble" aria-label="最新一轮对话">
          <div class="pet-bubble-heading"><strong>{{ manifest?.displayName || '学习伙伴' }}</strong><span role="status">{{ statusLabel }}</span></div>
          <div ref="answer" class="pet-answer" tabindex="0" aria-label="最新回答，可滚动阅读" aria-live="polite" aria-atomic="true">
            <p v-if="examPage">测评中先独立作答，交卷后再一起看。</p>
            <template v-else>
              <p v-if="session.restoring">正在找回上次对话…</p>
              <p v-else-if="session.sending">正在为你组织讲解…</p>
              <p v-else-if="session.error" role="alert">{{ session.error }}</p>
              <p v-else-if="!turn.replies.length">说说目标或卡住的地方，我们一起学。</p>
              <div v-for="reply in turn.replies" :key="reply.id" class="pet-reply"><span class="pet-speaker">{{ reply.agentName || '教学辅导师' }}</span><p>{{ reply.content }}</p></div>
            </template>
          </div>
          <button v-if="!examPage" type="button" class="pet-full" @click="openFull">展开完整对话与历史<icon-arrow-right aria-hidden="true" /></button>
        </section>
      </div>
      <form v-if="!examPage" class="pet-composer" @submit.prevent="submit">
        <label for="pet-question">和教学伙伴聊聊</label>
        <textarea id="pet-question" ref="field" v-model="text" rows="2" maxlength="2000" placeholder="说说目标或卡住的地方" :disabled="session.restoring" @compositionstart="composing = true" @compositionend="composing = false" @keydown="inputKeydown" />
        <div class="pet-composer-actions"><span>Ctrl / ⌘ + Enter 发送</span><button type="submit" :disabled="session.sending || session.restoring || !text.trim()">{{ session.sending ? '正在讲解' : '发送' }}</button></div>
      </form>
      <p v-if="floating.notice" class="pet-notice pet-window-notice" role="status">{{ floating.notice }}</p>
      <div class="pet-tools">
        <button v-if="!examPage && !floating.target" type="button" :disabled="floating.opening" @click="detach()">{{ floating.opening ? '正在打开…' : '置顶小窗' }}</button>
        <button v-if="floating.fallbackAvailable && !examPage" type="button" @click="detach(true)">打开普通小窗</button>
        <button v-if="floating.target" type="button" @click="dockWindow">回到平台页</button>
        <button ref="menuButton" type="button" aria-label="宠物菜单" aria-haspopup="menu" :aria-expanded="settingsOpen" @click="toggleMenu"><icon-settings aria-hidden="true" />菜单</button>
        <button type="button" aria-label="收起宠物，保留唤出按钮" @click="collapse">收起</button>
      </div>
      <section v-if="settingsOpen" ref="menu" class="pet-settings" aria-label="宠物设置">
        <div role="menu" aria-label="宠物菜单" @keydown="menuKeydown">
          <button type="button" role="menuitem" @click="showChoices = !showChoices" :aria-expanded="showChoices">切换形象</button>
          <button v-if="!floating.target" type="button" role="menuitem" @click="resetPosition">重置位置</button>
          <button v-if="assetError" type="button" role="menuitem" @click="reload++">重新加载形象</button>
          <button v-if="!examPage" type="button" role="menuitem" :disabled="session.sending || session.restoring" @click="confirmRestart">重新开始对话</button>
          <button type="button" role="menuitem" @click="hidePet">隐藏宠物以及智能体</button>
        </div>
        <PetSelector v-if="showChoices" :model-value="pet.preferences.pack" @update:model-value="selectPack" />
      </section>
      <p v-if="assetError" class="pet-notice" role="status">这个形象暂时没能显示，可以在菜单中重试或换一只。</p>
    </aside>
    <dialog v-if="floating.target" ref="restartDialog" class="pet-confirmation" aria-labelledby="pet-confirmation-title" @cancel="restartOpen = false" @close="closeRestartDialog">
      <h2 id="pet-confirmation-title">开始一段新对话？</h2>
      <p>当前对话会收好，接下来从新的问题开始。已有学习记录不会删除。</p>
      <div class="pet-tools"><button type="button" autofocus @click="restartOpen = false">取消</button><button type="button" @click="restart">确定</button></div>
    </dialog>
    <a-modal v-else v-model:visible="restartOpen" title="开始一段新对话？" :width="'min(92vw, 420px)'" @ok="restart" @cancel="restartOpen = false">
      <p>当前对话会收好，接下来从新的问题开始。已有学习记录不会删除。</p>
    </a-modal>
    </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { usePetStore } from '@/store/pet'
import PetSelector from './PetSelector.vue'
import { PET_ANIMATIONS, PET_LABELS, clampPetPosition, loadPetManifest, petFrameAt, validatePetImage } from '@/utils/pet'
import { latestPetTurn } from '@/learning/agent/petBridge.js'
import { closeTutorDrawer } from '@/learning/agent/host.js'
import { createPetWindowController } from '@/learning/agent/petWindow.js'

const props = defineProps({ session: { type: Object, required: true }, examPage: Boolean })
const emit = defineEmits(['send', 'full', 'restart'])
const pet = usePetStore()
const home = ref(null)
const floating = shallowRef({})
const petWindow = createPetWindowController({ owner: window, getStyleSource: () => home.value, onChange: value => { floating.value = value } })
const displayWindow = computed(() => floating.value.window || window)
const container = ref(null)
const launcher = ref(null)
const body = ref(null)
const menuButton = ref(null)
const menu = ref(null)
const field = ref(null)
const answer = ref(null)
const text = ref('')
const composing = ref(false)
const settingsOpen = ref(false)
const showChoices = ref(false)
const restartOpen = ref(false)
const restartDialog = ref(null)
const manifest = ref(null)
const imageReady = ref(false)
const assetError = ref(false)
const frame = ref(0)
const reload = ref(0)
const reducedMotion = ref(window.matchMedia('(prefers-reduced-motion: reduce)').matches)
const pageVisible = ref(!document.hidden)
const viewport = () => ({ width: displayWindow.value.visualViewport?.width || displayWindow.value.innerWidth, height: displayWindow.value.visualViewport?.height || displayWindow.value.innerHeight })
const defaultPosition = () => ({ x: Math.max(8, viewport().width - 464), y: Math.max(8, viewport().height - 480) })
const position = ref(pet.preferences.position || defaultPosition())
const turn = computed(() => latestPetTurn(props.session.messages))
const statusLabel = computed(() => props.examPage ? '陪你独立作答' : PET_LABELS[pet.state])
const animation = computed(() => manifest.value?.animations[PET_ANIMATIONS[pet.state]])
const spriteStyle = computed(() => {
  if (!manifest.value || !animation.value) return {}
  const { cellWidth, cellHeight, columns, spritesheetPath } = manifest.value
  const scale = Math.min(96 / cellWidth, 104 / cellHeight)
  const width = cellWidth * scale
  const height = cellHeight * scale
  return { width: `${width}px`, height: `${height}px`, backgroundImage: `url("${pet.preferences.pack}/${spritesheetPath}")`, backgroundSize: `${columns * width}px auto`, backgroundPosition: `${-frame.value * width}px ${-animation.value.row * height}px` }
})

watch([() => pet.preferences.pack, reload], async ([pack], _, onCleanup) => {
  const controller = new AbortController()
  let active = true
  let image
  onCleanup(() => { active = false; controller.abort(); if (image) image.onload = image.onerror = null })
  manifest.value = null
  imageReady.value = false
  assetError.value = false
  try {
    const data = await loadPetManifest(pack, controller.signal)
    if (!active) return
    image = new Image()
    image.onload = () => {
      if (!active) return
      try { validatePetImage(data, image); manifest.value = data; imageReady.value = true } catch { assetError.value = true }
    }
    image.onerror = () => { if (active) assetError.value = true }
    image.src = `${pack}/${data.spritesheetPath}`
  } catch { if (active) assetError.value = true }
}, { immediate: true })

watch([animation, imageReady, () => pet.preferences.hidden, () => pet.opened, reducedMotion, pageVisible, displayWindow], (_, __, onCleanup) => {
  frame.value = 0
  if (!animation.value || !imageReady.value || pet.preferences.hidden || !pet.opened || reducedMotion.value || !pageVisible.value) return
  let requestId
  const target = displayWindow.value
  const start = target.performance.now()
  const tick = now => { frame.value = petFrameAt(animation.value, now - start); requestId = target.requestAnimationFrame(tick) }
  requestId = target.requestAnimationFrame(tick)
  onCleanup(() => target.cancelAnimationFrame(requestId))
}, { immediate: true })
watch(() => turn.value.id, () => { if (answer.value) answer.value.scrollTop = 0 })
watch(() => pet.opened, async opened => {
  if (!opened) { settingsOpen.value = false; showChoices.value = false; petWindow.dock(); return }
  await nextTick()
  clampPosition()
})
watch(() => pet.preferences.hidden, hidden => { if (hidden) { settingsOpen.value = false; restartOpen.value = false; petWindow.dock() } }, { flush: 'sync' })
watch(() => props.examPage, () => { settingsOpen.value = false; restartOpen.value = false; petWindow.dock() }, { flush: 'sync' })
watch(displayWindow, async () => { restartOpen.value = false; settingsOpen.value = false; await nextTick(); clampPosition() })
watch([restartOpen, () => floating.value.target], async () => {
  await nextTick()
  const dialog = restartDialog.value
  if (!dialog) return
  if (restartOpen.value && !dialog.open) dialog.showModal()
  else if (!restartOpen.value && dialog.open) dialog.close()
})
let confirmationToken
watch(restartOpen, open => {
  if (open) confirmationToken = pet.requestInput('teaching-confirmation', { label: '确认开始新对话' })
  else { pet.clear('teaching-confirmation', confirmationToken); confirmationToken = undefined }
}, { flush: 'sync' })

function clampPosition(candidate = position.value) {
  if (floating.value.target) return
  const rect = container.value?.getBoundingClientRect()
  const available = viewport()
  available.height = Math.max(0, available.height - 80)
  position.value = clampPetPosition(candidate, available, { width: rect?.width || 448, height: rect?.height || 400 })
}
let drag = null
let suppressClick = false
function startDrag(event) {
  if (floating.value.target || event.button !== 0 || !event.isPrimary) return
  suppressClick = false
  drag = { id: event.pointerId, x: event.clientX, y: event.clientY, origin: { ...position.value }, moved: false }
  event.currentTarget.setPointerCapture(event.pointerId)
}
function moveDrag(event) {
  if (!drag || event.pointerId !== drag.id) return
  const dx = event.clientX - drag.x
  const dy = event.clientY - drag.y
  if (Math.hypot(dx, dy) > 4) drag.moved = true
  if (drag.moved) clampPosition({ x: drag.origin.x + dx, y: drag.origin.y + dy })
}
function endDrag(event) {
  if (!drag || event.pointerId !== drag.id) return
  suppressClick = drag.moved
  if (drag.moved) pet.setPosition(position.value)
  drag = null
  event.currentTarget.releasePointerCapture(event.pointerId)
}
function cancelDrag() { if (drag) { suppressClick = true; pet.setPosition(position.value); drag = null } }
function bodyKeydown(event) {
  if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) { event.preventDefault(); openMenu(); return }
  const steps = { ArrowLeft: [-16, 0], ArrowRight: [16, 0], ArrowUp: [0, -16], ArrowDown: [0, 16] }
  if (!steps[event.key]) return
  event.preventDefault()
  const [x, y] = steps[event.key]
  clampPosition({ x: position.value.x + x, y: position.value.y + y })
  pet.setPosition(position.value)
}
function focusInput(event) {
  if (suppressClick && event.detail !== 0) { suppressClick = false; return }
  pet.acknowledge('teaching-session')
  field.value?.focus()
}
function togglePet() { pet.setOpened(floating.value.target ? true : !pet.opened); if (floating.value.target) floating.value.window.focus(); else if (pet.opened) nextTick(() => field.value?.focus()) }
function detach(popup = false) { if (!props.examPage && !pet.preferences.hidden) { cancelDrag(); pet.setOpened(true); petWindow.open({ popup }) } }
function dockWindow() { petWindow.dock(); nextTick(() => { window.focus(); field.value?.focus() }) }
function openFull() { petWindow.dock(); window.focus(); emit('full') }
function collapse() { pet.setOpened(false); launcher.value?.focus() }
function escape() { if (settingsOpen.value) closeMenu(); else collapse() }
function closeMenu() { settingsOpen.value = false; showChoices.value = false; menuButton.value?.focus() }
function toggleMenu() { if (settingsOpen.value) closeMenu(); else openMenu() }
function openMenu() { settingsOpen.value = true; nextTick(() => menu.value?.querySelector('button')?.focus()) }
function menuKeydown(event) {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  const items = [...menu.value.querySelectorAll('[role="menuitem"]:not(:disabled)')]
  const index = items.indexOf(displayWindow.value.document.activeElement)
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
  event.preventDefault()
  items[next]?.focus()
}
function outside(event) { if (settingsOpen.value && !container.value?.contains(event.target)) { settingsOpen.value = false; showChoices.value = false } }
function selectPack(pack) { if (pet.setPack(pack)) reload.value++ }
function hidePet() { closeTutorDrawer(); pet.setHidden(true); document.querySelector('.personal-trigger')?.focus() }
function resetPosition() { clampPosition(defaultPosition()); pet.setPosition(position.value) }
function confirmRestart() { settingsOpen.value = false; restartOpen.value = true }
function closeRestartDialog() { restartOpen.value = false; menuButton.value?.focus() }
function restart() { restartOpen.value = false; text.value = ''; emit('restart') }
function submit() {
  const message = text.value.trim()
  if (!message || props.session.sending || props.session.restoring || props.examPage) return
  text.value = ''
  emit('send', message)
  field.value?.focus()
}
function inputKeydown(event) {
  if (event.isComposing || composing.value) return
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); submit() }
}
function onResize() { if (pet.opened) clampPosition() }
function onMotionChange(event) { reducedMotion.value = event.matches }
let stopDisplay
onMounted(() => {
  stopDisplay = watch(displayWindow, (target, _, onCleanup) => {
    const displayDocument = target.document
    const visibility = () => { pageVisible.value = !displayDocument.hidden }
    const motionQuery = target.matchMedia('(prefers-reduced-motion: reduce)')
    visibility(); reducedMotion.value = motionQuery.matches
    const observer = new target.ResizeObserver(onResize)
    observer.observe(container.value)
    target.addEventListener('resize', onResize)
    target.visualViewport?.addEventListener('resize', onResize)
    displayDocument.addEventListener('visibilitychange', visibility)
    displayDocument.addEventListener('pointerdown', outside)
    motionQuery.addEventListener('change', onMotionChange)
    onCleanup(() => {
      observer.disconnect()
      target.removeEventListener('resize', onResize)
      target.visualViewport?.removeEventListener('resize', onResize)
      displayDocument.removeEventListener('visibilitychange', visibility)
      displayDocument.removeEventListener('pointerdown', outside)
      motionQuery.removeEventListener('change', onMotionChange)
    })
  }, { immediate: true, flush: 'post' })
})
onBeforeUnmount(() => {
  stopDisplay?.()
  petWindow.dispose()
  pet.clear('teaching-confirmation', confirmationToken)
})
</script>

<style scoped>
.pet-layer, .pet-surface { color: var(--ink); }
.is-window .platform-pet { position: relative; width: 100%; max-height: 100dvh; }
.is-window .pet-body { cursor: pointer !important; }
.pet-confirmation { width: min(92vw, 420px); padding: var(--space-3); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); color: var(--ink); background: var(--surface); box-shadow: var(--shadow-overlay); }
.pet-confirmation::backdrop { background: var(--overlay); }
.pet-confirmation h2 { margin-top: 0; font-size: var(--text-section); }
.pet-confirmation p { line-height: var(--leading-body); }
.pet-launcher { position: fixed; right: var(--space-2); bottom: calc(var(--space-2) + env(safe-area-inset-bottom, 0px)); z-index: var(--z-pet); display: flex; align-items: center; gap: var(--space-1); min-height: var(--pet-size); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); background: var(--surface); color: var(--agent-accent); box-shadow: var(--shadow-raised); cursor: pointer; }
.pet-launcher svg { font-size: var(--text-section); }
.is-compact .pet-launcher { min-height: var(--control-height); }
.platform-pet { position: fixed; z-index: var(--z-pet); width: min(var(--form-width), calc(100vw - var(--space-2))); max-height: calc(100dvh - 80px); overflow-y: auto; overscroll-behavior: contain; padding: var(--space-1); }
.platform-pet button { cursor: pointer; font: inherit; }
.pet-scene { display: grid; grid-template-columns: var(--thumbnail-short-height) minmax(0, 1fr); align-items: end; gap: var(--space-1); }
.pet-body { display: grid; place-items: center; width: var(--thumbnail-short-height); height: var(--tile-short-height); padding: 0; border: 0; background: transparent; touch-action: none; cursor: grab !important; }
.pet-body:active { cursor: grabbing !important; }
.pet-sprite { display: block; background-repeat: no-repeat; image-rendering: pixelated; }
.pet-fallback { font-size: var(--space-8); color: var(--agent-accent); }
.pet-bubble { min-width: 0; border: var(--stroke) solid var(--line); border-radius: var(--radius-panel) var(--radius-panel) var(--radius-panel) 0; padding: var(--space-2); background: var(--surface); box-shadow: var(--shadow-raised); }
.pet-bubble-heading { display: flex; flex-wrap: wrap; gap: var(--space-1); align-items: baseline; font-size: var(--text-caption); }
.pet-bubble-heading span { color: var(--ink-secondary); }
.pet-answer { max-height: min(var(--content-short-height), 28dvh); overflow-y: auto; overflow-x: hidden; overscroll-behavior: contain; overflow-wrap: anywhere; white-space: pre-wrap; line-height: var(--leading-body); font-size: var(--text-caption); }
.pet-answer p { margin: var(--space-1) 0; }
.pet-reply + .pet-reply { margin-top: var(--space-2); }
.pet-speaker { color: var(--ink-secondary); font-size: var(--text-caption); }
.pet-full { display: flex; align-items: center; gap: var(--space-1); padding: var(--space-1) 0 0; border: 0; background: transparent; color: var(--action); font-size: var(--text-caption) !important; text-align: left; }
.pet-composer { margin-top: var(--space-1); padding: var(--space-2); background: var(--surface); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); box-shadow: var(--shadow-raised); }
.pet-composer label { font-size: var(--text-caption); color: var(--ink-secondary); }
.pet-composer textarea { display: block; width: 100%; margin: var(--space-1) 0; resize: none; font: inherit; background: var(--surface); color: var(--ink); border: 0; line-height: var(--leading-body); }
.pet-composer-actions { display: flex; flex-wrap: wrap; gap: var(--space-1); align-items: center; justify-content: space-between; }
.pet-composer-actions span { font-size: var(--text-caption); color: var(--ink-muted); }
.pet-composer-actions button { min-height: var(--control-height); padding: var(--space-1) var(--space-3); border: 0; border-radius: var(--radius-pill); color: var(--on-action); background: var(--button-primary); }
.pet-composer-actions button:disabled { color: var(--disabled-ink); background: var(--disabled); cursor: not-allowed; }
.pet-tools { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--space-1); margin-top: var(--space-1); }
.pet-tools button { display: flex; align-items: center; gap: var(--space-1); min-height: var(--control-height); padding: var(--space-1) var(--space-2); color: var(--ink-secondary); border: var(--stroke) solid var(--line); border-radius: var(--radius-pill); background: var(--surface); }
.pet-settings { margin-top: var(--space-1); padding: var(--space-2); max-height: 40dvh; overflow-y: auto; background: var(--surface); border: var(--stroke) solid var(--line); border-radius: var(--radius-panel); box-shadow: var(--shadow-overlay); }
.pet-settings [role='menu'] { display: grid; gap: var(--space-1); }
.pet-settings [role='menuitem'] { text-align: left; padding: var(--space-1); min-height: var(--control-height); border: 0; border-radius: var(--radius-control); background: var(--surface); color: var(--ink); }
.pet-settings [role='menuitem']:hover { background: var(--surface-hover); }
.pet-settings [role='menuitem']:disabled { color: var(--disabled-ink); cursor: not-allowed; }
.pet-notice { padding: var(--space-1); margin: var(--space-1) 0 0; font-size: var(--text-caption); color: var(--ink-secondary); background: var(--surface); border-radius: var(--radius-control); }
@media (max-width: 480px) {
  .pet-scene { grid-template-columns: var(--space-8) minmax(0, 1fr); }
  .pet-body { width: var(--space-8); overflow: hidden; }
  .pet-sprite { transform: scale(.67); }
  .pet-launcher span { display: none; }
  .pet-composer-actions span { font-size: var(--text-caption); }
}
</style>
