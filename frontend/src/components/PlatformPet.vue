<template>
  <aside
    ref="container"
    class="platform-pet"
    :style="{ left: `${position.x}px`, top: `${position.y}px` }"
    :data-state="pet.state"
    aria-label="状态宠物"
    @keydown.esc="settingsOpen = false"
  >
    <button v-if="pet.preferences.hidden" class="pet-recall" @click="pet.setHidden(false)">
      <i class="bi bi-shield-lock" aria-hidden="true"></i>
      唤回宠物<span v-if="pet.state !== 'idle'" class="pet-dot" :title="statusLabel"></span>
    </button>
    <template v-else>
      <div class="pet-toolbar">
        <span class="pet-name">{{ manifest?.displayName || '状态宠物' }}</span>
        <button aria-label="宠物设置" :aria-expanded="settingsOpen" @click="toggleSettings">⚙</button>
        <button aria-label="收起宠物" @click="hidePet">−</button>
      </div>
      <button
        class="pet-body"
        :aria-label="`${statusLabel}；点击查看，拖动或用方向键移动宠物`"
        :title="`${pet.current?.label || '学习伙伴'} · ${statusLabel}`"
        @pointerdown="startDrag"
        @pointermove="moveDrag"
        @pointerup="endDrag"
        @pointercancel="cancelDrag"
        @lostpointercapture="cancelDrag"
        @keydown="moveWithKeyboard"
        @click="activate"
      >
        <span v-if="manifest && imageReady" class="pet-sprite" :style="spriteStyle" aria-hidden="true"></span>
        <span v-else class="pet-fallback" aria-hidden="true"><i class="bi bi-shield-lock"></i></span>
      </button>
      <p class="pet-status" role="status" aria-live="polite">{{ statusLabel }}</p>
      <span v-if="assetError" class="pet-asset-error" title="可在设置中重试或更换目录">素材不可用 · 简洁模式</span>
      <section v-if="settingsOpen" class="pet-settings" aria-label="宠物设置面板">
        <PetSelector :model-value="pet.preferences.pack" @update:model-value="selectPack" />
        <details class="pet-custom">
          <summary>高级 / 自定义</summary>
          <form @submit.prevent="applyPack">
            <label for="pet-pack">宠物目录</label>
            <input id="pet-pack" v-model="packInput" placeholder="/pets/dundun" autocomplete="off" />
            <p>目录内需有 pet.json 和图集。</p>
            <button type="submit">加载 / 重试</button>
          </form>
        </details>
        <div class="pet-settings-actions">
          <button type="button" @click="resetPosition">重置位置</button>
        </div>
      </section>
      <p v-if="message" class="pet-message" role="alert">{{ message }}</p>
    </template>
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePetStore } from '@/store/pet'
import PetSelector from './PetSelector.vue'
import {
  PET_ANIMATIONS, PET_LABELS, clampPetPosition,
  loadPetManifest, petFrameAt, validatePetImage
} from '@/utils/pet'

const pet = usePetStore()
const router = useRouter()
const container = ref(null)
const defaultPosition = () => ({ x: Math.max(0, window.innerWidth - 140), y: Math.max(0, window.innerHeight - 260) })
const position = ref(pet.preferences.position || defaultPosition())
const settingsOpen = ref(false)
const packInput = ref(pet.preferences.pack)
const message = ref('')
const manifest = ref(null)
const imageReady = ref(false)
const assetError = ref(false)
const frame = ref(0)
const reducedMotion = ref(window.matchMedia('(prefers-reduced-motion: reduce)').matches)
const pageVisible = ref(!document.hidden)
const reload = ref(0)
const statusLabel = computed(() => PET_LABELS[pet.state])
const animation = computed(() => manifest.value?.animations[PET_ANIMATIONS[pet.state]])
const spriteStyle = computed(() => {
  if (!manifest.value || !animation.value) return {}
  const { cellWidth, cellHeight, columns, spritesheetPath } = manifest.value
  const scale = Math.min(96 / cellWidth, 104 / cellHeight)
  const width = cellWidth * scale
  const height = cellHeight * scale
  return {
    width: `${width}px`, height: `${height}px`,
    backgroundImage: `url("${pet.preferences.pack}/${spritesheetPath}")`,
    backgroundSize: `${columns * width}px auto`,
    backgroundPosition: `${-frame.value * width}px ${-animation.value.row * height}px`
  }
})

watch([() => pet.preferences.pack, reload], async ([pack], _, onCleanup) => {
  const controller = new AbortController()
  let active = true
  let image
  onCleanup(() => {
    active = false
    controller.abort()
    if (image) image.onload = image.onerror = null
  })
  manifest.value = null
  imageReady.value = false
  assetError.value = false
  try {
    const data = await loadPetManifest(pack, controller.signal)
    if (!active) return
    image = new Image()
    image.onload = () => {
      if (!active) return
      try {
        validatePetImage(data, image)
        manifest.value = data
        imageReady.value = true
      } catch {
        assetError.value = true
      }
    }
    image.onerror = () => { if (active) assetError.value = true }
    image.src = `${pack}/${data.spritesheetPath}`
  } catch {
    if (active) assetError.value = true
  }
}, { immediate: true })

watch(() => pet.preferences.hidden, hidden => {
  if (hidden) settingsOpen.value = false
})

watch([animation, imageReady, () => pet.preferences.hidden, reducedMotion, pageVisible], (_, __, onCleanup) => {
  frame.value = 0
  if (!animation.value || !imageReady.value || pet.preferences.hidden || reducedMotion.value || !pageVisible.value) return
  let requestId
  const start = performance.now()
  const tick = (now) => {
    frame.value = petFrameAt(animation.value, now - start)
    requestId = requestAnimationFrame(tick)
  }
  requestId = requestAnimationFrame(tick)
  onCleanup(() => cancelAnimationFrame(requestId))
}, { immediate: true })

function clampPosition(candidate = position.value) {
  const rect = container.value?.getBoundingClientRect()
  position.value = clampPetPosition(candidate, { width: window.innerWidth, height: window.innerHeight }, {
    width: rect?.width || 120, height: rect?.height || 160
  })
}

let drag = null
let suppressClick = false
function startDrag(event) {
  if (event.button !== 0 || !event.isPrimary) return
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
function cancelDrag() {
  if (!drag) return
  suppressClick = true
  pet.setPosition(position.value)
  drag = null
}
function moveWithKeyboard(event) {
  const steps = { ArrowLeft: [-16, 0], ArrowRight: [16, 0], ArrowUp: [0, -16], ArrowDown: [0, 16] }
  if (!steps[event.key]) return
  event.preventDefault()
  const [x, y] = steps[event.key]
  clampPosition({ x: position.value.x + x, y: position.value.y + y })
  pet.setPosition(position.value)
}
async function activate(event) {
  if (suppressClick && event.detail !== 0) {
    suppressClick = false
    return
  }
  const activity = pet.current
  message.value = ''
  try {
    const failure = await router.push(activity?.target || '/multi-agent')
    if (!failure && activity) pet.acknowledge(activity.source, activity.token)
    else if (activity && router.currentRoute.value.fullPath === router.resolve(activity.target).fullPath) {
      pet.acknowledge(activity.source, activity.token)
    }
  } catch {
    message.value = '页面暂时无法打开，请重试。'
  }
}
function hidePet() {
  settingsOpen.value = false
  message.value = ''
  pet.setHidden(true)
}
function toggleSettings() {
  packInput.value = pet.preferences.pack
  settingsOpen.value = !settingsOpen.value
}
function selectPack(pack) {
  packInput.value = pack
  applyPack()
}
function applyPack() {
  if (!pet.setPack(packInput.value)) {
    message.value = '请输入 /pets/ 下的目录，如 /pets/dundun。'
    return
  }
  message.value = ''
  reload.value++
}
function resetPosition() {
  clampPosition(defaultPosition())
  pet.setPosition(position.value)
}
function onResize() {
  clampPosition()
}
function onVisibilityChange() {
  pageVisible.value = !document.hidden
}
function onMotionChange(event) {
  reducedMotion.value = event.matches
}
const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
let observer
onMounted(() => {
  clampPosition()
  observer = new ResizeObserver(onResize)
  observer.observe(container.value)
  window.addEventListener('resize', onResize)
  document.addEventListener('visibilitychange', onVisibilityChange)
  motionQuery.addEventListener('change', onMotionChange)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('resize', onResize)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  motionQuery.removeEventListener('change', onMotionChange)
})
</script>

<style scoped>
.platform-pet {
  position: fixed;
  z-index: 900;
  width: 120px;
  color: var(--text-primary);
  user-select: none;
}
.platform-pet button {
  color: inherit;
  cursor: pointer;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--bg-light);
}
.platform-pet button:focus-visible, .platform-pet input:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}
.pet-toolbar { display: flex; gap: 4px; align-items: center; }
.pet-name { flex: 1; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pet-toolbar button { width: 26px; height: 26px; }
.platform-pet .pet-body {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 120px;
  height: 108px;
  border: 0;
  background: transparent;
  touch-action: none;
  cursor: grab;
}
.platform-pet .pet-body:active { cursor: grabbing; }
.pet-sprite { display: block; background-repeat: no-repeat; image-rendering: pixelated; }
.pet-fallback { display: grid; place-items: center; width: 76px; height: 76px; font-size: 42px; background: var(--bg-paper-2); border-radius: 12px; }
.pet-status { margin: 0; padding: 3px 4px; font-size: 11px; text-align: center; border-radius: 4px; background: var(--bg-light); border: 1px solid var(--border-color); }
[data-state="working"] .pet-status { border-color: var(--text-secondary); }
[data-state="needs-input"] .pet-status { border-color: var(--warning-color); }
[data-state="ready"] .pet-status { border-color: var(--success-color); }
[data-state="failed"] .pet-status { border-color: var(--error-color); }
.pet-asset-error { display: block; font-size: 10px; text-align: center; background: var(--bg-light); }
.pet-recall { width: 120px; min-height: 32px; padding: 4px 8px; font-size: 12px; }
.pet-dot { display: inline-block; width: 6px; height: 6px; margin-left: 4px; border-radius: 50%; background: var(--primary-color); }
.platform-pet:has(.pet-settings) { width: 280px; max-width: 100vw; }
.pet-settings { padding: 10px; margin-top: 6px; max-height: max(100px, calc(100dvh - 250px)); overflow-y: auto; background: var(--bg-light); border: 1px solid var(--border-color); border-radius: 6px; font-size: 12px; }
.pet-custom { margin: 10px 0; }
.pet-custom summary { cursor: pointer; color: var(--text-secondary); }
.pet-custom form { margin-top: 8px; }
.pet-settings input { width: 100%; padding: 4px; margin-top: 4px; color: var(--text-primary); background: var(--bg-light); border: 1px solid var(--border-color); border-radius: 4px; user-select: text; }
.pet-settings p { margin: 6px 0; color: var(--text-secondary); }
.pet-settings-actions { display: flex; gap: 6px; }
.pet-settings-actions button { padding: 4px 6px; }
.pet-message { padding: 4px; font-size: 12px; color: var(--error-color); background: var(--bg-light); }
</style>
