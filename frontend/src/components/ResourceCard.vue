<template>
  <div class="resource-card" @click="handleClick" role="button" tabindex="0" :aria-label="`打开资源：${resource.title}`" @keydown.enter="handleClick" @keydown.space.prevent="handleClick">
    <div class="card-cover">
      <img v-if="resource.cover_url" :src="resource.cover_url" :alt="resource.title" class="cover-image" />
      <div v-else class="cover-placeholder">

        <component :is="typeIcon" class="cover-icon" aria-hidden="true" />

      </div>
      <div class="resource-type-badge" :class="typeBadgeClass">
        {{ typeLabel }}
      </div>
    </div>
    <div class="card-body">
      <h3 class="resource-title">{{ resource.title }}</h3>
      <span v-if="isAIHighlighted" class="ai-generated-badge">导学推荐资料</span>
      <p class="resource-description">{{ resource.description }}</p>
      <div class="resource-meta">
        <span class="meta-tag">{{ resource.category }}</span>
        <span v-for="tag in resource.tags_list" :key="tag" class="meta-tag">
          {{ tag }}
        </span>
      </div>
    </div>
    <div class="card-footer">
      <div class="uploader-info">
        <span class="uploader-avatar">{{ displayUploaderInitial }}</span>
        <span class="uploader-name">{{ displayUploaderName }}</span>
      </div>
      <div class="stats-info">
        <span class="stat-item">
          <span class="stat-icon"><icon-eye aria-hidden="true" /></span>
          {{ resource.view_count }}
        </span>
        <span class="stat-item">
          <span class="stat-icon"><icon-download aria-hidden="true" /></span>
          {{ resource.download_count }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  resource: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['click'])

const typeIcon = computed(() => {
  const icons = {
    'document': 'icon-file',
    'video': 'icon-file-video',
    'report': 'icon-bar-chart',
    'zip': 'icon-storage',
    'ai_resource': 'icon-robot'
  }
  return icons[props.resource.resource_type] || 'icon-folder'
})

const isAIHighlighted = computed(() => Boolean(
  props.resource.is_ai_highlighted || props.resource.ai_generated_label
))

const typeLabel = computed(() => {
  if (isAIHighlighted.value) return '导学推荐资料'
  return props.resource.resource_type === 'ai_resource'
    ? 'AI资源'
    : props.resource.resource_type_display
})

const typeBadgeClass = computed(() => isAIHighlighted.value
  ? 'type-ai-recommended'
  : `type-${props.resource.resource_type}`)

const displayUploaderName = computed(() => props.resource.uploader_info?.username || '上传者暂不可用')
const displayUploaderInitial = computed(() => displayUploaderName.value.charAt(0))
const handleClick = () => {
  emit('click', props.resource)
}
</script>

<style scoped>
.resource-card { background: var(--surface); border-radius: var(--radius-panel); cursor: pointer; transition: background var(--motion-fast); display: flex; flex-direction: column; min-width: 0; }
.resource-card:hover { background: var(--surface-hover); }
.resource-card:active { background: var(--surface-muted); }
.card-cover { position: relative; height: calc(var(--space-8) * 2); color: var(--ink-secondary); background: var(--surface-muted); border-radius: var(--radius-panel) var(--radius-panel) 0 0; overflow: hidden; }
.cover-image { width: 100%; height: 100%; object-fit: cover; }
.cover-placeholder { height: 100%; display: grid; place-items: center; }
.cover-icon { font-size: var(--text-page); }
.resource-type-badge { position: absolute; top: var(--space-1); left: var(--space-1); max-width: calc(100% - var(--space-2)); padding: 0 var(--space-1); border-radius: var(--radius-control); font-size: var(--text-caption); color: var(--ink); background: var(--surface); }
.type-ai-recommended { background: var(--agent-soft); color: var(--agent-accent); }
.card-body { padding: var(--space-2); flex: 1; }
.resource-title { font-size: var(--text-card); line-height: var(--leading-tight); margin: 0 0 var(--space-1); overflow-wrap: anywhere; }
.ai-generated-badge { display: inline-flex; margin-bottom: var(--space-1); padding: 0 var(--space-1); border-radius: var(--radius-control); background: var(--agent-soft); color: var(--agent-accent); font-size: var(--text-caption); }
.resource-description { font-size: var(--text-caption); color: var(--ink-secondary); margin-bottom: var(--space-2); overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow-wrap: anywhere; }
.resource-meta { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.meta-tag { padding: 0 var(--space-1); background: var(--surface-muted); color: var(--ink-secondary); border-radius: var(--radius-control); font-size: var(--text-caption); }
.card-footer { padding: var(--space-2); border-top: var(--stroke) solid var(--line); display: flex; flex-wrap: wrap; gap: var(--space-2); justify-content: space-between; align-items: center; }
.uploader-info { display: flex; align-items: center; gap: var(--space-1); min-width: 0; }
.uploader-avatar { width: var(--space-4); height: var(--space-4); flex-shrink: 0; border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); display: grid; place-items: center; }
.uploader-name { font-size: var(--text-caption); color: var(--ink-secondary); overflow-wrap: anywhere; }
.stats-info { display: flex; gap: var(--space-2); }
.stat-item { display: flex; align-items: center; gap: var(--space-1); font-size: var(--text-caption); color: var(--ink-secondary); }
.stat-icon { font-size: var(--icon-size); }
</style>
