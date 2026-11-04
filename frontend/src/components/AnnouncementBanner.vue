<template>
  <div class="announcement-banner" v-if="announcements.length > 0">
    <div class="announcement-container">
      <div class="announcement-icon"><AppIcon name="bi-megaphone" /></div>
      <div class="announcement-content">
        <div
          v-for="(announcement, index) in visibleAnnouncements"
          :key="announcement.id"
          class="announcement-item"
          @click="handleView(announcement)"
        >
          <span
            v-if="announcement.priority === 'high'"
            class="priority-badge urgent"
          >
            [紧急]
          </span>
          <span
            v-else-if="announcement.priority === 'medium'"
            class="priority-badge important"
          >
            [重要]
          </span>
          <span class="announcement-title">{{ announcement.title }}</span>
          <span class="announcement-time">{{ formatTime(announcement.created_at) }}</span>
        </div>
      </div>
      <button
        v-if="announcements.length > maxVisible"
        class="toggle-btn"
        @click="toggleExpand"
      >
        {{ isExpanded ? '收起' : '更多' }}
      </button>
      <button
        class="close-btn"
        @click="handleClose"
        v-if="closable"
       aria-label="关闭">
        <AppIcon name="bi-x-lg" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'

const props = defineProps({
  maxVisible: {
    type: Number,
    default: 1
  },
  closable: {
    type: Boolean,
    default: true
  },
  autoFetch: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['close'])

const router = useRouter()
const announcements = ref([])
const isExpanded = ref(false)
const closedAnnouncementIds = ref(
  JSON.parse(localStorage.getItem('closed_announcement_ids') || '[]')
)

const visibleAnnouncements = computed(() => {
  const visible = isExpanded.value
    ? announcements.value
    : announcements.value.slice(0, props.maxVisible)

  return visible.filter(
    ann => !closedAnnouncementIds.value.includes(ann.id)
  )
})

const fetchAnnouncements = async () => {
  try {
    const response = await api.announcement.pinned()
    // 如果没有置顶公告，获取最新的公告
    if (response.results.length === 0) {
      const latestResponse = await api.announcement.latest()
      announcements.value = latestResponse.results || []
    } else {
      announcements.value = response.results || []
    }
  } catch (error) {
    console.error('获取公告失败:', error)
  }
}

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const handleView = (announcement) => {
  // 可以跳转到公告详情页或打开弹窗
  emit('view', announcement)
}

const handleClose = () => {
  emit('close')
}

const formatTime = (time) => {
  const date = new Date(time)
  const now = new Date()
  const diff = now - date

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`

  return date.toLocaleDateString('zh-CN')
}

onMounted(() => {
  if (props.autoFetch) {
    fetchAnnouncements()
  }
})

defineExpose({
  fetchAnnouncements
})
</script>

<style scoped>
.announcement-banner {
  background: var(--surface-muted);
  color:var(--ink);
  padding:var(--space-1) var(--space-2);
  box-shadow: var(--shadow-raised);
}

.announcement-container {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  max-width:var(--table-width);
  margin:0 auto;
}

.announcement-icon {
  font-size:var(--text-card);
  flex-shrink:0;
}

.announcement-content {
  flex:1;
  min-width:0;
}

.announcement-item {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  cursor:pointer;
  padding:calc(var(--space-1) / 2) 0;
  transition:opacity var(--motion-normal);
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}

.announcement-item:hover {
  opacity:0.8;
}

.priority-badge {
  font-size:var(--text-caption);
  font-weight:bold;
  padding:calc(var(--stroke) * 2) calc(var(--space-1) / 2);
  border-radius:var(--radius-control);
  flex-shrink:0;
}

.priority-badge.urgent {
  background:var(--action);
  color:var(--on-action);
}

.priority-badge.important {
  background:var(--action);
  color:var(--on-action);
}

.announcement-title {
  font-size:var(--text-caption);
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.announcement-time {
  font-size:var(--text-caption);
  opacity:0.8;
  flex-shrink:0;
  margin-left:auto;
}

.toggle-btn,
.close-btn {
  background:var(--surface-muted);
  border:none;
  color:var(--ink);
  padding:calc(var(--space-1) / 2) var(--space-1);
  border-radius:var(--radius-control);
  cursor:pointer;
  font-size:var(--text-caption);
  transition:background var(--motion-normal);
  flex-shrink:0;
}

.toggle-btn:hover,
.close-btn:hover {
  background:var(--surface-muted);
}

.close-btn {
  padding:calc(var(--space-1) / 2) var(--space-1);
  font-size:var(--text-body);
}

@media (max-width: 768px) {
  .announcement-container {
    gap:var(--space-1);
  }

  .announcement-item {
    font-size:var(--text-caption);
  }

  .toggle-btn,
  .close-btn {
    padding:calc(var(--space-1) / 2) var(--space-1);
    font-size:var(--text-caption);
  }
}
</style>
