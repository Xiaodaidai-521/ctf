<template>
  <div class="pet-selector" role="group" aria-label="选择宠物" :aria-busy="loading">
    <strong>选择宠物</strong>
    <p v-if="loading" role="status">正在加载宠物…</p>
    <div v-else-if="error" role="alert">
      <p>宠物列表暂时无法加载。</p>
      <button type="button" @click="loadRegistry">重试列表</button>
    </div>
    <template v-else>
      <p>点击即切换，自动保存。</p>
      <div class="pet-choices">
        <button
          v-for="(entry, index) in entries"
          :key="entry.pack"
          type="button"
          class="pet-choice"
          :aria-pressed="modelValue === entry.pack"
          :aria-label="choiceName(entry, index)"
          @click="choose(entry)"
        >
          <span class="pet-choice-thumbnail" aria-hidden="true">
            <span v-if="entry.manifest && !entry.imageFailed" class="pet-choice-frame" :style="petThumbnailStyle(entry.manifest)">
              <img :src="`${entry.pack}/${entry.manifest.spritesheetPath}`" alt="" @error="entry.imageFailed = true" />
            </span>
            <icon-robot v-else />
          </span>
          <span class="pet-choice-name">{{ choiceName(entry, index) }}</span>
          <span class="pet-choice-status">{{ !entry.manifest || entry.imageFailed ? '形象暂不可用 · 重试' : modelValue === entry.pack ? '已选择' : '选择' }}</span>
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { loadPetRegistry, petThumbnailStyle } from '@/utils/petRegistry'

defineProps({ modelValue: { type: String, required: true } })
const emit = defineEmits(['update:modelValue'])

const entries = ref([])
const loading = ref(true)
const error = ref(false)
let controller

function choiceName(entry, index) {
  return entry.manifest?.displayName.trim() || `宠物伙伴 ${index + 1}`
}

function choose(entry) {
  emit('update:modelValue', entry.pack)
  if (!entry.manifest || entry.imageFailed) return loadRegistry()
}

async function loadRegistry() {
  controller?.abort()
  const request = new AbortController()
  controller = request
  loading.value = true
  error.value = false
  try {
    const registry = await loadPetRegistry(request.signal)
    if (!request.signal.aborted) entries.value = registry
  } catch {
    if (!request.signal.aborted) error.value = true
  } finally {
    if (!request.signal.aborted) loading.value = false
  }
}

onMounted(loadRegistry)
onBeforeUnmount(() => controller?.abort())
</script>

<style scoped>
.pet-selector { color: var(--ink); font-size: var(--text-caption); line-height: var(--leading-body); }
.pet-selector strong { font-weight: var(--weight-strong); }
.pet-selector p { margin: var(--space-1) 0; color: var(--ink-secondary); }
.pet-selector button { min-height: var(--control-height); padding: var(--space-1) var(--space-2); font: inherit; color: inherit; cursor: pointer; border: var(--stroke) solid var(--line); border-radius: var(--radius-control); background: var(--surface); }
.pet-selector button:focus-visible { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.pet-choices { display: grid; gap: var(--space-1); }
.pet-selector .pet-choice { display: flex; align-items: center; gap: var(--space-1); width: 100%; padding: var(--space-1); text-align: left; }
.pet-choice:hover { background: var(--surface-hover); }
.pet-selector .pet-choice[aria-pressed="true"] { border-color: var(--agent-accent); background: var(--agent-soft); }
.pet-choice-thumbnail { position: relative; display: grid; place-items: center; flex-shrink: 0; width: var(--pet-size); height: var(--pet-size); overflow: hidden; font-size: var(--text-section); color: var(--agent-accent); }
.pet-choice-frame { position: relative; overflow: hidden; }
.pet-choice-frame img { position: absolute; left: 0; top: var(--sheet-top); width: var(--sheet-width); max-width: none; height: auto; image-rendering: pixelated; }
.pet-choice-name { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.pet-choice-status { flex: 0 1 auto; max-width: 50%; color: var(--ink-secondary); font-size: var(--text-caption); overflow-wrap: anywhere; }
</style>
