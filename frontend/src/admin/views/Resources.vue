<template>
  <div class="admin-resources">
    <ResourceSidebar @resource-clicked="focusReviewList" />
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">资源审核</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchResources">
            🔄 刷新
          </button>
        </div>
      </div>

      <!-- 状态筛选 -->
      <div class="filter-bar">
        <button
          v-for="status in statusFilters"
          :key="status.value"
          class="filter-btn"
          :class="{ active: selectedStatus === status.value }"
          @click="handleStatusFilter(status.value)"
        >
          {{ status.label }}
          <span class="count" v-if="statusCounts[status.value] !== undefined">({{ statusCounts[status.value] }})</span>
        </button>
      </div>

      <!-- 提示信息 -->
      <div v-if="selectedStatus === 'pending' && pendingCount > 0" class="info-bar">
        <span class="info-icon">ℹ️</span>
        <span class="info-text">只有待审核的资源可以进行审核操作</span>
      </div>
      <div v-else-if="selectedStatus !== 'pending'" class="info-bar">
        <span class="info-icon">ℹ️</span>
        <span class="info-text">已审核的资源无法再次操作，请切换到"待审核"标签进行审核</span>
      </div>
      <div v-else-if="pendingCount === 0" class="info-bar warning">
        <span class="info-icon">⚠️</span>
        <span class="info-text">当前没有待审核的资源</span>
      </div>

      <!-- 资源列表 -->
      <div v-if="loading" class="loading-state">
        <div class="loading-spinner"></div>
        <p>加载中...</p>
      </div>

      <div v-else-if="resources.length === 0" class="empty-state">
        <div class="empty-icon">📦</div>
        <p>{{ selectedStatus === 'pending' ? '暂无待审核资源' : '暂无资源' }}</p>
      </div>

      <div v-else class="resource-list">
        <div
          v-for="resource in resources"
          :key="resource.id"
          class="resource-item"
        >
          <div class="resource-cover">
            <img v-if="resource.cover_url" :src="resource.cover_url" />
            <div v-else class="cover-placeholder">
              <span>{{ getResourceTypeIcon(resource.resource_type) }}</span>
            </div>
          </div>
          <div class="resource-info">
            <div class="resource-header">
              <h4 class="resource-title">{{ resource.title }}</h4>
              <span class="status-badge" :class="`status-${resource.status}`">
                {{ getStatusText(resource.status) }}
              </span>
            </div>
            <p class="resource-description">{{ resource.description }}</p>
            <div class="resource-meta">
              <span class="meta-item">
                <strong>{{ resource.uploader_info?.username }}</strong>
              </span>
              <span class="meta-item">{{ resource.category }}</span>
              <span class="meta-item">{{ resource.resource_type_display }}</span>
              <span class="meta-item">{{ formatDate(resource.created_at) }}</span>
            </div>
          </div>
          <div class="resource-actions">
            <template v-if="resource.status === 'pending'">
              <button class="action-btn btn-success" @click="handleReview(resource, 'approved')">
                ✓ 通过
              </button>
              <button class="action-btn btn-danger" @click="handleReview(resource, 'rejected')">
                ✕ 拒绝
              </button>
            </template>
            <template v-else>
              <span class="reviewed-badge">已审核</span>
            </template>
            <button class="action-btn btn-default" @click="handlePreview(resource)">
              👁️ 查看
            </button>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="total > pageSize" class="pagination">
        <div class="pagination-info">共 {{ total }} 条记录</div>
        <div class="pagination-controls">
          <button class="action-btn btn-default" @click="changePage(page - 1)" :disabled="page === 1">
            上一页
          </button>
          <span>第 {{ page }} 页</span>
          <button class="action-btn btn-default" @click="changePage(page + 1)" :disabled="page * pageSize >= total">
            下一页
          </button>
        </div>
      </div>
    </div>

    <!-- 审核备注弹窗 -->
    <div v-if="showReviewModal" class="modal-overlay" @click.self="showReviewModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>审核备注</h3>
          <button class="close-btn" @click="showReviewModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="admin-form">
            <div class="form-group">
              <label class="form-label">
                {{ reviewAction === 'approved' ? '审核意见（可选）' : '拒绝原因（必填）' }}
              </label>
              <textarea
                v-model="reviewNote"
                class="form-textarea"
                rows="4"
                :placeholder="reviewAction === 'approved' ? '请输入审核意见...' : '请输入拒绝原因...'"
              ></textarea>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="showReviewModal = false">取消</button>
          <button class="action-btn" :class="reviewAction === 'approved' ? 'btn-success' : 'btn-danger'" @click="confirmReview" :disabled="reviewing">
            {{ reviewing ? '审核中...' : '确认' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 资源预览弹窗 -->
    <div v-if="showPreviewModal" class="modal-overlay" @click.self="showPreviewModal = false">
      <div class="modal-content modal-large">
        <div class="modal-header">
          <h3>资源详情</h3>
          <button class="close-btn" @click="showPreviewModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="preview-content">
            <div class="preview-cover">
              <img v-if="previewResource?.cover_url" :src="previewResource.cover_url" />
              <div v-else class="cover-placeholder">
                <span>{{ getResourceTypeIcon(previewResource?.resource_type) }}</span>
              </div>
            </div>
            <div class="preview-info">
              <h2>{{ previewResource?.title }}</h2>
              <div class="preview-badges">
                <span class="badge" :class="`type-${previewResource?.resource_type}`">
                  {{ previewResource?.resource_type_display }}
                </span>
                <span class="badge badge-primary">{{ previewResource?.category }}</span>
                <span class="badge" :class="`status-${previewResource?.status}`">
                  {{ getStatusText(previewResource?.status) }}
                </span>
              </div>
              <div class="preview-meta">
                <span>上传者: {{ previewResource?.uploader_info?.username }}</span>
                <span>上传时间: {{ formatDate(previewResource?.created_at) }}</span>
                <span>文件大小: {{ formatFileSize(previewResource?.file_size) }}</span>
                <span>查看: {{ previewResource?.view_count }}</span>
                <span>下载: {{ previewResource?.download_count }}</span>
              </div>
              <div class="preview-description">
                <h4>资源描述</h4>
                <p>{{ previewResource?.description }}</p>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="showPreviewModal = false">关闭</button>
          <button v-if="previewResource" class="action-btn btn-primary" @click="downloadResource">
            📥 下载文件
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import api from '@/api'
import ResourceSidebar from '@/components/ResourceSidebar.vue'

const resources = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const selectedStatus = ref('pending')

const statusFilters = [
  { label: '待审核', value: 'pending' },
  { label: '已通过', value: 'approved' },
  { label: '已拒绝', value: 'rejected' },
  { label: '全部', value: 'all' }
]

const statusCounts = ref({
  pending: 0,
  approved: 0,
  rejected: 0,
  all: 0
})

const showReviewModal = ref(false)
const reviewResource = ref(null)
const reviewAction = ref('')
const reviewNote = ref('')
const reviewing = ref(false)

const showPreviewModal = ref(false)
const previewResource = ref(null)

const pendingCount = computed(() => statusCounts.value.pending || 0)
const approvedCount = computed(() => statusCounts.value.approved || 0)
const rejectedCount = computed(() => statusCounts.value.rejected || 0)
const totalCount = computed(() => statusCounts.value.all || 0)

const focusReviewList = () => {
  document.querySelector('.page-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const fetchResources = async () => {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value
    }
    if (selectedStatus.value !== 'all') {
      params.status = selectedStatus.value
    }

    const response = await api.resource.adminList(params)
    resources.value = response.results || []
    total.value = response.count || 0
  } catch (error) {
    console.error('获取资源列表失败:', error)
  } finally {
    loading.value = false
  }
}

const fetchStatusCounts = async () => {
  try {
    // 获取各状态的资源数量
    const statuses = ['pending', 'approved', 'rejected']

    // 并行获取各状态的数量
    await Promise.all(statuses.map(async (status) => {
      const response = await api.resource.adminList({ page: 1, page_size: 1, status })
      statusCounts.value[status] = response.count || 0
    }))

    // 获取总数
    const allResponse = await api.resource.adminList({ page: 1, page_size: 1 })
    statusCounts.value.all = allResponse.count || 0
  } catch (error) {
    console.error('获取资源统计失败:', error)
  }
}

const handleStatusFilter = (status) => {
  selectedStatus.value = status
  page.value = 1
  fetchResources()
}

const handleReview = (resource, action) => {
  reviewResource.value = resource
  reviewAction.value = action
  reviewNote.value = ''
  showReviewModal.value = true
}

const confirmReview = async () => {
  if (reviewAction.value === 'rejected' && !reviewNote.value.trim()) {
    alert('请输入拒绝原因')
    return
  }

  reviewing.value = true
  try {
    await api.resource.review({
      resource_id: reviewResource.value.id,
      status: reviewAction.value,
      note: reviewNote.value
    })
    alert('审核成功')
    showReviewModal.value = false
    fetchResources()
    fetchStatusCounts()
  } catch (error) {
    console.error('审核失败:', error)
    alert('审核失败: ' + (error.response?.data?.error || '未知错误'))
  } finally {
    reviewing.value = false
  }
}

const handlePreview = (resource) => {
  previewResource.value = resource
  showPreviewModal.value = true
}

const downloadResource = async () => {
  if (!previewResource.value) return

  try {
    const response = await api.resource.download(previewResource.value.id)
    const contentDisposition = response.headers['content-disposition'] || ''
    const fileNameMatch = contentDisposition.match(/filename\*?=(?:UTF-8''|\")?([^;\"]+)/i)
    const fileName = fileNameMatch
      ? decodeURIComponent(fileNameMatch[1].trim())
      : previewResource.value.file_name || 'resource-download'
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    console.error('Resource download failed:', error)
  }
}

const changePage = (newPage) => {
  page.value = newPage
  fetchResources()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const getStatusText = (status) => {
  const map = {
    'pending': '待审核',
    'approved': '已通过',
    'rejected': '已拒绝'
  }
  return map[status] || status
}

const getResourceTypeIcon = (type) => {
  const icons = {
    'document': '📄',
    'video': '🎬',
    'report': '📊',
    'zip': '📦',
    'ai_resource': '✨'
  }
  return icons[type] || '📁'
}

const formatDate = (dateStr) => dateStr ? new Date(dateStr).toLocaleString('zh-CN') : ''

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i]
}

onMounted(() => {
  fetchResources()
  fetchStatusCounts()
})
</script>

<style scoped>
.admin-resources {
  padding: 24px;
}

.page-card {
  min-width: 0;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.info-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #e6f7ff;
  border: 1px solid #91d5ff;
  border-radius: 4px;
  margin-bottom: 16px;
  font-size: 14px;
  color: #0050b3;
}

.info-bar.warning {
  background: #fffbe6;
  border-color: #ffe58f;
  color: #d48806;
}

.info-icon {
  font-size: 16px;
}

.info-text {
  flex: 1;
}

.reviewed-badge {
  padding: 6px 12px;
  background: #f5f5f5;
  color: #999;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  text-align: center;
}

.filter-btn {
  padding: 8px 16px;
  border: 1px solid #d9d9d9;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.filter-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.filter-btn.active {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.count {
  font-size: 12px;
  opacity: 0.8;
}

.resource-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.resource-item {
  display: flex;
  gap: 16px;
  padding: 20px;
  background: #fafafa;
  border-radius: 8px;
  align-items: flex-start;
}

.resource-cover {
  width: 120px;
  height: 90px;
  border-radius: 6px;
  overflow: hidden;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  flex-shrink: 0;
}

.resource-cover img {
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
  font-size: 40px;
}

.resource-info {
  flex: 1;
  min-width: 0;
}

.resource-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.resource-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.status-pending {
  background: #fff7e6;
  color: #fa8c16;
}

.status-approved {
  background: #f6ffed;
  color: #52c41a;
}

.status-rejected {
  background: #fff1f0;
  color: #ff4d4f;
}

.resource-description {
  font-size: 14px;
  color: #666;
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
  gap: 12px;
  font-size: 13px;
  color: #999;
}

.resource-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.preview-content {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 24px;
}

.preview-cover {
  width: 200px;
  height: 150px;
  border-radius: 8px;
  overflow: hidden;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.preview-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preview-info h2 {
  font-size: 20px;
  margin-bottom: 12px;
}

.preview-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.type-document { background: rgba(24, 144, 255, 0.9); color: white; }
.type-video { background: rgba(250, 84, 28, 0.9); color: white; }
.type-report { background: rgba(82, 196, 26, 0.9); color: white; }
.type-zip { background: rgba(114, 46, 209, 0.9); color: white; }
.type-ai_resource { background: rgba(109, 74, 160, 0.9); color: white; }
.badge-primary { background: var(--primary-color); color: white; }

.preview-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 14px;
  color: #666;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid #f0f0f0;
}

.preview-description h4 {
  font-size: 14px;
  margin-bottom: 8px;
}

.preview-description p {
  font-size: 14px;
  line-height: 1.6;
  color: #333;
  white-space: pre-wrap;
}

.modal-large {
  max-width: 900px;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #f0f0f0;
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #f0f0f0;
}

.pagination-info {
  font-size: 14px;
  color: #666;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.action-btn {
  padding: 6px 16px;
  border: 1px solid #d9d9d9;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.action-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-success {
  background: #52c41a;
  color: white;
  border-color: #52c41a;
}

.btn-danger {
  background: #ff4d4f;
  color: white;
  border-color: #ff4d4f;
}

.btn-primary {
  background: var(--primary-color);
  color: white;
  border-color: var(--primary-color);
}

.btn-default {
  background: white;
  color: #333;
}

@media (max-width: 900px) {
  .admin-resources {
    padding: 16px;
  }
}
</style>
