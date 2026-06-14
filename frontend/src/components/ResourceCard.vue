<template>
  <div class="resource-card" @click="handleClick">
    <div class="card-cover">
      <img v-if="resource.cover_url" :src="resource.cover_url" :alt="resource.title" class="cover-image" />
      <div v-else class="cover-placeholder">
        <span class="cover-icon">{{ typeIcon }}</span>
      </div>
      <div class="resource-type-badge" :class="`type-${resource.resource_type}`">
        {{ resource.resource_type_display }}
      </div>
    </div>
    <div class="card-body">
      <h3 class="resource-title">{{ resource.title }}</h3>
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
        <span class="uploader-avatar">{{ resource.uploader_info?.username?.charAt(0) || 'U' }}</span>
        <span class="uploader-name">{{ resource.uploader_info?.username || '未知' }}</span>
      </div>
      <div class="stats-info">
        <span class="stat-item">
          <span class="stat-icon">👁️</span>
          {{ resource.view_count }}
        </span>
        <span class="stat-item">
          <span class="stat-icon">⬇️</span>
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
    'zip': '📦'
  }
  return icons[props.resource.resource_type] || '📁'
})

const handleClick = () => {
  emit('click', props.resource)
}
</script>

<style scoped>
.resource-card {
  background: white;
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  transition: all 0.3s;
  border: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
}

.resource-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-4px);
  border-color: var(--primary-color);
}

.card-cover {
  position: relative;
  height: 180px;
  overflow: hidden;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.8;
}

.cover-icon {
  font-size: 64px;
}

.resource-type-badge {
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  color: white;
  backdrop-filter: blur(4px);
}

.type-document {
  background: rgba(24, 144, 255, 0.9);
}

.type-video {
  background: rgba(250, 84, 28, 0.9);
}

.type-report {
  background: rgba(82, 196, 26, 0.9);
}

.type-zip {
  background: rgba(114, 46, 209, 0.9);
}

.card-body {
  padding: 16px;
  flex: 1;
}

.resource-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-description {
  font-size: 13px;
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
  padding: 2px 8px;
  background: #f0f0f0;
  color: var(--text-secondary);
  border-radius: 4px;
  font-size: 11px;
}

.card-footer {
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
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
  background: var(--primary-color);
  color: white;
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
  font-size: 14px;
}
</style>
