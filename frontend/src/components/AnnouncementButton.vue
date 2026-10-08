<template>
  <div v-if="showButton && hasAnnouncements" class="announcement-button-container">
    <button
      class="announcement-button"
      @click="showListModal = true"
      :class="{ 'has-urgent': hasUrgent, 'pulse': !isRead }"
    >
      <span class="button-icon">📢</span>
      <span class="button-text">公告</span>
      <span v-if="unreadCount > 0" class="badge">{{ unreadCount }}</span>
    </button>

    <!-- 公告列表弹窗 -->
    <div v-if="showListModal" class="modal-overlay" @click.self="showListModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>平台公告</h3>
          <button class="close-btn" @click="showListModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div v-if="loading" class="loading-state">
            <div class="loading-spinner"></div>
            <p>加载中...</p>
          </div>

          <div v-else-if="announcements.length === 0" class="empty-state">
            <p>暂无公告</p>
          </div>

          <div v-else class="announcement-list">
            <div
              v-for="announcement in announcements"
              :key="announcement.id"
              class="announcement-item"
              :class="{
                'unread': !isAnnouncementRead(announcement.id),
                'urgent': announcement.priority === 'high',
                'important': announcement.priority === 'medium'
              }"
              @click="viewDetail(announcement)"
            >
              <div class="announcement-header">
                <span class="priority-badge" :class="announcement.priority">
                  {{ announcement.priority_display }}
                </span>
                <span v-if="announcement.is_pinned" class="pinned-badge">📌</span>
                <span v-if="!isAnnouncementRead(announcement.id)" class="unread-dot"></span>
              </div>
              <h4 class="announcement-title">{{ announcement.title }}</h4>
              <p class="announcement-summary">{{ announcement.summary }}</p>
              <div class="announcement-meta">
                <span>{{ formatDate(announcement.created_at) }}</span>
                <span>👁️ {{ announcement.view_count }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 公告详情弹窗 -->
    <div v-if="showDetailModal" class="modal-overlay" @click.self="showDetailModal = false">
      <div class="modal-content modal-large">
        <div class="modal-header">
          <h3>公告详情</h3>
          <button class="close-btn" @click="showDetailModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div v-if="currentAnnouncement" class="announcement-detail">
            <div v-if="currentAnnouncement.loading" class="loading-state">
              <div class="loading-spinner"></div>
              <p>加载中...</p>
            </div>
            <div v-else>
              <div class="detail-header">
                <h2 class="detail-title">{{ currentAnnouncement.title }}</h2>
                <span class="priority-badge large" :class="currentAnnouncement.priority">
                  {{ currentAnnouncement.priority_display }}
                </span>
              </div>
              <div class="detail-meta">
                <span>发布者: {{ currentAnnouncement.author_name }}</span>
                <span>发布时间: {{ formatDate(currentAnnouncement.published_at || currentAnnouncement.created_at) }}</span>
                <span>浏览次数: {{ currentAnnouncement.view_count }}</span>
              </div>
              <div class="detail-content">
                <pre class="content-text">{{ currentAnnouncement.content }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api'

const route = useRoute()

const showButton = ref(true)
const showListModal = ref(false)
const showDetailModal = ref(false)
const loading = ref(false)
const announcements = ref([])
const currentAnnouncement = ref(null)
const readAnnouncementIds = ref(
  JSON.parse(localStorage.getItem('read_announcement_ids') || '[]')
)

// 检查是否为管理页面
const isAdminRoute = computed(() => {
  return route.path.startsWith('/admin')
})

// 是否有公告
const hasAnnouncements = computed(() => {
  return announcements.value.length > 0
})

// 是否有紧急公告
const hasUrgent = computed(() => {
  return announcements.value.some(ann => ann.priority === 'high')
})

// 未读数量
const unreadCount = computed(() => {
  return announcements.value.filter(
    ann => !readAnnouncementIds.value.includes(ann.id)
  ).length
})

// 是否已读
const isRead = computed(() => {
  return unreadCount.value === 0
})

// 判断公告是否已读
const isAnnouncementRead = (id) => {
  return readAnnouncementIds.value.includes(id)
}

// 获取公告列表
const fetchAnnouncements = async () => {
  loading.value = true
  try {
    const response = await api.announcement.pinned()
    if (response.results.length === 0) {
      const latestResponse = await api.announcement.latest()
      announcements.value = latestResponse.results || []
    } else {
      announcements.value = response.results || []
    }
  } catch (error) {
    console.error('获取公告失败:', error)
  } finally {
    loading.value = false
  }
}

// 查看详情
const viewDetail = async (announcement) => {
  // 先显示弹窗（使用列表数据作为占位）
  currentAnnouncement.value = {
    ...announcement,
    loading: true
  }
  showDetailModal.value = true

  // 标记为已读
  if (!readAnnouncementIds.value.includes(announcement.id)) {
    readAnnouncementIds.value.push(announcement.id)
    localStorage.setItem('read_announcement_ids', JSON.stringify(readAnnouncementIds.value))
  }

  // 获取完整公告详情并增加浏览次数
  try {
    const detailData = await api.announcement.detail(announcement.id)
    currentAnnouncement.value = detailData
  } catch (error) {
    console.error('获取公告详情失败:', error)
    currentAnnouncement.value.loading = false
  }
}

// 格式化日期
const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 监听路由变化，判断是否显示按钮
watch(() => route.path, (newPath) => {
  showButton.value = !newPath.startsWith('/admin')
})

onMounted(() => {
  showButton.value = !isAdminRoute.value
  fetchAnnouncements()
})
</script>

<style scoped>
.announcement-button-container {
  position: fixed;
  bottom: 30px;
  right: 30px;
  z-index: 999;
}

.announcement-button {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  background: var(--text-primary);
  color: #fbf7ef;
  border: 1px solid var(--text-primary);
  border-radius: 4px;
  cursor: pointer;
  box-shadow: 7px 7px 0 rgba(24, 23, 19, 0.12);
  transition: all 0.2s ease;
  font-size: 16px;
  font-weight: 850;
}

.announcement-button:hover {
  transform: translateY(-2px);
  box-shadow: 9px 9px 0 rgba(24, 23, 19, 0.14);
}

.announcement-button:active {
  transform: translateY(0);
}

.announcement-button.has-urgent {
  background: var(--primary-color);
  border-color: var(--primary-color);
}

.announcement-button.pulse {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% {
    box-shadow: 7px 7px 0 rgba(24, 23, 19, 0.12);
  }
  50% {
    box-shadow: 7px 7px 0 rgba(183, 53, 45, 0.28);
  }
}

.button-icon {
  font-size: 18px;
}

.button-text {
  font-size: 14px;
}

.badge {
  position: absolute;
  top: -5px;
  right: -5px;
  background: var(--secondary-color);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: bold;
  padding: 4px 8px;
  border-radius: 2px;
  min-width: 20px;
  text-align: center;
}

/* 弹窗样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: rgba(255, 250, 242, 0.98);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-large {
  max-width: 800px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h3 {
  margin: 0;
  font-size: 20px;
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
  transition: color 0.2s;
}

.close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

/* 列表样式 */
.announcement-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.announcement-item {
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.announcement-item:hover {
  border-color: var(--primary-color);
  box-shadow: 6px 6px 0 rgba(24, 23, 19, 0.08);
}

.announcement-item.unread {
  background: rgba(183, 53, 45, 0.08);
  border-color: var(--primary-color);
}

.announcement-item.urgent {
  border-left: 4px solid var(--primary-color);
}

.announcement-item.important {
  border-left: 4px solid var(--secondary-color);
}

.announcement-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.priority-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 850;
  flex-shrink: 0;
}

.priority-badge.high {
  background: rgba(183, 53, 45, 0.12);
  color: var(--primary-color);
}

.priority-badge.medium {
  background: rgba(239, 196, 107, 0.32);
  color: #785313;
}

.priority-badge.low {
  background: var(--bg-paper-2);
  color: var(--text-secondary);
}

.priority-badge.large {
  font-size: 14px;
  padding: 6px 12px;
}

.pinned-badge {
  font-size: 14px;
}

.unread-dot {
  width: 8px;
  height: 8px;
  background: var(--primary-color);
  border-radius: 50%;
  flex-shrink: 0;
}

.announcement-title {
  margin: 0 0 8px;
  font-size: 16px;
  color: var(--text-primary);
  line-height: 1.5;
}

.announcement-summary {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.announcement-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #999;
}

/* 详情样式 */
.announcement-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-title {
  margin: 0;
  font-size: 24px;
  color: var(--text-primary);
  flex: 1;
}

.detail-meta {
  display: flex;
  gap: 20px;
  font-size: 14px;
  color: #999;
  flex-wrap: wrap;
}

.detail-content {
  padding: 20px;
  background: var(--bg-paper-2);
  border-radius: 6px;
}

.content-text {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: inherit;
  line-height: 1.8;
  color: var(--text-primary);
}

/* 加载和空状态 */
.loading-state,
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #999;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid var(--primary-color);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .announcement-button-container {
    bottom: 20px;
    right: 20px;
  }

  .announcement-button {
    padding: 10px 16px;
    font-size: 14px;
  }

  .modal-content {
    max-width: 95%;
    max-height: 90vh;
  }

  .detail-title {
    font-size: 20px;
  }
}
</style>
