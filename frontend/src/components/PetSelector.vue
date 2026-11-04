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
          v-for="entry in entries"
          :key="entry.pack"
          type="button"
          class="pet-choice"
          :aria-pressed="modelValue === entry.pack"
          :aria-label="entry.manifest?.displayName || entry.pack"
          @click="$emit('update:modelValue', entry.pack)"
        >
          <span class="pet-choice-thumbnail" aria-hidden="true">
            <span v-if="entry.manifest && !entry.imageFailed" class="pet-choice-frame" :style="petThumbnailStyle(entry.manifest)">
              <img :src="`${entry.pack}/${entry.manifest.spritesheetPath}`" alt="" @error="entry.imageFailed = true" />
            </span>
            <i v-else class="bi bi-shield-lock"></i>
          </span>
          <span class="pet-choice-name">{{ entry.manifest?.displayName || entry.pack }}</span>
          <span class="pet-choice-status">{{ modelValue === entry.pack ? '已选择' : entry.manifest ? '选择' : '素材不可用 · 重试' }}</span>
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { loadPetRegistry, petThumbnailStyle } from '@/utils/petRegistry'

defineProps({ modelValue: { type: String, required: true } })
defineEmits(['update:modelValue'])

const entries = ref([])
const loading = ref(true)
const error = ref(false)
let controller

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
.pet-selector p { margin: 6px 0; color: var(--text-secondary); }
.pet-selector button { color: inherit; cursor: pointer; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-light); }
.pet-selector button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.pet-choices { display: grid; gap: 6px; }
.pet-selector .pet-choice { display: flex; align-items: center; gap: 8px; width: 100%; padding: 4px 8px; text-align: left; }
.pet-choice:hover { background: var(--bg-paper-2); }
.pet-selector .pet-choice[aria-pressed="true"] { border-color: var(--primary-color); background: var(--bg-paper-2); }
.pet-choice-thumbnail { position: relative; display: grid; place-items: center; flex-shrink: 0; width: 48px; height: 52px; overflow: hidden; font-size: 24px; }
.pet-choice-frame { position: relative; overflow: hidden; }
.pet-choice-frame img { position: absolute; left: 0; top: var(--sheet-top); width: var(--sheet-width); max-width: none; height: auto; image-rendering: pixelated; }
.pet-choice-name { flex: 1; overflow-wrap: anywhere; }
.pet-choice-status { color: var(--text-secondary); font-size: 10px; }
</style>
