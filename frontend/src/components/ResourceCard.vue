<template>
  <div class="resource-card" @click="handleClick">
    <div class="card-cover">
      <img v-if="resource.cover_url" :src="resource.cover_url" :alt="resource.title" class="cover-image" />
      <div v-else class="cover-placeholder">
        <span class="cover-kicker">RESOURCE FILE</span>
        <span class="cover-icon">{{ typeIcon }}</span>
        <span class="cover-code">#{{ resource.id }}</span>
      </div>
      <div class="resource-type-badge" :class="typeBadgeClass">
        {{ typeLabel }}
      </div>
    </div>
    <div class="card-body">
      <h3 class="resource-title">{{ resource.title }}</h3>
      <span v-if="isAIHighlighted" class="ai-generated-badge">AI多模态生成</span>
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
          <span class="stat-icon"><i class="bi bi-eye"></i></span>
          {{ resource.view_count }}
        </span>
        <span class="stat-item">
          <span class="stat-icon"><i class="bi bi-download"></i></span>
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
    'document': '📄',
    'video': '🎬',
    'report': '📊',
    'zip': '📦',
    'ai_resource': '✨'
  }
  return icons[props.resource.resource_type] || '📁'
})

const isAIHighlighted = computed(() => Boolean(
  props.resource.is_ai_highlighted || props.resource.ai_generated_label
))

const typeLabel = computed(() => {
  if (isAIHighlighted.value) return 'AI推荐多模态资料'
  return props.resource.resource_type === 'ai_resource'
    ? 'AI资源'
    : props.resource.resource_type_display
})

const typeBadgeClass = computed(() => isAIHighlighted.value
  ? 'type-ai-recommended'
  : `type-${props.resource.resource_type}`)

const displayUploaderName = computed(() => isAIHighlighted.value
  ? 'AI教学辅导师'
  : (props.resource.uploader_info?.username || '未知'))

const displayUploaderInitial = computed(() => isAIHighlighted.value
  ? 'AI'
  : (displayUploaderName.value?.charAt(0) || 'U'))
const handleClick = () => {
  emit('click', props.resource)
}
</script>

<style scoped>
.resource-card {
  background: rgba(255, 250, 242, 0.74);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: none;
  cursor: pointer;
  transition: all 0.3s;
  border: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}

.resource-card:hover {
  box-shadow: 8px 8px 0 rgba(24, 23, 19, 0.1);
  transform: translateY(-2px);
  border-color: var(--primary-color);
}

.card-cover {
  position: relative;
  height: 132px;
  overflow: hidden;
  color: #f8f1e8;
  background: var(--bg-dark);
  border-bottom: 1px solid var(--border-color);
}

.cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-placeholder {
  width: 100%;
  height: 100%;
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto 1fr auto;
  gap: 8px;
  padding: 18px;
}

.cover-kicker {
  color: var(--secondary-color);
  font-size: 12px;
  font-weight: 950;
}

.cover-icon {
  grid-column: 2;
  grid-row: 1 / span 3;
  align-self: center;
  font-size: 42px;
  opacity: 0.76;
}

.cover-code {
  align-self: end;
  color: rgba(248, 241, 232, 0.64);
  font-size: 13px;
  font-weight: 850;
}

.resource-type-badge {
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 4px 12px;
  border-radius: 2px;
  font-size: 12px;
  font-weight: 850;
  color: #fbf7ef;
  backdrop-filter: blur(4px);
}

.type-document {
  background: var(--primary-color);
}

.type-video {
  background: #7f3b30;
}

.type-report {
  background: var(--success-color);
}

.type-zip {
  background: #785313;
}

.type-ai_resource {
  background: #6d4aa0;
}

.type-ai-recommended {
  max-width: calc(100% - 24px);
  background: #ead0d4;
  color: #5f3c45;
  border: 1px solid rgba(95, 60, 69, 0.18);
  white-space: normal;
  text-align: center;
}

.card-body {
  padding: 18px;
  flex: 1;
}

.resource-title {
  font-size: 19px;
  line-height: 1.25;
  font-weight: 950;
  color: var(--text-primary);
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-generated-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  margin: 0 0 8px;
  padding: 3px 8px;
  border-radius: 3px;
  background: #1f7a5c;
  color: #fff;
  font-size: 12px;
  font-weight: 900;
}

.resource-description {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.resource-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.meta-tag {
  padding: 3px 8px;
  background: var(--bg-paper-2);
  color: var(--text-secondary);
  border-radius: 2px;
  font-size: 12px;
  font-weight: 750;
}

.card-footer {
  padding: 12px 18px;
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.uploader-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.uploader-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--text-primary);
  color: #fbf7ef;
  font-size: 12px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
}

.uploader-name {
  font-size: 12px;
  color: var(--text-secondary);
}

.stats-info {
  display: flex;
  gap: 12px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.stat-icon {
  color: var(--primary-color);
  font-size: 14px;
}
</style>
