<template>
  <div class="resource-modal" @click.self="handleClose">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal-container">
        <button class="close-btn" @click="handleClose">✕</button>

        <div v-if="loading" class="modal-loading">
          <div class="loading-spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else class="modal-content">
          <div class="resource-section">
            <div class="resource-header">
              <div class="resource-cover-large">
                <img v-if="resource?.cover_url" :src="resource.cover_url" />
                <div v-else class="cover-placeholder-large">{{ typeIcon }}</div>
              </div>
              <div class="resource-info">
                <h1 class="resource-title">{{ resource?.title }}</h1>
                <div class="resource-badges">
                  <span class="badge" :class="`type-${resource?.resource_type}`">
                    {{ resource?.resource_type_display }}
                  </span>
                  <span class="badge badge-primary">{{ resource?.category }}</span>
                </div>
                <div class="uploader-section">
                  <span class="uploader-avatar">{{ resource?.uploader_info?.username?.charAt(0) }}</span>
                  <div class="uploader-details">
                    <div class="uploader-name">{{ resource?.uploader_info?.username }}</div>
                    <div class="upload-time">{{ formatDate(resource?.created_at) }}</div>
                  </div>
                </div>
              </div>
            </div>

            <div class="resource-description">
              <h2>📝 资源描述</h2>
              <div class="description-content">{{ resource?.description }}</div>
            </div>

            <div class="resource-stats">
              <div class="stat-item">
                <span class="stat-icon">👁️</span>
                <span class="stat-value">{{ resource?.view_count }}</span>
                <span class="stat-label">查看</span>
              </div>
              <div class="stat-item">
                <span class="stat-icon">⬇️</span>
                <span class="stat-value">{{ resource?.download_count }}</span>
                <span class="stat-label">下载</span>
              </div>
              <div class="stat-item">
                <span class="stat-icon">📦</span>
                <span class="stat-value">{{ formatFileSize(resource?.file_size) }}</span>
                <span class="stat-label">大小</span>
              </div>
            </div>
          </div>

          <div class="action-section">
            <button class="btn btn-primary btn-large" @click="handleDownload" :disabled="downloading">
              {{ downloading ? '准备下载...' : '📥 下载资源' }}
            </button>
            <button class="btn btn-secondary btn-large" @click="togglePreview" :disabled="!canPreview">
              {{ showPreview ? '🔽 收起预览' : '👁️ 预览资源' }}
            </button>
            <div v-if="message" class="download-message" :class="messageType">{{ message }}</div>

            <!-- 预览区域 -->
            <div v-if="showPreview && canPreview" class="preview-section">
              <div class="preview-header">
                <h3>资源预览</h3>
              </div>
              <div class="preview-content">
                <!-- 图片预览 -->
                <div v-if="resource?.resource_type === 'document' && isImageFile" class="preview-image">
                  <img :src="resource.file_url" :alt="resource.title" @error="handlePreviewError" />
                </div>

                <!-- 视频预览 -->
                <div v-else-if="resource?.resource_type === 'video'" class="preview-video">
                  <video controls :src="resource.file_url" preload="metadata" @error="handlePreviewError">
                    您的浏览器不支持视频播放
                  </video>
                </div>

                <!-- 文档预览提示 -->
                <div v-else-if="resource?.resource_type === 'document' && !isImageFile" class="preview-placeholder">
                  <div class="placeholder-icon">📄</div>
                  <p>此文档类型暂不支持在线预览</p>
                  <p class="placeholder-tip">请下载后使用相应软件查看</p>
                </div>

                <!-- 压缩包预览提示 -->
                <div v-else-if="resource?.resource_type === 'zip'" class="preview-placeholder">
                  <div class="placeholder-icon">📦</div>
                  <p>压缩包无法在线预览</p>
                  <p class="placeholder-tip">请下载后解压查看内容</p>
                </div>

                <!-- 报告预览提示 -->
                <div v-else-if="resource?.resource_type === 'report'" class="preview-placeholder">
                  <div class="placeholder-icon">📊</div>
                  <p>报告暂不支持在线预览</p>
                  <p class="placeholder-tip">请下载后查看完整内容</p>
                </div>

                <!-- 加载失败 -->
                <div v-else-if="previewError" class="preview-placeholder error">
                  <div class="placeholder-icon">❌</div>
                  <p>预览加载失败</p>
                  <p class="placeholder-tip">{{ previewError }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '@/api'

const props = defineProps({
  resourceId: {
    type: Number,
    required: true
  }
})

const emit = defineEmits(['close'])

const resource = ref(null)
const loading = ref(false)
const downloading = ref(false)
const message = ref('')
const messageType = ref('')
const showPreview = ref(false)
const previewError = ref('')

const typeIcon = computed(() => {
  const icons = { 'document': '📄', 'video': '🎬', 'report': '📊', 'zip': '📦' }
  return icons[resource.value?.resource_type] || '📁'
})

const isImageFile = computed(() => {
  if (!resource.value?.file_name) return false
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']
  const fileName = resource.value.file_name.toLowerCase()
  return imageExtensions.some(ext => fileName.endsWith(ext))
})

const canPreview = computed(() => {
  if (!resource.value) return false
  const type = resource.value.resource_type
  // 视频和图片可以预览
  if (type === 'video' || (type === 'document' && isImageFile.value)) {
    return true
  }
  return false
})

const fetchResource = async () => {
  loading.value = true
  try {
    resource.value = await api.resource.detail(props.resourceId)
  } catch (error) {
    console.error('获取资源详情失败:', error)
    message.value = '获取资源失败'
    messageType.value = 'error'
  } finally {
    loading.value = false
  }
}

const handleClose = () => emit('close')

const togglePreview = () => {
  showPreview.value = !showPreview.value
  previewError.value = ''
  if (showPreview.value) {
    // 增加查看次数
    resource.value?.increment_view_count?.()
  }
}

const handlePreviewError = (event) => {
  previewError.value = '预览资源加载失败，请稍后重试'
  console.error('预览加载失败:', event)
}

const handleDownload = async () => {
  if (!resource.value) return
  downloading.value = true
  message.value = ''
  try {
    const result = await api.resource.download(props.resourceId)
    message.value = '下载链接已生成'
    messageType.value = 'success'
    const link = document.createElement('a')
    link.href = result.file_url
    link.download = result.file_name
    link.target = '_blank'
    link.click()
  } catch (error) {
    message.value = '下载失败，请稍后重试'
    messageType.value = 'error'
  } finally {
    downloading.value = false
  }
}

const formatDate = (dateStr) => dateStr ? new Date(dateStr).toLocaleString('zh-CN') : ''

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i]
}

watch(() => props.resourceId, (newId) => {
  if (newId) {
    message.value = ''
    messageType.value = ''
    fetchResource()
  }
}, { immediate: true })
</script>

<style scoped>
.resource-modal { position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 2000; }
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.modal-container {
  width: 100%; max-width: 900px; max-height: 90vh;
  background: white; border-radius: 16px; overflow: hidden; position: relative;
}
.modal-loading { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 400px; gap: 16px; }
.loading-spinner {
  width: 48px; height: 48px; border: 4px solid #f0f0f0;
  border-top-color: var(--primary-color); border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.close-btn {
  position: absolute; top: 16px; right: 16px; width: 36px; height: 36px;
  border: none; background: rgba(0,0,0,0.05); border-radius: 50%;
  font-size: 20px; cursor: pointer; z-index: 10;
}
.modal-content { display: grid; grid-template-columns: 1fr 280px; height: 90vh; overflow: hidden; }
.resource-section { padding: 32px; overflow-y: auto; }
.resource-header { display: grid; grid-template-columns: 200px 1fr; gap: 24px; margin-bottom: 24px; padding-bottom: 24px; border-bottom: 2px solid #f0f0f0; }
.resource-cover-large { width: 200px; height: 150px; border-radius: 12px; overflow: hidden; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.resource-cover-large img { width: 100%; height: 100%; object-fit: cover; }
.cover-placeholder-large { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 48px; }
.resource-info { display: flex; flex-direction: column; gap: 12px; }
.resource-title { font-size: 24px; font-weight: bold; }
.resource-badges { display: flex; flex-wrap: wrap; gap: 8px; }
.badge { padding: 4px 12px; border-radius: 12px; font-size: 12px; color: white; }
.type-document { background: rgba(24, 144, 255, 0.9); }
.type-video { background: rgba(250, 84, 28, 0.9); }
.type-report { background: rgba(82, 196, 26, 0.9); }
.type-zip { background: rgba(114, 46, 209, 0.9); }
.badge-primary { background: var(--primary-color); }
.uploader-section { display: flex; align-items: center; gap: 12px; padding: 12px; background: #f9f9f9; border-radius: 8px; }
.uploader-avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--primary-color); display: flex; align-items: center; justify-content: center; }
.resource-description { margin-bottom: 24px; }
.description-content { font-size: 15px; line-height: 1.8; padding: 20px; background: #fafafa; border-radius: 8px; border-left: 4px solid var(--primary-color); white-space: pre-wrap; }
.resource-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; padding: 20px; background: #f9f9f9; border-radius: 12px; }
.stat-item { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 16px; background: white; border-radius: 8px; }
.stat-icon { font-size: 32px; }
.stat-value { font-size: 24px; font-weight: bold; color: var(--primary-color); }
.stat-label { font-size: 12px; color: var(--text-secondary); }
.action-section { padding: 32px; background: #fafafa; display: flex; flex-direction: column; gap: 16px; }
.btn-large { width: 100%; padding: 16px; font-size: 16px; }
.btn-secondary {
  background: white;
  border: 2px solid var(--primary-color);
  color: var(--primary-color);
}
.btn-secondary:hover:not(:disabled) {
  background: var(--primary-color);
  color: white;
}
.btn-secondary:disabled {
  border-color: #d9d9d9;
  color: #d9d9d9;
  cursor: not-allowed;
}
.download-message { padding: 12px 16px; border-radius: 8px; font-size: 14px; }
.download-message.success { background: #f6ffed; color: #52c41a; }
.download-message.error { background: #fff1f0; color: #ff4d4f; }

/* 预览区域 */
.preview-section {
  margin-top: 16px;
  padding: 20px;
  background: white;
  border-radius: 12px;
  border: 1px solid #e8e8e8;
}
.preview-header {
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}
.preview-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}
.preview-content {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  max-height: 400px;
  overflow: auto;
}
.preview-image img {
  max-width: 100%;
  max-height: 400px;
  object-fit: contain;
  border-radius: 8px;
}
.preview-video video {
  max-width: 100%;
  max-height: 400px;
  border-radius: 8px;
  background: #000;
}
.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  color: #999;
}
.placeholder-icon {
  font-size: 64px;
  opacity: 0.5;
}
.preview-placeholder p {
  margin: 0;
  font-size: 14px;
}
.placeholder-tip {
  font-size: 12px;
  color: #ccc;
}
.preview-placeholder.error {
  color: #ff4d4f;
}
.preview-placeholder.error .placeholder-icon {
  opacity: 1;
}
</style>
