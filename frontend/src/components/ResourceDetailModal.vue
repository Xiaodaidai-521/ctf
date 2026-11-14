<template>
  <div class="resource-modal" @click.self="handleClose">
    <div class="modal-overlay" @click.self="handleClose">
      <div class="modal-container" :class="{ 'ai-modal-container': resource?.resource_type === 'ai_resource' }" role="dialog" aria-modal="true" :aria-label="resource?.title || '资源详情'" :aria-busy="loading">
        <div class="modal-toolbar">
          <span>资源详情</span>
          <button class="close-btn" @click="handleClose" aria-label="关闭资源详情"><icon-close aria-hidden="true" /></button>
        </div>

        <div v-if="loading" class="modal-loading" role="status">
          <icon-loading class="loading-icon" aria-hidden="true" />
          <p>加载中...</p>
        </div>

        <div v-else class="modal-content" :class="{ 'ai-modal-content': resource?.resource_type === 'ai_resource' }">
          <div class="resource-section">
            <div class="resource-header">
              <div class="resource-cover-large">
                <img v-if="resource?.cover_url" :src="resource.cover_url" :alt="resource.title" />
                <div v-else class="cover-placeholder-large"><component :is="typeIcon" aria-hidden="true" /></div>
              </div>
              <div class="resource-info">
                <h1 class="resource-title">{{ resource?.title }}</h1>
                <div class="resource-badges">
                  <span class="badge" :class="typeBadgeClass">{{ typeLabel }}</span>
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
              <h2><icon-file aria-hidden="true" /> 资源描述</h2>
              <div class="description-content">{{ resource?.description }}</div>
            </div>

            <div class="resource-stats">
              <div class="stat-item">
                <icon-eye aria-hidden="true" />
                <span class="stat-label">查看</span>
                <span class="stat-value">{{ resource?.view_count }}</span>
              </div>
              <div class="stat-item">
                <icon-download aria-hidden="true" />
                <span class="stat-label">下载</span>
                <span class="stat-value">{{ resource?.download_count }}</span>
              </div>
              <div class="stat-item">
                <icon-storage aria-hidden="true" />
                <span class="stat-label">大小</span>
                <span class="stat-value">{{ formatFileSize(resource?.file_size) }}</span>
              </div>
            </div>
          </div>

          <div class="action-section">
            <div class="action-buttons">
              <button class="btn btn-primary btn-large" @click="handleDownload" :disabled="downloading" :aria-busy="downloading">
                <icon-loading v-if="downloading" class="loading-icon" aria-hidden="true" />
                <icon-download v-else aria-hidden="true" />
                {{ downloading ? '准备下载...' : '下载资源' }}
              </button>
              <button class="btn btn-secondary btn-large" @click="togglePreview" :disabled="!canPreview" :aria-expanded="showPreview && canPreview">
                <icon-up v-if="showPreview" aria-hidden="true" />
                <icon-eye v-else aria-hidden="true" />
                {{ showPreview ? '收起预览' : '预览资源' }}
              </button>
            </div>
            <p v-if="resource && !canPreview" class="preview-unavailable">此类资源暂不支持在线预览，请下载后查看。</p>
            <div v-if="message" class="download-message" :class="messageType" :role="messageType === 'error' ? 'alert' : 'status'">
              <component :is="messageType === 'success' ? 'icon-check-circle' : 'icon-exclamation-circle'" aria-hidden="true" />
              {{ message }}
            </div>
            <ProtectionBadge :status="resource?.protection?.file" label="文件已加密保存" />
            <ProtectionBadge :status="resource?.protection?.cover_image" label="封面已加密保存" />

            <div v-if="showPreview && canPreview" class="preview-section">
              <div class="preview-header"><h3>资源预览</h3></div>
              <div class="preview-content" :aria-busy="previewLoading">
                <div v-if="previewError" class="preview-placeholder error" role="alert">
                  <icon-exclamation-circle class="placeholder-icon" aria-hidden="true" />
                  <p>预览加载失败</p>
                  <p class="placeholder-tip">{{ previewError }}</p>
                </div>

                <!-- 保留原预览类型与加载事件；错误提示在所有类型中可见。 -->
                <div v-if="resource?.resource_type === 'document' && isImageFile" class="preview-image">
                  <img :key="resource.file_url" :src="resource.file_url" :alt="resource.title" @error="handlePreviewError" />
                </div>
                <div v-else-if="resource?.resource_type === 'video'" class="preview-video">
                  <video :key="resource.file_url" controls :src="resource.file_url" preload="metadata" @error="handlePreviewError">您的浏览器不支持视频播放</video>
                </div>
                <div v-else-if="resource?.resource_type === 'ai_resource'" class="ai-resource-preview">
                  <p v-if="previewLoading" class="preview-loading" role="status"><icon-loading class="loading-icon" aria-hidden="true" /> 正在读取资源内容…</p>
                  <template v-else-if="!previewError">
                    <figure v-if="isMindMap && resource?.cover_url" class="mindmap-preview">
                      <a :href="resource.cover_url" target="_blank" rel="noopener"><img :src="resource.cover_url" :alt="`${resource.title} 思维导图`" /></a>
                      <figcaption>点击图片可在浏览器中放大查看</figcaption>
                    </figure>
                    <article v-else class="markdown-preview" v-html="previewHtml"></article>
                  </template>
                </div>
                <div v-else-if="resource?.resource_type === 'document' && !isImageFile" class="preview-placeholder">
                  <icon-file class="placeholder-icon" aria-hidden="true" />
                  <p>此文档类型暂不支持在线预览</p>
                  <p class="placeholder-tip">请下载后使用相应软件查看</p>
                </div>
                <div v-else-if="resource?.resource_type === 'zip'" class="preview-placeholder">
                  <icon-storage class="placeholder-icon" aria-hidden="true" />
                  <p>压缩包无法在线预览</p>
                  <p class="placeholder-tip">请下载后解压查看内容</p>
                </div>
                <div v-else-if="resource?.resource_type === 'report'" class="preview-placeholder">
                  <icon-file class="placeholder-icon" aria-hidden="true" />
                  <p>报告暂不支持在线预览</p>
                  <p class="placeholder-tip">请下载后查看完整内容</p>
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
import ProtectionBadge from '@/shared/privacy/ProtectionBadge.vue'
import { ref, computed, watch, onBeforeUnmount } from 'vue'
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
let requestVersion = 0
let previewVersion = 0

const highlightParams = computed(() => props.highlightResourceId
  ? { highlight_resource: props.highlightResourceId }
  : undefined)

const typeIcon = computed(() => {
  const icons = { 'document': 'icon-file', 'video': 'icon-file-video', 'report': 'icon-bar-chart', 'zip': 'icon-storage', 'ai_resource': 'icon-robot' }
  return icons[resource.value?.resource_type] || 'icon-folder'
})

const isAIHighlighted = computed(() => Boolean(
  resource.value?.is_ai_highlighted || resource.value?.ai_generated_label
))

const typeLabel = computed(() => {
  if (isAIHighlighted.value) return '导学推荐资料'
  return resource.value?.resource_type === 'ai_resource'
    ? 'AI资源'
    : resource.value?.resource_type_display
})

const typeBadgeClass = computed(() => isAIHighlighted.value
  ? 'type-ai-recommended'
  : 'type-' + resource.value?.resource_type)

const displayUploaderName = computed(() => resource.value?.uploader_info?.username || '上传者暂不可用')
const displayUploaderInitial = computed(() => displayUploaderName.value.charAt(0))

const isMindMap = computed(() => resource.value?.tags_list?.includes('思维导图'))

const isImageFile = computed(() => {
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
  if (resource.value?.file_type) return imageExtensions.includes(resource.value.file_type.toLowerCase())
  const fileName = resource.value?.file_name?.toLowerCase() || ''
  return imageExtensions.some(ext => fileName.endsWith(ext))
})

const canPreview = computed(() => {
  if (!resource.value?.file_url) return false
  const type = resource.value.resource_type
  // 视频和图片可以预览
  if (type === 'ai_resource' || type === 'video' || (type === 'document' && isImageFile.value)) {
    return true
  }
  return false
})

const previewHtml = computed(() => DOMPurify.sanitize(marked.parse(previewMarkdown.value || '暂无可预览内容。')))

const fetchResource = async () => {
  const version = requestVersion
  const id = props.resourceId
  const params = highlightParams.value
  loading.value = true
  try {
    const detail = await api.resource.detail(id, params)
    if (version !== requestVersion) return
    resource.value = detail
    if (resource.value?.resource_type === 'ai_resource') {
      showPreview.value = true
      await loadAiPreview()
    }
  } catch (error) {
    if (version !== requestVersion) return
    console.error('获取资源详情失败:', error)
    message.value = '获取资源失败'
    messageType.value = 'error'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

const invalidateRequests = () => { requestVersion++; previewVersion++ }
const handleClose = () => { invalidateRequests(); emit('close') }
onBeforeUnmount(invalidateRequests)

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
  const version = requestVersion
  const preview = ++previewVersion
  const id = resource.value?.id
  const params = highlightParams.value
  const current = () => version === requestVersion && preview === previewVersion && resource.value?.id === id
  previewLoading.value = true
  try {
    const response = await api.resource.download(id, params)
    if (!current()) return
    const text = await response.data.text()
    if (current()) previewMarkdown.value = text
  } catch (error) {
    if (!current()) return
    previewError.value = '无法读取资源内容，请稍后重试'
    console.error('AI 资源预览加载失败:', error)
  } finally {
    if (current()) previewLoading.value = false
  }
}

const handlePreviewError = (event) => {
  previewError.value = '预览资源加载失败，请稍后重试'
  console.error('预览加载失败:', event)
}

const handleDownload = async () => {
  if (!resource.value) return
  const version = requestVersion
  const currentResource = resource.value
  downloading.value = true
  message.value = ''
  try {
    const response = await api.resource.download(currentResource.id, highlightParams.value)
    if (version !== requestVersion) return
    const contentDisposition = response.headers['content-disposition'] || ''
    const fileNameMatch = contentDisposition.match(/filename\*?=(?:UTF-8''|\")?([^;\"]+)/i)
    const fileName = fileNameMatch
      ? decodeURIComponent(fileNameMatch[1].trim())
      : currentResource.file_name || 'resource-download'
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
    if (version !== requestVersion) return
    message.value = '下载失败，请稍后重试'
    messageType.value = 'error'
  } finally {
    if (version === requestVersion) downloading.value = false
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
  invalidateRequests()
  resource.value = null
  loading.value = false
  previewLoading.value = false
  downloading.value = false
  message.value = ''
  messageType.value = ''
  previewMarkdown.value = ''
  previewError.value = ''
  showPreview.value = false
  if (newId) {
    fetchResource()
  }
}, { immediate: true })
</script>

<style scoped>
.resource-modal { position: fixed; inset: 0; z-index: 2000; /* Preserve the existing modal stacking layer. */ color: var(--ink); font-family: var(--font-family); font-size: var(--text-body); line-height: var(--leading-body); }
.resource-modal *, .resource-modal *::before, .resource-modal *::after { box-sizing: border-box; }
.modal-overlay { position: fixed; inset: 0; display: flex; align-items: center; justify-content: center; padding: var(--space-3); background: var(--overlay); }
.modal-container { display: flex; flex-direction: column; width: 100%; max-width: var(--reading-width); max-height: calc(100vh - var(--space-6)); max-height: calc(100dvh - var(--space-6)); overflow: hidden; background: var(--surface); border-radius: var(--radius-panel); box-shadow: var(--shadow-overlay); }
.modal-toolbar { display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; gap: var(--space-2); padding: var(--space-1) var(--space-3); border-bottom: var(--stroke) solid var(--line); color: var(--ink-secondary); font-size: var(--text-caption); }
.modal-loading { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: calc(var(--space-10) * 3); padding: var(--space-3); gap: var(--space-2); color: var(--ink-secondary); }
.modal-loading p { margin: 0; }
.modal-content { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, var(--menu-width)); min-height: 0; overflow: auto; overscroll-behavior: contain; }
.resource-section, .action-section { min-width: 0; padding: var(--space-3); overflow-wrap: anywhere; }
.resource-header { display: grid; grid-template-columns: calc(var(--space-8) * 2) minmax(0, 1fr); gap: var(--space-2); margin-bottom: var(--space-3); padding-bottom: var(--space-3); border-bottom: var(--stroke) solid var(--line); }
.resource-cover-large { width: 100%; aspect-ratio: 1; border-radius: var(--radius-control); overflow: hidden; background: var(--surface-muted); color: var(--ink-secondary); }
.resource-cover-large img { width: 100%; height: 100%; object-fit: cover; }
.cover-placeholder-large { width: 100%; height: 100%; display: grid; place-items: center; }
.cover-placeholder-large .arco-icon { font-size: var(--text-page); }
.resource-info { display: flex; flex-direction: column; min-width: 0; gap: var(--space-2); }
.resource-title { margin: 0; font-size: var(--text-section); font-weight: var(--weight-strong); line-height: var(--leading-tight); }
.resource-badges { display: flex; flex-wrap: wrap; gap: var(--space-1); }
.badge { max-width: 100%; padding: 0 var(--space-1); border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink-secondary); font-size: var(--text-caption); }
.type-ai_resource, .type-ai-recommended { background: var(--agent-soft); color: var(--agent-accent); }
.uploader-section { display: flex; align-items: center; gap: var(--space-1); font-size: var(--text-caption); color: var(--ink-secondary); }
.uploader-details { min-width: 0; }
.uploader-avatar { display: grid; place-items: center; width: var(--avatar-size); height: var(--avatar-size); flex-shrink: 0; border-radius: var(--radius-pill); background: var(--surface-muted); color: var(--ink-secondary); }
.resource-description { margin-bottom: var(--space-3); }
.resource-description h2 { display: flex; align-items: center; gap: var(--space-1); margin: 0 0 var(--space-2); font-size: var(--text-card); font-weight: var(--weight-strong); }
.description-content { white-space: pre-wrap; }
.resource-stats { display: flex; flex-wrap: wrap; gap: var(--space-2); padding-top: var(--space-2); border-top: var(--stroke) solid var(--line); }
.stat-item { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1); min-width: 0; font-size: var(--text-caption); }
.stat-item .arco-icon, .stat-label { color: var(--ink-secondary); }
.stat-value { color: var(--ink); font-weight: var(--weight-medium); font-variant-numeric: tabular-nums; }
.action-section { display: flex; flex-direction: column; gap: var(--space-2); background: var(--surface-muted); }
.action-buttons { display: flex; flex-direction: column; gap: var(--space-2); }
.btn, .close-btn { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; gap: var(--space-1); min-height: var(--control-height); padding: var(--space-1) var(--space-2); border: var(--stroke) solid var(--line-strong); border-radius: var(--radius-control); background: var(--surface); color: var(--ink); font: inherit; font-weight: var(--weight-medium); cursor: pointer; white-space: normal; text-align: center; transition: background var(--motion-fast) var(--motion-ease); }
.close-btn { width: var(--control-height); padding: var(--space-1); border-color: transparent; background: transparent; }
.btn:hover:not(:disabled), .close-btn:hover { background: var(--surface-hover); }
.btn:active:not(:disabled), .close-btn:active { background: var(--surface-muted); }
.btn-primary { border-color: var(--action); background: var(--action); color: var(--on-action); }
.btn-primary:hover:not(:disabled) { background: var(--action-hover); }
.btn-primary:active:not(:disabled) { background: var(--action-pressed); }
.btn:disabled { background: var(--disabled); color: var(--disabled-ink); border-color: var(--line); cursor: not-allowed; opacity: 1; }
button:focus-visible, a:focus-visible, video:focus-visible, .markdown-preview :deep(a:focus-visible) { outline: var(--focus-width) solid var(--action); outline-offset: var(--focus-offset); }
.download-message { display: flex; align-items: flex-start; gap: var(--space-1); padding: var(--space-2); border-radius: var(--radius-control); font-size: var(--text-caption); }
.download-message.success { background: var(--positive-soft); color: var(--positive); }
.download-message.error, .preview-placeholder.error { background: var(--negative-soft); color: var(--negative); }
.preview-unavailable, .placeholder-tip, .mindmap-preview figcaption { margin: 0; font-size: var(--text-caption); color: var(--ink-secondary); }
.preview-section { min-width: 0; margin-top: var(--space-2); }
.preview-header { margin-bottom: var(--space-2); padding-bottom: var(--space-2); border-bottom: var(--stroke) solid var(--line); }
.preview-header h3 { margin: 0; font-size: var(--text-card); font-weight: var(--weight-strong); }
.preview-content { min-width: 0; }
.preview-image img, .preview-video video { display: block; max-width: 100%; max-height: var(--message-width); border-radius: var(--radius-control); }
.preview-video video { width: 100%; background: var(--ink); }
.preview-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--space-1); padding: var(--space-2); border-radius: var(--radius-control); color: var(--ink-secondary); }
.preview-placeholder p { margin: 0; }
.preview-placeholder.error .placeholder-tip { color: inherit; }
.preview-loading { display: flex; align-items: center; gap: var(--space-1); margin: 0; padding-block: var(--space-2); color: var(--ink-secondary); }
.ai-resource-preview, .markdown-preview { min-width: 0; width: 100%; }
.markdown-preview { color: var(--ink); font-size: var(--text-body); }
.markdown-preview :deep(h1), .markdown-preview :deep(h2), .markdown-preview :deep(h3), .markdown-preview :deep(h4), .markdown-preview :deep(h5), .markdown-preview :deep(h6) { margin: var(--space-3) 0 var(--space-2); color: var(--ink); font-size: var(--text-card); line-height: var(--leading-tight); font-weight: var(--weight-strong); }
.markdown-preview :deep(h1) { font-size: var(--text-section); }
.markdown-preview :deep(p) { margin: var(--space-2) 0; }
.markdown-preview :deep(ul), .markdown-preview :deep(ol) { padding-left: var(--space-3); }
.markdown-preview :deep(li) { margin-block: var(--space-1); }
.markdown-preview :deep(a) { color: var(--action); text-decoration: underline; overflow-wrap: anywhere; }
.markdown-preview :deep(a:hover) { color: var(--action-hover); }
.markdown-preview :deep(pre) { max-width: 100%; margin: var(--space-2) 0; padding: var(--space-2); white-space: pre-wrap; overflow-wrap: anywhere; border-radius: var(--radius-control); background: var(--surface-muted); color: var(--ink); }
.markdown-preview :deep(code) { background: var(--surface-muted); border-radius: var(--radius-control); font-size: var(--text-caption); }
.markdown-preview :deep(pre code) { background: transparent; }
.markdown-preview :deep(table) { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; font-size: var(--text-caption); }
.markdown-preview :deep(th), .markdown-preview :deep(td) { padding: var(--space-1); border: var(--stroke) solid var(--line); text-align: left; }
.markdown-preview :deep(blockquote) { margin-inline: 0; padding-left: var(--space-2); border-left: var(--stroke) solid var(--line-strong); color: var(--ink-secondary); }
.markdown-preview :deep(img) { max-width: 100%; height: auto; }
.mindmap-preview { margin: 0; text-align: center; }
.mindmap-preview a { display: block; border-radius: var(--radius-control); }
.mindmap-preview img { display: block; width: 100%; height: auto; cursor: zoom-in; border-radius: var(--radius-control); }
.mindmap-preview figcaption { margin-top: var(--space-1); }
.ai-modal-container { max-width: var(--reading-width); }
.ai-modal-content { grid-template-columns: minmax(0, 1fr); }
.ai-modal-content .resource-header { grid-template-columns: var(--space-10) minmax(0, 1fr); }
.ai-modal-content .action-section { background: var(--surface); padding-top: 0; }
.ai-modal-content .action-buttons { flex-direction: row; flex-wrap: wrap; }
.arco-icon { flex-shrink: 0; font-size: var(--icon-size); }
.loading-icon { animation: spin calc(var(--motion-slow) * 4) linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 768px) {
  .modal-overlay { padding: var(--space-1); }
  .modal-container { max-height: calc(100vh - var(--space-2)); max-height: calc(100dvh - var(--space-2)); }
  .modal-toolbar { padding-inline: var(--space-2); }
  .modal-content { grid-template-columns: minmax(0, 1fr); }
  .resource-section, .action-section { padding: var(--space-2); }
  .resource-header, .ai-modal-content .resource-header { grid-template-columns: var(--space-8) minmax(0, 1fr); }
  .resource-stats { flex-direction: column; }
  .ai-modal-content .action-buttons { flex-direction: column; }
}
@media (prefers-reduced-motion: reduce) {
  .loading-icon { animation: none; }
  .btn, .close-btn { transition: none; }
}
</style>
