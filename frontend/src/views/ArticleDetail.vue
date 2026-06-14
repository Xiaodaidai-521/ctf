<template>
  <div class="article-detail-page">
    <div class="detail-container">
      <!-- 返回按钮 -->
      <div class="back-nav">
        <button class="back-btn" @click="goBack">
          <span>← 返回</span>
        </button>
      </div>

      <!-- 左侧文章内容区 -->
      <div class="article-main">
        <!-- 文章头部 -->
        <div class="article-header">
          <h1 class="article-title">{{ article?.title }}</h1>

          <div class="article-meta">
            <div class="author-section">
              <div class="author-avatar">
                {{ article?.author?.username?.charAt(0) || 'U' }}
              </div>
              <div class="author-info">
                <span class="author-name">{{ article?.author?.username }}</span>
                <span class="publish-time">{{ formatTime(article?.published_at || article?.created_at) }}</span>
              </div>
            </div>

            <div class="article-actions">
              <button
                class="action-btn"
                :class="{ active: article?.is_liked }"
                @click="handleLike"
              >
                <span>{{ article?.is_liked ? '❤️' : '🤍' }}</span>
                {{ article?.like_count || 0 }}
              </button>
              <button
                class="action-btn"
                :class="{ active: article?.is_collected }"
                @click="handleCollect"
              >
                <span>{{ article?.is_collected ? '⭐' : '☆' }}</span>
                {{ article?.collect_count || 0 }}
              </button>
              <button class="action-btn" @click="handleShare">
                <span>🔗</span>
                分享
              </button>
            </div>
          </div>

          <div class="article-badges">
            <span v-if="article?.is_top" class="badge badge-top">🔝 置顶</span>
            <span v-if="article?.is_recommend" class="badge badge-recommend">⭐ 推荐</span>
            <span v-if="article?.category_name" class="badge badge-category">
              {{ article?.category_name }}
            </span>
            <span class="badge badge-views">👁️ {{ article?.view_count }} 阅读</span>
          </div>
        </div>

        <!-- 文章内容 -->
        <div v-if="loading" class="loading-state">
          <div class="loading-spinner"></div>
          <p>加载中...</p>
        </div>

        <div v-else class="article-content markdown-body">
          <div v-html="renderedContent"></div>
        </div>

        <!-- 文章标签 -->
        <div v-if="article?.tags_list?.length" class="article-tags-section">
          <span
            v-for="tag in article.tags_list"
            :key="tag"
            class="tag"
          >
            #{{ tag }}
          </span>
        </div>

        <!-- 分隔线 -->
        <div class="divider"></div>

        <!-- 评论区 -->
        <div class="comments-section">
          <div class="comments-header">
            <h3>评论 ({{ article?.comment_count || 0 }})</h3>
          </div>

          <!-- 评论输入框 -->
          <div class="comment-input-box">
            <textarea
              v-model="newComment"
              class="comment-textarea"
              placeholder="写下你的评论..."
              rows="4"
            ></textarea>
            <div class="comment-actions">
              <button
                class="submit-btn"
                :disabled="!newComment.trim() || submitting"
                @click="handleSubmitComment"
              >
                {{ submitting ? '发布中...' : '发表评论' }}
              </button>
            </div>
          </div>

          <!-- 评论列表 -->
          <div v-if="loadingComments" class="loading-state">
            <div class="loading-spinner small"></div>
            <p>加载评论中...</p>
          </div>

          <div v-else-if="comments.length === 0" class="empty-comments">
            <div class="empty-icon">💬</div>
            <p>还没有评论，快来发表第一条吧</p>
          </div>

          <div v-else class="comments-list">
            <CommentItem
              v-for="comment in comments"
              :key="comment.id"
              :comment="comment"
              @reply="handleReply"
              @like="handleCommentLike"
              @delete="handleDeleteComment"
            />
          </div>
        </div>
      </div>

      <!-- 右侧侧边栏 -->
      <div class="sidebar">
        <!-- 作者信息 -->
        <div class="sidebar-card author-card">
          <div class="card-header">
            <h3>作者信息</h3>
          </div>
          <div class="author-card-content">
            <div class="author-large-avatar">
              {{ article?.author?.username?.charAt(0) || 'U' }}
            </div>
            <h4 class="author-name">{{ article?.author?.username }}</h4>
            <p class="author-nickname">{{ article?.author?.nickname || '暂无昵称' }}</p>
            <div class="author-stats">
              <span>文章 {{ articleCount }}</span>
              <span>粉丝 0</span>
            </div>
            <button class="follow-btn" @click="handleFollow">+ 关注</button>
          </div>
        </div>

        <!-- 相关推荐 -->
        <div class="sidebar-card">
          <div class="card-header">
            <h3>相关推荐</h3>
          </div>
          <div v-if="relatedArticles.length > 0" class="related-articles">
            <div
              v-for="item in relatedArticles"
              :key="item.id"
              class="related-item"
              @click="goToArticle(item.id)"
            >
              <img v-if="item.cover" :src="item.cover" class="related-cover" />
              <div v-else class="related-cover related-cover-placeholder">
                {{ item.title.charAt(0) }}
              </div>
              <div class="related-info">
                <h5 class="related-title">{{ item.title }}</h5>
                <div class="related-meta">
                  <span class="related-tag">{{ item.category_name || '未分类' }}</span>
                  <span class="related-stats">👁️ {{ item.view_count }}</span>
                </div>
                <span class="related-time">{{ formatTime(item.published_at || item.created_at) }}</span>
              </div>
            </div>
          </div>
          <div v-else class="empty-related">
            <div class="empty-icon">📚</div>
            <p>暂无相关推荐</p>
          </div>
        </div>

        <!-- 文章统计 -->
        <div class="sidebar-card">
          <div class="card-header">
            <h3>文章统计</h3>
          </div>
          <div class="stats-list">
            <div class="stat-row">
              <span>阅读量</span>
              <strong>{{ article?.view_count || 0 }}</strong>
            </div>
            <div class="stat-row">
              <span>点赞数</span>
              <strong>{{ article?.like_count || 0 }}</strong>
            </div>
            <div class="stat-row">
              <span>评论数</span>
              <strong>{{ article?.comment_count || 0 }}</strong>
            </div>
            <div class="stat-row">
              <span>收藏数</span>
              <strong>{{ article?.collect_count || 0 }}</strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import api from '@/api'
import CommentItem from '@/components/CommentItem.vue'

const route = useRoute()
const router = useRouter()

const article = ref(null)
const comments = ref([])
const relatedArticles = ref([])
const loading = ref(false)
const loadingComments = ref(false)
const submitting = ref(false)
const newComment = ref('')
const articleCount = ref(0)

// 配置 marked
marked.setOptions({
  highlight: function(code, lang) {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext'
    return hljs.highlight(code, { language }).value
  },
  langPrefix: 'hljs language-'
})

const renderedContent = computed(() => {
  if (!article.value?.content) return ''
  try {
    return marked.parse(article.value.content)
  } catch (error) {
    console.error('Markdown 解析失败:', error)
    return article.value.content
  }
})

const fetchArticle = async () => {
  loading.value = true
  try {
    article.value = await api.article.detail(route.params.id)
    document.title = `${article.value.title} - 社区`
  } catch (error) {
    console.error('获取文章详情失败:', error)
    alert('文章不存在或已被删除')
    router.push('/community')
  } finally {
    loading.value = false
  }
}

const fetchComments = async () => {
  loadingComments.value = true
  try {
    const data = await api.comment.list({ article: route.params.id })
    comments.value = data.results || []
  } catch (error) {
    console.error('获取评论失败:', error)
  } finally {
    loadingComments.value = false
  }
}

const fetchRelatedArticles = async () => {
  try {
    // 先获取推荐文章（基于标记为推荐的文章）
    const recommendData = await api.article.recommend({ limit: 6 })
    
    // 再获取同分类的文章
    const categoryId = article.value?.category
    const categoryData = await api.article.list({
      category: categoryId,
      status: 'approved',
      page: 1,
      page_size: 6
    })

    // 合并推荐文章和同分类文章，去重
    const allArticles = [
      ...(recommendData.results || []),
      ...(categoryData.results || [])
    ]

    // 去重并排除当前文章
    const uniqueArticles = []
    const seenIds = new Set()
    for (const item of allArticles) {
      if (item.id !== article.value.id && !seenIds.has(item.id)) {
        seenIds.add(item.id)
        uniqueArticles.push(item)
      }
    }

    // 取前5篇
    relatedArticles.value = uniqueArticles.slice(0, 5)
    
    // 更新作者文章数
    articleCount.value = categoryData.count || 0
  } catch (error) {
    console.error('获取相关文章失败:', error)
    relatedArticles.value = []
  }
}

const handleLike = async () => {
  if (!article.value) return
  try {
    const result = await api.article.like(article.value.id)
    article.value.is_liked = result.liked
    article.value.like_count = result.like_count
  } catch (error) {
    console.error('点赞失败:', error)
  }
}

const handleCollect = async () => {
  if (!article.value) return
  try {
    const result = await api.article.collect(article.value.id)
    article.value.is_collected = result.collected
    article.value.collect_count = result.collect_count
  } catch (error) {
    console.error('收藏失败:', error)
  }
}

const handleShare = () => {
  const url = window.location.href
  navigator.clipboard.writeText(url).then(() => {
    alert('链接已复制到剪贴板')
  })
}

const handleSubmitComment = async () => {
  if (!newComment.value.trim()) return

  submitting.value = true
  try {
    await api.comment.create({
      article: route.params.id,
      content: newComment.value
    })
    newComment.value = ''
    article.value.comment_count++
    fetchComments()
  } catch (error) {
    console.error('发表评论失败:', error)
    alert('发表评论失败')
  } finally {
    submitting.value = false
  }
}

const handleReply = (parentId) => {
  // 回复已成功提交，刷新评论列表
  article.value.comment_count++
  fetchComments()
}

const handleCommentLike = async (commentId) => {
  try {
    await api.comment.like(commentId)
    fetchComments()
  } catch (error) {
    console.error('点赞评论失败:', error)
  }
}

const handleDeleteComment = async (commentId) => {
  if (!confirm('确定要删除这条评论吗？')) return

  try {
    await api.comment.delete(commentId)
    article.value.comment_count--
    fetchComments()
  } catch (error) {
    console.error('删除评论失败:', error)
    alert('删除失败')
  }
}

const handleFollow = () => {
  alert('关注功能开发中...')
}

const goBack = () => {
  router.back()
}

const goToArticle = (id) => {
  router.push(`/community/article/${id}`)
}

const formatTime = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

watch(() => route.params.id, (newId) => {
  if (newId) {
    fetchArticle()
    fetchComments()
    fetchRelatedArticles()
  }
}, { immediate: true })

onMounted(() => {
  fetchArticle()
  fetchComments()
  fetchRelatedArticles()
})
</script>

<style scoped>
.article-detail-page {
  max-width: 1400px;
  margin: 24px auto 32px;
  padding: 0 24px;
}

.detail-container {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 24px;
}

.article-main {
  background: white;
  border-radius: var(--radius-md);
  padding: 24px;
  box-shadow: var(--shadow-sm);
}

.article-header {
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 2px solid #f0f0f0;
}

.article-title {
  font-size: 32px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.4;
  margin-bottom: 20px;
}

.article-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 16px;
}

.author-section {
  display: flex;
  align-items: center;
  gap: 12px;
}

.author-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 16px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
}

.author-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.author-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.publish-time {
  font-size: 12px;
  color: var(--text-secondary);
}

.article-actions {
  display: flex;
  gap: 12px;
}

.action-btn {
  padding: 8px 16px;
  border: 1px solid #e8e8e8;
  border-radius: var(--radius-sm);
  background: white;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.3s;
}

.action-btn:hover {
  background: #f5f5f5;
  border-color: #d9d9d9;
}

.action-btn.active {
  background: #fff7e6;
  border-color: #ffc53d;
}

.article-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.badge-top {
  background: #fff7e6;
  color: #fa8c16;
}

.badge-recommend {
  background: #f6ffed;
  color: #52c41a;
}

.badge-category {
  background: #e6f7ff;
  color: var(--primary-color);
}

.badge-views {
  background: #f5f5f5;
  color: var(--text-secondary);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  gap: 16px;
  color: var(--text-secondary);
}

.loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #f0f0f0;
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-spinner.small {
  width: 32px;
  height: 32px;
  border-width: 3px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.article-content {
  font-size: 16px;
  line-height: 1.8;
  color: var(--text-primary);
  margin-bottom: 32px;
}

.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: var(--radius-sm);
}

.markdown-body :deep(pre) {
  background: #f6f8fa;
  border-radius: 6px;
  padding: 16px;
  overflow-x: auto;
}

.markdown-body :deep(code) {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 14px;
}

.markdown-body :deep(p) {
  margin-bottom: 16px;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
}

.markdown-body :deep(h1) {
  font-size: 28px;
}

.markdown-body :deep(h2) {
  font-size: 24px;
}

.markdown-body :deep(h3) {
  font-size: 20px;
}

.markdown-body :deep(blockquote) {
  border-left: 4px solid var(--primary-color);
  padding-left: 16px;
  margin: 16px 0;
  color: var(--text-secondary);
}

.article-tags-section {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 32px;
}

.tag {
  padding: 6px 14px;
  background: #e6f7ff;
  color: var(--primary-color);
  border-radius: 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.3s;
}

.tag:hover {
  background: #bae7ff;
}

.divider {
  height: 2px;
  background: #f0f0f0;
  margin: 32px 0;
}

.comments-section {
  margin-top: 32px;
}

.comments-header {
  margin-bottom: 20px;
}

.comments-header h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.comment-input-box {
  margin-bottom: 32px;
  padding: 20px;
  background: #f9f9f9;
  border-radius: var(--radius-sm);
}

.comment-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #e8e8e8;
  border-radius: var(--radius-sm);
  font-size: 14px;
  resize: vertical;
  min-height: 100px;
  margin-bottom: 12px;
}

.comment-textarea:focus {
  outline: none;
  border-color: var(--primary-color);
}

.comment-actions {
  display: flex;
  justify-content: flex-end;
}

.submit-btn {
  padding: 8px 24px;
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.submit-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.empty-comments {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.sidebar {
  position: sticky;
  top: 80px;
  height: fit-content;
}

.sidebar-card {
  background: white;
  border-radius: var(--radius-md);
  padding: 20px;
  margin-bottom: 16px;
  box-shadow: var(--shadow-sm);
}

.card-header {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.card-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.author-card-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.author-large-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 28px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
}

.author-name {
  font-size: 16px;
  font-weight: 600;
}

.author-nickname {
  font-size: 13px;
  color: var(--text-secondary);
}

.author-stats {
  display: flex;
  gap: 24px;
  font-size: 13px;
  color: var(--text-secondary);
}

.follow-btn {
  padding: 8px 24px;
  background: var(--primary-color);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
}

.follow-btn:hover {
  opacity: 0.9;
}

.related-articles {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.related-item {
  display: flex;
  gap: 12px;
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  border: 1px solid transparent;
}

.related-item:hover {
  background: #f9f9f9;
  border-color: #e8e8e8;
  transform: translateX(2px);
}

.related-cover {
  width: 80px;
  height: 60px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
}

.related-cover-placeholder {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 24px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
}

.related-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.related-title {
  font-size: 14px;
  font-weight: 500;
  margin: 0;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.related-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.related-tag {
  padding: 2px 8px;
  background: #f0f0f0;
  color: #666;
  border-radius: 4px;
  font-size: 11px;
}

.related-stats {
  font-size: 11px;
  color: #999;
}

.related-time {
  font-size: 11px;
  color: #ccc;
}

.empty-related {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #999;
}

.empty-related .empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.stats-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.stat-row:last-child {
  border-bottom: none;
}

.stat-row span {
  font-size: 14px;
  color: var(--text-secondary);
}

.stat-row strong {
  font-size: 16px;
  color: var(--text-primary);
}

.back-nav {
  margin-bottom: 8px;
  grid-column: 1 / -1;
}

.back-btn {
  padding: 6px 12px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: all 0.3s;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: fit-content;
}

.back-btn:hover {
  background: #f5f5f5;
  color: var(--primary-color);
  border-color: var(--primary-color);
}

@media (max-width: 1024px) {
  .detail-container {
    grid-template-columns: 1fr;
  }

  .sidebar {
    display: none;
  }

  .article-title {
    font-size: 24px;
  }
}
</style>
