<template>
  <div class="resource-modal" @click.self="handleClose">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal-container" :class="{ 'ai-modal-container': resource?.resource_type === 'ai_resource' }">
        <button class="close-btn" @click="handleClose">✕</button>

        <div v-if="loading" class="modal-loading">
          <div class="loading-spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else class="modal-content" :class="{ 'ai-modal-content': resource?.resource_type === 'ai_resource' }">
          <div class="resource-section">
            <div class="resource-header">
              <div class="resource-cover-large">
                <img v-if="resource?.cover_url" :src="resource.cover_url" />
                <div v-else class="cover-placeholder-large">{{ typeIcon }}</div>
              </div>
              <div class="resource-info">
                <h1 class="resource-title">{{ resource?.title }}</h1>
                <div class="resource-badges">
                  <span class="badge" :class="typeBadgeClass">
                    {{ typeLabel }}
                  </span>
                  <span class="badge badge-primary">{{ resource?.category }}</span>
                </div>
                <div class="uploader-section">
                  <span class="uploader-avatar">{{ displayUploaderInitial }}</span>
                  <div class="uploader-details">
                    <div class="uploader-name">{{ displayUploaderName }}</div>
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

                <!-- AI 资源 Markdown 预览 -->
                <div v-else-if="resource?.resource_type === 'ai_resource'" class="ai-resource-preview">
                  <p v-if="previewLoading" class="preview-loading">正在读取资源内容…</p>
                  <div v-else-if="previewError" class="preview-placeholder error">
                    <div class="placeholder-icon">❌</div>
                    <p>预览加载失败</p>
                    <p class="placeholder-tip">{{ previewError }}</p>
                  </div>
                  <figure v-else-if="isMindMap && resource?.cover_url" class="mindmap-preview">
                    <a :href="resource.cover_url" target="_blank" rel="noopener"><img :src="resource.cover_url" :alt="`${resource.title} 思维导图`" /></a>
                    <figcaption>点击图片可在浏览器中放大查看</figcaption>
                  </figure>
                  <article v-else class="markdown-preview" v-html="previewHtml"></article>
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
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import api from '@/api'

const props = defineProps({
  resourceId: {
    type: Number,
    required: true
  },
  highlightResourceId: {
    type: [Number, String],
    default: null
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
const previewLoading = ref(false)
const previewMarkdown = ref('')

const highlightParams = computed(() => props.highlightResourceId
  ? { highlight_resource: props.highlightResourceId }
  : undefined)

const typeIcon = computed(() => {
  const icons = { 'document': '📄', 'video': '🎬', 'report': '📊', 'zip': '📦', 'ai_resource': '✨' }
  return icons[resource.value?.resource_type] || '📁'
})

const isAIHighlighted = computed(() => Boolean(
  resource.value?.is_ai_highlighted || resource.value?.ai_generated_label
))

const typeLabel = computed(() => {
  if (isAIHighlighted.value) return 'AI推荐多模态资料'
  return resource.value?.resource_type === 'ai_resource'
    ? 'AI资源'
    : resource.value?.resource_type_display
})

const typeBadgeClass = computed(() => isAIHighlighted.value
  ? 'type-ai-recommended'
  : 'type-' + resource.value?.resource_type)

const displayUploaderName = computed(() => isAIHighlighted.value
  ? 'AI教学辅导师'
  : (resource.value?.uploader_info?.username || '未知'))

const displayUploaderInitial = computed(() => isAIHighlighted.value
  ? 'AI'
  : (displayUploaderName.value?.charAt(0) || 'U'))

const isMindMap = computed(() => resource.value?.tags_list?.includes('思维导图'))

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
  if (type === 'ai_resource' || type === 'video' || (type === 'document' && isImageFile.value)) {
    return true
  }
  return false
})

const previewHtml = computed(() => DOMPurify.sanitize(marked.parse(previewMarkdown.value || '暂无可预览内容。')))

const fetchResource = async () => {
  loading.value = true
  try {
    resource.value = await api.resource.detail(props.resourceId, highlightParams.value)
    if (resource.value?.resource_type === 'ai_resource') {
      showPreview.value = true
      await loadAiPreview()
    }
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
    if (resource.value?.resource_type === 'ai_resource' && !previewMarkdown.value) loadAiPreview()
  }
}

const loadAiPreview = async () => {
  previewLoading.value = true
  try {
    const response = await api.resource.download(props.resourceId, highlightParams.value)
    previewMarkdown.value = await response.data.text()
  } catch (error) {
    previewError.value = '无法读取资源内容，请稍后重试'
    console.error('AI 资源预览加载失败:', error)
  } finally {
    previewLoading.value = false
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
    const response = await api.resource.download(props.resourceId, highlightParams.value)
    const contentDisposition = response.headers['content-disposition'] || ''
    const fileNameMatch = contentDisposition.match(/filename\*?=(?:UTF-8''|\")?([^;\"]+)/i)
    const fileName = fileNameMatch
      ? decodeURIComponent(fileNameMatch[1].trim())
      : resource.value.file_name || 'resource-download'
    const url = URL.createObjectURL(response.data)
    message.value = '下载链接已生成'
    messageType.value = 'success'
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
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

watch([() => props.resourceId, () => props.highlightResourceId], ([newId]) => {
  if (newId) {
    message.value = ''
    messageType.value = ''
    previewMarkdown.value = ''
    previewError.value = ''
    showPreview.value = false
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
.type-ai_resource { background: rgba(109, 74, 160, 0.9); }
.type-ai-recommended {
  max-width: 100%;
  background: #ead0d4;
  color: #5f3c45;
  border: 1px solid rgba(95, 60, 69, 0.18);
  white-space: normal;
  text-align: center;
}
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
.ai-resource-preview { width: 100%; align-self: stretch; }
.preview-loading { margin: 0; padding: 24px; text-align: center; color: var(--text-secondary); }
.markdown-preview { width: 100%; padding: 4px 8px; color: #2f2a23; line-height: 1.75; }
.markdown-preview :deep(h1), .markdown-preview :deep(h2), .markdown-preview :deep(h3) { margin: 18px 0 8px; color: #1e1c18; }
.markdown-preview :deep(h1) { font-size: 22px; }
.markdown-preview :deep(h2) { font-size: 18px; }
.markdown-preview :deep(p) { margin: 8px 0; }
.markdown-preview :deep(ul), .markdown-preview :deep(ol) { padding-left: 22px; }
.markdown-preview :deep(pre) { margin: 14px 0; padding: 14px; overflow: auto; border-radius: 6px; background: #1e2b38; color: #f4f1eb; }
.markdown-preview :deep(code) { padding: 2px 4px; border-radius: 3px; background: #eee5d8; font-family: Consolas, monospace; }
.markdown-preview :deep(pre code) { padding: 0; background: transparent; }
.mindmap-preview { margin: 0; text-align: center; }
.mindmap-preview img { display: block; width: 100%; max-width: 1120px; height: auto; cursor: zoom-in; border: 1px solid #ded3c2; border-radius: 8px; background: #fff; }
.mindmap-preview figcaption { margin-top: 10px; color: #786f64; font-size: 13px; }

/* AI 资源使用完整阅读页，不复用普通资源的窄侧栏。 */
.ai-modal-container { max-width: min(1180px, 96vw); max-height: 94vh; }
.ai-modal-content { display: flex; flex-direction: column; height: 94vh; background: #fffaf2; }
.ai-modal-content .resource-section { flex: 0 0 auto; overflow: visible; padding: 30px 54px 0; }
.ai-modal-content .resource-header { grid-template-columns: 74px 1fr; gap: 18px; margin: 0; padding-bottom: 20px; }
.ai-modal-content .resource-cover-large { width: 74px; height: 74px; border-radius: 8px; }
.ai-modal-content .cover-placeholder-large { font-size: 30px; }
.ai-modal-content .resource-info { gap: 8px; }
.ai-modal-content .resource-title { padding-right: 42px; font-size: 30px; font-weight: 900; letter-spacing: -.03em; }
.ai-modal-content .uploader-section { display: none; }
.ai-modal-content .resource-description,
.ai-modal-content .resource-stats { display: none; }
.ai-modal-content .action-section { flex: 1; min-height: 0; padding: 18px 54px 44px; overflow: auto; background: transparent; }
.ai-modal-content .btn-large { width: auto; min-width: 132px; margin-right: 10px; padding: 10px 16px; font-size: 14px; }
.ai-modal-content .btn-secondary { display: none; }
.ai-modal-content .preview-section { margin: 18px 0 0; padding: 0; border: 0; border-radius: 0; background: transparent; }
.ai-modal-content .preview-header { display: flex; align-items: center; min-height: 42px; margin: 0; padding: 0 0 12px; border-bottom: 1px solid #ded3c2; }
.ai-modal-content .preview-header h3 { color: #6b6256; font-size: 13px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.ai-modal-content .preview-content { display: block; min-height: auto; max-height: none; overflow: visible; }
.ai-modal-content .ai-resource-preview { max-width: 900px; margin: 0 auto; padding: 34px 42px 56px; border: 1px solid #ded3c2; border-radius: 8px; background: #fffdf8; }
.ai-modal-content .markdown-preview { font-size: 16px; line-height: 1.9; }
.ai-modal-content .markdown-preview :deep(h1) { margin-top: 0; padding-bottom: 16px; border-bottom: 2px solid #b42318; font-size: 30px; }
.ai-modal-content .markdown-preview :deep(h2) { margin-top: 34px; color: #7d241b; }
.ai-modal-content .markdown-preview :deep(h3) { margin-top: 24px; }
.ai-modal-content .markdown-preview :deep(li) { margin: 7px 0; }
.ai-modal-content .markdown-preview :deep(pre) { padding: 20px; font-size: 14px; }
.ai-modal-content .mindmap-preview { max-width: 1080px; margin: 0 auto; padding: 18px; border: 1px solid #ded3c2; border-radius: 8px; background: #fffdf8; }

@media (max-width: 700px) {
  .ai-modal-container { max-width: 100%; max-height: 100vh; border-radius: 0; }
  .ai-modal-content { height: 100vh; }
  .ai-modal-content .resource-section { padding: 24px 22px 0; }
  .ai-modal-content .action-section { padding: 16px 22px 32px; }
  .ai-modal-content .ai-resource-preview { padding: 24px 20px 36px; }
  .ai-modal-content .resource-title { font-size: 24px; }
}
</style>
