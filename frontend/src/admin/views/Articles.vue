<template>
  <div class="admin-articles">
    <div class="page-card">
      <div class="page-header">
        <h3 class="page-title">{{ names.resourceReview }} · 文章</h3>
        <div class="page-actions">
          <button class="action-btn btn-default" @click="fetchArticles">
            <AppIcon name="bi-arrow-clockwise" /> 刷新
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

      <div v-else-if="readError" class="empty-state" role="alert"><p>{{ readError }}</p><button class="action-btn btn-default" @click="fetchArticles">重新读取</button></div>
      <div v-else-if="articles.length === 0" class="empty-state">
        <div class="empty-icon"><AppIcon name="bi-pencil-square" /></div>
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
            <div v-else class="cover-placeholder"><AppIcon name="bi-file-text" /></div>
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
              <span class="meta-item"><AppIcon name="bi-eye" /> {{ article.view_count }}</span>
              <span class="meta-item"><AppIcon name="bi-heart-fill" /> {{ article.like_count }}</span>
              <span class="meta-item"><AppIcon name="bi-chat-dots" /> {{ article.comment_count }}</span>
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
              <AppIcon name="bi-check2" /> 通过
            </button>
            <button class="action-btn btn-danger" @click="handleReview(article, 'rejected')" :disabled="article.status !== 'pending'">
              <AppIcon name="bi-x-lg" /> 拒绝
            </button>
            <button class="action-btn btn-default" @click="handlePreview(article)">
              <AppIcon name="bi-eye" /> 查看
            </button>
            <button class="action-btn btn-warning" @click="handleToggleRecommend(article)" :disabled="article.status !== 'approved'">
              {{ article.is_recommend ? '⭐ 取消推荐' : '⭐ 推荐' }}
            </button>
            <button class="action-btn btn-default" @click="handleToggleTop(article)" :disabled="article.status !== 'approved'">
              <AppIcon name="bi-pin-angle" /> {{ article.is_top ? '取消置顶' : '置顶' }}
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
          <button class="close-btn" @click="showReviewModal = false" aria-label="关闭"><AppIcon name="bi-x-lg" /></button>
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
          <button class="close-btn" @click="showPreviewModal = false" aria-label="关闭"><AppIcon name="bi-x-lg" /></button>
        </div>
        <div class="modal-body">
          <div class="preview-content">
            <h2 class="preview-title">{{ previewArticle?.title }}</h2>
            <div class="preview-badges">
              <span class="badge" :class="`status-${previewArticle?.status}`">
                {{ getStatusText(previewArticle?.status) }}
              </span>
              <span v-if="previewArticle?.is_top" class="badge badge-top"><AppIcon name="bi-pin-angle" /> 置顶</span>
              <span v-if="previewArticle?.is_recommend" class="badge badge-recommend"><AppIcon name="bi-star-fill" /> 推荐</span>
            </div>
            <div class="preview-meta">
              <span>作者: {{ previewArticle?.author?.username }}</span>
              <span>分类: {{ previewArticle?.category_name }}</span>
              <span>创建时间: {{ formatDate(previewArticle?.created_at) }}</span>
              <span><AppIcon name="bi-eye" /> {{ previewArticle?.view_count }}</span>
              <span><AppIcon name="bi-heart-fill" /> {{ previewArticle?.like_count }}</span>
              <span><AppIcon name="bi-chat-dots" /> {{ previewArticle?.comment_count }}</span>
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
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePageFilters } from '@/shared/state/usePageFilters.js'
import { createAccountGuard } from '@/shared/state/accountScope.js'
import api from '@/api'
import { names } from '@/shared/navigation/names.js'

const router = useRouter()
const route = useRoute()
const guard = createAccountGuard()
onBeforeUnmount(guard.dispose)
let request = 0

const articles = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const selectedStatus = ref('pending')
usePageFilters('admin-articles', { selectedStatus, page, pageSize })
const statuses = ['pending', 'approved', 'rejected', 'all']
if (statuses.includes(route.query.status)) { selectedStatus.value = route.query.status; page.value = 1 }
watch(() => route.query.status, status => {
  if (statuses.includes(status)) { selectedStatus.value = status; page.value = 1; fetchArticles() }
})

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

const readError = ref('')
const fetchArticles = async () => {
  const current = ++request
  loading.value = true
  readError.value = ''
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value
    }
    if (selectedStatus.value !== 'all') {
      params.status = selectedStatus.value
    }

    const response = await api.article.list(params)
    if (!guard.current() || current !== request) return
    articles.value = response.results || []
    total.value = response.count || 0
  } catch (error) {
    if (guard.current() && current === request) readError.value = '暂时无法读取文章，请重试。'
  } finally {
    if (guard.current() && current === request) loading.value = false
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
  padding:var(--space-3);
}

.filter-bar {
  display:flex;
  gap:var(--space-1);
  margin-bottom:var(--space-3);
  flex-wrap:wrap;
}

.filter-btn {
  padding:var(--space-1) var(--space-2);
  border:var(--stroke) solid var(--line);
  background:var(--surface);
  border-radius:var(--radius-control);
  cursor:pointer;
  font-size:var(--text-caption);
  transition:all var(--motion-normal);
  display:flex;
  align-items:center;
  gap:calc(var(--space-1) / 2);
}

.filter-btn:hover {
  border-color:var(--primary-color);
  color:var(--primary-color);
}

.filter-btn.active {
  background:var(--primary-color);
  color:var(--on-action);
  border-color:var(--primary-color);
}

.count {
  font-size:var(--text-caption);
  opacity:0.8;
}

.article-list {
  display:flex;
  flex-direction:column;
  gap:var(--space-2);
}

.article-item {
  display:flex;
  gap:var(--space-2);
  padding:var(--space-2);
  background:var(--surface);
  border-radius:var(--radius-control);
  align-items:flex-start;
}

.article-cover {
  width:var(--row-label-width);
  height:var(--thumbnail-short-height);
  border-radius:var(--radius-control);
  overflow:hidden;
  background: var(--surface-muted);
  flex-shrink:0;
}

.article-cover img {
  width:100%;
  height:100%;
  object-fit:cover;
}

.cover-placeholder {
  width:100%;
  height:100%;
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:var(--text-page);
}

.article-info {
  flex:1;
  min-width:0;
}

.article-header {
  display:flex;
  align-items:center;
  gap:var(--space-1);
  margin-bottom:var(--space-1);
}

.article-title {
  font-size:var(--text-body);
  font-weight: var(--weight-strong);
  margin:0;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}

.status-badge {
  padding:calc(var(--stroke) * 2) var(--space-1);
  border-radius:var(--radius-control);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
  white-space:nowrap;
}

.status-pending {
  background:var(--warning-soft);
  color:var(--warning);
}

.status-approved {
  background:var(--positive-soft);
  color:var(--positive);
}

.status-rejected {
  background:var(--negative-soft);
  color:var(--negative);
}

.article-summary {
  font-size:var(--text-caption);
  color:var(--ink-secondary);
  margin-bottom:var(--space-1);
  overflow:hidden;
  text-overflow:ellipsis;
  display:-webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.article-meta {
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-1);
  font-size:var(--text-caption);
  color:var(--ink-muted);
  margin-bottom:var(--space-1);
}

.article-tags {
  display:flex;
  flex-wrap:wrap;
  gap:calc(var(--space-1) / 2);
}

.tag {
  padding:calc(var(--stroke) * 2) var(--space-1);
  background:var(--surface);
  color:var(--primary-color);
  border-radius:var(--radius-panel);
  font-size:var(--text-caption);
}

.article-actions {
  display:flex;
  flex-direction:column;
  gap:var(--space-1);
  flex-shrink:0;
}

.preview-content h2 {
  font-size:var(--text-section);
  margin-bottom:var(--space-2);
}

.preview-badges {
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-1);
  margin-bottom:var(--space-2);
}

.badge {
  padding:calc(var(--space-1) / 2) var(--space-1);
  border-radius:var(--radius-panel);
  font-size:var(--text-caption);
  font-weight: var(--weight-strong);
}

.badge-top {
  background:var(--surface);
  color:var(--ink-secondary);
}

.badge-recommend {
  background:var(--surface);
  color:var(--ink-secondary);
}

.preview-meta {
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-2);
  font-size:var(--text-caption);
  color:var(--ink-secondary);
  margin-bottom:var(--space-2);
  padding-bottom:var(--space-2);
  border-bottom:var(--stroke) solid var(--line);
}

.preview-summary h4,
.preview-body h4 {
  font-size:var(--text-body);
  margin-bottom:var(--space-1);
  margin-top:var(--space-2);
}

.preview-summary p {
  font-size:var(--text-caption);
  color:var(--ink);
  line-height:1.6;
  margin-bottom:var(--space-2);
}

.preview-text {
  font-size:var(--text-caption);
  color:var(--ink);
  line-height:1.6;
  background:var(--surface);
  padding:var(--space-2);
  border-radius:var(--radius-control);
  white-space:pre-wrap;
}

.preview-tags {
  display:flex;
  flex-wrap:wrap;
  gap:var(--space-1);
  margin-top:var(--space-2);
}

.modal-large {
  max-width:var(--reading-width);
}

.loading-state,
.empty-state {
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  padding:var(--space-10) var(--space-2);
  text-align:center;
}

.loading-spinner {
  width:var(--space-5);
  height:var(--space-5);
  border:calc(var(--space-1) / 2) solid var(--line);
  border-top-color:var(--primary-color);
  border-radius:50%;
  animation:spin var(--motion-loop) linear infinite;
  margin-bottom:var(--space-2);
}

@keyframes spin {
  to { transform:rotate(360deg); }
}

.empty-icon {
  font-size:var(--text-page);
  margin-bottom:var(--space-2);
}

.pagination {
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin-top:var(--space-3);
  padding-top:var(--space-2);
  border-top:var(--stroke) solid var(--line);
}

.pagination-info {
  font-size:var(--text-caption);
  color:var(--ink-secondary);
}

.pagination-controls {
  display:flex;
  align-items:center;
  gap:var(--space-1);
}

.action-btn {
  padding:calc(var(--space-1) / 2) var(--space-2);
  border:var(--stroke) solid var(--line);
  background:var(--surface);
  border-radius:var(--radius-control);
  cursor:pointer;
  font-size:var(--text-caption);
  transition:all var(--motion-normal);
}

.action-btn:hover:not(:disabled) {
  opacity:0.85;
}

.action-btn:disabled {
  opacity:0.4;
  cursor:not-allowed;
}

.btn-success {
  background:var(--positive);
  color:var(--on-action);
  border-color:var(--positive);
}

.btn-danger {
  background:var(--negative);
  color:var(--on-action);
  border-color:var(--negative);
}

.btn-warning {
  background:var(--warning);
  color:var(--on-action);
  border-color:var(--warning);
}

.btn-primary {
  background:var(--primary-color);
  color:var(--on-action);
  border-color:var(--primary-color);
}

.btn-default {
  background:var(--surface);
  color:var(--ink);
}
</style>
