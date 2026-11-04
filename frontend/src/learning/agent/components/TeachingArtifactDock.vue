<template>
  <aside class="artifact-dock" :class="{ 'is-expanded': fullscreen }" aria-label="教学产出">
    <header class="dock-heading">
      <h3>教学产出</h3>
      <div class="dock-actions">
        <button type="button" class="quiet-action" :disabled="loading" @click="$emit('refresh')">刷新</button>
        <button v-if="artifacts" type="button" class="quiet-action" @click="fullscreen = true">全屏</button>
        <button type="button" class="quiet-action" aria-label="收起教学产出" @click="$emit('close')">收起</button>
      </div>
    </header>
    <p v-if="failures.length" class="dock-warning" role="status">{{ failures.join('、') }}暂时无法读取。已读取的内容仍可使用。</p>
    <div v-if="!hasArtifacts && !loading" class="dock-empty">
      <p>还没有可停靠的教学产出。</p>
      <p>对话完成后，真实返回的建议、航线进度和复习提醒会显示在这里。</p>
    </div>
    <a-spin v-if="loading" class="dock-loading" tip="正在整理教学产出…" />
    <div class="dock-list">
      <TeachingArtifactView v-if="artifacts?.plan" :artifact="artifacts.plan" />
      <TeachingArtifactView v-if="artifacts?.path" :artifact="artifacts.path" />
      <TeachingArtifactView v-if="artifacts?.reviews" :artifact="artifacts.reviews" />
    </div>
    <a-modal v-model:visible="fullscreen" :footer="false" :width="'min(96vw, 880px)'" title="教学产出">
      <div class="fullscreen-body">
        <TeachingArtifactView v-if="artifacts?.plan" :artifact="artifacts.plan" />
        <TeachingArtifactView v-if="artifacts?.path" :artifact="artifacts.path" />
        <TeachingArtifactView v-if="artifacts?.reviews" :artifact="artifacts.reviews" />
      </div>
    </a-modal>
  </aside>
</template>
<script setup>
import { computed, ref } from 'vue'
import TeachingArtifactView from './TeachingArtifactView.vue'
const props = defineProps({ artifacts: { type: Object, default: null }, failures: { type: Array, default: () => [] }, loading: Boolean })
defineEmits(['refresh', 'close'])
const fullscreen = ref(false)
const hasArtifacts = computed(() => Boolean(props.artifacts?.plan || props.artifacts?.path || props.artifacts?.reviews?.items?.length || props.artifacts?.reviews?.failed))
</script>
<style scoped>
.artifact-dock { display: grid; align-content: start; gap: var(--space-2); min-height: 0; overflow-y: auto; padding: var(--space-2); border-left: var(--stroke) solid var(--line); background: var(--surface-page); }
.dock-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
.dock-heading h3 { margin: 0; font-size: var(--text-card); }
.dock-actions { display: flex; gap: var(--space-1); }
.quiet-action { border: 0; background: transparent; color: var(--ink-secondary); cursor: pointer; font-size: var(--text-caption); padding: var(--space-1); }
.quiet-action:hover:not(:disabled) { color: var(--ink); }
.dock-warning { margin: 0; padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--warning-soft); color: var(--ink-secondary); font-size: var(--text-caption); }
.dock-empty p { margin: 0 0 var(--space-1); color: var(--ink-secondary); }
.dock-loading { display: block; }
.dock-list, .fullscreen-body { display: grid; gap: var(--space-2); }
@media (max-width: 768px) {
  .artifact-dock { border-left: 0; border-top: var(--stroke) solid var(--line); }
}
</style>
