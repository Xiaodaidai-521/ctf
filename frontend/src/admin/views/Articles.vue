<template>
  <div class="admin-articles">
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">文章审核</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchArticles">
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

      <!-- 文章列表 -->
      <div v-if="loading" class="loading-state">
        <div class="loading-spinner"></div>
        <p>加载中...</p>
      </div>

      <div v-else-if="articles.length === 0" class="empty-state">
        <div class="empty-icon">📝</div>
        <p>{{ selectedStatus === 'pending' ? '暂无待审核文章' : '暂无文章' }}</p>
      </div>

      <div v-else class="article-list">
        <div
          v-for="article in articles"
          :key="article.id"
          class="article-item"
        >
          <div class="article-cover">
            <img v-if="article.cover" :src="article.cover" />
            <div v-else class="cover-placeholder">📄</div>
          </div>
          <div class="article-info">
            <div class="article-header">
              <h4 class="article-title">{{ article.title }}</h4>
              <span class="status-badge" :class="`status-${article.status}`">
                {{ getStatusText(article.status) }}
              </span>
            </div>
            <p class="article-summary">{{ article.summary || article.title }}</p>
            <div class="article-meta">
              <span class="meta-item">
                <strong>{{ article.author?.username }}</strong>
              </span>
              <span class="meta-item">{{ article.category_name }}</span>
              <span class="meta-item">{{ formatDate(article.created_at) }}</span>
              <span class="meta-item">👁️ {{ article.view_count }}</span>
              <span class="meta-item">❤️ {{ article.like_count }}</span>
              <span class="meta-item">💬 {{ article.comment_count }}</span>
            </div>
            <div v-if="article.tags_list?.length" class="article-tags">
              <span
                v-for="tag in article.tags_list.slice(0, 3)"
                :key="tag"
                class="tag"
              >
                #{{ tag }}
              </span>
            </div>
          </div>
          <div class="article-actions">
            <button class="action-btn btn-success" @click="handleReview(article, 'approved')" :disabled="article.status !== 'pending'">
              ✓ 通过
            </button>
            <button class="action-btn btn-danger" @click="handleReview(article, 'rejected')" :disabled="article.status !== 'pending'">
              ✕ 拒绝
            </button>
            <button class="action-btn btn-default" @click="handlePreview(article)">
              👁️ 查看
            </button>
            <button class="action-btn btn-warning" @click="handleToggleRecommend(article)" :disabled="article.status !== 'approved'">
              {{ article.is_recommend ? '⭐ 取消推荐' : '⭐ 推荐' }}
            </button>
            <button class="action-btn btn-default" @click="handleToggleTop(article)" :disabled="article.status !== 'approved'">
              {{ article.is_top ? '🔝 取消置顶' : '🔝 置顶' }}
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

    <!-- 文章预览弹窗 -->
    <div v-if="showPreviewModal" class="modal-overlay" @click.self="showPreviewModal = false">
      <div class="modal-content modal-large">
        <div class="modal-header">
          <h3>文章预览</h3>
          <button class="close-btn" @click="showPreviewModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="preview-content">
            <h2 class="preview-title">{{ previewArticle?.title }}</h2>
            <div class="preview-badges">
              <span class="badge" :class="`status-${previewArticle?.status}`">
                {{ getStatusText(previewArticle?.status) }}
              </span>
              <span v-if="previewArticle?.is_top" class="badge badge-top">🔝 置顶</span>
              <span v-if="previewArticle?.is_recommend" class="badge badge-recommend">⭐ 推荐</span>
            </div>
            <div class="preview-meta">
              <span>作者: {{ previewArticle?.author?.username }}</span>
              <span>分类: {{ previewArticle?.category_name }}</span>
              <span>创建时间: {{ formatDate(previewArticle?.created_at) }}</span>
              <span>👁️ {{ previewArticle?.view_count }}</span>
              <span>❤️ {{ previewArticle?.like_count }}</span>
              <span>💬 {{ previewArticle?.comment_count }}</span>
            </div>
            <div v-if="previewArticle?.summary" class="preview-summary">
              <h4>摘要</h4>
              <p>{{ previewArticle.summary }}</p>
            </div>
            <div class="preview-body">
              <h4>内容预览（前500字）</h4>
              <div class="preview-text">{{ previewArticle?.content?.substring(0, 500) }}...</div>
            </div>
            <div v-if="previewArticle?.tags_list?.length" class="preview-tags">
              <span
                v-for="tag in previewArticle.tags_list"
                :key="tag"
                class="tag"
              >
                #{{ tag }}
              </span>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="action-btn btn-default" @click="showPreviewModal = false">关闭</button>
          <button class="action-btn btn-primary" @click="goToArticle">
            查看完整文章
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'

const router = useRouter()

const articles = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const selectedStatus = ref('pending')

const statusFilters = [
  { label: '待审核', value: 'pending' },
  { label: '已发布', value: 'approved' },
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
const reviewArticle = ref(null)
const reviewAction = ref('')
const reviewNote = ref('')
const reviewing = ref(false)

const showPreviewModal = ref(false)
const previewArticle = ref(null)

const fetchArticles = async () => {
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value
    }
    if (selectedStatus.value !== 'all') {
      params.status = selectedStatus.value
    }

    const response = await api.article.list(params)
    articles.value = response.results || []
    total.value = response.count || 0
  } catch (error) {
    console.error('获取文章列表失败:', error)
  } finally {
    loading.value = false
  }
}

const fetchStatusCounts = async () => {
  try {
    // 获取各状态文章数量
    const [pendingRes, approvedRes, rejectedRes] = await Promise.all([
      api.article.list({ status: 'pending', page: 1, page_size: 1 }),
      api.article.list({ status: 'approved', page: 1, page_size: 1 }),
      api.article.list({ status: 'rejected', page: 1, page_size: 1 })
    ])
    statusCounts.value = {
      pending: pendingRes.count || 0,
      approved: approvedRes.count || 0,
      rejected: rejectedRes.count || 0,
      all: (pendingRes.count || 0) + (approvedRes.count || 0) + (rejectedRes.count || 0)
    }
  } catch (error) {
    console.error('获取文章统计失败:', error)
  }
}

const handleStatusFilter = (status) => {
  selectedStatus.value = status
  page.value = 1
  fetchArticles()
}

const handleReview = (article, action) => {
  reviewArticle.value = article
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
    await api.article.review(reviewArticle.value.id, {
      status: reviewAction.value,
      note: reviewNote.value
    })
    alert('审核成功')
    showReviewModal.value = false
    fetchArticles()
    fetchStatusCounts()
  } catch (error) {
    console.error('审核失败:', error)
    alert('审核失败: ' + (error.response?.data?.error || '未知错误'))
  } finally {
    reviewing.value = false
  }
}

const handlePreview = (article) => {
  previewArticle.value = article
  showPreviewModal.value = true
}

const handleToggleRecommend = async (article) => {
  try {
    article.is_recommend = !article.is_recommend
    await api.article.update(article.id, {
      is_recommend: article.is_recommend
    })
    alert(article.is_recommend ? '已推荐' : '已取消推荐')
    fetchArticles()
  } catch (error) {
    console.error('操作失败:', error)
    alert('操作失败')
  }
}

const handleToggleTop = async (article) => {
  try {
    article.is_top = !article.is_top
    await api.article.update(article.id, {
      is_top: article.is_top
    })
    alert(article.is_top ? '已置顶' : '已取消置顶')
    fetchArticles()
  } catch (error) {
    console.error('操作失败:', error)
    alert('操作失败')
  }
}

const goToArticle = () => {
  if (previewArticle.value) {
    router.push(`/community/article/${previewArticle.value.id}`)
  }
}

const changePage = (newPage) => {
  page.value = newPage
  fetchArticles()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const getStatusText = (status) => {
  const map = {
    'pending': '待审核',
    'approved': '已发布',
    'rejected': '已拒绝'
  }
  return map[status] || status
}

const formatDate = (dateStr) => dateStr ? new Date(dateStr).toLocaleString('zh-CN') : ''

onMounted(() => {
  fetchArticles()
  fetchStatusCounts()
})
</script>

<style scoped>
.admin-articles {
  padding: 24px;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
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

.article-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.article-item {
  display: flex;
  gap: 16px;
  padding: 20px;
  background: #fafafa;
  border-radius: 8px;
  align-items: flex-start;
}

.article-cover {
  width: 120px;
  height: 90px;
  border-radius: 6px;
  overflow: hidden;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  flex-shrink: 0;
}

.article-cover img {
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

.article-info {
  flex: 1;
  min-width: 0;
}

.article-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.article-title {
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

.article-summary {
  font-size: 14px;
  color: #666;
  margin-bottom: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.article-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 13px;
  color: #999;
  margin-bottom: 8px;
}

.article-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  padding: 2px 8px;
  background: #e6f7ff;
  color: var(--primary-color);
  border-radius: 12px;
  font-size: 11px;
}

.article-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.preview-content h2 {
  font-size: 24px;
  margin-bottom: 16px;
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

.badge-top {
  background: #fff7e6;
  color: #fa8c16;
}

.badge-recommend {
  background: #f6ffed;
  color: #52c41a;
}

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

.preview-summary h4,
.preview-body h4 {
  font-size: 16px;
  margin-bottom: 8px;
  margin-top: 20px;
}

.preview-summary p {
  font-size: 14px;
  color: #333;
  line-height: 1.6;
  margin-bottom: 20px;
}

.preview-text {
  font-size: 14px;
  color: #333;
  line-height: 1.6;
  background: #fafafa;
  padding: 16px;
  border-radius: 6px;
  white-space: pre-wrap;
}

.preview-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 20px;
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

.btn-warning {
  background: #faad14;
  color: white;
  border-color: #faad14;
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
</style>
